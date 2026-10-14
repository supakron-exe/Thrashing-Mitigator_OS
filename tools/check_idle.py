"""Repeatable idle observation (single-process CPU %, RSS); no Optimize."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import time
import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from qa_support import QA_ROOT, qa_path
parser = argparse.ArgumentParser()
parser.add_argument("--collect-seconds", type=float, default=13)
parser.add_argument("--screenshots", action="store_true")
args = parser.parse_args()
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
from main import create_engine, dispose_engine
from backend.settings import SettingsController

QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.OpenGL)
app = QGuiApplication([])
temporary = tempfile.TemporaryDirectory(prefix="idle-")
settings = SettingsController("dark", path=Path(temporary.name) / "settings.json")
engine, memory, settings = create_engine(app, settings=settings)
process = psutil.Process()
values = []
started = time.monotonic()
process.cpu_percent()
try:
    while time.monotonic() - started < args.collect_seconds:
        app.processEvents(); time.sleep(.02)
        if 3 <= time.monotonic() - started < 13 and (not values or time.monotonic() - values[-1]["at"] >= 1):
            values.append({"at": time.monotonic(), "cpu": process.cpu_percent(), "rss": process.memory_info().rss})
    report = {"samples": values, "meanCpuPercent": sum(v["cpu"] for v in values) / len(values),
              "meanRssBytes": sum(v["rss"] for v in values) / len(values),
              "note": "13-second observation; first sample includes startup. Same method as baseline. CPU is psutil single-process CPU percent, not total-machine percent."}
    (QA_ROOT / "performance_v2.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2), flush=True)
    if args.screenshots:
        window = next(w for w in app.allWindows() if w.objectName() == "mainWindow")
        # Freeze motion for static grabs; these are actual live readings, no injected history.
        settings.setAnimations(False)
        for theme in ("dark", "light"):
            settings.setTheme(theme)
            stop = time.monotonic() + .5
            while time.monotonic() < stop:
                app.processEvents(); time.sleep(.02)
            assert window.grabWindow().save(str(QA_ROOT / "screenshots" / f"overview_{theme}.png"))
finally:
    dispose_engine(app, engine, memory)
    temporary.cleanup()
