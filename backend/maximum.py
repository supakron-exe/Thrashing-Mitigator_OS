"""Maximum mode: free the most RAM technically possible in one click.

Unlike Standard (idle background groups only), Maximum trims every
accessible user process — including the foreground app — then runs the
full system sequence. Pages an app touches again fault straight back from
standby, so this buys the biggest immediate number, not the longest-lived
one. The UI must show both the instant gain and the settled gain.

Order matters, so the sequence is fixed:

    privileges -> combine (while data is still resident) -> trim all apps
    -> file cache -> flush modified (dirty pages must be written before
    their RAM is reusable) -> purge standby -> settle -> measure

Needs Administrator for the system steps; the app-trim phase still helps
without it.
"""

from __future__ import annotations

import os
import time

from backend.deep import (
    _available_mb,
    combine_pages,
    flush_file_cache,
    flush_modified,
    free_physical_mb,
    is_admin,
    purge_standby,
    standby_mb,
)
from backend.optimizer import (
    _BY_MB,
    _ERROR_ACCESS_DENIED,
    _PSEUDO_PIDS,
    _apis,
    _is_alive,
    _known_exclusions,
    empty_working_set,
)
from backend.optimizer_v2 import _snapshot

MIN_WS_MB = 8.0
# Stop starting new trim passes after this long; system steps still run.
TRIM_BUDGET_S = 12.0
# Settle: stop early when Available moves less than this across 3 samples.
SETTLE_TOL_MB = 25.0
SETTLE_MAX_S = 12.0


def _candidates(skip_pids=frozenset(), own_family_ok=False):
    """Every accessible user process worth trimming, heaviest first.

    No idle/cooldown/foreground filters by design: Maximum trades
    endurance for the biggest immediate number. Self, launcher, system
    processes and nameless ghosts stay excluded. `own_family_ok` is the
    same benchmark-only escape hatch as in v2 (benchmark fixture lives
    below the benchmark's own PID).
    """
    import psutil

    apis = _apis()
    excluded = _known_exclusions()
    my_pid = os.getpid()
    my_ancestry = {my_pid}
    try:
        my_ancestry.add(psutil.Process(my_pid).ppid())
    except Exception:
        pass

    found = []
    for pid, (proc, info) in _snapshot().items():
        try:
            if pid in _PSEUDO_PIDS or pid in skip_pids:
                continue
            if pid in my_ancestry:
                continue
            if not own_family_ok and _below_ancestry(pid, my_ancestry):
                continue
            name = (info.get("name") or "").lower()
            if not name or name in excluded:
                continue
            try:
                ws_mb = proc.memory_info().rss / _BY_MB
            except Exception:
                continue
            if ws_mb < MIN_WS_MB:
                continue
            found.append({
                "pid": pid,
                "name": info.get("name"),
                "working_set_mb": round(ws_mb, 1),
                "api": "EmptyWorkingSet" if apis else None,
            })
        except Exception:
            continue
    found.sort(key=lambda c: c["working_set_mb"], reverse=True)
    return found


def _below_ancestry(pid, my_ancestry):
    """True when `pid` descends from my own process tree."""
    import psutil

    seen = set()
    node = pid
    while node not in seen:
        seen.add(node)
        try:
            parent = psutil.Process(node).ppid()
        except Exception:
            return False
        if parent in my_ancestry:
            return True
        if parent in (0, 4) or parent == node:
            return False
        node = parent
    return False


def _trim_all(dead_pids, result, on_step=None, deadline=None,
              own_family_ok=False):
    """Trim every candidate, then sweep once more for stragglers.

    Active apps fault their pages straight back, so re-trimming them in a
    tight loop is pure overhead (and a page-fault storm): two passes is the
    cap, and `deadline` bounds the whole phase regardless.
    """
    import psutil

    for sweep in (1, 2):
        if deadline is not None and time.monotonic() >= deadline:
            break
        cands = _candidates(skip_pids=dead_pids, own_family_ok=own_family_ok)
        if not cands:
            break
        if on_step is not None:
            try:
                on_step(f"trimming {len(cands)} apps")
            except Exception:
                pass
        for cand in cands:
            if deadline is not None and time.monotonic() >= deadline:
                break
            error = empty_working_set(cand["pid"])
            if error is None:
                try:
                    cand["working_set_after_mb"] = round(
                        psutil.Process(cand["pid"]).memory_info().rss / _BY_MB, 1
                    )
                except Exception:
                    cand["working_set_after_mb"] = None
                cand["ok"] = True
                result["trimmed"] += 1
            else:
                cand["ok"] = False
                dead_pids.add(cand["pid"])
                if not _is_alive(cand["pid"]):
                    cand["reason"] = "process exited during optimize"
                    result["skipped"] += 1
                elif error.code == _ERROR_ACCESS_DENIED:
                    cand["reason"] = "access denied (run as Administrator)"
                    result["failed"] += 1
                else:
                    cand["reason"] = error.message
                    result["skipped"] += 1
            result["targets"].append(cand)


