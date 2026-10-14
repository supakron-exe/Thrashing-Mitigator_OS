"""Real Qt UI and live RAM; fake optimization/clock/startup, isolated preferences."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from qa_support import QA_ROOT, qa_path
parser = argparse.ArgumentParser()
parser.add_argument('--theme', default='light', choices=('light', 'dark'))
parser.add_argument('--scale', type=float, default=1)
args = parser.parse_args()
env = dict(os.environ); env.pop('QT_SCALE_FACTOR', None)
native = float(subprocess.check_output([sys.executable, '-c', 'from PySide6.QtGui import QGuiApplication; a=QGuiApplication([]); print(a.primaryScreen().devicePixelRatio())'], env=env, text=True).strip())
os.environ['QT_SCALE_FACTOR'] = str(args.scale / native)
from PySide6.QtCore import QObject, Property, QMetaObject, Q_ARG, Qt, qInstallMessageHandler
from PySide6.QtGui import QFont, QFontDatabase, QRawFont, QKeyEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtQuick import QQuickWindow, QSGRendererInterface
from main import create_engine, dispose_engine
from backend.controller import MemoryController
from backend.settings import SettingsController
from backend.auto_optimize import AutoOptimizeController
from backend.lifecycle import TrayLifecycle
from backend.localization import display_text, LanguageController
from backend.presentation import present_result

class Clock:
    now = 0
    def __call__(self): return self.now
class Startup:
    def capture(self): return False
    def is_enabled(self): return False
    def set_enabled(self, value): raise AssertionError('Localization must not modify Windows startup')

gate = threading.Event()
def fixture(mode, progress):
    progress('trimming 5 apps')
    assert gate.wait(10), 'Fixture worker release timed out'
    return dict(supported=True, elevated=True, trimmed=2, failed=1,
                available_before_mb=2500, available_after_mb=2800, available_delta_mb=300,
                available_settled_mb=2800, available_settled_delta_mb=300, free_delta_mb=25,
                duration_s=3.5, steps=[dict(name='file_cache', ok=False, detail='access denied (run as Administrator)')],
                targets=[dict(name='example.exe', ok=False, reason='OS diagnostic: ' + 'error 5 ' * 35)])

messages = []
qInstallMessageHandler(lambda kind, context, message: messages.append(message))
QQuickWindow.setGraphicsApi(QSGRendererInterface.GraphicsApi.OpenGL)
app = QApplication([]); app.setQuitOnLastWindowClosed(False)
temp = tempfile.TemporaryDirectory()
prefs = SettingsController(args.theme, Path(temp.name)/'settings.json')
prefs.setAnimations(False)
memory = MemoryController(runner=fixture, hold_ms=300)
clock = Clock()
automatic = AutoOptimizeController(memory, prefs, startup=Startup(), clock=clock)
automatic._timer.stop()
lifecycle = TrayLifecycle(app, memory, automatic, prefs)
engine, memory, prefs = create_engine(app, controller=memory, settings=prefs, automatic=automatic, lifecycle=lifecycle)
language, presenter = engine._language, engine._presentation
language.changed.connect(lifecycle._update)

def pump(seconds=.06):
    end = time.monotonic() + seconds
    while time.monotonic() < end: app.processEvents(); time.sleep(.005)
def wait(predicate):
    end = time.monotonic()+5
    while not predicate():
        assert time.monotonic()<end, 'Timed out'
        pump(.02)
def find(name):
    item = window.findChild(QObject, name)
    assert item is not None, name
    return item
def click(name):
    assert QMetaObject.invokeMethod(find(name), 'clicked', Qt.QueuedConnection)
    pump()
def variant(value): return value.toVariant() if hasattr(value, 'toVariant') else value
def shot(name):
    target = QA_ROOT/'screenshots'/f'i18n_{language.code}_{args.theme}_{args.scale:g}_{name}.png'
    target.parent.mkdir(exist_ok=True)
    assert window.grabWindow().save(str(target))
def check_text(item):
    for child in item.childItems():
        if child.isVisible() and child.property('text') and child.property('contentWidth') is not None:
            if child.metaObject().indexOfProperty('wrapMode') >= 0 and not child.property('truncated'):
                assert child.width() >= child.property('contentWidth')-1, (child.property('text'), child.width(), child.property('contentWidth'))
                assert child.height() >= child.property('contentHeight')-1, ('height', child.property('text'), child.height(), child.property('contentHeight'))
        check_text(child)

try:
    pump(.7)
    window = next(w for w in app.allWindows() if w.objectName()=='mainWindow')
    window.setTitle('Localization QA — live RAM / simulated Optimize')
    assert abs(window.devicePixelRatio()-args.scale)<.01
    assert language.code == prefs.language == 'en'
    assert find('optimizeButton').property('text')=='Optimize now'
    assert find('languageSelector').property('currentIndex') == 0
    auto_events, result_events = [], []
    prefs.autoChanged.connect(lambda: auto_events.append(1))
    memory.resultChanged.connect(lambda: result_events.append(1))
    next_run, high_since = automatic._next, automatic._high_since
    click('autoNav')
    page = find('autoPage')
    assert QMetaObject.invokeMethod(page, 'edit', Qt.QueuedConnection, Q_ARG('QVariant','ramPercent'), Q_ARG('QVariant',80))
    pump()
    draft = variant(page.property('draft'))
    focus = find('autoRamInput'); focus.forceActiveFocus()
    selector = find('languageSelector')
    selector.setProperty('currentIndex', 1)
    assert QMetaObject.invokeMethod(selector, 'activated', Qt.QueuedConnection, Q_ARG('int', 1))
    pump()
    assert language.code == 'th' and selector.property('currentIndex') == 1
    assert window.property('page')==2 and variant(page.property('draft'))==draft
    assert focus.property('activeFocus')
    assert find('autoStatusText').property('text')=='ปิดอยู่'
    assert automatic._next==next_run and automatic._high_since==high_since and not auto_events
    assert lifecycle.open_action.text()=='เปิดแอป'
    # Check actual UI input handler uses the original field key in Thai.
    field = focus.parentItem().parentItem()
    assert QMetaObject.invokeMethod(field, 'edited', Qt.QueuedConnection, Q_ARG('int',81))
    pump()
    assert variant(page.property('draft'))['ramPercent']==81
    # Font probe includes Thai base letters, upper/lower vowels and tone marks.
    font = QRawFont.fromFont(QFont(language.fontFamily, 14), QFontDatabase.Thai)
    assert all(font.supportsCharacter(ord(c)) for c in 'กิุ้ํ')
    assert language.fontFamily in ('Leelawadee UI', 'Tahoma')
    with __import__('unittest.mock', fromlist=['patch']).patch('backend.localization.QFontDatabase.families', return_value=['Tahoma']):
        assert language.fontFamily == 'Tahoma'
    assert json.loads(prefs.path.read_text())['language']=='th'
    assert SettingsController(path=prefs.path).language=='th'
    # Failed persistence/catalog load must keep old language and saved language.
    original_write = prefs._write
    prefs._write = lambda *a, **k: (_ for _ in ()).throw(OSError('QA read-only settings'))
    assert not language.setLanguage('en') and language.code==prefs.language=='th'
    assert json.loads(prefs.path.read_text())['language']=='th'
    prefs._write = original_write
    original_load = language._load
    language._load = lambda code: (_ for _ in ()).throw(RuntimeError('QA missing catalog'))
    assert not language.setLanguage('en') and language.code=='th'
    language._load = original_load
    assert language.setLanguage('en')
    # A saved Thai preference with a missing Thai catalog opens English safely;
    # selecting English can persist the fallback without a false saved success.
    fallback_prefs = SettingsController(path=Path(temp.name)/'fallback.json')
    fallback_prefs.save_language('th')
    load = LanguageController._load
    def missing_thai(owner, code):
        if code == 'th': raise RuntimeError('QA missing Thai catalog')
        return load(owner, code)
    with __import__('unittest.mock', fromlist=['patch']).patch.object(LanguageController, '_load', missing_thai):
        fallback = LanguageController(app, fallback_prefs)
        assert fallback.code == 'en' and fallback_prefs.language == 'th' and fallback.error
        assert fallback.setLanguage('en') and fallback_prefs.language == 'en'
        fallback.dispose()
    language.initialize()
    click('overviewNav')
    window.requestActivate(); pump(.2)
    memory.startOptimization(); wait(lambda: memory.progress=='trimming 5 apps')
    thread = memory._thread
    assert language.setLanguage('th'); pump()
    assert memory._thread is thread and memory.running and presenter.progress=='กำลังปรับหน่วยความจำ 5 แอป'
    assert find('optimizeButton').property('disabled')
    assert memory.operation['stageId']=='trim'
    samples_before = memory.snapshot['timestamp']
    pump(2.1)
    assert memory.snapshot['timestamp']>samples_before
    gate.set(); wait(lambda: not memory.running)
    toast, card = find('resultToast'), find('resultCard')
    wait(lambda: bool(toast.property('opened')))
    deadline, operation_id, counts = toast.property('deadline'), toast.property('lastOperationId'), len(result_events)
    card.setProperty('expanded', True)
    assert language.setLanguage('en'); pump(.02)
    assert memory.busy and card.property('expanded')
    assert toast.property('deadline')==deadline and toast.property('lastOperationId')==operation_id
    assert len(result_events)==counts and not auto_events
    assert language.setLanguage('th'); pump(.02)
    assert card.property('expanded') and toast.property('height')==44 and toast.width()<=340
    assert 'ดูรายละเอียด' in toast.property('message')
    assert presenter.lastResult['title']=='ปรับหน่วยความจำเสร็จแล้ว'
    assert memory.lastResult['title']=='Optimization complete'
    wait(lambda: not memory.busy)
    # Existing result states, unavailable rights and raw native errors.
    for raw, mode, title in [
        (dict(supported=True,trimmed=2,available_delta_mb=0),'Standard','หน่วยความจำพร้อมใช้งานไม่เพิ่ม'),
        (dict(supported=True,trimmed=0),'Standard','ไม่มีแอปที่ว่างและเข้าเกณฑ์'),
        (dict(supported=True,trimmed=0,elevated=False),'Maximum','ต้องใช้สิทธิ์ผู้ดูแลระบบ'),
        (dict(error='NtSetSystemInformation 0xC0000022'),'Maximum','ปรับหน่วยความจำไม่สำเร็จ'),
        (dict(supported=False),'Standard','แสดงค่าเท่านั้น')]:
        translated = presenter.result(present_result(raw,mode))
        assert translated['title']==title, translated
        if raw.get('error'): assert raw['error'] in translated['message']
    assert display_text('ramPercent must be between 50 and 95.')=='ระดับ RAM (%) ต้องอยู่ระหว่าง 50 ถึง 95'
    assert display_text('trimming 13 apps')=='กำลังปรับหน่วยความจำ 13 แอป'
    assert display_text('SeProfileSingleProcessPrivilege not held — run as Administrator') # diagnostic preserved
    automatic._activity=[dict(time='19:12:34',mode='Maximum',reason='High RAM usage',title='Optimization complete',gain='+300.0 MB',tone='success',duration='3.5 s')]
    automatic.activityChanged.emit()
    assert presenter.recentActivity[0]['reason']=='ใช้ RAM สูง'
    # Keep chart selection across retranslation, including its tooltip.
    canvas = find('historyCanvas')
    chart = canvas.parentItem().parentItem().parentItem()
    # Find the actual HistoryCard through its declared selectedTimestamp property.
    while chart.metaObject().indexOfProperty('selectedTimestamp')<0: chart=chart.parentItem()
    assert QMetaObject.invokeMethod(chart,'selectIndex',Qt.QueuedConnection,Q_ARG('QVariant',0))
    pump()
    timestamp = chart.property('selectedTimestamp')
    assert language.setLanguage('en'); pump()
    assert chart.property('pinned') and chart.property('selectedTimestamp')==timestamp
    # Every page, both languages, minimum/default/maximized, at selected DPR.
    toast.setProperty('displayDuration',60000)
    for code in ('en','th'):
        assert language.setLanguage(code)
        for size,width,height in [('minimum',900,640),('default',1180,740),('maximized',None,None)]:
            if width is None: window.showMaximized()
            else: window.showNormal(); window.resize(width,height)
            pump(.12)
            for nav, page_id in [('overviewNav',0),('autoNav',2),('settingsNav',1)]:
                click(nav)
                check_text(window.contentItem())
                if size=='default' and args.scale==1: shot(nav)
            click('overviewNav')
            if size=='default' and args.scale==1:
                assert QMetaObject.invokeMethod(window,'viewResult',Qt.QueuedConnection)
                pump()
                check_text(window.contentItem())
                shot('result')
            plot_height = canvas.height()
            other = 'th' if code=='en' else 'en'
            assert language.setLanguage(other); pump()
            assert abs(canvas.height()-plot_height)<.1
            assert language.setLanguage(code)
    # Catalogs are complete, and positional arguments match in each message.
    import re
    for path in (ROOT/'i18n').glob('*.ts'):
        for message in ET.parse(path).getroot().iter('message'):
            source, translated = message.findtext('source'), message.findtext('translation')
            assert translated and message.find('translation').get('type')!='unfinished'
            assert sorted(re.findall(r'%\d+',source))==sorted(re.findall(r'%\d+',translated)), source
    assert not [m for m in messages if any(token in m for token in ('TypeError','ReferenceError','Binding loop','Error:'))], messages
    # Switching language also preserves expanded state while motion is enabled.
    prefs.setAnimations(True)
    window.setProperty('page',0)
    pump(.3)
    expanded=card.property('expanded')
    assert language.setLanguage('en'); pump(.1)
    assert card.property('expanded')==expanded
    prefs.setAnimations(False)
    # Thai shutdown copy is readable while Exit waits for the gated worker.
    assert language.setLanguage('th')
    gate.clear(); memory.startOptimization(); wait(lambda: memory.running)
    lifecycle.exit(); pump()
    assert memory.closing and memory._thread is not None
    check_text(window.contentItem())
    gate.set(); wait(lambda: memory.safeToClose)
    print(f'PASS localization {args.theme} DPR {args.scale:g}: both languages × three sizes × three pages; worker/cooldown, popup, focus, draft, chart, persistence/fallback and Tray')
finally:
    gate.set()
    dispose_engine(app,engine,memory)
    lifecycle.tray.hide(); lifecycle.menu.deleteLater()
    temp.cleanup()
