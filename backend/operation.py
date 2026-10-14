"""Presentation-only stages. Callbacks indicate activity, not successful work."""
STAGES = {
    "Standard": [("prepare", "Prepare"), ("trim", "Inspect and trim idle apps"), ("result", "Result")],
    "Deep": [("prepare", "Prepare"), ("trim", "Inspect and trim idle apps"), ("system", "System memory"), ("result", "Result")],
    "Maximum": [("prepare", "Prepare"), ("combine", "Combine identical pages"), ("trim", "Trim apps"),
                ("cache", "File cache"), ("modified", "Modified pages"), ("standby", "Standby memory"),
                ("settle", "Settle readings"), ("result", "Result")],
}


def stage_for_message(mode, message):
    text = message.lower()
    if text.startswith(("trimming", "scanning idle")):
        return "trim"
    if mode == "Deep" and text.startswith("cleaning system"):
        return "system"
    if mode == "Maximum":
        for prefix, stage in (("combining identical", "combine"), ("flushing file cache", "cache"),
                              ("writing dirty", "modified"), ("purging standby", "standby"), ("settling", "settle")):
            if text.startswith(prefix):
                return stage
    return None


def outcome_states(raw, mode):
    if raw.get("error"):
        return {"result": "failed"}  # No evidence that preceding stages succeeded.
    if not raw.get("supported"):
        return {stage: "skipped" for stage, _ in STAGES[mode]}
    states = {"prepare": "success", "result": "finished"}
    trimmed, failed = raw.get("trimmed", 0), raw.get("failed", 0)
    states["trim"] = "partial" if trimmed and failed else "success" if trimmed else "failed" if failed else "skipped"
    steps = raw.get("steps", []) if mode == "Maximum" else raw.get("deep_steps", [])
    steps = [s for s in steps if isinstance(s, dict)]
    if mode == "Deep":
        count = sum(bool(s.get("ok")) for s in steps)
        states["system"] = "success" if steps and count == len(steps) else "partial" if count else "skipped"
    elif mode == "Maximum":
        for index, stage in enumerate(("combine", "cache", "modified", "standby")):
            if index < len(steps):
                states[stage] = "success" if steps[index].get("ok") else "skipped"
        if "available_settled_mb" in raw:
            states["settle"] = "finished"  # Measurement finished; gain is reported separately.
    return states
