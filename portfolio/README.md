# แฟ้มสะสมงานแพทย์ประจำบ้านออร์โธปิดิกส์ — หน้าสาธิต

หน้าเว็บสาธิตสำหรับติดตามความก้าวหน้าการฝึกอบรมแพทย์ประจำบ้าน กลุ่มงานออร์โธปิดิกส์
โรงพยาบาลมหาราชนครราชสีมา

**เปิดที่:** https://oomkhomgt-pixel.github.io/MNRH/portfolio/

---

## หน้านี้ทำอะไร

ติดตามกิจกรรมตามหลักสูตรของแพทย์ประจำบ้านแต่ละคน โดยให้ **การบันทึกเกิดขึ้นตอนที่นำเสนอสไลด์**
แทนการมานั่งกรอกย้อนหลัง

1. **รับสไลด์** — ลากไฟล์ `.pptx` หรือ `.pdf` ที่ใช้นำเสนอมาวาง หน้าเว็บจะอ่านไฟล์ในเครื่อง
   แล้วดึงชื่อเรื่อง ผู้จัดทำ วันที่สร้าง จำนวนสไลด์ และข้อความในทุกสไลด์ออกมา
2. **เดาให้ก่อน** — จากคำที่พบในสไลด์ ระบบเดา
   * **ประเภทกิจกรรม**: นำเสนอหัวข้อวิชาการ / pre-op conference / post-op conference & M&M /
     trauma film conference / journal club / ความก้าวหน้างานวิจัย
   * **อนุสาขาออร์โธปิดิกส์** (9 อนุสาขา ใช้ชื่อภาษาอังกฤษ): Orthopaedic Trauma, Spine, Arthroplasty, Sports,
     Hand & Microsurgery, Foot & Ankle, Paediatric Orthopaedics, Musculoskeletal Oncology,
     Musculoskeletal Infection
   * **ผู้นำเสนอ** จากชื่อผู้จัดทำที่ฝังอยู่ในไฟล์ เทียบกับรายชื่อแพทย์ประจำบ้าน
   พร้อมบอกว่ามั่นใจแค่ไหนและจับคำใดได้ ผู้บันทึกตรวจแล้วแก้ได้ทุกช่องก่อนกดยืนยัน
3. **เก็บเป็นหลักฐาน** — บันทึกชื่อไฟล์ จำนวนสไลด์ ข้อความที่อ่านได้ และลายนิ้วมือไฟล์ (SHA-256)
   ซึ่งใช้เตือนได้ด้วยเมื่อมีการนำไฟล์เดิมมาบันทึกซ้ำ
4. **สรุปให้เห็นส่วนขาด** — ความก้าวหน้าเทียบเกณฑ์รายชั้นปี ตารางความครอบคลุมอนุสาขารายบุคคล
   คลังหัวข้อที่เคยนำเสนอ ทะเบียนงานวิจัยรายขั้น และรายการที่ยังไม่ได้รับการรับรองจากอาจารย์
