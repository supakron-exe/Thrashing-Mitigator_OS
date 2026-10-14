"""Contracts for real callback timing, outcome evidence and chart event lifetime."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qa_support import QA_ROOT, qa_path
from backend.controller import MemoryController
from backend.operation import stage_for_message, outcome_states
from test_contract import result, pump_until


class OperationTests(unittest.TestCase):
    def controller(self, runner):
        return MemoryController(runner=runner, sample_provider=lambda: SimpleNamespace(total=8192 * 1024**2, available=4096 * 1024**2), refresh_ms=25, hold_ms=10)

    def test_maximum_callback_order_and_unknown_message(self):
        labels = ["combining identical pages", "trimming apps", "trimming 4 apps", "flushing file cache", "writing dirty pages to disk", "purging standby", "settling"]
        self.assertEqual([stage_for_message("Maximum", label) for label in labels], ["combine", "trim", "trim", "cache", "modified", "standby", "settle"])
        self.assertIsNone(stage_for_message("Maximum", "An unfamiliar callback"))
        self.assertEqual(stage_for_message("Standard", "Scanning idle background apps…"), "trim")
        self.assertEqual(stage_for_message("Deep", "Cleaning system memory…"), "system")

    def test_stages_and_timestamps_do_not_claim_visited_steps_succeeded(self):
        def runner(mode, progress):
            progress("combining identical pages")
            time.sleep(.12)
            progress("An unfamiliar callback")
            time.sleep(.12)
            return result(engine="maximum", available_settled_mb=1100, available_settled_delta_mb=100,
                          steps=[{"ok": False}, {"ok": True}, {"ok": False}, {"ok": False}], failed=1)
        c = self.controller(runner)
        try:
            c.startOptimization()
            started = c.operation["startedAt"]
            pump_until(lambda: c.operation["stageId"] == "combine")
            c.startOptimization()
            self.assertEqual(len(c.optimizationEvents), 1)
            self.assertEqual(next(s["state"] for s in c.operation["stages"] if s["id"] == "prepare"), "finished")
            pump_until(lambda: c.progress == "An unfamiliar callback")
            self.assertEqual(c.operation["stageId"], "combine")
            pump_until(lambda: not c.busy and c._thread is None)
            states = {s["id"]: s["state"] for s in c.operation["stages"]}
            self.assertEqual(states["combine"], "skipped")
            self.assertEqual(states["cache"], "success")
            self.assertEqual(states["trim"], "partial")
            self.assertEqual(states["settle"], "finished")
            self.assertGreaterEqual(c.operation["finishedAt"], started)
            self.assertEqual(c.optimizationEvents[0]["finishedAt"], c.operation["finishedAt"])
            self.assertEqual(c.lastResult["totalMb"], 8192)
            self.assertEqual(c.lastResult["beforeMb"], 1000)
            self.assertEqual(c.lastResult["afterMb"], 1100)
            self.assertGreater(len(c.history), 2)
        finally:
            c.shutdown()

    def test_all_modes_and_event_expiry_keep_last_result(self):
        c = self.controller(lambda mode, progress: result())
        try:
            for mode, keys in (("Standard", ["prepare", "trim", "result"]), ("Deep", ["prepare", "trim", "system", "result"]), ("Maximum", ["prepare", "combine", "trim", "cache", "modified", "standby", "settle", "result"])):
                c.setMode(mode); c.startOptimization()
                self.assertEqual([s["id"] for s in c.operation["stages"]], keys)
                pump_until(lambda: not c.busy and c._thread is None)
            previous = c.lastResult.copy()
            with patch("backend.controller.time.time", return_value=c.operation["finishedAt"] + 121):
                c.refresh()
            self.assertEqual(c.optimizationEvents, [])
            self.assertEqual(c.lastResult, previous)
        finally:
            c.shutdown()

    def test_errors_keep_unreached_steps_and_stop_elapsed_timer(self):
        def fail(mode, progress):
            progress("trimming apps")
            raise PermissionError("Access denied")
        c = self.controller(fail)
        try:
            c.startOptimization()
            pump_until(lambda: not c.busy and c._thread is None)
            states = {s["id"]: s["state"] for s in c.operation["stages"]}
            self.assertEqual(states["trim"], "failed")
            self.assertEqual(states["standby"], "pending")
            self.assertEqual(states["result"], "failed")
            self.assertFalse(c._elapsed.isActive())
            self.assertFalse(c.optimizationEvents[0]["hasMeasurements"])
        finally:
            c.shutdown()

    def test_elapsed_uses_monotonic_and_no_gain_is_not_stage_failure(self):
        c = self.controller(lambda mode, progress: (time.sleep(.08), result(available_delta_mb=-10))[1])
        try:
            c.startOptimization()
            with patch("backend.controller.time.monotonic", return_value=c._started_clock + 7.9):
                c._tick_elapsed()
            self.assertEqual(c.operation["elapsedSeconds"], 7)
            pump_until(lambda: not c.busy and c._thread is None)
            self.assertEqual(c.lastResult["tone"], "warning")
            self.assertEqual(next(s["state"] for s in c.operation["stages"] if s["id"] == "trim"), "success")
        finally:
            c.shutdown()

    def test_partial_deep_and_unsupported_have_honest_outcomes(self):
        states = outcome_states(result(deep_steps=[{"ok": True}, {"ok": False}, {"ok": False}]), "Deep")
        self.assertEqual(states["system"], "partial")
        states = outcome_states(result(supported=False), "Maximum")
        self.assertEqual(set(states.values()), {"skipped"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
