"""Add the Insights catalog entries without dropping existing translations."""
import json
import re
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
TH={
    'Unidentified app':'แอปที่ยังระบุชื่อไม่ได้',
    'The app name was unavailable when this reading was recorded.':'ไม่สามารถอ่านชื่อแอปได้ขณะบันทึกข้อมูลนี้',
    'Windows memory compression':'ระบบบีบอัดหน่วยความจำของ Windows',
    'Windows kernel':'เคอร์เนลของ Windows',
    'System idle process':'โปรเซสขณะระบบว่าง',
    'Increase over observed readings':'RAM ที่เพิ่มจากค่าที่วัดได้',
    'First reading → last reading':'ค่าที่วัดครั้งแรก → ครั้งล่าสุด',
    'More':'เพิ่มเติม',
    'Back to latest':'กลับล่าสุด',
    'Apps gaining RAM':'แอปที่ RAM เพิ่มขึ้น',
    'Top 5':'สูงสุด 5 แอป',
    'Increase in the selected period':'RAM ที่เพิ่มขึ้นในช่วงที่เลือก',
    'Bars compare RAM increases across apps.':'แถบแสดงการเพิ่มขึ้นของ RAM เทียบระหว่างแอป',
    'Since first observed':'นับจากครั้งแรกที่พบแอป',
    'No continuous baseline':'ยังไม่มีข้อมูลต้นช่วงที่ต่อเนื่อง',
    'Partial readings':'อ่านข้อมูลได้บางส่วน',
    'Gaps in history':'มีช่วงที่ติดตามไม่ได้',
    'Last observed %1':'พบข้อมูลล่าสุด %1',
    'Last observed':'พบข้อมูลล่าสุด',
    'Observed readings':'ข้อมูลที่ติดตามได้',
    'No comparable increase yet':'ยังไม่พบ RAM เพิ่มขึ้นที่เปรียบเทียบได้',
    'Waiting for app readings':'รอข้อมูลแอป',
    'Apps may be steady, decreasing, or missing a baseline.':'RAM อาจทรงตัว ลดลง หรือยังไม่มีข้อมูลต้นช่วง',
    'Live readings will appear here as they arrive.':'ข้อมูลสดจะแสดงที่นี่เมื่อเริ่มอ่านได้',
    'View all apps':'ดูแอปทั้งหมด',
    'App memory trend':'แนวโน้ม RAM ของแอป',
    'Highest RAM usage · no comparable increase':'แอปใช้ RAM สูงสุด · ยังไม่มีค่าเพิ่มที่เปรียบเทียบได้',
    'RAM at range start → range end':'RAM ต้นช่วง → ปลายช่วง',
    'Loading app trend…':'กำลังโหลดกราฟแอป…',
    'Live readings':'ข้อมูลสด',
    'System RAM change':'RAM รวมที่เปลี่ยนแปลง',
    'Recent events':'เหตุการณ์ล่าสุด',
    'View all':'ดูทั้งหมด',
    'No notable events in this range':'ยังไม่มีเหตุการณ์สำคัญในช่วงนี้',
    'All apps':'แอปทั้งหมด',
    'Event timeline':'ไทม์ไลน์เหตุการณ์',
    'View this time window':'ดูช่วงเวลานี้',
    'Insights':'วิเคราะห์ RAM',
    'Understand when memory grows and which apps change.':'ย้อนดูช่วงที่ RAM เพิ่มขึ้น และแอปที่มีการเปลี่ยนแปลง',
    'New events':'มีเหตุการณ์ใหม่',
    'Historical':'ข้อมูลย้อนหลัง',
    'Tracking paused':'พักการติดตาม',
    'Readings delayed':'ข้อมูลล่าช้า',
    'Tracking':'กำลังติดตาม',
    'Collecting readings':'กำลังเก็บข้อมูล',
    'Partial reading':'ข้อมูลไม่ครบ',
    'Closed':'ปิดแล้ว',
    'Opened in this range':'เปิดในช่วงเวลานี้',
    'Observed in this range':'พบในช่วงเวลานี้',
    'No measured increase':'ยังไม่พบการเพิ่มขึ้นที่วัดได้',
    'Waiting for readings':'รอข้อมูล',
    'RAM increased quickly':'RAM เพิ่มขึ้นอย่างรวดเร็ว',
    'App memory kept increasing':'แอปใช้ RAM เพิ่มต่อเนื่อง',
    'High RAM usage continued':'ใช้ RAM สูงต่อเนื่อง',
    'Optimization':'การ Optimize',
    'App memory history':'ประวัติ RAM ของแอป',
    'System RAM history':'ประวัติ RAM รวม',
    'Use arrow keys to inspect readings. Events are also available in the event list.':'ใช้ปุ่มลูกศรดูข้อมูลแต่ละจุด หรือเลือกจากรายการเหตุการณ์',
    'Apps in this range':'แอปในช่วงเวลานี้',
    'Refresh ranking':'อัปเดตอันดับ',
    'Search apps':'ค้นหาแอป',
    'Increase':'การเพิ่มขึ้น',
    'RAM usage':'การใช้ RAM',
    'Name':'ชื่อ',
    'Sort apps':'เรียงแอป',
    'Application':'แอป',
    'At range end':'ปลายช่วง',
    'Change':'เปลี่ยนแปลง',
    'No app readings in this range.':'ยังไม่มีข้อมูลแอปในช่วงนี้',
    'App readings include shared memory and do not add up to system RAM usage.':'ค่ารายแอปอาจรวมหน่วยความจำที่ใช้ร่วมกัน ผลรวมจึงอาจไม่เท่ากับ RAM รวมของเครื่อง',
    'Events':'เหตุการณ์',
    'Mark all read':'อ่านทั้งหมด',
    'No events met the criteria in this range.':'ยังไม่พบเหตุการณ์ที่เข้าเกณฑ์ในช่วงนี้',
    '5 min':'5 นาที',
    '15 min':'15 นาที',
    '30 min':'30 นาที',
    '1 hour':'1 ชั่วโมง',
    '6 hours':'6 ชั่วโมง',
    '24 hours':'24 ชั่วโมง',
    'Earlier':'ก่อนหน้า',
    'Later':'ถัดไป',
    'Latest':'ล่าสุด',
    'Pause tracking':'พักการติดตาม',
    'Resume tracking':'ติดตามต่อ',
    'Updated %1':'อัปเดต %1',
    '24-hour local history':'ประวัติในเครื่อง 24 ชั่วโมง',
    'SYSTEM RAM CHANGE':'RAM รวมที่เปลี่ยนแปลง',
    'LARGEST APP INCREASE':'แอปที่ RAM เพิ่มมากที่สุด',
    'EVENTS IN THIS RANGE':'เหตุการณ์ในช่วงนี้',
    'Measured changes and sustained high RAM':'การเปลี่ยนแปลงที่วัดได้และช่วง RAM สูง',
    'When memory changed':'RAM เปลี่ยนแปลงเมื่อไร',
    'Select an event marker to inspect the apps in that time window.':'เลือกจุดเหตุการณ์เพื่อดูแอปในช่วงเวลานั้น',
    'Older readings use one-minute summaries with preserved peaks.':'ข้อมูลเก่าสรุปรายหนึ่งนาที โดยเก็บค่าสูงสุดของแต่ละช่วงไว้',
    'Detailed readings · Gaps show when tracking was unavailable.':'ข้อมูลละเอียด · ช่องว่างคือช่วงที่ติดตามไม่ได้',
    'Collecting data. Trend analysis needs about 5 minutes of continuous readings.':'กำลังเก็บข้อมูล การวิเคราะห์แนวโน้มต้องมีข้อมูลต่อเนื่องประมาณ 5 นาที',
    'Some processes could not be read. %1 readable, %2 unavailable.':'อ่านข้อมูลได้บางโปรเซส: อ่านได้ %1 รายการ อ่านไม่ได้ %2 รายการ',
    'History could not be saved. Live tracking continues. %1':'บันทึกประวัติไม่ได้ แต่ยังติดตามข้อมูลสดได้ %1',
    'Details':'รายละเอียด',
    'Close':'ปิด',
    'Observed changes do not by themselves confirm a memory leak.':'แนวโน้มที่พบเพียงอย่างเดียวยังยืนยันไม่ได้ว่าเป็น memory leak',
    'At range start':'ต้นช่วง',
    'Peak':'สูงสุด',
    'Processes at the range end':'โปรเซส ณ ปลายช่วง',
    'Process details are available for the latest 30 minutes of collected data.':'รายละเอียดโปรเซสมีให้ดูในข้อมูล 30 นาทีล่าสุดที่เก็บไว้',
    'Apps that increased in this window':'แอปที่ใช้ RAM เพิ่มขึ้นในช่วงนี้',
    'No comparable app readings for this event.':'ยังไม่มีข้อมูลแอปที่เปรียบเทียบได้สำหรับเหตุการณ์นี้',
    'Open Task Manager':'เปิด Task Manager',
    'Insights data':'ข้อมูลการวิเคราะห์ RAM',
    'History stays on this computer for 24 hours. Tracking continues in Tray.':'เก็บประวัติในเครื่อง 24 ชั่วโมง และติดตามต่อเมื่อย่อไว้ใน Tray',
    'Storage: %1 · Last saved: %2':'พื้นที่ใช้: %1 · บันทึกล่าสุด: %2',
    'Unreadable history was preserved as a backup: %1':'เก็บประวัติที่อ่านไม่ได้เป็นไฟล์สำรองไว้แล้ว: %1',
    'Clear history':'ล้างประวัติ',
    'Retry saving':'ลองบันทึกอีกครั้ง',
    'Clear Insights history?':'ล้างประวัติการวิเคราะห์ RAM?',
    'This removes the collected readings and events from this computer. Tracking will start a new history.':'ข้อมูลและเหตุการณ์ที่เก็บไว้ในเครื่องจะถูกลบ และเริ่มเก็บประวัติใหม่',
    'Cancel':'ยกเลิก',
    'Newer events':'เหตุการณ์ใหม่กว่า',
    'Older events':'เหตุการณ์เก่ากว่า',
    'Page %1 · %2 events':'หน้า %1 · %2 เหตุการณ์',
    'Temporary live history':'ประวัติสดชั่วคราว',
    'Loading this time range…':'กำลังโหลดช่วงเวลานี้…',
    '1-minute summary':'สรุปรายหนึ่งนาที',
}


