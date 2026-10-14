# Windows portable package

ชุดปัจจุบันมีเพียงหนึ่งรุ่นใน `release/`:

- `ThrashingMitigator/` — โฟลเดอร์ที่เปิดใช้งานได้
- `ThrashingMitigator-Windows-x64-Portable.zip` — ไฟล์สำหรับส่งให้เพื่อน
- `ThrashingMitigator-Windows-x64-Portable.zip.sha256` — checksum ของ ZIP
- `latest-build.json` — ข้อมูลชุดปัจจุบัน โดย path อ้างอิงจาก `release/` ไม่ผูกกับเครื่องที่ build

ส่ง ZIP ทั้งไฟล์ เพื่อนแตก ZIP แล้วเปิด `ThrashingMitigator/ThrashingMitigator.exe` ได้บน Windows 10/11 x64 โดยไม่ต้องติดตั้ง Python เก็บ `_internal` ไว้ข้าง exe เสมอ ไม่เปิด exe จากภายใน ZIP หากต้องการสิทธิ์แอดมิน ให้คลิกขวา exe แล้วเลือก Run as administrator

มี Overview, Auto Optimize, Insights, Settings, English/ไทย, Light/Dark และ Tray เช่นเดียวกับ source ปัจจุบัน Insights แสดงชื่อแอปจากข้อมูลที่ Windows ยืนยันได้และเก็บประวัติในเครื่อง 24 ชั่วโมง Auto และ Start with Windows ปิดตามค่าเริ่มต้นบน profile ใหม่ ผล Optimize รายงานตามค่าที่วัดได้ รวมถึงขั้นตอนที่ข้ามและกรณี RAM ไม่เพิ่ม

ข้อมูลและ log อยู่ใน `%LOCALAPPDATA%\ThrashingMitigatorRedesign` เช่นเดิม การเปิด source และ exe ใช้ single instance เดียวกัน ให้ออกด้วย Tray > Exit ก่อนสลับตัวที่ทดลอง

## สร้างชุดแจก

ใช้ environment ของโปรเจกต์ที่ root (Python 3.11 Windows x64 / PySide6 6.7.2):

```powershell
.\build_exe.cmd
```

ตัวเปิดติดตั้ง build tools ตาม `requirements-build.txt` แล้วเรียก `tools/build_exe.py` โดยไม่เปลี่ยนเลขรุ่น 0.2.0-preview จากการจัดโครงสร้างครั้งนี้

ขั้นตอน build สร้าง icon และ resources ใหม่ แล้วเก็บ candidate ใน `build/package-<เวลา>/candidate/` ใช้ PyInstaller 6.22.3 และ hooks-contrib 2026.8 สร้าง windowed portable folder จาก `packaging/ThrashingMitigator.spec` ไม่มี console และไม่บังคับสิทธิ์แอดมิน

ก่อนแทนที่ `release/` จะตรวจ ZIP และเปิด exe ที่แตกไปยัง path ชั่วคราวซึ่งมีช่องว่าง/ภาษาไทย โดยล้าง Python/Qt environment และใช้ profile ชั่วคราว ตรวจ RAM สด, Insights, ทั้งสองภาษา/ธีม, fonts/logo, Tray, single instance และ Exit ไม่เรียก Optimize และไม่แก้ Windows startup registration ของผู้ใช้ หากตรวจไม่ผ่าน ชุดเดิมใน `release/` ยังคงอยู่ หากการแทนที่ล้มเหลวจะคืนชุดก่อนหน้า

หากต้องการสร้างและตรวจ candidate โดยยังไม่แทนที่ชุดปัจจุบัน:

```powershell
.\.venv\Scripts\python.exe tools\build_exe.py --stage-only
```

`BUILD_INFO.json` ในโฟลเดอร์ exe บันทึกเวลาสร้าง dependencies และ checksum ของ exe/โค้ด ส่วน `SOURCE_HASHES.json` ระบุ SHA256 ของไฟล์ต้นฉบับที่ใช้ build เพื่อยืนยันว่าชุดแจกมาจากโค้ดล่าสุด ไม่มีสำเนา Source.zip ซ้ำใน release เพราะ source และเครื่องมือ rebuild อยู่ที่ root ของโปรเจกต์นี้

## ตรวจชุดที่เผยแพร่แล้ว

```powershell
.\.venv\Scripts\python.exe tests\check_packaged_exe.py
```

รายงานและภาพจาก exe จริงอยู่ใน `build/qa/package/` ซึ่ง Git ไม่ติดตาม ตัวตรวจยืนยัน dependencies โหลดจาก `_internal` และชื่อแอปจาก Windows file description ทำงานในชุด frozen ด้วย

Qt libraries/plugins อยู่แยกใน `_internal/PySide6` เพื่อให้ใช้ shared libraries และเปลี่ยนเป็น compatible builds ได้ QML/assets/fonts/translations ของแอปและ FluentUI อยู่ใน compiled resources ส่วน hook เก็บ QtQuick, QtQml, Qt5Compat.GraphicalEffects และ Qt.labs.qmlmodels ที่ใช้งาน

LICENSES เก็บ MIT notice ของ FluentUI, ประวัติ patch ในโปรเจกต์, Python license, metadata/license ของ dependencies และข้อความ LGPL/GPL/Qt exception ครบ `THIRD_PARTY_NOTICES.md` ระบุ source URL ของ FluentUI/Qt/PySide6/Python พร้อมข้อมูลการแทนที่ Qt libraries

ชุดนี้ยังไม่ได้เซ็นดิจิทัล การตรวจบนเครื่องพัฒนาไม่แทนการทดลองเครื่องเพื่อนหรือ Windows VM ที่สะอาด
