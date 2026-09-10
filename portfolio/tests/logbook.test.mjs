/* เกณฑ์เคสผ่าตัดใน logbook (RCOST ภาคผนวกที่ 4 — ประสบการณ์การสะสมจำนวนหัตถการ)
   ตัวเลขในตารางเป็นยอดสะสมตลอดหลักสูตรถึงจบชั้นปีนั้น ไม่ใช่โควตาต่อปี
   และเคสขั้นสูงกว่านับแทนขั้นต่ำกว่าได้เสมอ (ผ่าตัดหลักนับเป็นทั้งผู้ผ่าตัดหลัก+ผู้ช่วย+ผู้สังเกตการณ์) */
import { chromium } from "playwright";
import { serve, launchOptions, openAs, suite } from "./lib.mjs";

export default async function run() {
  const t = suite("เกณฑ์ logbook เคสผ่าตัด (RCOST ภาคผนวก 4)");
  const srv = await serve();
  const browser = await chromium.launch(launchOptions());
  try {
    const { page, errors } = await openAs(browser, srv.url, "admin");

    /* ---------- เกณฑ์ตั้งต้นตรงกับตาราง RCOST ทุกชั้นปี ---------- */
    const req = await page.evaluate(() => {
      const rcost = { 1: { caseSurgeon:0,  caseAssist:0,   caseObserve:30 },
                       2: { caseSurgeon:10, caseAssist:30,  caseObserve:30 },
                       3: { caseSurgeon:30, caseAssist:60,  caseObserve:30 },
                       4: { caseSurgeon:50, caseAssist:100, caseObserve:30 } };
      const got = {};
      const matches = [1, 2, 3, 4].every(y => {
        got[y] = { caseSurgeon: store.data.requirements[y].caseSurgeon, caseAssist: store.data.requirements[y].caseAssist,
                   caseObserve: store.data.requirements[y].caseObserve };
        return ["caseSurgeon", "caseAssist", "caseObserve"].every(k => store.data.requirements[y][k] === rcost[y][k]);
      });
      return { matches, got };
    });
    t.check("เกณฑ์เคสผ่าตัดตั้งต้นตรงกับตาราง RCOST ภาคผนวก 4 ทุกชั้นปี", req.matches, JSON.stringify(req.got));

    /* ---------- เคสขั้นสูงกว่านับแทนขั้นต่ำกว่าได้ · เคสสะสมข้ามปีการศึกษา ---------- */
    const r = await page.evaluate(() => {
      const res = store.data.residents.find(x => x.year === 3);
      const ay = currentAY(), prevAy = String(+ay - 1);
      /* ล้างเคสเดิมของคนนี้ให้ผลลัพธ์อ่านง่าย แล้วสร้างชุดควบคุม 3 เคส คนละบทบาท คนละปีการศึกษา */
      store.data.cases = (store.data.cases || []).filter(c => !(c.participants || []).some(p => p.residentId === res.id));
      const mk = (id, role, iso) => ({ id, date: iso, subspecialty:"trauma", complications: [], note:"",
        participants: [{ residentId: res.id, role, why:"ทดสอบ", verified: true }] });
      /* ผ่าตัดหลัก 1 เคสเมื่อปีก่อน (400 วันก่อน คนละ ay กับวันนี้แน่นอน) · ผู้ช่วย 1 เคส + สังเกตการณ์ 1 เคส ปีนี้ */
      store.data.cases.push(mk("case_lb_surgeon", "surgeon", addDaysISO(todayISO(), -400)));
      store.data.cases.push(mk("case_lb_assist", "assist1", todayISO()));
      store.data.cases.push(mk("case_lb_observe", "observer", todayISO()));

      const p = progressFor(res, ay);
      const gaps = gapsFor(res).map(g => g.text);
      store.data.cases = store.data.cases.filter(c => !["case_lb_surgeon", "case_lb_assist", "case_lb_observe"].includes(c.id));
      return {
        ay, prevAy, total: p.logbook.total, inYear: p.logbook.inYear,
        surgeon: p.logbook.surgeon, assist: p.logbook.assist, observer: p.logbook.observer,
        gapObserver: gaps.some(x => /สังเกตการณ์/.test(x)), gapSurgeon: gaps.some(x => /ผู้ผ่าตัดหลัก/.test(x))
      };
    });
    t.eq("เคสเมื่อปีก่อน + เคสปีนี้: total สะสม 3 เคส แต่ inYear เห็นเฉพาะ 2 เคสของปีนี้", [r.total, r.inYear], [3, 2]);
    t.eq("ผู้ผ่าตัดหลัก 1 เคส (แม้เป็นเคสปีการศึกษาก่อน) ยังนับสะสม", r.surgeon.done, 1);
    t.eq("ผู้ช่วยผ่าตัดขึ้นไป = ผ่าตัดหลัก(1) + ผู้ช่วย(1) = 2 — เคสขั้นสูงกว่านับแทนขั้นต่ำกว่าได้", r.assist.done, 2);
    t.eq("ผู้สังเกตการณ์ขึ้นไป = ผ่าตัดหลัก(1) + ผู้ช่วย(1) + สังเกตการณ์(1) = 3", r.observer.done, 3);
    t.check("gapsFor ขึ้นบรรทัดขาดเคสสังเกตการณ์และผู้ผ่าตัดหลักเมื่อยังไม่ครบเกณฑ์ปี 3 (30/30)", r.gapObserver && r.gapSurgeon,
      JSON.stringify(r));

    /* ---------- หน้าตั้งค่า: มีแถวเกณฑ์ผู้สังเกตการณ์ แก้แล้วบันทึกจริงและรอดรีเฟรช ---------- */
    const ui = await page.evaluate(async () => {
      showView("settings");
      const rows = [...document.querySelectorAll("#requirementEditor tr")].map(tr => tr.children[0]?.textContent || "");
      const hasObserveLabel = rows.some(x => /ผู้สังเกตการณ์/.test(x));
      const before = store.data.requirements[1].caseObserve;
      const inp = document.querySelector('[data-req="1|caseObserve"]');
      inp.value = "25";
      inp.dispatchEvent(new Event("change"));
      await new Promise(res => setTimeout(res, 50));
      const afterChange = store.data.requirements[1].caseObserve;
      store.save(); store.load();
      const afterReload = store.data.requirements[1].caseObserve;
      /* คืนค่าเดิมกันชนกับเทสต์อื่นที่รันหลังจากนี้ */
      store.data.requirements[1].caseObserve = before;
      store.save();
      return { hasObserveLabel, before, afterChange, afterReload };
    });
    t.check("หน้าตั้งค่ามีแถวเกณฑ์เคสผ่าตัด — ผู้สังเกตการณ์ขึ้นไป", ui.hasObserveLabel);
    t.eq("แก้เกณฑ์ผู้สังเกตการณ์ปี 1 แล้วบันทึกจริง และรอดรีเฟรชหน้า", [ui.afterChange, ui.afterReload], [25, 25]);

    /* ---------- ส่งต่อไป RCOSTLog: รหัส ICD จากระบบคิว/CSV · ตัวกรอง "รับรองแล้ว รอลง" · กล่องคัดลอกเรียงช่องตามแอป ---------- */
    const imp = await page.evaluate(() => {
      const fromJson = normaliseQueueCase({ id:"q1", date:"2026-08-20", operation:"TKA right", diagnosis:"OA knee",
        icd9:"81.54", icd10:"M17.1", hn:"1", age: 60, sex:"female" });
      const fromAlias = normaliseQueueCase({ id:"q2", date:"2026-08-21", operation:"PFN", diagnosis:"IT fx", procedureCode:"79.35", diagnosisCode:"S72.10" });
      const csv = casesFromCsv("date,hn,diagnosis,icd10,operation,icd9\n2026-08-22,77,OA hip,M16.1,THA left,81.51");
      /* รูปแบบจริงของระบบคิวห้องผ่าตัด: รหัสอยู่ในรายการ procedures[]/diagnoses[] พร้อมช่อง system */
      const fromList = normaliseQueueCase({ id:"q3", date:"2026-08-24", operationText:"Bipolar hemiarthroplasty, right hip",
        diagnoses:[{ code:"M16.1", system:"ICD-10-TM" }, { code:"S72.09", system:"ICD-10-TM", isPrimary:true }],
        procedures:[{ code:"81.52", system:"ICD-9-CM", isPrimary:true }] });
      const emptyList = normaliseQueueCase({ id:"q4", date:"2026-08-25", operation:"PFN", diagnosis:"IT fx", procedures:[], diagnoses:[] });
      return { j9: fromJson.icd9, j10: fromJson.icd10, a9: fromAlias.icd9, a10: fromAlias.icd10,
               c9: csv[0]?.icd9, c10: csv[0]?.icd10, cOp: csv[0]?.operationText,
               l9: fromList.icd9, l10: fromList.icd10, e9: emptyList.icd9 === undefined, e10: emptyList.icd10 === undefined };
    });
    t.eq("ระบบคิวส่ง icd9/icd10 มา → เก็บลงเคส", [imp.j9, imp.j10], ["81.54", "M17.1"]);
    t.eq("ชื่อคีย์อื่นของระบบคิว (procedureCode/diagnosisCode) ก็รับได้", [imp.a9, imp.a10], ["79.35", "S72.10"]);
    t.eq("CSV มีคอลัมน์ icd9/icd10 → อ่านได้", [imp.c9, imp.c10, imp.cOp], ["81.51", "M16.1", "THA left"]);
    t.eq("รูปแบบจริงของระบบคิว (procedures[]/diagnoses[]) → อ่านรหัสหลักของแต่ละชุดได้", [imp.l9, imp.l10], ["81.52", "S72.09"]);
    t.check("รายการรหัสว่าง = ไม่มีรหัสส่งมา (ไม่ใช่ตั้งใจล้าง) จึงไม่ทับของเดิมตอนนำเข้าซ้ำ", imp.e9 && imp.e10);

    /* ดึงข้อมูลรอบใหม่จากระบบคิวที่ไม่ส่งรหัส ICD มา ต้องไม่ล้างรหัสที่กรอกมือไว้ */
    const reimport = await page.evaluate(() => {
      const raw = { id:"q_keep", date:"2026-08-23", operation:"ORIF distal radius", diagnosis:"Distal radius fx", hn:"55", age: 45, sex:"male" };
      importCaseList([raw], "ทดสอบ");
      const c = store.data.cases.find(x => x.sourceRef === "q_keep");
      c.icd9 = "79.32"; c.icd10 = "S52.50"; c.note = "กรอกมือ"; store.save();
      /* ดึงรอบสอง: ข้อมูลชุดเดิม (ไม่มี ICD) + ชื่อหัตถการที่แก้ที่ต้นทาง */
      importCaseList([{ ...raw, operation:"ORIF distal radius, left" }], "ทดสอบ");
      const after = store.data.cases.find(x => x.sourceRef === "q_keep");
      const out = { icd9: after.icd9, icd10: after.icd10, note: after.note, op: after.operation };
      /* CSV ที่มีคอลัมน์ ICD แต่เว้นว่าง = ตั้งใจล้าง (เช่น export ออกไปแก้แล้วนำเข้ากลับ) */
      importCaseList(casesFromCsv("id,date,operation,diagnosis,icd9,icd10\nq_keep,2026-08-23,ORIF distal radius,Distal radius fx,,"), "ทดสอบ CSV", { fromFile: true });
      const cleared = store.data.cases.find(x => x.sourceRef === "q_keep");
      out.clearedIcd9 = cleared.icd9; out.clearedIcd10 = cleared.icd10;
      /* เคสที่ระบบคิวส่งรหัสมาเอง (procedures[]/diagnoses[]) แล้วคนแก้ให้ตรงรายการราชวิทยาลัย
         การดึงข้อมูลรอบใหม่ต้องไม่ย้อนกลับเป็นรหัสของระบบคิว แต่ไฟล์ที่คนเลือกนำเข้าเองยังทับได้ */
      const queued = { id:"q_edit", date:"2026-08-26", operationText:"Bipolar hemiarthroplasty",
        diagnoses:[{ code:"S72.09", system:"ICD-10-TM", isPrimary:true }],
        procedures:[{ code:"81.52", system:"ICD-9-CM", isPrimary:true }] };
      importCaseList([queued], "ทดสอบคิว");
      const q = store.data.cases.find(x => x.sourceRef === "q_edit");
      out.fromQueue = [q.icd9, q.icd10];
      q.icd9 = "81.521"; q.icd10 = "S72.001"; q.icdEdited = true; store.save();
      importCaseList([queued], "ทดสอบคิว");
      const q2 = store.data.cases.find(x => x.sourceRef === "q_edit");
      out.afterRepull = [q2.icd9, q2.icd10];
      importCaseList([{ ...queued, icd9:"81.53", icd10:"S72.08" }], "ทดสอบไฟล์", { fromFile: true });
      const q3 = store.data.cases.find(x => x.sourceRef === "q_edit");
      out.afterFile = [q3.icd9, q3.icd10];
      /* ไฟล์ที่คนแก้เองแล้วนำเข้า ต้องปักธงให้ด้วย ไม่งั้นการดึงคิวรอบถัดไปย้อนรหัสกลับ */
      const fileCase = store.data.cases.find(x => x.sourceRef === "q_edit");
      fileCase.icdEdited = false; store.save();
      importCaseList([{ ...queued, icd9:"81.531", icd10:"S72.081" }], "ทดสอบไฟล์", { fromFile: true });
      importCaseList([queued], "ทดสอบคิว");
      const q4 = store.data.cases.find(x => x.sourceRef === "q_edit");
      out.fileThenQueue = [q4.icd9, q4.icd10];

      /* ไฟล์ CSV ที่แอปนี้ export เอง ต้องนำเข้ากลับได้: จับคู่เคสเดิมได้ ไม่สร้างซ้ำ และอ่านรหัส ICD ที่แก้มาได้ */
      const before = store.data.cases.length;
      const csvText = toCsv(caseCsvRows([store.data.cases.find(x => x.sourceRef === "q_edit")]));
      const edited = csvText.replace("81.531", "81.599");
      importCaseList(casesFromCsv(edited), "ทดสอบ export กลับเข้า", { fromFile: true });
      const q5 = store.data.cases.find(x => x.sourceRef === "q_edit");
      out.roundTrip = { grew: store.data.cases.length - before, icd9: q5.icd9, icd10: q5.icd10 };

      /* คอลัมน์ที่ไฟล์มีแต่เว้นว่าง = ตั้งใจล้าง · คอลัมน์ที่ไฟล์ไม่มี = ไม่แตะของเดิม */
      const c2 = store.data.cases.find(x => x.sourceRef === "q_edit");
      c2.room = "OR1"; c2.primarySurgeon = "อ. ก"; store.save();
      importCaseList(casesFromCsv("id,operation,room\nq_edit,Bipolar hemiarthroplasty,"), "ทดสอบล้างช่อง", { fromFile: true });
      const c3 = store.data.cases.find(x => x.sourceRef === "q_edit");
      out.clearOne = { room: c3.room, surgeon: c3.primarySurgeon };

      /* เคสที่มีผู้ร่วมผ่าตัดหลายคน export ออกมาหลายแถว — แก้ไม่ครบทุกแถวต้องเตือน ไม่ใช่ปล่อยให้แถวท้ายชนะ
         และ round-trip ต้องไม่ลบชื่อศัลยแพทย์หลัก/ห้อง ที่ไฟล์ไม่มีคอลัมน์ให้ */
      const res2 = store.data.residents.slice(0, 2);
      store.data.cases.push({ id:"case_multi", source:"or-queue", sourceRef:"q_multi", date: todayISO(), subspecialty:"trauma",
        operation:"Bipolar hemiarthroplasty", diagnosis:"Femoral neck fx", hn:"7", age: 70, sex:"female",
        room:"OR3", primarySurgeon:"อ. สมชาย", durationMin: 90, icd9:"81.52", icd10:"S72.09", complications:[], note:"",
        participants: res2.map((r, i) => ({ residentId: r.id, role: i ? "assist1" : "surgeon", verified:true })) });
      store.save();
      const multiCsv = toCsv(caseCsvRows([store.data.cases.find(x => x.id === "case_multi")]));
      out.rowsExported = multiCsv.trim().split("\n").length - 1;
      /* แก้แค่แถวแรก → ต้องข้ามเคสนั้นพร้อมบอกชื่อคอลัมน์ตามที่เห็นในไฟล์ ไม่ใช่เลือกแถวใดแถวหนึ่งเงียบ ๆ */
      const lines = multiCsv.split("\n");
      lines[1] = lines[1].replace("81.52", "81.599");
      const mixed = casesFromCsv(lines.join("\n"));
      out.mixedRows = { kept: mixed.length, conflicts: mixed.conflicts || [] };
      /* คอลัมน์เลขที่เคสอยู่ตำแหน่งไหนก็ต้องทำงานเหมือนกัน (ดัชนี 0 ต้องไม่ถูกมองว่า "ไม่มีคอลัมน์") */
      const idFirst = "id,operation,icd9\nq_multi,Bipolar hemiarthroplasty,81.599\nq_multi,Bipolar hemiarthroplasty,81.52";
      const mixed2 = casesFromCsv(idFirst);
      out.idFirst = { kept: mixed2.length, warned: (mixed2.conflicts || []).length };
      /* แก้ทุกแถวให้ตรงกัน → นำเข้าได้ ไม่สร้างซ้ำ และช่องที่ไฟล์ไม่มีคอลัมน์ยังอยู่ */
      const allRows = multiCsv.replace(/81\.52/g, "81.599");
      const n0 = store.data.cases.length;
      importCaseList(casesFromCsv(allRows), "ทดสอบหลายแถว", { fromFile: true });
      const m = store.data.cases.find(x => x.sourceRef === "q_multi");
      out.multi = { grew: store.data.cases.length - n0, icd9: m.icd9, surgeon: m.primarySurgeon, room: m.room, people: m.participants.length };

      store.data.cases = store.data.cases.filter(x => !["q_keep", "q_edit", "q_multi"].includes(x.sourceRef));
      store.save();
      return out;
    });
    t.eq("ดึงข้อมูลซ้ำจากระบบคิวที่ไม่มีรหัส ICD: รหัสที่กรอกมือและบันทึกยังอยู่ ส่วนข้อมูลที่ต้นทางแก้อัปเดตตาม",
         [reimport.icd9, reimport.icd10, reimport.note, reimport.op],
         ["79.32", "S52.50", "กรอกมือ", "ORIF distal radius, left"]);
    t.eq("แต่ถ้าไฟล์นำเข้ามีคอลัมน์ ICD แล้วเว้นว่าง = ตั้งใจล้าง ระบบล้างให้จริง",
         [reimport.clearedIcd9, reimport.clearedIcd10], ["", ""]);
    t.eq("เคสจากระบบคิวได้รหัสมาเอง แล้วคนแก้ให้ตรงรายการราชวิทยาลัย: ดึงรอบใหม่ไม่ย้อนรหัสกลับ · ไฟล์ที่คนนำเข้าเองยังทับได้",
         [reimport.fromQueue, reimport.afterRepull, reimport.afterFile],
         [["81.52", "S72.09"], ["81.521", "S72.001"], ["81.53", "S72.08"]]);
    t.eq("แก้รหัสผ่านไฟล์นำเข้าก็นับว่าคนแก้เอง — ดึงคิวรอบถัดไปไม่ย้อนกลับ",
         reimport.fileThenQueue, ["81.531", "S72.081"]);
    t.eq("ไฟล์ CSV ที่แอปนี้ export เอง นำเข้ากลับได้: จับคู่เคสเดิม ไม่สร้างเคสซ้ำ และรับรหัสที่แก้มา",
         [reimport.roundTrip.grew, reimport.roundTrip.icd9, reimport.roundTrip.icd10], [0, "81.599", "S72.081"]);
    t.eq("ไฟล์มีคอลัมน์ห้องแต่เว้นว่าง = ตั้งใจล้าง (ล้างจริง) · ไม่มีคอลัมน์ศัลยแพทย์ = ไม่แตะของเดิม",
         [reimport.clearOne.room, reimport.clearOne.surgeon], ["", "อ. ก"]);
    t.check("เคสที่มีผู้ร่วมผ่าตัด 2 คน export เป็น 2 แถว · แก้ไม่ครบทุกแถว → ข้ามเคสนั้นพร้อมบอกชื่อคอลัมน์ในไฟล์ ไม่เลือกแถวเงียบ ๆ",
            reimport.rowsExported === 2 && reimport.mixedRows.kept === 0 && /ICD-9/.test(reimport.mixedRows.conflicts.join(" ")),
            JSON.stringify(reimport.mixedRows));
    t.eq("คอลัมน์เลขที่เคสอยู่ตำแหน่งแรกก็ยังตรวจแถวที่ไม่ตรงกันได้ (ดัชนี 0 ไม่ใช่ 'ไม่มีคอลัมน์')",
         [reimport.idFirst.kept, reimport.idFirst.warned], [0, 1]);
    t.eq("แก้ครบทุกแถวแล้วนำเข้า: อัปเดตเคสเดิม ไม่สร้างซ้ำ ผู้ร่วมผ่าตัดคงเดิม และช่องที่ไฟล์ไม่มีคอลัมน์ (ห้อง/ศัลยแพทย์หลัก) ไม่ถูกล้าง",
         [reimport.multi.grew, reimport.multi.icd9, reimport.multi.surgeon, reimport.multi.room, reimport.multi.people],
         [0, "81.599", "อ. สมชาย", "OR3", 2]);

    /* ระดับข้อมูลผู้ป่วยของเครื่องนี้ต้องชนะเสมอ — ทั้งตอนนำเข้าซ้ำและตอนดึงข้อมูลทั้งชุดจากคลาวด์ */
    const priv = await page.evaluate(() => {
      const lvBefore = store.data.orQueue.patientData;
      const raw = { id:"q_priv", date: todayISO(), operation:"ORIF", diagnosis:"Fx", hn:"HN-9988", age: 57, sex:"male" };
      store.data.orQueue.patientData = "full";
      importCaseList([raw], "ทดสอบ");
      const full = store.data.cases.find(x => x.sourceRef === "q_priv");
      const kept = [full.hn, String(full.age), full.sex];
      /* เปลี่ยนเครื่องนี้เป็น "ไม่เก็บข้อมูลผู้ป่วย" แล้วนำเข้าซ้ำ → ต้องล้าง ไม่ใช่คงค่าเดิมไว้ */
      store.data.orQueue.patientData = "minimal";
      importCaseList([raw], "ทดสอบ");
      const after = store.data.cases.find(x => x.sourceRef === "q_priv");
      const cleared = [after.hn, String(after.age), after.sex];
      /* ดึงข้อมูลทั้งชุดจากเครื่องที่เก็บ HN เต็ม → เครื่องนี้ต้องบังคับระดับของตัวเองทันที */
      const cloud = JSON.parse(JSON.stringify(store.data));
      cloud.cases = cloud.cases.map(c => c.sourceRef === "q_priv" ? { ...c, hn:"HN-9988", age: 57, sex:"male" } : c);
      applyMerged(cloud);
      const pulled = store.data.cases.find(x => x.sourceRef === "q_priv");
      const afterPull = [pulled.hn, String(pulled.age), pulled.sex];
      store.data.cases = store.data.cases.filter(x => x.sourceRef !== "q_priv");
      store.data.orQueue.patientData = lvBefore; store.save();
      return { kept, cleared, afterPull };
    });
    t.eq("เครื่องที่ตั้งเก็บข้อมูลผู้ป่วยเต็ม: นำเข้าแล้วได้ HN/อายุ/เพศ", priv.kept, ["HN-9988", "57", "male"]);
    t.eq("เปลี่ยนเป็นไม่เก็บข้อมูลผู้ป่วยแล้วนำเข้าซ้ำ → ล้าง HN/อายุ/เพศ ไม่คงค่าเดิม", priv.cleared, ["", "", ""]);
    t.eq("ดึงข้อมูลทั้งชุดจากคลาวด์ที่มี HN มาด้วย → เครื่องนี้บังคับระดับของตัวเองทันที", priv.afterPull, ["", "", ""]);

    const flt = await page.evaluate(() => {
      const res = store.data.residents.find(x => x.year === 2);
      const mk = (id, verified, rcost) => ({ id, date: todayISO(), subspecialty:"trauma", operation:"OP " + id, diagnosis:"DX", complications:[], note:"",
        hn:"HN" + id, age: 30, sex:"male", icd9:"79.35", icd10:"S72.10",
        participants: [{ residentId: res.id, role:"assist1", why:"ทดสอบ", verified, verifiedBy: verified ? "อ." : "", rcost }] });
      store.data.cases.push(mk("case_rc_todo", true, { done:false, at:"" }),
                            mk("case_rc_unverified", false, { done:false, at:"" }),
                            mk("case_rc_done", true, { done:true, at: todayISO() }),
                            mk("case_rc_val", true, { done:true, at: todayISO(), validated:true, validatedAt: todayISO() }));
      const ids = (want) => { caseFilter.residentId = res.id; caseFilter.rcost = want; return filterCases().map(c => c.id).filter(x => x.startsWith("case_rc_")).sort(); };
      caseFilter.residentId = res.id; caseFilter.rcost = "todo";
      const todoAll = filterCases().length;
      const out = { todo: ids("todo"), no: ids("no"), yes: ids("yes"), validated: ids("validated"),
                    todoCount: rcostTodo(res.id).length, todoAll, resId: res.id };
      caseFilter.residentId = ""; caseFilter.rcost = "";
      return out;
    });
    t.eq("ตัวกรอง 'รับรองแล้ว รอลง RCOSTLog' เห็นเฉพาะเคสที่อาจารย์รับรองแล้วแต่ยังไม่ได้ลง", flt.todo, ["case_rc_todo"]);
    t.eq("ตัวกรอง 'ยังไม่ได้ลง (ทั้งหมด)' รวมเคสที่ยังไม่รับรองด้วย", flt.no, ["case_rc_todo", "case_rc_unverified"]);
    t.eq("ตัวกรอง 'ลงแล้ว' และ 'validated แล้ว'", [flt.yes, flt.validated], [["case_rc_done", "case_rc_val"], ["case_rc_val"]]);
    t.check("rcostTodo() นับเท่าตัวกรอง todo (รวมเคสสาธิตของคนนี้)", flt.todoCount === flt.todoAll && flt.todoCount >= 1, flt.todoCount + " vs " + flt.todoAll);

    /* มุมทั้งกลุ่มงานของอาจารย์ (ไม่ได้เลือกคน): "ลงแล้ว" กับ "ยังไม่ได้ลง" ต้องไม่ทับกัน
       เคสที่คนหนึ่งลงแล้วอีกคนยังไม่ลง ต้องนับเป็น "ลงแล้ว" ไม่ใช่โผล่ทั้งสองฝั่ง */
    const grp = await page.evaluate(() => {
      const [a, b] = store.data.residents.filter(x => x.year === 2).slice(0, 2);
      const mk = (id, ps) => ({ id, date: todayISO(), subspecialty:"trauma", operation:"OP " + id, diagnosis:"DX",
        complications:[], note:"", hn:"HN", age: 30, sex:"male", participants: ps });
      store.data.cases.push(
        mk("case_gr_half", [{ residentId: a.id, role:"surgeon", verified:true, rcost:{ done:true, at: todayISO() } },
                            { residentId: b.id, role:"assist1", verified:true, rcost:{ done:false, at:"" } }]),
        mk("case_gr_none", [{ residentId: a.id, role:"surgeon", verified:true, rcost:{ done:false, at:"" } },
                            { residentId: b.id, role:"assist1", verified:true, rcost:{ done:false, at:"" } }]));
      const ids = (want) => { caseFilter.residentId = ""; caseFilter.rcost = want;
        return filterCases().map(c => c.id).filter(x => x.startsWith("case_gr_")).sort(); };
      const out = { yes: ids("yes"), no: ids("no"), todo: ids("todo") };
      store.data.cases = store.data.cases.filter(c => !c.id.startsWith("case_gr_"));
      caseFilter.residentId = ""; caseFilter.rcost = "";
      return out;
    });
    t.eq("ดูทั้งกลุ่ม: เคสที่มีคนลงแล้ว = 'ลงแล้ว' · เคสที่ยังไม่มีใครลง = 'ยังไม่ได้ลง/รอลง' และไม่ทับกัน",
         [grp.yes, grp.no, grp.todo], [["case_gr_half"], ["case_gr_none"], ["case_gr_none"]]);

    /* อาจารย์ติ๊ก Validated ในกล่องแก้ไขเคส → ถือว่าลงแล้วด้วย และบันทึกจริง */
    const val = await page.evaluate(async () => {
      editCaseParticipants("case_rc_todo");
      const rid = store.data.residents.find(x => x.year === 2).id;
      const hasCol = !!document.querySelector('#dlgBody [data-rcostval="' + rid + '"]');
      const icd9Input = document.querySelector('#dlgBody [name="icd9"]');
      icd9Input.value = "86.22";
      document.querySelector('#dlgBody [data-rcostval="' + rid + '"]').checked = true;
      document.querySelector("#dlgFoot .btn-primary").click();
      await new Promise(r => setTimeout(r, 50));
      const c = store.data.cases.find(x => x.id === "case_rc_todo");
      const p = c.participants.find(x => x.residentId === rid);
      return { hasCol, done: p.rcost.done, validated: p.rcost.validated, icd9: c.icd9, state: rcostState(p), icdEdited: !!c.icdEdited };
    });
    t.check("กล่องแก้ไขเคสมีคอลัมน์ Validated ใน RCOSTLog", val.hasCol);
    t.eq("ติ๊ก validated โดยยังไม่ติ๊กลงแล้ว → ระบบถือว่าลงแล้วด้วย และแก้ ICD-9 ในกล่องเดียวกันได้", [val.done, val.validated, val.icd9, val.state], [true, true, "86.22", "validated"]);
    t.check("แก้รหัส ICD ในกล่องแก้ไขเคส → ปักธงว่าคนแก้เอง (กันการดึงข้อมูลรอบหน้าทับกลับ)", val.icdEdited);
    await page.evaluate(() => { store.data.cases = store.data.cases.filter(c => !c.id.startsWith("case_rc_")); store.save(); });

    t.check("เกณฑ์ logbook: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
    await page.close();

    /* ---------- แพทย์ประจำบ้าน: กล่อง "ลงใน RCOSTLog" ของเคสตัวเอง + ตัวเลขบนหน้าวันนี้ ---------- */
    {
      const { page, errors } = await openAs(browser, srv.url, "resident");
      const r = await page.evaluate(async () => {
        const me = myResidentId();
        const other = store.data.residents.find(x => x.id !== me).id;
        store.data.cases.push(
          { id:"case_rc_mine", date:"2026-02-25", subspecialty:"foot", operation:"Debridement of foot infection", diagnosis:"Laceration wound Lt heel",
            side:"left", hn:"1743650", age: 10, sex:"male", icd9:"86.22", icd10:"S91.0", note:"Prone position", complications:[],
            participants:[{ residentId: me, role:"surgeon", why:"ทดสอบ", verified:true, verifiedBy:"อ.", rcost:{ done:false, at:"" } }] },
          { id:"case_rc_theirs", date:"2026-02-26", subspecialty:"trauma", operation:"PFN", diagnosis:"IT fx", hn:"2", age: 70, sex:"female", complications:[], note:"",
            participants:[{ residentId: other, role:"surgeon", why:"ทดสอบ", verified:true, verifiedBy:"อ.", rcost:{ done:false, at:"" } }] });
        store.save();
        /* หน้าวันนี้: ตัวเลขและปุ่มไปหน้า logbook */
        renderToday();
        const tile = [...document.querySelectorAll("#todayBody .nowcard")].find(x => x.textContent.includes("รอลง RCOSTLog"));
        const tileCount = tile?.querySelector(".tag")?.textContent.trim();
        const expectTodo = String(rcostTodo(me).length);
        const goBtn = tile?.querySelector("[data-tgo-rcost]");
        goBtn?.click();
        await new Promise(r => setTimeout(r, 80));
        const landed = { view: currentViewName(), filter: caseFilter.rcost,
                         rowsShown: [...document.querySelectorAll("#caseTable [data-rcostcopy]")].map(b => b.dataset.rcostcopy.split("|")[0]) };
        /* กล่องคัดลอก */
        rcostCopyDialog("case_rc_mine", me);
        const open1 = document.querySelector("#dlg")?.open;
        const dataRows = [...document.querySelectorAll("#dlgBody tbody tr")].filter(tr => tr.children.length === 3);
        const labels = dataRows.map(tr => tr.children[0].textContent.trim());
        const cell = (label) => dataRows.find(tr => tr.children[0].textContent.trim() === label)?.children[1]?.textContent.trim();
        const copies = document.querySelectorAll("#dlgBody [data-copy]").length;
        /* Note มีปุ่มคัดลอกของตัวเอง แต่ต้องไม่ติดไปกับ "คัดลอกทั้งหมด" และต้องมีคำเตือนกำกับ */
        const noteRow = dataRows.find(tr => tr.children[0].textContent.trim() === "Note");
        const noteHasCopy = !!noteRow?.querySelector("[data-copy]");
        const noteWarned = /ห้ามมีชื่อหรือตัวระบุตัวตนผู้ป่วย/.test(noteRow?.textContent || "");
        const allBtn = [...document.querySelectorAll("#dlgFoot button")].find(b => b.textContent.includes("คัดลอกทั้งหมด"));
        let copied = "";
        try { Object.defineProperty(navigator, "clipboard", { configurable: true,
          value: { writeText: (txt) => { copied = txt; return Promise.resolve(); } } }); } catch (e) { copied = "(stub ไม่ได้)"; }
        allBtn?.click();
        await new Promise(r => setTimeout(r, 60));
        const values = { level: cell("Performing Level"), date: cell("Date of Procedure"), gender: cell("Gender"), hn: cell("Patient's HN"), icd10: cell("ICD10") };
        const auditBefore = store.data.audit.length;
        const markBtn = [...document.querySelectorAll("#dlgFoot button")].find(b => b.textContent.includes("ลง RCOSTLog แล้ว"));
        markBtn?.click();
        await new Promise(r => setTimeout(r, 50));
        const p = store.data.cases.find(c => c.id === "case_rc_mine").participants[0];
        const after = { done: p.rcost.done, at: p.rcost.at, auditGrew: store.data.audit.length > auditBefore, closed: !document.querySelector("#dlg")?.open };
        /* เคสของคนอื่นเปิดไม่ได้ */
        rcostCopyDialog("case_rc_theirs", other);
        const openOther = !!document.querySelector("#dlg")?.open;
        store.data.cases = store.data.cases.filter(c => !c.id.startsWith("case_rc_")); store.save();
        return { tileCount, expectTodo, hasGo: !!goBtn, landed, open1, labels, copies, values, after, openOther, today: todayISO(),
                 noteHasCopy, noteWarned, copied, note: store.data.cases.find(c => c.id === "case_rc_mine")?.note || "Prone position" };
      });
      t.check("หน้าวันนี้: ช่อง 'รับรองแล้ว รอลง RCOSTLog' นับเคสของฉันที่รับรองแล้วแต่ยังไม่ลง (รวมเคสสาธิต)",
              r.tileCount === r.expectTodo && +r.tileCount >= 1, r.tileCount + " vs " + r.expectTodo);
      t.check("กดปุ่มแล้วไปหน้า logbook พร้อมตัวกรอง todo และเห็นปุ่ม 'ลงใน RCOSTLog' ของเคสนั้น",
              r.hasGo && r.landed.view === "logbook" && r.landed.filter === "todo" && r.landed.rowsShown.includes("case_rc_mine"), JSON.stringify(r.landed));
      t.check("กล่องคัดลอกเปิดได้ และเรียงช่องตามหน้าจอ RCOSTLog", r.open1 &&
              JSON.stringify(r.labels) === JSON.stringify(["Patient's HN","Diagnosis","Gender","Age","Procedure","ICD9","Note","Performing Level","Date of Procedure","ICD10"]),
              JSON.stringify(r.labels));
      t.eq("ค่าถูกแปลงเป็นแบบที่ RCOSTLog ใช้: ผู้ผ่าตัดหลัก→Performer · เพศอังกฤษ · วันที่แบบ 25 February 2026",
           [r.values.level, r.values.gender, r.values.date, r.values.hn, r.values.icd10], ["Performer", "Male", "25 February 2026", "1743650", "S91.0"]);
      t.check("ทุกช่องที่มีค่ามีปุ่มคัดลอก", r.copies === 10, String(r.copies));
      t.check("ช่อง Note มีปุ่มคัดลอกของตัวเองและมีคำเตือนกำกับ", r.noteHasCopy && r.noteWarned);
      t.check("'คัดลอกทั้งหมด' ไม่รวม Note (ข้อความอิสระที่อาจมีตัวระบุตัวตนผู้ป่วย) แต่รวมช่องอื่นครบ",
              !/Note:/.test(r.copied) && !r.copied.includes("Prone position") && /Patient's HN:/.test(r.copied) && /ICD10:/.test(r.copied),
              JSON.stringify(r.copied));
      t.check("กด 'ลง RCOSTLog แล้ว' → เปลี่ยนสถานะ บันทึกวันที่ ลง audit และปิดกล่อง",
              r.after.done && r.after.at === r.today && r.after.auditGrew && r.after.closed, JSON.stringify(r.after));
      t.check("เคสของคนอื่นเปิดกล่องไม่ได้ (สิทธิ์เห็นเฉพาะของตัวเอง)", !r.openOther);

      /* ตัวกรองของแพทย์ประจำบ้านไม่เคยเลือกคน (เห็นแค่ตัวเอง) — ต้องยึดตัวเองเสมอ
         เคสที่ฉันลงแล้วแต่ผู้ช่วยยังไม่ลง ต้องไม่โผล่ใน "รอลง" ของฉัน ไม่งั้นจะลอกซ้ำลง RCOSTLog */
      const mine = await page.evaluate(() => {
        const me = myResidentId();
        const other = store.data.residents.find(x => x.id !== me).id;
        store.data.cases.push({ id:"case_rc_shared", date: todayISO(), subspecialty:"trauma", operation:"Shared case",
          diagnosis:"DX", hn:"9", age: 40, sex:"male", complications:[], note:"",
          participants:[{ residentId: me, role:"surgeon", verified:true, verifiedBy:"อ.", rcost:{ done:true, at: todayISO() } },
                        { residentId: other, role:"assist1", verified:true, verifiedBy:"อ.", rcost:{ done:false, at:"" } }] });
        const ids = (want) => { caseFilter.residentId = ""; caseFilter.rcost = want; return filterCases().map(c => c.id); };
        const todo = ids("todo"), yes = ids("yes");
        const todoMatchesTile = todo.length === rcostTodo(me).length;
        store.data.cases = store.data.cases.filter(c => c.id !== "case_rc_shared");
        caseFilter.rcost = "";
        return { inTodo: todo.includes("case_rc_shared"), inYes: yes.includes("case_rc_shared"), todoMatchesTile };
      });
      t.check("เคสที่ฉันลงแล้วแต่เพื่อนร่วมเคสยังไม่ลง: ไม่อยู่ใน 'รอลง' ของฉัน แต่อยู่ใน 'ลงแล้ว'",
              !mine.inTodo && mine.inYes, JSON.stringify(mine));
      t.check("จำนวนแถวในตัวกรอง 'รอลง' เท่ากับตัวเลขบนหน้าวันนี้", mine.todoMatchesTile);
      t.check("RCOSTLog (resident): ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }
  } finally {
    await browser.close();
    await srv.close();
  }
  return t;
}
