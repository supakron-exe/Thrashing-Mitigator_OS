import ast
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import sys
import re

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from qa_support import QA_ROOT, qa_path
from PySide6.QtCore import QCoreApplication
from backend.controller import MemoryController
from backend.presentation import present_result, memory_label
from backend.settings import SettingsController
from backend.service import run_optimization

APP = QCoreApplication.instance() or QCoreApplication([])

def pump_until(predicate, timeout=3):
    end = time.monotonic() + timeout
    while not predicate():
        APP.processEvents()
        time.sleep(.005)
        if time.monotonic() > end:
            raise AssertionError("Timed out")
    APP.processEvents()

def result(**overrides):
    data = {"supported": True, "trimmed": 2, "failed": 0, "available_before_mb": 1000,
            "available_after_mb": 1120, "available_delta_mb": 120, "duration_s": 2.5, "targets": []}
    data.update(overrides)
    return data

class PresentationTests(unittest.TestCase):
    def test_success_uses_available_not_working_set(self):
        r = present_result(result(trimmed_mb=9000), "Standard")
        self.assertEqual(r["gainMb"], 120)
        self.assertEqual(r["tone"], "success")

    def test_zero_and_negative_gain_are_honest(self):
        for delta in (0, -100):
            r = present_result(result(available_delta_mb=delta), "Standard")
            self.assertEqual(r["title"], "No RAM gain measured")
            self.assertEqual(r["gainMb"], delta)

    def test_no_eligible_apps(self):
        self.assertEqual(present_result(result(trimmed=0), "Standard")["title"], "No eligible idle apps")

    def test_unsupported(self):
        r = present_result(result(supported=False), "Standard")
        self.assertEqual(r["title"], "Readings only")
        self.assertFalse(r["hasMeasurements"])

    def test_error_does_not_claim_no_changes(self):
        r = present_result({"error": "Failure after partial work"}, "Maximum")
        self.assertEqual(r["tone"], "error")
        self.assertNotIn("Nothing", r["message"])
        self.assertFalse(r["hasMeasurements"])

    def test_admin_needed_and_partial_nonadmin(self):
        for mode in ("Deep", "Maximum"):
            self.assertEqual(present_result(result(trimmed=0, elevated=False), mode)["title"], "Administrator access needed")
            self.assertEqual(present_result(result(trimmed=2, elevated=False), mode)["title"], "Optimization complete")

    def test_maximum_prefers_positive_settled_and_falls_back(self):
        for settled, expected in ((65, 65), (0, 120), (-20, 120)):
            r = present_result(result(engine="maximum", elevated=True, available_settled_delta_mb=settled, available_settled_mb=1065, free_delta_mb=300), "Maximum")
            self.assertEqual(r["gainMb"], expected)
            self.assertEqual(r["freeChange"], "+300.0 MB")

    def test_denied_targets_remain_skipped(self):
        r = present_result(result(failed=1, targets=[{"name": "Denied", "ok": False, "reason": "Access denied"}, {"name": "Good", "ok": True, "freed_mb": 50}]), "Standard")
        self.assertFalse(r["targets"][0]["ok"])
        self.assertTrue(r["targets"][1]["ok"])
        self.assertIn("skipped", r["message"])

    def test_missing_nonfinite_measurements(self):
        self.assertEqual(memory_label(float("nan")), "0.0 MB")
        self.assertEqual(memory_label(None), "0.0 MB")
        self.assertEqual(memory_label(2048, True), "+2.0 GB")

    def test_missing_settled_measurement_uses_completion_for_comparison(self):
        r = present_result(result(engine="maximum"), "Maximum")
        self.assertEqual(r["measurementLabel"], "At completion")
        self.assertEqual(r["afterMb"], 1120)

