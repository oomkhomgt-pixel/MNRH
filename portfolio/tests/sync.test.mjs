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

    /* ---------- ล้าง/โหลดสาธิต/นำเข้าไฟล์ ต้องล้างฐานเปรียบเทียบเก่าทิ้งด้วย ----------
       ฐานเก่าอ้างถึงข้อมูลชุดก่อน ถ้าไม่ล้าง รอบซิงก์ถัดไปจะเข้าใจผิดว่าทุกอย่างถูก "แก้"
       พร้อมกันหมด แล้วทับของบนคลาวด์ทั้งก้อนแบบไม่บันทึกเป็นรายการที่ชนกันด้วยซ้ำ */
    {
      const { page, errors } = await openAs(browser, srv.url, "admin");
      const r = await page.evaluate(() => {
        writeBaseline(3, { rotationEvals: [{ id: "rev_baseline" }] });
        const hadBefore = readBaseline() !== null;
        store.wipe();
        const afterWipe = readBaseline();
        writeBaseline(4, { rotationEvals: [{ id: "rev_baseline2" }] });
        store.reset();
        const afterReset = readBaseline();
        return { hadBefore, afterWipe, afterReset };
      });
      t.check("ตั้งฐานเปรียบเทียบไว้ก่อนทดสอบได้จริง", r.hadBefore);
      t.eq("wipe() ล้างฐานเปรียบเทียบเก่าทิ้งด้วย", r.afterWipe, null);
      t.eq("reset() ล้างฐานเปรียบเทียบเก่าทิ้งด้วย", r.afterReset, null);
      t.check("ล้างฐานเปรียบเทียบ: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }

    /* ---------- ล้างข้อมูลเมื่อตั้งซิงก์อัตโนมัติไว้ ต้องถามแยกก่อนดันขึ้นคลาวด์ ----------
       ปฏิเสธคำถามที่สองแล้วข้อมูลในเครื่องยังต้องถูกล้างตามปกติ แค่ไม่ตั้งคิวส่งขึ้นคลาวด์
       (wipe()/reset() เองก็ล้างค่าซิงก์ทิ้งเป็นผลข้างเคียงอยู่แล้ว จึงพิสูจน์ผ่านปุ่มลบข้อมูลได้ตรง ๆ) */
    {
      const { page, errors } = await openAs(browser, srv.url, "admin");
      let dialogs = [];
      page.on("dialog", async (d) => {
        const accept = dialogs.shift();
        if (accept) await d.accept(); else await d.dismiss();
      });
      await page.evaluate(() => {
        syncCfg().url = "https://example.invalid/logbook"; syncCfg().auto = true;
        syncCfg().pending = false;
      });
      dialogs = [true, false]; /* ยืนยันลบ → ปฏิเสธการดันขึ้นคลาวด์ */
      await page.evaluate(() => { document.querySelector("#btnWipe").click(); });
      const afterDecline = await page.evaluate(() => ({
        residents: store.data.residents.length, pending: !!syncCfg().pending
      }));
      t.check("ปฏิเสธการดันขึ้นคลาวด์แล้ว ข้อมูลในเครื่องยังถูกล้างตามปกติ", afterDecline.residents === 0);
      t.check("ปฏิเสธการดันขึ้นคลาวด์แล้ว ไม่ตั้งคิวส่งขึ้นคลาวด์", afterDecline.pending === false);
      t.check("ปุ่มลบข้อมูล + ปฏิเสธดันขึ้นคลาวด์: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }

    /* ---------- กลไก confirmCloudPushGate/runDestructiveDataOp เอง ----------
       ทดสอบตรงที่ตัวกลไก ไม่ผ่านปุ่ม UI เพราะ wipe()/reset() ล้างเป้าหมายซิงก์ทิ้งเองอยู่แล้ว
       จึงไม่เห็นผลต่างของ pending หลัง save() — ต้องพิสูจน์ด้วยการกระทำที่ไม่ล้างเป้าหมายซิงก์ */
    {
      const { page, errors } = await openAs(browser, srv.url, "admin");
      let dialogAnswer = true;
      page.on("dialog", async (d) => { if (dialogAnswer) await d.accept(); else await d.dismiss(); });

      const noTarget = await page.evaluate(() => {
        syncCfg().url = ""; syncCfg().auto = true;
        return confirmCloudPushGate(); /* ไม่มีเป้าหมาย → ผ่านเลยไม่ต้องถาม */
      });
      t.check("ไม่มีเป้าหมายซิงก์ → ไม่มีคำถามซ้อน ผ่านทันที", noTarget === true);

      dialogAnswer = false;
      const declined = await page.evaluate(() => {
        syncCfg().url = "https://example.invalid/logbook"; syncCfg().pending = false;
        let ran = false;
        runDestructiveDataOp(() => { ran = true; store.data.activities.push({ id:"a_gate_test" }); store.save(); });
        return { ran, pending: !!syncCfg().pending, activities: store.data.activities.length };
      });
      t.check("ปฏิเสธคำถามที่สองแล้ว การกระทำยังรันจริง", declined.ran);
      t.check("ปฏิเสธคำถามที่สองแล้ว ไม่ตั้งคิวส่งขึ้นคลาวด์ (markDirty ถูกกด suppress)", declined.pending === false);

      dialogAnswer = true;
      const accepted = await page.evaluate(() => {
        syncCfg().pending = false;
        let ran = false;
        runDestructiveDataOp(() => { ran = true; store.data.activities.push({ id:"a_gate_test2" }); store.save(); });
        return { ran, pending: !!syncCfg().pending };
      });
      t.check("ยอมรับคำถามที่สองแล้ว การกระทำรันจริง", accepted.ran);
      t.check("ยอมรับคำถามที่สองแล้ว ตั้งคิวส่งขึ้นคลาวด์ตามปกติ", accepted.pending === true);
      t.check("กลไกยืนยันก่อนดันขึ้นคลาวด์: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }
  } finally {
    await browser.close();
    await srv.close();
  }
  return t;
}
