"""Add new QML source strings to app catalogs without losing reviewed translations."""
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]

def main():
    for path in sorted((ROOT/'i18n').glob('*.ts')):
        tree=ET.parse(path)
        contexts={c.findtext('name'):c for c in tree.getroot().findall('context')}
        added=0
        for qml in sorted((ROOT/'qml').glob('*.qml')):
            sources={json.loads(source) for source in re.findall(r'qsTr\(("(?:[^"\\]|\\.)*")\)',qml.read_text(encoding='utf-8'))}
            if not sources: continue
            if qml.stem not in contexts:
                context=ET.SubElement(tree.getroot(),'context')
                ET.SubElement(context,'name').text=qml.stem
                contexts[qml.stem]=context
            context=contexts[qml.stem]
            existing={m.findtext('source') for m in context.findall('message')}
            for source in sorted(sources-existing):
                message=ET.SubElement(context,'message')
                ET.SubElement(message,'source').text=source
                translation=ET.SubElement(message,'translation')
                if path.stem=='en_US': translation.text=source
                else: translation.set('type','unfinished')
                added+=1
        ET.indent(tree)
        tree.write(path,encoding='utf-8',xml_declaration=True)
        print(f'{path.name}: {added} new strings. Review unfinished Thai entries before building.')

if __name__=='__main__': main()
