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

## ใช้เป็นแอปบนมือถือ และเป็นเว็บแอปพร้อมกัน

หน้านี้เป็น **PWA** แล้ว — โค้ดชุดเดียวใช้ได้ทั้งบนเบราว์เซอร์และติดตั้งเป็นแอปบนมือถือ

| อุปกรณ์ | วิธีติดตั้ง |
|---|---|
| Android (Chrome/Edge) | กดปุ่ม **“ติดตั้งแอป”** มุมขวาบน หรือเมนู ⋮ → ติดตั้งแอป |
| iPhone / iPad (Safari) | ปุ่มแชร์ → **เพิ่มไปยังหน้าจอโฮม** (iOS ไม่มีปุ่มติดตั้งอัตโนมัติ) |
| คอมพิวเตอร์ | ใช้ในเบราว์เซอร์ได้เลย หรือกดไอคอนติดตั้งในแถบที่อยู่ |

เมื่อติดตั้งแล้วจะเปิดเต็มจอ มีไอคอนของตัวเอง และ **ใช้งานได้แม้ไม่มีสัญญาณ** เพราะหน้าเว็บถูกเก็บไว้ในเครื่อง
ด้วย service worker และข้อมูลอยู่ใน localStorage อยู่แล้ว · เงื่อนไข: ต้องเสิร์ฟผ่าน **https** หรือ **localhost**
(เปิดไฟล์ตรง ๆ แบบ `file://` จะติดตั้งไม่ได้) · หน้า “ตั้งค่า &amp; ข้อมูล” มีปุ่ม **ตรวจการเชื่อมต่อ**
ที่บอกสถานะการติดตั้ง การทำงานออฟไลน์ และสาเหตุเมื่อต่อระบบคิวไม่ได้

**ถ้าต้องการเป็นแอปใน store หรือแจกผ่าน MDM ของโรงพยาบาลจริง ๆ** ห่อไฟล์ชุดนี้ด้วย Capacitor ได้โดยไม่ต้องเขียนใหม่

```bash
npm create @capacitor/app@latest ortho-portfolio     # แล้วคัดลอกไฟล์ในโฟลเดอร์นี้ไปไว้ใน www/
npm i @capacitor/android @capacitor/ios
npx cap add android && npx cap add ios
npx cap sync && npx cap open android                 # build เป็น .apk / .ipa ต่อจากนี้
```

ข้อดีที่ได้เพิ่มจากการห่อเป็นแอป native คือคำขอเครือข่ายวิ่งผ่าน native HTTP layer จึง**ไม่ติดกฎ CORS และ
mixed content ของเบราว์เซอร์** ซึ่งเป็นอุปสรรคหลักเมื่อระบบคิวอยู่ใน intranet (ดูตารางถัดไป)

## เชื่อมกับระบบคิวที่อยู่ใน intranet ได้ไหม

ได้ แต่ผลลัพธ์ขึ้นกับว่า **หน้านี้ถูกวางไว้ที่ไหน** เพราะเบราว์เซอร์บังคับกฎ 2 ข้อ: หน้า https เรียก http ไม่ได้
(mixed content) และการเรียกข้ามโดเมนต้องได้รับอนุญาตจากปลายทาง (CORS)

| วางหน้า portfolio ไว้ที่ | ดึงเคสจากระบบคิว | ข้อควรรู้ |
|---|---|---|
| **เซิร์ฟเวอร์เดียวกับระบบคิวใน intranet** (แนะนำที่สุด) เช่น `https://or-queue.hospital.local/portfolio/` | ได้ทันที เรียก `/api/cases` แบบ same-origin | ไม่ต้องตั้ง CORS ไม่ติด mixed content และใช้ session ที่ผู้ใช้ล็อกอินระบบคิวไว้แล้ว |
| เครื่องแม่ข่ายอื่นใน intranet ที่เป็น **https** | ได้ ถ้าระบบคิวส่ง `Access-Control-Allow-Origin` เป็นโดเมนนี้ และ `Access-Control-Allow-Credentials: true` | ต้องแก้ตั้งค่าฝั่งระบบคิว |
| เครื่องแม่ข่ายอื่นใน intranet ที่เป็น **http** | ได้ ถ้าหน้านี้ก็เป็น http เหมือนกัน | แต่ http จะติดตั้งเป็นแอป (service worker) ไม่ได้ |
| **GitHub Pages** (https สาธารณะ) | **เรียกระบบคิวที่เป็น http ใน intranet ไม่ได้** เบราว์เซอร์บล็อกเพราะ mixed content | ใช้ทางนำเข้าไฟล์ JSON/CSV แทน หรือย้ายไปโฮสต์ใน intranet |
| **แอป native (Capacitor)** | เรียกตรงได้ ข้าม CORS/mixed content | เครื่องต้องอยู่ในวง intranet หรือ VPN ของโรงพยาบาล |
| ไม่เชื่อมเลย | export JSON/CSV จากระบบคิว → นำเข้าที่หน้า Logbook | ใช้ได้เสมอ ไม่ต้องแก้อะไรฝั่งระบบคิว |

