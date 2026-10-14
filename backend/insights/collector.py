import hashlib
import time
import uuid
import sys
import psutil
from .app_names import AppNameResolver, UNKNOWN


class ProcessCollector:
    def __init__(self):
        self.session = uuid.uuid4().hex
        self.cache = {}
        self.previous = {}
        self.names = AppNameResolver()
        self.name_metadata = {}
        self.metadata_retry = {}
        self.reader=None
        if sys.platform=='win32':
            from .windows_reader import WindowsReader
            self.reader=WindowsReader()

    def collect(self, snapshot):
        started = time.monotonic()
        groups, seen, denied = {}, set(), 0
        pids=psutil.pids()
        seen=set(pids)
        births={}
        for pid in pids:
            identity = None
            handle=None
            try:
                if self.reader:
                    handle=self.reader.open(pid)
                    born,rss=self.reader.read(handle,pid)
                else:
                    process=psutil.Process(pid)
                    with process.oneshot():born,rss=process.create_time(),int(process.memory_info().rss)
                identity = (pid,born)
                births[pid]=born
                info = self.cache.get(identity)
                if info is None or started >= self.metadata_retry.get(identity,float('inf')):
                    if self.reader:name,exe,owner=self.reader.metadata(handle,pid)
                    else:
                        name=process.name()
                        try:exe,owner=process.exe(),process.username()
                        except (psutil.AccessDenied,psutil.NoSuchProcess):exe,owner='',None
                    key=hashlib.sha256((exe.casefold()+'\0'+owner).encode()).hexdigest()[:24] if exe and owner else None
                    # PID plus creation time identifies the same process across
                    # collector restarts without joining unknown owners by name.
                    key = info[0] if info else key or hashlib.sha256(f'process:{pid}:{born:.7f}'.encode()).hexdigest()[:24]
                    if info and UNKNOWN.fullmatch(name) and not UNKNOWN.fullmatch(info[1]):name=info[1]
                    info = self.cache[identity] = (key, name)
                    self.name_metadata[identity] = self.names.resolve(name,exe)
                    self.metadata_retry[identity] = started+60 if not exe or not owner else float('inf')
                key, name = info
                group = groups.setdefault(key, dict(id=key, name=name, **self.name_metadata.get(identity,{}), rss=0, count=0, complete=True, processes=[]))
                group['rss'] += rss
                group['count'] += 1
                group['processes'].append(dict(pid=pid, born=identity[1], rss=rss))
            except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
                denied += 1
                if identity in self.cache:
                    key, name = self.cache[identity]
                    group = groups.setdefault(key, dict(id=key, name=name, **self.name_metadata.get(identity,{}), rss=0, count=0, complete=False, processes=[]))
                    group['complete'] = False
            finally:
                if handle:self.reader.close(handle)
        for key, old in self.previous.items():
            missing = [p for p in old['processes'] if not any(q['pid'] == p['pid'] and q['born'] == p['born'] for q in groups.get(key, {}).get('processes', []))]
            uncertain = any(p['pid'] in seen and p['pid'] not in births for p in missing)
            if key not in groups and missing:
                groups[key] = dict(id=key, name=old['name'], **{k:old[k] for k in ('displayName','processName','nameSource') if k in old}, rss=0, count=0, complete=not uncertain, processes=[])
            elif uncertain:
                groups[key]['complete'] = False
        newest={}
        for identity in self.cache:
            if identity[0] in seen and (identity[0] not in newest or identity[1]>newest[identity[0]][1]):newest[identity[0]]=identity
        self.cache = {identity: self.cache[identity] for identity in newest.values()}
        self.name_metadata = {identity:value for identity,value in self.name_metadata.items() if identity in self.cache}
        self.metadata_retry = {identity:value for identity,value in self.metadata_retry.items() if identity in self.cache}
        self.previous = {key: value for key, value in groups.items() if value['count'] or not value['complete']}
        ended = time.monotonic()
        return dict(timestamp=snapshot['timestamp'], snapshot=dict(snapshot), groups=list(groups.values()),
                    readable=sum(g['count'] for g in groups.values()), denied=denied,
                    duration=ended-started, complete=ended-started < 6, session=self.session)
