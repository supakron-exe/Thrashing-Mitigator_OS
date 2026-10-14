"""Administrator launch safety, existing-instance handling, and Windows quoting."""
import ctypes
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PySide6.QtCore import QCoreApplication
from backend.instance import SingleInstance
from tools import launch_admin as launcher

APP = QCoreApplication.instance() or QCoreApplication([])


class AdminLauncherTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.profile = Path(self.directory.name)
        self.root = self.profile / "App folder ภาษาไทย"
        self.lock_path = self.profile / "application.lock"

    def tearDown(self):
        self.directory.cleanup()

    def probe(self, state, pid=42, hostname="test-host", name="pythonw.exe"):
        self.lock_path.write_text("test lock", encoding="utf-8")
        lock = MagicMock()
        lock.getLockInfo.return_value = (pid, hostname, name)
        reader = MagicMock()
        reader.inspect.return_value = state
        return launcher.lookup_owner(self.profile, reader, lambda _: lock, "test-host")

    def test_absent_lock_has_no_owner(self):
        reader = MagicMock()
        self.assertIsNone(launcher.lookup_owner(self.profile, reader))
        reader.inspect.assert_not_called()

    def test_live_lock_reads_actual_elevation(self):
        for elevated in (False, True):
            with self.subTest(elevated=elevated):
                state = launcher.ProcessState(r"C:\App\.runtime\pythonw.exe", 1, elevated)
                self.assertEqual(self.probe(state), launcher.Owner(42, elevated))

    def test_ended_process_and_recycled_pid_are_not_existing_owners(self):
        self.assertIsNone(self.probe(None))
        self.assertIsNone(self.probe(launcher.ProcessState(r"C:\App\pythonw.exe", 9999999999, True)))

    def test_unverifiable_lock_and_other_executable_are_rejected(self):
        for options in ({"pid": 0}, {"hostname": "another-machine"}, {"name": ""}):
            with self.subTest(options=options), self.assertRaises(launcher.OwnerLookupError):
                self.probe(launcher.ProcessState(r"C:\App\pythonw.exe", 1, True), **options)
        with self.assertRaises(launcher.OwnerLookupError):
            self.probe(launcher.ProcessState(r"C:\Windows\notepad.exe", 1, True))

    def test_normal_owner_gets_exit_first_guidance_without_launch(self):
        with patch.object(launcher, "lookup_owner", return_value=launcher.Owner(42, False)), \
                patch.object(launcher, "forward_activation") as forward, \
                patch.object(launcher, "launch_elevated") as elevate, \
                patch.object(launcher.subprocess, "Popen") as launch, \
                patch.object(launcher, "notify") as notify:
            self.assertEqual(launcher.run_admin(self.root), 1)
            notify.assert_called_once_with("normal")
            forward.assert_not_called()
            elevate.assert_not_called()
            launch.assert_not_called()

    def test_elevated_owner_is_activated_instead_of_launched(self):
        with patch.object(launcher, "profile_directory", return_value=self.profile), \
                patch.object(launcher, "lookup_owner", return_value=launcher.Owner(42, True)), \
                patch.object(launcher, "forward_activation", return_value=True) as forward, \
                patch.object(launcher, "launch_elevated") as elevate, \
                patch.object(launcher.subprocess, "Popen") as launch:
            self.assertEqual(launcher.run_admin(self.root, "dark", True), 0)
            forward.assert_called_once_with(self.profile, "dark", True)
            elevate.assert_not_called()
            launch.assert_not_called()

    def test_unresponsive_admin_owner_is_not_replaced(self):
        with patch.object(launcher, "lookup_owner", return_value=launcher.Owner(42, True)), \
                patch.object(launcher, "forward_activation", return_value=False), \
                patch.object(launcher, "launch_elevated") as elevate, \
                patch.object(launcher, "notify") as notify:
            self.assertEqual(launcher.run_admin(self.root), 1)
            notify.assert_called_once_with("activate")
            elevate.assert_not_called()

    def test_unknown_permission_never_claims_or_launches_administrator(self):
        with patch.object(launcher, "lookup_owner", side_effect=launcher.OwnerLookupError("denied")), \
                patch.object(launcher, "launch_elevated") as elevate, \
                patch.object(launcher, "notify") as notify:
            self.assertEqual(launcher.run_admin(self.root), 1)
            notify.assert_called_once_with("unknown")
            elevate.assert_not_called()

    def test_no_owner_requests_native_uac_and_cancellation_is_quiet(self):
        for result in (True, False):
            with self.subTest(uac_result=result), \
                    patch.object(launcher, "lookup_owner", return_value=None), \
                    patch.object(launcher, "WindowsSecurity") as security, \
                    patch.object(launcher, "launch_elevated", return_value=result) as elevate, \
                    patch.object(launcher, "notify") as notify:
                security.return_value.inspect.return_value = launcher.ProcessState("pythonw.exe", 1, False)
                self.assertEqual(launcher.run_admin(self.root, "light"), 0)
                elevate.assert_called_once_with(self.root, "light", False)
                notify.assert_not_called()

    def test_already_elevated_launcher_preserves_permission_without_second_uac(self):
        with patch.object(launcher, "lookup_owner", return_value=None), \
                patch.object(launcher, "WindowsSecurity") as security, \
                patch.object(launcher.subprocess, "Popen") as launch, \
                patch.object(launcher, "launch_elevated") as elevate:
            security.return_value.inspect.return_value = launcher.ProcessState("pythonw.exe", 1, True)
            self.assertEqual(launcher.run_admin(self.root, "dark", True), 0)
            launch.assert_called_once_with(launcher.source_command(self.root, "dark", True), cwd=str(self.root.resolve()), close_fds=True)
            elevate.assert_not_called()

    def test_launch_error_is_reported_without_privilege_fallback(self):
        with patch.object(launcher, "lookup_owner", return_value=None), \
                patch.object(launcher, "WindowsSecurity") as security, \
                patch.object(launcher, "launch_elevated", side_effect=OSError("denied")), \
                patch.object(launcher, "notify") as notify:
            security.return_value.inspect.return_value = launcher.ProcessState("pythonw.exe", 1, False)
            self.assertEqual(launcher.run_admin(self.root), 1)
            self.assertEqual(notify.call_args.args[0], "failed")

    def test_argv_uses_current_root_and_preserves_saved_theme_by_default(self):
        command = launcher.source_command(self.root)
        self.assertEqual(command, [str(self.root / ".venv" / "Scripts" / "pythonw.exe"), str(self.root / "main.py"), "--require-admin"])
        self.assertNotIn("--theme", command)
        self.assertEqual(launcher.source_command(self.root, "dark", True)[2:], ["--require-admin", "--theme", "dark", "--background"])

    def test_activation_channel_matches_the_production_instance(self):
        with patch("backend.instance.QLocalServer"):
            instance = SingleInstance(self.profile)
            try:
                self.assertTrue(instance.primary)
                self.assertEqual(launcher.channel_name(self.profile), instance.name)
            finally:
                instance.close()

    @unittest.skipUnless(sys.platform == "win32", "Windows native lock owner query")
    def test_actual_qt_lock_owner_matches_queried_process_permission(self):
        with patch("backend.instance.QLocalServer"):
            instance = SingleInstance(self.profile)
            try:
                self.assertTrue(instance.primary)
                state = launcher.WindowsSecurity().inspect(os.getpid())
                self.assertEqual(launcher.lookup_owner(self.profile), launcher.Owner(os.getpid(), state.elevated))
            finally:
                instance.close()

    @unittest.skipUnless(sys.platform == "win32", "Windows native process query")
    def test_native_query_reads_this_process_and_dead_pid(self):
        reader = launcher.WindowsSecurity()
        state = reader.inspect(os.getpid())
        self.assertIsInstance(state, launcher.ProcessState)
        self.assertEqual(Path(state.image).name.lower(), Path(sys.executable).name.lower())
        self.assertIs(type(state.elevated), bool)
        self.assertGreater(state.created, 0)
        self.assertIsNone(reader.inspect(0xFFFFFFFE))

    @unittest.skipUnless(sys.platform == "win32", "Windows ctypes shell call")
    def test_shell_requests_runas_with_quoted_thai_path_and_closes_process_handle(self):
        shell, kernel = MagicMock(), MagicMock()
        captured = {}
        def invoke(pointer):
            info = ctypes.cast(pointer, ctypes.POINTER(launcher.ShellExecuteInfo)).contents
            captured.update(verb=info.lpVerb, file=info.lpFile, arguments=info.lpParameters, directory=info.lpDirectory)
            info.hProcess = 707
            return True
        shell.ShellExecuteExW.side_effect = invoke
        with patch.object(launcher.ctypes, "WinDLL", side_effect=[shell, kernel]):
            self.assertTrue(launcher.launch_elevated(self.root, "dark", True))
        self.assertEqual(captured["verb"], "runas")
        self.assertEqual(captured["file"], str(self.root / ".venv" / "Scripts" / "pythonw.exe"))
        self.assertEqual(captured["arguments"], f'"{self.root / "main.py"}" --require-admin --theme dark --background')
        self.assertEqual(captured["directory"], str(self.root))
        kernel.CloseHandle.assert_called_once_with(707)

    @unittest.skipUnless(sys.platform == "win32", "Windows ctypes shell call")
    def test_shell_uac_cancel_is_distinct_from_other_failure(self):
        shell = MagicMock()
        shell.ShellExecuteExW.return_value = False
        with patch.object(launcher.ctypes, "WinDLL", return_value=shell), \
                patch.object(launcher.ctypes, "get_last_error", return_value=1223):
            self.assertFalse(launcher.launch_elevated(self.root))
        with patch.object(launcher.ctypes, "WinDLL", return_value=shell), \
                patch.object(launcher.ctypes, "get_last_error", return_value=5):
            with self.assertRaises(OSError):
                launcher.launch_elevated(self.root)

    def test_admin_entrypoint_requires_real_self_elevation(self):
        with patch.object(launcher, "WindowsSecurity") as security, \
                patch.object(launcher, "lookup_owner") as lookup, \
                patch.object(launcher, "notify") as notify:
            security.return_value.inspect.return_value = launcher.ProcessState("pythonw.exe", 1, False)
            self.assertFalse(launcher.verify_admin_context(self.profile))
            self.assertEqual(notify.call_args.args[0], "failed")
            lookup.assert_not_called()
            notify.reset_mock()
            security.return_value.inspect.return_value = launcher.ProcessState("pythonw.exe", 1, True)
            self.assertTrue(launcher.verify_admin_context(self.profile))
            notify.assert_not_called()
            lookup.assert_not_called()

    def test_normal_instance_started_during_uac_is_never_forwarded_as_admin(self):
        with patch.object(launcher, "WindowsSecurity") as security, \
                patch.object(launcher, "lookup_owner", return_value=launcher.Owner(42, False)), \
                patch.object(launcher, "notify") as notify:
            security.return_value.inspect.return_value = launcher.ProcessState("pythonw.exe", 1, True)
            self.assertFalse(launcher.verify_admin_context(self.profile, require_owner=True))
            notify.assert_called_once_with("normal")

    def test_admin_secondary_entrypoint_requires_verified_admin_owner(self):
        with patch.object(launcher, "WindowsSecurity") as security, \
                patch.object(launcher, "lookup_owner") as lookup, \
                patch.object(launcher, "notify") as notify:
            security.return_value.inspect.return_value = launcher.ProcessState("pythonw.exe", 1, True)
            lookup.return_value = launcher.Owner(42, True)
            self.assertTrue(launcher.verify_admin_context(self.profile, require_owner=True))
            notify.assert_not_called()
            lookup.return_value = None
            self.assertFalse(launcher.verify_admin_context(self.profile, require_owner=True))
            notify.assert_called_once_with("unknown")
            notify.reset_mock()
            lookup.side_effect = launcher.OwnerLookupError("denied")
            self.assertFalse(launcher.verify_admin_context(self.profile, require_owner=True))
            notify.assert_called_once_with("unknown")


if __name__ == "__main__":
    unittest.main()