class MonitoringTests(unittest.TestCase):
    def test_one_snapshot_clamped_and_thresholds(self):
        data = SimpleNamespace(total=1000, available=600)
        c = MemoryController(sample_provider=lambda: data)
        try:
            for available, state in ((251, "Normal"), (250, "Warning"), (150, "High RAM usage"), (1200, "Normal"), (-10, "High RAM usage")):
                data.available = available
                c.refresh()
                self.assertEqual(c.snapshot["pressure"], state)
                self.assertEqual(c.snapshot["used"] + c.snapshot["available"], c.snapshot["total"])
                self.assertEqual(c.history[-1]["percent"], c.snapshot["percent"])
            data.total = 0
            c.refresh()
            self.assertEqual(c.snapshot["percent"], 0)
        finally:
            c.shutdown()

    def test_history_bound(self):
        c = MemoryController(sample_provider=lambda: SimpleNamespace(total=1000, available=600))
        try:
            for _ in range(70): c.refresh()
            self.assertEqual(len(c.history), 60)
        finally: c.shutdown()

    def test_sampling_failure_preserves_last_snapshot_and_recovers(self):
        c = MemoryController(sample_provider=lambda: SimpleNamespace(total=1000, available=600))
        old = c.snapshot.copy()
        try:
            def fail(): raise OSError("No readings")
            c._provider = fail
            c.refresh()
            self.assertFalse(c.live)
            self.assertEqual(c.snapshot, old)
            c._provider = lambda: SimpleNamespace(total=1000, available=700)
            c.refresh()
            self.assertTrue(c.live)
            self.assertEqual(c.monitorError, "")
        finally: c.shutdown()

class WorkerTests(unittest.TestCase):
    def test_worker_progress_duplicate_guard_cooldown_and_live_monitoring(self):
        calls = []
        gui_thread = threading.get_ident()
        def run(mode, progress):
            calls.append((mode, threading.get_ident()))
            progress("Real queued progress")
            time.sleep(.15)
            return result()
        c = MemoryController(runner=run, sample_provider=lambda: SimpleNamespace(total=1000, available=600), refresh_ms=20, hold_ms=120)
        try:
            c.startOptimization()
            c.startOptimization()
            c.setMode("Standard")
            self.assertEqual(c.selectedMode, "Maximum")
            pump_until(lambda: c.progress == "Real queued progress")
            pump_until(lambda: not c.running)
            self.assertTrue(c.busy)
            self.assertGreater(len(c.history), 2)
            c.startOptimization()
            self.assertEqual(len(calls), 1)
            self.assertNotEqual(calls[0][1], gui_thread)
            pump_until(lambda: not c.busy and c._thread is None)
            self.assertTrue(c.lastResult)
            c.setMode("Standard")
            self.assertEqual(c.selectedMode, "Standard")
        finally: c.shutdown()

    def test_worker_exception_releases_action(self):
        def fail(mode, progress): raise RuntimeError("Failure")
        c = MemoryController(runner=fail, hold_ms=10)
        try:
            c.startOptimization()
            pump_until(lambda: not c.busy and c._thread is None)
            self.assertEqual(c.lastResult["title"], "Optimization failed")
        finally: c.shutdown()

    def test_close_waits_for_worker_and_stops_sampling(self):
        finished = threading.Event()
        def run(mode, progress):
            time.sleep(.15)
            finished.set()
            return result()
        c = MemoryController(runner=run, refresh_ms=20)
        closed = []
        c.closeReady.connect(lambda: closed.append(finished.is_set()))
        try:
            c.startOptimization()
            c.requestClose()
            self.assertFalse(closed)
            length = len(c.history)
            c.startOptimization()
            pump_until(lambda: bool(closed))
            self.assertEqual(closed, [True])
            self.assertEqual(len(c.history), length)
            self.assertIsNone(c._thread)
        finally: c.shutdown()

