"""Per-user startup registration; no registration happens merely by importing."""
import subprocess
from pathlib import Path
import sys
import winreg


class WindowsStartup:
    key = r"Software\Microsoft\Windows\CurrentVersion\Run"
    name = "ThrashingMitigatorRedesign"

    def __init__(self, root):
        if getattr(sys, "frozen", False):
            arguments = [sys.executable, "--background"]
        else:
            pythonw = Path(sys.executable).with_name("pythonw.exe")
            arguments = [str(pythonw), str(Path(root) / "main.py"), "--background"]
        self.command = subprocess.list2cmdline(arguments)

    def is_enabled(self):
        entry = self.capture()
        return entry is not None and entry[0] == self.command

    def capture(self):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.key) as key:
                return winreg.QueryValueEx(key, self.name)
        except FileNotFoundError:
            return None

    def restore(self, entry):
        if entry is None: self.set_enabled(False)
        else:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, self.key, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, self.name, 0, entry[1], entry[0])

    def set_enabled(self, enabled):
        if enabled:
            if len(self.command) > 260:
                raise OSError("The application path is too long for Windows startup registration.")
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, self.key, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, self.name, 0, winreg.REG_SZ, self.command)
        else:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.key, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.DeleteValue(key, self.name)
            except FileNotFoundError: pass
