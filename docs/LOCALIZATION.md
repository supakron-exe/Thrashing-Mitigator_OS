# English / ไทย

แอปรองรับ English และภาษาไทย โดยคง English เป็นค่าเริ่มต้น หากเคยบันทึกภาษาไทยไว้ แอปจะใช้ภาษาไทยเมื่อเปิดครั้งถัดไป ตัวเปิด `run_light.cmd` และ `run_dark.cmd` ยังคงเลือกเฉพาะธีมและใช้ภาษาที่บันทึกไว้

## วิธีใช้

เปิดแอปจากโฟลเดอร์โปรเจกต์หลัก แล้วไป **Settings → Language → ไทย** ข้อความเปลี่ยนทันที ไม่ต้องเปิดแอปใหม่ กลับเป็นอังกฤษได้ที่ **ตั้งค่า → ภาษา → English**

แปล Overview, Auto Optimize, Insights, Settings, ผล Optimize, ขั้นตอน/ข้อความระหว่างทำงาน, กราฟ, popup, validation, tooltip, accessibility และเมนู Tray ชื่อแอปและโหมด Standard / Deep / Maximum ยังเหมือนเดิม ใช้เลข 0–9, หน่วย MB/GB และเวลา 24 ชั่วโมงเหมือนเดิม

ฟอนต์ภาษาไทยใช้ Leelawadee UI และ fallback เป็น Tahoma ข้อความทั่วไป 14 px คำอธิบายไทยอย่างน้อย 13 px และเพิ่มความสูงบรรทัด ตัวเลขหลักใช้ขนาดเดิม การ์ดและหัวข้อปรับความสูงตามเนื้อหา พื้นที่วาดกราฟยังคงขนาดตามหน้าต่าง ส่วน popup ยังคงสูง 44 px และกว้างไม่เกิน 340 px โดยไม่จองพื้นที่ใน layout

## การเก็บสถานะ

`settings.json` ที่ `%LOCALAPPDATA%\ThrashingMitigatorRedesign` เก็บคีย์ `language` (`en` / `th`) โดยใช้ตำแหน่งข้อมูลเดิมหลังจัดโครงสร้างโปรเจกต์

การเปลี่ยนภาษาไม่ส่ง `autoChanged`, `Memory.resultChanged` หรือ completion ใหม่ จึงไม่รีเซ็ตเวลารอบ Auto, cooldown, draft, หน้าปัจจุบัน, focus, รายละเอียดที่กางไว้, reading ที่ตรึงบนกราฟ หรืออายุ popup ข้อมูลเดิมใน backend ยังเป็นภาษาอังกฤษและ ID เดิม ใช้ presentation properties แยกในการแสดงคำแปล

หากโหลด catalog หรือบันทึกการตั้งค่าไม่ได้ จะคงภาษาปัจจุบันและแจ้งข้อผิดพลาด หาก catalog ไทยขาดตอนเปิดแอป จะใช้ English เป็น fallback โดยไม่บันทึกว่าภาษาเปลี่ยนสำเร็จ ชื่อ process, path, WinAPI, privilege และรหัสข้อผิดพลาดจากระบบคงข้อความจริงไว้ พร้อมคำอธิบายไทย

## แก้คำแปลและสร้าง resources

แอปใช้ catalog `i18n/en_US.ts` และ `i18n/th_TH.ts` คอมไพล์เป็น `.qm` และฝังใน `qrc:/redesign/i18n` ไม่แก้ source/vendor ของ FluentUI

```powershell
.\.venv\Scripts\python.exe tools\update_translations.py
# แก้รายการ unfinished ใน th_TH.ts ด้วย Qt Linguist หรือ text editor
.\.venv\Scripts\python.exe tools\build_resources.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_*.py'
.\.venv\Scripts\python.exe tests\check_localization.py --theme dark --scale 1.25
```

QML ใช้ `qsTr()` โดย context ตรงกับชื่อไฟล์ เครื่องมือ update เพิ่ม source ใหม่และรักษาคำแปลที่ตรวจแล้ว ข้อความ Python/structured results ใช้ context `Presentation`; เมื่อเพิ่มข้อความใหม่ใน backend ให้เพิ่ม source/translation ใน context นี้ของทั้งสอง catalog ด้วย รักษา `%1`, `%2`, ... ให้ครบ

LanguageController ติดตั้ง catalog ของแอปอีกครั้งหลัง `FluApp.init` เพื่อให้ lookup ของแอปมีลำดับก่อน translator ของ FluentUI ใช้ `QQmlEngine.retranslate()` และ signals ของ presentation แยกตามประเภทข้อมูล ไม่มีการย้าย optimizer หรือเปลี่ยนอัลกอริทึม

## การตรวจสอบ

ชุด unit tests ตรวจ catalog coverage, placeholders, persistence/fallback และการคงสถานะเมื่อสลับภาษา ส่วน GUI checks ตรวจข้อความไทยที่มีสระ/วรรณยุกต์ ตัวเลข ฟอนต์ focus ผล Optimize และ Tray ในสองธีม

```powershell
.\.venv\Scripts\python.exe tests\check_localization.py --theme light --scale 1
.\.venv\Scripts\python.exe tests\check_localization.py --theme dark --scale 1.5
.\.venv\Scripts\python.exe tests\check_insights_visual_matrix.py
```

ภาพใหม่อยู่ใน `build/qa/screenshots/i18n_*` และ `build/qa/insights_visual/` ดูรายการชุดทดสอบใน [VALIDATION.md](VALIDATION.md) ข้อมูล Optimize/เวลา/Startup จำลองอยู่เฉพาะ tests และใช้ settings แยกจากผู้ใช้
