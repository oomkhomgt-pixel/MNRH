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
      await page.close();
    }
  } finally {
    await browser.close();
    await srv.close();
  }
  return t;
}
