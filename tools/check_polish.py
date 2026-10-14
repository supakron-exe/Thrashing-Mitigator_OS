"""Motion/interaction checks and clearly labelled QA-fixture GIFs; no real Optimize."""
import argparse
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import ctypes
from ctypes import wintypes
import faulthandler
faulthandler.enable()

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from qa_support import QA_ROOT, qa_path
parser = argparse.ArgumentParser()
parser.add_argument("--theme", choices=("light", "dark"), default="dark")
parser.add_argument("--record", action="store_true")
args = parser.parse_args()
os.environ["QT_QUICK_CONTROLS_STYLE"] = "Basic"
from PySide6.QtCore import QObject, Qt, QMetaObject, QEvent, qInstallMessageHandler
from PySide6.QtGui import QGuiApplication, QKeyEvent
from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
from PIL import Image, ImageGrab
from main import create_engine, dispose_engine
from backend.controller import MemoryController
from backend.settings import SettingsController

messages, frames, frame_times = [], [], []
def message_handler(kind, context, text):
    messages.append(text)
    if "qrc:/redesign" in text: print(text, flush=True)
qInstallMessageHandler(message_handler)

def fake_run(mode, progress):
    for label in ("combining identical pages", "trimming 4 apps", "flushing file cache", "writing dirty pages to disk", "purging standby", "settling"):
        progress(label); time.sleep(.35)
    return {"engine": "maximum", "supported": True, "elevated": False,
            "available_before_mb": 3100, "available_after_mb": 3400, "available_delta_mb": 300,
            "available_settled_mb": 3380, "available_settled_delta_mb": 280, "free_delta_mb": 110,
            "trimmed": 4, "failed": 1, "duration_s": 2.1,
            "steps": [{"name": name, "ok": False, "detail": "Administrator required (QA fixture)"}
                      for name in ("Combine", "File cache", "Modified", "Standby")], "targets": []}

QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.OpenGL)
app = QGuiApplication([])
app.setQuitOnLastWindowClosed(False)
preferences = SettingsController(args.theme, Path(tempfile.gettempdir()) / "thrashing-polish-qa" / "settings.json")
preferences.setAnimations(True)
memory = MemoryController(runner=fake_run)
engine, memory, preferences = create_engine(app, controller=memory, settings=preferences)
window, last_frame, recording = None, 0, False

def pump(seconds):
    global last_frame
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents(); time.sleep(.01)
        if args.record and recording and window and window.isActive() and time.monotonic() - last_frame >= .08:
            # Capture only this tool's own foreground window. Synchronous Qt
            # grabWindow during an animation deadlocks with the upstream native filter.
            rect = wintypes.RECT()
            assert ctypes.windll.user32.GetWindowRect(wintypes.HWND(int(window.winId())), ctypes.byref(rect))
            frame = ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom), all_screens=True)
            frame = frame.resize((944, round(frame.height * 944 / frame.width)), Image.Resampling.BILINEAR)
            frames.append(frame.convert("RGB"))
            frame_times.append(time.monotonic())
            last_frame = time.monotonic()

def find(name):
    item = window.findChild(QObject, name)
    assert item is not None, name
    return item

def click(name):
    print("Activate", name, flush=True)
    assert find(name).property("enabled"), name
    assert QMetaObject.invokeMethod(find(name), "clicked", Qt.QueuedConnection)

def wait_for(predicate, timeout=12):
    end = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < end, "Timed out"
        pump(.04)

def shot(name):
    folder = QA_ROOT / "screenshots"
    folder.mkdir(exist_ok=True)
    assert window.grabWindow().save(str(folder / name))

