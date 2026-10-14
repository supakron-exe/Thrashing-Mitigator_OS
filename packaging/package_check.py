"""Exercise the frozen production entry point with live RAM in a temporary profile."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import traceback
from contextlib import closing


def run():
    position = sys.argv.index('--verify-package')
    report_path = Path(sys.argv[position + 1]).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = {'frozen': bool(getattr(sys, 'frozen', False)), 'executable': sys.executable, 'screens': []}
    from PySide6.QtCore import QTimer, QFile, QObject, QLibraryInfo, qInstallMessageHandler
    from PySide6 import QtCore
    from PySide6.QtGui import QImage, QFontDatabase
    import psutil
    import main as application
    from backend.startup import WindowsStartup
    startup = WindowsStartup(application.ROOT)
    registry_before = startup.capture()
    state = {'failed': False, 'secondary': None}
    original_create = application.create_engine

    def instrumented(*args, **kwargs):
        engine, memory, preferences = original_create(*args, **kwargs)
        app, language, lifecycle = args[0], engine._language, engine._lifecycle
        def window():
            return next(w for w in app.allWindows() if w.objectName() == 'mainWindow')
        def guarded(action):
            def callback():
                try: action()
                except Exception:
                    state['failed'] = True
                    report['error'] = traceback.format_exc()
                    lifecycle.exit()
            return callback
        def finished():
            assert memory.live and len(memory.history) >= 2
            assert memory._thread is None, 'Diagnostic must not run Optimize'
            report['liveSamples'] = len(memory.history)
            assert engine._insights.appModel.rowCount()>0
            report['insightsLiveApps']=engine._insights.appModel.rowCount()
            report['insightsReadableProcesses']=engine._insights.coverage.get('readable',0)
            report['insightsUnavailableProcesses']=engine._insights.coverage.get('denied',0)
            assert report['insightsReadableProcesses']>0
            report['liveTotalRamBytes'] = memory.snapshot['total']
            report['startupCommand'] = startup.command
            assert startup.command == subprocess.list2cmdline([sys.executable, '--background']) if report['frozen'] else 'main.py' in startup.command
            assert startup.capture() == registry_before
            report['startupRegistryUnchanged'] = True
            lifecycle.closeWindow(window())
            assert not window().isVisible() if lifecycle.trayAvailable else window().isVisible()
            lifecycle.open()
            assert window().isVisible()
            report['trayHideRestore'] = lifecycle.trayAvailable
            lifecycle.exit()
        def forwarded():
            child = state['secondary']
            if child.poll() is None:
                assert time.monotonic() < state['deadline'], 'Secondary activation timeout'
                QTimer.singleShot(100, guarded(forwarded))
                return
            assert child.returncode == 0 and preferences.theme == 'light'
            report['secondaryForwarding'] = True
            QTimer.singleShot(800, guarded(finished))
        def secondary():
            if not report['frozen']:
                QTimer.singleShot(800, guarded(finished))
                return
            state['secondary'] = subprocess.Popen([sys.executable, '--theme', 'light'], cwd=report_path.parent,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            state['deadline'] = time.monotonic() + 8
            QTimer.singleShot(150, guarded(forwarded))
        combinations = [('en', 'light'), ('en', 'dark'), ('th', 'light'), ('th', 'dark')]
        report['insightsScreens']=[]
        def insights_step(index=0):
            if index==len(combinations):
                secondary();return
            code,theme=combinations[index]
            assert language.setLanguage(code)
            preferences.setTheme(theme)
            window().setProperty('page',3)
            def capture_insights():
                filename=f'packaged_insights_{code}_{theme}.png'
                assert window().grabWindow().save(str(report_path.parent/filename))
                report['insightsScreens'].append(dict(language=code,theme=theme,image=filename))
                QTimer.singleShot(150,guarded(lambda:insights_step(index+1)))
            QTimer.singleShot(500,guarded(capture_insights))
        def step(index=0):
            if index == len(combinations):
                insights_step()
                return
            code, theme = combinations[index]
            assert language.setLanguage(code)
            preferences.setTheme(theme)
            window().setProperty('page', 1 if index == 2 else 2 if index == 3 else 0)
            def capture():
                button = window().findChild(QObject, 'optimizeButton')
                assert button.property('text') == ('ปรับหน่วยความจำ' if code == 'th' else 'Optimize now')
                assert window().findChild(QObject, 'languageSelector') is not None
                filename = f'packaged_{code}_{theme}.png'
                assert window().grabWindow().save(str(report_path.parent / filename))
                report['screens'].append({'language': code, 'theme': theme, 'page': window().property('page'), 'image': filename})
                QTimer.singleShot(250, guarded(lambda: step(index + 1)))
            QTimer.singleShot(150, guarded(capture))
        def begin():
            assert not engine._automatic.enabled
            assert language.code == 'en'
            if report['frozen']:
                from backend.insights.app_names import AppNameResolver
                identity = AppNameResolver().resolve(Path(sys.executable).name, sys.executable)
                assert identity['displayName'] == 'Thrashing Mitigator — Fluent Premium', identity
                assert identity['nameSource'] == 'file_description', identity
                report['descriptiveNameResolver'] = True
            preferences.setAnimations(False)
            assert QFile(':/redesign/i18n/th_TH.qm').exists()
            assert not QImage(':/redesign/assets/logo.png').isNull()
            assert QFile(':/FluentUI/Font/FluentIcons.ttf').exists()
            assert any('Fluent' in family for family in QFontDatabase.families())
            report['qtVersion'] = QtCore.qVersion()
            report['qtModulePath'] = QtCore.__file__
            report['psutilModulePath'] = psutil.__file__
            report['qmlImportPath'] = QLibraryInfo.path(QLibraryInfo.QmlImportsPath)
            report['initialAutoOff'] = True
            assert not lifecycle.tray.icon().isNull()
            assert not app.windowIcon().isNull()
            report['nativeTrayAndWindowIcons'] = True
            report['englishDefault'] = True
            report['qmlResourcesLogoFontAndThaiCatalog'] = True
            step()
        QTimer.singleShot(700, guarded(begin))
        return engine, memory, preferences

    with tempfile.TemporaryDirectory(prefix='ThrashingMitigator-package-check-') as temporary:
        old_stdout, old_stderr = sys.stdout, sys.stderr
        old_local = os.environ.get('LOCALAPPDATA')
        os.environ['LOCALAPPDATA'] = temporary
        application.create_engine = instrumented
        sys.argv = [sys.argv[0]]
        try:
            result = application.main()
            report['cleanExit'] = result == 0 and not state['failed']
            import sqlite3
            history=Path(temporary)/'ThrashingMitigatorRedesign'/'insights'/'insights.db'
            assert history.exists()
            with closing(sqlite3.connect(history)) as database:
                assert database.execute('SELECT COUNT(*) FROM apps').fetchone()[0]>0
            report['insightsPersistedOnExit']=True
            log = Path(temporary) / 'ThrashingMitigatorRedesign' / 'application.log'
            messages = log.read_text(encoding='utf-8') if log.exists() else ''
            report['qtDiagnostics'] = messages
            assert not any(error in messages for error in ('ReferenceError', 'TypeError', 'is not installed', 'failed to load component', 'Binding loop'))
            assert report['cleanExit'] and report.get('liveSamples', 0) >= 2
        except Exception:
            report['cleanExit'] = False
            report.setdefault('error', traceback.format_exc())
        finally:
            qInstallMessageHandler(None)
            opened_streams = {stream for stream in (sys.stdout, sys.stderr) if stream is not None and stream not in (old_stdout, old_stderr)}
            sys.stdout, sys.stderr = old_stdout, old_stderr
            for stream in opened_streams: stream.close()
            application.create_engine = original_create
            if old_local is None: os.environ.pop('LOCALAPPDATA', None)
            else: os.environ['LOCALAPPDATA'] = old_local
            report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    return 0 if report['cleanExit'] else 1
