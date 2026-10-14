# Thrashing Mitigator

แอป Windows สำหรับดู RAM สด, Optimize หน่วยความจำ, ตั้ง Auto Optimize และย้อนดู RAM รายแอปใน Insights ใช้ PySide6 + FluentUI QML รองรับ Light/Dark และภาษาไทย/อังกฤษ โปรเจกต์นี้เป็นดีไซน์ล่าสุดรุ่นเดียว โค้ดหลักอยู่ในโฟลเดอร์นี้โดยตรง

## เปิดแอป

ดับเบิลคลิกตัวเปิดที่ต้องการ:

| ตัวเปิด | การทำงาน |
|---|---|
| `run.cmd` | เปิดด้วยธีมและภาษาที่บันทึกไว้ |
| `run_light.cmd` | เปิด Light |
| `run_dark.cmd` | เปิด Dark |
| `run_admin.cmd` | เปิดแบบ Administrator ผ่านหน้าต่าง UAC ของ Windows |
| `setup.cmd` | เตรียมหรือซ่อม environment |
| `build_exe.cmd` | สร้าง EXE และ ZIP สำหรับส่งให้เพื่อน |

ตัวเปิดอ้างอิงตำแหน่งโฟลเดอร์ของตัวเอง ไม่ผูกกับชื่อผู้ใช้หรือ path เครื่องนี้ หากยังไม่มี environment จะเรียก setup ก่อนเปิดแอป ปุ่ม X ซ่อนแอปใน Tray; คลิกขวาไอคอนใน Tray → **Exit** เพื่อออกจริง แอปจะรอให้งาน Optimize ที่กำลังทำอยู่จบก่อนออก เปิดตัวเปิดซ้ำจะเรียกหน้าต่างเดิมกลับมา

ถ้าตัวปกติเปิดอยู่ `run_admin.cmd` จะบอกให้ออกจาก Tray ก่อน จากนั้นเปิดใหม่และกด **Yes** บน UAC หากตัวแอดมินเปิดอยู่แล้วจะเรียก instance เดิมกลับมา โดยไม่บังคับปิดแอป ตัวเปิดแอดมินใช้ธีมที่บันทึกไว้ หรือระบุ `run_admin.cmd --theme dark` ได้

เปิดจาก PowerShell:

```powershell
Set-Location -LiteralPath 'C:\Users\User456\Documents\OS\Thrashing-Mitigator'
.\run.cmd
```

แบบแอดมิน:

```powershell
.\run_admin.cmd
```

## ส่งให้เพื่อน

ส่งไฟล์ `release/ThrashingMitigator-Windows-x64-Portable.zip` เพื่อนแตก ZIP ทั้งชุดแล้วเปิด `ThrashingMitigator/ThrashingMitigator.exe` บน Windows 10/11 x64 โดยไม่ต้องติดตั้ง Python เก็บ `_internal`, `LICENSES` และไฟล์ประกอบทั้งหมดไว้ด้วย หากต้องการสิทธิ์แอดมิน ให้คลิกขวา EXE → **Run as administrator**

ชุดพร้อมใช้ในโปรเจกต์อยู่ที่ `release/ThrashingMitigator/ThrashingMitigator.exe` รายละเอียดรุ่นและ checksum อยู่ใน `release/latest-build.json` และ `BUILD_INFO.json` ภายในชุดแจก ดูวิธี build และตรวจชุดแจกใน [docs/PACKAGING.md](docs/PACKAGING.md)

source และ EXE ใช้ instance และข้อมูลร่วมกัน ให้ออกจาก Tray ก่อนสลับไปทดสอบอีกตัว

## Setup และพัฒนา

