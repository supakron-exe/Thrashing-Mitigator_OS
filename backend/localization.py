"""Application-owned translators and presentation; never mutate scheduler state."""
import re
from PySide6.QtCore import QObject, Property, Signal, Slot, QCoreApplication, QTranslator
from PySide6.QtGui import QFont, QFontDatabase


def tr(source):
    return QCoreApplication.translate('Presentation', source)


def format_text(source, *values):
    def argument(match):
        index = int(match.group(1)) - 1
        return str(values[index]) if index < len(values) else match.group()
    return re.sub(r'%([1-9]\d*)', argument, tr(source))


def display_text(value):
    """Known application messages only. OS diagnostics remain verbatim."""
    value = str(value or '')
    translated = tr(value)
    if translated != value: return translated
    patterns = (
        (r'trimming (\d+) apps', 'Trimming %1 apps'),
        (r'(Time \+ RAM|Time interval|High RAM usage) triggered (Standard|Deep|Maximum)\.', '%1 triggered %2.'),
        (r'(intervalMinutes|ramPercent|sustainSeconds|cooldownMinutes) must be between (\d+) and (\d+)\.', '%1 must be between %2 and %3.'),
        (r'([+\-\d.]+ (?:MB|GB)) working set trimmed', '%1 working set trimmed'),
        (r'(\d+) pages combined', '%1 pages combined'),
        (r'((?:all|low priority|full|priority-0) )?standby (\d+) -> (\d+) MB', '%1Standby: %2 → %3 MB'),
        (r'modified (\d+) -> (\d+) MB', 'Modified pages: %1 → %2 MB'),
        (r'(\S+) not held — run as Administrator', '%1: Administrator access needed (privilege not held)'),
        (r'(OpenProcessToken|AdjustTokenPrivileges|SetSystemFileCacheSize) failed \(error (\d+)\)', '%1 failed (error %2)'),
        (r'unknown privilege (\S+) \(error (\d+)\)', 'Unknown privilege %1 (error %2)'),
        (r'privilege not assigned \(error (\d+)\)', 'Privilege not assigned (error %1)'),
    )
    for pattern, source in patterns:
        match = re.fullmatch(pattern, value, flags=re.IGNORECASE)
        if match:
            return format_text(source, *(display_text(v) if v else '' for v in match.groups()))
    for prefix in ('Auto paused for this session. Settings could not be saved: ',
                   'Unable to enable Auto: ', 'Auto paused: ', 'unexpected error: '):
        if value.startswith(prefix): return tr(prefix) + display_text(value[len(prefix):])
    return value


def diagnostic_text(value, language):
    translated = display_text(value)
    if value and translated == value and language == 'th':
        return format_text('System diagnostic: %1', value)
    return translated


class LanguageController(QObject):
    changed = Signal()
    errorChanged = Signal()

    def __init__(self, app, preferences, parent=None):
        super().__init__(parent)
        self.app, self.preferences, self.engine = app, preferences, None
        self._revision, self._error, self._translators = 0, '', []
        self._code = preferences.language
        try: self._translators = self._load(self._code)
        except RuntimeError as exc:
            self._code, self._error = 'en', str(exc)
            try: self._translators = self._load('en')
            except RuntimeError: self._translators = []  # English source fallback.
        self.initialize()

    def _load(self, code):
        translators = []
        for locale in (['en_US', 'th_TH'] if code == 'th' else ['en_US']):
            translator = QTranslator(self)
            if not translator.load(':/redesign/i18n/' + locale + '.qm'):
                raise RuntimeError('Unable to load the language catalog: ' + locale)
            translators.append(translator)
        return translators

    @Property(str, notify=changed)
    def code(self): return self._code

    @Property(int, notify=changed)
    def revision(self): return self._revision

    @Property(str, notify=changed)
    def fontFamily(self):
        if self._code == 'en': return 'Segoe UI'
        return 'Leelawadee UI' if 'Leelawadee UI' in QFontDatabase.families() else 'Tahoma'

    @Property(str, notify=errorChanged)
    def error(self):
        return format_text('Language could not be changed. %1', self._error) if self._error else ''

    @Slot()
    def initialize(self):
        # FluApp.init installs its translator. Restore app catalogs' priority.
        for translator in self._translators:
            self.app.removeTranslator(translator)
            self.app.installTranslator(translator)
        self.app.setFont(QFont(self.fontFamily, 10))
        if self.engine: self.engine.retranslate()

    @Slot(str, result=bool)
    def setLanguage(self, code):
        if code == self._code and code == self.preferences.language:
            self._error = ''
            self.errorChanged.emit()
            return True
        try:
            if code not in ('en', 'th'): raise ValueError('Unsupported language.')
            candidates = self._load(code)
            self.preferences.save_language(code)
        except (OSError, ValueError, RuntimeError) as exc:
            self._error = str(exc)
            self.errorChanged.emit()
            return False
        for translator in self._translators:
            self.app.removeTranslator(translator)
            translator.deleteLater()
        self._translators, self._code, self._error = candidates, code, ''
        self.initialize()
        self._revision += 1
        self.changed.emit()
        self.errorChanged.emit()
        return True

    def dispose(self):
        self.engine = None
        for translator in self._translators: self.app.removeTranslator(translator)
        self._translators = []


