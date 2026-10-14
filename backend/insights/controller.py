import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import QObject, Property, QThread, QTimer, Signal, Slot, Qt
from backend.localization import tr
from .collector import ProcessCollector
from .events import EventDetector
from .models import RowModel
from .store import HistoryStore, disk_size


def amount(value, signed=False):
    if value is None: return '—'
    sign = '+' if signed and value > 0 else '−' if value < 0 else ''
    value = abs(value)
    if value>=1024**3: label=f'{value/1024**3:.2f} GB'
    elif value>=.1*1024**2 or value==0: label=f'{value/1024**2:.1f} MB'
    elif value>=1024: label=f'{value/1024:.1f} KB'
    else: label=f'{value:.0f} B'
    return sign+label


def clock(value, with_date=False): return datetime.fromtimestamp(value).strftime('%d/%m %H:%M' if with_date else '%H:%M:%S') if value else '—'


class CollectorWorker(QObject):
    completed = Signal(object)
    stopped = Signal()

    def __init__(self, provider=None):
        super().__init__()
        self.collector = provider or ProcessCollector()
        self.detector = EventDetector()
        self.generation = -1
        self.segment = uuid.uuid4().hex
        self.last_wall = self.last_mono = 0
        self.last_global = 0

    @Slot(object)
    def collect(self, request):
        wall, mono = request['snapshot']['timestamp'], time.monotonic()
        if self.generation != request['generation'] or (self.last_wall and (wall-self.last_wall > 18 or wall <= self.last_wall or abs((wall-self.last_wall)-(mono-self.last_mono))>5)):
            self.segment=uuid.uuid4().hex
            self.detector.reset()
        self.generation = request['generation']
        self.last_wall,self.last_mono = wall,mono
        for sample in request['system']:
            if self.last_global and (sample['timestamp']-self.last_global>4.5 or sample['timestamp']<=self.last_global):
                self.segment=uuid.uuid4().hex
                self.detector.reset()
            sample['segment']=self.segment
            self.last_global=sample['timestamp']
        try:
            batch = self.collector.collect(request['snapshot'])
            batch['segment'] = self.segment
            events = self.detector.feed(batch, request['suppress'])
            packet = dict(batch=batch,events=events,system=request['system'],segment=self.segment,generation=self.generation,error='')
        except Exception as exc:
            self.detector.reset()
            packet = dict(batch=None,events=[],system=request['system'],segment=self.segment,generation=self.generation,error=str(exc))
        self.completed.emit(packet)

    @Slot()
    def stop(self): self.stopped.emit()


