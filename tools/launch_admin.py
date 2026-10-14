"""Open the source app through Windows UAC, without replacing a running instance."""
import argparse
import ctypes
from ctypes import wintypes as W
from dataclasses import dataclass
import hashlib
import json
import ntpath
import os
from pathlib import Path
import subprocess
import sys
import time

from PySide6.QtCore import QLockFile, QSysInfo
from PySide6.QtNetwork import QLocalSocket

ROOT = Path(__file__).resolve().parents[1]
APP_DIRECTORY = "ThrashingMitigatorRedesign"


class OwnerLookupError(OSError):
    """A present lock cannot be linked safely to a live process."""


@dataclass(frozen=True)
class ProcessState:
    image: str
    created: float
    elevated: bool


@dataclass(frozen=True)
class Owner:
    pid: int
    elevated: bool


class WindowsSecurity:
    """Query-only process and token inspection; handles are always closed."""

    def __init__(self):
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.security = ctypes.WinDLL("advapi32", use_last_error=True)
        self.kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
        self.kernel.OpenProcess.restype = W.HANDLE
        self.kernel.CloseHandle.argtypes = [W.HANDLE]
        self.kernel.CloseHandle.restype = W.BOOL
        self.kernel.GetExitCodeProcess.argtypes = [W.HANDLE, ctypes.POINTER(W.DWORD)]
        self.kernel.GetExitCodeProcess.restype = W.BOOL
        self.kernel.GetProcessTimes.argtypes = [W.HANDLE] + [ctypes.POINTER(W.FILETIME)] * 4
        self.kernel.GetProcessTimes.restype = W.BOOL
        self.kernel.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, ctypes.POINTER(W.DWORD)]
        self.kernel.QueryFullProcessImageNameW.restype = W.BOOL
        self.security.OpenProcessToken.argtypes = [W.HANDLE, W.DWORD, ctypes.POINTER(W.HANDLE)]
        self.security.OpenProcessToken.restype = W.BOOL
        self.security.GetTokenInformation.argtypes = [W.HANDLE, ctypes.c_int, W.LPVOID, W.DWORD, ctypes.POINTER(W.DWORD)]
        self.security.GetTokenInformation.restype = W.BOOL

    def inspect(self, pid):
        process = self.kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not process:
            code = ctypes.get_last_error()
            if code == 87:  # ERROR_INVALID_PARAMETER: PID no longer exists.
                return None
            raise OwnerLookupError(f"Unable to inspect process {pid} (Windows error {code}).")
        token = W.HANDLE()
        try:
            exit_code = W.DWORD()
            if not self.kernel.GetExitCodeProcess(process, ctypes.byref(exit_code)):
                raise OwnerLookupError("Unable to inspect the running application.")
            if exit_code.value != 259:  # STILL_ACTIVE
                return None
            created, exited, kernel, user = W.FILETIME(), W.FILETIME(), W.FILETIME(), W.FILETIME()
            if not self.kernel.GetProcessTimes(process, ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel), ctypes.byref(user)):
                raise OwnerLookupError("Unable to verify the application process identity.")
            buffer = ctypes.create_unicode_buffer(32768)
            length = W.DWORD(len(buffer))
            if not self.kernel.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(length)):
                raise OwnerLookupError("Unable to verify the application executable.")
            if not self.security.OpenProcessToken(process, 8, ctypes.byref(token)):  # TOKEN_QUERY
                raise OwnerLookupError("Unable to check the application's administrator permission.")
            elevation, needed = W.DWORD(), W.DWORD()
            if not self.security.GetTokenInformation(token, 20, ctypes.byref(elevation), ctypes.sizeof(elevation), ctypes.byref(needed)):
                raise OwnerLookupError("Unable to check the application's administrator permission.")
            born = ((created.dwHighDateTime << 32) | created.dwLowDateTime) / 10000000 - 11644473600
            return ProcessState(buffer.value, born, elevation.value != 0)
        finally:
            if token:
                self.kernel.CloseHandle(token)
            self.kernel.CloseHandle(process)


def profile_directory():
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / APP_DIRECTORY


def lookup_owner(directory, reader=None, lock_factory=QLockFile, hostname=None):
    path = Path(directory) / "application.lock"
    if not path.exists():
        return None
    pid, host, name = lock_factory(str(path)).getLockInfo()
    if pid <= 0 or not name or host.casefold() != (hostname or QSysInfo.machineHostName()).casefold():
        raise OwnerLookupError("Unable to verify the existing application's lock.")
    state = (reader or WindowsSecurity()).inspect(pid)
    if state is None:
        return None
    # A process created after the lock is a recycled PID, not its original owner.
    if state.created > path.stat().st_mtime + .001:
        return None
    if ntpath.basename(state.image).casefold() not in ("python.exe", "pythonw.exe", "thrashingmitigator.exe"):
        raise OwnerLookupError("The existing lock does not belong to the application executable.")
    return Owner(pid, state.elevated)


def channel_name(directory):
    digest = hashlib.sha256(str(Path(directory).resolve()).lower().encode()).hexdigest()[:16]
    return APP_DIRECTORY + "-" + digest


