import json
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from qa_support import QA_ROOT, qa_path
from PySide6.QtCore import QCoreApplication, QTranslator
from backend.settings import SettingsController
from backend.localization import display_text, format_text
APP = QCoreApplication.instance() or QCoreApplication([])


class LanguageSettingsTests(unittest.TestCase):
    def test_default_and_invalid_language_are_english(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'settings.json'
            self.assertEqual(SettingsController(path=path).language,'en')
            path.write_text(json.dumps({'language':'unexpected','custom':1}))
            self.assertEqual(SettingsController(path=path).language,'en')

    def test_persistence_preserves_auto_and_unknown_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'settings.json'
            path.write_text(json.dumps({'custom':1}))
            settings=SettingsController(path=path)
            auto, changed=[], []
            settings.autoChanged.connect(lambda: auto.append(1))
            settings.languageChanged.connect(lambda: changed.append(1))
            config=settings.autoConfig
            settings.save_language('th')
            self.assertEqual(SettingsController(path=path).language,'th')
            self.assertEqual(settings.autoConfig,config)
            self.assertEqual(auto,[])
            self.assertEqual(changed,[1])
            self.assertEqual(json.loads(path.read_text())['custom'],1)

    def test_write_failure_and_invalid_language_are_atomic(self):
        with tempfile.TemporaryDirectory() as directory:
            settings=SettingsController(path=Path(directory)/'settings.json')
            with patch.object(settings,'_write',side_effect=OSError('Read-only')):
                with self.assertRaises(OSError): settings.save_language('th')
            self.assertEqual(settings.language,'en')
            with self.assertRaises(ValueError): settings.save_language('other')


class CatalogTests(unittest.TestCase):
    def test_complete_catalogs_cover_every_qml_binding(self):
        for locale in ('en_US','th_TH'):
            contexts={context.findtext('name'):{m.findtext('source'):m.findtext('translation') for m in context.findall('message')}
                      for context in ET.parse(ROOT/'i18n'/f'{locale}.ts').getroot().findall('context')}
            for path in (ROOT/'qml').glob('*.qml'):
                for source in re.findall(r'qsTr\(("(?:[^"\\]|\\.)*")\)',path.read_text(encoding='utf-8')):
                    self.assertTrue(contexts[path.stem].get(json.loads(source)),(locale,path.name,source))
            for context in contexts.values():
                for source,translation in context.items():
                    self.assertEqual(sorted(re.findall(r'%\d+',source)),sorted(re.findall(r'%\d+',translation)))

    def test_internal_ids_never_go_through_qstr(self):
        source=(ROOT/'qml'/'AutoOptimizePage.qml').read_text(encoding='utf-8')
        self.assertNotRegex(source,r'page\.edit\(qsTr')
        self.assertNotRegex(source,r'===\s*qsTr')

    def test_thai_dynamic_messages_keep_numeric_and_native_parameters(self):
        translator=QTranslator()
        self.assertTrue(translator.load(str(ROOT/'i18n'/'th_TH.qm')))
        APP.installTranslator(translator)
        try:
            self.assertEqual(display_text('trimming 12 apps'),'กำลังปรับหน่วยความจำ 12 แอป')
            self.assertEqual(display_text('High RAM usage triggered Maximum.'),'ใช้ RAM สูง เริ่มโหมด Maximum')
            self.assertEqual(display_text('SeProfileSingleProcessPrivilege not held — run as Administrator'),
                             'SeProfileSingleProcessPrivilege: ต้องใช้สิทธิ์ผู้ดูแลระบบ (ไม่มีสิทธิ์ที่ต้องการ)')
            self.assertEqual(display_text('NtSetSystemInformation NTSTATUS 0xC0000022'),'NtSetSystemInformation NTSTATUS 0xC0000022')
            self.assertEqual(format_text('%1 working set trimmed','120.0 MB'),'ลดหน่วยความจำที่แอปใช้อยู่ 120.0 MB')
        finally: APP.removeTranslator(translator)