class StoreWorker(QObject):
    response = Signal(object)
    state = Signal(object)
    stopped = Signal()

    def __init__(self, path):
        super().__init__()
        self.path, self.store, self.error, self.generation = path,None,'',0

    @Slot()
    def initialize(self):
        try:
            self.store = HistoryStore(self.path)
            self.store.resolve_recorded_names()
            self.store.flush()
        except Exception as exc:
            self.error=str(exc)
            self.store=HistoryStore(':memory:')
        self.timer=QTimer(self)
        self.timer.setInterval(30000)
        self.timer.timeout.connect(self.flush)
        self.timer.start()
        self.publish()

    def publish(self):
        self.state.emit(dict(error=self.error,savedAt=0 if self.store.memory_only else self.store.saved_at,temporary=self.store.memory_only,
            unread=self.store.db.execute('SELECT COUNT(*) FROM events WHERE unread=1').fetchone()[0],
            size=disk_size(self.path),recovery=self.store.recovery))

    def fail(self, exc):
        self.error=str(exc)
        try: self.store.db.rollback(); self.store.db.close()
        except Exception: pass
        self.store=HistoryStore(':memory:')

    @Slot(object)
    def write(self, packet):
        if packet['generation'] != self.generation: return
        try:
            self.store.write(packet)
            if packet.get('events'): self.store.db.commit(); self.store.saved_at=time.time()
        except Exception as exc:
            self.fail(exc)
            self.store.write(packet)
        self.publish()

    @Slot()
    def flush(self):
        try: self.store.flush()
        except Exception as exc: self.fail(exc)
        self.publish()

    @Slot(object)
    def query(self, request):
        try:
            data=self.store.query(request['start'],request['end'],request['app'],request.get('eventOffset',0))
            data.update(request=request,error=self.error)
        except Exception as exc:
            self.fail(exc)
            data=self.store.query(request['start'],request['end'],request['app'],request.get('eventOffset',0))
            data.update(request=request,error=self.error)
        self.response.emit(data)

    @Slot(str)
    def read(self, event_id):
        try: self.store.mark_read(event_id or None)
        except Exception as exc: self.error=str(exc)
        self.publish()

    @Slot(int)
    def clear(self, generation):
        self.generation=generation
        disk=None
        try:
            if self.store.memory_only:
                disk=HistoryStore(self.path)
                disk.clear()
                self.store.db.close()
                self.store=disk
                self.error=''
            else:self.store.clear()
        except Exception as exc:
            if disk:
                disk.db.rollback();disk.db.close()
            self.error='Could not clear saved history: '+str(exc)
        self.publish()

    @Slot(int)
    def set_generation(self, generation): self.generation=generation

    @Slot()
    def retry(self):
        disk=None
        try:
            if not self.store.memory_only:self.store.flush()
            disk=HistoryStore(self.path)
            if self.store.memory_only:
                for table in ('system','apps','system_minutes','app_minutes','events','app_identity'):
                    columns=len(self.store.db.execute(f'PRAGMA table_info({table})').fetchall())
                    disk.db.executemany(f"INSERT OR REPLACE INTO {table} VALUES({','.join('?' for _ in range(columns))})",(tuple(row) for row in self.store.db.execute(f'SELECT * FROM {table}')))
            disk.flush()
            self.store.db.close()
            self.store=disk
            self.error=''
        except Exception as exc:
            if disk:
                disk.db.rollback();disk.db.close()
            self.error=str(exc)
        self.publish()

    @Slot()
    def stop(self):
        self.timer.stop()
        try: self.store.close()
        except Exception as exc: self.state.emit(dict(error=str(exc)))
        self.stopped.emit()