def forward_activation(directory, theme=None, background=False, timeout=5):
    """Only activate the verified owner; never acquire the application lock."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        socket = QLocalSocket()
        socket.connectToServer(channel_name(directory))
        if socket.waitForConnected(200):
            socket.write(json.dumps(dict(theme=theme, background=background)).encode() + b"\n")
            socket.flush()
            if socket.waitForReadyRead(1000) and bytes(socket.readAll()) == b"OK\n":
                socket.disconnectFromServer()
                return True
        socket.abort()
        time.sleep(.1)
    return False


def source_command(root, theme=None, background=False):
    root = Path(root).resolve()
    arguments = [str(root / ".venv" / "Scripts" / "pythonw.exe"), str(root / "main.py"), "--require-admin"]
    if theme is not None:
        arguments += ["--theme", theme]
    if background:
        arguments.append("--background")
    return arguments


class ShellExecuteInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", W.DWORD), ("fMask", W.ULONG), ("hwnd", W.HWND),
        ("lpVerb", W.LPCWSTR), ("lpFile", W.LPCWSTR), ("lpParameters", W.LPCWSTR),
        ("lpDirectory", W.LPCWSTR), ("nShow", ctypes.c_int), ("hInstApp", W.HINSTANCE),
        ("lpIDList", W.LPVOID), ("lpClass", W.LPCWSTR), ("hkeyClass", W.HKEY),
        ("dwHotKey", W.DWORD), ("hIcon", W.HANDLE), ("hProcess", W.HANDLE),
    ]


def launch_elevated(root, theme=None, background=False):
    arguments = source_command(root, theme, background)
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    shell.ShellExecuteExW.argtypes = [ctypes.POINTER(ShellExecuteInfo)]
    shell.ShellExecuteExW.restype = W.BOOL
    info = ShellExecuteInfo()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = 0x40  # SEE_MASK_NOCLOSEPROCESS
    info.lpVerb = "runas"
    info.lpFile = arguments[0]
    info.lpParameters = subprocess.list2cmdline(arguments[1:])
    info.lpDirectory = str(Path(root).resolve())
    info.nShow = 1
    if not shell.ShellExecuteExW(ctypes.byref(info)):
        code = ctypes.get_last_error()
        if code == 1223:  # The user cancelled UAC.
            return False
        raise OSError(code, "Windows could not open the app as administrator.")
    if info.hProcess:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.CloseHandle.argtypes = [W.HANDLE]
        kernel.CloseHandle.restype = W.BOOL
        kernel.CloseHandle(info.hProcess)
    return True


def notify(kind, detail=""):
    from PySide6.QtWidgets import QMessageBox
    try:
        settings = json.loads((profile_directory() / "settings.json").read_text(encoding="utf-8"))
        thai = isinstance(settings, dict) and settings.get("language") == "th"
    except (OSError, ValueError):
        thai = False
    messages = {
        "normal": (
            "The app is already running without administrator permission.\nRight-click its Tray icon → Exit, then open run_admin.cmd again.\nThe app will finish any active optimization before exiting.",
            "แอปที่เปิดอยู่ยังไม่ได้ใช้สิทธิ์แอดมิน\nคลิกขวาไอคอนแอปใน Tray → Exit แล้วเปิด run_admin.cmd อีกครั้ง\nแอปจะรอให้งาน Optimize ที่กำลังทำอยู่จบก่อนออก",
        ),
        "unknown": (
            "Unable to verify the running application's permission.\nExit the app from its Tray menu, then open run_admin.cmd again.",
            "ยังตรวจสอบสิทธิ์ของแอปที่เปิดอยู่ไม่ได้\nออกจากแอปผ่านเมนู Tray → Exit แล้วเปิด run_admin.cmd อีกครั้ง",
        ),
        "activate": (
            "The administrator app is already running, but could not be brought forward.\nOpen it from its Tray icon, or use Tray → Exit and try again.",
            "แอปแบบแอดมินเปิดอยู่แล้ว แต่ยังเรียกหน้าต่างกลับมาไม่ได้\nเปิดจากไอคอนใน Tray หรือเลือก Tray → Exit แล้วลองใหม่",
        ),
        "failed": (
            "Unable to open Thrashing Mitigator as administrator.",
            "เปิด Thrashing Mitigator แบบแอดมินไม่สำเร็จ",
        ),
    }
    message = messages[kind][1 if thai else 0]
    if detail:
        message += "\n\n" + str(detail)
    QMessageBox.warning(None, "Thrashing Mitigator", message)


def run_admin(root=ROOT, theme=None, background=False):
    directory = profile_directory()
    try:
        owner = lookup_owner(directory)
    except (OSError, RuntimeError):
        notify("unknown")
        return 1
    if owner is not None:
        if not owner.elevated:
            notify("normal")
            return 1
        if forward_activation(directory, theme, background):
            return 0
        notify("activate")
        return 1
    try:
        current = WindowsSecurity().inspect(os.getpid())
        if current is not None and current.elevated:
            subprocess.Popen(source_command(root, theme, background), cwd=str(Path(root).resolve()), close_fds=True)
        else:
            launch_elevated(root, theme, background)
        return 0
    except (OSError, RuntimeError) as exc:
        notify("failed", exc)
        return 1


def verify_admin_context(directory, require_owner=False):
    """Guard the elevated entry point against a normal instance starting during UAC."""
    try:
        current = WindowsSecurity().inspect(os.getpid())
        if current is None or not current.elevated:
            notify("failed", "Open run_admin.cmd to request administrator permission through Windows UAC.")
            return False
        if require_owner:
            owner = lookup_owner(directory)
            if owner is None:
                notify("unknown")
                return False
            if not owner.elevated:
                notify("normal")
                return False
        return True
    except (OSError, RuntimeError):
        notify("unknown")
        return False


def main():
    parser = argparse.ArgumentParser(description="Open Thrashing Mitigator as administrator using Windows UAC.")
    parser.add_argument("--theme", choices=("light", "dark"), default=None)
    parser.add_argument("--background", action="store_true")
    args = parser.parse_args()
    from PySide6.QtWidgets import QApplication
    application = QApplication(sys.argv)
    application.setApplicationName("Thrashing Mitigator launcher")
    return run_admin(ROOT, args.theme, args.background)


if __name__ == "__main__":
    raise SystemExit(main())