5. **ตาราง 3 แบบในหน้าเดียว** — หน้า “ตาราง: หมุนเวียน · เวร · นำเสนอ” เริ่มด้วยการ์ด *ตอนนี้ใครอยู่หน่วยไหน*
   (หน่วยที่กำลังหมุนเวียน สถานที่ อาจารย์ผู้กำกับ วันสิ้นสุดบล็อก และเซสชันของวันนี้) แล้วสลับดูได้ 3 แบบ
   * **ตารางรายเดือน** — แถวคือแพทย์ประจำบ้าน คอลัมน์คือ 12 เดือนของปีการศึกษา **เริ่ม ก.ค. จบ มิ.ย.**
     ช่องระบายสีตามหน่วยที่หมุนเวียน: สายฟ้า สายขาว สายแดง สายเหลือง, หน่วยอนุสาขา (TR/PED, HND/ONC, FT/SPT, SPN, ARP),
     การวนนอกภาควิชา (ANES, RHEU, TRS, PM&R) และ ELE = free elective · ★ = ปี 3 ที่ทำหน้าที่หัวหน้าสายในเดือนนั้น
     มีคำอธิบายสีกำกับ เลือกปีการศึกษาได้ กดที่ช่องเพื่อแก้ไขบล็อกนั้น พิมพ์และดาวน์โหลด CSV ได้
     · ปุ่ม **“สร้างแผนอัตโนมัติ”** จัดแผนทั้งปีให้ตามกติกาด้านล่าง แล้วรายงานข้อที่ยังไม่ลงตัวให้ตรวจ
     · สี ตัวย่อ ประเภทหน่วย และ subspecialty ที่หน่วยครอบคลุม แก้ได้ในหน้าตั้งค่า
   * **ตารางเวรรายสัปดาห์** — แถวคือแพทย์ประจำบ้าน คอลัมน์คือวัน แต่ละช่องคือหนึ่งเซสชัน (OR / OPD / ward round /
     conference / เวรนอกเวลา) พร้อม **อาจารย์ผู้รับผิดชอบของเซสชันนั้น** เซสชันถูกสร้างอัตโนมัติจาก *ช่วงหมุนเวียน*
     ประกอบกับ *ตารางกิจกรรมประจำสัปดาห์ของหน่วย* จึงไม่ต้องกรอกทีละวัน
   * **ตารางนำเสนอ** — ลงว่า **วันไหน ใครนำเสนอเรื่องอะไร เวลาใด ที่ห้องไหน และอาจารย์ท่านใดเป็นผู้ดำเนินการ**
     มีรายการที่กำลังจะถึง และตารางทั้งหมดพร้อมตัวกรอง แต่ละแถวมีสถานะ: ตามกำหนด / บันทึกสไลด์แล้ว /
     ยังไม่มีบันทึกสไลด์ — เมื่อวางไฟล์สไลด์เข้าระบบ ระบบจะจับคู่กับรายการในตารางให้เอง (คนเดียวกัน ประเภทเดียวกัน
     วันใกล้กันไม่เกิน 3 วัน) จึงเห็นได้ทันทีว่าการนำเสนอครั้งไหนยังไม่มีหลักฐานเก็บไว้
6. **ประเมินท้ายเซสชัน** — กดที่เซสชันใดก็ได้เพื่อบันทึกแบบประเมิน: ผู้ประเมิน (ตั้งต้นเป็นอาจารย์ผู้รับผิดชอบเซสชันนั้น),
   คะแนน 3 ด้าน (ความรู้/การตัดสินใจ, ทักษะหัตถการ, ความเป็นวิชาชีพและการสื่อสาร), ระดับการปฏิบัติงานด้วยตนเอง
   ที่ไว้วางใจได้ (entrustment 1–5) และข้อเสนอแนะทันทีหลังเซสชัน
   หน้าเดียวกันมีกระดาน **“เซสชันที่รอการประเมิน แยกตามอาจารย์ผู้รับผิดชอบ”** ย้อนหลัง 14 วัน
   เพื่อให้เห็นว่าใครยังค้างประเมินอยู่กี่เซสชัน จำนวนครั้งที่ประเมินแล้วนับรวมเป็นเกณฑ์ความก้าวหน้าของแต่ละชั้นปีด้วย
7. **พิมพ์ออกได้** — แฟ้มสะสมงานรายบุคคล (พร้อมช่องลงนาม) และรายงานหลักฐานตามมาตรฐาน WFME
   รวมถึงดาวน์โหลดเป็น CSV

## เชื่อมกับระบบคิวห้องผ่าตัดเพื่อลง logbook

หน้า **“Logbook เคสผ่าตัด”** ดึงรายการเคสจากระบบคิวห้องผ่าตัดมาใช้เป็นสมุดบันทึกการผ่าตัดของแพทย์ประจำบ้าน
ต่อได้ 3 ทาง เลือกทางที่ตรงกับการติดตั้งจริง

1. **อ่านจากหน้าระบบคิวในที่เก็บเดียวกัน** — กดปุ่มเดียว หน้านี้จะอ่าน `../index.html` (หน้าสาธิตระบบคิว)
   ดึงข้อมูลเคสที่ฝังอยู่ในหน้านั้นออกมา ใช้ได้เมื่อเปิดผ่าน GitHub Pages หรือเว็บเซิร์ฟเวอร์
   (เปิดจาก `file://` เบราว์เซอร์จะไม่ยอมให้อ่านไฟล์ข้างเคียง)
