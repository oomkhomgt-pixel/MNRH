/* เส้นทางนำเข้าเคสจาก API ของระบบคิว — ทดสอบกับตัวจำลองที่อยู่ใน or-queue-mock/
   ระบบคิวจริงอยู่ใน intranet ของโรงพยาบาล เข้าถึงจากที่นี่ไม่ได้ */
import { spawn } from "node:child_process";
import path from "node:path";
import { chromium } from "playwright";
import { ROOT, serve, launchOptions, openAs, suite } from "./lib.mjs";

function startMock() {
  return new Promise((ok, fail) => {
    const proc = spawn(process.execPath, [path.join(ROOT, "or-queue-mock", "server.js")],
                       { env: { ...process.env, PORT: "0", DAYS_BACK: "30", DAYS_AHEAD: "7" } });
    const timer = setTimeout(() => fail(new Error("ตัวจำลองไม่ตอบใน 10 วินาที")), 10000);
    proc.stdout.on("data", buf => {
      const m = String(buf).match(/127\.0\.0\.1:(\d+)/);
      if (!m) return;
      clearTimeout(timer);
      ok({ url: "http://127.0.0.1:" + m[1], stop: () => proc.kill() });
    });
    proc.on("error", fail);
  });
}

export default async function run() {
  const t = suite("นำเข้าเคสจาก API ของระบบคิว");
  const srv = await serve();
  const mock = await startMock();
  const browser = await chromium.launch(launchOptions());
  try {
    const { page, errors } = await openAs(browser, srv.url, "admin");

    const first = await page.evaluate(async (base) => {
      store.data.cases = [];
      Object.assign(store.data.orQueue, { apiBase: base, apiPath: "/api/cases?scope=all&includeClosed=true" });
      const r = await importFromApi();
      const c = store.data.cases[0];
      return { ...r, stored: store.data.cases.length,
               hasOperation: !!c?.operation, hasDiagnosis: !!c?.diagnosis,
               hasDate: /^\d{4}-\d{2}-\d{2}$/.test(c?.date || ""),
               sub: c?.subspecialty, surgeon: c?.primarySurgeon,
               noPatientName: !("name" in (c || {})) && !("patientName" in (c || {})),
               suggested: store.data.cases.filter(x => x.participants?.length).length };
    }, mock.url);
    t.check("ดึงเคสจาก API ได้", first.added > 0, first.added + " เคส");
    t.check("ฟิลด์ที่ต้องใช้มาครบ", first.hasOperation && first.hasDiagnosis && first.hasDate,
            first.sub + " · " + first.surgeon);
    t.check("ไม่มีชื่อผู้ป่วยติดเข้ามา", first.noPatientName);
    t.check("ระบบเดาผู้ร่วมผ่าตัดจากตารางหมุนเวียนให้", first.suggested > 0,
            first.suggested + " เคสมีผู้ร่วมผ่าตัดที่ระบบเสนอ");

    /* ดึงซ้ำต้องไม่เพิ่มรายการ และต้องไม่ลบผู้ร่วมผ่าตัดที่ยืนยันไว้แล้ว */
    const again = await page.evaluate(async () => {
      const c = store.data.cases.find(x => x.participants?.length);
      c.participants[0].verified = true;
      const before = store.data.cases.length;
      const r = await importFromApi();
      const same = store.data.cases.find(x => x.id === c.id);
      return { added: r.added, updated: r.updated, before, after: store.data.cases.length,
               keptVerified: !!same?.participants?.[0]?.verified };
    });
    t.eq("ดึงซ้ำแล้วไม่มีรายการเพิ่ม", [again.added, again.after], [0, again.before]);
    t.check("อัปเดตของเดิมแทนการสร้างใหม่", again.updated > 0, again.updated + " เคส");
    t.check("ผู้ร่วมผ่าตัดที่อาจารย์รับรองแล้วไม่ถูกลบตอนดึงซ้ำ", again.keptVerified);

    /* ระดับข้อมูลผู้ป่วยที่ตั้งไว้ ต้องมีผลกับสิ่งที่นำเข้าจริง */
    const levels = await page.evaluate(async () => {
      const take = async (level) => {
        store.data.orQueue.patientData = level;
        store.data.cases = [];
        await importFromApi();
        const c = store.data.cases[0];
        return { hn: c.hn, age: String(c.age ?? ""), sex: c.sex };
      };
      const full = await take("full"), nohn = await take("nohn"), minimal = await take("minimal");
      store.data.orQueue.patientData = "full";
      return { full, nohn, minimal };
    });
    t.check("ระดับ full เก็บ HN ได้", levels.full.hn.startsWith("MOCK-"), levels.full.hn);
    t.check("ระดับ nohn ไม่เก็บ HN แต่ยังมีอายุ/เพศ",
            !levels.nohn.hn && !!levels.nohn.age, JSON.stringify(levels.nohn));
    t.check("ระดับ minimal ไม่เก็บข้อมูลผู้ป่วยเลย",
            !levels.minimal.hn && !levels.minimal.age && !levels.minimal.sex, JSON.stringify(levels.minimal));

    /* ระบบคิวมีปัญหา — หน้าเว็บต้องบอกสาเหตุ ไม่ใช่เงียบหรือพัง */
    const failures = await page.evaluate(async (base) => {
      const tryPath = async (p) => {
        Object.assign(store.data.orQueue, { apiBase: base, apiPath: p });
        try { const r = await importFromApi(); return "ok:" + r.added; }
        catch (e) { return "err:" + e.message; }
      };
      const five = await tryPath("/api/cases?_fail=500");
      const empty = await tryPath("/api/cases?_fail=empty");
      const garbage = await tryPath("/api/cases?_fail=garbage");
      Object.assign(store.data.orQueue, { apiBase: "http://127.0.0.1:9", apiPath: "/api/cases" });
      let wrongHost;
      try { await importFromApi(); wrongHost = "ok"; } catch (e) { wrongHost = "err:" + e.message; }
      return { five, empty, garbage, wrongHost };
    }, mock.url);
    t.check("ระบบคิวตอบ 500 → บอกรหัสสถานะ", failures.five.includes("HTTP 500"), failures.five);
    t.check("ไม่มีเคสในคำตอบ → บอกว่าเชื่อมต่อได้แต่ไม่พบเคส", failures.empty.startsWith("err:"), failures.empty);
    t.check("คำตอบไม่มีเคสอยู่ข้างใน → ไม่เงียบ", failures.garbage.startsWith("err:"), failures.garbage);
    t.check("ต่อไม่ติด → บอกว่าต่อไม่ได้ ไม่ใช่ค้าง", failures.wrongHost.startsWith("err:"), failures.wrongHost);

    await page.close();
  } finally {
    await browser.close();
    mock.stop();
    await srv.close();
  }
  return t;
}
