"""Present measured outcomes without conflating working sets, Free and Available."""
import math

def number(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else 0.0
    except (ValueError, TypeError):
        return 0.0

def memory_label(mb, signed=False):
    mb = number(mb)
    suffix, value = ("GB", mb / 1024) if abs(mb) >= 1024 else ("MB", mb)
    spec = "+.1f" if signed else ".1f"
    return f"{value:{spec}} {suffix}"

def present_result(raw, mode):
    raw = dict(raw)
    delta = number(raw.get("available_delta_mb"))
    maximum = raw.get("engine") == "maximum" or mode == "Maximum"
    settled = number(raw.get("available_settled_delta_mb", delta))
    use_settled = maximum and settled > 0 and "available_settled_mb" in raw and "available_settled_delta_mb" in raw
    gain = settled if use_settled else delta
    steps = raw.get("steps", []) if maximum else raw.get("deep_steps", [])
    steps = [s for s in steps if isinstance(s, dict)]
    completed = sum(bool(s.get("ok")) for s in steps)
    trimmed, failed = int(raw.get("trimmed", 0)), int(raw.get("failed", 0))
    tone = "success" if gain > 0 else "warning"
    title = "Optimization complete" if gain > 0 else "No RAM gain measured"
    message = "Available memory increased. Applications may reclaim memory as you use them." if gain > 0 else "The operation finished, but Available memory did not increase."
    if raw.get("error"):
        title, message, tone = "Optimization failed", str(raw["error"]), "error"
    elif not raw.get("supported", False):
        title, message, tone = "Readings only", "Memory optimization is supported on Windows.", "warning"
    elif mode in ("Deep", "Maximum") and trimmed == 0 and completed == 0 and not raw.get("elevated"):
        title, message, tone = "Administrator access needed", "Run this version as Administrator to enable system-memory steps.", "warning"
    elif mode == "Standard" and trimmed == 0:
        title, message, tone = "No eligible idle apps", "There were no eligible idle background apps to trim this time.", "warning"
    elif failed or (steps and completed < len(steps)):
        message = "Some apps or system steps were skipped. Expand the details to see their outcomes."
    targets = []
    for t in raw.get("targets", []):
        if not isinstance(t, dict):
            continue
        targets.append({"name": str(t.get("name", "Unknown app")), "ok": bool(t.get("ok")),
                        "detail": str(t.get("reason", memory_label(t.get("freed_mb", 0)) + " working set trimmed"))})
    before = number(raw.get("available_before_mb"))
    after = number(raw.get("available_settled_mb")) if use_settled else number(raw.get("available_after_mb"))
    has_measurements = bool(raw.get("supported")) and not bool(raw.get("error"))
    return {"title": title, "message": message, "tone": tone, "mode": mode,
            "gain": memory_label(gain, True), "gainMb": gain, "before": memory_label(before),
            "after": memory_label(after), "beforeMb": before, "afterMb": after,
            "duration": f"{number(raw.get('duration_s')):.1f} s",
            "trimmed": trimmed, "failed": failed, "stepSummary": f"{completed} / {len(steps)}",
            "freeChange": memory_label(raw.get("free_delta_mb"), True),
            "completionChange": memory_label(delta, True), "settledChange": memory_label(settled, True),
            "maximum": maximum, "hasFree": has_measurements and mode in ("Deep", "Maximum") and "free_delta_mb" in raw,
            "hasSettled": has_measurements and "available_settled_mb" in raw and "available_settled_delta_mb" in raw,
            "hasMeasurements": has_measurements,
            "measurementLabel": "After settling" if use_settled else "At completion",
            "steps": [{"name": str(s.get("name", "System step")), "ok": bool(s.get("ok")), "detail": str(s.get("detail", ""))} for s in steps],
            "targets": targets, "raw": raw}
