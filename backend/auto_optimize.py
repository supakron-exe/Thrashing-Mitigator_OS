"""One scheduler using the existing RAM snapshot and guarded worker."""
from datetime import datetime
import math
import time
from PySide6.QtCore import QObject, Property, Signal, Slot, QTimer
from backend.settings import validate_auto


class AutoOptimizeController(QObject):
    changed = Signal()
    configurationChanged = Signal()
    activityChanged = Signal()
    attention = Signal(str)

    def __init__(self, memory, settings, startup=None, clock=time.monotonic, parent=None):
        super().__init__(parent)
        self.memory, self.settings, self.startup, self.clock = memory, settings, startup, clock
        now = clock()
        self._next = now + settings.autoConfig["intervalMinutes"] * 60
        self._sample_at = now if memory.live else None
        self._last_tick, self._high_since, self._finished = now, None, None
        self._status, self._detail, self._error = "Disabled", "Auto Optimize is off.", ""
        self._activity, self._last_result, self._stopped = [], {}, False
        self._blocked = False
        self._last_config = self.configuration
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self.evaluate)
        memory.sampleChanged.connect(self._sample)
        memory.operationChanged.connect(self.evaluate)
        memory.optimizationCompleted.connect(self._completed)
        settings.autoChanged.connect(self._configuration_changed)
        self._timer.start()
        self.evaluate()

    @Property('QVariantMap', notify=configurationChanged)
    def configuration(self): return self.settings.autoConfig

    @Property(bool, notify=changed)
    def enabled(self): return self.settings.autoEnabled and not self._blocked

    @Property(str, notify=changed)
    def status(self): return self._status

    @Property(str, notify=changed)
    def detail(self): return self._detail

    @Property(str, notify=changed)
    def error(self): return self._error

    @Property(int, notify=changed)
    def nextRunSeconds(self): return max(0, math.ceil(self._next - self.clock()))

    @Property(int, notify=changed)
    def cooldownSeconds(self): return max(0, math.ceil(self._cooldown_end() - self.clock()))

    @Property('QVariantList', notify=activityChanged)
    def recentActivity(self): return list(self._activity)

    @Property('QVariantMap', notify=activityChanged)
    def lastResult(self): return dict(self._last_result)

    @Property(bool, notify=changed)
    def startupAvailable(self): return self.startup is not None

    def _cooldown_end(self):
        return self._finished + self.configuration["cooldownMinutes"] * 60 if self._finished is not None else 0

    def _configuration_changed(self):
        if self.configuration != self._last_config:
            self._last_config = self.configuration
            self.configurationChanged.emit()
        self._next = self.clock() + self.configuration["intervalMinutes"] * 60
        self._high_since = None
        self.evaluate()

    @Slot('QVariantMap', result=bool)
    def applyConfiguration(self, config):
        old_startup, startup_changed = None, False
        try:
            candidate = validate_auto(dict(config))
            if self.startup:
                old_startup = self.startup.capture()
                if candidate["startWithWindows"] != self.startup.is_enabled():
                    startup_changed = True
                    self.startup.set_enabled(candidate["startWithWindows"])
            elif candidate["startWithWindows"]:
                raise ValueError("Start with Windows is unavailable in this session.")
            self.settings.save_auto(candidate)
            self._error = ""
            self.changed.emit()
            return True
        except (OSError, ValueError) as exc:
            if self.startup and startup_changed:
                try: self.startup.restore(old_startup)
                except OSError: pass
            self._error = str(exc)
            self.changed.emit()
            return False

    @Slot(bool, result=bool)
    def setEnabled(self, enabled):
        if not enabled:
            self._blocked = True  # Pause is effective even if the disk is read-only.
            self._high_since = None
        try:
            self.settings.save_auto(enabled=bool(enabled))
            self._blocked = False
            self._error = ""
            self.evaluate()
            return True
        except OSError as exc:
            self._error = ("Auto paused for this session. Settings could not be saved: " if not enabled else "Unable to enable Auto: ") + str(exc)
            self.evaluate()
            return False

    @Slot()
    def resume(self): self.setEnabled(True)

    def _sample(self):
        now = self.clock()
        if not self.memory.live or not self.memory.snapshot.get("total"):
            self._sample_at, self._high_since = None, None
        else:
            if self._sample_at is None or now - self._sample_at > 5:
                self._next = now + self.configuration["intervalMinutes"] * 60
                self._high_since = None
            self._sample_at = now
            if self.memory.snapshot["percent"] >= self.configuration["ramPercent"] and now >= self._cooldown_end() and not self.memory.busy:
                if self._high_since is None: self._high_since = now
            else: self._high_since = None
        self.evaluate()

    @Slot()
    def evaluate(self):
        now = self.clock()
        if now - self._last_tick > 5:
            self._next = now + self.configuration["intervalMinutes"] * 60
            self._high_since = None
        self._last_tick = now
        config = self.configuration
        if self._stopped or self.memory.closing:
            self._status, self._detail = "Disabled", "Shutting down."
        elif not self.enabled:
            self._status = "Paused" if self._error else "Disabled"
            self._detail = "Review the error below, then enable Auto to resume." if self._error else "Auto Optimize is off."
        elif self.memory.busy or not self.memory.safeToClose:
            if getattr(self.memory, "running", self.memory.busy):
                self._status, self._detail = "Running", "Waiting for the current optimization to finish."
            else:
                self._status, self._detail = "Cooldown", "Finishing this run and releasing its controls."
        elif self._sample_at is None or now - self._sample_at > 5 or not self.memory.live or not self.memory.snapshot.get("total"):
            self._high_since = None
            self._status, self._detail = "Waiting", "Waiting for fresh memory readings."
        elif now < self._cooldown_end():
            self._status, self._detail = "Cooldown", "Giving memory readings time to settle."
        else:
            timed = config["intervalEnabled"] and now >= self._next
            ram = config["ramEnabled"] and self._high_since is not None and now - self._high_since >= config["sustainSeconds"]
            self._status, self._detail = "Waiting", "Watching your enabled triggers."
            if timed or ram:
                reason = "Time + RAM" if timed and ram else "Time interval" if timed else "High RAM usage"
                if self.memory.startAutomaticOptimization(config["mode"], reason):
                    self._high_since = None
                    self._status, self._detail = "Running", reason + " triggered " + config["mode"] + "."
        self.changed.emit()

    def _completed(self, result):
        self._finished = self.clock()
        self._next = self._finished + self.configuration["intervalMinutes"] * 60
        self._high_since = None
        if result.get("source") == "auto":
            self._last_result = dict(result)
            self._activity.insert(0, dict(time=datetime.now().strftime("%H:%M:%S"), mode=result["mode"],
                                         reason=result["reason"], title=result["title"],
                                         gain=result["gain"] if result.get("hasMeasurements") else "—",
                                         tone=result["tone"], duration=result["duration"] if result.get("hasMeasurements") else "—",
                                         result=dict(result)))
            self._activity = self._activity[:20]
            self.activityChanged.emit()
            if result.get("raw", {}).get("error"):
                self._error = "Auto paused: " + result["message"]
                try: self.settings.save_auto(enabled=False)
                except OSError: self._blocked = True
                self.attention.emit(self._error)
        self.evaluate()

    def shutdown(self):
        self._stopped = True
        self._timer.stop()
