"""Build and verify a portable candidate before publishing the single current release."""
import argparse
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
NAME = 'ThrashingMitigator'
ARCHIVE_NAME = f'{NAME}-Windows-x64-Portable.zip'
VERSION = '0.2.0-preview'
FLUENT_COMMIT = '617986a17c9850ecb365bc02713433abab79c7aa'
SOURCE_DIRECTORIES = ('backend', 'qml', 'assets', 'i18n', 'vendor', 'packaging', 'tools', 'tests', 'docs')
DEPENDENCIES = ('PySide6', 'PySide6_Essentials', 'PySide6_Addons', 'shiboken6', 'psutil',
                'keyboard', 'qrcode', 'pillow', 'typing_extensions', 'pypng', 'PyInstaller',
                'pyinstaller-hooks-contrib', 'packaging')


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def source_hashes():
    """Fingerprint only source/build inputs; exclude caches and generated QA artifacts."""
    files = []
    for directory in SOURCE_DIRECTORIES:
        files.extend((ROOT / directory).rglob('*'))
    files.extend(path for path in ROOT.iterdir() if path.is_file() and path.suffix in
                 ('.py', '.txt', '.cmd', '.ps1', '.md', '.qrc'))
    return {path.relative_to(ROOT).as_posix(): sha256(path) for path in sorted(set(files))
            if path.is_file() and not any(part in ('__pycache__', '.git', 'qa', 'build', 'release')
                                          for part in path.relative_to(ROOT).parts)}


