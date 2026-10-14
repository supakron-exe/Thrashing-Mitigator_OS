Thrashing Mitigator — Fluent Premium (0.2.0 preview)
Windows 10/11, 64-bit

วิธีเปิด / Getting started
1. แตก ZIP ทั้งหมดก่อนใช้งาน / Extract the whole ZIP first.
2. ดับเบิลคลิก ThrashingMitigator.exe / Double-click ThrashingMitigator.exe.
3. เก็บโฟลเดอร์ _internal ไว้ข้าง exe เสมอ ไม่ต้องติดตั้ง Python
   Keep _internal next to the exe. Python installation is not required.

เปลี่ยนภาษา: Settings > Language > ไทย
Change language: ตั้งค่า > ภาษา > English
เปลี่ยน Light/Dark ได้จากปุ่มบนหน้าต่างหรือ Settings
Switch Light/Dark using the top button or Settings.

Auto Optimize เริ่มต้นปิด เปิดจากหน้า Auto Optimize เมื่อพร้อม
Auto Optimize is off on first launch. Enable it on the Auto Optimize page.
ปุ่ม X ซ่อนแอปใน Tray; ออกจริงด้วย Tray > Exit / ออกจากแอป
X hides the app in Tray. Use Tray > Exit to quit.

Insights / วิเคราะห์ RAM: กดไอคอนกราฟถัดจาก Auto Optimize
ดูกราฟ RAM รายแอป เหตุการณ์ และประวัติ 24 ชั่วโมงที่เก็บในเครื่อง
ชื่อแอปใช้ข้อมูลที่ Windows ยืนยันได้; หากอ่านชื่อไม่ได้จะแจ้งตามจริง
ข้อมูลเริ่มเก็บเมื่อเปิดแอปและเก็บต่อใน Tray; ไม่มีข้อมูลในช่วงที่ปิดแอป
Insights shows app memory trends and 24-hour local history while the app runs.
Names use Windows metadata; an unavailable name is reported without guessing.
Protected processes may be unavailable. Trend changes do not confirm a memory leak.
History: %LOCALAPPDATA%\ThrashingMitigatorRedesign\insights\insights.db

หากต้องการทำ system-memory steps ของ Deep/Maximum ให้ครบ
คลิกขวา exe > Run as administrator (การเปิดปกติอาจข้ามบางขั้นตอน)
หากมีแอปเปิดอยู่ ให้ออกด้วย Tray > Exit ก่อนเปลี่ยนสิทธิ์
Run as administrator for system-memory steps; ordinary launch can skip some steps.
Exit the existing instance from Tray before changing privilege level.
ค่าผล Optimize ขึ้นกับระบบขณะนั้น หน่วยความจำอาจไม่เพิ่มในบางรอบ
Results depend on the current system; a run may show no memory gain.

Start with Windows ใช้ไฟล์ exe ที่ตำแหน่งนี้ หากย้ายโฟลเดอร์หลังเปิดตัวเลือก
ให้ปิด/เปิด Start with Windows ใหม่เพื่ออัปเดตตำแหน่ง
If you move the folder, turn Start with Windows off/on to update its path.

Settings/log: %LOCALAPPDATA%\ThrashingMitigatorRedesign
ไฟล์นี้ยังไม่มีลายเซ็นดิจิทัล / This package is not digitally signed.
LICENSES และ THIRD_PARTY_NOTICES.md รวมข้อกำหนดและ source URL ของ dependencies
Dependency notices and upstream source URLs are in LICENSES and THIRD_PARTY_NOTICES.md.
BUILD_INFO.json / SOURCE_HASHES.json บอกข้อมูลชุดแจกและ SHA256 ของโค้ดที่ใช้สร้าง
Current application source and rebuild instructions are in the main project folder.
