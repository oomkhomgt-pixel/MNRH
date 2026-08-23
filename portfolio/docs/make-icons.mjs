/* สร้างไอคอนแอปจากโลโก้จริงของกลุ่มงาน — ไม่ได้วาดใหม่ ใช้ภาพต้นฉบับที่ตัดพื้นออกแล้ว
   โครงเดียวกับไอคอนของระบบคิวห้องผ่าตัด: โลโก้ด้านบน ป้ายชื่อล่างกลาง
   ต่างกันตรงที่ป้ายของแฟ้มสะสมงานอยู่ในแถบทึบ — เพราะที่ 48px ตัวอักษรอ่านไม่ออกแล้ว
   แต่แถบยังเห็น จึงเป็นสิ่งเดียวที่แยกสองแอปออกจากกันได้ทุกขนาด

   รัน:  node portfolio/docs/make-icons.mjs        (ต้องมี playwright)  */
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const DIR  = path.join(path.dirname(new URL(import.meta.url).pathname), "..");
const TEAL = "#0A5570";                         /* สีน้ำเงินเขียวของ CI */
const TREE = "data:image/png;base64," + fs.readFileSync(path.join(DIR, "logo-tree.png")).toString("base64");
const LABEL = "แฟ้ม";

/* inset > 0 = ย่อทั้งก้อนเข้ามาให้อยู่ในวงปลอดภัยของ Android (ไอคอนแบบ maskable) */
const page = (inset) => {
  const s = (1 - inset * 2);
  const band = Math.round(118 * s), tree = Math.round(286 * s);
  const radius = inset > 0 ? `border-radius:${Math.round(40 * s)}px;overflow:hidden;` : "";
  return `<style>
    html,body{margin:0;width:512px;height:512px;background:#fff}
    .box{position:absolute;left:${inset*512}px;top:${inset*512}px;
         width:${512*s}px;height:${512*s}px;background:#fff;${radius}
         font-family:system-ui,'Noto Sans Thai',sans-serif}
    img{display:block;height:${tree}px;width:auto;margin:${Math.round(26*s)}px auto 0}
    .band{position:absolute;left:0;right:0;bottom:0;height:${band}px;background:${TEAL};
          display:flex;align-items:center;justify-content:center;color:#fff;
          font-size:${Math.round(62*s)}px;font-weight:700;line-height:1}
  </style><div class="box"><img src="${TREE}"/><div class="band">${LABEL}</div></div>`;
};

const FILES = [["icon-512.png", 512, 0], ["icon-192.png", 192, 0],
               ["apple-touch-icon.png", 180, 0], ["icon-maskable-512.png", 512, 0.13]];
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