สรุปที่ใช้ได้จริงที่สุดสำหรับสถานการณ์ “ระบบคิวเป็นเว็บแอปใน intranet”: **วางไฟล์หน้านี้ไว้บนเซิร์ฟเวอร์เดียวกับระบบคิว**
แล้วให้แพทย์ประจำบ้านติดตั้งจากที่อยู่ intranet นั้นลงมือถือ เวลาอยู่ในโรงพยาบาล (ต่อ wifi โรงพยาบาลหรือ VPN)
จะดึงเคสได้ตรง ๆ ส่วนเวลาอยู่นอกโรงพยาบาลยังเปิดแอปดูและบันทึกได้ตามปกติ เพียงแต่ดึงเคสใหม่ไม่ได้จนกว่าจะกลับเข้าวง

หน้าตั้งค่าการเชื่อมต่อมีสวิตช์ **“ไม่บันทึก HN ลงเครื่องนี้”** สำหรับกรณีติดตั้งบนโทรศัพท์ส่วนตัว
เมื่อเปิดไว้ HN จะไม่ถูกเก็บลงเครื่องเลย (ทั้งข้อมูลเดิมและที่นำเข้าใหม่)

## ควรวางระบบอย่างไรเมื่อ OR queue อยู่ใน intranet แต่ผู้ใช้ต้องใช้จากนอกโรงพยาบาล

ข้อเสนอ: **แยกเป็นสองโซน** และให้ intranet ถูกใช้เฉพาะตอนดึงข้อมูลเคสเท่านั้น

- **โซนนอก** — แฟ้มสะสมงานสำหรับแพทย์ประจำบ้านและอาจารย์ (ติดตั้งเป็นแอปได้ ใช้จากที่บ้านได้ ไม่ต้อง VPN)
- **โซนใน** — ระบบคิวห้องผ่าตัดอยู่ที่เดิม ไม่ต้องเปิดออกสู่อินเทอร์เน็ต

ตัวเชื่อมระหว่างสองโซนเลือกได้ 3 แบบ เรียงจากที่แนะนำ

1. **ให้ผู้ใช้ดึงเองตอนอยู่ในโรงพยาบาล** (ทำได้แล้ววันนี้ ไม่ต้องแก้อะไรฝั่งระบบคิว)
   เปิดแอปตอนต่อ wifi โรงพยาบาล กดดึงเคส ระบบเก็บเฉพาะข้อมูลที่ตั้งระดับไว้ · ไม่ต้องเปิดพอร์ตใด ๆ ออกนอก
   ข้อจำกัดคือต้องอยู่ในวงและต้องกดเอง
2. **สคริปต์ซิงก์ขาเดียวจากข้างใน** (แนะนำถ้าจะทำระบบกลาง) — โปรแกรมเล็ก ๆ รันในโรงพยาบาล ดึงเคสจากระบบคิว
   → ตัดข้อมูลผู้ป่วยออก → ส่งขึ้นเซิร์ฟเวอร์ของแฟ้มสะสมงานผ่าน HTTPS **ขาออกอย่างเดียว**
   ไม่ต้องเปิด inbound ให้ intranet เลย และแพทย์ประจำบ้านเห็นเคสได้โดยไม่ต้องอยู่ในโรงพยาบาล
3. **เปิดระบบคิวออกนอกผ่าน VPN หรือ reverse proxy** — ไม่แนะนำ เพราะเพิ่มพื้นที่เสี่ยงให้ระบบที่มีข้อมูลผู้ป่วยจริง

**สิ่งที่ควรระวังเรื่อง PDPA** ถ้าเซิร์ฟเวอร์ของแฟ้มสะสมงานอยู่นอกโรงพยาบาล