def source_digest(hashes):
    canonical = json.dumps(hashes, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(canonical).hexdigest()


def copy_notices(destination):
    notices = destination / 'LICENSES'
    notices.mkdir()
    shutil.copy2(ROOT / 'vendor' / 'LICENSE', notices / 'FluentUI-MIT.txt')
    patches = ROOT / 'vendor' / 'LOCAL_PATCHES.md'
    if patches.exists():
        shutil.copy2(patches, notices / 'FluentUI-LOCAL-PATCHES.md')
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if not python_license.exists():
        raise RuntimeError('Python LICENSE.txt is missing from the build runtime.')
    shutil.copy2(python_license, notices / 'Python.txt')
    for name in DEPENDENCIES:
        distribution = metadata.distribution(name)
        for file in distribution.files or []:
            parts = file.parts
            info_index = next((index for index, part in enumerate(parts)
                               if part.endswith('.dist-info')), None)
            if info_index is None:
                continue
            relative = Path(*parts[info_index + 1:])
            if not any('license' in part.lower() or 'licence' in part.lower() or 'copying' in part.lower()
                       for part in relative.parts):
                continue
            target = notices / name / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(distribution.locate_file(file), target)
        (notices / f'{name}-metadata.txt').write_text(
            distribution.read_text('METADATA') or '', encoding='utf-8')
    for file in (ROOT / 'packaging' / 'licenses').glob('*'):
        if file.is_file():
            shutil.copy2(file, notices / file.name)


def create_icon():
    from PIL import Image
    with Image.open(ROOT / 'assets' / 'logo.png') as image:
        mark = image.crop((880, 256, 1938, 1191)).convert('RGBA')
        mark.thumbnail((224, 224))
        canvas = Image.new('RGBA', (256, 256))
        canvas.alpha_composite(mark, ((256 - mark.width) // 2, (256 - mark.height) // 2))
        canvas.save(ROOT / 'assets' / 'app.ico',
                    sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def publish(candidate, stage, manifest):
    """Replace only known release entries, restoring the preceding release on failure."""
    release = ROOT / 'release'
    project = ROOT.resolve()
    for path in (candidate, stage, release):
        if not path.resolve().is_relative_to(project):
            raise RuntimeError(f'Packaging path must remain inside the project: {path}')
    release.mkdir(exist_ok=True)
    names = (NAME, ARCHIVE_NAME, ARCHIVE_NAME + '.sha256', 'latest-build.json')
    for directory in (candidate, release, stage / 'previous-release', stage / 'unpublished-release'):
        for name in names:
            if not (directory / name).resolve().is_relative_to(project):
                raise RuntimeError(f'Release path resolves outside the project: {directory / name}')
    unexpected = [path.name for path in release.iterdir() if path.name not in names]
    if unexpected:
        raise RuntimeError('Release contains other files; preserve them before publishing: ' + ', '.join(unexpected))
    previous = stage / 'previous-release'
    previous.mkdir()
    installed = []
    backed_up = []
    try:
        for name in names:
            path = release / name
            if path.exists():
                os.replace(path, previous / name)
                backed_up.append(name)
        for name in names[:-1]:
            os.replace(candidate / name, release / name)
            installed.append(name)
        write_json(stage / 'latest-build.json', manifest)
        os.replace(stage / 'latest-build.json', release / 'latest-build.json')
        installed.append('latest-build.json')
    except Exception:
        failed = stage / 'unpublished-release'
        failed.mkdir(exist_ok=True)
        for name in reversed(installed):
            path = release / name
            if path.exists():
                os.replace(path, failed / name)
        for name in backed_up:
            os.replace(previous / name, release / name)
        raise
    return release / ARCHIVE_NAME


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage-only', action='store_true',
                        help='Build and verify a candidate without replacing release/.')
    args = parser.parse_args()
    if sys.platform != 'win32' or sys.version_info[:2] != (3, 11):
        raise SystemExit('Build with the project Windows x64 Python 3.11 environment.')
    now = datetime.now(timezone.utc)
    stamp = now.strftime('%Y%m%d-%H%M%S-%f')
    stage = ROOT / 'build' / f'package-{stamp}'
    candidate = stage / 'candidate'
    candidate.mkdir(parents=True, exist_ok=False)
    create_icon()
    subprocess.run([sys.executable, str(ROOT / 'tools' / 'build_resources.py')], check=True, cwd=ROOT)
    inputs = source_hashes()
    input_digest = source_digest(inputs)
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--distpath', str(candidate),
                    '--workpath', str(stage / 'pyinstaller'),
                    str(ROOT / 'packaging' / 'ThrashingMitigator.spec')], check=True, cwd=ROOT)
    if source_hashes() != inputs:
        raise RuntimeError('Source changed during packaging; build again from the completed source.')
    folder = candidate / NAME
    for name in ('READ_ME.txt', 'THIRD_PARTY_NOTICES.md'):
        shutil.copy2(ROOT / 'packaging' / name, folder / name)
    copy_notices(folder)
    write_json(folder / 'SOURCE_HASHES.json', inputs)
    build_info = dict(product='Thrashing Mitigator', version=VERSION, architecture='Windows x64',
                      features=['Overview', 'Auto Optimize', 'Insights: visual 24-hour local history',
                                'English/Thai', 'Light/Dark', 'Descriptive application names'],
                      buildTimeUtc=now.isoformat(), python=sys.version,
                      dependencies={name: metadata.version(name) for name in DEPENDENCIES},
                      fluentUICommit=FLUENT_COMMIT, sourceSha256=input_digest, sourceFileCount=len(inputs),
                      executableSha256=sha256(folder / f'{NAME}.exe'))
    write_json(folder / 'BUILD_INFO.json', build_info)
    archive = candidate / ARCHIVE_NAME
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in sorted(folder.rglob('*')):
            if path.is_file():
                bundle.write(path, path.relative_to(candidate))
    archive_hash = sha256(archive)
    archive.with_suffix('.zip.sha256').write_text(archive_hash + '  ' + archive.name + '\n', encoding='utf-8')
    qa = stage / 'qa'
    subprocess.run([sys.executable, str(ROOT / 'tests' / 'check_packaged_exe.py'),
                    '--archive', str(archive), '--report-dir', str(qa)], check=True, cwd=ROOT)
    if source_hashes() != inputs:
        raise RuntimeError('Source changed during candidate verification; release was not replaced.')
    if args.stage_only:
        print(f'Verified candidate: {archive}', flush=True)
        return
    qa_current = ROOT / 'build' / 'qa' / 'package'
    shutil.copytree(qa, qa_current, dirs_exist_ok=True)
    manifest = dict(schemaVersion=1, product='Thrashing Mitigator', version=VERSION,
                    buildTimeUtc=now.isoformat(), folder=NAME, archive=ARCHIVE_NAME,
                    archiveSha256=archive_hash, executableSha256=build_info['executableSha256'],
                    sourceSha256=input_digest, qaReport='../build/qa/package/report.json')
    published = publish(candidate, stage, manifest)
    report = qa_current / 'report.json'
    data = json.loads(report.read_text(encoding='utf-8'))
    data['archive'] = str(published)
    write_json(report, data)
    print(f'Published verified portable ZIP: {published}', flush=True)


if __name__ == '__main__':
    main()
