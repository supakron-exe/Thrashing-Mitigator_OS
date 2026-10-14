"""Real QML result-notification checks. Optimize fixtures exist only in this test."""
import argparse
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import time
import faulthandler
faulthandler.enable()

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from qa_support import QA_ROOT, qa_path
parser = argparse.ArgumentParser()
parser.add_argument("--theme", choices=("light", "dark"), default="light")
parser.add_argument("--scale", default="1")
parser.add_argument("--full-timeout", action="store_true")
args = parser.parse_args()
# Normalize the native Windows scale so --scale tests the requested effective
# DPR, rather than multiplying e.g. Windows 125% by another 150%.
native_env = dict(os.environ)
native_env.pop("QT_SCALE_FACTOR", None)
native_scale = float(subprocess.check_output([sys.executable, "-c", "from PySide6.QtGui import QGuiApplication; a=QGuiApplication([]); print(a.primaryScreen().devicePixelRatio())"], env=native_env, text=True).strip())
qt_factor = float(args.scale) / native_scale
os.environ["QT_SCALE_FACTOR"] = str(qt_factor)
from PySide6.QtCore import QObject, QPointF, Qt, QMetaObject, QEvent, Q_ARG, QUrl, qInstallMessageHandler
from PySide6.QtGui import QGuiApplication, QKeyEvent, QMouseEvent, QCursor
from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
from PySide6.QtQml import QQmlComponent
from PySide6.QtTest import QTest
from main import create_engine, dispose_engine
from backend.controller import MemoryController
from backend.settings import SettingsController

messages, checks = [], []
notification_id = 1000000
original_cursor = QCursor.pos()
def handler(kind, context, text):
    messages.append(text)
    if "qrc:/redesign" in text: print(text, flush=True)
qInstallMessageHandler(handler)

case = "success"
def fixture(mode, progress):
    progress("trimming apps")
    time.sleep(.08)
    if case == "error": raise RuntimeError("QA simulated failure")
    change = 0 if case == "zero" else -50 if case == "negative" else 3500
    return {"supported": True, "engine": "maximum", "elevated": True,
            "trimmed": 4, "failed": 1 if case == "partial" else 0,
            "available_before_mb": 2800, "available_after_mb": 2800 + change,
            "available_delta_mb": change, "available_settled_mb": 2800 + change,
            "available_settled_delta_mb": change, "duration_s": .08, "free_delta_mb": 200,
            "steps": [{"name": label, "ok": case != "partial", "detail": "QA fixture"}
                      for label in ("Combine", "File cache", "Modified", "Standby")], "targets": []}

QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.OpenGL)
app = QGuiApplication([])
app.setQuitOnLastWindowClosed(False)
preferences = SettingsController(args.theme, Path(tempfile.gettempdir()) / "thrashing-toast-qa" / "settings.json")
preferences.setAnimations(False)
memory = MemoryController(runner=fixture, hold_ms=30)
engine, memory, preferences = create_engine(app, controller=memory, settings=preferences)

