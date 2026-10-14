"""Real QML geometry regression with live RAM and test-only Optimize fixtures."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from qa_support import QA_ROOT, qa_path

parser = argparse.ArgumentParser()
parser.add_argument("--theme", choices=("light", "dark"), default="light")
parser.add_argument("--scale", type=float, default=1)
parser.add_argument("--automatic", action="store_true")
args = parser.parse_args()
native_env = dict(os.environ)
native_env.pop("QT_SCALE_FACTOR", None)
native_scale = float(subprocess.check_output([
    sys.executable, "-c",
    "from PySide6.QtGui import QGuiApplication; a=QGuiApplication([]); print(a.primaryScreen().devicePixelRatio())",
], env=native_env, text=True).strip())
os.environ["QT_SCALE_FACTOR"] = str(args.scale / native_scale)

from PySide6.QtCore import QObject, QPointF, Qt, QMetaObject, QEvent, qInstallMessageHandler
from PySide6.QtGui import QGuiApplication, QKeyEvent
from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
from main import create_engine, dispose_engine
from backend.controller import MemoryController
from backend.settings import SettingsController

messages, checks = [], []
qInstallMessageHandler(lambda kind, context, message: messages.append(message))
gate, stopped = threading.Event(), threading.Event()
scenario = {}
stage_messages = {
    "Standard": ["trimming apps"],
    "Deep": ["trimming apps", "cleaning system memory"],
    "Maximum": ["combining identical pages", "trimming apps", "flushing file cache",
                "writing dirty pages to disk", "purging standby", "settling"],
}

def fixture(mode, progress):
    case, texts = scenario["case"], list(scenario["messages"])
    for text in texts:
        if stopped.is_set():
            return {"error": "QA stopped"}
        gate.clear()
        progress(text)
        if not gate.wait(15):
            raise RuntimeError("QA stage was not released")
    if case == "error":
        raise RuntimeError("QA simulated error. " * 30)
    gain = 0 if case == "zero" else 350
    detail = "QA long detail with multiple words. " * (30 if case == "long" else 1)
    return dict(supported=True, engine="maximum" if mode == "Maximum" else "v2", elevated=True,
                available_before_mb=2800, available_after_mb=2800 + gain, available_delta_mb=gain,
                duration_s=.5, trimmed=4, failed=0, free_delta_mb=100,
                steps=[dict(name=name, ok=True, detail=detail) for name in ("Combine", "File cache", "Modified", "Standby")],
                deep_steps=[dict(name="System memory", ok=True, detail=detail)],
                targets=[dict(name="QA application", ok=True, reason=detail)])

QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.OpenGL)
app = QGuiApplication([])
app.setQuitOnLastWindowClosed(False)
preferences = SettingsController(args.theme, Path(tempfile.gettempdir()) / "thrashing-geometry-qa" / "settings.json")
preferences.setAnimations(False)
memory = MemoryController(runner=fixture, hold_ms=50)
engine, memory, preferences = create_engine(app, controller=memory, settings=preferences)

def pump(seconds=.02):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        app.processEvents()
        time.sleep(.003)

def wait_for(predicate, timeout=10):
    until = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < until, "Timed out waiting for QA state"
        pump(.005)

def find(name):
    item = window.findChild(QObject, name)
    assert item is not None, name
    return item

def geometry():
    c = card.mapToItem(dashboard, QPointF(0, 0))
    p = plot.mapToItem(card, QPointF(0, 0))
    return [c.x(), c.y(), card.width(), card.height(), p.x(), p.y(), plot.width(), plot.height()]

def check(label):
    current = geometry()
    assert all(abs(a - b) <= .6 for a, b in zip(current, baseline)), (label, baseline, current)
    assert abs(plot.height() - card.property("plotHeight")) <= .6
    checks.append(dict(view=view, motion=preferences.animations, mode=memory.selectedMode,
                       case=scenario.get("case", "idle"), phase=label, geometry=current))

def shot(label):
    assert not preferences.animations, "Capture static screenshots only"
    image = window.grabWindow()
    target = QA_ROOT / "screenshots" / f"history_stable_{args.theme}_{args.scale:g}_{view}_{label}.png"
    assert not image.isNull() and image.save(str(target))

def click(name):
    assert QMetaObject.invokeMethod(find(name), "clicked", Qt.QueuedConnection)
    pump(.03)

def expire_events():
    for event in memory._events:
        event["startedAt"] = time.time() - 150
        event["finishedAt"] = time.time() - 121
    memory.refresh()  # Exercise real expiry/filtering and its signal.
    pump()
    assert not memory.optimizationEvents
    check("events expired")

try:
    pump(1)
    window = next(w for w in app.allWindows() if w.objectName() == "mainWindow")
    window.setTitle("Geometry QA — live RAM / simulated Optimize")
    assert abs(window.devicePixelRatio() - args.scale) < .01
    plot = find("historyCanvas")
    card = plot.parentItem().parentItem().parentItem()
    dashboard = find("dashboard")
    scroll = find("mainScroll")
    flick = scroll.property("contentItem")
    boundary = round(window.width() + 900 - scroll.property("availableWidth"))
    views = [("default", 1180, 740), ("minimum", 900, 640),
             ("below_breakpoint", boundary - 1, 740), ("above_breakpoint", boundary + 1, 740),
             ("maximized", None, None)]
    default_plot_height = None
    for view, width, height in views:
        if width is None:
            window.showMaximized()
        else:
            window.showNormal()
            window.resize(width, height)
        pump(.12)
        flick.setProperty("contentY", 0)
        baseline = geometry()
        expected = max(168, min(360, int((168 + (window.height() - 740) * .4) / 8 + .5) * 8))
        assert abs(plot.height() - expected) < .6, (view, plot.height(), expected)
        if view == "default":
            default_plot_height = plot.height()
        if view == "below_breakpoint":
            assert not window.property("wide")
        if view == "above_breakpoint":
            assert window.property("wide")
        if window.property("wide"):
            assert abs(card.width() - int((scroll.property("availableWidth") - 20) * .64)) < .6
        else:
            assert abs(card.width() - scroll.property("availableWidth")) < .6
        for animated in (False, True):
            preferences.setAnimations(animated)
            for mode, case in [("Standard", "success"), ("Deep", "success"), ("Maximum", "success"),
                               ("Maximum", "zero"), ("Maximum", "error"), ("Maximum", "long")]:
                wait_for(lambda: not memory.busy and memory._thread is None)
                memory.setMode("Standard" if args.automatic else mode)
                texts = stage_messages[mode]
                if case == "long":
                    texts = [text + ": " + "QA detailed progress with several words. " * 30 for text in texts]
                scenario.update(case=case, messages=texts)
                check("before start")
                if view == "default" and not animated and mode == "Maximum" and case == "success":
                    shot("before")
                actual_hold = args.theme == "light" and args.scale == 1 and view == "default" and not animated and mode == "Standard"
                memory._hold_ms = 3000 if actual_hold else 50
                if args.automatic:
                    assert memory.startAutomaticOptimization(mode, "QA geometry trigger")
                else:
                    memory.startOptimization()
                check("start")
                assert memory.running and not find("optimizeButton").property("enabled")
                run_id = memory.operation["id"]
                memory.startOptimization()
                assert memory.operation["id"] == run_id, "Duplicate run started"
                for index, text in enumerate(texts):
                    wait_for(lambda: memory.progress == text)
                    check("stage " + str(index + 1))
                    if actual_hold and index == 0:
                        timestamp = memory.snapshot["timestamp"]
                        pump(2.15)
                        assert memory.snapshot["timestamp"] > timestamp, "Live polling stopped during work"
                        check("live polling while worker blocked")
                    if view == "default" and not animated and mode == "Maximum" and case == "success" and index == 0:
                        shot("during")
                    gate.set()
                wait_for(lambda: not memory.running)
                check("result/cooldown")
                wait_for(lambda: not memory.busy and memory._thread is None)
                if animated:
                    pump(.30)  # Complete result opacity/translation before details checks.
                check("ready")
                assert find("optimizeButton").property("enabled")
                result = find("resultCard")
                result.setProperty("expanded", True)
                pump(.18 if animated else .02)
                check("details expanded")
                result.setProperty("expanded", False)
                pump(.18 if animated else .02)
                check("details collapsed")
                if view == "default" and not animated and mode == "Maximum" and case == "success":
                    shot("after")
            expire_events()
        print(f"PASS {args.theme} DPR {args.scale:g}: {view}, all modes/outcomes, motion on/off", flush=True)
    # Actual height resizing must still grow the graph, independently of runs.
    window.showNormal()
    window.resize(1180, 900)
    pump(.12)
    assert plot.height() > default_plot_height
    preferences.setAnimations(False)
    window.resize(1180, 740)
    pump(.12)
    flick.setProperty("contentY", 0)
    view = "navigation"
    baseline = geometry()
    click("settingsNav")
    click("viewResultButton")
    assert window.property("page") == 0 and find("resultCard").property("activeFocus")
    assert flick.property("contentY") > 0
    check("View result navigation")
    flick.setProperty("contentY", 0)
    plot.forceActiveFocus(Qt.TabFocusReason)
    for key in (Qt.Key_Home, Qt.Key_End, Qt.Key_Escape):
        app.postEvent(window, QKeyEvent(QEvent.KeyPress, key, Qt.NoModifier))
        app.postEvent(window, QKeyEvent(QEvent.KeyRelease, key, Qt.NoModifier))
        pump()
        check("chart key " + str(key))
    assert not card.property("pinned")
    assert memory.live
    diagnostics = [m for m in messages if "qrc:/redesign" in m or "binding loop" in m.lower()]
    assert not diagnostics, diagnostics
    report = dict(theme=args.theme, effectiveDpr=window.devicePixelRatio(), nativeDpr=native_scale,
                  liveRam=True, simulatedOptimize=True, windowsScalingChanged=False,
                  actualThreeSecondHoldChecked=args.theme == "light" and args.scale == 1,
                  automaticSource=args.automatic,
                  checks=checks, diagnostics=diagnostics)
    (QA_ROOT / f"history_geometry_qa_{args.theme}_{args.scale:g}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
finally:
    stopped.set()
    gate.set()
    dispose_engine(app, engine, memory)
