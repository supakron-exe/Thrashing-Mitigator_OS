from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from qa_support import QA_ROOT, qa_path
from backend.startup import WindowsStartup


class StartupTests(unittest.TestCase):
    def test_frozen_startup_uses_stable_executable_not_bundle_python(self):
        with patch('backend.startup.sys.executable', r'C:\App Folder\ThrashingMitigator.exe'), patch('backend.startup.sys.frozen', True, create=True):
            startup=WindowsStartup(Path(r'C:\Temporary Extraction'))
        self.assertEqual(startup.command, r'"C:\App Folder\ThrashingMitigator.exe" --background')
        self.assertNotIn('main.py', startup.command)

    def test_quoted_current_interpreter_and_background_command(self):
        with patch('backend.startup.sys.executable',r'C:\App Folder\.venv\Scripts\python.exe'):
            startup=WindowsStartup(Path(r'C:\App Folder'))
        self.assertIn('pythonw.exe"',startup.command)
        self.assertIn('main.py"',startup.command)
        self.assertTrue(startup.command.endswith('--background'))

    def test_only_owned_per_user_value_is_modified_and_exactly_restored(self):
        registry=MagicMock()
        registry.HKEY_CURRENT_USER='user'; registry.KEY_SET_VALUE=2; registry.REG_SZ=1
        key=registry.CreateKeyEx.return_value.__enter__.return_value
        old=(r'"C:\Older App\pythonw.exe" main.py',1)
        registry.QueryValueEx.return_value=old
        with patch('backend.startup.winreg',registry):
            startup=WindowsStartup(ROOT)
            self.assertEqual(startup.capture(),old)
            self.assertFalse(startup.is_enabled())
            startup.set_enabled(True)
            registry.CreateKeyEx.assert_called_with('user',startup.key,0,2)
            registry.SetValueEx.assert_called_with(key,startup.name,0,1,startup.command)
            startup.restore(old)
            registry.SetValueEx.assert_called_with(key,startup.name,0,old[1],old[0])
            startup.set_enabled(False)
            self.assertEqual(registry.DeleteValue.call_args.args[1],startup.name)
            registry.DeleteKey.assert_not_called()

    def test_missing_registration_and_permission_errors(self):
        registry=MagicMock()
        registry.OpenKey.side_effect=FileNotFoundError
        with patch('backend.startup.winreg',registry):
            startup=WindowsStartup(ROOT)
            self.assertFalse(startup.is_enabled())
            startup.set_enabled(False)
            registry.CreateKeyEx.side_effect=PermissionError('Denied')
            with self.assertRaises(PermissionError):startup.set_enabled(True)


if __name__=='__main__':unittest.main()