try:
    pump(1)
    print("Window ready", flush=True)
    window = next(w for w in app.allWindows() if w.objectName() == "mainWindow")
    window.setTitle("Thrashing Mitigator · Motion QA (simulated Optimize)")
    window.requestActivate(); pump(.4)
    assert window.isActive(), "Motion requires an active window"
    recording = True
    print("Recording", args.record, flush=True)
    pump(.3)
    click("settingsNav"); pump(.05)
    settings = find("settingsNav")  # Ensure the real navigation control remains enabled.
    assert window.property("page") == 1
    # Turning motion off mid-transition must settle both outgoing/incoming pages.
    preferences.setAnimations(False)
    pump(.03)
    assert find("dashboard").property("opacity") == 0
    preferences.setAnimations(True)
    pump(.35)
    click("overviewNav"); pump(.05)
    assert 0 < find("dashboard").property("opacity") < 1, "Missing page transition"
    pump(.5)
    button = find("optimizeButton")
    button.forceActiveFocus(Qt.TabFocusReason)
    app.postEvent(window, QKeyEvent(QEvent.KeyPress, Qt.Key_Space, Qt.NoModifier)); pump(.10)
    assert button.property("scale") < 1, "Missing press feedback"
    app.postEvent(window, QKeyEvent(QEvent.KeyRelease, Qt.Key_Space, Qt.NoModifier)); pump(.15)
    assert memory.running
    assert find("operationSpinner").property("animate")
    assert len(memory.optimizationEvents) == 1
    before = len(memory.history)
    preferences.setAnimations(False); pump(.05)
    assert not find("operationSpinner").property("animate")
    assert button.property("scale") == 1
    memory.refresh(); pump(.03)
    assert find("liveHalo").property("opacity") == 0
    preferences.setAnimations(True); pump(.35)
    shot(f"qa_progress_{args.theme}.png")
    # No second run, no mode changes while busy; live sampling and theme changes continue.
    memory.startOptimization(); memory.setMode("Standard")
    assert memory.selectedMode == "Maximum"
    preferences.setTheme("light" if args.theme == "dark" else "dark"); pump(.35)
    preferences.setTheme(args.theme); pump(.35)
    wait_for(lambda: not memory.running)
    assert len(memory.history) > before
    pump(.35)
    click("viewResultButton"); pump(.4)
    assert find("resultCard").property("activeFocus")
    assert find("resultCard").property("opacity") == 1
    click("detailsButton"); pump(.3)
    shot(f"qa_motion_details_{args.theme}.png")
    click("detailsButton"); pump(.3)
    # Failed sampling must never animate the successful-sample halo.
    pump(.3)
    provider = memory._provider
    memory._provider = lambda: (_ for _ in ()).throw(OSError("QA read failure"))
    memory.refresh(); pump(.05)
    assert not memory.live
    assert find("liveHalo").property("opacity") == 0
    memory._provider = provider; memory.refresh(); pump(.3)
    # Minimize suspends animated busy indicators even with motion enabled.
    recording = False
    window.showMinimized(); pump(.15)
    assert not find("operationSpinner").property("animate")
    window.showNormal(); window.requestActivate(); pump(.3)
    recording = False
    wait_for(lambda: not memory.busy)
    assert not [m for m in messages if "qrc:/redesign" in m and any(word in m for word in ("Error", "Cannot", "Unable", "Binding loop"))], messages
    if frames:
        target = QA_ROOT / "screenshots" / f"motion_qa_{args.theme}.gif"
        durations = [max(40, round((b - a) * 1000 / 10) * 10) for a, b in zip(frame_times, frame_times[1:])] + [300]
        palette_frames = [frame.convert("P", palette=Image.Palette.ADAPTIVE, colors=256) for frame in frames]
        palette_frames[0].save(target, save_all=True, append_images=palette_frames[1:], duration=durations, loop=0, optimize=False)
        print(f"Saved {target.name}: {len(frames)} frames (simulated Optimize, live RAM)", flush=True)
    (QA_ROOT / f"polish_qa_{args.theme}.json").write_text(json.dumps({"passed": True, "messages": messages, "operation": memory.operation}, indent=2), encoding="utf-8")
    print("PASS: motion, interruption, static spinner, sample feedback, stage sequence, result focus, minimize", flush=True)
finally:
    faulthandler.cancel_dump_traceback_later()
    dispose_engine(app, engine, memory)
