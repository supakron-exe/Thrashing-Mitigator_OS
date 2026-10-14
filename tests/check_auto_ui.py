"""Live RAM, simulated Optimize/time/startup; no real Windows registration."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from qa_support import QA_ROOT, qa_path

parser = argparse.ArgumentParser()
parser.add_argument("--theme", default="light", choices=("light", "dark"))
parser.add_argument("--scale", type=float, default=1)
args = parser.parse_args()
env = dict(os.environ); env.pop("QT_SCALE_FACTOR", None)
native = float(subprocess.check_output([sys.executable, "-c", "from PySide6.QtGui import QGuiApplication; a=QGuiApplication([]); print(a.primaryScreen().devicePixelRatio())"], env=env, text=True).strip())
os.environ["QT_SCALE_FACTOR"] = str(args.scale / native)
from PySide6.QtCore import QObject, Property, QPointF, Qt, QMetaObject, Q_ARG, QEvent, qInstallMessageHandler
from PySide6.QtGui import QGuiApplication, QKeyEvent
from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
from main import create_engine, dispose_engine
from backend.controller import MemoryController
from backend.settings import SettingsController
from backend.auto_optimize import AutoOptimizeController
from backend.lifecycle import WindowLifecycle

class Clock:
    now = 0
    def __call__(self): return self.now
class Startup:
    state = False
    def capture(self): return self.state
    def restore(self, state): self.state = state
    def is_enabled(self): return self.state
    def set_enabled(self, state): self.state = state
class Lifecycle(WindowLifecycle):
    @Property(bool, constant=True)
    def trayAvailable(self): return True

messages, checks = [], []
qInstallMessageHandler(lambda kind, context, message: messages.append(message))
QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.OpenGL)
app = QGuiApplication([]); app.setQuitOnLastWindowClosed(False)
temp = tempfile.TemporaryDirectory()
prefs = SettingsController(args.theme, Path(temp.name) / "settings.json")
prefs.setAnimations(False)
def fixture(mode, progress):
    progress("combining identical pages")
    time.sleep(.08)
    return dict(supported=True, elevated=True, trimmed=2, available_before_mb=2500,
                available_after_mb=2700, available_delta_mb=200, duration_s=.08, targets=[])
memory = MemoryController(runner=fixture, hold_ms=30)
clock, startup = Clock(), Startup()
automatic = AutoOptimizeController(memory, prefs, startup, clock)
automatic._timer.stop()
engine, memory, prefs = create_engine(app, controller=memory, settings=prefs, automatic=automatic, lifecycle=Lifecycle(memory))

def pump(seconds=.06):
    end = time.monotonic() + seconds
    while time.monotonic() < end: app.processEvents(); time.sleep(.005)
def find(name):
    item = window.findChild(QObject, name)
    assert item is not None, name
    return item
def click(name):
    item = find(name)
    end = time.monotonic() + 1
    while not item.property("enabled") and time.monotonic() < end:
        pump(.02)
    assert item.property("enabled"), (name, window.property("page"), memory.closing, page.property("enabled"))
    assert QMetaObject.invokeMethod(item, "clicked", Qt.QueuedConnection)
    pump()
def edit(key, value):
    assert QMetaObject.invokeMethod(page, "edit", Qt.QueuedConnection, Q_ARG("QVariant", key), Q_ARG("QVariant", value))
    pump(.03)
def key(code, modifiers=Qt.NoModifier, text=""):
    app.postEvent(window, QKeyEvent(QEvent.KeyPress, code, modifiers, text))
    app.postEvent(window, QKeyEvent(QEvent.KeyRelease, code, modifiers, text))
    pump(.03)
def shot(label):
    pump(.1)
    target = QA_ROOT / "screenshots" / f"auto_{args.theme}_{args.scale:g}_{label}.png"
    assert window.grabWindow().save(str(target))
def check_text(item):
    for child in item.childItems():
        if child.isVisible() and child.property("text") and child.property("contentWidth") is not None:
            # Labels and captions must fit their allocated width; input controls
            # have their own validation and horizontal scrolling.
            if child.metaObject().indexOfProperty("wrapMode") >= 0:
                assert child.width() >= child.property("contentWidth") - 1, (child.property("text"), child.width(), child.property("contentWidth"))
        check_text(child)

try:
    pump(1)
    window = next(w for w in app.allWindows() if w.objectName() == "mainWindow")
    window.setTitle("Auto QA — live RAM / simulated time and Optimize")
    assert abs(window.devicePixelRatio() - args.scale) < .01
    page, scroll = find("autoPage"), find("mainScroll")
    flick = scroll.property("contentItem")
    click("autoNav")
    assert window.property("page") == 2 and not automatic.enabled
    for label, width, height in [("default",1180,740), ("minimum",900,640), ("maximized",None,None)]:
        if width is None: window.showMaximized()
        else: window.showNormal(); window.resize(width,height)
        pump(.15); flick.setProperty("contentY", 0); pump()
        check_text(page)
        shot(label)
        checks.append(dict(view=label, width=window.width(), height=window.height(), contentHeight=flick.property("contentHeight")))
    window.showNormal(); window.resize(1180,740); pump(.12)
    click("autoAdvancedButton"); flick.setProperty("contentY", 0); pump()
    shot("advanced")
    edit("intervalEnabled", False); edit("ramEnabled", False)
    assert page.property("validationError") and not find("autoApplyButton").property("enabled")
    assert not find("autoEnabledToggle").property("enabled")
    click("autoDiscardButton")
    edit("ramEnabled", False); edit("cooldownMinutes", 1)
    # Actual editable SpinBox keyboard path, not just assigning its value.
    number = find("autoIntervalInput")
    point = number.mapToScene(QPointF(0, 0))
    flick.setProperty("contentY", max(0, point.y() + flick.property("contentY") - 200))
    pump()
    number.property("contentItem").forceActiveFocus(Qt.TabFocusReason)
    key(Qt.Key_A, Qt.ControlModifier)
    key(Qt.Key_1, text="1")
    key(Qt.Key_Return)
    assert page.property("draft").toVariant()["intervalMinutes"] == 1, page.property("draft").toVariant()
    click("autoApplyButton")
    assert automatic.configuration["intervalMinutes"] == 1 and not page.property("dirty")
    click("autoEnabledToggle")
    assert automatic.enabled
    memory.setMode("Standard")
    for _ in range(60):
        clock.now += 1; memory.refresh(); automatic.evaluate()
    assert memory.running and memory.operation["source"] == "auto"
    end = time.monotonic() + 5
    while memory.busy or not memory.safeToClose:
        pump(.01); assert time.monotonic() < end
    assert memory.selectedMode == "Standard" and memory.lastResult["mode"] == "Maximum"
    assert automatic.recentActivity[0]["reason"] == "Time interval"
    assert automatic.status == "Cooldown"
    flick.setProperty("contentY", 0); shot("enabled")
    flick.setProperty("contentY", max(0, flick.property("contentHeight") - flick.height())); shot("activity")
    click("autoStartupToggle"); click("autoApplyButton")
    assert startup.state and automatic.configuration["startWithWindows"]
    click("autoEnabledToggle"); assert not automatic.enabled
    click("themeToggle"); click("themeToggle")
    assert automatic.configuration["intervalMinutes"] == 1 and startup.state
    click("overviewNav"); assert window.property("page") == 0
    click("settingsNav"); assert window.property("page") == 1
    prefs.setAnimations(True); click("autoNav"); pump(.30)
    assert page.property("opacity") == 1
    find("autoEnabledToggle").forceActiveFocus(Qt.TabFocusReason)
    key(Qt.Key_Tab)
    assert window.activeFocusItem() is not None
    # Long worker failures remain readable and pause Auto without inventing gain.
    prefs.setAnimations(False)
    def fail(mode, progress): raise RuntimeError("QA long failure message. " * 40)
    memory._runner = fail
    assert memory.startAutomaticOptimization("Maximum", "QA failure")
    end = time.monotonic() + 5
    while memory.busy or not memory.safeToClose:
        pump(.01); assert time.monotonic() < end
    assert automatic.status == "Paused" and not automatic.enabled
    assert automatic.recentActivity[0]["gain"] == "—"
    flick.setProperty("contentY", 0); pump(.1)
    check_text(page); shot("error")
    diagnostics = [m for m in messages if "qrc:/redesign" in m or "binding loop" in m.lower()]
    assert not diagnostics, diagnostics
    report = dict(theme=args.theme, effectiveDpr=window.devicePixelRatio(), liveRam=True,
                  simulatedOptimize=True, simulatedTime=True, simulatedStartup=True,
                  views=checks, diagnostics=diagnostics)
    (QA_ROOT / f"auto_ui_qa_{args.theme}_{args.scale:g}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("PASS Auto page",args.theme,args.scale,"keyboard input, validation, scheduler, activity, themes and navigation",flush=True)
finally:
    dispose_engine(app, engine, memory)
    temp.cleanup()