- อย่านำ **ชื่อผู้ป่วยและ HN** ออกไป — ใช้ระดับ “ไม่เก็บข้อมูลผู้ป่วยเลย” ในหน้าตั้งค่าการเชื่อมต่อ
  (เก็บเฉพาะ diagnosis / operation / บทบาท / วันที่) แล้วอ้างอิงกลับด้วยเลขที่เคสของระบบคิวซึ่งไม่มีความหมายนอกโรงพยาบาล
- ถ้าจำเป็นต้องมี HN เพื่อตรวจสอบย้อนกลับ ให้เก็บไว้เฉพาะในเครื่องผู้ใช้หรือในวง intranet เท่านั้น
- ระบบกลางควรมี: ล็อกอินผูกกับบัญชีโรงพยาบาล, สิทธิ์ตามบทบาท (ผู้เข้าฝึกอบรม / อาจารย์ / ผู้จัดหลักสูตร),
  บันทึกการเข้าถึง, การสำรองข้อมูล, กำหนดอายุการเก็บ และเอกสาร ROPA/DPIA ตามที่โรงพยาบาลใช้อยู่

**ลำดับที่แนะนำให้ทำ**

1. *ตอนนี้* — ใช้แบบไฟล์เดียวต่อเครื่องไปก่อน ดึงเคสตอนอยู่ในโรงพยาบาล พิสูจน์ว่ากระบวนการเวิร์กกับกลุ่มงานจริง
2. *ขั้นถัดไป* — เพิ่มเซิร์ฟเวอร์กลางเล็ก ๆ (ผู้ใช้ + สิทธิ์ + ซิงก์) วางใน DMZ ของโรงพยาบาล ผูกกับบัญชีเดิม
   ทั้งแอปอ่านเขียนผ่านชั้น `store` ชั้นเดียว จึงต่อซิงก์ได้โดยไม่ต้องรื้อหน้าอื่น
3. *เมื่อพร้อม* — เพิ่มสคริปต์ซิงก์ขาเดียวจากข้างใน เพื่อให้ logbook เต็มโดยไม่ต้องรอให้ผู้ใช้กดเอง

## ซิงก์ logbook ขึ้นระบบกลางอัตโนมัติ

หน้า Logbook มีปุ่ม **“ซิงก์ระบบกลาง”** ตั้งที่อยู่ปลายทาง เลือกว่าเป็น logbook ของใคร แล้วระบบจะส่งให้เอง —
ส่งตอนเปิดแอป ตอนมีการแก้ไข (รวบไว้ 5 วินาทีแล้วส่งครั้งเดียว) ทุก 10 นาทีถ้ายังค้าง และทันทีที่กลับมาออนไลน์
มีป้ายสถานะบนแถบบน (ซิงก์แล้ว / รอซิงก์ / กำลังซิงก์)

**ข้อมูลที่ส่งออกมีเพียง 3 อย่าง: วันที่ผ่าตัด, diagnosis, operation** (บวก `role` ถ้าผู้ใช้เลือกเปิด)
ไม่มี HN ไม่มีชื่อผู้ป่วย ไม่มีอายุ/เพศ ไม่มีชื่อศัลยแพทย์ · หน้าตั้งค่าจะแสดง **ตัวอย่าง JSON จริงที่จะถูกส่ง**
ให้ตรวจก่อนเปิดใช้

สัญญาข้อมูล: `PUT {url}` รับ `{user, updatedAt, items[]}` และ `GET {url}?user=…` คืน `{items[]}`
มีเซิร์ฟเวอร์อ้างอิงพร้อมทดลองอยู่ที่ [`sync-server/`](../sync-server/) ซึ่ง **ตัดฟิลด์ที่ไม่ได้ตกลงกันทิ้งอีกชั้นหนึ่ง**
ก่อนบันทึก ของจริงควรเพิ่มเส้นทางนี้เข้าไปในเซิร์ฟเวอร์ของระบบคิวที่มีระบบผู้ใช้อยู่แล้ว

## ความสัมพันธ์กับระบบ logbook ของราชวิทยาลัย

ระบบของราชวิทยาลัยเป็น **ที่บันทึกอย่างเป็นทางการ** และต้องแนบฟิล์มกับ operative note ซึ่งเจ้าตัวต้องลงเอง
หน้านี้จึง **ไม่ทำ logbook ซ้อน** และไม่เก็บฟิล์มหรือ op note

บทบาทของหน้านี้คือ **ตัวเตรียมข้อมูลและตัวจับตก**