class PresentationController(QObject):
    resultPresentationChanged = Signal()
    operationPresentationChanged = Signal()
    eventsPresentationChanged = Signal()
    autoPresentationChanged = Signal()
    activityPresentationChanged = Signal()

    def __init__(self, memory, automatic, language, parent=None):
        super().__init__(parent)
        self.memory, self.automatic, self.language = memory, automatic, language
        memory.resultChanged.connect(self.resultPresentationChanged)
        memory.operationChanged.connect(self.operationPresentationChanged)
        memory.eventsChanged.connect(self.eventsPresentationChanged)
        automatic.changed.connect(self.autoPresentationChanged)
        automatic.activityChanged.connect(self.activityPresentationChanged)
        language.changed.connect(self._retranslate)

    def _retranslate(self):
        for signal in (self.resultPresentationChanged, self.operationPresentationChanged,
                       self.eventsPresentationChanged, self.autoPresentationChanged,
                       self.activityPresentationChanged): signal.emit()

    @Slot(str, int, result=str)
    def text(self, value, revision=0): return display_text(value)

    @Slot('QVariantMap', int, result='QVariantMap')
    def result(self, value, revision=0):
        value = dict(value)
        for key in ('title', 'message', 'measurementLabel', 'reason'):
            if key in value: value[key] = display_text(value[key])
        if value.get('raw', {}).get('error') and self.language.code == 'th':
            value['message'] = format_text('System diagnostic: %1', value['raw']['error'])
        for key in ('steps', 'targets'):
            items = []
            for item in value.get(key, []):
                item = dict(item)
                item['detail'] = diagnostic_text(item.get('detail', ''), self.language.code)
                if key == 'steps': item['name'] = display_text(item.get('name', ''))
                elif item.get('name') == 'Unknown app': item['name'] = tr('Unknown app')
                items.append(item)
            value[key] = items
        return value

    @Property('QVariantMap', notify=resultPresentationChanged)
    def lastResult(self): return self.result(self.memory.lastResult)

    @Property(str, notify=operationPresentationChanged)
    def progress(self): return display_text(self.memory.progress)

    @Property('QVariantMap', notify=operationPresentationChanged)
    def operation(self):
        value = dict(self.memory.operation)
        value['stages'] = [dict(stage, label=display_text(stage['label'])) for stage in value.get('stages', [])]
        return value

    @Property('QVariantList', notify=eventsPresentationChanged)
    def events(self):
        return [dict(event, title=display_text(event.get('title', '')), reason=display_text(event.get('reason', '')))
                for event in self.memory.optimizationEvents]

    @Property('QVariantList', notify=activityPresentationChanged)
    def recentActivity(self):
        return [dict(item, title=display_text(item['title']), reason=display_text(item['reason']))
                for item in self.automatic.recentActivity]

    @Property(str, notify=autoPresentationChanged)
    def autoStatus(self): return display_text(self.automatic.status)

    @Property(str, notify=autoPresentationChanged)
    def autoDetail(self): return display_text(self.automatic.detail)

    @Property(str, notify=autoPresentationChanged)
    def autoError(self): return diagnostic_text(self.automatic.error, self.language.code)
