/* สร้างไอคอนแอปจากโลโก้จริงของกลุ่มงาน — ไม่ได้วาดใหม่
   logo-lockup.png = ต้นไม้ + คำว่า "Ortho Korat" ตัดมาจากไฟล์โลโก้ตรง ๆ

   โครงเดียวกับไอคอนของระบบคิวห้องผ่าตัด: โลโก้ด้านบน ชื่อระบบล่างกลาง
   ต่างกันตรงที่ชื่อของแฟ้มสะสมงานอยู่ใน "แถบทึบ" ส่วนของระบบคิวเป็นข้อความเปล่า
   แถบสำคัญเพราะที่ 48px ตัวอักษรอ่านไม่ออกแล้วทั้งคู่ — แถบเป็นสิ่งเดียวที่ยังเห็น

   รัน:  CHROMIUM_PATH=... node portfolio/docs/make-icons.mjs        (ต้องมี playwright)  */
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const DIR   = path.join(path.dirname(new URL(import.meta.url).pathname), "..");
const TEAL  = "#0A5570";                        /* สีน้ำเงินเขียวของ CI */
const LABEL = "PORTFOLIO";
const LOGO  = "data:image/png;base64," + fs.readFileSync(path.join(DIR, "logo-lockup.png")).toString("base64");
const ASPECT = 1.666;                           /* สัดส่วนของ logo-lockup.png */

/* inset > 0 = ย่อทั้งก้อนเข้ามาให้อยู่ในวงปลอดภัยของ Android (ไอคอนแบบ maskable) */
const page = (inset) => {
  const s = 1 - inset * 2;
  const W = Math.round(430 * s), Hh = Math.round(430 / ASPECT * s);
  const band = Math.round(112 * s);
  const top = Math.round((512 * s - band - Hh) / 2);
  const radius = inset > 0 ? `border-radius:${Math.round(44 * s)}px;overflow:hidden;` : "";
  return `<style>
    html,body{margin:0;width:512px;height:512px;background:#fff}
    .box{position:absolute;left:${inset*512}px;top:${inset*512}px;width:${512*s}px;height:${512*s}px;
         background:#fff;${radius}font-family:system-ui,'Noto Sans Thai',sans-serif}
    img{display:block;width:${W}px;height:${Hh}px;margin:${top}px auto 0}
    .band{position:absolute;left:0;right:0;bottom:0;height:${band}px;background:${TEAL};color:#fff;
          font-weight:700;font-size:${Math.round(44*s)}px;letter-spacing:${(3*s).toFixed(1)}px;
          display:flex;align-items:center;justify-content:center;line-height:1}
  </style><div class="box"><img src="${LOGO}"/><div class="band">${LABEL}</div></div>`;
};

const FILES = [["icon-512.png", 512, 0], ["icon-192.png", 192, 0],
               ["apple-touch-icon.png", 180, 0], ["icon-maskable-512.png", 512, 0.12]];
const b = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH, args: ["--no-sandbox"] });
for (const [name, px, inset] of FILES) {
  const p = await b.newPage({ viewport: { width: 512, height: 512 }, deviceScaleFactor: px / 512 });
  await p.setContent(page(inset));
  await p.waitForTimeout(150);
  await p.screenshot({ path: path.join(DIR, name) });
  await p.close();
  console.log(name, px + "px", inset ? "· inset " + inset : "");
}
await b.close();
