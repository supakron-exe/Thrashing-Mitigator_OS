"""Render and exercise real QML. Mock operations are available only to this QA tool."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import faulthandler
faulthandler.enable()

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from qa_support import QA_ROOT, qa_path
parser = argparse.ArgumentParser()
parser.add_argument("--theme", choices=("light", "dark"), default="light")
parser.add_argument("--scale", default="1")
parser.add_argument("--live-optimize", action="store_true")
parser.add_argument("--collect-seconds", type=float, default=7)
args = parser.parse_args()
os.environ["QT_SCALE_FACTOR"] = args.scale
os.environ["QT_QUICK_CONTROLS_STYLE"] = "Basic"
from PySide6.QtCore import QObject, QPoint, QPointF, Qt, QMetaObject, qInstallMessageHandler
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickWindow, QQuickItem, QSGRendererInterface
from PySide6.QtTest import QTest
from main import create_engine, dispose_engine
from backend.controller import MemoryController
from backend.settings import SettingsController

messages = []
def handler(kind, context, text):
    messages.append(text)
    if "qrc:/redesign" in text or "Error" in text or "polish" in text.lower():
        print(text, flush=True)
qInstallMessageHandler(handler)

def pump(seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(.02)

def wait_for(predicate, timeout=15):
    end = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > end:
            raise AssertionError("Timed out waiting for interface state")
        pump(.05)

def find(name):
    item = window.findChild(QObject, name)
    assert item is not None, name
    return item

def click(name):
    item = find(name)
    assert item.property("enabled"), name
    print(f"Activating {name}", flush=True)
    # QtTest's synchronous mouseClick can deadlock with Python native event
    # filters in this upstream/Qt combination. Exercise the real control signal.
    assert QMetaObject.invokeMethod(item, "clicked", Qt.QueuedConnection)
    print(f"Activated {name}", flush=True)
    pump(.2)

def shot(name):
    pump(.4)
    target = QA_ROOT / "screenshots" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    image = window.grabWindow()
    assert not image.isNull(), "Empty Qt screenshot"
    assert image.save(str(target))
    print(f"Saved {target.name} ({image.width()}×{image.height()})", flush=True)

def mock_run(mode, progress):
    for text in ("combining identical pages", "trimming 4 apps", "flushing file cache", "writing dirty pages to disk", "purging standby", "settling"):
        progress(text)
        time.sleep(.35)
    return {"supported": True, "engine": "maximum", "elevated": True,
            "available_before_mb": 2450, "available_after_mb": 2860,
            "available_delta_mb": 410, "available_settled_mb": 2810,
            "available_settled_delta_mb": 360, "free_delta_mb": 530,
            "trimmed": 4, "failed": 1, "duration_s": 5.7,
            "steps": [{"name": "File cache", "ok": True, "detail": "Completed"}, {"name": "Long system-step name " * 5, "ok": False, "detail": "Access denied " * 30}],
            "targets": [{"name": "Long application name " * 12, "ok": False, "reason": "Access denied " * 30}]}

QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.OpenGL)
app = QGuiApplication([sys.argv[0]])
app.setQuitOnLastWindowClosed(False)
preferences = SettingsController(theme=args.theme, path=Path(tempfile.gettempdir()) / "thrashing-redesign-qa" / "settings.json")
preferences.setAnimations(True)
memory = MemoryController(runner=None if args.live_optimize else mock_run)
engine, memory, preferences = create_engine(app, controller=memory, settings=preferences)
pump(2)
windows = [w for w in app.allWindows() if w.objectName() == "mainWindow"]
assert windows, "FluRouter did not create MainWindow"
window = windows[0]
print(f"Window loaded: {window.width()}×{window.height()}, RAM {memory.snapshot['percent']:.1f}%", flush=True)
try:
    pump(max(0, args.collect_seconds - 2))
    for name in ("shell", "mainContent", "mainScroll", "dashboard"):
        item = find(name)
        print(name, {p: item.property(p) for p in ("x", "y", "width", "height", "implicitWidth", "availableWidth", "contentWidth")}, flush=True)
    button = find("optimizeButton")
    print("Button colors", button.property("textColor"), button.property("contentItem").property("color"), flush=True)
    shot(f"overview_{args.theme}.png" if args.live_optimize else f"qa_overview_{args.theme}_{args.scale}.png")
    if args.live_optimize:
        preferences.setTheme("dark" if args.theme == "light" else "light")
        shot(f"overview_{preferences.theme}.png")
        preferences.setTheme(args.theme)
    window.requestActivate()
    pump(.2)
    find("themeToggle").forceActiveFocus(Qt.TabFocusReason)
    QTest.keyClick(window, Qt.Key_Tab)
    pump(.05)
    assert window.activeFocusItem() is not None, "Missing keyboard focus"
    plot = find("historyCanvas")
    plot.forceActiveFocus(Qt.TabFocusReason)
    QTest.keyClick(window, Qt.Key_Home)
    pump(.05)
    chart = plot.parentItem().parentItem().parentItem()
    assert chart.property("pinned")
    assert chart.property("selectedTimestamp") == memory.history[0]["timestamp"]
    selected = chart.property("selectedTimestamp")
    memory.refresh()
    pump(.05)
    assert chart.property("selectedTimestamp") == selected, "Selection moved with rolling samples"
    QTest.keyClick(window, Qt.Key_End)
    pump(.05)
    assert chart.property("selectedTimestamp") == memory.history[-1]["timestamp"]
    QTest.keyClick(window, Qt.Key_Escape)
    pump(.05)
    assert not chart.property("pinned") and chart.property("hoveredIndex") == -1
    click("themeToggle")
    assert preferences.theme != args.theme
    click("themeToggle")
    assert preferences.theme == args.theme
    click("settingsNav")
    assert window.property("page") == 1
    click("motionToggle")
    assert not preferences.animations
    shot(f"settings_{args.theme}_{args.scale}.png")
    click("overviewNav")
    assert window.property("page") == 0
    window.resize(900, 640)
    pump(.4)
    shot(f"minimum_{args.theme}_{args.scale}.png")
    assert not window.property("wide")
    window.resize(1180, 740)
    window.showMaximized()
    pump(.5)
    shot(f"maximized_{args.theme}_{args.scale}.png")
    window.showNormal()
    window.resize(1180, 740)
    pump(.5)
    modes = ("Standard", "Deep", "Maximum") if args.live_optimize else ("Maximum",)
    outcomes = []
    for mode in modes:
        memory.setMode(mode)
        history_before = len(memory.history)
        click("optimizeButton")
        assert memory.busy
        assert not find("optimizeButton").property("enabled")
        assert not find("modeSelector").property("enabled")
        assert not find("operationSpinner").property("animate"), "Motion-off spinner still animated"
        spinner = find("operationSpinner")
        assert spinner.mapToScene(QPointF(0, 0)).y() + spinner.height() < window.height(), "Progress hidden below the window"
        assert memory.operation["mode"] == mode
        assert memory.optimizationEvents[-1]["mode"] == mode
        click("themeToggle")
        click("themeToggle")
        wait_for(lambda: not memory.busy, timeout=150)
        assert memory.lastResult
        assert memory.live
        assert len(memory.history) >= history_before
        assert memory.operation["finishedAt"] >= memory.operation["startedAt"]
        assert memory.optimizationEvents[-1]["title"] == memory.lastResult["title"]
        click("viewResultButton")
        assert find("resultCard").property("activeFocus"), "Result navigation did not move focus"
        assert find("resultCard").property("opacity") == 1, "Motion-off result not immediately visible"
        outcomes.append(memory.lastResult)
        # Scroll to the persistent result panel.
        scroll = find("mainScroll")
        flickable = scroll.property("contentItem")
        if flickable is not None:
            flickable.setProperty("contentY", max(0, flickable.property("contentHeight") - flickable.property("height")))
        pump(.5)
        shot(f"result_{args.theme}.png" if args.live_optimize and mode == "Maximum" else f"qa_result_{args.theme}_{mode}_{args.scale}.png")
        if args.live_optimize and mode == "Maximum":
            preferences.setTheme("dark" if args.theme == "light" else "light")
            shot(f"result_{preferences.theme}.png")
            preferences.setTheme(args.theme)
        click("detailsButton")
        pump(.5)
        # Details are exercised with long process names/errors in mock mode.
        if flickable is not None:
            flickable.setProperty("contentY", max(0, flickable.property("contentHeight") - flickable.property("height")))
        shot(f"details_{args.theme}_{mode}_{args.scale}.png")
        if flickable is not None:
            flickable.setProperty("contentY", 0)
    errors = [m for m in messages if "qrc:/redesign" in m and ("Error" in m or "Unable" in m or "Binding loop" in m or "Cannot" in m)]
    assert not errors, errors
    (QA_ROOT / f"{'live' if args.live_optimize else 'qa'}_{args.theme}_{args.scale}.json").write_text(json.dumps({"passed": True, "theme": args.theme, "scale": args.scale, "outcomes": outcomes, "messages": messages}, indent=2), encoding="utf-8")
    print("PASS: theme, navigation, motion, resize, progress, results and monitoring", flush=True)
finally:
    dispose_engine(app, engine, memory)
    faulthandler.cancel_dump_traceback_later()
