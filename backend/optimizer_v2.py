"""Memory optimizer engine v2 — trim whole idle app groups, not 5 processes.

v1 capped each run at 5 processes and kept one process per program name, so
multi-process apps (Chrome, Edge, Discord) were barely touched. v2 instead:

  * builds real process groups from the ppid tree (one browser = one group),
  * refuses to touch the foreground app's whole group,
  * judges idleness from CPU *and* disk I/O *and* working-set growth,
  * works in time-boxed batches so one click keeps going while it is useful.

Same UI contract as v1: optimize(mode) -> float, optimize_detailed() -> dict
(superset of v1's keys, plus "engine": "v2" and per-group bookkeeping).
"""

from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import wintypes

from backend.optimizer import (
    MODES,
    _BY_MB,
    _ERROR_ACCESS_DENIED,
    _PSEUDO_PIDS,
    _apis,
    _available_mb,
    _is_alive,
    _known_exclusions,
    _own_names,
    empty_working_set,
)

# --- tuning knobs -------------------------------------------------------
MIN_TARGET_MB = 32.0        # per-process floor; groups add up from here
MIN_GROUP_MB = 48.0         # a group must hold this much to be worth it
CPU_SAMPLE_S = 2.0
IDLE_CPU_MAX_PCT = 3.0
# A process doing more I/O than this over the sample window is busy.
IDLE_IO_MAX_MB = 4.0
# A working set growing faster than this is being actively used.
IDLE_WS_GROW_MAX_MB = 8.0
RECENTLY_USED_S = 20.0
# Stop starting new batches after this long; finish the current batch.
TIME_BUDGET_S = 8.0
BATCH_SIZE = 6


# --- foreground detection -----------------------------------------------


def _foreground_pid():
    """PID owning the foreground window, or None if it cannot be told."""
    if sys.platform != "win32":
        return None
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.GetForegroundWindow.argtypes = ()
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.GetWindowThreadProcessId.argtypes = (
            wintypes.HWND, ctypes.POINTER(wintypes.DWORD),
        )
        user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value) or None
    except Exception:
        return None


# --- process groups -----------------------------------------------------


def _recently_launched(create_time: float) -> bool:
    return (time.time() - create_time) < RECENTLY_USED_S


def _snapshot():
    """One psutil pass: {pid: info}. Unknown/vanished processes are skipped."""
    import psutil

    procs = {}
    for proc in psutil.process_iter(
        ["pid", "ppid", "name", "username", "create_time"]
    ):
        try:
            info = proc.info
            if info.get("pid") is None:
                continue
            procs[info["pid"]] = (proc, info)
        except Exception:
            continue
    return procs


def _group_root(pid, by_pid, my_ancestry, own_family_ok=False):
    """Walk up the ppid chain to the top-level ancestor we can see.

    Returns None for my own process, my launcher, anything I spawned, and
    chains that loop or leave our view. `own_family_ok` is a benchmark-only
    escape hatch: the benchmark's fixture processes are my descendants by
    construction, so treat the subtree below my ancestry as a normal group.
    In production the app spawns no child processes, so the flag changes
    nothing there.
    """
    seen = set()
    node = pid
    while True:
        if node in seen or node in _PSEUDO_PIDS:
            return None
        seen.add(node)
        entry = by_pid.get(node)
        if entry is None:
            return None if node in my_ancestry else node
        _, info = entry
        ppid = info.get("ppid")
        if not ppid or ppid == node or ppid in _PSEUDO_PIDS or ppid not in by_pid:
            return None if node in my_ancestry else node
        if ppid in my_ancestry:
            if own_family_ok:
                return node
            return None
        node = ppid


def _prime(proc):
    """Prime counters; returns the I/O baseline, or None when unreadable."""
    try:
        proc.cpu_percent(interval=None)
        io = proc.io_counters()
        proc.memory_info()
        return io.read_bytes + io.write_bytes
    except Exception:
        return None


def _sample(proc):
    """Second-half sample. None when the process cannot be read."""
    try:
        io = proc.io_counters()
        return {
            "cpu": float(proc.cpu_percent(interval=None)),
            "io_bytes": io.read_bytes + io.write_bytes,
            "ws_mb": proc.memory_info().rss / _BY_MB,
        }
    except Exception:
        return None


