/* ด่านแรก เร็วที่สุด และไม่ต้องใช้เบราว์เซอร์:
   หน้านี้เป็นไฟล์เดียวที่ไม่มีขั้นตอน build จึงไม่มีอะไรมาเตือนตอนพิมพ์ผิด
   เคยพังมาแล้วจากการมี </script> หลุดเข้าไปในโค้ด ซึ่งปิดบล็อกสคริปต์กลางคัน */
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { ROOT, suite } from "./lib.mjs";

export default function run() {
  const t = suite("โครงสร้างไฟล์และไวยากรณ์");
  const html = fs.readFileSync(path.join(ROOT, "portfolio/index.html"), "utf8");

  const blocks = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m => m[1]);
  t.check("มีบล็อกสคริปต์ในหน้า", blocks.length > 0, blocks.length + " บล็อก");

  const app = blocks.reduce((a, b) => (b.length > a.length ? b : a), "");
  t.check("บล็อกหลักยาวเกิน 100 KB (ไม่ถูกตัดกลางคัน)", app.length > 100000,
          Math.round(app.length / 1024) + " KB");

  let syntax = "";
  try { new vm.Script(app); } catch (e) { syntax = e.message; }
  t.check("JavaScript ทั้งบล็อกคอมไพล์ผ่าน", !syntax, syntax);

  /* </script> ที่ต้องอยู่ในสตริงต้องถูก escape ไว้เสมอ ไม่งั้นเบราว์เซอร์ปิดบล็อกให้ตรงนั้น */
  t.check("ไม่มี </script> ที่ไม่ได้ escape อยู่ในโค้ด",
          !app.includes("</scr" + "ipt>"));

  /* กฎของโปรเจกต์: ไม่มี dependency ภายนอก ไม่มี asset ภายนอก */
  const ext = [...html.matchAll(/(?:src|href)="(https?:)?\/\/[^"]+"/g)].map(m => m[0]);
  t.check("ไม่มีการอ้าง asset จากภายนอก", ext.length === 0, ext.join(", "));

  for (const f of ["portfolio/sw.js", "portfolio/manifest.webmanifest"]) {
    const s = fs.readFileSync(path.join(ROOT, f), "utf8");
    let err = "";
    try { f.endsWith(".js") ? new vm.Script(s) : JSON.parse(s); } catch (e) { err = e.message; }
    t.check(f + " ใช้ได้", !err, err);
  }
  return t;
}
