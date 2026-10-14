"""Resolve descriptive names off the GUI thread; never infer identity from a PID."""
import ctypes
from ctypes import wintypes as W
from collections import OrderedDict
import re
import sys


UNKNOWN = re.compile(r'^Process (\d+)$')
SYSTEM_NAMES = {'memcompression': 'Windows memory compression',
                'system': 'Windows kernel', 'system idle process': 'System idle process'}


def clean_name(value):
    return ' '.join(str(value or '').replace('\x00', '').split())[:160]


class AppNameResolver:
    def __init__(self):
        self.cache = OrderedDict()
        self.version = None
        if sys.platform == 'win32':
            self.version = ctypes.WinDLL('version', use_last_error=True)
            self.version.GetFileVersionInfoSizeW.argtypes = [W.LPCWSTR, ctypes.POINTER(W.DWORD)]
            self.version.GetFileVersionInfoSizeW.restype = W.DWORD
            self.version.GetFileVersionInfoW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, W.LPVOID]
            self.version.GetFileVersionInfoW.restype = W.BOOL
            self.version.VerQueryValueW.argtypes = [W.LPCVOID, W.LPCWSTR, ctypes.POINTER(W.LPVOID), ctypes.POINTER(W.UINT)]
            self.version.VerQueryValueW.restype = W.BOOL

    def _description(self, exe):
        if not self.version or not exe:
            return '', ''
        size = self.version.GetFileVersionInfoSizeW(exe, None)
        if not size or size > 4 * 1024 * 1024:
            return '', ''
        data = ctypes.create_string_buffer(size)
        if not self.version.GetFileVersionInfoW(exe, 0, size, data):
            return '', ''
        address, length = W.LPVOID(), W.UINT()
        translations = []
        if self.version.VerQueryValueW(data, r'\VarFileInfo\Translation', ctypes.byref(address), ctypes.byref(length)):
            words = ctypes.cast(address, ctypes.POINTER(W.WORD))
            translations = [(words[i], words[i + 1]) for i in range(0, length.value // 2 - 1, 2)]
        for field, source in (('FileDescription', 'file_description'), ('ProductName', 'product_name')):
            for language, codepage in translations:
                key = f'\\StringFileInfo\\{language:04x}{codepage:04x}\\{field}'
                if self.version.VerQueryValueW(data, key, ctypes.byref(address), ctypes.byref(length)) and length.value:
                    value = clean_name(ctypes.wstring_at(address, length.value).rstrip('\x00'))
                    if value:
                        return value, source
        return '', ''

    def resolve(self, name, exe=''):
        name = clean_name(name)
        if UNKNOWN.fullmatch(name):
            return dict(displayName='', processName=name, nameSource='unavailable')
        cache_key = exe.casefold() if exe else ''
        if cache_key:
            if cache_key not in self.cache:
                self.cache[cache_key] = self._description(exe)
                if len(self.cache) > 512:
                    self.cache.popitem(last=False)
            self.cache.move_to_end(cache_key)
            description, source = self.cache[cache_key]
        else:
            description, source = '', ''
        if not description:
            description = SYSTEM_NAMES.get(name.casefold(), name)
            source = 'system_name' if name.casefold() in SYSTEM_NAMES else 'process_name'
        return dict(displayName=description, processName=name, nameSource=source)
