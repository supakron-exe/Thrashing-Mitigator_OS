"""UI-independent mode dispatch. Optimizer algorithms remain in the copied modules."""
def run_optimization(mode, progress):
    from backend import optimizer_v2
    if mode == "Maximum":
        from backend.maximum import maximum_optimize
        return maximum_optimize(on_step=progress)
    progress("Scanning idle background apps…")
    result = optimizer_v2.optimize_detailed("free")
    if mode == "Deep":
        from backend.deep import deep_optimize
        progress("Cleaning system memory…")
        deep = deep_optimize()
        result = dict(result)
        result.update(deep=True, deep_steps=deep.get("steps", []),
                      elevated=deep.get("elevated", False),
                      free_delta_mb=deep.get("free_delta_mb", 0.0))
        result["available_delta_mb"] = round(deep.get("available_after_mb", 0.0) - result.get("available_before_mb", 0.0), 1)
        result["available_after_mb"] = deep.get("available_after_mb", result.get("available_after_mb"))
        result["duration_s"] = round(result.get("duration_s", 0.0) + deep.get("duration_s", 0.0), 2)
    return result
