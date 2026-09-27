/* สองเรื่องของการซิงก์หลายเครื่องที่ทำให้สิ่งที่คนอื่นแก้หายไปเงียบ ๆ
   1) ก้อนคอนฟิก (เกณฑ์ พันธกิจ เป้าหมาย EPA คำค้น) เคยรวมกันทั้งก้อน — สองคนแก้คนละช่อง ฝั่งหนึ่งหายทั้งหมด
   2) เครื่องที่ไม่ได้เปิดข้ามปีการศึกษา เลื่อนชั้นปีเองจากทะเบียนเก่าตอนโหลด แล้วดันขึ้นคลาวด์ชนะการรวมข้อมูล
      ทับสิ่งที่เครื่องอื่นแก้ในทะเบียนหลังเลื่อนไปแล้ว
   ทุกข้อเคยพังจริง อย่าลบออกโดยไม่เข้าใจว่ามันกันอะไรอยู่ */
import { chromium } from "playwright";
import { serve, launchOptions, openAs, suite } from "./lib.mjs";

const CLOUD = "https://cloud.test.invalid/api/portfolio";

/* จำลองคลาวด์ในหน้าเว็บ: GET คืนชุดของเครื่องอื่น · PUT ที่ baseRev ไม่ตรงได้ 409 พร้อมชุดของคลาวด์
   ต้องติดตั้งก่อนสคริปต์ของแอปทำงาน (addInitScript) เพราะการรวมข้อมูลตอนเปิดแอปเกิดเองอัตโนมัติ */
function fakeCloud({ url, getStatus }) {
  const remote = JSON.parse(localStorage.getItem("__test_remote") || "null");
  if (!remote) return;
  const real = window.fetch;
  window.fetch = async (u, opts = {}) => {
    if (String(u) !== url) return real(u, opts);
    const log = JSON.parse(localStorage.getItem("__test_calls") || "[]");
    const method = (opts.method || "GET").toUpperCase();
    if (method === "GET") {
      log.push("GET"); localStorage.setItem("__test_calls", JSON.stringify(log));
      if (getStatus !== 200) return new Response("down", { status: getStatus });
      return new Response(JSON.stringify({ rev: 10, updatedAt: new Date().toISOString(), device: "เครื่องอื่น", data: remote }), { status: 200 });
    }
    const body = JSON.parse(opts.body || "{}");
    log.push("PUT@" + body.baseRev); localStorage.setItem("__test_calls", JSON.stringify(log));
    if (body.baseRev !== 10) return new Response(JSON.stringify({ rev: 10, data: remote }), { status: 409 });
    localStorage.setItem("__test_put", JSON.stringify(body.data));
    return new Response(JSON.stringify({ rev: 11, updatedAt: new Date().toISOString(), bytes: 10 }), { status: 200 });
  };
}

/* เตรียมเครื่องนี้ให้เป็น "เครื่องที่ไม่ได้เปิดข้ามปีการศึกษา" และเตรียมชุดของคลาวด์ที่เครื่องอื่นเลื่อนชั้นปีแล้ว
   และแก้ทะเบียนต่อหลังเลื่อน (เปลี่ยนอาจารย์ที่ปรึกษาของคนหนึ่ง) */
async function staleDevice(page) {
  return page.evaluate(({ url }) => {
    const ay = String(currentAY());
    const cfg = syncCfg();
    Object.assign(cfg, { mode: "full", auto: true, cloudUrl: url, rev: 5, token: "" });
    store.setRolledAY(+ay - 1);                    /* ทะเบียนในเครื่องนี้ยังเป็นของปีก่อน */
    /* เครื่องอื่น: เลื่อนชั้นปี แล้วแก้ทะเบียนต่อ */
    store.rollAcademicYear(ay, "auto");
    const remote = JSON.parse(JSON.stringify(fullPayload()));
    const target = remote.residents.find(r => r.active !== false && r.year === 3);
    target.advisor = "อ.ที่แก้จากเครื่องอื่นหลังเลื่อนชั้นปี";
    store.undoYearRoll(); store.save();             /* เครื่องนี้กลับไปเป็นทะเบียนของปีก่อน */
    /* ฐานเปรียบเทียบต้องถ่ายหลังย้อนกลับ — undoYearRoll คืนค่าไม่ตรงไบต์เดิม (เช่น เติม graduatedAY:"")
       ถ้าถ่ายก่อน เครื่องนี้จะดูเหมือนแก้ทะเบียนทุกคน ซึ่งไม่ใช่สถานการณ์ที่ต้องการทดสอบ */
    const stale = JSON.parse(JSON.stringify(fullPayload()));
    writeBaseline(5, stale);                        /* ซิงก์กับคลาวด์ครั้งล่าสุดตอนก่อนขึ้นปีใหม่ */
    localStorage.setItem("__test_remote", JSON.stringify(remote));
    localStorage.removeItem("__test_put"); localStorage.removeItem("__test_calls");
    return { ay, targetId: target.id, remoteYears: Object.fromEntries(remote.residents.map(r => [r.id, r.year])),
             localCursor: store.data.meta.yearRolledAY };
  }, { url: CLOUD });
}

