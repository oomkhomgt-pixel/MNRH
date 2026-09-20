/* การกระทำที่ทำลายข้อมูลทั้งก้อน — ล้างข้อมูล และนำเข้าไฟล์สำรอง
   สองอย่างนี้คือทางเดียวที่ผู้ใช้จะเสียข้อมูลของทั้งภาควิชาในคลิกเดียว จึงต้องกู้คืนได้เสมอ
   ทุกข้อในนี้เคยพังจริง อย่าลบออกโดยไม่เข้าใจว่ามันกันอะไรอยู่ */
import { chromium } from "playwright";
import { serve, launchOptions, openAs, suite } from "./lib.mjs";

export default async function run() {
  const t = suite("ล้างข้อมูล และนำเข้าไฟล์สำรอง");
  const srv = await serve();
  const browser = await chromium.launch(launchOptions());
  try {
    /* ---------- ล้างข้อมูลทั้งหมด แล้วต้องยังนำไฟล์สำรองกลับเข้ามาได้ ----------
       เดิม wipe() ล้าง users ทิ้งด้วย ทำให้ canManage() เป็น false ทันที แท็บตั้งค่าและปุ่ม
       "นำเข้าไฟล์สำรอง" ถูกซ่อน และเมื่อรีโหลด renderLoginGate() ก็ซ่อนหน้าเข้าสู่ระบบ
       (users ว่าง = โหมดที่ยังไม่ตั้งบัญชี) — ล็อกตัวเองออกถาวรทั้งที่เพิ่งถูกบอกให้สำรองไฟล์ไว้กู้ */
    {
      const { page, errors } = await openAs(browser, srv.url, "admin");
      const before = await page.evaluate(() => ({
        me: currentUser().username, users: store.data.users.length, residents: store.data.residents.length
      }));
      t.check("ตั้งต้นเป็นผู้จัดหลักสูตรที่มีข้อมูลจริง", before.residents > 0 && before.users > 1,
              before.residents + " คน · " + before.users + " บัญชี");

      const after = await page.evaluate(async () => {
        const realCD = confirmDialog; confirmDialog = async () => true;
        try { document.querySelector("#btnWipe").click(); await new Promise(r => setTimeout(r, 400)); }
        finally { confirmDialog = realCD; }
        return {
          residents: store.data.residents.length, activities: store.data.activities.length,
          users: store.data.users.length, me: currentUser()?.username || "",
          manage: canManage(),
          settingsHidden: !!document.querySelector('#tabs [data-view="settings"]')?.hidden,
          importHidden: !!document.querySelector("#btnImport")?.hidden
        };
      });
      t.eq("ข้อมูลถูกล้างจริง", [after.residents, after.activities], [0, 0]);
      t.eq("เหลือไว้เฉพาะบัญชีที่กำลังใช้อยู่", after.users, 1);
      t.eq("ยังเป็นคนเดิมที่ล็อกอินอยู่", after.me, before.me);
      t.check("ยังมีสิทธิ์ผู้จัดหลักสูตร", after.manage);
      t.check("แท็บตั้งค่ายังเปิดได้", !after.settingsHidden);
      t.check("ปุ่มนำเข้าไฟล์สำรองยังอยู่", !after.importHidden);

      /* รีโหลดแล้วต้องยังเข้าใช้งานได้ ไม่ใช่หน้าจอที่ไม่มีทั้งหน้าเข้าสู่ระบบและปุ่มนำเข้า */
      await page.reload();
      await page.waitForFunction(() => typeof store !== "undefined" && !!store.data);
      const reloaded = await page.evaluate(() => ({
        me: currentUser()?.username || "", manage: canManage(),
        gateHidden: !!document.querySelector("#loginGate")?.hidden,
        importHidden: !!document.querySelector("#btnImport")?.hidden,
        users: store.data.users.length
      }));
      t.eq("รีโหลดแล้วยังเป็นคนเดิม", reloaded.me, before.me);
      t.check("รีโหลดแล้วยังมีสิทธิ์และยังเห็นปุ่มนำเข้า", reloaded.manage && !reloaded.importHidden,
              reloaded.users + " บัญชี");

      /* กู้คืนจริงจากไฟล์สำรอง — ปิดวงจรที่กล่องยืนยันสัญญาไว้ */
      const restored = await page.evaluate(async () => {
        const backup = { residents:[{ id:"r_x", name:"นพ. ทดสอบกู้คืน", year:2, cohort:"2568", active:true }],
                         activities:[], users:[], meta:{} };
        const realCD = confirmDialog; confirmDialog = async () => true;
        try {
          importJson(new File([JSON.stringify(backup)], "backup.json", { type:"application/json" }));
          await new Promise(r => setTimeout(r, 600));
        } finally { confirmDialog = realCD; }
        return { residents: store.data.residents.length, name: store.data.residents[0]?.name || "" };
      });
      t.eq("นำไฟล์สำรองกลับเข้ามาได้หลังล้างข้อมูล", [restored.residents, restored.name],
           [1, "นพ. ทดสอบกู้คืน"]);
      t.check("ล้างข้อมูล: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }

    /* ---------- นำเข้าไฟล์ที่โครงสร้างพัง ต้องไม่แตะข้อมูลเดิมเลย ----------
       เดิม importJson() ทำ store.data = data ก่อน migrate() ถ้า migrate โยน error กลางทาง
       (เช่น "services": {} ซึ่ง ||= ไม่ทับให้ เพราะ object เป็น truthy) จะเหลือก้อนที่แปลงไม่จบ
       ค้างในหน่วยความจำ ทั้งที่ผู้ใช้เห็นข้อความ "นำเข้าไม่สำเร็จ" แล้วการบันทึกครั้งถัดไป
       จะเขียนก้อนนั้นทับข้อมูลจริงใน localStorage — ข้อมูลของทั้งภาควิชาหายแบบเงียบที่สุด */
    {
      const { page, errors } = await openAs(browser, srv.url, "admin");
      const before = await page.evaluate(() => {
        store.data.meta.__probe = "ของเดิมต้องอยู่ครบ";
        store.save();
        return { residents: store.data.residents.length, activities: store.data.activities.length };
      });

      const failed = await page.evaluate(async () => {
        /* ผ่านการตรวจโครงสร้างชั้นแรก (residents/activities เป็น array) แต่ services รูปร่างผิด */
        const bad = { residents:[], activities:[], services:{}, meta:{} };
        const realCD = confirmDialog; confirmDialog = async () => true;
        const toasts = [];
        const realToast = toast; toast = (m) => { toasts.push(m); return realToast(m); };
        try {
          importJson(new File([JSON.stringify(bad)], "bad.json", { type:"application/json" }));
          await new Promise(r => setTimeout(r, 600));
        } finally { confirmDialog = realCD; toast = realToast; }
        return {
          toasts,
          residents: store.data.residents.length, activities: store.data.activities.length,
          probe: store.data.meta.__probe || "",
          servicesIsArray: Array.isArray(store.data.services)
        };
      });
      t.check("ขึ้นข้อความว่านำเข้าไม่สำเร็จ", failed.toasts.some(m => m.includes("นำเข้าไม่สำเร็จ")),
              failed.toasts.join(" | "));
      t.eq("ข้อมูลในหน่วยความจำยังเป็นชุดเดิมครบ",
           [failed.residents, failed.activities], [before.residents, before.activities]);
      t.eq("ก้อนข้อมูลเดิมไม่ถูกสลับทิ้ง", failed.probe, "ของเดิมต้องอยู่ครบ");
      t.check("คอลเลกชันยังมีรูปร่างถูกต้อง", failed.servicesIsArray);

      /* ระเบิดเวลาของจริง: บันทึกครั้งถัดไปต้องไม่เขียนก้อนพังทับข้อมูลจริง */
      await page.evaluate(() => store.save());
      await page.reload();
      await page.waitForFunction(() => typeof store !== "undefined" && !!store.data);
      const persisted = await page.evaluate(() => ({
        residents: store.data.residents.length, activities: store.data.activities.length,
        probe: store.data.meta.__probe || ""
      }));
      t.eq("บันทึกแล้วรีโหลด ข้อมูลจริงยังอยู่ครบ",
           [persisted.residents, persisted.activities, persisted.probe],
           [before.residents, before.activities, "ของเดิมต้องอยู่ครบ"]);

      /* ไฟล์ที่ถูกต้องยังต้องนำเข้าได้ตามปกติ — ไม่ใช่กันพลาดจนใช้งานจริงไม่ได้ */
      const ok = await page.evaluate(async () => {
        const good = { residents:[{ id:"r_y", name:"นพ. ไฟล์ดี", year:3, cohort:"2567", active:true }],
                       activities:[], services:[], users:[], meta:{} };
        const realCD = confirmDialog; confirmDialog = async () => true;
        try {
          importJson(new File([JSON.stringify(good)], "good.json", { type:"application/json" }));
          await new Promise(r => setTimeout(r, 600));
        } finally { confirmDialog = realCD; }
        return { residents: store.data.residents.length, name: store.data.residents[0]?.name || "" };
      });
      t.eq("ไฟล์ที่ถูกต้องยังนำเข้าได้", [ok.residents, ok.name], [1, "นพ. ไฟล์ดี"]);
      t.check("นำเข้าไฟล์: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }
  } finally {
    await browser.close();
    await srv.close();
  }
  return t;
}
