from collections import deque
from statistics import median
import uuid

MIB = 1024**2


class EventDetector:
    def __init__(self):
        self.reset()

    def reset(self):
        self.history = deque(maxlen=60)
        self.high_since = None
        self.low_since = None
        self.high_armed = True
        self.recent = {}
        self.suppressed = False

    def _event(self, kind, batch, before, contributors, app='', values=None):
        now = batch['timestamp']
        key = (kind, app)
        previous = self.recent.get(key)
        first_value,last_value=values if values is not None else (before['snapshot']['used'],batch['snapshot']['used'])
        if previous and now - previous['timestamp'] < 600:
            if last_value<=previous.get('peak',previous['after']) and now-previous.get('lastSeen',previous['timestamp'])<60:return None
            event=dict(previous,lastSeen=now,peak=max(previous.get('peak',previous['after']),last_value),peakPercent=max(previous.get('peakPercent',previous['percent']),batch['snapshot']['percent']))
            self.recent[key]=event
            return event
        event = dict(id=uuid.uuid4().hex, kind=kind, app=app, timestamp=now,
                     startedAt=before['timestamp'], before=first_value,
                     after=last_value, percent=batch['snapshot']['percent'], contributors=contributors,lastSeen=now,peak=last_value,peakPercent=batch['snapshot']['percent'],
                     segment=batch['segment'])
        self.recent[key] = event
        return event

    def feed(self, batch, suppress=False):
        now, sample = batch['timestamp'], batch['snapshot']
        events = []
        if self.history and (batch['segment'] != self.history[-1]['segment'] or now-self.history[-1]['timestamp'] > 18 or now <= self.history[-1]['timestamp']):
            self.reset()
        if sample['percent'] >= 85:
            self.high_since = self.high_since if self.high_since is not None else now
            self.low_since = None
            if self.high_armed and now-self.high_since >= 30:
                event = self._event('high', batch, batch, [])
                if event:
                    event['startedAt']=self.high_since
                    events.append(event)
                self.high_armed = False
            elif not self.high_armed and ('high','') in self.recent:
                previous=self.recent[('high','')]
                if now-previous.get('lastSeen',previous['timestamp'])>=60 or sample['percent']>=previous.get('peakPercent',previous['percent'])+1:
                    event=dict(previous,lastSeen=now,peak=max(previous.get('peak',previous['after']),sample['used']),peakPercent=max(previous.get('peakPercent',previous['percent']),sample['percent']))
                    self.recent[('high','')]=event;events.append(event)
        else:
            self.high_since = None
            if sample['percent'] < 80:
                self.low_since = self.low_since if self.low_since is not None else now
                if now-self.low_since >= 60: self.high_armed = True
            else: self.low_since = None
        if suppress or not batch['complete']:
            self.history.clear()
            return events
        self.history.append(batch)
        history = list(self.history)
        if len(history) < 51 or now-history[0]['timestamp'] < 300:
            return events
        baseline = [b for b in history if now-318 <= b['timestamp'] <= now-300]
        ending = [b for b in history if b['timestamp'] >= now-18]
        if len(baseline)<3 or len(ending) < 3: return events
        base_indices=[i for i,b in enumerate(history) if now-318<=b['timestamp']<=now-300]
        end_indices=[i for i,b in enumerate(history) if b['timestamp']>=now-18]
        base_used = median(b['snapshot']['used'] for b in baseline)
        end_used = median(b['snapshot']['used'] for b in ending)
        contributions = []
        lookup = [{g['id']: g for g in b['groups']} for b in history]
        for key in lookup[-1]:
            samples = [items.get(key) for items in lookup]
            if not all(g is not None and g['complete'] for g in samples): continue
            # Compare the same processes, not RAM from newly opened children.
            common = set((p['pid'], p['born']) for p in samples[0]['processes'])
            for group in samples:
                common.intersection_update((p['pid'], p['born']) for p in group['processes'])
            if not common: continue
            values = [sum(p['rss'] for p in g['processes'] if (p['pid'],p['born']) in common) for g in samples]
            base = median(values[i] for i in base_indices)
            end = median(values[i] for i in end_indices)
            delta = end-base
            if delta > 0:
                contributions.append(dict(id=key,name=samples[-1]['name'],delta=delta))
            minute_values = [values[min(range(len(history)), key=lambda i:abs(history[i]['timestamp']-(now-300+60*j)))] for j in range(6)]
            rises = sum(b>a for a,b in zip(minute_values,minute_values[1:]))
            if delta >= max(256*MIB, base*.2) and rises >= 4:
                event = self._event('growth', batch, baseline[0], [dict(id=key,name=samples[-1]['name'],delta=delta)], key,values=(base,end))
                if event:
                    events.append(event)
        contributions.sort(key=lambda row:row['delta'], reverse=True)
        if end_used-base_used >= max(512*MIB, sample['total']*.05) and all(b['snapshot']['used']-base_used >= max(512*MIB,sample['total']*.05) for b in ending):
            event = self._event('spike', batch, baseline[0], contributions[:3],values=(base_used,end_used))
            if event:
                events.append(event)
        return events
