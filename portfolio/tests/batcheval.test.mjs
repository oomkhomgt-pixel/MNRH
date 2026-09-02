/* ประเมินทั้งคาบ — อาจารย์ที่คุม ward round 4 คน เดิมต้องเปิดกล่อง 4 ใบ ใบละ ~11 ช่อง
   ตอนนี้กล่องเดียว แถวละคน และตัวบันทึก (saveSessionEval) เป็นตัวเดียวกับกล่องรายคน
   บวกเรื่องงานค้าง: คาบเช้าวันนี้ที่จบแล้วต้องนับเป็นงานค้างตั้งแต่บ่าย ไม่ใช่รอข้ามวัน */
import { chromium } from "playwright";
import { serve, launchOptions, openAs, suite } from "./lib.mjs";

export default async function run() {
  const t = suite("ประเมินทั้งคาบ และงานค้างของวันนี้");
  const srv = await serve();
  const browser = await chromium.launch(launchOptions());
  try {
    const { page, errors } = await openAs(browser, srv.url, "staff");

    /* หากลุ่มคาบที่มีคนตั้งแต่ 3 คนขึ้นไปในสองสัปดาห์นี้ (ไม่ผูกกับวันนี้ เพราะวันหยุดไม่มีคาบ) */
    const grp = await page.evaluate(() => {
      for (let i = 0; i < 14; i++) {
        const iso = addDaysISO(todayISO(), -i);
        const g = {};
        sessionsForDate(iso).filter(s => !s.superseded).forEach(s => (g[batchKey(s)] ||= []).push(s));
        const hit = Object.values(g).find(x => x.length >= 3);
        if (hit) return { keys: hit.map(s => s.key), name: hit[0].name, date: iso };
      }
      return null;
    });
    t.check("มีคาบที่มีแพทย์ประจำบ้านตั้งแต่ 3 คนให้ทดสอบ", !!grp, grp ? grp.name + " · " + grp.date : "ไม่มี");
    if (grp) {
      /* ---------- เติมให้ทุกคน + แก้แถวแรก แล้วบันทึก ---------- */
      const r1 = await page.evaluate((keys) => {
        keys.forEach(k => { store.data.sessionEvals = store.data.sessionEvals.filter(e => e.key !== k); });
        openSessionBatch(keys.map(sessionByKey));
        const rows = document.querySelectorAll('#dlgBody tbody tr').length - 1;   /* หักแถว "ใช้ค่านี้กับทุกคน" */
        EVAL_ITEMS.forEach(it => { document.querySelector(`#dlgBody [name="q_sc_${it.id}"]`).value = "4"; });
        document.querySelector('#dlgBody [name="q_entrust"]').value = "3";
        document.querySelector("#dlgBody [data-fillall]").click();
        document.querySelector(`#dlgBody [name="r0_sc_${EVAL_ITEMS[0].id}"]`).value = "5";
        document.querySelector('#dlgBody [name="r0_comment"]').value = "แถวแรกแก้เอง";
        const before = store.data.sessionEvals.length;
        document.querySelector("#dlgFoot .btn-primary").click();
        const evs = keys.map(k => evalForKey(k));
        return {
          rows, closed: !document.querySelector("#dlg").open,
          added: store.data.sessionEvals.length - before,
          allSaved: evs.every(Boolean),
          row0: evs[0] && { first: evs[0].scores[EVAL_ITEMS[0].id], comment: evs[0].comment, entrust: evs[0].entrust },
          row1: evs[1] && { first: evs[1].scores[EVAL_ITEMS[0].id], entrust: evs[1].entrust, staff: evs[1].staffId === myStaffId() }
        };
      }, grp.keys);
      t.eq("กล่องมีแถวเท่าจำนวนคนในคาบ", r1.rows, grp.keys.length);
      t.check("บันทึกแล้วกล่องปิด และทุกคนมีผลประเมิน", r1.closed && r1.allSaved);
      t.eq("จำนวนผลประเมินเพิ่มเท่าจำนวนคน", r1.added, grp.keys.length);
      t.eq("แถวแรกใช้ค่าที่แก้เอง ไม่ใช่ค่าเติมรวม", [r1.row0.first, r1.row0.comment, r1.row0.entrust], [5, "แถวแรกแก้เอง", 3]);
      t.eq("แถวอื่นได้ค่าจาก 'เติมให้ทุกคน' และอาจารย์ผู้ประเมินคือฉัน", [r1.row1.first, r1.row1.entrust, r1.row1.staff], [4, 3, true]);

      /* ---------- แถวว่างไม่ถูกบันทึก + prefill ของเดิม ---------- */
      const r2 = await page.evaluate((keys) => {
        keys.forEach(k => { store.data.sessionEvals = store.data.sessionEvals.filter(e => e.key !== k); });
        openSessionBatch(keys.map(sessionByKey));
        document.querySelector(`#dlgBody [name="r0_sc_${EVAL_ITEMS[1].id}"]`).value = "2";
        document.querySelector("#dlgFoot .btn-primary").click();
        const saved = keys.filter(k => evalForKey(k)).length;
        openSessionBatch(keys.map(sessionByKey));
        const prefill = document.querySelector(`#dlgBody [name="r0_sc_${EVAL_ITEMS[1].id}"]`).value;
        const tagOnRow0 = !!document.querySelector("#dlgBody tbody tr:nth-child(2) .tag.ok");
        const tagOnRow1 = !!document.querySelector("#dlgBody tbody tr:nth-child(3) .tag.ok");
        document.querySelector("#dlg").close();
        return { saved, prefill, tagOnRow0, tagOnRow1 };
      }, grp.keys);
      t.eq("กรอกแค่คนเดียว → บันทึกแค่คนเดียว แถวว่างไม่ถูกบันทึก", r2.saved, 1);
      t.eq("เปิดใหม่แล้วค่าเดิมถูกเติมไว้", r2.prefill, "2");
      t.eq("ป้าย 'ประเมินแล้ว' ขึ้นเฉพาะคนที่มีผล", [r2.tagOnRow0, r2.tagOnRow1], [true, false]);

      /* ---------- ไม่กรอกใครเลย → กล่องไม่ปิด ---------- */
      const r3 = await page.evaluate((keys) => {
        keys.forEach(k => { store.data.sessionEvals = store.data.sessionEvals.filter(e => e.key !== k); });
        openSessionBatch(keys.map(sessionByKey));
        document.querySelector("#dlgFoot .btn-primary").click();
        const open = document.querySelector("#dlg").open;
        document.querySelector("#dlg").close();
        return open;
      }, grp.keys);
      t.check("ไม่กรอกใครเลย: กล่องยังเปิดอยู่ ไม่ปิดเงียบ", r3);

      /* ---------- regression: กล่องรายคนยังบันทึก EPA ได้ผ่านตัวบันทึกตัวเดียวกัน ---------- */
      const r4 = await page.evaluate((keys) => {
        const key = keys[0];
        store.data.sessionEvals = store.data.sessionEvals.filter(e => e.key !== key);
        store.data.epaAssessments = (store.data.epaAssessments || []).filter(a => a.sessionKey !== key);
        openSession(key);
        document.querySelector(`#dlgBody [name="sc_${EVAL_ITEMS[0].id}"]`).value = "4";
        document.querySelector('#dlgBody [name="entrust"]').value = "3";
        const box = document.querySelector('#dlgBody [name^="epa_"]');
        if (box) box.checked = true;
        document.querySelector("#dlgFoot .btn-primary").click();
        return { hadBox: !!box, saved: !!evalForKey(key),
                 epa: (store.data.epaAssessments || []).filter(a => a.sessionKey === key).length };
      }, grp.keys);
      t.check("กล่องรายคน: ยังบันทึกผลได้", r4.saved);
      t.check("กล่องรายคน: ติ๊ก EPA แล้วมีผล EPA ผูกกับคาบ", !r4.hadBox || r4.epa === 1, r4.epa + " รายการ");
    }

    /* ---------- งานค้างรวมคาบของวันนี้ที่จบแล้ว ---------- */
    const pend = await page.evaluate(() => {
      /* หาวันทำการที่มีคาบเช้า แล้วจำลองเวลา 07:00 กับ 23:00 ของวันนั้น */
      let iso = todayISO();
      for (let i = 0; i < 10; i++) { if (sessionsForDate(iso).some(s => s.part === "am" && !s.superseded)) break; iso = addDaysISO(iso, 1); }
      const am = sessionsForDate(iso).filter(s => s.part === "am" && !s.superseded && !evalForKey(s.key)).map(s => s.key);
      const morning = new Set(pendingEvaluations(14, null, new Date(iso + "T07:00:00")).map(s => s.key));
      const night = new Set(pendingEvaluations(14, null, new Date(iso + "T23:00:00")).map(s => s.key));
      return { n: am.length,
               inMorning: am.filter(k => morning.has(k)).length,
               inNight: am.filter(k => night.has(k)).length,
               ended: sessionEnded({ date: iso, part: "am" }, new Date(iso + "T13:00:00")),
               notEnded: sessionEnded({ date: iso, part: "am" }, new Date(iso + "T09:00:00")),
               callNotEnded: sessionEnded({ date: iso, part: "call" }, new Date(iso + "T23:00:00")) };
    });
    t.check("มีคาบเช้าให้ทดสอบ", pend.n > 0, pend.n + " คาบ");
    t.eq("ตอนเช้า คาบเช้าของวันนี้ยังไม่เป็นงานค้าง", pend.inMorning, 0);
    t.eq("ตอนกลางคืน คาบเช้าของวันนี้ทั้งหมดเป็นงานค้าง", pend.inNight, pend.n);
    t.eq("sessionEnded: เช้าจบตอนบ่าย ไม่จบตอน 09:00 · เวรนอกเวลาไม่จบในวันเดียวกัน",
         [pend.ended, pend.notEnded, pend.callNotEnded], [true, false, false]);

    t.check("ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
    await page.close();
  } finally {
    await browser.close();
    await srv.close();
  }
  return t;
}