export default async function run() {
  const t = suite("ซิงก์หลายเครื่อง · คอนฟิกรายช่อง · เลื่อนชั้นปีหลังรวมข้อมูล");
  const srv = await serve();
  const browser = await chromium.launch(launchOptions());
  try {
    /* ---------- 1) ก้อนคอนฟิกรวมรายช่อง ---------- */
    {
      const { page, errors } = await openAs(browser, srv.url, "admin");
      const r = await page.evaluate(() => {
        const empty = {};
        const run = (key, b, m, th) => mergeDatasets({ ...empty, [key]: b }, { ...empty, [key]: m }, { ...empty, [key]: th });
        const prog = run("programme", { mission: "เดิม", reviewed: "2026-01-01" },
                                      { mission: "แก้โดยเครื่องนี้", reviewed: "2026-01-01" },
                                      { mission: "เดิม", reviewed: "2026-09-01" });
        const reqs = run("requirements", { 2: { topic: 6, preop: 24 }, 3: { topic: 6 } },
                                         { 2: { topic: 7, preop: 24 }, 3: { topic: 6 } },
                                         { 2: { topic: 6, preop: 30 }, 3: { topic: 8 } });
        const same = run("requirements", { 2: { topic: 6 } }, { 2: { topic: 7 } }, { 2: { topic: 9 } });
        const del = run("keywords", { trauma: ["a"], spine: ["b"] }, { spine: ["b"] }, { trauma: ["a"], spine: ["b"] });
        const form = run("rotationForm", { v: 1, items: ["a"] }, { v: 1, items: ["a", "b"] }, { v: 1, items: ["a", "c"] });
        return {
          prog: prog.merged.programme, progConf: prog.conflicts.length,
          reqs: reqs.merged.requirements, reqsConf: reqs.conflicts.length,
          same: same.merged.requirements, sameConf: same.conflicts.map(c => c.key + ":" + c.id),
          del: del.merged.keywords,
          form: form.merged.rotationForm, formConf: form.conflicts.map(c => c.id)
        };
      });
      t.eq("พันธกิจที่เครื่องนี้แก้ กับวันทบทวนที่เครื่องอื่นแก้ อยู่ครบทั้งคู่ ไม่ถือว่าชน",
           [r.prog, r.progConf], [{ mission: "แก้โดยเครื่องนี้", reviewed: "2026-09-01" }, 0]);
      t.eq("เกณฑ์รายชั้นปีรวมลงไปถึงรายช่อง — ต่างช่องกันไม่ทับกัน",
           [r.reqs, r.reqsConf], [{ 2: { topic: 7, preop: 30 }, 3: { topic: 8 } }, 0]);
      t.eq("ช่องเดียวกันแก้ทั้งสองฝั่ง → เก็บของเครื่องนี้ และบันทึกว่าชนที่ช่องนั้น",
           [r.same, r.sameConf], [{ 2: { topic: 7 } }, ["requirements:2.topic"]]);
      t.eq("ช่องที่เครื่องนี้ลบ และเครื่องอื่นไม่ได้แตะ → ลบจริง", r.del, { spine: ["b"] });
      t.eq("แบบประเมินลงกองยังไปทั้งชุด (ไม่เอาข้อของสองเครื่องมาสลับกัน) และบันทึกว่าชน",
           [r.form, r.formConf], [{ v: 1, items: ["a", "b"] }, ["(ทั้งชุด)"]]);
      t.check("คอนฟิกรายช่อง: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }

    /* ---------- 2) เครื่องที่ไม่ได้เปิดข้ามปีการศึกษา — รวมกับคลาวด์ก่อน แล้วค่อยเลื่อน ---------- */
    {
      const { page, errors } = await openAs(browser, srv.url, "admin");
      const s = await staleDevice(page);
      t.check("ตั้งต้น: ทะเบียนในเครื่องนี้เป็นของปีก่อน", +s.localCursor === +s.ay - 1, s.localCursor + " vs " + s.ay);
      await page.addInitScript(fakeCloud, { url: CLOUD, getStatus: 200 });
      await page.reload();
      await page.waitForFunction(() => !!localStorage.getItem("__test_put"), null, { timeout: 20000 }).catch(() => {});
      const r = await page.evaluate(({ targetId }) => {
        const put = JSON.parse(localStorage.getItem("__test_put") || "null");
        return {
          calls: JSON.parse(localStorage.getItem("__test_calls") || "[]"),
          advisor: store.resident(targetId)?.advisor || "",
          putAdvisor: put?.residents?.find(x => x.id === targetId)?.advisor || "",
          years: Object.fromEntries(store.data.residents.map(x => [x.id, x.year])),
          cursor: store.data.meta.yearRolledAY, synced: store.data.programme.yearRolledAY
        };
      }, s);
      t.check("ดึงของคลาวด์ก่อน แล้วค่อยส่งขึ้น", r.calls[0] === "GET" && r.calls.includes("PUT@10"), r.calls.join(" → "));
      t.eq("การแก้ทะเบียนของเครื่องอื่นหลังเลื่อนชั้นปี ไม่ถูกทะเบียนที่เลื่อนจากของเก่าทับ", r.advisor, "อ.ที่แก้จากเครื่องอื่นหลังเลื่อนชั้นปี");
      t.eq("ชุดที่ส่งขึ้นคลาวด์ก็ยังเป็นฉบับที่แก้แล้ว", r.putAdvisor, "อ.ที่แก้จากเครื่องอื่นหลังเลื่อนชั้นปี");
      t.eq("ชั้นปีของทุกคนตรงกับที่เครื่องอื่นเลื่อนไว้ — ไม่เลื่อนซ้ำ", r.years, s.remoteYears);
      t.eq("ตัวชี้ปีที่เลื่อนแล้ว ทั้งในเครื่องและฉบับที่ซิงก์ เป็นปีปัจจุบัน", [r.cursor, r.synced], [s.ay, s.ay]);
      t.check("รวมก่อนเลื่อน: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }

    /* ---------- 3) ดึงจากคลาวด์ไม่ได้ → ยังเลื่อนชั้นปีจากข้อมูลในเครื่องครั้งเดียว ไม่ค้างปีเก่า ---------- */
    {
      const { page, errors } = await openAs(browser, srv.url, "admin");
      const s = await staleDevice(page);
      const before = await page.evaluate(() => Object.fromEntries(store.data.residents.map(x => [x.id, x.year])));
      await page.addInitScript(fakeCloud, { url: CLOUD, getStatus: 503 });
      await page.reload();
      await page.waitForFunction(() => store.data.meta.yearRolledAY === String(currentAY()), null, { timeout: 20000 }).catch(() => {});
      const r = await page.evaluate(() => ({
        calls: JSON.parse(localStorage.getItem("__test_calls") || "[]"),
        years: Object.fromEntries(store.data.residents.map(x => [x.id, x.year])),
        cursor: store.data.meta.yearRolledAY, status: syncCfg().lastStatus || ""
      }));
      const onceOk = Object.entries(before).every(([id, y]) => r.years[id] === (y >= 4 ? 4 : y + 1));
      t.check("ดึงไม่ได้ก็ยังเลื่อนชั้นปีจากข้อมูลในเครื่อง (ครั้งเดียว)", r.cursor === s.ay && onceOk, JSON.stringify(r.calls));
      t.check("บันทึกสถานะไว้ให้เห็นว่ายังไม่ได้รวมกับคลาวด์", /ก่อนเลื่อนชั้นปีไม่สำเร็จ/.test(r.status), r.status);
      t.check("ดึงไม่ได้: ไม่มี error หลุดในคอนโซล", errors.filter(e => !/503|Failed to load resource/.test(e)).length === 0, errors.join(" | "));
      await page.close();
    }
  } finally {
    await browser.close();
    await srv.close();
  }
  return t;
}
