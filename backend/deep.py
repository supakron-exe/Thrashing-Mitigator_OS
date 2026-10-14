"""Deep system-memory steps: file cache flush, standby purge, page combine.

These are the OS-level operations behind Wise's "Empty Standby RAM" style
buttons. Unlike per-process EmptyWorkingSet, they act on system-wide lists
and need Administrator rights. Every step reports its own outcome, so the
UI can show exactly what ran and what was skipped for lack of privilege.

References: `NtSetSystemInformation` commands as used by System Informer's
memory-lists dialog (`MemoryPurgeStandbyList`, ...), `SetSystemFileCacheSize`
flush idiom, and `SystemCombinePhysicalMemoryInformation`.
"""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

_BY_MB = 1024.0 * 1024.0

# SYSTEM_INFORMATION_CLASS values (winternl / phnt).
_SystemMemoryListInformation = 80
_SystemCombinePhysicalMemoryInformation = 130

# MEMORY_LIST_COMMAND values (phnt ntmmapi.h).
_MemoryEmptyWorkingSets = 2
_MemoryFlushModifiedList = 3
_MemoryPurgeStandbyList = 4
_MemoryPurgeLowPriorityStandbyList = 5

_STATUS_SUCCESS = 0x00000000
_STATUS_PRIVILEGE_NOT_HELD = 0xC0000061


class _SYSTEM_MEMORY_LIST_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("ZeroPageCount", ctypes.c_size_t),
        ("FreePageCount", ctypes.c_size_t),
        ("ModifiedPageCount", ctypes.c_size_t),
        ("ModifiedNoWritePageCount", ctypes.c_size_t),
        ("BadPageCount", ctypes.c_size_t),
        ("PageCountByPriority", ctypes.c_size_t * 8),
        ("RepurposedPagesByPriority", ctypes.c_size_t * 8),
        ("ModifiedPageCountPageFile", ctypes.c_size_t),
    ]


class _MEMORY_COMBINE_INFORMATION_EX(ctypes.Structure):
    _fields_ = [
        ("EventHandle", wintypes.HANDLE),
        ("PagesCombined", ctypes.c_size_t),
        ("Flags", wintypes.ULONG),
    ]


def _page_size() -> int:
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        class _SYSTEM_INFO(ctypes.Structure):
            _fields_ = [
                ("wProcessorArchitecture", wintypes.WORD),
                ("wReserved", wintypes.WORD),
                ("dwPageSize", wintypes.DWORD),
                ("lpMinimumApplicationAddress", wintypes.LPVOID),
                ("lpMaximumApplicationAddress", wintypes.LPVOID),
                ("dwActiveProcessorMask", ctypes.c_size_t),
                ("dwNumberOfProcessors", wintypes.DWORD),
                ("dwProcessorType", wintypes.DWORD),
                ("dwAllocationGranularity", wintypes.DWORD),
                ("wProcessorLevel", wintypes.WORD),
                ("wProcessorRevision", wintypes.WORD),
            ]

        kernel32.GetSystemInfo.argtypes = (ctypes.POINTER(_SYSTEM_INFO),)
        kernel32.GetSystemInfo.restype = None
        info = _SYSTEM_INFO()
        kernel32.GetSystemInfo(ctypes.byref(info))
        return int(info.dwPageSize) or 4096
    except Exception:
        return 4096


_ntdll = None
_kernel32 = None


def _natives():
    """Bind ntdll/kernel32 entry points once. None off-Windows."""
    global _ntdll, _kernel32
    if sys.platform != "win32":
        return None
    if _ntdll is None:
        try:
            _ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
            _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

            _ntdll.NtSetSystemInformation.argtypes = (
                ctypes.c_int, wintypes.LPVOID, wintypes.ULONG,
            )
            _ntdll.NtSetSystemInformation.restype = wintypes.ULONG
            _ntdll.NtQuerySystemInformation.argtypes = (
                ctypes.c_int, wintypes.LPVOID, wintypes.ULONG,
                ctypes.POINTER(wintypes.ULONG),
            )
            _ntdll.NtQuerySystemInformation.restype = wintypes.ULONG

            _kernel32.SetSystemFileCacheSize.argtypes = (
                ctypes.c_size_t, ctypes.c_size_t, wintypes.DWORD,
            )
            _kernel32.SetSystemFileCacheSize.restype = wintypes.BOOL
        except Exception:
            return None
    return (_ntdll, _kernel32)


