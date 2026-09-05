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
      return { j9: fromJson.icd9, j10: fromJson.icd10, a9: fromAlias.icd9, a10: fromAlias.icd10,
               c9: csv[0]?.icd9, c10: csv[0]?.icd10, cOp: csv[0]?.operationText };
    });
    t.eq("ระบบคิวส่ง icd9/icd10 มา → เก็บลงเคส", [imp.j9, imp.j10], ["81.54", "M17.1"]);
    t.eq("ชื่อคีย์อื่นของระบบคิว (procedureCode/diagnosisCode) ก็รับได้", [imp.a9, imp.a10], ["79.35", "S72.10"]);
    t.eq("CSV มีคอลัมน์ icd9/icd10 → อ่านได้", [imp.c9, imp.c10, imp.cOp], ["81.51", "M16.1", "THA left"]);

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
      return { hasCol, done: p.rcost.done, validated: p.rcost.validated, icd9: c.icd9, state: rcostState(p) };
    });
    t.check("กล่องแก้ไขเคสมีคอลัมน์ Validated ใน RCOSTLog", val.hasCol);
    t.eq("ติ๊ก validated โดยยังไม่ติ๊กลงแล้ว → ระบบถือว่าลงแล้วด้วย และแก้ ICD-9 ในกล่องเดียวกันได้", [val.done, val.validated, val.icd9, val.state], [true, true, "86.22", "validated"]);
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
        return { tileCount, expectTodo, hasGo: !!goBtn, landed, open1, labels, copies, values, after, openOther, today: todayISO() };
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
      t.check("กด 'ลง RCOSTLog แล้ว' → เปลี่ยนสถานะ บันทึกวันที่ ลง audit และปิดกล่อง",
              r.after.done && r.after.at === r.today && r.after.auditGrew && r.after.closed, JSON.stringify(r.after));
      t.check("เคสของคนอื่นเปิดกล่องไม่ได้ (สิทธิ์เห็นเฉพาะของตัวเอง)", !r.openOther);
      t.check("RCOSTLog (resident): ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }
  } finally {
    await browser.close();
    await srv.close();
  }
  return t;
}