def pump(seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents(); time.sleep(.01)

def wait_for(predicate, timeout=10):
    end = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < end, "Timed out"
        pump(.02)

def find(name):
    item = window.findChild(QObject, name)
    assert item is not None, name
    return item

def click(name):
    item = find(name)
    assert item.property("enabled"), name
    assert QMetaObject.invokeMethod(item, "clicked", Qt.QueuedConnection)
    pump(.05)

def key(value):
    app.postEvent(window, QKeyEvent(QEvent.KeyPress, value, Qt.NoModifier))
    app.postEvent(window, QKeyEvent(QEvent.KeyRelease, value, Qt.NoModifier))
    pump(.05)

def mouse_at(point):
    global_position = QPointF(window.mapToGlobal(point.toPoint()))
    # The upstream frameless filter consults the native cursor, so keep it
    # aligned with posted events inside this test's own window.
    QCursor.setPos(global_position.toPoint())
    QTest.mouseMove(window, point.toPoint(), 0)
    pump(.03)

def start(outcome="success"):
    global case
    wait_for(lambda: not memory.busy and memory._thread is None)
    case = outcome
    memory.startOptimization()
    assert not toast.property("opened"), "Old notification survived new run"
    wait_for(lambda: not memory.running)
    pump(.02)
    print("Completed fixture:", outcome, "operation", memory.operation["id"], flush=True)

def screenshot(label):
    pump(.1)
    target = QA_ROOT / "screenshots" / f"toast_compact_{args.theme}_{args.scale}_{label}.png"
    assert window.grabWindow().save(str(target))

def invoke(item, name, *values):
    assert QMetaObject.invokeMethod(item, name, Qt.QueuedConnection, *[Q_ARG("QVariant", value) for value in values]), name

def repeat_notification(title=None):
    global notification_id
    notification_id += 1
    data = dict(memory.lastResult, operationId=notification_id)
    if title is not None: data["title"] = title
    invoke(toast, "offer", data)
    pump(.03)

def layout_snapshot():
    return (scroll.property("availableHeight"), flick.width(), flick.height(), flick.property("contentHeight"), flick.property("contentY"),
            find("dashboard").height(), find("resultCard").y(), find("historyCanvas").mapToScene(QPointF(0, 0)))

def stable_overlay(at_bottom=False, animated=False):
    invoke(toast, "dismiss", False); pump(.25)
    if at_bottom:
        flick.setProperty("contentY", max(0, flick.property("contentHeight") - flick.height()))
        pump(.03)
    before = layout_snapshot()
    preferences.setAnimations(animated)
    repeat_notification()
    assert layout_snapshot() == before, "Entrance changed viewport/layout/scroll"
    pump(.20)
    assert layout_snapshot() == before, "Visible popup changed layout"
    invoke(toast, "dismiss", False); pump(.03)
    assert layout_snapshot() == before, "Exit changed layout"
    pump(.20)
    assert layout_snapshot() == before, "Dismissal clamped scroll position"
    preferences.setAnimations(False)

def pointer_click(point):
    mouse_at(point)
    # Use Qt's platform-event test path; posted QMouseEvents do not update
    # Qt Controls' primary-button state. All targets belong to this QA window.
    QTest.mouseClick(window, Qt.LeftButton, Qt.NoModifier, point.toPoint(), 0)
    pump(.05)

try:
    pump(1)
    window = next(w for w in app.allWindows() if w.objectName() == "mainWindow")
    window.setTitle("Thrashing Mitigator · Toast QA (simulated Optimize)")
    window.requestActivate(); pump(.2)
    assert abs(window.devicePixelRatio() - float(args.scale)) < .01, "Unexpected effective display scale"
    toast = find("resultToast")
    scroll = find("mainScroll")
    flick = scroll.property("contentItem")
    theme_button = find("themeToggle")
    mouse_at(QPointF(20, 110))
    assert not toast.property("visible")
    assert toast.property("displayDuration") == 6000
    theme_button.forceActiveFocus(Qt.TabFocusReason)
    start()
    assert toast.property("opened") and toast.property("tone") == "success"
    assert theme_button.property("activeFocus"), "Notification stole focus"
    assert flick.property("contentY") == 0, "Notification scrolled the page automatically"
    assert "below" in toast.property("message")
    deadline = toast.property("deadline")
    memory.resultChanged.emit(); pump(.03)
    assert toast.property("deadline") == deadline, "Duplicate result reset timeout"
    assert scroll.property("bottomPadding") == 0
    assert toast.height() == 44 and toast.width() <= 340
    assert find("toastViewResults").property("text") == "View"
    assert find("resultToastMessage").property("text") == memory.lastResult["title"]
    screenshot("default")
    if args.full_timeout:
        wait_for(lambda: not toast.property("opened"), timeout=7)
        assert memory.lastResult, "Timeout removed persistent results"
        checks.append("actual 6-second timeout")

    stable_overlay(animated=True)
    stable_overlay(at_bottom=True, animated=True)
    checks.append("fixed viewport/layout/scroll through entrance/display/exit, including bottom")
    flick.setProperty("contentY", 0)
    repeat_notification("An exceptionally long optimization outcome title " * 8)
    assert toast.width() <= 340 and toast.height() == 44
    assert find("resultToastMessage").property("truncated")
    assert "exceptionally" in toast.property("message")
    invoke(toast, "dismiss", False); pump(.03)
    repeat_notification()

    # A test-only button underneath the popup proves that it shields its own
    # background while allowing interaction immediately outside its bounds.
    probe_component = QQmlComponent(engine)
    probe_component.setData(b'''import QtQuick
import QtQuick.Controls
Button {
    property int hits: 0
    onClicked: hits++
    background: Rectangle { color: "transparent" }
    contentItem: Item {}
}''', QUrl())
    probe = probe_component.create()
    assert probe is not None, probe_component.errors()
    probe.setParentItem(find("mainContent"))
    probe.setX(toast.x() - 20); probe.setY(toast.y()); probe.setWidth(toast.width() + 40); probe.setHeight(toast.height()); probe.setZ(899)
    pump(.2)
    pointer_click(toast.mapToScene(QPointF(35, 22)))
    assert probe.property("hits") == 0, "Popup click leaked to covered control"
    pointer_click(toast.mapToScene(QPointF(-10, 22)))
    assert probe.property("hits") == 1, "Popup blocked outside interaction"
    probe.deleteLater(); pump(.03)
    mouse_at(QPointF(20, 110)); theme_button.forceActiveFocus(Qt.TabFocusReason)
    checks.append("long-title elision / background pointer shielding / outside interaction")

    toast.setProperty("displayDuration", 350)
    start()
    view = find("toastViewResults")
    view.forceActiveFocus(Qt.TabFocusReason); pump(.03)
    assert toast.property("held")
    pump(.5)
    assert toast.property("opened"), "Focused notification expired"
    key(Qt.Key_Tab)
    assert find("toastClose").property("activeFocus"), "Close action not keyboard reachable"
    key(Qt.Key_Escape)
    assert not toast.property("opened") and theme_button.property("activeFocus")
    checks.append("keyboard focus pause / Tab / Escape / restore")

    start()
    point = toast.mapToScene(QPointF(50, toast.height() / 2))
    mouse_at(point)
    wait_for(lambda: find("toastHover").property("hovered"), timeout=.3)
    remaining = toast.property("remainingMs")
    pump(.5)
    assert toast.property("opened") and toast.property("remainingMs") == remaining
    mouse_at(QPointF(20, 110))
    wait_for(lambda: not toast.property("opened"), timeout=1)
    assert memory.lastResult
    checks.append("hover pause / remaining timeout / persistent result")

    toast.setProperty("displayDuration", 3000)
    for width, height, label in ((900, 640, "minimum"), (1180, 740, "default")):
        window.resize(width, height); pump(.1)
        start()
        assert toast.width() <= find("mainContent").width() - 32
        assert toast.mapToScene(QPointF(0, 0)).y() + toast.height() <= window.height() - 16
        screenshot(label)
        click("toastViewResults")
        assert not toast.property("opened")
        assert find("resultCard").property("activeFocus")
        panel = find("resultCard")
        assert panel.y() >= flick.property("contentY") - 1
        assert panel.y() < flick.property("contentY") + flick.height()
        flick.setProperty("contentY", 0)
    window.showMaximized(); pump(.2)
    start(); screenshot("maximized"); click("toastClose")
    window.showNormal(); window.resize(1180, 740); pump(.1)
    checks.append("minimum/default/maximized / compact overlay / result scroll")

    preferences.setAnimations(True)
    click("settingsNav")
    pump(.25)
    start()
    assert "on Overview" in toast.property("message")
    preferences.setAnimations(False)  # Static Qt grab; motion itself is checked below.
    screenshot("settings")
    preferences.setAnimations(True)
    click("toastViewResults")
    assert window.property("page") == 0
    assert find("resultCard").property("activeFocus")
    assert find("resultCard").y() < flick.property("contentY") + flick.height()
    preferences.setAnimations(False)
    checks.append("Settings to Overview result navigation")

    for outcome, tone in (("partial", "success"), ("zero", "warning"), ("negative", "warning"), ("error", "error")):
        theme_button.forceActiveFocus(Qt.TabFocusReason)
        start(outcome)
        assert toast.property("tone") == tone
        if outcome in ("zero", "error"):
            screenshot(outcome)
        click("toastClose")
        assert memory.lastResult
    checks.append("partial / zero / negative / error tones")

    toast.setProperty("displayDuration", 1000)
    window.showMinimized(); pump(.1)
    start()
    assert not toast.property("opened") and toast.property("pending")
    pump(1.1)
    window.showNormal(); window.requestActivate(); pump(.05)
    assert toast.property("opened"), "Background completion was lost"
    pump(.1)
    window.showMinimized(); pump(.05)
    remaining = toast.property("remainingMs")
    assert 0 < remaining < 1000
    pump(1.1)
    window.showNormal(); window.requestActivate(); pump(.03)
    assert toast.property("opened") and toast.property("remainingMs") == remaining
    click("toastClose")
    checks.append("background completion / minimize / remaining-time resume")

    toast.setProperty("displayDuration", 3000)
    preferences.setAnimations(True)
    theme_button.forceActiveFocus(Qt.TabFocusReason)
    start()
    pump(.03)
    assert toast.property("opened")
    assert 0 < toast.property("opacity") < 1, "Missing entrance motion"
    preferences.setAnimations(False)
    assert toast.property("opacity") == 1 and toast.property("slide") == 0
    start()
    assert len(window.findChildren(QObject, "resultToast")) == 1
    memory.requestClose(); pump(.05)
    assert not toast.property("opened") and not toast.property("pending")
    checks.append("motion interruption / replacement / close cleanup")

    errors = [m for m in messages if "qrc:/redesign" in m and any(s in m for s in ("Error", "Cannot", "Unable", "Binding loop"))]
    assert not errors, errors
    (QA_ROOT / f"toast_compact_qa_{args.theme}_{args.scale}.json").write_text(json.dumps({"passed": True, "checks": checks, "messages": messages, "requestedScale": args.scale, "qtScaleFactor": qt_factor, "nativeScale": native_scale, "devicePixelRatio": window.devicePixelRatio()}, indent=2), encoding="utf-8")
    print(f"PASS {args.theme} scale {args.scale}: " + "; ".join(checks), flush=True)
finally:
    QCursor.setPos(original_cursor)
    dispose_engine(app, engine, memory)
