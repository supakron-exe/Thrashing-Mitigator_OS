import ctypes
from ctypes import wintypes as W
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from qa_support import QA_ROOT, qa_path
from backend.insights.app_names import AppNameResolver
from backend.insights.collector import ProcessCollector
from backend.insights.controller import InsightsController
from backend.insights.store import HistoryStore


class NameTests(unittest.TestCase):
    def test_names_use_file_metadata_and_cache_by_path_not_basename(self):
        resolver=AppNameResolver()
        with patch.object(resolver,'_description',side_effect=[('Visual Studio Code','file_description'),('Other editor','file_description')]) as read:
            first=resolver.resolve('Code.exe',r'C:\Editor\Code.exe')
            second=resolver.resolve('Code.exe',r'c:\editor\code.exe')
            other=resolver.resolve('Code.exe',r'C:\Other\Code.exe')
        self.assertEqual(first['displayName'],'Visual Studio Code')
        self.assertEqual(first,second)
        self.assertEqual(first['processName'],'Code.exe')
        self.assertEqual(other['displayName'],'Other editor')
        self.assertEqual(read.call_count,2)

    def test_unreadable_description_falls_back_to_verified_process_name(self):
        resolver=AppNameResolver()
        with patch.object(resolver,'_description',return_value=('','')):
            self.assertEqual(resolver.resolve('custom.exe',r'C:\custom.exe')['displayName'],'custom.exe')
        self.assertEqual(resolver.resolve('MemCompression')['displayName'],'Windows memory compression')
        self.assertEqual(resolver.resolve('Process 4164')['nameSource'],'unavailable')

    def test_presentation_is_honest_about_unknown_names_and_keeps_executable(self):
        named=InsightsController._name_labels(None,dict(name='Code.exe',displayName='Visual Studio Code'))
        self.assertEqual(named['nameDetail'],'Code.exe')
        unknown=InsightsController._name_labels(None,dict(name='Process 4164'))
        self.assertEqual(unknown['displayName'],'Unidentified app (PID 4164)')
        self.assertTrue(unknown['nameUnavailable'])
        self.assertIn('unavailable',unknown['nameDetail'])

    def test_retry_improves_name_without_changing_identity_or_ram(self):
        class Reader:
            name='Process 7'
            def open(self,pid):return pid
            def close(self,handle):pass
            def read(self,handle,pid):return 100,123456
            def metadata(self,handle,pid):return self.name,'',None
        collector=ProcessCollector();collector.reader=Reader()
        snapshot=dict(timestamp=time.time(),used=1,total=10,percent=10)
        with patch('backend.insights.collector.psutil.pids',return_value=[7]):
            original=collector.collect(snapshot)['groups'][0]
            collector.reader.name='MemCompression'
            collector.metadata_retry[(7,100)]=0
            updated=collector.collect(snapshot)['groups'][0]
        self.assertEqual(updated['id'],original['id'])
        self.assertEqual(updated['rss'],original['rss'])
        self.assertEqual(updated['displayName'],'Windows memory compression')

    @unittest.skipUnless(sys.platform=='win32','Windows names')
    def test_real_binary_description_and_process_table_fallback(self):
        from backend.insights.windows_reader import WindowsReader
        resolver=AppNameResolver()
        self.assertTrue(resolver.resolve('python.exe',sys.executable)['displayName'])
        reader=WindowsReader();handle=reader.open(os.getpid())
        try:
            with patch.object(reader.kernel,'QueryFullProcessImageNameW',return_value=False):
                name,exe,owner=reader.metadata(handle,os.getpid())
            self.assertNotEqual(name,f'Process {os.getpid()}')
            self.assertEqual(exe,'')
            with patch.object(reader.kernel,'QueryFullProcessImageNameW',return_value=False), patch('backend.insights.windows_reader.psutil.Process') as process:
                process.return_value.name.return_value='wrong.exe'
                process.return_value.create_time.return_value=0
                name,_,_=reader.metadata(handle,os.getpid())
            self.assertEqual(name,f'Process {os.getpid()}')
        finally:reader.close(handle)


class NameHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'history.db'
        self.store=HistoryStore(self.path)
        self.now=time.time()
    def tearDown(self):
        self.store.close();self.temp.cleanup()
    def write(self,key,name,born,at=None,**metadata):
        timestamp=self.now if at is None else at
        group=dict(id=key,name=name,rss=123456,count=1,complete=True,processes=[dict(pid=4164,born=born,rss=123456)],**metadata)
        self.store.write(dict(segment='test',system=[],batch=dict(timestamp=timestamp,segment='test',groups=[group]),events=[]))

    def test_descriptive_name_survives_rollup_and_restart_without_storing_path(self):
        at=self.now-3600
        self.write('app','Code.exe',100,at,displayName='Visual Studio Code',processName='Code.exe',nameSource='file_description')
        self.store.flush(self.now);self.store.close();self.store=HistoryStore(self.path)
        row=self.store.query(at-1,at+1)['apps'][0]
        self.assertEqual(row['displayName'],'Visual Studio Code')
        self.assertEqual(row['processName'],'Code.exe')
        self.assertEqual(row['bytes'],123456)
        self.assertNotIn('path',{r[1] for r in self.store.db.execute('PRAGMA table_info(app_identity)')})

    def test_old_unknown_identity_is_named_only_for_matching_creation_time(self):
        at=self.now-60
        self.write('old','Process 4164',100,at)
        self.write('reused','Process 4164',200,at)
        self.write('new','MemCompression',100,self.now,displayName='Windows memory compression',processName='MemCompression',nameSource='system_name')
        rows={r['id']:r for r in self.store.query(at-1,self.now+1)['apps']}
        self.assertEqual(rows['old']['displayName'],'Windows memory compression')
        self.assertNotIn('displayName',rows['reused'])
        self.assertEqual(rows['old']['bytes'],123456)

    def test_old_rolled_up_unknown_name_is_resolved_and_clear_removes_names(self):
        at=self.now-3600
        self.write('old','Process 4164',100,at)
        self.store.flush(self.now)
        self.write('new','MemCompression',100,displayName='Windows memory compression',processName='MemCompression',nameSource='system_name')
        self.assertEqual(self.store.query(at-1,at+1)['apps'][0]['displayName'],'Windows memory compression')
        self.store.clear()
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM app_identity').fetchone()[0],0)

    def test_startup_recovery_checks_creation_time_before_and_after_name_lookup(self):
        self.write('old','Process 4164',100,self.now-60)
        with patch('psutil.Process') as process:
            process.return_value.create_time.side_effect=[100,200]
            process.return_value.name.return_value='MemCompression'
            process.return_value.exe.return_value=''
            self.store.resolve_recorded_names()
        self.assertNotIn('displayName',self.store.query(self.now-120,self.now)['apps'][0])
        with patch('psutil.Process') as process:
            process.return_value.create_time.return_value=100
            process.return_value.name.return_value='MemCompression'
            process.return_value.exe.return_value=''
            self.store.resolve_recorded_names()
        self.assertEqual(self.store.query(self.now-120,self.now)['apps'][0]['displayName'],'Windows memory compression')


if __name__=='__main__':unittest.main()