def _select_groups(max_groups=None, skip_pids=frozenset(), own_family_ok=False,
                   skip_names=frozenset(), scores=None):
    """Idle background app groups worth trimming, heaviest group first.

    `skip_names` holds executables on cooldown from the adaptive memory;
    `scores` maps executable -> 0..1 keep-rate used to rank groups.
    """
    import psutil

    scores = scores or {}

    apis = _apis()
    excluded = _known_exclusions()
    my_pid = os.getpid()
    my_ancestry = {my_pid}
    try:
        my_ancestry.add(psutil.Process(my_pid).ppid())
    except Exception:
        pass

    by_pid = _snapshot()
    fg_pid = _foreground_pid()
    fg_root = (
        _group_root(fg_pid, by_pid, my_ancestry, own_family_ok)
        if fg_pid else None
    )

    # Pass 1: plausible members + prime their counters.
    members = {}  # pid -> (proc, info, ws_before, io_before)
    for pid, (proc, info) in by_pid.items():
        try:
            if pid in _PSEUDO_PIDS or pid in my_ancestry:
                continue
            if pid in skip_pids:
                continue
            name = (info.get("name") or "").lower()
            if not name or name in excluded or name in skip_names:
                continue
            if _recently_launched(info.get("create_time") or 0):
                continue
            try:
                ws_before = proc.memory_info().rss / _BY_MB
            except Exception:
                continue
            if ws_before < MIN_TARGET_MB:
                continue
            io_before = _prime(proc)
            if io_before is None:
                continue
            members[pid] = (proc, info, ws_before, io_before)
        except Exception:
            continue
    if not members:
        return []

    time.sleep(CPU_SAMPLE_S)

    # Pass 2: keep idle members, grouped by their top-level ancestor.
    groups: dict[int, dict] = {}
    for pid, (proc, info, ws_before, io_before) in members.items():
        sample = _sample(proc)
        if sample is None:
            continue
        if sample["cpu"] > IDLE_CPU_MAX_PCT:
            continue
        io_mb = max(0.0, sample["io_bytes"] - io_before) / _BY_MB
        if io_mb > IDLE_IO_MAX_MB:
            continue
        ws_growth = sample["ws_mb"] - ws_before
        if ws_growth > IDLE_WS_GROW_MAX_MB:
            continue
        root = _group_root(pid, by_pid, my_ancestry, own_family_ok)
        if root is None or root == fg_root:
            continue
        group = groups.setdefault(root, {"root": root, "members": []})
        try:
            root_name = by_pid[root][1].get("name") or info.get("name")
        except Exception:
            root_name = info.get("name")
        group["name"] = root_name
        group["members"].append(
            {
                "pid": pid,
                "name": info.get("name"),
                "cpu_pct": round(sample["cpu"], 1),
                "working_set_mb": round(ws_before, 1),
                "api": "EmptyWorkingSet" if apis else None,
            }
        )

    candidates = []
    for group in groups.values():
        total = sum(m["working_set_mb"] for m in group["members"])
        if total < MIN_GROUP_MB:
            continue
        group["members"].sort(key=lambda m: m["working_set_mb"], reverse=True)
        group["total_mb"] = round(total, 1)
        # Rank by expected kept megabytes, not raw size: a huge app that
        # faults everything back ranks below a smaller one that stays down.
        keep = min(scores.get(m["name"].lower(), 1.0) for m in group["members"])
        group["keep"] = round(keep, 3)
        candidates.append(group)
    candidates.sort(
        key=lambda g: (g["total_mb"] * g["keep"], g["total_mb"]), reverse=True
    )
    if max_groups is not None:
        return candidates[:max_groups]
    return candidates


# --- adaptive memory ----------------------------------------------------
# Learns which apps keep a trim and which fault everything straight back.
# Each run first grades the previous run's targets (opportunistic: no extra
# waiting), then records its own targets for the next run to grade.

import json as _json


def _memory_path():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    try:
        os.makedirs(os.path.join(base, "ThrashingMitigatorRedesign"), exist_ok=True)
    except Exception:
        pass
    return os.path.join(base, "ThrashingMitigatorRedesign", "optimizer_memory.json")


def _load_memory():
    try:
        with open(_memory_path(), encoding="utf-8") as fh:
            data = _json.load(fh)
        if isinstance(data, dict):
            data.setdefault("apps", {})
            data.setdefault("pending", [])
            return data
    except Exception:
        pass
    return {"apps": {}, "pending": []}


def _save_memory(data):
    try:
        with open(_memory_path(), "w", encoding="utf-8") as fh:
            _json.dump(data, fh)
    except Exception:
        pass


def _grade_pending(memory):
    """Score last run's targets by how much working set came back.

    Returns {name: score 0..1} and apps to leave alone for a while.
    """
    import psutil

    now = time.time()
    grades = {}
    for item in memory.get("pending", []):
        try:
            name = item["name"]
            dropped = max(0.0, item.get("dropped_mb", 0.0))
            after = item.get("ws_after_mb")
            if dropped <= 0 or after is None:
                continue
            try:
                current = psutil.Process(item["pid"]).memory_info().rss / _BY_MB
            except Exception:
                current = None
            if current is None:
                # Gone: trim stuck (or the app closed) — count as kept.
                score = 1.0
            else:
                regrown = max(0.0, current - after)
                score = max(0.0, min(1.0, 1.0 - regrown / dropped))
            prev = memory["apps"].get(name, {})
            ema = 0.6 * score + 0.4 * float(prev.get("score", score))
            memory["apps"][name] = {
                "score": round(ema, 3),
                "cooldown_until": prev.get("cooldown_until", 0),
                "last_seen": now,
            }
            if ema < 0.3:
                # Faults it straight back: rest this app for 10 minutes.
                memory["apps"][name]["cooldown_until"] = now + 600.0
            grades[name] = round(ema, 3)
        except Exception:
            continue
    memory["pending"] = []
    return grades


