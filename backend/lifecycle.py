from PySide6.QtCore import QObject, Property, Signal, Slot, Qt, QRect
from backend.localization import tr, display_text


class WindowLifecycle(QObject):
    """No-tray lifecycle for embedded engines and existing QGuiApplication QA."""
    changed = Signal()

    def __init__(self, memory, parent=None):
        super().__init__(parent)
        self.memory, self._exiting = memory, False

    @Property(bool, notify=changed)
    def exiting(self): return self._exiting

    @Property(bool, notify=changed)
    def trayAvailable(self): return False

    @Slot(QObject)
    def windowReady(self, window): pass

    @Slot(QObject)
    def closeWindow(self, window): self.exit()

    @Slot()
    def exit(self):
        self._exiting = True
        self.changed.emit()
        self.memory.requestClose()


class TrayLifecycle(WindowLifecycle):
    def __init__(self, app, memory, automatic, preferences, background=False, parent=None):
        super().__init__(memory, parent)
        from PySide6.QtGui import QIcon, QPixmap
        from PySide6.QtWidgets import QSystemTrayIcon, QMenu
        self.app, self.automatic, self.preferences = app, automatic, preferences
        self.window, self._maximized, self._pending, self._background = None, False, None, background
        self._available = None
        pixmap = QPixmap(":/redesign/assets/logo.png").copy(QRect(880, 256, 1058, 935)).scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.tray = QSystemTrayIcon(QIcon(pixmap), self)
        self.menu = QMenu()
        self.open_action = self.menu.addAction("Open", self.open)
        self.pause_action = self.menu.addAction("Resume Auto Optimize", self.toggleAuto)
        self.menu.addSeparator()
        self.exit_action = self.menu.addAction("Exit", self.exit)
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._activated)
        self.tray.messageClicked.connect(self.open)
        automatic.changed.connect(self._update)
        automatic.attention.connect(self._attention)
        memory.closeReady.connect(self.tray.hide)
        self.tray.show()
        self._update()

    @Property(bool, notify=WindowLifecycle.changed)
    def trayAvailable(self):
        from PySide6.QtWidgets import QSystemTrayIcon
        return QSystemTrayIcon.isSystemTrayAvailable()

    def attach(self, window, background=False):
        self.window = window
        if self._pending:
            data, self._pending = self._pending, None
            self.activate(data)
        elif background and self.trayAvailable:
            window.hide()
        elif background: self.open()

    @Slot(QObject)
    def windowReady(self, window): self.attach(window, self._background)

    @Slot(object)
    def activate(self, data):
        if self.window is None:
            self._pending = data
            return
        if data.get("theme"): self.preferences.setTheme(data["theme"])
        if not data.get("background"): self.open()

    @Slot()
    def open(self):
        if self.window is None: return
        if self._maximized: self.window.showMaximized()
        else: self.window.showNormal()
        self.window.raise_()
        self.window.requestActivate()

    @Slot(QObject)
    def closeWindow(self, window):
        if self._exiting: return
        if self.trayAvailable:
            self._maximized = window.visibility() == window.Visibility.Maximized
            window.hide()
        else:
            window.show()
            window.requestActivate()
            self.changed.emit()

    def _activated(self, reason):
        from PySide6.QtWidgets import QSystemTrayIcon
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick): self.open()

    @Slot()
    def toggleAuto(self): self.automatic.setEnabled(not self.automatic.enabled)

    @Slot()
    def exit(self):
        if self._exiting: return
        self.automatic.shutdown()
        super().exit()

    def _update(self):
        available = self.trayAvailable
        if available != self._available:
            self._available = available
            self.changed.emit()
        self.open_action.setText(tr("Open"))
        self.exit_action.setText(tr("Exit"))
        self.pause_action.setText(tr("Pause Auto Optimize" if self.automatic.enabled else "Resume Auto Optimize"))
        self.menu.setFont(self.app.font())
        self.tray.setToolTip("Thrashing Mitigator — " + tr("Auto Optimize") + " · " + display_text(self.automatic.status))

    def _attention(self, message):
        from PySide6.QtWidgets import QSystemTrayIcon
        if self.window is None or not self.window.isVisible():
            self.tray.showMessage(tr("Auto Optimize paused"), display_text(message)[:200], QSystemTrayIcon.Warning)
