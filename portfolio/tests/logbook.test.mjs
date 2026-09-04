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

    t.check("เกณฑ์ logbook: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
    await page.close();
  } finally {
    await browser.close();
    await srv.close();
  }
  return t;
}
