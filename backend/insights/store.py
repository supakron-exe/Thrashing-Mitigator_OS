import json
import sqlite3
import time
from pathlib import Path
from .aggregation import compact_series


def disk_size(path):
    total=0
    for candidate in (Path(path),Path(str(path)+'-wal')):
        try:
            if candidate.is_file():total+=candidate.stat().st_size
        except OSError:pass
    return total


class HistoryStore:
    def __init__(self, path):
        self.path = Path(path)
        self.memory_only = str(path)==':memory:'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.recovery = ''
        try:
            self.db = sqlite3.connect(self.path, timeout=1)
            check=self.db.execute('PRAGMA quick_check').fetchone()[0]
            if check!='ok': raise sqlite3.DatabaseError('malformed history: '+check)
        except sqlite3.DatabaseError as exc:
            if hasattr(self,'db'): self.db.close()
            if getattr(exc,'sqlite_errorcode',None) not in (sqlite3.SQLITE_CORRUPT,sqlite3.SQLITE_NOTADB) and not any(s in str(exc) for s in ('malformed','not a database')):
                raise
            backup = self.path.with_name(self.path.name + '.corrupt-' + str(time.time_ns()))
            self.path.replace(backup)
            for suffix in ('-wal','-shm'):
                side = Path(str(self.path)+suffix)
                if side.exists(): side.replace(Path(str(backup)+suffix))
            self.recovery = str(backup.name)
            self.db = sqlite3.connect(self.path, timeout=1)
        self.db.row_factory = sqlite3.Row
        version = self.db.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0,1,2):
            self.db.close()
            raise RuntimeError('This history was created by a newer application version.')
        if version==1:
            for table in ('apps','app_minutes'):
                if 'born' not in {row[1] for row in self.db.execute(f'PRAGMA table_info({table})')}:
                    self.db.execute(f'ALTER TABLE {table} ADD COLUMN born REAL')
        self.db.executescript('''
            PRAGMA journal_mode=WAL;
            PRAGMA wal_autocheckpoint=256;
            PRAGMA journal_size_limit=4194304;
            PRAGMA max_page_count=51200;
            CREATE TABLE IF NOT EXISTS system(ts REAL PRIMARY KEY, segment TEXT, percent REAL, used INTEGER, total INTEGER);
            CREATE TABLE IF NOT EXISTS apps(ts REAL, id TEXT, name TEXT, rss INTEGER, count INTEGER, complete INTEGER, segment TEXT, processes TEXT, born REAL, PRIMARY KEY(ts,id));
            CREATE INDEX IF NOT EXISTS apps_id_time ON apps(id,ts);
            CREATE TABLE IF NOT EXISTS system_minutes(bucket INTEGER, segment TEXT, first_ts REAL, last_ts REAL, first REAL, last REAL, low REAL, high REAL, used INTEGER, total INTEGER, n INTEGER, PRIMARY KEY(bucket,segment));
            CREATE TABLE IF NOT EXISTS app_minutes(bucket INTEGER, id TEXT, segment TEXT, name TEXT, first_ts REAL, last_ts REAL, first INTEGER, last INTEGER, low INTEGER, high INTEGER, average REAL, n INTEGER, count INTEGER, complete INTEGER, born REAL, PRIMARY KEY(bucket,id,segment));
            CREATE INDEX IF NOT EXISTS minutes_id_time ON app_minutes(id,bucket);
            CREATE INDEX IF NOT EXISTS minutes_id_first ON app_minutes(id,first_ts);
            CREATE INDEX IF NOT EXISTS minutes_id_last ON app_minutes(id,last_ts);
            CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, ts REAL, kind TEXT, data TEXT, unread INTEGER);
            CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value REAL);
            CREATE TABLE IF NOT EXISTS app_identity(id TEXT PRIMARY KEY,display_name TEXT,process_name TEXT,source TEXT,updated_at REAL);
            CREATE INDEX IF NOT EXISTS apps_unknown_name ON apps(name,born);
            CREATE INDEX IF NOT EXISTS minutes_unknown_name ON app_minutes(name,born);
            PRAGMA user_version=2;
        ''')
        row=self.db.execute("SELECT value FROM metadata WHERE key='savedAt'").fetchone()
        self.saved_at = row[0] if row else 0
        self._identity_seen = {}

    def _write_identity(self, group, timestamp):
        from .app_names import UNKNOWN, clean_name
        process_name=clean_name(group.get('processName',group['name']))
        display_name=clean_name(group.get('displayName'))
        if not display_name or UNKNOWN.fullmatch(process_name):return
        source=group.get('nameSource','process_name')
        value=(display_name,process_name,source)
        self.db.execute('''INSERT INTO app_identity VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
            display_name=excluded.display_name,process_name=excluded.process_name,source=excluded.source,updated_at=MAX(app_identity.updated_at,excluded.updated_at)''',
            (group['id'],*value,timestamp))
        if self._identity_seen.get(group['id'])==value:return
        self._identity_seen[group['id']]=value
        # Upgrade old unnamed records only for the same PID AND creation time.
        # A new process with a reused PID must never rename an old application's history.
        for process in group.get('processes',[]):
            for table in ('apps','app_minutes'):
                self.db.execute(f'''INSERT INTO app_identity
                    SELECT DISTINCT id,?,?,?,? FROM {table} WHERE name=? AND ABS(born-?)<0.00001
                    ON CONFLICT(id) DO UPDATE SET display_name=excluded.display_name,process_name=excluded.process_name,source=excluded.source,updated_at=MAX(app_identity.updated_at,excluded.updated_at)''',
                    (*value,timestamp,f"Process {process['pid']}",process['born']))

    def resolve_recorded_names(self):
        """Recover unnamed history on this worker without changing RAM samples."""
        import psutil
        from .app_names import AppNameResolver, UNKNOWN
        resolver=AppNameResolver()
        records=self.db.execute('''SELECT DISTINCT id,name,born FROM (
            SELECT id,name,born FROM apps UNION SELECT id,name,born FROM app_minutes)
            WHERE name GLOB 'Process [0-9]*' AND born IS NOT NULL
            AND id NOT IN (SELECT id FROM app_identity)''').fetchall()
        for row in records:
            match=UNKNOWN.fullmatch(row['name'])
            if not match:continue
            pid=int(match[1])
            try:
                process=psutil.Process(pid)
                if abs(process.create_time()-row['born'])>=.00001:continue
                name=process.name()
                try:exe=process.exe()
                except (psutil.AccessDenied,psutil.NoSuchProcess,psutil.ZombieProcess):exe=''
                # A fresh object bypasses psutil's cached creation time.
                if abs(psutil.Process(pid).create_time()-row['born'])>=.00001:continue
                info=resolver.resolve(name,exe)
                self._write_identity(dict(id=row['id'],name=name,processes=[dict(pid=pid,born=row['born'])],**info),time.time())
            except (psutil.AccessDenied,psutil.NoSuchProcess,psutil.ZombieProcess):continue

    def write(self, packet):
        batch = packet.get('batch')
        for sample in packet.get('system', []):
            self.db.execute('INSERT OR REPLACE INTO system VALUES(?,?,?,?,?)', (sample['timestamp'],sample.get('segment',packet['segment']),sample['percent'],sample['used'],sample['total']))
        if batch:
            for group in batch['groups']:self._write_identity(group,batch['timestamp'])
            self.db.executemany('INSERT OR REPLACE INTO apps VALUES(?,?,?,?,?,?,?,?,?)',
                [(batch['timestamp'],g['id'],g['name'],g['rss'],g['count'],int(g['complete']),batch['segment'],json.dumps(g['processes'],separators=(',',':')),min((p['born'] for p in g['processes']),default=None)) for g in batch['groups']])
        for event in packet.get('events',[]):
            self.db.execute('INSERT INTO events VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data,ts=excluded.ts',
                            (event['id'],event['timestamp'],event['kind'],json.dumps(event,separators=(',',':')),int(event['kind']!='optimize')))

    def flush(self, now=None):
        now = time.time() if now is None else now
        cutoff = int((now-1800)//60)*60
        # Window functions keep first/last endpoints as well as extrema.
        self.db.execute('''INSERT INTO system_minutes
            SELECT bucket,segment,MIN(ts),MAX(ts),MAX(CASE WHEN a=1 THEN percent END),MAX(CASE WHEN z=1 THEN percent END),MIN(percent),MAX(percent),MAX(CASE WHEN z=1 THEN used END),MAX(total),COUNT(*)
            FROM (SELECT *,CAST(ts/60 AS INTEGER)*60 AS bucket,ROW_NUMBER() OVER(PARTITION BY CAST(ts/60 AS INTEGER),segment ORDER BY ts) a,ROW_NUMBER() OVER(PARTITION BY CAST(ts/60 AS INTEGER),segment ORDER BY ts DESC) z FROM system WHERE ts<?)
            GROUP BY bucket,segment
            ON CONFLICT(bucket,segment) DO UPDATE SET
            first=CASE WHEN excluded.first_ts<system_minutes.first_ts THEN excluded.first ELSE system_minutes.first END,
            last=CASE WHEN excluded.last_ts>system_minutes.last_ts THEN excluded.last ELSE system_minutes.last END,
            used=CASE WHEN excluded.last_ts>system_minutes.last_ts THEN excluded.used ELSE system_minutes.used END,
            first_ts=MIN(system_minutes.first_ts,excluded.first_ts),last_ts=MAX(system_minutes.last_ts,excluded.last_ts),
            low=MIN(system_minutes.low,excluded.low),high=MAX(system_minutes.high,excluded.high),n=system_minutes.n+excluded.n''', (cutoff,))
        self.db.execute('''INSERT INTO app_minutes
            SELECT bucket,id,segment,MAX(name),MIN(ts),MAX(ts),MAX(CASE WHEN a=1 THEN rss END),MAX(CASE WHEN z=1 THEN rss END),MIN(rss),MAX(rss),AVG(rss),COUNT(*),MAX(CASE WHEN z=1 THEN count END),MIN(complete),MAX(CASE WHEN a=1 THEN born END)
            FROM (SELECT *,CAST(ts/60 AS INTEGER)*60 AS bucket,ROW_NUMBER() OVER(PARTITION BY CAST(ts/60 AS INTEGER),id,segment ORDER BY ts) a,ROW_NUMBER() OVER(PARTITION BY CAST(ts/60 AS INTEGER),id,segment ORDER BY ts DESC) z FROM apps WHERE ts<?)
            GROUP BY bucket,id,segment
            ON CONFLICT(bucket,id,segment) DO UPDATE SET
            first=CASE WHEN excluded.first_ts<app_minutes.first_ts THEN excluded.first ELSE app_minutes.first END,
            born=CASE WHEN excluded.first_ts<app_minutes.first_ts THEN excluded.born ELSE app_minutes.born END,
            last=CASE WHEN excluded.last_ts>app_minutes.last_ts THEN excluded.last ELSE app_minutes.last END,
            count=CASE WHEN excluded.last_ts>app_minutes.last_ts THEN excluded.count ELSE app_minutes.count END,
            first_ts=MIN(app_minutes.first_ts,excluded.first_ts),last_ts=MAX(app_minutes.last_ts,excluded.last_ts),
            low=MIN(app_minutes.low,excluded.low),high=MAX(app_minutes.high,excluded.high),
            average=(app_minutes.average*app_minutes.n+excluded.average*excluded.n)/(app_minutes.n+excluded.n),
            n=app_minutes.n+excluded.n,complete=MIN(app_minutes.complete,excluded.complete)''', (cutoff,))
        self.db.execute('DELETE FROM system WHERE ts<?',(cutoff,))
        self.db.execute('DELETE FROM apps WHERE ts<?',(cutoff,))
        for table,col in (('system','ts'),('apps','ts'),('system_minutes','bucket'),('app_minutes','bucket'),('events','ts')):
            self.db.execute(f'DELETE FROM {table} WHERE {col}<?',(now-(1800 if self.memory_only else 86400),))
        self.db.execute("INSERT OR REPLACE INTO metadata VALUES('savedAt',?)",(now,))
        self.db.execute('DELETE FROM app_identity WHERE updated_at<? AND id NOT IN (SELECT id FROM apps UNION SELECT id FROM app_minutes)',(now-86400,))
        self.db.commit()
        self.saved_at = now

    def query(self, start, end, app_id='', event_offset=0):
        points = [dict(timestamp=r['ts'],percent=r['percent'],used=r['used'],total=r['total'],segment=r['segment']) for r in self.db.execute('SELECT * FROM system WHERE ts BETWEEN ? AND ? ORDER BY ts',(start,end))]
        for row in self.db.execute('SELECT * FROM system_minutes WHERE first_ts>=? AND last_ts<=? ORDER BY first_ts',(start,end)):
            # Extrema are an envelope of this minute, not exact instant measurements.
            for t,v in ((row['first_ts'],row['first']),(row['first_ts']+.01,row['low']),(row['last_ts']-.01,row['high']),(row['last_ts'],row['last'])):
                if start<=t<=end: points.append(dict(timestamp=t,percent=v,used=int(v/100*row['total']),total=row['total'],segment=row['segment'],aggregated=True))
        points.sort(key=lambda p:p['timestamp'])
        sql = '''WITH source AS (
            SELECT ts first_ts,ts last_ts,id,name,rss first,rss last,rss high,count,complete,segment,1 n,born FROM apps WHERE ts BETWEEN ? AND ?
            UNION ALL SELECT first_ts,last_ts,id,name,first,last,high,count,complete,segment,n,born FROM app_minutes WHERE first_ts>=? AND last_ts<=?
        ) SELECT id,MAX(name) name,MIN(first_ts) firstAt,MAX(last_ts) lastAt,MAX(high) peak,MIN(complete) complete,COUNT(DISTINCT segment) segments,SUM(n) n FROM source GROUP BY id'''
        apps=[]
        identities={row['id']:dict(displayName=row['display_name'],processName=row['process_name'],nameSource=row['source']) for row in self.db.execute('SELECT * FROM app_identity')}
        summaries=self.db.execute(sql,(start,end,start,end)).fetchall()
        latest_process_sample=max((row['lastAt'] for row in summaries),default=0)
        for row in summaries:
            item=dict(row)
            item.update(identities.get(item['id'],{}))
            key=item['id']
            first=self.db.execute('SELECT rss,segment,born,complete FROM apps WHERE id=? AND ts=? UNION ALL SELECT first,segment,born,complete FROM app_minutes WHERE id=? AND first_ts=? LIMIT 1',(key,item['firstAt'],key,item['firstAt'])).fetchone()
            last=self.db.execute('SELECT rss,count,segment,complete FROM apps WHERE id=? AND ts=? UNION ALL SELECT last,count,segment,complete FROM app_minutes WHERE id=? AND last_ts=? LIMIT 1',(key,item['lastAt'],key,item['lastAt'])).fetchone()
            item.update(before=first['rss'] if first['complete'] else None,bytes=last['rss'] if last['complete'] else None,count=last['count'],born=first['born'],firstSegment=first['segment'],lastSegment=last['segment'])
            # Net change compares observed endpoints. A restart or an unreadable
            # middle sample leaves a graph gap, not an invented endpoint value.
            item['comparable']=bool(item['n']>1 and item['firstAt']<item['lastAt'] and
                                    item['before'] is not None and item['bytes'] is not None)
            item['delta'] = item['bytes']-item['before'] if item['comparable'] else None
            item['hasGaps']=item['segments']>1
            item['hasPartialReadings']=not bool(item['complete'])
            item['stale']=item['lastAt']<latest_process_sample-18
            item['closed']=item['count']==0 and bool(last['complete'])
            observed_start=points[0]['timestamp'] if points else start
            item['new']=item['born'] is not None and item['born']>observed_start
            spark=[dict(timestamp=r['ts'],percent=r['rss'],segment=r['segment'],complete=bool(r['complete'])) for r in self.db.execute('SELECT ts,rss,segment,complete FROM apps WHERE id=? AND ts BETWEEN ? AND ? ORDER BY ts DESC LIMIT 12',(key,start,end))]
            if len(spark)<12:
                spark.extend(dict(timestamp=r['last_ts'],percent=r['last'],segment=r['segment'],complete=bool(r['complete'])) for r in self.db.execute('SELECT last_ts,last,segment,complete FROM app_minutes WHERE id=? AND first_ts>=? AND last_ts<=? ORDER BY last_ts DESC LIMIT ?',(key,start,end,12-len(spark))))
            item['sparkline']=sorted(spark,key=lambda p:p['timestamp'])
            apps.append(item)
        events=[]
        event_filter="(ts BETWEEN ? AND ? OR (kind='optimize' AND ts>=? AND json_extract(data,'$.startedAt')<=?))"
        event_args=(start,end,start,end)
        for row in self.db.execute('SELECT * FROM events WHERE '+event_filter+' ORDER BY ts DESC LIMIT 200 OFFSET ?',event_args+(event_offset,)):
            event=json.loads(row['data']); event['unread']=bool(row['unread']); events.append(event)
        markers=[]
        for row in self.db.execute('SELECT * FROM events WHERE '+event_filter+' ORDER BY ts DESC LIMIT 1000',event_args):
            event=json.loads(row['data']);event['unread']=bool(row['unread']);markers.append(event)
        details=[]
        for event in events+markers:
            for contributor in event.get('contributors',[]):contributor.update(identities.get(contributor['id'],{}))
        processes=[]
        if app_id:
            for row in self.db.execute('SELECT * FROM apps WHERE id=? AND ts BETWEEN ? AND ? ORDER BY ts',(app_id,start,end)):
                details.append(dict(timestamp=row['ts'],percent=row['rss'],segment=row['segment'],complete=bool(row['complete'])))
                processes=json.loads(row['processes'])
            for row in self.db.execute('SELECT * FROM app_minutes WHERE id=? AND first_ts>=? AND last_ts<=? ORDER BY first_ts',(app_id,start,end)):
                details.extend([dict(timestamp=t,percent=value,segment=row['segment'],complete=bool(row['complete']),aggregated=True) for t,value in ((row['first_ts'],row['first']),(row['first_ts']+.01,row['low']),(row['last_ts']-.01,row['high']),(row['last_ts'],row['last'])) if start<=t<=end])
            details.sort(key=lambda p:p['timestamp'])
        return dict(series=compact_series(points),apps=apps,events=events,markers=markers,details=compact_series(details,300),processes=processes,
                    eventTotal=self.db.execute('SELECT COUNT(*) FROM events WHERE '+event_filter,event_args).fetchone()[0],
                    eventCount=self.db.execute("SELECT COUNT(*) FROM events WHERE kind!='optimize' AND "+event_filter,event_args).fetchone()[0],
                    unread=self.db.execute('SELECT COUNT(*) FROM events WHERE unread=1').fetchone()[0],
                    storedSince=self.db.execute('SELECT MIN(t) FROM (SELECT MIN(ts) t FROM system UNION ALL SELECT MIN(first_ts) t FROM system_minutes)').fetchone()[0],
                    savedAt=0 if self.memory_only else self.saved_at,size=disk_size(self.path),recovery=self.recovery)

    def mark_read(self, event_id=None):
        if event_id: self.db.execute('UPDATE events SET unread=0 WHERE id=?',(event_id,))
        else: self.db.execute('UPDATE events SET unread=0')
        self.db.commit()

    def clear(self):
        for table in ('system','apps','system_minutes','app_minutes','events','app_identity'): self.db.execute(f'DELETE FROM {table}')
        self._identity_seen.clear()
        self.db.execute('DELETE FROM metadata')
        self.db.commit()
        self.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        self.db.execute('VACUUM')
        self.saved_at=0

    def close(self):
        try:
            self.flush()
            self.db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        finally: self.db.close()