class InsightsController(QObject):
    changed = Signal()
    viewChanged = Signal()
    closeReady = Signal()
    collectRequested = Signal(object)
    writeRequested = Signal(object)
    queryRequested = Signal(object)
    readRequested = Signal(str)
    clearRequested = Signal(int)
    retryRequested = Signal()
    stopCollector = Signal()
    stopStore = Signal()

    def __init__(self, memory, path=None, language=None, provider=None, parent=None):
        super().__init__(parent)
        self.memory=memory
        self.path=Path(path) if path else Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'ThrashingMitigatorRedesign'/'insights'/'insights.db'
        self._tracking,self._active,self._closing=True,False,False
        self._collecting,self._querying,self._pending=False,False,False
        self._generation,self._revision,self._request_id=0,0,0
        self._range,self._end,self._follow=900,0,True
        self._event_offset=0
        self._last_collect,self._last_sample,self._suppress_until=0,0,0
        self._collector_error,self._storage_error='',''
        self._last_live=memory.live
        self._coverage,self._storage,self._summary={},{},{}
        self._series,self._raw,self._system=[],{},[]
        self._app_id,self._search,self._sort='','','growth'
        self._manual_app_selection=False
        self._order=[]
        self._selected_app,self._selected_event={},{}
        self._unread=0
        self._operation_id=None
        self._segment=uuid.uuid4().hex
        self._collector_done,self._store_done=False,False
        self._app_model,self._event_model=RowModel(self),RowModel(self)
        self._visual_ranking=RowModel(self)
        self._recent_event_model=RowModel(self)
        self._visual_summary,self._recent_events={},[]
        self.collector_thread=QThread(self)
        self.store_thread=QThread(self)
        self.collector=CollectorWorker(provider)
        self.storage=StoreWorker(self.path)
        self.collector.moveToThread(self.collector_thread)
        self.storage.moveToThread(self.store_thread)
        self.collectRequested.connect(self.collector.collect)
        self.collector.completed.connect(self._collected)
        self.stopCollector.connect(self.collector.stop)
        self.collector.stopped.connect(self.collector_thread.quit,Qt.DirectConnection)
        self.collector.stopped.connect(self.collector.deleteLater)
        self.collector_thread.finished.connect(self._collector_finished)
        self.store_thread.started.connect(self.storage.initialize)
        self.writeRequested.connect(self.storage.write)
        self.queryRequested.connect(self.storage.query)
        self.readRequested.connect(self.storage.read)
        self.clearRequested.connect(self.storage.clear)
        self.storage_generationRequested.connect(self.storage.set_generation)
        self.retryRequested.connect(self.storage.retry)
        self.stopStore.connect(self.storage.stop)
        self.storage.response.connect(self._received)
        self.storage.state.connect(self._state)
        self.storage.stopped.connect(self.store_thread.quit,Qt.DirectConnection)
        self.storage.stopped.connect(self.storage.deleteLater)
        self.store_thread.finished.connect(self._store_finished)
        self.store_thread.start()
        self.collector_thread.start()
        memory.sampleChanged.connect(self._sample)
        memory.operationChanged.connect(self._operation)
        memory.closingChanged.connect(self._memory_closing)
        if language: language.changed.connect(self._present)
        self._sample()
        self._operation()

    @Property(bool,notify=changed)
    def tracking(self): return self._tracking
    @Property(bool,notify=changed)
    def safeToClose(self): return self._collector_done and self._store_done
    @Property(bool,notify=changed)
    def followLive(self): return self._follow
    @Property(int,notify=changed)
    def selectedRange(self): return self._range
    @Property(float,notify=changed)
    def selectedEnd(self): return self._end
    @Property(str,notify=changed)
    def lastSampleAt(self): return clock(self._last_sample)
    @Property(str,notify=changed)
    def status(self):
        if not self._tracking: return tr('Tracking paused')
        if self._collector_error or not self.memory.live or (self._coverage and not self._coverage.get('complete',True)) or (self._last_sample and time.time()-self._last_sample>18): return tr('Readings delayed')
        return tr('Tracking') if self._last_sample else tr('Collecting readings')
    @Property('QVariantMap',notify=changed)
    def coverage(self): return self._coverage
    @Property('QVariantMap',notify=changed)
    def storageState(self):
        return dict(self._storage,error=self._storage_error, sizeLabel=amount(self._storage.get('size',0)),savedLabel=clock(self._storage.get('savedAt',0)))
    @Property('QVariantMap',notify=viewChanged)
    def summary(self): return self._summary
    @Property('QVariantList',notify=viewChanged)
    def chartSeries(self): return self._series
    @Property(QObject,constant=True)
    def appModel(self): return self._app_model
    @Property(QObject,constant=True)
    def eventModel(self): return self._event_model
    @Property(QObject,constant=True)
    def visualRanking(self): return self._visual_ranking
    @Property('QVariantMap',notify=viewChanged)
    def visualSummary(self): return self._visual_summary
    @Property('QVariantList',notify=viewChanged)
    def recentEvents(self): return self._recent_events
    @Property(QObject,constant=True)
    def recentEventModel(self): return self._recent_event_model
    @Property('QVariantMap',notify=viewChanged)
    def selectedApp(self): return self._selected_app
    @Property('QVariantList',notify=viewChanged)
    def selectedAppMarkers(self):
        if not self._app_id:return []
        return [event for event in self._raw.get('markers',[]) if
                event.get('kind')=='optimize' or event.get('app')==self._app_id or
                any(contributor.get('id')==self._app_id for contributor in event.get('contributors',[]))]
    @Property('QVariantMap',notify=viewChanged)
    def selectedEvent(self): return self._selected_event
    @Property(int,notify=changed)
    def unreadCount(self): return self._unread
    @Property('QVariantList',notify=viewChanged)
    def markers(self): return self._raw.get('markers',[])

    @Property(int,notify=changed)
    def eventPage(self): return self._event_offset//200
    @Property(int,notify=changed)
    def eventTotal(self): return self._raw.get('eventTotal',0)
    @Property(bool,notify=changed)
    def loading(self): return self._querying

    @Slot()
    def _sample(self):
        if self._last_live != self.memory.live:
            self._last_live=self.memory.live
            self.changed.emit()
        if self._closing or not self._tracking or not self.memory.live: return
        snapshot=dict(self.memory.snapshot)
        if not snapshot.get('timestamp'): return
        self._system.append(snapshot)
        self._system=self._system[-30:]
        now=snapshot['timestamp']
        mono=time.monotonic()
        if mono-self._last_collect<6: return
        if self._collecting: return
        self._last_collect=mono
        self._collecting=True
        samples,self._system=self._system,[]
        self.collectRequested.emit(dict(snapshot=snapshot,system=samples,generation=self._generation,suppress=self.memory.running or mono<self._suppress_until))

    @Slot(object)
    def _collected(self, packet):
        self._collecting=False
        if packet['generation'] != self._generation: return
        self._segment=packet['segment']
        self._collector_error=packet['error']
        batch=packet['batch']
        if batch:
            self._last_sample=batch['timestamp']
            self._coverage=dict(readable=batch['readable'],denied=batch['denied'],duration=batch['duration'],complete=batch['complete'])
        self.writeRequested.emit(packet)
        if self._follow: self._request_view()
        self.changed.emit()

    @Slot()
    def _operation(self):
        op=self.memory.operation
        if not op: return
        op_id=op.get('id')
        if self.memory.running and op_id != self._operation_id:
            self._operation_id=op_id
            self._marker_id=uuid.uuid4().hex
            event=dict(id=self._marker_id,kind='optimize',timestamp=op['startedAt'],startedAt=op['startedAt'],finishedAt=0,mode=op['mode'],source=op['source'],segment=self._segment,contributors=[])
            self.writeRequested.emit(dict(events=[event],system=[],segment=self._segment,generation=self._generation))
        if not self.memory.running and op_id==self._operation_id and op.get('finishedAt'):
            self._suppress_until=time.monotonic()+60
            event=dict(id=self._marker_id,kind='optimize',timestamp=op['finishedAt'],startedAt=op['startedAt'],finishedAt=op['finishedAt'],mode=op['mode'],source=op['source'],segment=self._segment,contributors=[])
            self.writeRequested.emit(dict(events=[event],system=[],segment=self._segment,generation=self._generation))
            self._operation_id=None
            self._request_view()

    @Slot(object)
    def _state(self, state):
        old_unread=self._unread
        old_error=self._storage_error
        old_temporary=self._storage.get('temporary')
        self._storage.update(state)
        self._storage_error=state.get('error',self._storage_error)
        self._unread=state.get('unread',self._unread)
        self.changed.emit()
        if self._active and (old_unread!=self._unread or old_error!=self._storage_error or old_temporary!=state.get('temporary')): self._request_view()

    def _request_view(self):
        if self._closing or not self._active: return
        if self._querying:
            self._pending=True
            return
        self._querying=True
        self._request_id+=1
        end=self._last_sample or time.time() if self._follow else self._end
        self.queryRequested.emit(dict(start=end-self._range,end=end,app=self._app_id,eventOffset=self._event_offset,revision=self._revision,generation=self._generation,id=self._request_id))
        self.changed.emit()

    @Slot(object)
    def _received(self, data):
        self._querying=False
        request=data['request']
        if request['generation']==self._generation and request['revision']==self._revision:
            self._raw=data
            self._series=data['series']
            self._storage_error=data['error']
            self._present()
        if self._pending:
            self._pending=False
            self._request_view()

    @Slot()
    def _present(self):
        data=self._raw
        rows=[]
        for raw in data.get('apps',[]):
            item=dict(raw)
            self._name_labels(item)
            item['complete']=bool(item['complete'])
            first_label=clock(item['firstAt'],self._range>=21600 or not self._follow)
            last_label=clock(item['lastAt'],self._range>=21600 or not self._follow)
            item.update(ramLabel=amount(item['bytes']),deltaLabel=amount(item['delta'],True),
                        stateLabel=tr('Closed') if item['closed'] else tr('Last observed') if item.get('stale') else tr('Partial reading') if not item['complete'] else tr('Opened in this range') if item.get('new') else tr('Observed readings') if item.get('hasGaps') else tr('Observed in this range') if item['delta'] is None else tr('Tracking'),
                        peakLabel=amount(item['peak']),beforeLabel=amount(item['before']),
                        firstLabel=first_label,lastLabel=last_label,
                        observedSpanLabel=first_label+' – '+last_label)
            rows.append(item)
        # Rank the measured observation interval, also for newly opened apps.
        # Historical-only identities never masquerade as current live apps.
        eligible=[r for r in rows if not r['closed'] and not(self._follow and r.get('stale'))]
        growth=sorted((r for r in eligible if r.get('comparable',r['delta'] is not None) and r['delta'] is not None and r['delta']>0),
                      key=lambda r:(-r['delta'],r['name'].casefold(),r['id']))[:5]
        maximum=growth[0]['delta'] if growth else 0
        highest=max((r for r in eligible if r['bytes'] is not None),key=lambda r:r['bytes'],default=None)
        self._visual_ranking.update([dict(r,barRatio=r['delta']/maximum) for r in growth])
        self._visual_summary=dict(maxDelta=maximum,appCount=len(rows),
            excluded=sum(r['closed'] or (self._follow and r.get('stale',False)) or r['delta'] is None for r in rows),
            fallback=not bool(growth),fallbackAppId=highest['id'] if highest else '')
        selected_raw=next((r for r in rows if r['id']==self._app_id),None)
        auto_selection_expired=(not self._manual_app_selection and self._follow and
                                (not selected_raw or selected_raw['closed'] or selected_raw.get('stale')))
        if (not self._app_id or auto_selection_expired) and not self._selected_event:
            candidate=growth[0] if growth else highest
            if candidate and candidate['id']!=self._app_id:
                self._app_id=candidate['id']
                self._revision+=1
                QTimer.singleShot(0,self._request_view)
        if not self._order:
            rows.sort(key=(lambda r:r['displayName'].casefold()) if self._sort=='name' else (lambda r:-(r.get('bytes') or 0)) if self._sort=='ram' else (lambda r:-(r['delta'] if r['delta'] is not None else -float('inf'))))
            self._order=[r['id'] for r in rows]
        known={key:i for i,key in enumerate(self._order)}
        rows.sort(key=lambda r:known.get(r['id'],len(known)))
        self._order.extend(r['id'] for r in rows if r['id'] not in known)
        self._app_model.update([r for r in rows if self._search in (r['displayName']+' '+r['processName']).casefold()])
        events=[]
        for raw in data.get('events',[]):
            events.append(self._format_event(raw))
        self._event_model.update(events)
        self._recent_events=[self._format_event(e) for e in data.get('markers',[])[:3]]
        self._recent_event_model.update(self._recent_events)
        selected=next((r for r in rows if r['id']==self._app_id),{})
        matching=data.get('request',{}).get('app')==self._app_id
        self._selected_app=dict(selected,series=data.get('details',[]) if matching else [],processes=[dict(p,ramLabel=amount(p['rss'])) for p in data.get('processes',[])] if matching else []) if selected else {}
        if self._selected_event:
            self._selected_event=next((e for e in events if e['id']==self._selected_event['id']),self._format_event(self._selected_event))
        points=self._series
        valid=(len(points)>1 and points[0].get('used') is not None and points[-1].get('used') is not None)
        system_has_gaps=len({point['segment'] for point in points})>1
        top=max((r for r in rows if r['delta'] is not None and r['delta']>0),key=lambda r:r['delta'],default=None)
        self._summary=dict(changeLabel=amount(points[-1]['used']-points[0]['used'],True) if valid else '—',
            systemHasGaps=system_has_gaps,
            topName=top['displayName'] if top else tr('No measured increase'),topDelta=top['deltaLabel'] if top else '—',
            eventCount=data.get('eventCount',0),spanLabel=(clock(points[0]['timestamp'],self._range>=21600 or not self._follow)+' – '+clock(points[-1]['timestamp'],self._range>=21600 or not self._follow)) if points else tr('Waiting for readings'),
            observedSeconds=points[-1]['timestamp']-points[0]['timestamp'] if points else 0,
            storedSince=clock(data.get('storedSince')),minuteSummary=any(p.get('aggregated') for p in points))
        self.viewChanged.emit()
        self.changed.emit()

    def _selection_changed(self):
        self._revision+=1
        self._event_offset=0
        self._order=[]
        self._request_view()
        self.viewChanged.emit()
        self.changed.emit()

    @Slot(bool)
    def setActive(self, active):
        self._active=active
        if active: self._request_view()
    @Slot(int)
    def setRange(self, seconds):
        if seconds not in (300,900,1800,3600,21600,86400): return
        self._range=seconds
        self._selected_event={}
        self._selection_changed()
    @Slot(float)
    def setEndTime(self, timestamp):
        if timestamp<=0 or timestamp>time.time()+6: return
        self._end=timestamp
        self._follow=False
        self._selection_changed()
    @Slot()
    def previousRange(self): self.setEndTime((self._last_sample or time.time() if self._follow else self._end)-self._range)
    @Slot()
    def nextRange(self):
        if self._end+self._range>=self._last_sample: self.returnToLive()
        else: self.setEndTime(self._end+self._range)
    @Slot()
    def returnToLive(self):
        self._follow=True
        self._selected_event={}
        self._selection_changed()
    @Slot(str)
    def selectApp(self, app_id):
        previous_event=self._selected_event
        self._app_id=app_id
        self._manual_app_selection=bool(app_id)
        self._selected_event={}
        self._selected_app=next((dict(r,series=[],processes=[]) for r in self._app_model.rows if r['id']==app_id),{})
        if app_id and not self._selected_app:
            info=next((r for r in self._raw.get('apps',[]) if r['id']==app_id),None) or next((r for r in previous_event.get('contributors',[]) if r['id']==app_id),None)
            if info:
                self._selected_app=dict(info,ramLabel='—',beforeLabel='—',deltaLabel='—',peakLabel='—',series=[],processes=[])
                self._name_labels(self._selected_app)
        self._revision+=1
        self._request_view()
        self.viewChanged.emit()
        self.changed.emit()
    @Slot(str)
    def selectEvent(self, event_id):
        event=next((e for e in self._raw.get('markers',[]) if e['id']==event_id),None)
        if event is None:event=next((e for e in self._event_model.rows if e['id']==event_id),None)
        if event is None: return
        self._selected_event=self._format_event(event)
        self._app_id=''
        self._manual_app_selection=False
        self._selected_app={}
        self._follow=False
        self._end=event['timestamp']
        self._range=max(300,min(86400,int(event['timestamp']-event['startedAt'])+18))
        self.readRequested.emit(event_id)
        self._selection_changed()

    @Slot(str)
    def inspectEvent(self, event_id):
        """Inspect and mark read without changing the inline app or live range."""
        event=next((e for e in self._raw.get('markers',[]) if e['id']==event_id),None)
        if event is None:event=next((e for e in self._event_model.rows if e['id']==event_id),None)
        if event is None:return
        self._selected_event=self._format_event(event)
        self.readRequested.emit(event_id)
        self.viewChanged.emit()

    @Slot()
    def closeEventInspection(self):
        self._selected_event={}
        self.viewChanged.emit()

    @Slot()
    def jumpToInspectedEvent(self):
        if self._selected_event:self.selectEvent(self._selected_event['id'])
    @Slot()
    def closeDetails(self):
        self._selected_event={}
        self.selectApp('')
    @Slot()
    def markAllRead(self): self.readRequested.emit('')
    @Slot(int)
    def changeEventPage(self, direction):
        offset=self._event_offset+direction*200
        if offset<0 or offset>=self.eventTotal:return
        self._event_offset=offset;self._revision+=1
        self._request_view()
        self.changed.emit()

    def _name_labels(self, item):
        from .app_names import UNKNOWN, SYSTEM_NAMES
        process_name=item.get('processName') or item.get('name','')
        unknown=UNKNOWN.fullmatch(process_name)
        item['processName']=process_name
        item['nameUnavailable']=bool(unknown and not item.get('displayName'))
        system_name=SYSTEM_NAMES.get(process_name.casefold())
        item['displayName']=tr(system_name) if system_name and item.get('nameSource') in (None,'system_name') else item.get('displayName') or (tr('Unidentified app')+' (PID '+unknown[1]+')' if unknown else process_name)
        item['nameDetail']=tr('The app name was unavailable when this reading was recorded.') if item['nameUnavailable'] else process_name if process_name!=item['displayName'] else ''
        return item

    def _format_event(self, raw):
        event=dict(raw)
        titles={'spike':'RAM increased quickly','growth':'App memory kept increasing','high':'High RAM usage continued','optimize':'Optimization'}
        contributors=[self._name_labels(dict(c,deltaLabel=amount(c['delta'],True))) for c in event.get('contributors',[])]
        event.update(title=tr(titles[event['kind']]),timeLabel=clock(event['timestamp']),contributors=contributors,
            detail=(event.get('mode','')+' · '+tr(event.get('source','').title())) if event['kind']=='optimize' else f"{event.get('percent',0):.1f}%" if event['kind']=='high' else amount(event.get('before'))+' → '+amount(event.get('after')))
        return event
    @Slot(str)
    def setSearch(self, text): self._search=text.casefold(); self._present()
    @Slot(str)
    def setSort(self, value):
        if value in ('growth','ram','name'): self._sort=value; self._order=[]; self._present()
    @Slot()
    def refreshRanking(self): self._order=[]; self._present()
    @Slot()
    def pauseTracking(self):
        self._tracking=False
        self.changed.emit()
    @Slot()
    def resumeTracking(self):
        self._tracking=True
        self._generation+=1
        # Advance storage generation without clearing the user's history.
        self.storage_generationRequested.emit(self._generation)
        self._last_collect=0
        self._system=[]
        self._sample()
        self.changed.emit()
    storage_generationRequested = Signal(int)
    @Slot()
    def clearHistory(self):
        self._generation+=1
        self._revision+=1
        self._system=[]
        self._raw={}; self._series=[]; self._order=[]; self._unread=0
        self._app_id=''; self._selected_app={}; self._selected_event={}
        self._manual_app_selection=False
        self._last_sample=self._last_collect=0
        self._follow=True;self._end=0
        self._event_offset=0
        self.clearRequested.emit(self._generation)
        self._present()
        self._sample()
    @Slot()
    def retryStorage(self): self.retryRequested.emit(); self._request_view()
    @Slot()
    def openTaskManager(self):
        import subprocess
        subprocess.Popen([str(Path(os.environ.get('WINDIR','C:/Windows'))/'System32'/'Taskmgr.exe')])
    @Slot()
    def _memory_closing(self):
        if self.memory.closing: self.requestClose()
    @Slot()
    def requestClose(self):
        if self._closing: return
        self._closing=True
        self._tracking=False
        self.stopCollector.emit()
        self.changed.emit()
    @Slot()
    def _collector_finished(self):
        self._collector_done=True
        if self._closing:
            if self._system:
                segment=self._segment
                previous=self._last_sample
                for sample in self._system:
                    if previous and (sample['timestamp']-previous>4.5 or sample['timestamp']<=previous):segment=uuid.uuid4().hex
                    sample['segment']=segment;previous=sample['timestamp']
                self.writeRequested.emit(dict(system=self._system,events=[],segment=segment,generation=self._generation))
                self._system=[]
            self.stopStore.emit()
    @Slot()
    def _store_finished(self):
        self._store_done=True
        self.changed.emit()
        if self._collector_done: self.closeReady.emit()
    def shutdown(self):
        if self.collector_thread.isRunning():
            self.stopCollector.emit(); self.collector_thread.wait()
        if self.store_thread.isRunning():
            self.stopStore.emit(); self.store_thread.wait()
        self._collector_done=self._store_done=True
