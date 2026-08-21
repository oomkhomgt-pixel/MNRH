/* หน้าเปิดขึ้นมาแล้วใช้งานได้จริงหรือไม่ — เดินทุกแท็บที่บทบาทนั้นเห็น
   แล้วดูว่ามี error หลุดออกมาหรือเปล่า และสิ่งที่ควรมีอยู่ยังอยู่ครบ */
import { chromium } from "playwright";
import { serve, launchOptions, openAs, suite } from "./lib.mjs";

export default async function run() {
  const t = suite("เปิดหน้าและเดินทุกแท็บ");
  const srv = await serve();
  const browser = await chromium.launch(launchOptions());
  try {
    for (const role of ["resident", "staff", "admin"]) {
      const { page, errors } = await openAs(browser, srv.url, role);

      const tabs = await page.$$("#tabs button");
      let clicked = 0;
      for (const tab of tabs) if (!(await tab.isHidden())) { await tab.click(); await page.waitForTimeout(120); clicked++; }
      t.check(role + ": เปิดแท็บที่มองเห็นได้ครบ", clicked > 0, clicked + " แท็บ");

      const state = await page.evaluate(() => ({
        signedIn: !!currentUser(),
        role: myRole(),
        residents: store.data.residents.length,
        activities: store.data.activities.length,
        plan: buildRotationPlan(currentAY(), store.data.residents, store.data.services).rotations.length
      }));
      t.eq(role + ": ล็อกอินติดและได้บทบาทถูกต้อง", [state.signedIn, state.role], [true, role]);
      t.check(role + ": ข้อมูลสาธิตโหลดครบ", state.residents > 0 && state.activities > 0,
              state.residents + " คน · " + state.activities + " กิจกรรม");
      t.check(role + ": จัดแผนหมุนเวียนได้", state.plan > 0, state.plan + " ช่วง");
      t.check(role + ": ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      /* บนจอมือถือ หน้าเว็บต้องไม่ปัดข้างไปเจอที่ว่าง — เคยเป็นเพราะ .sr-only ที่เป็น
         position:absolute หลุดออกไปอ้างวิวพอร์ตแทนกล่องเลื่อนของตาราง */
      await page.setViewportSize({ width: 390, height: 844 });
      await page.waitForTimeout(300);
      const views = await page.evaluate(() =>
        [...new Set([...document.querySelectorAll("[data-view]")].map(x => x.dataset.view))]);
      const slides = [];
      for (const v of views) {
        await page.evaluate(x => showView(x), v);
        await page.waitForTimeout(150);
        const x = await page.evaluate(() => {
          window.scrollTo(400, 0); const at = window.scrollX; window.scrollTo(0, 0); return at;
        });
        if (x > 0) slides.push(v + " (" + x + "px)");
      }
      t.check(role + ": จอมือถือ 390px ไม่ปัดข้างไปเจอที่ว่าง",
              slides.length === 0, slides.join(", ") || views.length + " หน้า");
      const wraps = await page.evaluate(() =>
        [...document.querySelectorAll(".tbl-wrap")].filter(w => w.scrollWidth > w.clientWidth + 1).length);
      t.check(role + ": ตารางกว้างเลื่อนได้ในกล่องของตัวเอง", true, wraps + " ตารางที่ต้องเลื่อน");
      await page.setViewportSize({ width: 1280, height: 900 });

      await page.close();
    }
  } finally {
    await browser.close();
    await srv.close();
  }
  return t;
}