Setup ใช้ Python 3.11 และ PySide6 6.7.2 สร้าง `.venv` ในโฟลเดอร์นี้ หากไม่มี runtime จะดาวน์โหลด Python 3.11.16 แบบ portable ที่ล็อก SHA256 มาเก็บใน `.runtime` ครั้งแรกต้องใช้อินเทอร์เน็ต หากย้ายโปรเจกต์ไปตำแหน่งใหม่ ให้ลบเฉพาะ `.venv` แล้วเปิด `setup.cmd` เพื่อสร้าง environment สำหรับตำแหน่งใหม่

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
```

หากมี Python 3.11 ของตัวเอง:

```powershell
.\setup.ps1 -PythonPath 'C:\path\to\python.exe'
```

โครงสร้างหลัก: `main.py` เป็น entry point, `backend/` เป็นระบบ RAM/Optimize/Auto/Insights, `qml/` เป็นหน้าจอ, `assets/` เป็นโลโก้, `i18n/` เป็นภาษา, `vendor/` เป็น FluentUI, `tests/` เป็นชุดทดสอบ และ `tools/` เป็นเครื่องมือพัฒนา ส่วนไฟล์ที่สร้างระหว่างทดสอบหรือ build อยู่ใน `build/` ซึ่ง Git ไม่ติดตาม

หลังแก้ QML, assets หรือภาษา ต้องสร้าง resources ใหม่ ห้ามแก้ `resource_rc.py` ที่สร้างอัตโนมัติ:

```powershell
.\.venv\Scripts\python.exe tools\build_resources.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## การใช้งานและข้อมูลเดิม

- **Overview:** อัปเดต RAM ทุก 2 วินาที เก็บกราฟล่าสุด 60 readings เลือก Standard/Deep/Maximum ได้ โดย Maximum เป็นค่าเริ่มต้น ผล Optimize คงอยู่จนเริ่มรอบใหม่ และกด View ในป๊อปอัปเพื่อดูผลด้านล่างได้
- **Auto:** ตั้งช่วงเวลา หรือเกณฑ์ RAM พร้อมระยะรอและ cooldown; Auto และ Start with Windows ปิดเริ่มต้นบน profile ใหม่ ดู [docs/AUTO_OPTIMIZE.md](docs/AUTO_OPTIMIZE.md)
- **Insights:** เก็บประวัติในเครื่องย้อนหลัง 24 ชั่วโมงและติดตามต่อเมื่อย่อไว้ใน Tray การ์ด Apps gaining RAM เรียงตาม RAM ที่เพิ่มขึ้นในช่วงที่เลือก; หากต้องการดูแอปที่ใช้ RAM มากที่สุด ให้กด View all apps แล้วเรียงตาม RAM usage ดู [docs/INSIGHTS.md](docs/INSIGHTS.md)
- **Settings:** เปลี่ยนภาษา ธีม และปิด animation ได้ ภาษาเริ่มต้นเป็น English ดู [docs/LOCALIZATION.md](docs/LOCALIZATION.md)

ค่าตั้งค่า ประวัติ Insights และข้อมูล optimizer ยังคงอยู่ใน `%LOCALAPPDATA%\ThrashingMitigatorRedesign` การจัดโครงสร้างโปรเจกต์ไม่ย้ายหรือล้างข้อมูลนี้ สำเนาโปรเจกต์ก่อนจัดโครงสร้างเก็บไว้นอกโฟลเดอร์หลักใน `C:\Users\User456\Documents\OS\Thrashing-Mitigator-Backups`

Deep/Maximum ทำงานบางส่วนได้โดยไม่มีสิทธิ์แอดมิน และรายงานขั้นตอนที่ข้ามตามจริง ผล Optimize แสดงค่าที่วัดได้ รวมถึงกรณี RAM ไม่เพิ่ม

## Dependencies และลิขสิทธิ์

Dependencies ล็อกใน `requirements.txt` และ `requirements-build.txt` FluentUI มาจาก [zhuzichu520/PySide6-FluentUI-QML](https://github.com/zhuzichu520/PySide6-FluentUI-QML), commit `617986a17c9850ecb365bc02713433abab79c7aa` พร้อม MIT notice ใน `vendor/` ชุด EXE เก็บเอกสารลิขสิทธิ์ของ Python, Qt, FluentUI และ dependencies ไว้ใน `LICENSES`
