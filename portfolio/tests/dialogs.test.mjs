/* กล่องโต้ตอบและการนำทางด้วยเบราว์เซอร์ — สองบั๊กที่เจอจากการตรวจ UX:
   (1) Enter ในช่องกรอกของกล่องเคยปิดกล่องทิ้งข้อมูล เพราะปุ่ม submit ตัวเดียวคือ "ปิด" ในหัว
   (2) ปุ่ม Back ของเบราว์เซอร์เปลี่ยน hash แต่หน้าไม่เปลี่ยน เพราะไม่มีใครฟัง hashchange */
import { chromium } from "playwright";
import { serve, launchOptions, openAs, suite } from "./lib.mjs";

export default async function run() {
  const t = suite("กล่องโต้ตอบ · Enter/Esc/focus · ปุ่ม Back");
  const srv = await serve();
  const browser = await chromium.launch(launchOptions());
  try {
    const { page, errors } = await openAs(browser, srv.url, "admin");

    /* ---------- focus ตกที่ช่องกรอกแรก ไม่ใช่ปุ่มปิด ---------- */
    const focus = await page.evaluate(() => {
      manualAdd();
      const a = document.activeElement;
      const r = { inBody: !!a?.closest("#dlgBody"), tag: a?.tagName, isClose: a?.id === "dlgClose" };
      document.querySelector("#dlg").close();
      return r;
    });
    t.check("เปิดกล่องแล้ว focus อยู่ในช่องกรอก ไม่ใช่ปุ่มปิด", focus.inBody && !focus.isClose, focus.tag);

    /* ---------- Enter ในช่องกรอก = บันทึก ---------- */
    const before = await page.evaluate(() => store.data.activities.length);
    await page.evaluate(() => manualAdd());
    await page.fill('#dlgBody [name="title"]', "ทดสอบกด Enter แล้วต้องบันทึก");
    await page.keyboard.press("Enter");
    await page.waitForTimeout(150);
    const enter = await page.evaluate(() => ({
      open: document.querySelector("#dlg").open,
      count: store.data.activities.length,
      saved: store.data.activities.some(a => a.title === "ทดสอบกด Enter แล้วต้องบันทึก")
    }));
    t.check("Enter แล้วกล่องปิด", !enter.open);
    t.check("Enter แล้วกิจกรรมถูกบันทึกจริง (ไม่ใช่ปิดทิ้ง)", enter.saved && enter.count === before + 1,
            "ก่อน " + before + " หลัง " + enter.count);

    /* ---------- Esc = ปิดโดยไม่บันทึก ---------- */
    await page.evaluate(() => manualAdd());
    await page.fill('#dlgBody [name="title"]', "ทดสอบกด Esc ต้องไม่บันทึก");
    await page.keyboard.press("Escape");
    await page.waitForTimeout(150);
    const esc = await page.evaluate(() => ({
      open: document.querySelector("#dlg").open,
      saved: store.data.activities.some(a => a.title === "ทดสอบกด Esc ต้องไม่บันทึก")
    }));
    t.check("Esc ปิดกล่องโดยไม่บันทึก", !esc.open && !esc.saved);

    /* ---------- กล่องดูอย่างเดียว (ไม่มีปุ่มหลัก) Enter ต้องไม่ปิด ---------- */
    const viewOnly = await page.evaluate(() => {
      showDialog("ทดสอบ", `<input name="x" value="1" />`, []);
      const form = document.querySelector("#dlgForm");
      form.requestSubmit();
      const r = { stillOpen: document.querySelector("#dlg").open };
      document.querySelector("#dlg").close();
      return r;
    });
    t.check("กล่องที่ไม่มีปุ่มหลัก: submit แล้วยังเปิดอยู่ ไม่ปิดทิ้ง", viewOnly.stillOpen);

    /* ---------- ปุ่ม Back ของเบราว์เซอร์ ---------- */
    await page.evaluate(() => { showView("epa"); showView("logbook"); });
    await page.goBack();
    await page.waitForTimeout(150);
    const back = await page.evaluate(() => ({ view: currentViewName(), hash: location.hash }));
    t.eq("กด Back แล้วกลับไปหน้าก่อนหน้า (EPA)", [back.view, back.hash], ["epa", "#epa"]);
    await page.goForward();
    await page.waitForTimeout(150);
    t.eq("กด Forward แล้วไปหน้า logbook", await page.evaluate(() => currentViewName()), "logbook");

    t.check("admin: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
    await page.close();

    /* ---------- resident: Back/hash ไปหน้าที่ไม่มีสิทธิ์ ต้องอยู่ที่เดิม ---------- */
    {
      const { page: rp, errors: re } = await openAs(browser, srv.url, "resident");
      await rp.evaluate(() => { showView("today"); location.hash = "settings"; });
      await rp.waitForTimeout(150);
      const r = await rp.evaluate(() => ({ view: currentViewName(), hash: location.hash }));
      t.eq("resident ใส่ hash หน้าตั้งค่า → หน้าไม่เปลี่ยน และ hash ถูกดึงกลับ", [r.view, r.hash], ["today", "#today"]);
      t.check("resident: ไม่มี error หลุดในคอนโซล", re.length === 0, re.join(" | "));
      await rp.close();
    }
  } finally {
    await browser.close();
    await srv.close();
  }
  return t;
}