def is_admin():
    """True when the process runs elevated."""
    if sys.platform != "win32":
        return False
    try:
        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        shell32.IsUserAnAdmin.restype = wintypes.BOOL
        return bool(shell32.IsUserAnAdmin())
    except Exception:
        return False


class _LUID(ctypes.Structure):
    _fields_ = [("LowPart", wintypes.DWORD),
                ("HighPart", wintypes.LONG)]


class _TOKEN_PRIVILEGES(ctypes.Structure):
    _fields_ = [("PrivilegeCount", wintypes.DWORD),
                ("Luid", _LUID),
                ("Attributes", wintypes.DWORD)]


def _advapi():
    """Bind advapi32 token functions with explicit 64-bit signatures."""
    try:
        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        advapi32.OpenProcessToken.argtypes = (
            wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE),
        )
        advapi32.OpenProcessToken.restype = wintypes.BOOL
        advapi32.LookupPrivilegeValueW.argtypes = (
            wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.POINTER(_LUID),
        )
        advapi32.LookupPrivilegeValueW.restype = wintypes.BOOL
        advapi32.AdjustTokenPrivileges.argtypes = (
            wintypes.HANDLE, wintypes.BOOL,
            ctypes.POINTER(_TOKEN_PRIVILEGES), wintypes.DWORD,
            ctypes.POINTER(_TOKEN_PRIVILEGES),
            ctypes.POINTER(wintypes.DWORD),
        )
        advapi32.AdjustTokenPrivileges.restype = wintypes.BOOL
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.argtypes = ()
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
        kernel32.CloseHandle.restype = wintypes.BOOL
        return advapi32, kernel32
    except Exception:
        return None


def _enable_privilege(name: str) -> tuple[bool, str]:
    """Enable a privilege for this process.

    Returns (True, "ok") only when the privilege is actually assigned:
    AdjustTokenPrivileges reports success even when nothing changed, so
    GetLastError must read ERROR_SUCCESS (0). ERROR_NOT_ALL_ASSIGNED
    (1300) means the token does not hold the privilege — typically the
    process is not elevated.
    """
    if sys.platform != "win32":
        return False, "unavailable on this platform"
    bound = _advapi()
    if bound is None:
        return False, "cannot bind advapi32"
    advapi32, kernel32 = bound
    try:
        token = wintypes.HANDLE()
        if not advapi32.OpenProcessToken(
            kernel32.GetCurrentProcess(), 0x20 | 0x08, ctypes.byref(token)
        ):
            return False, f"OpenProcessToken failed (error {ctypes.get_last_error()})"
        try:
            luid = _LUID()
            if not advapi32.LookupPrivilegeValueW(None, name, ctypes.byref(luid)):
                return False, (
                    f"unknown privilege {name} "
                    f"(error {ctypes.get_last_error()})"
                )
            tp = _TOKEN_PRIVILEGES(1, luid, 0x02)
            if not advapi32.AdjustTokenPrivileges(
                token, False, ctypes.byref(tp), 0, None, None
            ):
                return False, (
                    f"AdjustTokenPrivileges failed "
                    f"(error {ctypes.get_last_error()})"
                )
            code = ctypes.get_last_error()
            if code == 0:
                return True, "ok"
            if code == 1300:
                return False, (
                    f"{name} not held — run as Administrator"
                )
            return False, f"privilege not assigned (error {code})"
        finally:
            kernel32.CloseHandle(token)
    except Exception as exc:  # noqa: BLE001 - reported, never raised
        return False, f"unexpected error: {exc}"


def _query_memory_lists():
    """Raw SYSTEM_MEMORY_LIST_INFORMATION, or None when it cannot be read."""
    natives = _natives()
    if natives is None:
        return None
    ntdll, _ = natives
    try:
        info = _SYSTEM_MEMORY_LIST_INFORMATION()
        ret_len = wintypes.ULONG(0)
        status = ntdll.NtQuerySystemInformation(
            _SystemMemoryListInformation,
            ctypes.byref(info),
            ctypes.sizeof(info),
            ctypes.byref(ret_len),
        )
        if status != _STATUS_SUCCESS:
            return None
        return info
    except Exception:
        return None


def standby_mb():
    """Current standby-list size in MB, or None when it cannot be queried."""
    info = _query_memory_lists()
    if info is None:
        return None
    total_pages = sum(info.PageCountByPriority)
    return total_pages * _page_size() / _BY_MB