def main():
    sources={p.stem:{json.loads(s) for s in re.findall(r'qsTr\(("(?:[^"\\]|\\.)*")\)',p.read_text(encoding='utf-8'))} for p in (ROOT/'qml').glob('*.qml')}
    sources['Presentation']=set(TH)
    for locale in ('en_US','th_TH'):
        path=ROOT/'i18n'/f'{locale}.ts'
        tree=ET.parse(path)
        root=tree.getroot()
        contexts={c.findtext('name'):c for c in root.findall('context')}
        existing={m.findtext('source'):m.findtext('translation') for c in contexts.values() for m in c.findall('message')}
        for name,words in sources.items():
            context=contexts.get(name)
            if context is None:
                context=ET.SubElement(root,'context'); ET.SubElement(context,'name').text=name
            known={m.findtext('source') for m in context.findall('message')}
            for source in sorted(words-known):
                translation=source if locale=='en_US' else TH.get(source,existing.get(source))
                if translation is None: raise RuntimeError('Missing Thai translation: '+source)
                message=ET.SubElement(context,'message')
                ET.SubElement(message,'source').text=source
                ET.SubElement(message,'translation').text=translation
        ET.indent(tree)
        tree.write(path,encoding='utf-8',xml_declaration=True)


if __name__=='__main__':main()