2. **นำเข้าไฟล์** — JSON ที่ export จากระบบคิว หรือ CSV ที่มีหัวคอลัมน์
   `date, hn, diagnosis, operation, subspecialty, surgeon, assistant, room, anesthesia, asa, side, duration, id`
3. **ต่อ API ของระบบจริง** — ตั้งที่อยู่ระบบคิวในหน้าตั้งค่าการเชื่อมต่อ ระบบจะเรียก
   `GET {ที่อยู่}/api/cases?scope=all&includeClosed=true` พร้อม cookie ของผู้ใช้ (ต้องล็อกอินระบบคิวอยู่ และฝั่งระบบคิวต้องอนุญาต CORS)
   หน้านี้ไม่เก็บรหัสผ่านหรือโทเคนใด ๆ

เคสซ้ำจะถูกอัปเดตทับ ไม่สร้างรายการซ้ำ (จับคู่ด้วยเลขที่เคสของระบบคิว) และ **ชื่อผู้ป่วยไม่ถูกนำเข้ามาโดยตั้งใจ**
สิ่งที่นำเข้าคือ วันที่ HN อายุ เพศ การวินิจฉัย การผ่าตัด ข้าง อนุสาขา ห้อง ประเภทเคส การระงับความรู้สึก ASA
ระยะเวลา และชื่อศัลยแพทย์หลัก · HN แสดงแบบปิดบังไว้ก่อน กดเปิดดูเต็มได้เมื่อต้องตรวจสอบ

### ใครร่วมผ่าตัดเคสไหน

ข้อจำกัดที่ต้องรู้: **ระบบคิวรุ่นปัจจุบันบันทึกเฉพาะศัลยแพทย์หลัก ยังไม่มีช่องผู้ช่วยผ่าตัด**
(ในข้อมูลสาธิต `assistantSurgeonNames` ว่างทุกเคส) หน้านี้จึงเติมชั้น “ผู้ร่วมผ่าตัด” ให้เอง โดย

- จับคู่ชื่อที่มีอยู่ในเคส (ศัลยแพทย์หลัก ผู้ช่วย ผู้ลงข้อมูล) กับรายชื่อแพทย์ประจำบ้านให้อัตโนมัติ
- ถ้าจับคู่ไม่ได้ **เสนอชื่อจากตารางหมุนเวียน** — ใครหมุนเวียนอยู่หน่วยที่ตรงกับอนุสาขาของเคสในวันนั้น
  กดปุ่มเดียวเพื่อเติมทั้งหมด แล้วค่อยไล่แก้บทบาททีหลัง
- บทบาทที่บันทึกได้: ผู้ผ่าตัดหลัก / ผู้ช่วยที่ 1 / ผู้ช่วยที่ 2 / ผู้สังเกตการณ์ พร้อมช่องให้อาจารย์รับรอง

จำนวนเคสแยกตามบทบาทนับรวมเป็นเกณฑ์ความก้าวหน้าของแต่ละชั้นปี (ตั้งค่าได้) แสดงในแฟ้มรายบุคคล
และพิมพ์เป็น logbook รายคนได้ (สรุปตามอนุสาขา + รายการเคสเรียงลำดับ + ช่องลงนามอาจารย์ผู้รับรอง)

**ถ้าอยากให้อัตโนมัติเต็มรูปแบบ** ระบบคิวต้องเพิ่มการบันทึกผู้ร่วมผ่าตัดในเคส เช่นฟิลด์
`attendees: [{ userId, role }]` หรือเติมชื่อลง `assistantSurgeonNames` ให้ครบ เมื่อมีข้อมูลนั้นแล้ว
หน้านี้จะจับคู่ให้เองทันทีโดยไม่ต้องยืนยันทีละเคส

## กติกาการจัดหมุนเวียนที่ระบบใช้

ปีการศึกษาเริ่ม **1 กรกฎาคม** จบ **30 มิถุนายน** แบ่งเป็น 12 บล็อก บล็อกละ 1 เดือน

