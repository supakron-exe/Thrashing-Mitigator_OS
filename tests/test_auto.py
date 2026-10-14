import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from qa_support import QA_ROOT, qa_path
from PySide6.QtCore import QCoreApplication, QObject, Signal
from backend.settings import SettingsController, AUTO_DEFAULTS, validate_auto
from backend.auto_optimize import AutoOptimizeController
from backend.controller import MemoryController
from backend.presentation import present_result

APP = QCoreApplication.instance() or QCoreApplication([])


class Clock:
    def __init__(self): self.now = 0.
    def __call__(self): return self.now


class FakeMemory(QObject):
    sampleChanged = Signal()
    operationChanged = Signal()
    optimizationCompleted = Signal(object)
    def __init__(self):
        super().__init__()
        self.snapshot = dict(total=1000, percent=80)
        self.live, self.busy, self.safeToClose, self.closing = True, False, True, False
        self.calls = []
    def startAutomaticOptimization(self, mode, reason):
        if self.busy or self.closing or not self.safeToClose: return False
        self.busy = True
        self.calls.append((mode, reason))
        self.operationChanged.emit()
        return True
    def finish(self, source="auto", error=False, gain="+0.0 MB"):
        self.optimizationCompleted.emit(dict(source=source, mode="Maximum", reason=self.calls[-1][1] if self.calls else "",
            title="Failed" if error else "Complete", message="QA error" if error else "", gain=gain, tone="error" if error else "warning", duration="1 s", hasMeasurements=not error, raw={"error": "QA"} if error else {}))
        self.busy = False
        self.operationChanged.emit()


class FakeStartup:
    def __init__(self): self.state, self.calls = False, []
    def capture(self): return self.state
    def restore(self, state): self.state = state; self.calls.append(state)
    def is_enabled(self): return self.state
    def set_enabled(self, value): self.state = value; self.calls.append(value)


class AutoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.settings = SettingsController(path=Path(self.temp.name) / "settings.json")
        self.memory, self.clock, self.startup = FakeMemory(), Clock(), FakeStartup()
        self.auto = AutoOptimizeController(self.memory, self.settings, self.startup, self.clock)
        self.auto._timer.stop()
    def tearDown(self): self.auto.shutdown(); self.temp.cleanup()
    def configure(self, **kwargs):
        self.assertTrue(self.auto.applyConfiguration(dict(AUTO_DEFAULTS, **kwargs)), self.auto.error)
        self.assertTrue(self.auto.setEnabled(True))
    def tick(self, seconds=1, fresh=True):
        for _ in range(seconds):
            self.clock.now += 1
            if fresh: self.memory.sampleChanged.emit()
            self.auto.evaluate()

    def test_defaults_disabled_and_maximum(self):
        self.tick(200)
        self.assertFalse(self.auto.enabled)
        self.assertFalse(self.startup.state)
        self.assertEqual(self.auto.configuration["mode"], "Maximum")
        self.assertFalse(self.memory.calls)

    def test_ram_requires_sustained_samples_and_resets_on_dip(self):
        self.configure(intervalEnabled=False)
        self.tick(6)
        self.memory.snapshot["percent"] = 74
        self.tick()
        self.memory.snapshot["percent"] = 80
        self.tick(10)
        self.assertFalse(self.memory.calls)
        self.tick()
        self.assertEqual(self.memory.calls, [("Maximum", "High RAM usage")])

    def test_interval_runs_without_ram_and_no_overlap(self):
        self.configure(intervalMinutes=1, cooldownMinutes=1, ramEnabled=False)
        self.tick(59); self.assertFalse(self.memory.calls)
        self.tick(); self.assertEqual(len(self.memory.calls), 1)
        self.tick(90); self.assertEqual(len(self.memory.calls), 1)

    def test_simultaneous_triggers_coalesce(self):
        self.configure(intervalMinutes=1, cooldownMinutes=1, sustainSeconds=59)
        self.tick(60)
        self.assertEqual(self.memory.calls, [("Maximum", "Time + RAM")])

    def test_repeat_waits_cooldown_then_sustained_ram_again(self):
        self.configure(intervalEnabled=False, cooldownMinutes=1, sustainSeconds=2)
        self.tick(3); self.memory.finish()
        self.tick(60); self.assertEqual(len(self.memory.calls), 1)
        self.tick(2); self.assertEqual(len(self.memory.calls), 2)

    def test_manual_completion_resets_schedule_and_cooldown(self):
        self.configure(intervalMinutes=1, cooldownMinutes=1, ramEnabled=False)
        self.tick(50); self.memory.finish(source="manual")
        self.tick(59); self.assertFalse(self.memory.calls)
        self.tick(); self.assertEqual(len(self.memory.calls), 1)
        self.assertEqual(len(self.auto.recentActivity), 0)

    def test_pause_does_not_cancel_current_work(self):
        self.configure(sustainSeconds=2)
        self.tick(3)
        self.auto.setEnabled(False)
        self.assertTrue(self.memory.busy)
        self.memory.finish(); self.tick(200)
        self.assertEqual(len(self.memory.calls), 1)

    def test_exception_pauses_persistently_but_no_gain_does_not(self):
        self.configure(sustainSeconds=2)
        self.tick(3); self.memory.finish(error=True)
        self.assertFalse(self.auto.enabled)
        self.assertEqual(self.auto.status, "Paused")
        self.assertEqual(self.auto.recentActivity[0]["gain"], "—")
        self.assertFalse(SettingsController(path=self.settings.path).autoEnabled)
        self.auto.resume(); self.tick(182)
        self.memory.finish(gain="+0.0 MB")
        self.assertTrue(self.auto.enabled)

    def test_stale_failed_zero_readings_and_sleep_do_not_replay(self):
        self.configure(intervalMinutes=1, cooldownMinutes=1, ramEnabled=False)
        self.tick(59)
        self.memory.live = False; self.tick(10)
        self.assertFalse(self.memory.calls)
        self.memory.live = True; self.tick()
        self.assertGreater(self.auto.nextRunSeconds, 50)
        self.memory.snapshot["total"] = 0; self.tick(70)
        self.assertFalse(self.memory.calls)
        self.memory.snapshot["total"] = 1000; self.tick()
        self.clock.now += 600
        self.memory.sampleChanged.emit(); self.auto.evaluate()
        self.assertFalse(self.memory.calls)
        self.assertEqual(self.auto.nextRunSeconds, 60)
        self.tick(10, fresh=False)
        self.assertIn("fresh", self.auto.detail)

    def test_theme_animation_changes_preserve_deadline_and_config(self):
        self.configure(intervalMinutes=10)
        self.tick(5)
        deadline = self.auto._next
        self.settings.setTheme("dark"); self.settings.setAnimations(False)
        self.assertEqual(self.auto._next, deadline)
        restored = SettingsController(path=self.settings.path)
        self.assertTrue(restored.autoEnabled)
        self.assertEqual(restored.autoConfig["intervalMinutes"], 10)

    def test_invalid_apply_retains_active_config_and_startup(self):
        original = self.auto.configuration
        self.assertFalse(self.auto.applyConfiguration(dict(original, intervalMinutes=1)))
        self.assertEqual(self.auto.configuration, original)
        self.assertFalse(self.startup.calls)
        self.assertFalse(self.auto.applyConfiguration(dict(original, intervalEnabled=False, ramEnabled=False)))

    def test_atomic_save_failure_rolls_back_startup(self):
        with patch.object(self.settings, "_write", side_effect=OSError("Disk full")):
            self.assertFalse(self.auto.applyConfiguration(dict(AUTO_DEFAULTS, startWithWindows=True)))
        self.assertFalse(self.startup.state)
        self.assertEqual(self.startup.calls, [True, False])
        self.assertFalse(self.auto.configuration["startWithWindows"])

    def test_startup_permission_failure(self):
        with patch.object(self.startup, "set_enabled", side_effect=PermissionError("Denied")):
            self.assertFalse(self.auto.applyConfiguration(dict(AUTO_DEFAULTS, startWithWindows=True)))
        self.assertIn("Denied", self.auto.error)

    def test_pause_still_stops_when_settings_cannot_be_saved(self):
        self.configure(intervalMinutes=1, cooldownMinutes=1, ramEnabled=False)
        with patch.object(self.settings, "_write", side_effect=OSError("Read-only")):
            self.assertFalse(self.auto.setEnabled(False))
        self.assertFalse(self.auto.enabled)
        self.assertEqual(self.auto.status, "Paused")
        self.tick(200)
        self.assertFalse(self.memory.calls)

    def test_countdown_does_not_rebuild_activity_or_configuration(self):
        activity, configuration = [], []
        self.auto.activityChanged.connect(lambda: activity.append(True))
        self.auto.configurationChanged.connect(lambda: configuration.append(True))
        self.configure(intervalMinutes=10, ramEnabled=False)
        self.tick(10)
        self.assertEqual(len(configuration), 1)
        self.assertFalse(activity)

    def test_finished_worker_hold_is_cooldown_not_running(self):
        self.configure(sustainSeconds=2)
        self.tick(3)
        self.memory.running = False
        self.memory.operationChanged.emit()
        self.assertEqual(self.auto.status, "Cooldown")
        self.assertTrue(self.memory.busy)

    def test_history_bounded_and_restore_starts_fresh(self):
        self.configure(intervalEnabled=False, sustainSeconds=2, cooldownMinutes=1)
        for _ in range(23):
            self.tick(63); self.memory.finish()
        self.assertEqual(len(self.auto.recentActivity), 20)
        self.auto.shutdown()
        restored = AutoOptimizeController(self.memory, SettingsController(path=self.settings.path), clock=self.clock)
        try:
            self.assertEqual(restored.nextRunSeconds, 180)
            self.assertIsNone(restored._high_since)
        finally: restored.shutdown()

    def test_settings_validation_and_integer_qml_values(self):
        self.assertEqual(validate_auto(dict(AUTO_DEFAULTS, intervalMinutes=3.0))["intervalMinutes"], 3)
        for value in (True, "3", -1, float("nan"), 2.5):
            with self.assertRaises(ValueError): validate_auto(dict(AUTO_DEFAULTS, intervalMinutes=value))
        self.settings.path.write_text(json.dumps(dict(autoEnabled=True, autoConfig=dict(AUTO_DEFAULTS, ramPercent=999, mode="Bad"))))
        restored = SettingsController(path=self.settings.path)
        self.assertEqual(restored.autoConfig["ramPercent"], 75)
        self.assertEqual(restored.autoConfig["mode"], "Maximum")
        self.assertFalse(restored.autoEnabled)


