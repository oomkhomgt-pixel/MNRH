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
   * **อนุสาขาออร์โธปิดิกส์**: อุบัติเหตุ, กระดูกสันหลัง, ข้อเทียม, เวชศาสตร์การกีฬา, มือและจุลศัลยกรรม,
     เท้าและข้อเท้า, ออร์โธปิดิกส์เด็ก, เนื้องอกกระดูก, ไหล่และข้อศอก, การติดเชื้อ, โรคกระดูกเมตาบอลิก,
     วิทยาศาสตร์พื้นฐาน
   * **ผู้นำเสนอ** จากชื่อผู้จัดทำที่ฝังอยู่ในไฟล์ เทียบกับรายชื่อแพทย์ประจำบ้าน
   พร้อมบอกว่ามั่นใจแค่ไหนและจับคำใดได้ ผู้บันทึกตรวจแล้วแก้ได้ทุกช่องก่อนกดยืนยัน
3. **เก็บเป็นหลักฐาน** — บันทึกชื่อไฟล์ จำนวนสไลด์ ข้อความที่อ่านได้ และลายนิ้วมือไฟล์ (SHA-256)
   ซึ่งใช้เตือนได้ด้วยเมื่อมีการนำไฟล์เดิมมาบันทึกซ้ำ
4. **สรุปให้เห็นส่วนขาด** — ความก้าวหน้าเทียบเกณฑ์รายชั้นปี ตารางความครอบคลุมอนุสาขารายบุคคล
   คลังหัวข้อที่เคยนำเสนอ ทะเบียนงานวิจัยรายขั้น และรายการที่ยังไม่ได้รับการรับรองจากอาจารย์
5. **ตาราง 3 แบบในหน้าเดียว** — หน้า “ตาราง: หมุนเวียน · เวร · นำเสนอ” เริ่มด้วยการ์ด *ตอนนี้ใครอยู่หน่วยไหน*
   (หน่วยที่กำลังหมุนเวียน สถานที่ อาจารย์ผู้กำกับ วันสิ้นสุดบล็อก และเซสชันของวันนี้) แล้วสลับดูได้ 3 แบบ
   * **ตารางรายเดือน** — แถวคือแพทย์ประจำบ้าน คอลัมน์คือ 12 เดือนของปีการศึกษา (มิ.ย.–พ.ค.)
     ช่องระบายสีตามสายหรืออนุสาขา: สายฟ้า สายขาว สายแดง สายเหลือง, ELE = elective และตัวย่ออนุสาขาเมื่อวน sub
     (TR, SPN, ARP, HND, PED, SPT, ONC, ER) มีคำอธิบายสีกำกับ เลือกปีการศึกษาได้ กดที่ช่องเพื่อแก้ไขบล็อกนั้น
     พิมพ์และดาวน์โหลด CSV ได้ · สีและตัวย่อของแต่ละหน่วยแก้ได้ในหน้าตั้งค่า
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

## ชื่ออนุสาขาเป็นภาษาอังกฤษทั้งหมด

อนุสาขาที่ระบบเก็บและแสดงใช้ชื่อภาษาอังกฤษอย่างเดียว (Orthopaedic Trauma, Spine, Adult Reconstruction /
Arthroplasty, Sports Medicine / Arthroscopy, Hand & Microsurgery, Foot & Ankle, Paediatric Orthopaedics,
Musculoskeletal Oncology, Shoulder & Elbow, Musculoskeletal Infection, Metabolic Bone Disease /
Osteoporosis, Basic Science / Biomechanics) ทั้งในตัวเลือก ตารางความครอบคลุม รายงาน และไฟล์ CSV
ส่วนคำสำคัญที่ใช้เดาอนุสาขายังมีทั้งคำไทยและคำอังกฤษ เพื่อให้จับสไลด์ที่เขียนด้วยภาษาไทยได้

## การผูกกับมาตรฐาน WFME

ทุกกิจกรรมถูกผูกกับหัวข้อมาตรฐานไว้ตั้งแต่ตอนบันทึก เช่น topic presentation ผูกกับ 2.1, 2.3, 3.1, 6.5 และ
trauma film conference ผูกกับ 2.3, 2.6, 6.2 หน้า “มาตรฐาน WFME” จึงแสดงได้ว่าแต่ละหัวข้อมีหลักฐานอะไรอยู่จริง
กี่รายการ และหัวข้อใดยังไม่มี

ตารางหมุนเวียนรายเดือน ตารางเซสชันประจำสัปดาห์ ตารางนำเสนอ ทะเบียนอาจารย์ และแบบประเมินท้ายเซสชัน
ถูกนับเป็นหลักฐานของหมวด
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
(residents x the 12 months of the Thai academic year) colours each cell by the team or subspecialty the
resident rotates through — the four ward teams named by colour (blue/white/red/yellow), elective, or a
subspecialty service; colours and abbreviations are editable. A **weekly roster** expands the current
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

Tested in headless Chromium: `.pptx`/`.pdf` ingestion, classification, persistence, exports and reports.
Requires a browser with `DecompressionStream` (Chrome/Edge 80+, Safari 16.4+, Firefox 113+).
