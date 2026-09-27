/* สองเรื่องที่ทำให้ระบบ "ดูเหมือนปกติ" ทั้งที่มีบางอย่างหายไปหรือซ้อนกันอยู่
   1) ลบหน่วยแล้วตารางเวร ER/OPD ที่อ้างหน่วยนั้นค้างเป็น id ที่ตายแล้ว — วันนั้นไม่มีใครรับ ER เงียบ ๆ
   2) cloudPush ส่งใหม่หลังรวมข้อมูล (409) จากใน try — finally ของรอบแรกตั้ง syncing = false ทับรอบใหม่
      ที่ยังส่งอยู่ ตัวตั้งเวลาจึงยิง PUT ซ้อนได้
   ทุกข้อเคยพังจริง อย่าลบออกโดยไม่เข้าใจว่ามันกันอะไรอยู่ */
import { chromium } from "playwright";
import { serve, launchOptions, openAs, suite } from "./lib.mjs";

export default async function run() {
  const t = suite("ลบหน่วยกับตารางเวร · ส่งขึ้นคลาวด์ซ้อนกัน");
  const srv = await serve();
  const browser = await chromium.launch(launchOptions());
  try {
    /* ---------- 1) ลบหน่วยที่ตารางเวรอ้างอยู่ ---------- */
    {
      const { page, errors } = await openAs(browser, srv.url, "admin");
      const setup = await page.evaluate(() => {
        /* หาหน่วยสายที่มีคนวนอยู่ในวันที่ยังมาไม่ถึง แล้วตั้งให้วันนั้นเป็นเวร ER ของหน่วยนั้น */
        const today = todayISO();
        for (let k = 3; k < 60; k++) {
          const iso = addDaysISO(today, k);
          const rot = (store.data.rotations || []).find(x => x.start <= iso && x.end >= iso &&
            store.data.services.find(s => s.id === x.serviceId)?.team);
          if (!rot) continue;
          let d = (store.data.duty || []).find(x => x.date === iso);
          if (!d) { d = { date: iso, holiday:false, opdServiceId:"", opdStaffIds:[], erServiceId:"", erStaffIds:[], erResidentIds:[] };
                    (store.data.duty ||= []).push(d); }
          d.erServiceId = rot.serviceId; d.erResidentIds = []; d.holiday = false;
          store.save();
          const svc = store.data.services.find(s => s.id === rot.serviceId);
          const erBefore = sessionsForDate(iso).filter(s => s.kind === "duty").length;
          return { iso, svcId: svc.id, svcName: svc.name, erBefore };
        }
        return null;
      });
      t.check("ตั้งต้น: มีวันที่ตั้งเวร ER ให้หน่วยที่มีคนวนอยู่ และมีคนรับ ER จริง",
              !!setup && setup.erBefore > 0, setup ? setup.svcName + " · " + setup.iso + " · " + setup.erBefore + " คน" : "ไม่พบ");

      const del = await page.evaluate(async ({ svcId, iso }) => {
        const asked = [];
        const realCI = confirmInline, realCD = confirmDialog;
        confirmInline = async (m) => { asked.push(m); return true; };
        confirmDialog = async (m) => { asked.push(m); return true; };
        try {
          editService(svcId);
          await new Promise(r => setTimeout(r, 150));
          [...document.querySelectorAll("#dlgFoot button")].find(b => b.textContent.includes("ลบหน่วยนี้")).click();
          await new Promise(r => setTimeout(r, 400));
        } finally { confirmInline = realCI; confirmDialog = realCD; }
        const d = store.data.duty.find(x => x.date === iso);
        return {
          asked: asked.join(" | "),
          svcGone: !store.data.services.some(s => s.id === svcId),
          dangling: (store.data.duty || []).filter(x => x.erServiceId === svcId || x.opdServiceId === svcId).length,
          erField: d.erServiceId,
          audit: (store.data.audit || []).slice(-1)[0]?.action || ""
        };
      }, setup);
      t.check("ถามยืนยันก่อน และบอกว่าตารางเวร ER จะถูกล้างกี่วัน รวมวันที่ยังมาไม่ถึง",
              del.asked.includes("เวร ER") && del.asked.includes("ยังมาไม่ถึง"), del.asked.slice(0, 140));
      t.check("ลบหน่วยแล้ว", del.svcGone);
      t.eq("ไม่เหลือตารางเวรที่ชี้หน่วยที่ถูกลบ", del.dangling, 0);
      t.eq("วันนั้นกลับเป็น 'ยังไม่กำหนด' ให้เห็นว่าต้องไปตั้งใหม่ ไม่ใช่ id ที่ตายแล้ว", del.erField, "");
      t.eq("ลง audit", del.audit, "ลบหน่วย");

      /* เลิกทำต้องคืนทั้งหน่วยและตารางเวร */
      const undone = await page.evaluate(async ({ svcId, iso }) => {
        const undo = [...document.querySelectorAll("#toast button, .toast button")].find(b => /เลิกทำ/.test(b.textContent));
        undo?.click();
        await new Promise(r => setTimeout(r, 300));
        return { found: !!undo, svc: store.data.services.some(s => s.id === svcId),
                 er: store.data.duty.find(x => x.date === iso)?.erServiceId,
                 erSessions: sessionsForDate(iso).filter(s => s.kind === "duty").length };
      }, setup);
      t.check("เลิกทำแล้วหน่วยและตารางเวรกลับมาครบ มีคนรับ ER เหมือนเดิม",
              undone.found && undone.svc && undone.er === setup.svcId && undone.erSessions === setup.erBefore,
              JSON.stringify(undone));
      t.check("ลบหน่วย: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }

    /* ---------- 2) cloudPush ส่งใหม่หลัง 409 ต้องไม่ปล่อยให้ส่งซ้อน ---------- */
    {
      const { page, errors } = await openAs(browser, srv.url, "admin");
      const r = await page.evaluate(async () => {
        const cfg = syncCfg();
        cfg.cloudUrl = "https://example.invalid/portfolio"; cfg.mode = "full"; cfg.auto = false; cfg.rev = 1;
        const snapshot = JSON.parse(JSON.stringify(fullPayload()));
        let calls = 0, release;
        const realFetch = window.fetch;
        window.fetch = async (url, opts) => {
          calls++;
          /* รอบแรก: มีเครื่องอื่นส่งขึ้นไปก่อน → 409 พร้อมข้อมูลของเซิร์ฟเวอร์ */
          if (calls === 1) return new Response(JSON.stringify({ rev: 5, data: snapshot }), { status: 409 });
          /* รอบส่งใหม่: ค้างไว้ก่อน เพื่อตรวจสถานะระหว่างที่ยังส่งอยู่ */
          if (calls === 2) await new Promise(res => { release = res; });
          return new Response(JSON.stringify({ rev: 5 + calls, updatedAt: new Date().toISOString(), bytes: 10 }), { status: 200 });
        };
        /* ห้ามให้เทสต์ค้างได้ — ทุกการรอมีเพดานเวลา และปล่อยรอบที่ค้างเสมอก่อนจบ */
        const settle = (p, ms) => Promise.race([p, new Promise(res => setTimeout(() => res("timeout"), ms))]);
        try {
          const first = cloudPush(true);
          /* รอบแรกต้องรวมข้อมูลและวาดหน้าใหม่ทั้งหน้าก่อนส่งใหม่ — ใช้เวลาหลายวินาทีในเบราว์เซอร์ทดสอบ */
          for (let i = 0; i < 300 && calls < 2; i++) await new Promise(res => setTimeout(res, 50));
          const reachedRetry = calls >= 2;
          const syncingWhileRetry = syncing;
          /* ตัวตั้งเวลาของ markDirty ยิงเข้ามาระหว่างที่รอบส่งใหม่ยังค้างอยู่ */
          const extra = settle(cloudPush(true), 1500);
          await new Promise(res => setTimeout(res, 100));
          const callsDuring = calls;
          release?.();
          await settle(extra, 3000);
          const firstDone = await settle(first, 3000);
          return { reachedRetry, syncingWhileRetry, callsDuring, syncingAfter: syncing,
                   rev: cfg.rev, status: cfg.lastStatus, firstTimedOut: firstDone === "timeout" };
        } finally { release?.(); window.fetch = realFetch; }
      });
      t.check("ตั้งต้น: เข้ารอบส่งใหม่หลัง 409 จริง", r.reachedRetry, r.status);
      t.check("ระหว่างที่รอบส่งใหม่ยังค้างอยู่ สถานะยังเป็น 'กำลังซิงก์'", r.syncingWhileRetry === true);
      t.eq("การกระตุ้นซ้อนเข้ามาระหว่างนั้นไม่ส่ง PUT ก้อนที่สาม", r.callsDuring, 2);
      t.check("ส่งจบแล้วสถานะกลับเป็นว่าง และได้รุ่นใหม่จากเซิร์ฟเวอร์", r.syncingAfter === false && r.rev === 7, "rev " + r.rev);
      t.check("ส่งขึ้นคลาวด์: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }
  } finally {
    await browser.close();
    await srv.close();
  }
  return t;
}
