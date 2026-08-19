/* เครื่องมือร่วมของชุดทดสอบ: เซิร์ฟเวอร์ไฟล์นิ่ง ตัวเปิดเบราว์เซอร์ และการรายงานผล
   ตั้งใจให้ไม่มี dependency นอกจาก playwright เพราะโปรเจกต์นี้ไม่มีขั้นตอน build */
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");

const MIME = {
  ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8", ".webmanifest": "application/manifest+json",
  ".png": "image/png", ".csv": "text/csv; charset=utf-8"
};

/* เสิร์ฟไฟล์จากโฟลเดอร์ repo เพื่อให้หน้าเว็บทำงานเหมือนตอนวางบนเซิร์ฟเวอร์จริง
   (เปิดด้วย file:// จะติดข้อจำกัดของ service worker และ fetch) */
export function serve() {
  const srv = http.createServer((req, res) => {
    const rel = decodeURIComponent(req.url.split("?")[0]).replace(/^\/+/, "");
    const file = path.join(ROOT, rel);
    if (!file.startsWith(ROOT) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
      res.writeHead(404).end("not found"); return;
    }
    res.writeHead(200, { "Content-Type": MIME[path.extname(file)] || "application/octet-stream" });
    fs.createReadStream(file).pipe(res);
  });
  return new Promise(ok => srv.listen(0, "127.0.0.1", () =>
    ok({ url: "http://127.0.0.1:" + srv.address().port, close: () => new Promise(r => srv.close(r)) })));
}

/* หา Chromium ที่ติดตั้งไว้: บนเครื่องที่ตั้งค่า PLAYWRIGHT_BROWSERS_PATH ไว้แล้วให้ใช้ตัวนั้น
   ส่วนบน CI ปล่อยให้ playwright หาเอง */
export function launchOptions() {
  const p = process.env.CHROMIUM_PATH;
  return p ? { executablePath: p } : {};
}

/* เปิดหน้าแฟ้มสะสมงานพร้อมล็อกอินเป็นบทบาทที่ต้องการ และเก็บ error ทุกชนิดที่หลุดออกมา */
export async function openAs(browser, base, role) {
  const errors = [];
  const page = await browser.newPage();
  page.on("pageerror", e => errors.push("uncaught: " + e.message));
  page.on("console", m => { if (m.type() === "error") errors.push("console: " + m.text()); });
  await page.goto(base + "/portfolio/index.html");
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  /* store/currentUser เป็น const ระดับสคริปต์ จึงไม่ได้อยู่บน window ต้องอ้างชื่อตรง ๆ */
  await page.waitForFunction(() => typeof store !== "undefined" && store.data?.users?.length);
  if (role) {
    await page.evaluate(r => {
      const u = store.data.users.find(x => x.role === r);
      localStorage.setItem("mnrh_ortho_portfolio_session_v1",
        JSON.stringify({ userId: u.id, at: new Date().toISOString() }));
    }, role);
    await page.reload();
    await page.waitForFunction(() => typeof currentUser === "function" && !!currentUser());
  }
  await page.waitForTimeout(300);
  return { page, errors };
}

/* ตัวรายงานผลอย่างง่าย — พอสำหรับชุดทดสอบขนาดนี้ และอ่านออกใน log ของ CI */
export function suite(name) {
  const results = [];
  const t = {
    name, results,
    check(label, ok, detail) { results.push({ label, ok: !!ok, detail }); return !!ok; },
    eq(label, got, want) {
      const ok = JSON.stringify(got) === JSON.stringify(want);
      return t.check(label, ok, ok ? "" : "ได้ " + JSON.stringify(got) + " ต้องการ " + JSON.stringify(want));
    },
    report() {
      const bad = results.filter(r => !r.ok);
      console.log("\n▸ " + name);
      results.forEach(r => console.log("  " + (r.ok ? "✓" : "✗") + " " + r.label + (r.detail ? " — " + r.detail : "")));
      return bad.length;
    }
  };
  return t;
}