class AutoWorkerTests(unittest.TestCase):
    def test_unavailable_free_and_settled_measurements_are_not_shown(self):
        failed = present_result({"error": "Failure"}, "Maximum")
        self.assertFalse(failed["hasFree"])
        self.assertFalse(failed["hasSettled"])
        measured = present_result(dict(supported=True, elevated=True, trimmed=1, available_delta_mb=10), "Maximum")
        self.assertTrue(measured["hasMeasurements"])
        self.assertFalse(measured["hasFree"])
        self.assertFalse(measured["hasSettled"])

    def test_auto_mode_and_metadata_do_not_mutate_manual_mode(self):
        seen = []
        def run(mode, progress):
            seen.append(mode); progress("combining identical pages")
            return dict(supported=True, elevated=True, trimmed=1, available_delta_mb=10)
        memory = MemoryController(runner=run, hold_ms=10, sample_provider=lambda: SimpleNamespace(total=1000, available=400))
        try:
            memory.setMode("Standard")
            self.assertTrue(memory.startAutomaticOptimization("Maximum", "High RAM usage"))
            self.assertFalse(memory.startAutomaticOptimization("Deep", "Time interval"))
            end = time.monotonic() + 3
            while memory.busy or not memory.safeToClose:
                APP.processEvents(); time.sleep(.005)
                self.assertLess(time.monotonic(), end)
            self.assertEqual(seen, ["Maximum"])
            self.assertEqual(memory.selectedMode, "Standard")
            self.assertEqual(memory.lastResult["mode"], "Maximum")
            self.assertEqual(memory.lastResult["source"], "auto")
            self.assertEqual(memory.optimizationEvents[-1]["reason"], "High RAM usage")
            self.assertEqual(len(memory.operation["stages"]), 8)
        finally: memory.shutdown()


if __name__ == "__main__": unittest.main()