def _settle(timeout_s=SETTLE_MAX_S):
    """Wait until Available stops moving, then return the settled value."""
    import psutil

    samples = []
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        samples.append(psutil.virtual_memory().available / _BY_MB)
        samples = samples[-3:]
        if len(samples) == 3 and max(samples) - min(samples) <= SETTLE_TOL_MB:
            break
        time.sleep(1.0)
    samples.append(psutil.virtual_memory().available / _BY_MB)
    samples.sort()
    return samples[len(samples) // 2]


def maximum_optimize(on_step=None, own_family_ok: bool = False) -> dict:
    """Run the full Maximum sequence. `on_step(str)` reports progress."""
    started = time.monotonic()

    def _say(text):
        if on_step is not None:
            try:
                on_step(text)
            except Exception:
                pass

    result = {
        "engine": "maximum",
        "mode": "maximum",
        "supported": _apis() is not None,
        "elevated": is_admin(),
        "available_before_mb": 0.0,
        "available_after_mb": 0.0,
        "available_delta_mb": 0.0,
        "available_settled_mb": 0.0,
        "available_settled_delta_mb": 0.0,
        "free_before_mb": 0.0,
        "free_after_mb": 0.0,
        "free_delta_mb": 0.0,
        "standby_before_mb": 0.0,
        "standby_after_mb": 0.0,
        "targets": [],
        "steps": [],
        "trimmed": 0,
        "skipped": 0,
        "failed": 0,
        "duration_s": 0.0,
    }
    if not result["supported"]:
        result["duration_s"] = round(time.monotonic() - started, 2)
        return result

    result["available_before_mb"] = round(_available_mb(), 1)
    free_before = free_physical_mb()
    result["free_before_mb"] = round(free_before, 1) if free_before is not None else 0.0
    standby_before = standby_mb()
    result["standby_before_mb"] = (
        round(standby_before, 1) if standby_before is not None else 0.0
    )

    # 1. Combine while duplicate data is still resident.
    _say("combining identical pages")
    result["steps"].append(combine_pages())

    # 2. Trim every accessible user process (two sweeps max, then move on:
    # re-trimming active apps every few seconds only faults pages back).
    _say("trimming apps")
    dead_pids: set[int] = set()
    _trim_all(dead_pids, result, on_step, deadline=started + TRIM_BUDGET_S,
              own_family_ok=own_family_ok)

    # 3. System file cache.
    _say("flushing file cache")
    result["steps"].append(flush_file_cache())

    # 4. Dirty pages must hit disk before their RAM is reusable. This step's
    # duration depends on outstanding writes and disk speed.
    _say("writing dirty pages to disk")
    result["steps"].append(flush_modified())

    # 5. Purge what is left on standby.
    _say("purging standby")
    result["steps"].append(purge_standby(low_priority_only=False))

    # 6. Let the numbers land, then measure the honest outcome.
    _say("settling")
    settled = _settle()
    result["available_settled_mb"] = round(settled, 1)
    result["available_settled_delta_mb"] = round(
        settled - result["available_before_mb"], 1
    )
    # Instant reading straight after the last step, for comparison.
    result["available_after_mb"] = round(_available_mb(), 1)
    result["available_delta_mb"] = round(
        result["available_after_mb"] - result["available_before_mb"], 1
    )
    free_after = free_physical_mb()
    result["free_after_mb"] = round(free_after, 1) if free_after is not None else 0.0
    if free_before is not None and free_after is not None:
        result["free_delta_mb"] = round(free_after - free_before, 1)
    standby_after = standby_mb()
    result["standby_after_mb"] = (
        round(standby_after, 1) if standby_after is not None else 0.0
    )

    freed = 0.0
    for cand in result["targets"]:
        if not cand.get("ok"):
            continue
        after_ws = cand.get("working_set_after_mb")
        if after_ws is None:
            continue
        cand["freed_mb"] = round(max(0.0, cand["working_set_mb"] - after_ws), 1)
        freed += cand["freed_mb"]
    result["trimmed_mb"] = round(freed, 1)
    result["duration_s"] = round(time.monotonic() - started, 2)
    return result


if __name__ == "__main__":
    r = maximum_optimize(on_step=lambda s: print(f"[{s}]"))
    print(f"engine={r['engine']} elevated={r['elevated']} "
          f"trimmed={r['trimmed']} skipped={r['skipped']} failed={r['failed']}")
    for s in r["steps"]:
        mark = "ok " if s["ok"] else "SKIP"
        print(f"  [{mark}] {s['name']:<10} freed={s['freed_mb']} MB  {s['detail']}")
    print(f"available {r['available_before_mb']} -> {r['available_after_mb']} "
          f"({r['available_delta_mb']:+} MB), "
          f"settled {r['available_settled_mb']} "
          f"({r['available_settled_delta_mb']:+} MB)")
    print(f"free {r['free_before_mb']} -> {r['free_after_mb']} "
          f"({r['free_delta_mb']:+} MB), "
          f"standby {r['standby_before_mb']} -> {r['standby_after_mb']} MB "
          f"in {r['duration_s']}s")
