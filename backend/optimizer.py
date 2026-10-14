"""Memory optimizer — frees RAM by trimming the working set of idle apps.

Contract (Main-Plan 3.1):
    optimize(mode: str) -> float        # returns freed MB
    optimize_detailed(...) -> dict      # what the UI renders

Windows only. Trimming works by calling `EmptyWorkingSet` on each target,
which asks the memory manager to drop as many resident pages as possible
from that process's working set. Two honest caveats:

  1. Trimming does NOT create RAM. It moves pages into the standby list,
     where they stay resident until something needs them. The number that
     matters is `psutil.virtual_memory().available`, and it can legitimately
     stay flat or even drop.
  2. A trimmed app reloads its pages on next use. That is a soft page fault
     served from the standby list, so it is far cheaper than a hard fault,
     but it is not free. That is why targets must be idle.

A trimmed page is not written to disk unless it is dirty, so this is not
I/O bound and does not fight the page replacement algorithm the Simulator
teaches.
"""

from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import wintypes

# --- tuning knobs -------------------------------------------------------
# An app must have held at least this much working set to be worth trimming.
MIN_TARGET_MB = 64.0
# Cap per run so one click cannot stall on a machine with hundreds of procs.
MAX_TARGETS = 5
# Sample window used to decide "idle".
CPU_SAMPLE_S = 2.0
# A process must be under this CPU% over the window to count as idle.
IDLE_CPU_MAX_PCT = 3.0
# Grace period after an app started, to skip things the user just opened.
RECENTLY_USED_S = 20.0

_BY_MB = 1024.0 * 1024.0

# PIDs 0-3 are Idle/System/Idle/sReserved pseudo-processes on Windows.
_PSEUDO_PIDS = frozenset({0, 2, 3})

MODES = ("free", "standby", "defrag_sim")


class WinErrorInfo:
    """Why a candidate could not be trimmed."""

    __slots__ = ("code", "message")

    def __init__(self, code: int, message: str):
        self.code = code
        self.message = message


# --- Windows bindings ---------------------------------------------------


def _load_apis():
    """Bind OpenProcess / EmptyWorkingSet / CloseHandle once, lazily.

    Returns None on non-Windows or when the DLLs refuse to load, so callers
    can degrade instead of raising.
    """
    if sys.platform != "win32":
        return None
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)

        kernel32.OpenProcess.argtypes = (
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        )
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL

        # psapi.dll exports EmptyWorkingSet on every supported Windows, but
        # fall back to kernel32 for the PSAPI_VERSION=2 export location.
        for dll in (psapi, kernel32):
            try:
                if hasattr(dll, "EmptyWorkingSet"):
                    dll.EmptyWorkingSet.argtypes = (wintypes.HANDLE,)
                    dll.EmptyWorkingSet.restype = wintypes.BOOL
                    return kernel32, dll
            except Exception:
                continue
    except Exception:
        return None
    return None


_APIS = None


def _apis():
    global _APIS
    if _APIS is None:
        _APIS = _load_apis()
    return _APIS


# PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_SET_QUOTA
_QUERY_LIMITED_INFORMATION = 0x1000
_SET_QUOTA = 0x0100
_ACCESS = _QUERY_LIMITED_INFORMATION | _SET_QUOTA
_ERROR_ACCESS_DENIED = 5


def empty_working_set(pid: int):
    """Trim `pid`'s working set.

    Returns None on success, otherwise a WinErrorInfo describing the failure.
    """
    apis = _apis()
    if apis is None:
        return WinErrorInfo(0, "EmptyWorkingSet unavailable on this platform")
    kernel32, target = apis
    handle = None
    try:
        handle = kernel32.OpenProcess(_ACCESS, False, int(pid))
        if not handle:
            return WinErrorInfo(
                ctypes.get_last_error(), "OpenProcess failed"
            )
        if target.EmptyWorkingSet(handle):
            return None
        return WinErrorInfo(ctypes.get_last_error(), "EmptyWorkingSet failed")
    except Exception as exc:  # noqa: BLE001 - report, never raise into the UI
        return WinErrorInfo(0, f"unexpected error: {exc}")
    finally:
        if handle:
            try:
                kernel32.CloseHandle(handle)
            except Exception:
                pass


# --- candidate selection ------------------------------------------------


def _known_exclusions():
    """Names never worth trimming, plus our own helpers."""
    names = {
        # OS memory manager internals: trimming these either fails outright
        # or degrades the whole machine, never a user's app.
        "system",
        "system idle process",
        "registry",
        "memory compression",
        "memcompression",
        "secure system",
        # Shells and agents whose working set other apps fault pages out of.
        "explorer.exe",
        "dwm.exe",
        "smss.exe",
        "csrss.exe",
        "wininit.exe",
        "winlogon.exe",
        "services.exe",
        "lsass.exe",
        "svchost.exe",
        "audiodg.exe",
        "fontdrvhost.exe",
        "wudfhost.exe",
        "searchindexer.exe",
        "searchprotocolhost.exe",
        "runtimebroker.exe",
    }
    return names | set(_own_names())


_OWN = None


def _own_names():
    global _OWN
    if _OWN is None:
        names = {os.path.basename(sys.argv[0] or "").lower()}
        names.add(os.path.basename(__file__).lower())
        names.discard("")
        _OWN = names
    return _OWN


def _recently_launched(pid: int) -> bool:
    try:
        import psutil

        proc = psutil.Process(pid)
        started = proc.create_time()
    except Exception:
        return True  # unknown age: skip, safer than trimming a starting app
    return (time.time() - started) < RECENTLY_USED_S