class IsolationTests(unittest.TestCase):
    def test_preferences_persist_and_launcher_forces_theme(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "settings.json"
            s = SettingsController("light", path)
            s.setTheme("dark")
            s.setAnimations(False)
            remembered = SettingsController(path=path)
            self.assertEqual(remembered.theme, "dark")
            self.assertFalse(remembered.animations)
            self.assertEqual(SettingsController("light", path).theme, "light")

    def test_invalid_preferences_fall_back(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "settings.json"
            path.write_text("broken")
            self.assertEqual(SettingsController(path=path).theme, "light")
            path.write_text("[]")
            self.assertEqual(SettingsController(path=path).theme, "light")

    def test_maximum_dispatch_keeps_runner_results_and_progress_callback(self):
        from backend import maximum, optimizer_v2, deep
        expected = result(engine="maximum", available_settled_delta_mb=-15)
        messages = []
        progress = messages.append
        def run(*, on_step):
            on_step("settling")
            return expected
        with patch.object(maximum, "maximum_optimize", side_effect=run) as maximum_run, \
                patch.object(optimizer_v2, "optimize_detailed") as standard_run, \
                patch.object(deep, "deep_optimize") as deep_run:
            self.assertIs(run_optimization("Maximum", progress), expected)
            maximum_run.assert_called_once_with(on_step=progress)
            standard_run.assert_not_called()
            deep_run.assert_not_called()
        self.assertEqual(messages, ["settling"])

    def test_current_runtime_has_no_dependencies_on_removed_legacy_packages(self):
        for path in [ROOT / "main.py", *(ROOT / "backend").rglob("*.py")]:
            with self.subTest(source=str(path.relative_to(ROOT))):
                tree = ast.parse(path.read_text(encoding="utf-8"))
                imported = set()
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        imported.update(alias.name.split(".")[0] for alias in node.names)
                    elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
                        imported.add(node.module.split(".")[0])
                self.assertFalse(imported.intersection({"core", "ui"}), imported)

    def test_standard_and_deep_mode_dispatch(self):
        from backend import optimizer_v2, deep
        with patch.object(optimizer_v2, "optimize_detailed", return_value=result()) as standard:
            self.assertEqual(run_optimization("Standard", lambda _: None)["available_delta_mb"], 120)
            standard.assert_called_once_with("free")
        with patch.object(optimizer_v2, "optimize_detailed", return_value=result()), patch.object(deep, "deep_optimize", return_value={"available_after_mb": 1300, "free_delta_mb": 400, "duration_s": 1.5, "elevated": True, "steps": []}):
            r = run_optimization("Deep", lambda _: None)
            self.assertEqual(r["available_delta_mb"], 300)
            self.assertEqual(r["duration_s"], 4.0)
            self.assertEqual(r["free_delta_mb"], 400)

class ContrastTests(unittest.TestCase):
    def test_text_and_semantic_states_in_both_themes(self):
        source = (ROOT / "qml" / "Theme.qml").read_text()
        colors = dict((name, (dark, light)) for name, dark, light in re.findall(r'property color (\w+): dark \? "(#[0-9A-Fa-f]+)" : "(#[0-9A-Fa-f]+)"', source))
        def luminance(hex_color):
            channels = [int(hex_color[i:i+2], 16) / 255 for i in (1, 3, 5)]
            linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in channels]
            return sum(c * weight for c, weight in zip(linear, (.2126, .7152, .0722)))
        for mode in (0, 1):
            pairs = [(fg, bg) for fg in ("text", "muted") for bg in ("background", "surface", "inset")]
            pairs += [("accentText", "accent"), ("success", "successSoft"), ("warning", "warningSoft"), ("error", "errorSoft")]
            pairs += [("accent", "surface"), ("accent", "background")]
            for foreground, background in pairs:
                light, dark = sorted((luminance(colors[foreground][mode]), luminance(colors[background][mode])), reverse=True)
                self.assertGreaterEqual((light + .05) / (dark + .05), 4.5, (mode, foreground, background))

if __name__ == "__main__": unittest.main(verbosity=2)
