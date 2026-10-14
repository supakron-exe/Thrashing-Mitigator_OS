import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from qa_support import QA_ROOT, qa_path
from PySide6.QtCore import QCoreApplication, QPersistentModelIndex
from backend.insights.events import EventDetector
from backend.insights.store import HistoryStore
from backend.insights.collector import ProcessCollector
from backend.insights.controller import InsightsController, StoreWorker, amount
from backend.controller import MemoryController
from backend.insights.models import RowModel

APP=QCoreApplication.instance() or QCoreApplication([])
MIB=1024**2


def batch(t, growth=0, used=3*1024*MIB, percent=30, segment='a', born=1, complete=True):
    return dict(timestamp=t,segment=segment,complete=True,readable=1,denied=0,duration=.01,
        snapshot=dict(timestamp=t,used=used,total=10*1024*MIB,percent=percent),
        groups=[dict(id='app',name='example.exe',rss=100*MIB+growth,count=1,complete=complete,
                     processes=[dict(pid=7,born=born,rss=100*MIB+growth)])])


def pump(predicate, timeout=5):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        APP.processEvents()
        if predicate(): return
        time.sleep(.002)
    raise AssertionError('Qt condition did not finish')


class EventTests(unittest.TestCase):
    def test_stable_and_temporary_spike_do_not_report_growth(self):
        detector=EventDetector();events=[]
        for t in range(0,420,6): events.extend(detector.feed(batch(t,used=(6 if t==300 else 3)*1024*MIB)))
        self.assertEqual(events,[])

    def test_continuous_growth_has_evidence_and_deduplicates(self):
        detector=EventDetector();events=[]
        for t in range(0,600,6): events.extend(detector.feed(batch(t,growth=t*2*MIB,used=3*1024*MIB+t*2*MIB)))
        self.assertEqual(len({e['id'] for e in events if e['kind']=='growth'}),1)
        self.assertEqual(len({e['id'] for e in events if e['kind']=='spike'}),1)
        self.assertGreater(events[0]['contributors'][0]['delta'],256*MIB)
        growth=[e for e in events if e['kind']=='growth']
        self.assertEqual(growth[0]['after'],growth[-1]['after'])
        self.assertGreater(growth[-1]['peak'],growth[0]['peak'])

    def test_new_process_and_pid_reuse_are_not_continuous_growth(self):
        detector=EventDetector();events=[]
        for t in range(0,420,6): events.extend(detector.feed(batch(t,growth=t*2*MIB,born=1 if t<200 else 2)))
        self.assertFalse(any(e['kind']=='growth' for e in events))

    def test_gap_partial_reading_and_optimization_restart_baseline(self):
        for variant in ('gap','partial','optimize'):
            detector=EventDetector();events=[]
            for t in range(0,420,6):
                b=batch(t,growth=t*2*MIB,segment='a' if t<200 or variant!='gap' else 'b',complete=t<200 or variant!='partial')
                events.extend(detector.feed(b,suppress=variant=='optimize' and t>=200))
            self.assertFalse(any(e['kind']=='growth' for e in events),variant)

    def test_high_usage_needs_sustained_readings_and_rearms(self):
        d=EventDetector();events=[]
        for t in range(0,42,6):events.extend(d.feed(batch(t,percent=90)))
        self.assertEqual(len({e['id'] for e in events if e['kind']=='high'}),1)
        for t in range(42,132,6):events.extend(d.feed(batch(t,percent=70)))
        for t in range(132,174,6):events.extend(d.feed(batch(t,percent=90)))
        # Same-type events remain deduplicated for ten minutes.
        self.assertEqual(len({e['id'] for e in events if e['kind']=='high'}),1)


