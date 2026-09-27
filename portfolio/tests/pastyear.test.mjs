/* สามเรื่องที่ทำให้เอกสารและบันทึกของอดีตผิดหรือหายแบบไม่มีใครรู้
   1) ถอดผู้ร่วมผ่าตัด ("— ไม่ได้ร่วม —") ลบการรับรองและสถานะ RCOSTLog เงียบ ๆ ไม่มีเลิกทำ
   2) คอลัมน์ "ชั้นปี" ในไฟล์ส่งราชวิทยาลัยฯ และตาราง/ใบพิมพ์ปีเก่า เป็นชั้นปีของวันนี้
   3) คำเตือน "ลงหน่วยผิดชั้นปี" ไม่ผูกกับปีที่เลือกดู และเทียบกับชั้นปีวันนี้
   ทุกข้อเคยพังจริง อย่าลบออกโดยไม่เข้าใจว่ามันกันอะไรอยู่ */
import { chromium } from "playwright";
import { serve, launchOptions, openAs, suite } from "./lib.mjs";

/* สตับการยืนยัน — confirmAny เป็น const จึงสตับที่ตัวจริงที่มันเรียก (กล่องเปิดอยู่ = confirmInline) */
const STUB_CONFIRM = `
  window.__asked = [];
  window.__realCI = confirmInline; window.__realCD = confirmDialog;
  confirmInline = async (m) => { window.__asked.push(m); return window.__answer ?? true; };
  confirmDialog = async (m) => { window.__asked.push(m); return window.__answer ?? true; };`;

