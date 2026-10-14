"""Lock enforces exclusivity; the local socket only activates the owner."""
import hashlib
import json
import time
from PySide6.QtCore import QObject, QLockFile, QTimer, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class SingleInstance(QObject):
    activate = Signal(object)

    def __init__(self, directory, parent=None):
        super().__init__(parent)
        directory.mkdir(parents=True, exist_ok=True)
        self.name = "ThrashingMitigatorRedesign-" + hashlib.sha256(str(directory.resolve()).lower().encode()).hexdigest()[:16]
        self.lock = QLockFile(str(directory / "application.lock"))
        self.lock.setStaleLockTime(0)
        self.primary = self.lock.tryLock(0)
        self.server = None
        self._clients = {}
        if self.primary:
            self.server = QLocalServer(self)
            self.server.setSocketOptions(QLocalServer.UserAccessOption)
            if not self.server.listen(self.name):
                self.lock.unlock()
                raise OSError("Unable to create application activation channel.")
            self.server.newConnection.connect(self._connection)

    def forward(self, theme=None, background=False, timeout=5):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            socket = QLocalSocket()
            socket.connectToServer(self.name)
            if socket.waitForConnected(200):
                socket.write(json.dumps(dict(theme=theme, background=background)).encode() + b"\n")
                socket.flush()
                if socket.waitForReadyRead(1000) and bytes(socket.readAll()) == b"OK\n":
                    socket.disconnectFromServer()
                    return True
            socket.abort()
            time.sleep(.1)
        return False

    def _connection(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            self._clients[socket] = bytearray()
            socket.readyRead.connect(lambda s=socket: self._read(s))
            socket.disconnected.connect(lambda s=socket: self._discard(s))
            timeout = QTimer(socket)
            timeout.setSingleShot(True)
            timeout.timeout.connect(socket.disconnectFromServer)
            timeout.start(2000)
            self._read(socket)

    def _read(self, socket):
        if socket not in self._clients: return
        buffer = self._clients[socket]
        buffer.extend(bytes(socket.readAll()))
        if len(buffer) > 512:
            socket.disconnectFromServer()
            return
        if b"\n" not in buffer: return
        try:
            data = json.loads(bytes(buffer).split(b"\n")[0])
            if not isinstance(data, dict) or data.get("theme") not in (None, "light", "dark"):
                raise ValueError("Invalid activation")
            self.activate.emit(dict(theme=data.get("theme"), background=data.get("background") is True))
            socket.write(b"OK\n")
            socket.flush()
        except (ValueError, TypeError):
            socket.disconnectFromServer()
        self._clients.pop(socket, None)

    def _discard(self, socket):
        self._clients.pop(socket, None)
        socket.deleteLater()

    def close(self):
        if self.server: self.server.close()
        if self.primary: self.lock.unlock()
