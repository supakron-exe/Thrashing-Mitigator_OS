"""Read WorkingSetSize with documented, query-only Windows process handles.

psutil's access-denied fallback enumerates the whole system per protected PID.
Limited query handles avoid that repeated work; unavailable processes stay partial.
"""
import ctypes
from ctypes import wintypes as W
import ntpath
import psutil


class MemoryCounters(ctypes.Structure):
    _fields_=[('cb',W.DWORD),('PageFaultCount',W.DWORD)]+[(name,ctypes.c_size_t) for name in
        ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage',
         'QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage')]


class SidAttributes(ctypes.Structure):
    _fields_=[('Sid',W.LPVOID),('Attributes',W.DWORD)]


class WindowsReader:
    def __init__(self):
        self.kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        self.security=ctypes.WinDLL('advapi32',use_last_error=True)
        self.kernel.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];self.kernel.OpenProcess.restype=W.HANDLE
        self.kernel.CloseHandle.argtypes=[W.HANDLE];self.kernel.CloseHandle.restype=W.BOOL
        self.kernel.GetProcessTimes.argtypes=[W.HANDLE]+[ctypes.POINTER(W.FILETIME)]*4;self.kernel.GetProcessTimes.restype=W.BOOL
        self.kernel.K32GetProcessMemoryInfo.argtypes=[W.HANDLE,ctypes.POINTER(MemoryCounters),W.DWORD];self.kernel.K32GetProcessMemoryInfo.restype=W.BOOL
        self.kernel.QueryFullProcessImageNameW.argtypes=[W.HANDLE,W.DWORD,W.LPWSTR,ctypes.POINTER(W.DWORD)];self.kernel.QueryFullProcessImageNameW.restype=W.BOOL
        self.security.OpenProcessToken.argtypes=[W.HANDLE,W.DWORD,ctypes.POINTER(W.HANDLE)];self.security.OpenProcessToken.restype=W.BOOL
        self.security.GetTokenInformation.argtypes=[W.HANDLE,ctypes.c_int,W.LPVOID,W.DWORD,ctypes.POINTER(W.DWORD)];self.security.GetTokenInformation.restype=W.BOOL
        self.security.GetLengthSid.argtypes=[W.LPVOID];self.security.GetLengthSid.restype=W.DWORD

    def open(self,pid):
        handle=self.kernel.OpenProcess(0x1000,False,pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:raise psutil.AccessDenied(pid)
        return handle

    def close(self,handle):self.kernel.CloseHandle(handle)

    def read(self,handle,pid):
        created,exited,kernel,user=W.FILETIME(),W.FILETIME(),W.FILETIME(),W.FILETIME()
        if not self.kernel.GetProcessTimes(handle,ctypes.byref(created),ctypes.byref(exited),ctypes.byref(kernel),ctypes.byref(user)):
            raise psutil.AccessDenied(pid)
        counters=MemoryCounters();counters.cb=ctypes.sizeof(counters)
        if not self.kernel.K32GetProcessMemoryInfo(handle,ctypes.byref(counters),counters.cb):raise psutil.AccessDenied(pid)
        born=((created.dwHighDateTime<<32)|created.dwLowDateTime)/10000000-11644473600
        return born,int(counters.WorkingSetSize)

    def metadata(self,handle,pid):
        buffer=ctypes.create_unicode_buffer(32768);length=W.DWORD(len(buffer))
        exe=buffer.value if self.kernel.QueryFullProcessImageNameW(handle,0,buffer,ctypes.byref(length)) else ''
        name=ntpath.basename(exe) if exe else f'Process {pid}'
        if not exe:
            # Kernel pseudo-processes (e.g. MemCompression) have no image path.
            # psutil reads their name from the system process table. Confirm the
            # creation time against this handle so a recycled PID is never named.
            created,exited,kernel,user=W.FILETIME(),W.FILETIME(),W.FILETIME(),W.FILETIME()
            if self.kernel.GetProcessTimes(handle,ctypes.byref(created),ctypes.byref(exited),ctypes.byref(kernel),ctypes.byref(user)):
                born=((created.dwHighDateTime<<32)|created.dwLowDateTime)/10000000-11644473600
                try:
                    process=psutil.Process(pid)
                    fallback=process.name()
                    if abs(process.create_time()-born)<.00001 and fallback:name=fallback
                except (psutil.AccessDenied,psutil.NoSuchProcess,psutil.ZombieProcess):pass
        owner=None
        token=W.HANDLE()
        if self.security.OpenProcessToken(handle,8,ctypes.byref(token)):
            try:
                needed=W.DWORD()
                self.security.GetTokenInformation(token,1,None,0,ctypes.byref(needed))
                if needed.value:
                    data=ctypes.create_string_buffer(needed.value)
                    if self.security.GetTokenInformation(token,1,data,len(data),ctypes.byref(needed)):
                        sid=ctypes.cast(data,ctypes.POINTER(SidAttributes)).contents.Sid
                        owner=ctypes.string_at(sid,self.security.GetLengthSid(sid)).hex()
            finally:self.kernel.CloseHandle(token)
        return name,exe,owner