- ดึงเคสจากระบบคิวมาให้ครบ แล้วระบุบทบาทของแต่ละคนในไม่กี่คลิก (ข้อมูลที่ระบบคิวมีอยู่แล้วไม่ต้องพิมพ์ซ้ำ)
- ทำเครื่องหมาย **“ลงระบบราชวิทยาลัยแล้ว”** รายเคส เพื่อให้เห็นว่าเหลือค้างกี่เคส — มีตัวกรอง “ยังไม่ได้ลงราชวิทยาลัย”
  และปุ่มทำเครื่องหมายทีเดียวทั้งชุดที่กรองไว้
- พิมพ์ **“ใบกรอกราชวิทยาลัย”** เฉพาะเคสที่ยังไม่ได้ลง เรียงตามวันที่ พร้อมช่องติ๊ก เพื่อนั่งกรอกรวดเดียว
- นับจำนวนเคสตามบทบาทเข้าเกณฑ์ของหลักสูตร และใช้เป็นหลักฐาน WFME ในภาพรวมของกลุ่มงาน

ถ้าวันหนึ่งราชวิทยาลัยเปิด API ให้ส่งข้อมูลเข้าโดยตรง ก็ต่อเพิ่มจากจุดนี้ได้ทันที เพราะข้อมูลถูกจัดรูปไว้แล้ว

## ข้อมูลยังแยกกันคนละเครื่อง

ต้องรู้ก่อนตัดสินใจ: ตอนนี้ข้อมูลเก็บใน **เบราว์เซอร์ของแต่ละเครื่อง** ไม่ได้แชร์กัน — แพทย์ประจำบ้านบันทึกในมือถือตัวเอง
อาจารย์เปิดในคอมพิวเตอร์จะไม่เห็นข้อมูลนั้น ย้ายข้อมูลได้ด้วยไฟล์สำรอง JSON เท่านั้น

ถ้าต้องการให้ทุกคนเห็นข้อมูลชุดเดียวกัน (แพทย์ประจำบ้านบันทึก อาจารย์รับรอง ผู้จัดหลักสูตรดูภาพรวม)
ต้องมี **ฐานข้อมูลกลาง** เพิ่มเข้ามา ทางที่สมเหตุสมผลที่สุดคือฝากไว้กับเซิร์ฟเวอร์ของระบบคิวที่มีอยู่แล้ว
เพราะมีระบบผู้ใช้ สิทธิ์ และการบันทึกตาม PDPA อยู่แล้ว โดยเพิ่ม API ประมาณ
`GET/POST /api/portfolio/{residents,activities,rotations,sessions,cases}` แล้วให้หน้านี้ซิงก์ขึ้นลง
ส่วนที่เหลือของแอปไม่ต้องแก้ เพราะทุกอย่างอ่าน–เขียนผ่านชั้น `store` ชั้นเดียว

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
| ปี 4 | วนหน่วยอนุสาขา**ให้ครบทุกหน่วย**ก่อน · เดือนที่เหลือเป็นกำลังเสริมให้สายที่ขาด **สายละไม่เกิน 1 เดือน และไม่จำเป็นต้องลงสายจนครบ** · ตั้งแต่ มี.ค. เป็น free elective พร้อมกันทั้งชั้นปีถึง มิ.ย. |

เงื่อนไขเพิ่มเติมที่ตัวจัดแผนพยายามรักษา

- การวนนอกภาควิชาของชั้นปีเดียวกัน **ไม่ให้ชนกัน** (ไม่เกิน ⌈จำนวนคนในชั้นปี ÷ 3⌉ คนต่อเดือน)
- การลงสาย **แบ่งจำนวนคนให้เท่ากันที่สุด** ในแต่ละเดือน และเลี่ยงการอยู่สายเดิมสองเดือนติด
- **คุมองค์ประกอบรุ่นในสาย** — เกลี่ยรุ่นพี่ (ปี 3–4) และรุ่นน้อง (ปี 1–2) แยกกัน ไม่ให้สายใดมีแต่รุ่นน้องหรือมีแต่รุ่นพี่
  ถ้าสายใดไม่มีรุ่นพี่ ระบบจะย้ายปี 3 จากสายที่มีรุ่นพี่เกินมาให้ก่อน
- **ปี 4 เป็นกำลังเสริม** — ระบบจะกันเดือนให้ครบทุกหน่วยอนุสาขาก่อนเสมอ เดือนที่เหลือจึงถูกจัดไปช่วยสายที่ว่าง
  หรือสายที่ไม่มีรุ่นพี่ โดย **สายละไม่เกิน 1 เดือนต่อคน** ถ้าไม่มีสายไหนขาดก็ไม่ต้องลงสาย (ได้อยู่หน่วยอนุสาขาต่อ)
  และในเดือนเดียวกันปี 4 จะไม่ซ้ำหน่วยอนุสาขากันเอง

