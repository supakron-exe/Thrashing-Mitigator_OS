"""Compile source resources with this application's Qt toolchain."""
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]

def main():
    rcc = Path(sys.executable).parent / "pyside6-rcc.exe"
    if not rcc.exists():
        raise SystemExit("Install requirements.txt into the redesign environment first.")
    library = ROOT / "vendor" / "FluentUI" / "imports"
    translations = library / "FluentUI" / "i18n"
    translations.mkdir(parents=True, exist_ok=True)
    lrelease = Path(sys.executable).parent / "pyside6-lrelease.exe"
    for source in sorted((ROOT / "i18n").glob("*.ts")):
        subprocess.run([str(lrelease), str(source), "-qm", str(source.with_suffix(".qm"))], check=True)
    for source in (ROOT / "vendor" / "FluentUI").glob("*.ts"):
        subprocess.run([str(lrelease), str(source), "-qm", str(translations / (source.stem + ".qm"))], check=True)
    subprocess.run([str(rcc), str(library / "resource.qrc"), "-o", str(library / "resource_rc.py")], check=True)
    resource = ET.Element("RCC")
    group = ET.SubElement(resource, "qresource", prefix="/redesign")
    for folder in ("qml", "assets", "i18n"):
        for path in sorted((ROOT / folder).rglob("*")):
            if path.is_file() and (folder != "i18n" or path.suffix == ".qm"):
                name = path.relative_to(ROOT).as_posix()
                ET.SubElement(group, "file", alias=name).text = name
    ET.indent(resource)
    ET.ElementTree(resource).write(ROOT / "resources.qrc", encoding="utf-8", xml_declaration=True)
    subprocess.run([str(rcc), str(ROOT / "resources.qrc"), "-o", str(ROOT / "resource_rc.py")], check=True)
    print("FluentUI and application resources compiled.")

if __name__ == "__main__":
    main()