| ชั้นปี | การหมุนเวียน |
|---|---|
| ปี 1 | วนนอกภาควิชา 3 เดือน — วิสัญญีวิทยา, โรคข้อ (rheumatology), ศัลยกรรมอุบัติเหตุ อย่างละ 1 เดือน · ที่เหลือวนตามสาย |
| ปี 2 | เวชศาสตร์ฟื้นฟู (PM&R) 1 เดือน · ที่เหลือวนตามสาย |
| ปี 3 | วนตามสาย + free elective 3 เดือน (ไปพร้อมกันได้ไม่เกิน 2 คน) · ทำหน้าที่หัวหน้าสายเมื่อสายนั้นไม่มีปี 4 |
| ปี 4 | วนตาม sub/สาย ถึงเดือนกุมภาพันธ์ · จากนั้น free elective พร้อมกันทั้งชั้นปี มี.ค.–มิ.ย. |

เงื่อนไขเพิ่มเติมที่ตัวจัดแผนพยายามรักษา

- การวนนอกภาควิชาของชั้นปีเดียวกัน **ไม่ให้ชนกัน** (ไม่เกิน ⌈จำนวนคนในชั้นปี ÷ 3⌉ คนต่อเดือน)
- การลงสาย **แบ่งจำนวนคนให้เท่ากันที่สุด** ในแต่ละเดือน และเลี่ยงการอยู่สายเดิมสองเดือนติด
- หน่วยอนุสาขาที่อยู่คู่กัน: **Trauma/Paediatrics · Hand/Tumour · Foot & Ankle/Sports** ส่วน Spine และ Arthroplasty แยกหน่วย
- ไม่มีการวน ER เป็นบล็อกแยก (งานห้องฉุกเฉินอยู่ในเวรของแต่ละสาย)

ปุ่ม “สร้างแผนอัตโนมัติ” สร้างแผนทั้งปีตามกติกานี้ แล้วรายงานสิ่งที่ยังไม่ลงตัว เช่น เดือนที่สายใดไม่มีคนลง
หรือเดือนที่ elective เต็มเพดาน เพื่อให้ผู้จัดตารางแก้เองต่อได้ (ทุกบล็อกยังกดแก้ทีละช่องได้ตามปกติ)

## ชื่ออนุสาขาเป็นภาษาอังกฤษทั้งหมด

อนุสาขาที่ระบบเก็บและแสดงมี 9 อนุสาขา ใช้ชื่อภาษาอังกฤษอย่างเดียว ทั้งในตัวเลือก ตารางความครอบคลุม รายงาน
และไฟล์ CSV

| id | ชื่อที่แสดง |
|---|---|
| `trauma` | Orthopaedic Trauma |
| `spine` | Spine |
| `arthroplasty` | Arthroplasty |
| `sports` | Sports |
| `hand` | Hand & Microsurgery |
| `foot` | Foot & Ankle |
| `pediatric` | Paediatric Orthopaedics |
| `oncology` | Musculoskeletal Oncology |
| `infection` | Musculoskeletal Infection |
| `general` | General / Unclassified (ไม่ถูกนับในตารางความครอบคลุม) |

หัวข้อที่เคยอยู่ในหมวด Shoulder & Elbow, Metabolic Bone Disease และ Basic Science ถูกยุบเข้าหมวดที่รับช่วงต่อ
(ไหล่ → Sports, กระดูกพรุน/fragility fracture และ fracture healing → Orthopaedic Trauma, ที่เหลือ → General)
พร้อมคำสำคัญของหมวดเดิม ข้อมูลเก่าที่บันทึกไว้ในเบราว์เซอร์จะถูกย้ายให้อัตโนมัติเมื่อเปิดหน้าเว็บครั้งถัดไป

ส่วนคำสำคัญที่ใช้เดาอนุสาขายังมีทั้งคำไทยและคำอังกฤษ เพื่อให้จับสไลด์ที่เขียนด้วยภาษาไทยได้

## การผูกกับมาตรฐาน WFME

ทุกกิจกรรมถูกผูกกับหัวข้อมาตรฐานไว้ตั้งแต่ตอนบันทึก เช่น topic presentation ผูกกับ 2.1, 2.3, 3.1, 6.5 และ
trauma film conference ผูกกับ 2.3, 2.6, 6.2 หน้า “มาตรฐาน WFME” จึงแสดงได้ว่าแต่ละหัวข้อมีหลักฐานอะไรอยู่จริง
กี่รายการ และหัวข้อใดยังไม่มี