def _trim_candidates(max_targets: int | None = None, min_mb: float | None = None):
    """Idle, non-system, single-instance-looking processes worth trimming.

    Returns a list of dicts sorted by working set descending.
    """
    import psutil

    max_targets = MAX_TARGETS if max_targets is None else max_targets
    min_mb = MIN_TARGET_MB if min_mb is None else min_mb

    apis = _apis()
    excluded = _known_exclusions()
    my_pid = os.getpid()
    my_ancestry = {my_pid}
    try:
        my_ancestry.add(psutil.Process(my_pid).ppid())
    except Exception:
        pass

    # Pass 1: keep plausible targets and prime their CPU counters.
    procs = {}
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            info = proc.info
            pid = info.get("pid")
            name = (info.get("name") or "").lower()
            if pid is None or pid in _PSEUDO_PIDS or pid in my_ancestry:
                continue
            if name in excluded:
                continue
            if _recently_launched(pid):
                continue
            try:
                proc.cpu_percent(interval=None)  # primes the counter
            except Exception:
                continue
            procs[pid] = proc
        except Exception:
            continue
    if not procs:
        return []

    # Pass 2: sample CPU to decide who is idle. Per-process, not per-core.
    time.sleep(CPU_SAMPLE_S)
    cpu = {}
    for pid, proc in procs.items():
        try:
            cpu[pid] = float(proc.cpu_percent(interval=None))
        except Exception:
            continue
    idle_pids = {pid for pid, pct in cpu.items() if pct <= IDLE_CPU_MAX_PCT}
    if not idle_pids:
        return []

    # Pass 3: rank idle processes by working set.
    candidates = []
    for pid in idle_pids:
        proc = procs[pid]
        try:
            ws_mb = proc.memory_info().rss / _BY_MB
        except Exception:
            continue
        if ws_mb < min_mb:
            continue
        candidates.append(
            {
                "pid": pid,
                "name": proc.name(),
                "cpu_pct": round(cpu[pid], 1),
                "working_set_mb": round(ws_mb, 1),
                "api": "EmptyWorkingSet" if apis else None,
            }
        )

    # Multi-process apps (chrome.exe, msedge.exe) share one name across a
    # launcher and its children. Trimming every one of them would touch a
    # browser the user is actively looking at, so keep only the heaviest
    # process per name.
    by_name: dict[str, list[dict]] = {}
    for cand in candidates:
        by_name.setdefault(cand["name"].lower(), []).append(cand)

    filtered = [
        max(group, key=lambda c: c["working_set_mb"])
        for group in by_name.values()
    ]
    filtered.sort(key=lambda c: c["working_set_mb"], reverse=True)
    return filtered[:max_targets]


# --- public API ---------------------------------------------------------


def _available_mb():
    import psutil

    return psutil.virtual_memory().available / _BY_MB


def _is_alive(pid: int) -> bool:
    try:
        import psutil

        return psutil.Process(pid).is_running()
    except Exception:
        return False


def optimize_detailed(mode: str = "free", max_targets: int = MAX_TARGETS) -> dict:
    """Trim idle background apps and report measured before/after numbers.

    Returns a dict with keys:
        mode, available_before_mb, available_after_mb, available_delta_mb,
        trimmed_mb, targets (list), trimmed, skipped, failed,
        duration_s, supported
    """
    started = time.monotonic()
    mode = (mode or "free").lower()
    if mode not in MODES:
        raise ValueError(f"unknown mode: {mode} (use {'/'.join(MODES)})")

    supported = _apis() is not None
    result = {
        "mode": mode,
        "supported": supported,
        "available_before_mb": 0.0,
        "available_after_mb": 0.0,
        "available_delta_mb": 0.0,
        "trimmed_mb": 0.0,
        "targets": [],
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

    try:
        candidates = _trim_candidates(max_targets=max_targets)
    except Exception:
        result["duration_s"] = round(time.monotonic() - started, 2)
        return result
    if not candidates:
        result["duration_s"] = round(time.monotonic() - started, 2)
        return result

    import psutil

    for cand in candidates:
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
            # An exited process also reports ACCESS_DENIED on some Windows
            # builds, so check liveness before blaming permissions.
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

    # Only count a measured drop, never a number we invented.
    freed = 0.0
    for cand in result["targets"]:
        if not cand.get("ok"):
            continue
        after_ws = cand.get("working_set_after_mb")
        if after_ws is None:
            continue
        cand["freed_mb"] = round(
            max(0.0, cand["working_set_mb"] - after_ws), 1
        )
        freed += cand["freed_mb"]
    result["trimmed_mb"] = round(freed, 1)

    after_mb = _available_mb()
    result["available_after_mb"] = round(after_mb, 1)
    result["available_delta_mb"] = round(after_mb - before_mb, 1)
    result["duration_s"] = round(time.monotonic() - started, 2)
    return result


def optimize(mode: str = "free") -> float:
    """Contract entry point: return available MB gained (may be 0.0 or negative)."""
    try:
        result = optimize_detailed(mode)
    except ValueError:
        raise
    except Exception:
        return 0.0
    return max(0.0, result["available_delta_mb"])


if __name__ == "__main__":
    r = optimize_detailed("free")
    print(f"mode={r['mode']} supported={r['supported']} trimmed={r['trimmed']} "
          f"skipped={r['skipped']} failed={r['failed']}")
    print(f"available {r['available_before_mb']} MB -> {r['available_after_mb']} MB "
          f"({r['available_delta_mb']:+} MB) in {r['duration_s']}s")
    for t in r["targets"]:
        tail = t.get("reason") or f"{t.get('freed_mb', 0)} MB trimmed"
        print(f"  {t['name']:<20} pid={t['pid']:<7} ws={t['working_set_mb']} MB  {tail}")