def free_physical_mb():
    """True free RAM (Free + Zero page lists) in MB.

    This is NOT psutil's `.free`: on Windows psutil reports `.free` equal
    to `.available` (Free + Zero + Standby). After purging standby, Free
    jumps while Available barely moves — that split is the honest story.
    """
    info = _query_memory_lists()
    if info is None:
        return None
    pages = info.FreePageCount + info.ZeroPageCount
    return pages * _page_size() / _BY_MB


def modified_mb():
    """Modified (dirty, awaiting write-back) pages in MB, or None."""
    info = _query_memory_lists()
    if info is None:
        return None
    pages = info.ModifiedPageCount + info.ModifiedNoWritePageCount
    return pages * _page_size() / _BY_MB


def _ensure_privileges(names):
    """Enable every privilege in `names`. Returns (True, "ok") or details."""
    problems = []
    for name in names:
        ok, detail = _enable_privilege(name)
        if not ok:
            problems.append(f"{name}: {detail}")
    if problems:
        return False, "; ".join(problems)
    return True, "ok"


def _nt_status_message(status: int) -> str:
    if status == _STATUS_PRIVILEGE_NOT_HELD:
        return "needs Administrator rights (privilege not held)"
    return f"NTSTATUS 0x{status:08X}"


def _issue_list_command(command: int) -> tuple[bool, str]:
    natives = _natives()
    if natives is None:
        return False, "unavailable on this platform"
    ntdll, _ = natives
    try:
        cmd = ctypes.c_int(command)
        status = ntdll.NtSetSystemInformation(
            _SystemMemoryListInformation,
            ctypes.byref(cmd),
            ctypes.sizeof(cmd),
        )
        if status == _STATUS_SUCCESS:
            return True, "ok"
        return False, _nt_status_message(status)
    except Exception as exc:  # noqa: BLE001 - reported, never raised
        return False, f"unexpected error: {exc}"


def flush_file_cache() -> dict:
    """Flush the system file cache. Needs SeIncreaseQuotaPrivilege."""
    step = {"name": "file_cache", "ok": False, "freed_mb": 0.0, "detail": ""}
    natives = _natives()
    if natives is None:
        step["detail"] = "unavailable on this platform"
        return step
    _, kernel32 = natives
    before = standby_mb()
    ok, detail = _enable_privilege("SeIncreaseQuotaPrivilege")
    if not ok:
        step["detail"] = detail
        return step
    try:
        max_size = ctypes.c_size_t(-1).value
        ok = kernel32.SetSystemFileCacheSize(max_size, max_size, 0)
        if not ok:
            step["detail"] = (
                f"SetSystemFileCacheSize failed "
                f"(error {ctypes.get_last_error()})"
            )
            return step
    except Exception as exc:  # noqa: BLE001
        step["detail"] = f"unexpected error: {exc}"
        return step
    after = standby_mb()
    step["ok"] = True
    if before is not None and after is not None:
        step["freed_mb"] = round(max(0.0, before - after), 1)
        step["detail"] = f"standby {before:.0f} -> {after:.0f} MB"
    else:
        step["detail"] = "flushed (standby size unreadable)"
    return step


def purge_standby(low_priority_only: bool = False) -> dict:
    """Purge the standby list (or only priority-0). Needs Administrator."""
    step = {"name": "standby", "ok": False, "freed_mb": 0.0, "detail": ""}
    before = standby_mb()
    ok, detail = _ensure_privileges(["SeProfileSingleProcessPrivilege"])
    if not ok:
        step["detail"] = detail
        return step
    ok, message = _issue_list_command(
        _MemoryPurgeLowPriorityStandbyList if low_priority_only else _MemoryPurgeStandbyList
    )
    if not ok:
        step["detail"] = message
        return step
    after = standby_mb()
    step["ok"] = True
    if before is not None and after is not None:
        step["freed_mb"] = round(max(0.0, before - after), 1)
        scope = "priority-0" if low_priority_only else "full"
        step["detail"] = f"{scope} standby {before:.0f} -> {after:.0f} MB"
    else:
        step["detail"] = "purged (standby size unreadable)"
    return step


