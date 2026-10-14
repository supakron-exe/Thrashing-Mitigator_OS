import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from qa_support import QA_ROOT, qa_path
from PySide6.QtCore import QCoreApplication,QPersistentModelIndex
from backend.controller import MemoryController
from backend.insights.controller import InsightsController
from backend.insights.store import HistoryStore

APP=QCoreApplication.instance() or QCoreApplication([])
MIB=1024**2

def pump(condition):
    end=time.monotonic()+5
    while time.monotonic()<end:
        APP.processEvents()
        if condition():return
        time.sleep(.002)
    raise AssertionError('Controller response timed out')

class EmptyProvider:
    def collect(self,snapshot):
        return dict(timestamp=snapshot['timestamp'],snapshot=snapshot,groups=[],complete=True,readable=0,denied=0,duration=0,segment='live')

class VisualInsightsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'insights.db'
        self.now=time.time()
        self.memory=None;self.insights=None

    def tearDown(self):
        if self.insights:self.insights.shutdown()
        if self.memory:self.memory.shutdown()
        self.temp.cleanup()

    def seed(self,values,event=False):
        store=HistoryStore(self.path)
        for i in range(2):
            t=self.now-18+i*6
            groups=[]
            for key,before,after,flags in values:
                if flags.get('single') and i==0:continue
                rss=(before if i==0 else after)*MIB
                count=0 if flags.get('closed') and i==1 else 1
                groups.append(dict(id=key,name=key+'.exe',rss=rss,count=count,complete=not(flags.get('partial') and i==1),processes=[dict(pid=10+len(groups),born=self.now-15 if flags.get('new') else self.now-7200,rss=rss)] if count else []))
            system=dict(timestamp=t,percent=40,used=4*1024*MIB,total=10*1024*MIB)
            store.write(dict(system=[system],batch=dict(timestamp=t,segment='test',groups=groups),events=[],segment='test'))
        if event:
            store.write(dict(system=[],events=[dict(id='growth-event',kind='growth',timestamp=self.now-12,startedAt=self.now-312,before=100*MIB,after=500*MIB,segment='test',contributors=[])],segment='test'))
        store.close()
        self.memory=MemoryController(refresh_ms=1000)
        self.insights=InsightsController(self.memory,path=self.path,provider=EmptyProvider())
        self.insights.pauseTracking();self.insights.setActive(True)
        pump(lambda:bool(self.insights.selectedApp.get('series')))

    def test_ranking_excludes_missing_baselines_and_table_filter_is_independent(self):
        self.seed([('a',100,200,{}),('b',100,150,{}),('new',100,500,{'new':True}),('partial',100,800,{'partial':True}),('closed',100,0,{'closed':True}),('single',100,900,{'single':True}),('decreased',300,200,{})])
        self.assertEqual([r['id'] for r in self.insights.visualRanking.rows],['new','a','b'])
        self.assertEqual(self.insights.selectedApp['id'],'new')
        self.assertTrue(self.insights.selectedApp['new'])
        self.assertTrue(self.insights.selectedApp['observedSpanLabel'])
        self.insights.setSearch('no matching app')
        self.assertEqual(self.insights.appModel.rowCount(),0)
        self.assertEqual(self.insights.visualRanking.rowCount(),3)
        self.assertEqual(self.insights.selectedApp['id'],'new')
        self.insights.setSort('ram')
        self.assertEqual(self.insights.visualRanking.rows[0]['id'],'new')

    def test_steady_or_decreasing_apps_show_an_honest_fallback(self):
        self.seed([('steady',500,500,{}),('decreased',400,100,{})])
        self.assertEqual(self.insights.visualRanking.rowCount(),0)
        self.assertTrue(self.insights.visualSummary['fallback'])
        self.assertEqual(self.insights.selectedApp['id'],'steady')
        self.assertEqual(self.insights.selectedApp['delta'],0)

    def test_unavailable_latest_process_read_is_not_reported_as_closed(self):
        self.seed([('a',100,200,{}),('unavailable',100,0,{'partial':True,'closed':True})])
        row=next(r for r in self.insights.appModel.rows if r['id']=='unavailable')
        self.assertFalse(row['closed'])
        self.assertTrue(row['hasPartialReadings'])
        self.assertIsNone(row['delta'])

    def test_event_inspection_keeps_selection_live_and_explicit_jump_changes_range(self):
        self.seed([('a',100,200,{})],event=True)
        period=self.insights.selectedRange
        self.insights.inspectEvent('growth-event')
        self.assertTrue(self.insights.followLive)
        self.assertEqual(self.insights.selectedRange,period)
        self.assertEqual(self.insights.selectedApp['id'],'a')
        pump(lambda:self.insights.unreadCount==0)
        self.insights.closeEventInspection()
        self.assertEqual(self.insights.selectedApp['id'],'a')
        self.insights.inspectEvent('growth-event');self.insights.jumpToInspectedEvent()
        self.assertFalse(self.insights.followLive)

    def test_reordering_preserves_selected_app_and_model_identity(self):
        self.seed([('a',100,200,{}),('b',100,150,{})])
        self.insights.selectApp('b')
        pump(lambda:self.insights.selectedApp.get('id')=='b' and bool(self.insights.selectedApp.get('series')))
        index=QPersistentModelIndex(self.insights.visualRanking.index(1))
        self.insights._raw['apps'][1]['delta']=300*MIB
        self.insights._present()
        self.assertEqual(self.insights.selectedApp['id'],'b')
        self.assertTrue(index.isValid())
        self.assertEqual(index.data(self.insights.visualRanking.RowRole)['id'],'b')

    def test_stale_auto_selection_switches_to_fresh_identity_without_filename_merge(self):
        self.seed([('a',100,200,{}),('b',100,150,{})])
        rows=self.insights._raw['apps']
        rows[0].update(stale=True,name='same.exe')
        rows[1].update(stale=False,name='same.exe')
        self.insights._present()
        self.assertEqual(self.insights.selectedApp['id'],'b')
        self.assertEqual([r['id'] for r in self.insights.visualRanking.rows],['b'])
        self.assertEqual(self.insights.visualSummary['fallbackAppId'],'b')
        self.insights.selectApp('a')
        self.insights._present()
        self.assertEqual(self.insights.selectedApp['id'],'a')
        self.assertTrue(self.insights.selectedApp['stale'])
        self.assertEqual(self.insights.selectedApp['stateLabel'],'Last observed')

    def test_selected_markers_only_contain_identity_matches_and_optimization(self):
        self.seed([('a',100,200,{})])
        self.insights._raw['markers']=[
            dict(id='same',kind='growth',app='a',contributors=[]),
            dict(id='contribution',kind='spike',contributors=[dict(id='a')]),
            dict(id='unrelated',kind='growth',app='b',contributors=[dict(id='b')]),
            dict(id='global',kind='high',contributors=[]),
            dict(id='optimized',kind='optimize',contributors=[])]
        self.assertEqual([e['id'] for e in self.insights.selectedAppMarkers],['same','contribution','optimized'])

    def test_system_net_change_uses_observed_endpoints_across_gaps_and_accepts_zero(self):
        self.seed([('a',100,200,{})])
        self.insights._series=[
            dict(timestamp=self.now-60,segment='before-restart',used=100*MIB),
            dict(timestamp=self.now,segment='after-restart',used=125*MIB)]
        self.insights._present()
        self.assertEqual(self.insights.summary['changeLabel'],'+25.0 MB')
        self.assertTrue(self.insights.summary['systemHasGaps'])
        self.insights._series[-1]['used']=100*MIB
        self.insights._present()
        self.assertEqual(self.insights.summary['changeLabel'],'0.0 MB')
        self.insights._series[-1]['used']=None
        self.insights._present()
        self.assertEqual(self.insights.summary['changeLabel'],'—')

    def test_live_view_reorders_top_five_but_keeps_manual_selection_and_table_order(self):
        self.seed([('a',100,200,{}),('b',100,150,{})])
        self.insights.selectApp('a')
        pump(lambda:bool(self.insights.selectedApp.get('series')))
        at=self.now+6
        groups=[dict(id=key,name=key+'.exe',rss=rss*MIB,count=1,complete=True,
                     processes=[dict(pid=10+i,born=self.now-7200,rss=rss*MIB)])
                for i,(key,rss) in enumerate([('a',210),('b',400)])]
        system=dict(timestamp=at,percent=40,used=4*1024*MIB,total=10*1024*MIB)
        self.insights.writeRequested.emit(dict(system=[system],batch=dict(timestamp=at,segment='test',groups=groups),events=[],segment='test',generation=0))
        self.insights._last_sample=at
        self.insights._request_view()
        pump(lambda:bool(self.insights.visualRanking.rows) and self.insights.visualRanking.rows[0]['id']=='b')
        self.assertEqual(self.insights.selectedApp['id'],'a')
        self.assertEqual(self.insights.selectedApp['delta'],110*MIB)
        self.assertEqual(self.insights.selectedApp['series'][-1]['timestamp'],at)
        self.assertEqual([r['id'] for r in self.insights.appModel.rows],['a','b'])

if __name__=='__main__':unittest.main()
