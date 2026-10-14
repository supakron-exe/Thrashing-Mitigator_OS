"""Native tray lifecycle with live RAM and a gated simulated worker."""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from qa_support import QA_ROOT, qa_path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QSystemTrayIcon
from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
from main import create_engine, dispose_engine
from backend.controller import MemoryController
from backend.settings import SettingsController
from backend.auto_optimize import AutoOptimizeController
from backend.lifecycle import TrayLifecycle

QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.OpenGL)
app = QApplication([]); app.setQuitOnLastWindowClosed(False)
temp = tempfile.TemporaryDirectory()
gate = threading.Event()
completed = []
def fixture(mode, progress):
    progress("combining identical pages")
    gate.wait(10)
    completed.append(mode)
    return dict(supported=True, elevated=True, trimmed=1, available_delta_mb=20)
memory = MemoryController(runner=fixture, hold_ms=50)
prefs = SettingsController("light", Path(temp.name)/"settings.json")
prefs.setAnimations(False)
automatic = AutoOptimizeController(memory, prefs)
lifecycle = TrayLifecycle(app, memory, automatic, prefs)
engine, memory, prefs = create_engine(app, controller=memory, settings=prefs, automatic=automatic, lifecycle=lifecycle)
checks = []
def pump(seconds=.1):
    end = time.monotonic()+seconds
    while time.monotonic()<end: app.processEvents(); time.sleep(.01)
try:
    pump(1)
    window = next(w for w in app.allWindows() if w.objectName()=="mainWindow")
    window.setTitle("Tray QA — live RAM / simulated Optimize")
    assert lifecycle.window is window
    assert lifecycle.trayAvailable, "Native Windows tray unavailable"
    memory.setMode("Standard")
    memory.startAutomaticOptimization("Maximum", "QA gated run")
    pump(.1)
    assert memory.running
    timestamp = memory.snapshot["timestamp"]
    assert not window.close()  # Real QML close listener hides instead of exiting.
    pump(.1)
    assert not window.isVisible() and not memory.closing and memory.running
    pump(2.1)
    assert memory.snapshot["timestamp"]>timestamp
    checks.append("native close hides while worker and live monitoring continue")
    lifecycle.open(); pump()
    assert window.isVisible()
    window.showMaximized(); pump()
    lifecycle.closeWindow(window); pump()
    lifecycle.open(); pump()
    assert window.visibility()==window.Visibility.Maximized
    checks.append("restore retains maximized state")
    automatic.setEnabled(True)
    lifecycle.toggleAuto()
    assert not automatic.enabled and memory.running
    checks.append("Tray Pause stops future jobs without cancelling worker")
    with patch.object(QSystemTrayIcon, "isSystemTrayAvailable", return_value=False):
        lifecycle.closeWindow(window); pump()
        assert window.isVisible() and not memory.closing
    checks.append("unavailable tray keeps a recoverable visible window")
    lifecycle.closeWindow(window); pump()
    assert not window.isVisible()
    gate.set()
    end=time.monotonic()+5
    while memory.busy or not memory.safeToClose:
        pump(.02); assert time.monotonic()<end
    assert automatic.lastResult["mode"]=="Maximum"
    assert memory.selectedMode=="Standard"
    checks.append("hidden completion retained without activating window")
    gate.clear()
    memory.startAutomaticOptimization("Maximum", "QA exit during run")
    pump(.1)
    finished=[]
    memory.closeReady.connect(lambda: finished.append(len(completed)))
    lifecycle.exit()
    assert memory.closing and not finished
    QTimer.singleShot(250, gate.set)
    QTimer.singleShot(5000, app.quit)
    started=time.monotonic()
    app.exec()
    assert finished==[2] and memory.safeToClose and time.monotonic()-started>=.2
    assert not lifecycle.tray.isVisible()
    checks.append("actual application event loop waits for worker before Exit")
    (QA_ROOT/"auto_tray_qa.json").write_text(json.dumps(dict(checks=checks, nativeTray=True, liveRam=True, simulatedOptimize=True),indent=2),encoding="utf-8")
    print("PASS native Tray:", "; ".join(checks),flush=True)
finally:
    gate.set(); automatic.shutdown(); lifecycle.tray.hide()
    dispose_engine(app,engine,memory)
    lifecycle.menu.deleteLater(); temp.cleanup()
