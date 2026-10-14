from collections import deque
from datetime import datetime
import time

import psutil
from PySide6.QtCore import QObject, Property, QThread, QTimer, Signal, Slot
from backend.presentation import present_result
from backend.service import run_optimization
from backend.operation import STAGES, stage_for_message, outcome_states


class OptimizationWorker(QObject):
    progress = Signal(str)
    completed = Signal(object)

    def __init__(self, mode, runner):
        super().__init__()
        self.mode, self.runner = mode, runner

    @Slot()
    def run(self):
        try:
            result = self.runner(self.mode, self.progress.emit)
        except Exception as exc:
            result = {"error": str(exc)}
        self.completed.emit(result)


class MemoryController(QObject):
    sampleChanged = Signal()
    modeChanged = Signal()
    operationChanged = Signal()
    resultChanged = Signal()
    eventsChanged = Signal()
    closingChanged = Signal()
    closeReady = Signal()
    optimizationCompleted = Signal(object)

    def __init__(self, parent=None, sample_provider=None, runner=None, refresh_ms=2000, hold_ms=3000):
        super().__init__(parent)
        self._provider = sample_provider or psutil.virtual_memory
        self._runner = runner or run_optimization
        self._sample = {"total": 0, "used": 0, "available": 0, "percent": 0, "time": "Waiting for readings", "pressure": "Normal"}
        self._history = deque(maxlen=60)
        self._mode, self._busy, self._running = "Maximum", False, False
        self._live, self._monitor_error, self._closing = False, "", False
        self._progress, self._result = "", {}
        self._operation, self._events = {}, []
        self._run_id, self._started_clock = 0, 0.0
        self._thread, self._worker = None, None
        self._hold_ms = hold_ms
        self._timer = QTimer(self)
        self._timer.setInterval(refresh_ms)
        self._timer.timeout.connect(self.refresh)
        self._hold = QTimer(self)
        self._hold.setSingleShot(True)
        self._hold.timeout.connect(self._release)
        self._elapsed = QTimer(self)
        self._elapsed.setInterval(1000)
        self._elapsed.timeout.connect(self._tick_elapsed)
        self.refresh()
        self._timer.start()

    @Property('QVariantMap', notify=sampleChanged)
    def snapshot(self):
        return self._sample

    @Property('QVariantList', notify=sampleChanged)
    def history(self):
        return list(self._history)

    @Property(bool, notify=sampleChanged)
    def live(self):
        return self._live

    @Property(str, notify=sampleChanged)
    def monitorError(self):
        return self._monitor_error

    @Property(str, notify=modeChanged)
    def selectedMode(self):
        return self._mode

    @Slot(str)
    def setMode(self, mode):
        if not self._busy and mode in ("Standard", "Deep", "Maximum") and mode != self._mode:
            self._mode = mode
            self.modeChanged.emit()

    @Property(bool, notify=operationChanged)
    def busy(self):
        return self._busy

    @Property(bool, notify=operationChanged)
    def running(self):
        return self._running

    @Property(str, notify=operationChanged)
    def progress(self):
        return self._progress

    @Property('QVariantMap', notify=resultChanged)
    def lastResult(self):
        return self._result

    @Property('QVariantMap', notify=operationChanged)
    def operation(self):
        return self._operation

    @Property('QVariantList', notify=eventsChanged)
    def optimizationEvents(self):
        return [dict(event) for event in self._events]

    @Slot()
    def _tick_elapsed(self):
        if self._running:
            self._operation = dict(self._operation, elapsedSeconds=int(time.monotonic() - self._started_clock))
            self.operationChanged.emit()

    @Property(bool, notify=closingChanged)
    def closing(self):
        return self._closing

    @Property(bool, notify=closingChanged)
    def safeToClose(self):
        return self._thread is None

    @Slot()
    def refresh(self):
        if self._closing:
            return
        try:
            memory = self._provider()
            total = max(int(memory.total), 0)
            available = min(max(int(memory.available), 0), total)
            used = total - available
            percent = used / total * 100 if total else 0.0
            pressure = "High RAM usage" if percent >= 85 else "Warning" if percent >= 75 else "Normal"
            now = time.time()
            self._sample = {"total": total, "used": used, "available": available, "percent": percent,
                            "pressure": pressure, "time": datetime.fromtimestamp(now).strftime("%H:%M:%S"), "timestamp": now}
            self._history.append({"percent": percent, "timestamp": now})
            recent = [event for event in self._events if event.get("finishedAt", now) >= now - 120]
            if len(recent) != len(self._events):
                self._events = recent
                self.eventsChanged.emit()
            self._live, self._monitor_error = True, ""
        except Exception as exc:
            self._live, self._monitor_error = False, str(exc)
        self.sampleChanged.emit()

    @Slot()
    def startOptimization(self):
        self._startOptimization(self._mode, "manual", "")

    @Slot(str, str, result=bool)
    def startAutomaticOptimization(self, mode, reason):
        return self._startOptimization(mode, "auto", reason)

    def _startOptimization(self, mode, source, reason):
        if self._busy or self._closing or self._thread is not None:
            return False
        if mode not in STAGES:
            return False
        self._busy = self._running = True
        self._run_id += 1
        self._started_clock = time.monotonic()
        started = time.time()
        self._operation = {"id": self._run_id, "mode": mode, "source": source, "reason": reason, "stageId": "prepare",
                           "startedAt": started, "finishedAt": 0.0, "elapsedSeconds": 0,
                           "totalMb": self._sample["total"] / 1024**2,
                           "stages": [{"id": key, "label": label, "state": "active" if key == "prepare" else "pending"}
                                      for key, label in STAGES[mode]]}
        self._events.append({"id": self._run_id, "mode": mode, "source": source, "reason": reason, "startedAt": started,
                             "tone": "neutral", "title": "Optimizing"})
        self._events = self._events[-60:]
        self.eventsChanged.emit()
        self._elapsed.start()
        self._progress, self._result = "Preparing memory optimization…", {}
        self.resultChanged.emit()
        self.operationChanged.emit()
        thread = QThread(self)
        worker = OptimizationWorker(mode, self._runner)
        self._thread, self._worker = thread, worker
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progress.connect(self._on_progress)
        worker.completed.connect(self._on_result)
        worker.completed.connect(thread.quit)
        worker.completed.connect(worker.deleteLater)
        thread.finished.connect(self._thread_finished)
        thread.finished.connect(thread.deleteLater)
        thread.start()
        return True

    @Slot(str)
    def _on_progress(self, text):
        self._progress = text
        stage = stage_for_message(self._operation["mode"], text)
        if stage and stage != self._operation.get("stageId"):
            stages = [dict(item) for item in self._operation["stages"]]
            for item in stages:
                if item["state"] == "active":
                    item["state"] = "finished"
                if item["id"] == stage:
                    item["state"] = "active"
            self._operation = dict(self._operation, stageId=stage, stages=stages)
        self.operationChanged.emit()

    @Slot(object)
    def _on_result(self, raw):
        self._running = False
        self._elapsed.stop()
        self._result = present_result(raw, self._operation["mode"])
        finished = time.time()
        states = outcome_states(raw, self._operation["mode"])
        stages = [dict(item) for item in self._operation["stages"]]
        for item in stages:
            if item["id"] in states:
                item["state"] = states[item["id"]]
            elif item["state"] == "active":
                item["state"] = "failed" if raw.get("error") else "finished"
        self._operation = dict(self._operation, stageId="result", stages=stages, finishedAt=finished,
                               elapsedSeconds=int(time.monotonic() - self._started_clock))
        self._result.update(totalMb=self._operation["totalMb"], operationId=self._run_id,
                            source=self._operation["source"], reason=self._operation["reason"])
        self._events[-1] = dict(self._events[-1], finishedAt=finished, title=self._result["title"],
                                tone=self._result["tone"], gain=self._result["gain"],
                                hasMeasurements=self._result["hasMeasurements"])
        self.eventsChanged.emit()
        self._progress = "Ready for another run in 3 seconds."
        self.resultChanged.emit()
        self.operationChanged.emit()
        self.refresh()
        if not self._closing:
            self._hold.start(self._hold_ms)
        self.optimizationCompleted.emit(dict(self._result))

    @Slot()
    def _thread_finished(self):
        self._thread, self._worker = None, None
        self.closingChanged.emit()
        if self._closing:
            self.closeReady.emit()

    @Slot()
    def _release(self):
        self._busy, self._progress = False, ""
        self.operationChanged.emit()

    @Slot()
    def requestClose(self):
        if self._closing:
            return
        self._closing = True
        self._timer.stop()
        self._hold.stop()
        self.closingChanged.emit()
        if self._thread is None:
            self.closeReady.emit()

    def shutdown(self):
        self._timer.stop()
        self._hold.stop()
        self._elapsed.stop()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
