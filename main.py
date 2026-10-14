import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "vendor"))
os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

from PySide6.QtCore import QUrl, qInstallMessageHandler
from PySide6.QtGui import QGuiApplication, QFont, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
from FluentUI import FluentUI
from backend.controller import MemoryController
from backend.settings import SettingsController
from backend.auto_optimize import AutoOptimizeController
from backend.lifecycle import WindowLifecycle
from backend.localization import LanguageController, PresentationController, tr
from backend.insights.controller import InsightsController
import resource_rc  # Generated from resources.qrc, not edited by hand.
import shiboken6


def create_engine(app, theme=None, controller=None, settings=None, automatic=None, lifecycle=None, language=None):
    engine = QQmlApplicationEngine()
    memory = controller or MemoryController()
    preferences = settings or SettingsController(theme=theme)
    automatic = automatic or AutoOptimizeController(memory, preferences)
    lifecycle = lifecycle or WindowLifecycle(memory)
    language = language or LanguageController(app, preferences)
    language.engine = engine
    presentation = PresentationController(memory, automatic, language)
    insights = InsightsController(memory, path=preferences.path.parent / 'insights' / 'insights.db', language=language)
    engine.rootContext().setContextProperty("Memory", memory)
    engine.rootContext().setContextProperty("Preferences", preferences)
    engine.rootContext().setContextProperty("Auto", automatic)
    engine.rootContext().setContextProperty("Lifecycle", lifecycle)
    engine.rootContext().setContextProperty("Language", language)
    engine.rootContext().setContextProperty("Presenter", presentation)
    engine.rootContext().setContextProperty("Insights", insights)
    FluentUI.registerTypes(engine)
    engine.load(QUrl("qrc:/redesign/qml/App.qml"))
    if not engine.rootObjects():
        insights.shutdown()
        memory.shutdown()
        raise RuntimeError("The QML interface could not be loaded. See the diagnostics above.")
    def quit_when_ready():
        if memory.closing and memory.safeToClose and insights.safeToClose:
            app.quit()
    memory.closeReady.connect(quit_when_ready)
    insights.closeReady.connect(quit_when_ready)
    engine._quit_when_ready = quit_when_ready
    engine._memory, engine._preferences = memory, preferences
    engine._automatic, engine._lifecycle = automatic, lifecycle
    engine._language, engine._presentation = language, presentation
    engine._insights = insights
    return engine, memory, preferences


def dispose_engine(app, engine, memory):
    """Destroy routed windows while their Python context objects are still alive."""
    engine._automatic.shutdown()
    engine._insights.shutdown()
    memory.shutdown()
    for window in list(app.allWindows()):
        if window.objectName() == "mainWindow":
            window.hide()
            shiboken6.delete(window)
    engine._language.dispose()
    shiboken6.delete(engine)


def main():
    parser = argparse.ArgumentParser(description="Thrashing Mitigator — Fluent Premium")
    parser.add_argument("--theme", choices=("light", "dark"), default=None)
    parser.add_argument("--background", action="store_true")
    parser.add_argument("--require-admin", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.OpenGL)
    from PySide6.QtWidgets import QApplication, QMessageBox
    from backend.instance import SingleInstance
    from backend.startup import WindowsStartup
    from backend.lifecycle import TrayLifecycle
    directory = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ThrashingMitigatorRedesign"
    directory.mkdir(parents=True, exist_ok=True)
    log = (directory / "application.log").open("a", encoding="utf-8", buffering=1)
    if sys.stdout is None: sys.stdout = log
    if sys.stderr is None: sys.stderr = log
    qInstallMessageHandler(lambda kind, context, message: log.write(message + "\n"))
    app = QApplication(sys.argv)
    app.setApplicationName("ThrashingMitigatorRedesign")
    app.setApplicationDisplayName("Thrashing Mitigator")
    app.setOrganizationName("ThrashingMitigatorRedesign")
    app.setFont(QFont("Segoe UI", 10))
    app.setWindowIcon(QIcon(":/redesign/assets/logo.png"))
    app.setQuitOnLastWindowClosed(False)
    preferences = SettingsController(args.theme)
    language = LanguageController(app, preferences)
    if args.require_admin:
        from tools.launch_admin import verify_admin_context
        if not verify_admin_context(directory):
            return 1
    instance = SingleInstance(directory)
    if not instance.primary:
        if args.require_admin and not verify_admin_context(directory, require_owner=True):
            instance.close()
            return 1
        if not instance.forward(args.theme, args.background):
            QMessageBox.warning(None, "Thrashing Mitigator", tr("This version is already running. Open it from Tray, or try again shortly."))
            return 1
        return 0
    memory = MemoryController()
    startup = WindowsStartup(ROOT)
    try: preferences._auto["startWithWindows"] = startup.is_enabled()
    except OSError: pass
    automatic = AutoOptimizeController(memory, preferences, startup=startup)
    lifecycle = TrayLifecycle(app, memory, automatic, preferences, background=args.background)
    lifecycle.language = language
    language.changed.connect(lifecycle._update)
    lifecycle._update()
    instance.activate.connect(lifecycle.activate)
    engine, memory, preferences = create_engine(app, controller=memory, settings=preferences, automatic=automatic, lifecycle=lifecycle, language=language)
    try:
        return app.exec()
    finally:
        dispose_engine(app, engine, memory)
        lifecycle.tray.hide()
        lifecycle.menu.deleteLater()
        instance.close()


if __name__ == "__main__":
    raise SystemExit(main())
