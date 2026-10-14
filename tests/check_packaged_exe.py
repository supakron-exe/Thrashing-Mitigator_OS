"""Extract a candidate ZIP and verify its standalone exe from a path with spaces and Thai."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--report-dir', type=Path, default=ROOT / 'build' / 'qa' / 'package')
    args = parser.parse_args()
    if args.archive:
        archive = args.archive.resolve()
    else:
        release = ROOT / 'release'
        latest = json.loads((release / 'latest-build.json').read_text(encoding='utf-8'))
        archive = Path(latest['archive'])
        if not archive.is_absolute():
            archive = release / archive
    report_dir = args.report_dir.resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    report = report_dir / 'report.json'
    if report.exists():
        report.unlink()
    with tempfile.TemporaryDirectory(prefix='ThrashingMitigator-share-') as temporary:
        extracted = Path(temporary) / 'Friend test ภาษาไทย'
        extracted.mkdir()
        with zipfile.ZipFile(archive) as bundle:
            assert bundle.testzip() is None
            for member in bundle.infolist():
                target = (extracted / member.filename).resolve()
                assert target.is_relative_to(extracted.resolve()), 'Unsafe ZIP path'
            bundle.extractall(extracted)
        exe = extracted / 'ThrashingMitigator' / 'ThrashingMitigator.exe'
        assert exe.exists()
        folder = exe.parent
        build_info = json.loads((folder / 'BUILD_INFO.json').read_text(encoding='utf-8'))
        hashes = json.loads((folder / 'SOURCE_HASHES.json').read_text(encoding='utf-8'))
        canonical = json.dumps(hashes, sort_keys=True, separators=(',', ':')).encode('utf-8')
        assert hashlib.sha256(canonical).hexdigest() == build_info['sourceSha256']
        assert len(hashes) == build_info['sourceFileCount']
        assert build_info['executableSha256'] == sha256(exe)
        assert 'backend/insights/app_names.py' in hashes and 'qml/InsightsPage.qml' in hashes
        for license_file in ('FluentUI-MIT.txt', 'Python.txt', 'LGPL-3.0-only.txt', 'GPL-3.0-only.txt'):
            assert (folder / 'LICENSES' / license_file).is_file(), license_file
        assert (folder / 'THIRD_PARTY_NOTICES.md').is_file()
        bundle_root = folder / '_internal'
        assert (bundle_root / 'python311.dll').exists()
        assert (bundle_root / 'PySide6' / 'plugins' / 'platforms' / 'qwindows.dll').exists()
        assert (bundle_root / 'PySide6' / 'qml' / 'QtQuick' / 'Controls' / 'Basic' / 'qmldir').exists()
        env = dict(os.environ)
        for key in list(env):
            if key.startswith(('PYTHON', 'QML', 'QT_')):
                env.pop(key, None)
        windows_root = os.environ['SystemRoot']
        env['PATH'] = str(Path(windows_root) / 'System32') + os.pathsep + windows_root
        child = subprocess.Popen([str(exe), '--verify-package', str(report)], cwd=extracted, env=env,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            result = child.wait(60)
            assert report.exists(), ('No diagnostic report', result)
            data = json.loads(report.read_text(encoding='utf-8'))
            assert result == 0 and data['cleanExit'], data
            assert data['frozen'] and data['secondaryForwarding'] and data['initialAutoOff']
            assert data['englishDefault'] and data['liveSamples'] >= 2
            assert data['startupRegistryUnchanged'] and data['trayHideRestore']
            assert data['nativeTrayAndWindowIcons']
            assert data['descriptiveNameResolver']
            assert len(data['screens']) == 4
            assert len(data['insightsScreens']) == 4 and data['insightsLiveApps'] > 0 and data['insightsPersistedOnExit']
            for key in ('qtModulePath', 'psutilModulePath', 'qmlImportPath'):
                assert str(bundle_root).replace('\\', '/').lower() in data[key].replace('\\', '/').lower(), (key, data[key])
            data.update(archive=str(archive), archiveSha256=sha256(archive),
                        sourceSha256=build_info['sourceSha256'], sourceFileCount=len(hashes),
                        executableSha256=build_info['executableSha256'],
                        extractedOutsideWorkspace=not extracted.resolve().is_relative_to(ROOT),
                        cleanPythonAndQtEnvironment=True, licenseNoticesVerified=True,
                        windowsVersion=sys.getwindowsversion().build)
            report.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
            print('PASS packaged ZIP: standalone exe, current source hashes, notices, live RAM/Insights, '
                  'both themes/languages, QML/fonts/logo, clean environment, Thai/spaced path, Tray, '
                  'secondary activation, clean Exit; registry unchanged.')
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait(5)


if __name__ == '__main__':
    main()