class ModelTests(unittest.TestCase):
    def test_existing_row_identity_survives_insert_remove_and_reorder(self):
        model=RowModel();resets=[]
        model.modelReset.connect(lambda:resets.append(True))
        model.update([dict(id='a',value=1),dict(id='b',value=2)])
        retained=QPersistentModelIndex(model.index(1))
        model.update([dict(id='a',value=3),dict(id='b',value=4),dict(id='c',value=5)])
        self.assertTrue(retained.isValid())
        model.update([dict(id='c',value=6),dict(id='b',value=7)])
        self.assertEqual(retained.data(model.RowRole)['id'],'b')
        self.assertEqual(retained.data(model.RowRole)['value'],7)
        self.assertEqual(resets,[])


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'insights.db'
        self.store=HistoryStore(self.path)
        self.now=time.time()
    def tearDown(self):self.store.close();self.temp.cleanup()
    def write(self,b,events=None):self.store.write(dict(batch=b,system=[b['snapshot']],events=events or [],segment=b['segment']))

    def test_restart_rollup_retains_peaks_endpoints_and_unread(self):
        t=self.now-3600
        values=[100*MIB,900*MIB,200*MIB]
        for i,value in enumerate(values):
            b=batch(t+i*6,growth=value-100*MIB)
            b['snapshot']['percent']=[20,90,30][i]
            self.write(b)
        event=dict(id='event',timestamp=t+12,startedAt=t,kind='spike',contributors=[])
        self.write(batch(t+12,growth=100*MIB),[event])
        self.store.flush(self.now)
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM apps').fetchone()[0],0)
        self.store.close();self.store=HistoryStore(self.path)
        data=self.store.query(t-1,t+30,'app')
        self.assertEqual(data['apps'][0]['peak'],900*MIB)
        self.assertEqual(data['apps'][0]['delta'],100*MIB)
        self.assertEqual(max(p['percent'] for p in data['series']),90)
        self.assertEqual(data['unread'],1)
        self.store.mark_read('event')
        self.store.close();self.store=HistoryStore(self.path)
        self.assertEqual(self.store.query(t-1,t+30)['unread'],0)

    def test_retention_gap_and_partial_data_do_not_make_fake_delta(self):
        self.write(batch(self.now-90000))
        self.write(batch(self.now-60))
        self.write(batch(self.now,segment='resumed',complete=False))
        self.store.flush(self.now)
        data=self.store.query(self.now-100000,self.now+1)
        self.assertEqual(len(data['series']),2)
        self.assertIsNone(data['apps'][0]['delta'])
        self.assertIsNone(data['apps'][0]['bytes'])

    def test_complete_endpoints_remain_comparable_across_restart_segments(self):
        self.write(batch(self.now-60,growth=10*MIB))
        self.write(batch(self.now,growth=30*MIB,segment='restarted'))
        row=self.store.query(self.now-120,self.now+1)['apps'][0]
        self.assertEqual(row['delta'],20*MIB)
        self.assertTrue(row['comparable'])
        self.assertTrue(row['hasGaps'])
        self.assertFalse(row['stale'])

    def test_partial_middle_preserves_endpoints_but_partial_endpoint_does_not(self):
        self.write(batch(self.now-60,growth=10*MIB))
        self.write(batch(self.now-30,growth=900*MIB,complete=False))
        self.write(batch(self.now,growth=30*MIB))
        row=self.store.query(self.now-120,self.now+1)['apps'][0]
        self.assertFalse(row['complete'])
        self.assertTrue(row['hasPartialReadings'])
        self.assertTrue(row['comparable'])
        self.assertEqual(row['delta'],20*MIB)
        self.write(batch(self.now,growth=30*MIB,segment='restarted',complete=False))
        row=self.store.query(self.now-120,self.now+1)['apps'][0]
        self.assertFalse(row['comparable'])
        self.assertIsNone(row['bytes'])
        self.assertIsNone(row['delta'])
        self.write(batch(self.now,growth=30*MIB))
        self.write(batch(self.now-60,growth=10*MIB,complete=False))
        row=self.store.query(self.now-120,self.now+1)['apps'][0]
        self.assertIsNone(row['before'])
        self.assertIsNone(row['delta'])

    def test_old_identity_is_stale_without_inventing_a_closed_process(self):
        self.write(batch(self.now-66,growth=10*MIB))
        self.write(batch(self.now-60,growth=20*MIB))
        latest=batch(self.now)
        latest['groups'][0]['id']='fresh'
        self.write(latest)
        rows={r['id']:r for r in self.store.query(self.now-120,self.now+1)['apps']}
        self.assertTrue(rows['app']['stale'])
        self.assertFalse(rows['app']['closed'])
        self.assertEqual(rows['app']['bytes'],120*MIB)
        self.assertFalse(rows['fresh']['stale'])
        old=self.store.query(self.now-120,self.now-30)['apps'][0]
        self.assertFalse(old['stale'])

    def test_rollup_gap_and_partial_middle_bucket_preserve_valid_endpoint_buckets(self):
        t=int((self.now-3600)//60)*60
        self.write(batch(t+6,growth=10*MIB))
        self.write(batch(t+66,growth=900*MIB,complete=False))
        self.write(batch(t+126,growth=30*MIB,segment='restarted'))
        self.store.flush(self.now)
        row=self.store.query(t,t+180)['apps'][0]
        self.assertTrue(row['hasPartialReadings'])
        self.assertTrue(row['hasGaps'])
        self.assertTrue(row['comparable'])
        self.assertEqual(row['delta'],20*MIB)

    def test_historical_selection_never_uses_future_samples(self):
        self.write(batch(self.now-60,growth=10*MIB))
        self.write(batch(self.now,growth=500*MIB))
        old=self.store.query(self.now-120,self.now-30)
        self.assertEqual(old['apps'][0]['bytes'],110*MIB)

    def test_clear_removes_events_samples_and_read_state(self):
        self.write(batch(self.now),[dict(id='a',timestamp=self.now,kind='high')])
        self.store.clear()
        data=self.store.query(self.now-60,self.now+1)
        self.assertEqual((data['series'],data['apps'],data['events'],data['unread']),([],[],[],0))

    def test_corrupt_history_is_preserved_and_recovered(self):
        self.store.close()
        self.path.write_bytes(b'broken sqlite history')
        self.store=HistoryStore(self.path)
        self.assertTrue(self.store.recovery)
        self.assertEqual((self.path.parent/self.store.recovery).read_bytes(),b'broken sqlite history')

    def test_partial_minute_does_not_leak_future_values(self):
        t=int((self.now-3600)//60)*60
        self.write(batch(t+6,growth=10*MIB))
        self.write(batch(t+54,growth=800*MIB))
        self.store.flush(self.now)
        before=self.store.query(t,t+30,'app')
        self.assertEqual((before['apps'],before['series'],before['details']),([],[],[]))
        covered=self.store.query(t,t+60,'app')
        self.assertEqual(covered['apps'][0]['bytes'],900*MIB)

    def test_event_paging_counts_the_full_range(self):
        events=[dict(id=str(i),timestamp=self.now-i,startedAt=self.now-i,kind='high',contributors=[]) for i in range(250)]
        self.write(batch(self.now),events)
        first=self.store.query(self.now-300,self.now+1)
        second=self.store.query(self.now-300,self.now+1,event_offset=200)
        self.assertEqual((len(first['events']),len(second['events']),first['eventCount']),(200,50,250))
        self.assertFalse({e['id'] for e in first['events']} & {e['id'] for e in second['events']})

    def test_late_samples_merge_with_existing_minute_and_preserve_peak(self):
        t=int((self.now-3600)//60)*60
        self.write(batch(t+6,growth=800*MIB));self.store.flush(self.now)
        self.write(batch(t+54,growth=200*MIB));self.store.flush(self.now)
        data=self.store.query(t,t+60)
        self.assertEqual(data['apps'][0]['peak'],900*MIB)
        self.assertEqual(data['apps'][0]['bytes'],300*MIB)
        self.assertEqual(data['apps'][0]['delta'],-600*MIB)


@unittest.skipUnless(sys.platform=='win32','Windows query handles')
class WindowsReaderTests(unittest.TestCase):
    def test_own_process_uses_same_working_set_and_creation_identity(self):
        import os
        import psutil
        from backend.insights.windows_reader import WindowsReader
        reader=WindowsReader();handle=reader.open(os.getpid())
        try:
            born,rss=reader.read(handle,os.getpid())
            process=psutil.Process()
            self.assertLess(abs(born-process.create_time()),.1)
            self.assertLess(abs(rss-process.memory_info().rss),16*MIB)
            name,exe,owner=reader.metadata(handle,os.getpid())
            self.assertTrue(name and exe and owner)
        finally:reader.close(handle)


class CollectorIdentityTests(unittest.TestCase):
    def test_unknown_owner_fallback_survives_restart_and_does_not_merge_names_or_pid_reuse(self):
        class Reader:
            def __init__(self,born=100):self.born=born
            def open(self,pid):return pid
            def close(self,handle):pass
            def read(self,handle,pid):return self.born+pid,100*MIB
            def metadata(self,handle,pid):return 'same.exe','C:/same.exe',None
        snapshot=dict(timestamp=time.time(),used=1,total=10,percent=10)
        with patch('backend.insights.collector.psutil.pids',return_value=[10,11]):
            first,second=ProcessCollector(),ProcessCollector()
            first.reader=Reader();second.reader=Reader()
            original=first.collect(snapshot)['groups']
            reopened=second.collect(snapshot)['groups']
            self.assertEqual({g['id'] for g in original},{g['id'] for g in reopened})
            self.assertEqual(len(original),2)
            second.reader=Reader(200)
            reused=[g for g in second.collect(snapshot)['groups'] if g['count']]
            self.assertFalse({g['id'] for g in original}&{g['id'] for g in reused})


class AmountTests(unittest.TestCase):
    def test_small_measured_changes_do_not_round_to_zero(self):
        self.assertEqual(amount(4096,True),'+4.0 KB')
        self.assertEqual(amount(32,True),'+32 B')
        self.assertEqual(amount(-4096,True),'−4.0 KB')
        self.assertEqual(amount(0,True),'0.0 MB')
        self.assertEqual(amount(None,True),'—')


class StorageFailureTests(unittest.TestCase):
    def test_retry_merges_temporary_readings_with_saved_history(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'insights.db'
            worker=StoreWorker(path);worker.initialize()
            t=time.time()
            def packet(at,growth):
                b=batch(at,growth=growth)
                return dict(batch=b,system=[b['snapshot']],events=[],segment='a',generation=0)
            try:
                worker.write(packet(t-6,10*MIB));worker.flush()
                worker.fail(OSError('Fixture: disk full'))
                worker.write(packet(t,20*MIB))
                self.assertTrue(worker.store.memory_only)
                worker.retry()
                self.assertEqual(worker.error,'')
                data=worker.store.query(t-10,t+1)
                self.assertEqual(data['apps'][0]['delta'],10*MIB)
                self.assertEqual(len(data['series']),2)
            finally:worker.stop()

    def test_clear_in_temporary_mode_also_clears_saved_history(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'insights.db'
            worker=StoreWorker(path);worker.initialize()
            t=time.time();b=batch(t)
            packet=dict(batch=b,system=[b['snapshot']],events=[],segment='a',generation=0)
            try:
                worker.write(packet);worker.flush()
                worker.fail(OSError('Fixture: disk full'));worker.write(packet)
                worker.clear(1)
                self.assertEqual(worker.error,'')
                self.assertFalse(worker.store.memory_only)
                self.assertEqual(worker.store.query(t-60,t+1)['apps'],[])
            finally:worker.stop()


class ControllerTests(unittest.TestCase):
    def test_background_polling_pause_resume_and_clean_shutdown(self):
        class Provider:
            def collect(self,snapshot):
                b=batch(snapshot['timestamp']);b['snapshot']=snapshot;return b
        with tempfile.TemporaryDirectory() as directory:
            memory=MemoryController(refresh_ms=20)
            insights=InsightsController(memory,path=Path(directory)/'insights.db',provider=Provider())
            try:
                pump(lambda:bool(insights.lastSampleAt!='—'))
                insights.setActive(True)
                pump(lambda:insights.appModel.rowCount()==1)
                self.assertEqual(insights.selectedRange,900)
                insights.pauseTracking()
                before=memory.snapshot['timestamp']
                pump(lambda:memory.snapshot['timestamp']>before)
                insights.resumeTracking()
                pump(lambda:insights._last_sample>before)
                insights.clearHistory()
                pump(lambda:insights._last_sample>0 and not insights._querying)
                memory.requestClose()
                pump(lambda:insights.safeToClose)
                self.assertTrue(memory.safeToClose)
            finally:insights.shutdown();memory.shutdown()

    def test_exit_waits_for_collector_and_optimizer(self):
        gate=threading.Event()
        class Provider:
            def collect(self,snapshot):
                gate.wait(3);b=batch(snapshot['timestamp']);b['snapshot']=snapshot;return b
        with tempfile.TemporaryDirectory() as directory:
            def runner(mode,progress):
                gate.wait(3)
                return dict(error='Fixture: insufficient privileges')
            memory=MemoryController(runner=runner,refresh_ms=20)
            insights=InsightsController(memory,path=Path(directory)/'insights.db',provider=Provider())
            try:
                memory.startOptimization()
                self.assertFalse(memory.safeToClose)
                memory.requestClose()
                self.assertFalse(insights.safeToClose)
                gate.set()
                pump(lambda:insights.safeToClose and memory.safeToClose)
            finally:gate.set();insights.shutdown();memory.shutdown()


if __name__=='__main__':unittest.main()