export default async function run() {
  const t = suite("ถอดผู้ร่วมผ่าตัด · ชั้นปีของอดีต · คำเตือนชั้นปี");
  const srv = await serve();
  const browser = await chromium.launch(launchOptions());
  try {
    /* ---------- 1) ถอดผู้ร่วมผ่าตัด ---------- */
    {
      const { page, errors } = await openAs(browser, srv.url, "admin");
      const setup = await page.evaluate(() => {
        /* เคสที่มีแพทย์ประจำบ้านอย่างน้อยหนึ่งคน อาจารย์รับรองแล้ว และลง RCOSTLog แล้ว */
        const c = store.data.cases.find(x => (x.participants || []).length);
        const p = c.participants[0];
        p.verified = true; p.verifiedBy = "อาจารย์ทดสอบ";
        p.rcost = { done: true, at: "2026-08-01", validated: true, validatedAt: "2026-08-02" };
        store.save();
        return { caseId: c.id, rid: p.residentId, name: store.resident(p.residentId)?.name, n: c.participants.length };
      });

      /* แพทย์ประจำบ้านถอดแถวของตัวเองที่อาจารย์รับรองแล้วไม่ได้ */
      const userId = await page.evaluate(rid => store.data.users.find(u => u.residentId === rid)?.id, setup.rid);
      await page.evaluate(id => localStorage.setItem("mnrh_ortho_portfolio_session_v1",
        JSON.stringify({ userId: id, at: new Date().toISOString() })), userId);
      await page.reload();
      await page.waitForFunction(() => typeof currentUser === "function" && !!currentUser());
      const asRes = await page.evaluate(async ({ caseId, rid }) => {
        editCaseParticipants(caseId);
        await new Promise(r => setTimeout(r, 150));
        document.querySelector(`#dlgBody [data-role="${rid}"]`).value = "";
        [...document.querySelectorAll("#dlgFoot button")].find(b => b.textContent === "บันทึก").click();
        await new Promise(r => setTimeout(r, 300));
        const stillOpen = !!document.querySelector("#dlg")?.open;
        document.querySelector("#dlg")?.close();
        const c = store.data.cases.find(x => x.id === caseId);
        const p = c.participants.find(x => x.residentId === rid);
        return { stillOpen, kept: !!p, verified: !!p?.verified, validated: !!p?.rcost?.validated };
      }, setup);
      t.check("แพทย์ประจำบ้านถอดแถวของตัวเองที่อาจารย์รับรองแล้วไม่ได้ — แถวและสถานะยังอยู่ครบ",
              asRes.stillOpen && asRes.kept && asRes.verified && asRes.validated, JSON.stringify(asRes));

      /* แพทย์ประจำบ้านเปลี่ยนบทบาทหลังรับรอง → การรับรองต้องไม่ติดไปกับบทบาทใหม่ */
      const roleChange = await page.evaluate(async ({ caseId, rid }) => {
        const c = store.data.cases.find(x => x.id === caseId);
        const before = c.participants.find(x => x.residentId === rid).role;
        const other = CASE_ROLES.find(x => x.id !== before).id;
        editCaseParticipants(caseId);
        await new Promise(r => setTimeout(r, 150));
        document.querySelector(`#dlgBody [data-role="${rid}"]`).value = other;
        [...document.querySelectorAll("#dlgFoot button")].find(b => b.textContent === "บันทึก").click();
        await new Promise(r => setTimeout(r, 300));
        const p = store.data.cases.find(x => x.id === caseId).participants.find(x => x.residentId === rid);
        return { role: p.role, other, verified: p.verified, validated: !!p.rcost?.validated,
                 audit: (store.data.audit || []).slice(-1)[0]?.detail || "" };
      }, setup);
      t.check("เปลี่ยนบทบาทหลังอาจารย์รับรอง → ต้องรับรองใหม่ ไม่พาการรับรองเดิมติดไป",
              roleChange.role === roleChange.other && roleChange.verified === false, JSON.stringify(roleChange));
      /* validated ใน RCOSTLog ก็เป็นของอาจารย์และรับรองบทบาทเดิมเช่นกัน — เดิมหลุดรอดไป ทำให้ CSV ที่ลอกลง
         RCOSTLog ออกมาเป็นบทบาทใหม่ + validated ทั้งที่อาจารย์ validate ไว้แค่บทบาทเดิม */
      t.check("เปลี่ยนบทบาทหลังอาจารย์ validate → สถานะ validated ไม่ติดไปกับบทบาทใหม่", roleChange.validated === false);
      t.check("audit บันทึกว่ามีการเปลี่ยนบทบาทหลังรับรอง", roleChange.audit.includes("เปลี่ยนบทบาทหลังรับรอง"), roleChange.audit);

      /* อาจารย์ถอดได้ แต่ต้องถูกถามก่อน บอกว่าเสียสถานะอะไร ลง audit ด้วยชื่อ และเลิกทำได้ */
      const staffId = await page.evaluate(() => store.data.users.find(u => u.role === "admin").id);
      await page.evaluate(id => localStorage.setItem("mnrh_ortho_portfolio_session_v1",
        JSON.stringify({ userId: id, at: new Date().toISOString() })), staffId);
      await page.reload();
      await page.waitForFunction(() => typeof currentUser === "function" && !!currentUser());
      const asStaff = await page.evaluate(async ({ caseId, rid, stub }) => {
        /* ตั้งสถานะกลับให้เป็นแถวที่รับรองแล้วก่อน เพื่อพิสูจน์ว่าข้อความยืนยันบอกสิ่งที่จะหายไป */
        const c0 = store.data.cases.find(x => x.id === caseId);
        const p0 = c0.participants.find(x => x.residentId === rid);
        p0.verified = true; p0.rcost = { done: true, at: "2026-08-01", validated: true, validatedAt: "2026-08-02" };
        store.save();
        eval(stub);
        editCaseParticipants(caseId);
        await new Promise(r => setTimeout(r, 150));
        document.querySelector(`#dlgBody [data-role="${rid}"]`).value = "";
        [...document.querySelectorAll("#dlgFoot button")].find(b => b.textContent === "บันทึก").click();
        await new Promise(r => setTimeout(r, 400));
        const c = store.data.cases.find(x => x.id === caseId);
        const out = {
          asked: window.__asked.join(" | "),
          gone: !c.participants.some(x => x.residentId === rid),
          audit: (store.data.audit || []).slice(-1)[0]?.detail || ""
        };
        /* เลิกทำ */
        const undo = [...document.querySelectorAll("#toast button, .toast button")].find(b => /เลิกทำ/.test(b.textContent));
        undo?.click();
        await new Promise(r => setTimeout(r, 300));
        const back = store.data.cases.find(x => x.id === caseId).participants.find(x => x.residentId === rid);
        out.undoFound = !!undo;
        out.restored = !!back && !!back.verified && !!back.rcost?.validated;
        confirmInline = window.__realCI; confirmDialog = window.__realCD;
        return out;
      }, { ...setup, stub: STUB_CONFIRM });
      t.check("อาจารย์ถอดแล้วถูกถามก่อน และข้อความบอกสถานะที่จะหายไป",
              asStaff.asked.includes(setup.name) && asStaff.asked.includes("อาจารย์รับรองแล้ว"), asStaff.asked.slice(0, 120));
      t.check("ถอดออกจากเคสได้จริงหลังยืนยัน", asStaff.gone);
      t.check("audit บอกชื่อคนที่ถูกถอดและสถานะที่เสียไป",
              asStaff.audit.includes(setup.name) && asStaff.audit.includes("รับรอง"), asStaff.audit);
      t.check("เลิกทำแล้วแถวกลับมาพร้อมการรับรองและสถานะ RCOSTLog เดิม", asStaff.undoFound && asStaff.restored);
      t.check("ถอดผู้ร่วมผ่าตัด: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }

    /* ---------- 2 + 3) ชั้นปีของอดีต และคำเตือนชั้นปีตามปีที่เลือก ---------- */
    {
      const { page, errors } = await openAs(browser, srv.url, "admin");
      const r = await page.evaluate(() => {
        /* เลื่อนชั้นปีหนึ่งรอบ แล้วย้อนดูปีเก่า — ทุกคนที่ยังอยู่มีชั้นปีวันนี้ต่างจากชั้นปีของปีเก่า 1 ปี */
        const ayOld = store.data.meta.yearRolledAY || currentAY();
        store.rollAcademicYear(String(+ayOld + 1), "manual");
        store.save();
        ayView = ayOld;
        /* เลือกคนที่มีผลประเมินลงกองของปีเก่าอยู่จริง — ไม่งั้นข้อที่ตรวจไฟล์ส่งราชวิทยาลัยฯ จะผ่านโดยไม่ได้ตรวจอะไร */
        const withEval = new Set((store.data.rotationEvals || [])
          .filter(x => academicYear(x.start || x.month + "-01") === ayOld).map(x => x.residentId));
        const someone = store.data.residents.find(x => isActiveResident(x) && x.year >= 2 && withEval.has(x.id))
                     || store.data.residents.find(x => isActiveResident(x) && x.year >= 2);

        /* CSV ตารางรายเดือน */
        const month = monthCsvRows();
        const mRow = month.find(row => row[0] === someone.name);

        /* CSV กิจกรรม — แถวของปีเก่า */
        const act = store.activitiesOf(someone.id).find(a => a.academicYear === ayOld);
        const aRow = act ? activityCsvRows([act])[1] : null;

        /* CSV ผลประเมินลงกอง (ไฟล์ส่งราชวิทยาลัยฯ) */
        const ev = (store.data.rotationEvals || []).find(x => x.residentId === someone.id && academicYear(x.start || x.month + "-01") === ayOld);
        const evRows = rotationEvalCsvRows();
        const eRow = ev ? evRows.find(row => row[3] === someone.name && row[0] === ev.month) : null;

        return {
          ayOld, name: someone.name, now: someone.year, then: yearOnAY(someone, ayOld),
          monthYear: mRow?.[1], actYear: aRow?.[3], hasAct: !!act, evYear: eRow?.[4], hasEv: !!ev
        };
      });
      t.eq("ตั้งต้น: ชั้นปีวันนี้กับชั้นปีของปีเก่าต่างกัน 1 ปี", r.then, r.now - 1);
      t.eq("CSV ตารางรายเดือนของปีเก่า ใช้ชั้นปีของปีนั้น", r.monthYear, r.then);
      t.check("CSV กิจกรรม: คอลัมน์ชั้นปีตรงกับปีการศึกษาในแถวเดียวกัน",
              !r.hasAct || r.actYear === r.then, r.hasAct ? "ได้ " + r.actYear + " ต้องการ " + r.then : "ไม่มีกิจกรรมของปีเก่า");
      t.check("CSV ผลประเมินลงกอง (ส่งราชวิทยาลัยฯ): ชั้นปีเป็นของเดือนที่ประเมิน",
              !r.hasEv || r.evYear === r.then, r.hasEv ? "ได้ " + r.evYear + " ต้องการ " + r.then : "ไม่มีผลประเมินของปีเก่า");
      t.check("มีข้อมูลของปีเก่าให้ตรวจจริงทั้งสองไฟล์", r.hasAct && r.hasEv);

      /* ใบพิมพ์และตารางบนจอ */
      const screen = await page.evaluate(({ name, then }) => {
        let printed = "";
        const realPrint = printReport; printReport = (h) => { printed = h; };
        try { printMonthGrid(); } finally { printReport = realPrint; }
        showView("rotation"); renderMonthGrid();
        const th = [...document.querySelectorAll("#monthGrid th.who")].find(x => x.textContent.includes(name));
        return { printedOk: printed.includes(name) && new RegExp(name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "[\\s\\S]{0,120}ปี " + then).test(printed),
                 gridOk: !!th && th.textContent.includes("ชั้นปีที่ " + then) };
      }, r);
      t.check("ใบพิมพ์ตารางรายเดือนของปีเก่า ใช้ชั้นปีของปีนั้น", screen.printedOk);
      t.check("ตารางรายเดือนบนจอของปีเก่า ใช้ชั้นปีของปีนั้น", screen.gridOk);

      /* คำเตือนชั้นปี: ผิดกติกาจริงในปีเก่าต้องยังถูกเตือนแม้วันนี้เลื่อนชั้นมาตรงกับหน่วยแล้ว
         และคำเตือนของปีหนึ่งต้องไม่โผล่ตอนดูอีกปี */
      const warn = await page.evaluate(({ ayOld }) => {
        const svc = store.data.services.find(s => (s.years || []).length === 1);
        const need = svc.years[0];
        /* คนที่ "ปีเก่า" อยู่ชั้นปีที่ไม่ตรงหน่วย แต่ "วันนี้" ตรงหน่วยพอดี = ความผิดพลาดที่เดิมหายเงียบ */
        const who = store.data.residents.find(x => yearOnAY(x, ayOld) === need - 1 && x.year === need);
        if (!who) return { skip: true };
        const start = ayMonths(ayOld)[2]; /* เดือนที่สามของปีเก่า */
        const rot = { id: "rot_wrongyear", residentId: who.id, serviceId: svc.id,
                      start: monthStartISO(start), end: monthEndISO(start) };
        store.data.rotations.push(rot);
        const inOld = rotationYearWarnings(store.data.rotations.filter(x => academicYear(x.start) === ayOld),
                                           store.data.services, residentsForAY(ayOld));
        ayView = ayOld; renderMonthGrid();
        const noteOld = document.querySelector("#rotationRuleNotes")?.textContent || "";
        const ayNew = String(+ayOld + 1);
        /* ตัวเลือกปีมีเฉพาะปีที่มีข้อมูล — ใส่ช่วงหมุนเวียนธรรมดาหนึ่งช่วงในปีใหม่ ไม่งั้น renderMonthGrid
           จะเด้ง ayView กลับไปปีเก่าเอง แล้วเทสต์นี้วัดปีผิด */
        const free = store.data.services.find(s => !(s.years || []).length);
        const other = store.data.residents.find(x => isActiveResident(x) && x.id !== who.id);
        const mNew = ayMonths(ayNew)[0];
        store.data.rotations.push({ id: "rot_newyear", residentId: other.id, serviceId: free.id,
                                    start: monthStartISO(mNew), end: monthEndISO(mNew) });
        ayView = ayNew; renderMonthGrid();
        const viewedNew = ayView === ayNew;
        const noteNew = document.querySelector("#rotationRuleNotes")?.textContent || "";
        store.data.rotations = store.data.rotations.filter(x => x.id !== "rot_wrongyear" && x.id !== "rot_newyear");
        return { name: who.name, svc: svc.name, inOld: inOld.some(w => w.includes(who.name) && w.includes(svc.name)),
                 shownOld: noteOld.includes(who.name), shownNew: noteNew.includes(who.name), viewedNew };
      }, r);
      if (warn.skip) t.check("คำเตือนชั้นปี: มีข้อมูลตั้งต้นให้ทดสอบ", false, "ไม่พบคนที่เลื่อนชั้นมาตรงกับหน่วยพอดี");
      else {
        t.check("ความผิดพลาดของปีเก่ายังถูกเตือน แม้วันนี้คนนั้นเลื่อนชั้นมาตรงกับหน่วยแล้ว", warn.inOld, warn.name + " · " + warn.svc);
        t.check("คำเตือนขึ้นเหนือตารางของปีที่ผิดจริง", warn.shownOld);
        t.check("ตั้งต้น: สลับไปดูปีใหม่ได้จริง", warn.viewedNew);
        t.check("คำเตือนของปีหนึ่งไม่โผล่ตอนดูอีกปี", !warn.shownNew);
      }
      t.check("ชั้นปีของอดีต: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }
  } finally {
    await browser.close();
    await srv.close();
  }
  return t;
}
