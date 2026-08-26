/* การรวมข้อมูลเมื่อสองเครื่องแก้ชนกัน และการล้างข้อมูล
   สองเรื่องนี้ไม่มีชุดทดสอบมาก่อน ทั้งที่เป็นทางเดินที่ "เงียบ" ที่สุดในระบบ —
   เวลาพัง ผู้ใช้ไม่เห็นอะไรเลย รู้อีกทีคือข้อมูลหายไปแล้ว */
import { chromium } from "playwright";
import { serve, launchOptions, openAs, suite } from "./lib.mjs";

export default async function run() {
  const t = suite("การรวมข้อมูลเมื่อชนกัน และการล้างข้อมูล");
  const srv = await serve();
  const browser = await chromium.launch(launchOptions());
  try {
    /* ---------- mergeDatasets: ของที่เครื่องนี้เพิ่งบันทึกต้องไม่หาย ---------- */
    {
      const { page, errors } = await openAs(browser, srv.url, "admin");
      const r = await page.evaluate(() => {
        /* ทุกคอลเลกชันที่ซิงก์ขึ้นคลาวด์ต้องถูกรวมรายรายการ ไม่งั้นของฝั่งเราถูกทับทั้งก้อน
           ตรวจทุกคีย์พร้อมกัน จะได้ไม่ต้องมาไล่เพิ่มทีละตัวตอนที่มันหายไปแล้ว */
        const perRecord = SYNCED_KEYS.filter(k => Array.isArray(store.data[k]));
        const missing = perRecord.filter(k => !ID_COLLECTIONS.includes(k) && !WHOLE_KEYS.includes(k));

        const mk = (id) => ({ id, rotationId:"rot_x", residentId:"res_a", month:"2026-07",
                              scores:{ knowledge:4 }, comment:"บันทึกจากเครื่องนี้" });
        const base   = { rotationEvals: [] };
        const mine   = { rotationEvals: [mk("rev_local")] };
        const theirs = { rotationEvals: [] };
        const out = mergeDatasets(base, mine, theirs);

        /* แก้ทั้งสองฝั่งต้องได้ conflict ที่มีชื่อภาษาไทย ไม่ใช่ชื่อคีย์ดิบ */
        const b2 = { rotationEvals: [mk("rev_1")] };
        const m2 = { rotationEvals: [{ ...mk("rev_1"), comment:"ของเครื่องนี้" }] };
        const t2 = { rotationEvals: [{ ...mk("rev_1"), comment:"ของอีกเครื่อง" }] };
        const out2 = mergeDatasets(b2, m2, t2);

        return { missing, kept: out.merged.rotationEvals?.length ?? 0,
                 conflictKeys: out2.conflicts.map(c => c.key),
                 winner: out2.merged.rotationEvals?.[0]?.comment };
      });
      t.eq("ทุกคอลเลกชันที่ซิงก์ ถูกรวมรายรายการครบ ไม่มีตัวไหนตกหล่น", r.missing, []);
      t.eq("ผลประเมินลงกองที่เพิ่งบันทึก ไม่หายเมื่อข้อมูลชนกัน", r.kept, 1);
      t.eq("แก้ทั้งสองฝั่งแล้วเก็บฉบับของเครื่องนี้ไว้", r.winner, "ของเครื่องนี้");
      t.eq("และบันทึกไว้เป็นรายการที่ชนกัน", r.conflictKeys, ["rotationEvals"]);
      t.check("รวมข้อมูล: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }

    /* ---------- ชื่อภาษาไทยของส่วนข้อมูลที่ชนกัน ---------- */
    {
      const { page } = await openAs(browser, srv.url, "admin");
      const r = await page.evaluate(() => {
        /* ตารางรายการที่ชนกันแปลชื่อคีย์เป็นภาษาไทย ถ้าคีย์ไหนไม่มีในตารางแปล
           ผู้ใช้จะเห็นชื่อตัวแปรภาษาอังกฤษดิบ ๆ ซึ่งไม่มีความหมายกับอาจารย์ */
        store.data.syncConflicts = [...ID_COLLECTIONS, ...WHOLE_KEYS].map(k =>
          ({ at:new Date().toISOString(), key:k, id:"x", note:"ทดสอบ" }));
        renderConflictList();
        const cells = [...document.querySelectorAll("#conflictList tbody tr")]
          .map(tr => tr.children[1]?.textContent.trim());
        store.data.syncConflicts = [];
        return { raw: cells.filter(c => /^[a-zA-Z]+$/.test(c || "")) };
      });
      t.eq("ทุกส่วนข้อมูลมีชื่อภาษาไทยกำกับในตารางรายการที่ชนกัน", r.raw, []);
      await page.close();
    }

    /* ---------- ล้างข้อมูลแล้วต้องได้ก้อนข้อมูลที่ครบรูป ---------- */
    {
      const { page, errors } = await openAs(browser, srv.url, "admin");
      const r = await page.evaluate(() => {
        const rotId = (store.data.rotations || [])[0]?.id || "";
        store.wipe();
        /* ทุกคีย์ที่ซิงก์ต้องมีอยู่จริงหลังล้าง ไม่ใช่ undefined จนกว่าจะรีโหลด
           ไม่งั้นปุ่มที่ไปแตะคอลเลกชันนั้นจะพังทันที */
        const missing = SYNCED_KEYS.filter(k => store.data[k] === undefined);
        let threw = "";
        try { openRotationEval(rotId); closeDialog(); } catch (e) { threw = e.message; }
        return { missing, threw };
      });
      t.eq("ล้างข้อมูลแล้วยังมีทุกส่วนที่ซิงก์ครบ", r.missing, []);
      t.eq("เปิดแบบประเมินลงกองบนข้อมูลที่เพิ่งล้าง ไม่พัง", r.threw, "");
      t.check("ล้างข้อมูล: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }
  } finally {
    await browser.close();
    await srv.close();
  }
  return t;
}