หน้าตารางรายเดือนมีตาราง **“องค์ประกอบของแต่ละสาย”** อยู่ใต้ตารางหลัก แสดงจำนวนคนในสายแต่ละเดือนพร้อมสัดส่วน
ปี 3–4 / ปี 1–2 ทำสีให้เห็นทันทีว่าเดือนไหนสายว่าง ไม่มีรุ่นพี่ หรือรุ่นน้องกระจุก

ตรวจแล้วทุกขนาดรุ่น: ปี 4 ทุกคน**วนครบทั้ง 5 หน่วยอนุสาขา** และ**ไม่เคยลงสายเดิมซ้ำ**

ผลทดสอบกับขนาดรุ่นต่าง ๆ (48 ช่อง = 4 สาย × 12 เดือน)

| ขนาดรุ่น | สายว่าง | สายที่ไม่มีรุ่นพี่ | ขนาดสายเฉลี่ย | ปี 4 ได้ sub/สาย/elective |
|---|---|---|---|---|
| ชั้นปีละ 2 คน (8) | 0 | 24 | 1.3 | 5 / 3 / 4 เดือน |
| ชั้นปีละ 3 คน (12) | 0 | 13 | 2.0 | 5–6 / 2–3 / 4 |
| ชั้นปีละ 4 คน (16) | 0 | 3 | 2.6 | 5–6 / 2–3 / 4 |
| ชั้นปีละ 5 คน (20) | 0 | 0 | 3.1 | 6–7 / 1–2 / 4 |

ยิ่งรุ่นใหญ่ยิ่งลงตัว ส่วนรุ่นเล็กมากจะมีบางเดือนที่สายมีแต่รุ่นน้อง ซึ่งเป็นข้อจำกัดของจำนวนคนจริง ๆ
ระบบจึงรายงานออกมาให้ผู้จัดตารางตัดสินใจ แทนที่จะซ่อนไว้
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

**Installable on phones, same code as the web app.** The page ships a manifest, icons and a service worker
scoped to its own folder, so it installs from Android's install button or iOS's *Add to Home Screen*, opens
full-screen and runs with no signal. A diagnostics panel in settings reports install state, offline
readiness, and why a queue connection failed. Wrapping the same files with Capacitor gives a store/MDM
build, whose native HTTP layer also sidesteps browser CORS and mixed-content rules.

**Recommended shape when the queue is intranet-only but people need the portfolio from anywhere:** keep two
zones and let the intranet matter only at the moment cases are pulled. Users fetch cases while on hospital
wifi (works today, nothing to open up), or — once a shared backend exists — a small one-way sync agent
inside the hospital pushes de-identified cases outward over HTTPS, so nothing inbound is exposed. Opening
the queue system through a VPN or reverse proxy is the option to avoid. If the portfolio's server sits
outside the hospital, set the patient-data level to "store nothing", so only diagnosis, operation, role and
date leave the building, with the queue's own case id as the reference back.

**Reaching an intranet-only queue system** depends on where this page is hosted: same server as the queue is
frictionless (same-origin, existing session, no CORS); another intranet host needs CORS with credentials; a
public HTTPS host such as GitHub Pages cannot reach an HTTP intranet service at all (mixed content) and must
fall back to file import. Data still lives per-device; sharing one record across residents and staff would
need a backend, most sensibly an endpoint on the queue system's own server, which the single `store` layer
here is ready to sync against.

**Logbook sync** runs per user and automatically — on load, five seconds after any edit, every ten minutes
while pending, and the moment the device comes back online — with a status chip in the header. The payload is
three fields: operation date, diagnosis, operation (plus role if the user opts in), and the settings dialog
shows the exact JSON before it is enabled. A reference server under `sync-server/` documents the contract and
strips anything outside the agreed field list a second time on the way in.

**The Royal College logbook stays the system of record** — it needs films and operative notes uploaded by the
resident. This page does not duplicate it: it prepares the data (cases pulled from the queue, roles tagged in
a couple of clicks), tracks which cases are still not entered there, and prints a tick-box worksheet of
exactly those, so the official entry is quick rather than reconstructed from memory.

Tested in headless Chromium: `.pptx`/`.pdf` ingestion, classification, persistence, exports and reports.
Requires a browser with `DecompressionStream` (Chrome/Edge 80+, Safari 16.4+, Firefox 113+).
