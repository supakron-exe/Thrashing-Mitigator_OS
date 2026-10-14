"""Check the real history-card layout; RAM fixtures exist only in this test."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from qa_support import QA_ROOT, qa_path

parser = argparse.ArgumentParser()
parser.add_argument("--theme", choices=("light", "dark"), default="light")
parser.add_argument("--scale", type=float, default=1)
args = parser.parse_args()
native_env = dict(os.environ)
native_env.pop("QT_SCALE_FACTOR", None)
native_scale = float(subprocess.check_output([
    sys.executable, "-c",
    "from PySide6.QtGui import QGuiApplication; a=QGuiApplication([]); print(a.primaryScreen().devicePixelRatio())",
], env=native_env, text=True).strip())
os.environ["QT_SCALE_FACTOR"] = str(args.scale / native_scale)

from PySide6.QtCore import QObject, QPointF, qInstallMessageHandler
from PySide6.QtGui import QGuiApplication
from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
from backend.controller import MemoryController
from backend.settings import SettingsController
from main import create_engine, dispose_engine

messages = []
qInstallMessageHandler(lambda kind, context, message: messages.append(message))
QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.OpenGL)
app = QGuiApplication([])
app.setQuitOnLastWindowClosed(False)
sample = SimpleNamespace(total=16 * 1024**3, available=8 * 1024**3)
memory = MemoryController(sample_provider=lambda: sample)
preferences = SettingsController(args.theme, Path(tempfile.gettempdir()) / "thrashing-header-qa" / "settings.json")
preferences.setAnimations(False)
engine, memory, preferences = create_engine(app, controller=memory, settings=preferences)

def pump(seconds=.08):
    until = time.monotonic() + seconds
    while time.monotonic() < until:
        app.processEvents()
        time.sleep(.005)

def descendants(item):
    for child in item.childItems():
        yield child
        yield from descendants(child)

def rect(item):
    point = item.mapToScene(QPointF(0, 0))
    return dict(x=point.x(), y=point.y(), width=item.width(), height=item.height())

def near(a, b):
    assert abs(a - b) <= .6, (a, b)

checks = []
try:
    pump(1)
    window = next(w for w in app.allWindows() if w.objectName() == "mainWindow")
    window.setTitle("History header QA — simulated RAM")
    near(window.devicePixelRatio(), args.scale)
    plot = window.findChild(QObject, "historyCanvas")
    card = plot.parentItem().parentItem().parentItem()
    title = next(i for i in descendants(card) if i.property("text") == "RAM usage history")
    subtitle = next(i for i in descendants(card) if i.property("text") == "The last 2 minutes of memory activity")
    badge = next(i for i in descendants(card) if i.property("label") == "Normal")
    header = title.parentItem().parentItem()
    views = [("minimum", 900, 640), ("default", 1180, 740)]
    # Find the exact responsive boundary using the actual ScrollView width.
    scroll = window.findChild(QObject, "mainScroll")
    window.resize(1180, 740)
    pump()
    boundary = round(window.width() + 900 - scroll.property("availableWidth"))
    views += [("below_breakpoint", boundary - 1, 740), ("above_breakpoint", boundary + 1, 740), ("maximized", None, None)]
    for view, width, height in views:
        if width is None:
            window.showMaximized()
        else:
            window.showNormal()
            window.resize(width, height)
        pump(.15)
        if view == "below_breakpoint":
            assert not window.property("wide")
        elif view == "above_breakpoint":
            assert window.property("wide")
        stable = None
        for percent, label in [(50, "Normal"), (80, "Warning"), (90, "High RAM usage"), (50, "Normal")]:
            sample.available = sample.total * (100 - percent) // 100
            memory.refresh()
            pump()
            assert badge.property("label") == label
            b, t, s, c, h = map(rect, (badge, title, subtitle, card, header))
            near(b["x"] + b["width"], c["x"] + c["width"] - 24)
            near(t["y"] + t["height"] / 2, b["y"] + b["height"] / 2)
            near(t["x"], c["x"] + 24)
            near(s["x"], t["x"])
            near(s["y"], b["y"] + b["height"] + 6)
            near(b["width"], badge.property("implicitWidth"))
            near(b["height"], 32)
            assert t["x"] + t["width"] + 11 <= b["x"], "Title overlaps badge"
            for text in [title, subtitle] + [i for i in descendants(badge) if i.property("text") == label]:
                assert text.property("lineCount") == 1, "Header text wrapped"
                assert text.width() >= text.property("contentWidth") - .6, "Header text clipped"
            geometry = (h["height"], rect(plot)["y"], plot.height())
            if stable is None:
                stable = geometry
            else:
                for current, previous in zip(geometry, stable):
                    near(current, previous)
            assert plot.width() > 100 and plot.height() > 100
            checks.append(dict(view=view, status=label, window=[window.width(), window.height()], wide=window.property("wide"), badge=b, header=h, chart=rect(plot)))
            if (view == "default" and percent != 50) or (view in ("minimum", "default", "maximized") and label == "Normal" and len(checks) % 4 == 1):
                image = window.grabWindow()
                target = QA_ROOT / "screenshots" / f"history_header_{args.theme}_{args.scale:g}_{view}_{label.replace(' ', '_')}.png"
                assert not image.isNull() and image.save(str(target))
        print(f"PASS {args.theme} DPR {args.scale:g}: {view}, all three statuses", flush=True)
    diagnostics = [m for m in messages if "qrc:/redesign" in m or "binding loop" in m.lower()]
    assert not diagnostics, diagnostics
    report = dict(theme=args.theme, effectiveDpr=window.devicePixelRatio(), nativeDpr=native_scale,
                  windowsScalingChanged=False, simulatedRam=True, checks=checks, diagnostics=diagnostics)
    (QA_ROOT / f"history_header_qa_{args.theme}_{args.scale:g}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
finally:
    dispose_engine(app, engine, memory)