def _cooled_down(memory):
    now = time.time()
    return {
        name
        for name, app in memory.get("apps", {}).items()
        if float(app.get("cooldown_until", 0)) > now
    }


# --- public API ---------------------------------------------------------


def optimize_detailed(mode: str = "free", max_targets: int = BATCH_SIZE,
                      own_family_ok: bool = False) -> dict:
    """Trim idle background app groups; same contract as v1 (superset)."""
    started = time.monotonic()
    mode = (mode or "free").lower()
    if mode not in MODES:
        raise ValueError(f"unknown mode: {mode} (use {'/'.join(MODES)})")

    supported = _apis() is not None
    result = {
        "engine": "v2",
        "mode": mode,
        "supported": supported,
        "available_before_mb": 0.0,
        "available_after_mb": 0.0,
        "available_delta_mb": 0.0,
        "trimmed_mb": 0.0,
        "targets": [],
        "groups": 0,
        "trimmed": 0,
        "skipped": 0,
        "failed": 0,
        "duration_s": 0.0,
    }

    before_mb = _available_mb()
    result["available_before_mb"] = round(before_mb, 1)

    if not supported:
        result["duration_s"] = round(time.monotonic() - started, 2)
        return result

    import psutil

    memory = _load_memory()
    grades = _grade_pending(memory)
    cooled = _cooled_down(memory)
    scores = {
        name: float(app.get("score", 1.0))
        for name, app in memory.get("apps", {}).items()
    }
    result["grades"] = grades
    if cooled:
        result["cooled_skipped"] = sorted(cooled)

    # Time-boxed batches: keep trimming while there is useful work, but
    # never keep the user waiting past the budget. PIDs that fail are
    # remembered so later batches do not retry what already refused.
    dead_pids: set[int] = set()
    while True:
        try:
            groups = _select_groups(max_groups=max_targets, skip_pids=dead_pids,
                                    own_family_ok=own_family_ok,
                                    skip_names=cooled, scores=scores)
        except Exception:
            break
        if not groups:
            break
        for group in groups:
            for cand in group["members"]:
                error = empty_working_set(cand["pid"])
                if error is None:
                    try:
                        cand["working_set_after_mb"] = round(
                            psutil.Process(cand["pid"]).memory_info().rss / _BY_MB, 1
                        )
                    except Exception:
                        cand["working_set_after_mb"] = None
                    cand["ok"] = True
                    cand["group"] = group["name"]
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
            result["groups"] += 1
        elapsed = time.monotonic() - started
        if elapsed >= TIME_BUDGET_S:
            break
        # Re-scan: a new batch only starts when fresh idle groups appear.
        # The scan itself costs CPU_SAMPLE_S, which counts toward the budget.
        if elapsed + CPU_SAMPLE_S > TIME_BUDGET_S + 1.0:
            break

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

    after_mb = _available_mb()
    result["available_after_mb"] = round(after_mb, 1)
    result["available_delta_mb"] = round(after_mb - before_mb, 1)
    result["duration_s"] = round(time.monotonic() - started, 2)

    # Record this run's targets so the next run can grade the rebound.
    try:
        memory["pending"] = [
            {
                "pid": cand["pid"],
                "name": cand["name"].lower(),
                "dropped_mb": cand.get("freed_mb", 0.0),
                "ws_after_mb": cand.get("working_set_after_mb"),
            }
            for cand in result["targets"]
            if cand.get("ok")
        ]
        _save_memory(memory)
    except Exception:
        pass
    return result


def optimize(mode: str = "free") -> float:
    """Contract entry point: return available MB gained (never negative)."""
    try:
        result = optimize_detailed(mode)
    except ValueError:
        raise
    except Exception:
        return 0.0
    return max(0.0, result["available_delta_mb"])


if __name__ == "__main__":
    r = optimize_detailed("free")
    print(f"engine={r['engine']} mode={r['mode']} supported={r['supported']} "
          f"groups={r['groups']} trimmed={r['trimmed']} "
          f"skipped={r['skipped']} failed={r['failed']}")
    print(f"available {r['available_before_mb']} MB -> {r['available_after_mb']} MB "
          f"({r['available_delta_mb']:+} MB) in {r['duration_s']}s")
    for t in r["targets"]:
        tail = t.get("reason") or f"{t.get('freed_mb', 0)} MB trimmed"
        print(f"  [{t.get('group')}] {t['name']:<20} pid={t['pid']:<7} "
              f"ws={t['working_set_mb']} MB  {tail}")
