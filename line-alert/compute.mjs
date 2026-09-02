/* คำนวณกิจกรรมของ "วันนี้" จาก dataset ที่ส่งมา — เปิด portfolio/index.html ตัวจริงแบบไม่มีหน้าจอ
   (headless Chromium) แล้วเรียก sessionsForDate()/topicConfInfo() ตัวเดียวกับที่คนใช้งานเห็นในแอปจริง
   ไม่มีการ port ตรรกะตารางเวรมาเขียนใหม่ใน Node เลย — ตรรกะการจัดตารางในโปรเจกต์นี้ซับซ้อนและถูกทดสอบไว้
   แล้วกว่า 1000 บรรทัดใน portfolio/tests/schedule.test.mjs ถ้าเขียนซ้ำจะมีความเสี่ยงสองฝั่งไม่ตรงกัน */
import { chromium } from "playwright";
import { serve, launchOptions } from "../portfolio/tests/lib.mjs";

/* iso: ถ้าไม่ระบุ ใช้ "วันนี้ตามเขตเวลาไทย" ของหน้าเว็บเอง (todayISO() ในแอป) */
export async function computeToday(data, iso) {
  const srv = await serve();
  const browser = await chromium.launch(launchOptions());
  try {
    /* เขตเวลาต้องเป็นเมืองไทยตรง ๆ ไม่พึ่ง TZ ของเครื่องที่รัน (CI อาจรันเป็น UTC) — กันบั๊กคลาสเดียวกับที่
       เคยแก้มาแล้วในโปรเจกต์นี้ (ดู portfolio/tests/schedule.test.mjs: "ทดสอบเขตเวลาไทย") */
    const page = await browser.newPage({ timezoneId: "Asia/Bangkok" });
    const errors = [];
    page.on("pageerror", e => errors.push("uncaught: " + e.message));
    page.on("console", m => { if (m.type() === "error") errors.push("console: " + m.text()); });

    await page.goto(srv.url + "/portfolio/index.html");
    await page.evaluate(() => localStorage.clear());
    await page.reload();
    await page.waitForFunction(() => typeof store !== "undefined" && store.data?.users?.length);

    /* แทนที่ข้อมูลสาธิตด้วย dataset จริงที่ส่งมา — เหมือนที่ importJson() ทำในแอป
       (store.data = data; store.migrate();) migrate() เผื่อไฟล์ export เก่ายังไม่มีธง topicConference */
    await page.evaluate((d) => { store.data = d; store.migrate(); }, data);

    const targetIso = iso || await page.evaluate(() => todayISO());
    const result = await page.evaluate((i) => ({
      sessions: sessionsForDate(i),
      topicConf: topicConfInfo(i)
    }), targetIso);

    if (errors.length) throw new Error("หน้าเว็บมี error ระหว่างคำนวณตาราง: " + errors.join(" | "));
    return { iso: targetIso, sessions: result.sessions, topicConf: result.topicConf };
  } finally {
    await browser.close();
    await srv.close();
  }
}