logbook เคสผ่าตัดที่ดึงจากระบบคิว ตารางหมุนเวียนรายเดือน ตารางเซสชันประจำสัปดาห์ ตารางนำเสนอ ทะเบียนอาจารย์
และแบบประเมินท้ายเซสชัน ถูกนับเป็นหลักฐานของหมวด
2.4 / 2.5 / 2.6 (โครงสร้างหลักสูตรและความสัมพันธ์กับงานบริการ), 3.1 / 3.2 (วิธีการประเมินและความเชื่อมโยงกับการเรียนรู้),
5.1 / 5.2 (อาจารย์และหน้าที่ของอาจารย์), 6.2 (สถานที่ฝึกปฏิบัติทางคลินิก), 6.4 (ทีมผู้ให้บริการทางคลินิก)
และ 8.4 (การบริหารจัดการและงานธุรการ)

สิ่งที่กิจกรรมการนำเสนอตอบไม่ได้ (พันธกิจ ผลลัพธ์การเรียนรู้ เอกสารหลักสูตร) บันทึกแยกไว้ในหน้า
“ตั้งค่า & ข้อมูล” เป็นข้อความพันธกิจ รายการผลลัพธ์การเรียนรู้ และทะเบียนเอกสาร ที่ผูกเข้ากับหัวข้อมาตรฐานได้เอง

> **ข้อควรระวัง** หมวดและหัวข้อในหน้านี้เรียบเรียงตามโครง 9 หมวดของ *WFME Global Standards for Quality
> Improvement: Postgraduate Medical Education* (ฉบับปรับปรุง ค.ศ. 2015) เพื่อใช้จัดหมวดหลักฐานภายในกลุ่มงาน
> **ยังไม่ได้ทาบถ้อยคำและหมายเลขกับเอกสารต้นฉบับทีละข้อ** ก่อนนำไปใช้ยื่นประเมินจริง ผู้รับผิดชอบหลักสูตร
> ควรตรวจสอบกับเอกสารทางการของ WFME และเทียบกับเกณฑ์ของแพทยสภา/ราชวิทยาลัยแพทย์ออร์โธปิดิกส์
> แห่งประเทศไทยอีกชั้นหนึ่ง แก้ไขข้อความได้ที่ตัวแปร `WFME_AREAS` ในไฟล์ `index.html`

เกณฑ์จำนวนกิจกรรมต่อชั้นปีที่ใส่มาให้เป็น **ค่าตั้งต้นสำหรับสาธิต ไม่ใช่เกณฑ์ทางการ** แก้ได้ในหน้าตั้งค่า

## ข้อจำกัดที่ต้องรู้ก่อนใช้

- **ข้อมูลอยู่ในเบราว์เซอร์ของเครื่องที่เปิดเท่านั้น** (localStorage) ไม่มีเซิร์ฟเวอร์ ไม่มีการรับส่งข้อมูลออกนอกเครื่อง
  เปิดคนละเครื่องจะไม่เห็นข้อมูลของกัน ใช้ปุ่มสำรอง/นำเข้าไฟล์ JSON เพื่อย้ายข้อมูล
- **ไม่ได้เก็บตัวไฟล์สไลด์** เก็บเฉพาะข้อความที่อ่านได้ ชื่อไฟล์ และค่าแฮช ต้นฉบับต้องเก็บไว้ที่อื่นตามระบบของกลุ่มงาน
- `.pptx` อ่านได้ครบที่สุด ส่วน `.pdf` อ่าน metadata ได้เสมอ แต่เนื้อความในสไลด์อ่านได้บ้างไม่ได้บ้าง
  ขึ้นกับวิธีฝังฟอนต์ (ภาษาไทยใน PDF มักอ่านไม่ออก) หน้าเว็บจะบอกเมื่ออ่านไม่ได้และให้กรอกเอง
- การเดาประเภทและอนุสาขาเป็นการช่วยกรอก ไม่ใช่คำตัดสิน ผู้บันทึกต้องตรวจก่อนยืนยันเสมอ
- ข้อมูลตัวอย่างทั้งหมดเป็นข้อมูลสมมติ ไม่มีชื่อบุคคลจริงและไม่มีข้อมูลผู้ป่วย