def flush_modified() -> dict:
    """Write dirty modified pages back so their RAM can be reused.

    How long this takes depends on how much dirty data is outstanding and
    on disk speed — the UI should show progress while this step runs.
    """
    step = {"name": "modified", "ok": False, "freed_mb": 0.0, "detail": ""}
    before = modified_mb()
    ok, detail = _ensure_privileges(["SeProfileSingleProcessPrivilege"])
    if not ok:
        step["detail"] = detail
        return step
    ok, message = _issue_list_command(_MemoryFlushModifiedList)
    if not ok:
        step["detail"] = message
        return step
    after = modified_mb()
    step["ok"] = True
    if before is not None and after is not None:
        step["freed_mb"] = round(max(0.0, before - after), 1)
        step["detail"] = f"modified {before:.0f} -> {after:.0f} MB"
    else:
        step["detail"] = "flushed (modified list unreadable)"
    return step


def combine_pages() -> dict:
    """Combine identical physical pages. Needs Administrator; Win10+."""
    step = {"name": "combine", "ok": False, "freed_mb": 0.0, "detail": ""}
    natives = _natives()
    if natives is None:
        step["detail"] = "unavailable on this platform"
        return step
    ok, detail = _ensure_privileges(["SeProfileSingleProcessPrivilege"])
    if not ok:
        step["detail"] = detail
        return step
    ntdll, _ = natives
    try:
        info = _MEMORY_COMBINE_INFORMATION_EX()
        info.EventHandle = None
        info.PagesCombined = 0
        info.Flags = 0
        status = ntdll.NtSetSystemInformation(
            _SystemCombinePhysicalMemoryInformation,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if status != _STATUS_SUCCESS:
            step["detail"] = _nt_status_message(status)
            return step
        step["ok"] = True
        step["freed_mb"] = round(info.PagesCombined * 4096 / _BY_MB, 1)
        step["detail"] = f"{info.PagesCombined} pages combined"
        return step
    except Exception as exc:  # noqa: BLE001
        step["detail"] = f"unexpected error: {exc}"
        return step


def _available_mb():
    import psutil

    return psutil.virtual_memory().available / _BY_MB


def deep_optimize(include_combine: bool = True,
                  include_modified: bool = False) -> dict:
    """Run the system-level steps and report each one honestly.

    Free gain and Available gain are reported separately: purging standby
    mostly converts Standby into Free, and Available already counted that
    Standby — so Free can jump by gigabytes while Available barely moves.
    `free_delta_mb` uses the true Free/Zero page lists, not psutil's `.free`
    (which equals `.available` on Windows).
    """
    started = time.monotonic()
    result = {
        "engine": "deep",
        "supported": sys.platform == "win32",
        "elevated": is_admin(),
        "available_before_mb": 0.0,
        "available_after_mb": 0.0,
        "available_delta_mb": 0.0,
        "free_before_mb": 0.0,
        "free_after_mb": 0.0,
        "free_delta_mb": 0.0,
        "steps": [],
        "duration_s": 0.0,
    }
    if sys.platform != "win32":
        result["duration_s"] = round(time.monotonic() - started, 2)
        return result

    result["available_before_mb"] = round(_available_mb(), 1)
    free_before = free_physical_mb()
    result["free_before_mb"] = round(free_before, 1) if free_before is not None else 0.0

    result["steps"].append(flush_file_cache())
    if include_modified:
        result["steps"].append(flush_modified())
    result["steps"].append(purge_standby(low_priority_only=False))
    if include_combine:
        result["steps"].append(combine_pages())

    result["available_after_mb"] = round(_available_mb(), 1)
    result["available_delta_mb"] = round(
        result["available_after_mb"] - result["available_before_mb"], 1
    )
    free_after = free_physical_mb()
    result["free_after_mb"] = round(free_after, 1) if free_after is not None else 0.0
    if free_before is not None and free_after is not None:
        result["free_delta_mb"] = round(free_after - free_before, 1)
    result["duration_s"] = round(time.monotonic() - started, 2)
    return result


if __name__ == "__main__":
    print(f"elevated: {is_admin()}")
    print(f"standby now: {standby_mb()} MB")
    r = deep_optimize()
    for s in r["steps"]:
        mark = "ok " if s["ok"] else "SKIP"
        print(f"  [{mark}] {s['name']:<10} freed={s['freed_mb']} MB  {s['detail']}")
    print(f"available {r['available_before_mb']} -> {r['available_after_mb']} "
          f"({r['available_delta_mb']:+} MB), "
          f"free {r.get('free_delta_mb', 0):+} MB in {r['duration_s']}s")
