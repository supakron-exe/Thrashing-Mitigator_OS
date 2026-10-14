import json
import os
import math
from pathlib import Path
from PySide6.QtCore import QObject, Property, Signal, Slot

AUTO_DEFAULTS = dict(mode='Maximum', intervalEnabled=True, intervalMinutes=3,
                     ramEnabled=True, ramPercent=75, sustainSeconds=10,
                     cooldownMinutes=3, startWithWindows=False)


def validate_auto(config):
    if not isinstance(config, dict):
        raise ValueError('Invalid Auto configuration.')
    result = {key: config.get(key, value) for key, value in AUTO_DEFAULTS.items()}
    for key in ('intervalEnabled', 'ramEnabled', 'startWithWindows'):
        if type(result[key]) is not bool:
            raise ValueError('Invalid switch value.')
    if result['mode'] not in ('Standard', 'Deep', 'Maximum'):
        raise ValueError('Choose Standard, Deep or Maximum.')
    for key, low, high in (('intervalMinutes', 1, 1440), ('ramPercent', 50, 95),
                           ('sustainSeconds', 2, 120), ('cooldownMinutes', 1, 60)):
        value = result[key]
        if type(value) not in (int, float) or not math.isfinite(value) or int(value) != value or not low <= value <= high:
            raise ValueError(f'{key} must be between {low} and {high}.')
        result[key] = int(value)
    if not result['intervalEnabled'] and not result['ramEnabled']:
        raise ValueError('Enable at least one trigger.')
    if result['intervalEnabled'] and result['intervalMinutes'] < result['cooldownMinutes']:
        raise ValueError('The interval must be at least the cooldown.')
    return result


class SettingsController(QObject):
    changed = Signal()
    autoChanged = Signal()
    languageChanged = Signal()

    def __init__(self, theme=None, path=None, parent=None):
        super().__init__(parent)
        self.path = Path(path) if path else Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'ThrashingMitigatorRedesign' / 'settings.json'
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            data = {}
        self._data = data if isinstance(data, dict) else {}
        self._theme = theme or self._data.get('theme', 'light')
        if self._theme not in ('light', 'dark'):
            self._theme = 'light'
        self._motion = bool(self._data.get('animations', True))
        self._language = self._data.get('language', 'en')
        if self._language not in ('en', 'th'): self._language = 'en'
        self._auto_enabled = self._data.get('autoEnabled') is True
        clean = dict(AUTO_DEFAULTS)
        stored = self._data.get('autoConfig', {})
        repaired = not isinstance(stored, dict) or (self._auto_enabled and 'autoConfig' not in self._data)
        if isinstance(stored, dict):
            for key, default in AUTO_DEFAULTS.items():
                value = stored.get(key, default)
                if type(value) is type(default):
                    trial = dict(AUTO_DEFAULTS, **{key: value})
                    if key == 'cooldownMinutes': trial['intervalMinutes'] = 1440
                    if key == 'intervalMinutes': trial['cooldownMinutes'] = 1
                    try: validate_auto(trial); clean[key] = value
                    except ValueError: repaired = True
                else: repaired = True
        try: self._auto = validate_auto(clean)
        except ValueError:
            self._auto = dict(AUTO_DEFAULTS)
            repaired = True
        if repaired: self._auto_enabled = False

    @Property(str, notify=changed)
    def theme(self): return self._theme

    @Property(bool, notify=changed)
    def animations(self): return self._motion

    @Property(str, notify=languageChanged)
    def language(self): return self._language

    def save_language(self, language):
        if language not in ('en', 'th'): raise ValueError('Unsupported language.')
        previous = self._language
        self._language = language
        try: self._write()
        except OSError:
            self._language = previous
            raise
        if previous != language: self.languageChanged.emit()

    @Property(bool, notify=autoChanged)
    def autoEnabled(self): return self._auto_enabled

    @Property('QVariantMap', notify=autoChanged)
    def autoConfig(self): return dict(self._auto)

    def _write(self, auto=None, enabled=None):
        data = dict(self._data, theme=self._theme, animations=self._motion, language=self._language,
                    autoEnabled=self._auto_enabled if enabled is None else enabled,
                    autoConfig=self._auto if auto is None else auto)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f'.{os.getpid()}.tmp')
        temporary.write_text(json.dumps(data, indent=2), encoding='utf-8')
        temporary.replace(self.path)
        self._data = data

    def save_auto(self, config=None, enabled=None):
        candidate = validate_auto(config if config is not None else self._auto)
        self._write(candidate, enabled)
        self._auto = candidate
        if enabled is not None: self._auto_enabled = bool(enabled)
        self.autoChanged.emit()

    def _save(self):
        try: self._write()
        except OSError: pass
        self.changed.emit()

    @Slot(str)
    def setTheme(self, theme):
        if theme in ('light', 'dark') and theme != self._theme:
            self._theme = theme
            self._save()

    @Slot(bool)
    def setAnimations(self, enabled):
        if bool(enabled) != self._motion:
            self._motion = bool(enabled)
            self._save()