---

## For readers of this repository

A **demonstration page only**: one self-contained HTML file, no backend, no build step, no external
assets, no network requests. It tracks orthopaedic residents' training activities — topic presentations,
pre-/post-operative conferences, trauma film conferences, journal clubs and research progress.

The point of it is that recording happens *when the resident presents*: drop the `.pptx`/`.pdf` used for
the presentation onto the page and it is parsed in the browser (zip + OOXML for `.pptx`, object/stream
parsing for `.pdf`) to recover the title, author, creation date, slide count and slide text. Keyword
scoring over that text proposes the activity type and the orthopaedic subspecialty; the person recording
checks and confirms. The file's SHA-256 is kept as an evidence fingerprint and for duplicate detection —
the file itself is never uploaded or stored.

Every activity is tagged with the WFME postgraduate-standard sub-areas it can serve as evidence for, so
the programme can print an evidence report per standard area and per resident. The standards skeleton
follows the 9 areas of the WFME Global Standards for Quality Improvement (PGME, 2015 revision) but has
**not been reconciled word-for-word with the official document** — verify before using it for real
accreditation. All demo data is fictitious.

A second half of the page answers *where is each resident right now*, in three tables. A **monthly grid**
(residents x the 12 blocks of the academic year, July through June) colours each cell by what the resident
rotates through — the four ward teams named by colour, a paired subspecialty unit (trauma/paediatrics,
hand/tumour, foot & ankle/sports, spine, arthroplasty), an out-of-department month, or free elective. A
one-click planner lays out a whole year under the programme's rules (first-years take anaesthesia,
rheumatology and trauma surgery for a month each; second-years take PM&R; third-years take three elective
months, at most two of them away at once, and act as team chief when no fourth-year is on that team;
fourth-years rotate subspecialties until February and then take free elective together through June), keeps
out-of-department months from colliding within a year group, balances team numbers, and reports whatever it
could not satisfy. Colours, abbreviations and unit types are editable. A **weekly roster** expands the current
rotation into individual sessions — OR lists, OPD clinics, ward rounds, conferences, on-call — generated
automatically from each service's weekly template, each carrying the staff member responsible for it. A
**presentation schedule** records who presents what, on which day, at what time, in which room, and which
attending moderates; recording a slide deck auto-links to its scheduled entry, so entries with no evidence
recorded stand out.

The staff member responsible for a session evaluates the resident at the end of it: three domain scores, an
entrustment level (1-5) and written feedback, with a per-staff board of sessions still awaiting evaluation
over the last 14 days. Those evaluations count toward each year's requirements and serve as workplace-based
assessment evidence for WFME areas 3, 5 and 7; the rotation schedule evidences 2.4, 2.5, 2.6 and 6.2, and the
presentation schedule 2.5 and 8.4. Subspecialty names are recorded and displayed in English throughout.

**Operative logbook from the OR queue system.** The queue demo in this same repository (`../index.html`)
carries its case data inside the page, so the portfolio can read it directly over one fetch on GitHub Pages;
a JSON/CSV export or a real `GET /api/cases?scope=all&includeClosed=true` endpoint work the same way. Cases
de-duplicate on the queue's own case id, and **patient names are deliberately not imported** — date, HN, age,
sex, diagnosis, operation, side, subspecialty, room, anaesthesia, ASA, duration and the primary surgeon are.
HN is masked in the table until you ask to see it.

The queue system records only the primary surgeon — there is no assistant field yet — so the portfolio adds
the attendance layer: names found on the case are matched against the resident roster, and where that fails
the rotation calendar suggests who was on that service that day, in bulk if wanted. Roles are primary
surgeon, first/second assistant, observer, each with a staff sign-off. Case counts by role feed the per-year
requirements and print as a per-resident logbook. For full automation the queue system would need to record
attendees per case (`attendees: [{userId, role}]`, or a populated assistant list).

Tested in headless Chromium: `.pptx`/`.pdf` ingestion, classification, persistence, exports and reports.
Requires a browser with `DecompressionStream` (Chrome/Edge 80+, Safari 16.4+, Firefox 113+).
