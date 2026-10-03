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
  if (!localStorage.getItem("__test_remote")) return;
  /* คลาวด์มีสถานะเหมือนเซิร์ฟเวอร์จริง: PUT ที่สำเร็จกลายเป็นชุดใหม่บนคลาวด์และขึ้นรุ่นใหม่ — ถ้าไม่เก็บ
     PUT รอบถัดไปจะได้ 409 กับชุดเก่า แล้วการรวมข้อมูลจะเอาค่าเก่ากลับมาบังบั๊กที่กำลังทดสอบ */
  const state = () => ({ rev: +(localStorage.getItem("__test_rev") || 10), data: JSON.parse(localStorage.getItem("__test_remote")) });
  const real = window.fetch;
  window.fetch = async (u, opts = {}) => {
    if (String(u) !== url) return real(u, opts);
    const log = JSON.parse(localStorage.getItem("__test_calls") || "[]");
    const method = (opts.method || "GET").toUpperCase();
    const cur = state();
    if (method === "GET") {
      log.push("GET"); localStorage.setItem("__test_calls", JSON.stringify(log));
      /* สถานะของคลาวด์สลับได้ระหว่างเทสต์ (ล่ม → กลับมา) ผ่าน localStorage */
      const st = +(localStorage.getItem("__test_getStatus") || getStatus);
      if (st !== 200) return new Response("down", { status: st });
      return new Response(JSON.stringify({ rev: cur.rev, updatedAt: new Date().toISOString(), device: "เครื่องอื่น", data: cur.data }), { status: 200 });
    }
    const body = JSON.parse(opts.body || "{}");
    log.push("PUT@" + body.baseRev); localStorage.setItem("__test_calls", JSON.stringify(log));
    if (body.baseRev !== cur.rev) return new Response(JSON.stringify({ rev: cur.rev, data: cur.data }), { status: 409 });
    localStorage.setItem("__test_put", JSON.stringify(body.data));
    localStorage.setItem("__test_remote", JSON.stringify(body.data));
    localStorage.setItem("__test_rev", String(cur.rev + 1));
    return new Response(JSON.stringify({ rev: cur.rev + 1, updatedAt: new Date().toISOString(), bytes: 10 }), { status: 200 });
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
    /* ถ่ายฐานเปรียบเทียบหลังย้อนกลับ ให้ฐานตรงกับของในเครื่องแน่นอนโดยไม่ขึ้นกับรายละเอียดของ undoYearRoll
       (ว่าย้อนกลับตรงทุกไบต์หรือไม่ ตรวจแยกในบล็อกที่ 4) */
    const stale = JSON.parse(JSON.stringify(fullPayload()));
    writeBaseline(5, stale);                        /* ซิงก์กับคลาวด์ครั้งล่าสุดตอนก่อนขึ้นปีใหม่ */
    localStorage.setItem("__test_remote", JSON.stringify(remote));
    localStorage.removeItem("__test_put"); localStorage.removeItem("__test_calls"); localStorage.removeItem("__test_rev"); localStorage.removeItem("__test_getStatus");
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

    /* ---------- 3) ดึงจากคลาวด์ไม่ได้ → เลื่อนชั่วคราวในเครื่อง ไม่ส่งทะเบียนนั้นขึ้นไป · คลาวด์กลับมาแล้วค่อยรวม ----------
       เดิมเลื่อนจากข้อมูลในเครื่องแล้วดันขึ้นทันทีที่ติดต่อได้ ทะเบียนที่เลื่อนจากของเก่าไปแข่งกับของเครื่องอื่น
       ที่เลื่อนและแก้ต่อไปแล้ว — ตอนนี้ต้องรวมกับของคลาวด์ก่อนเสมอ แบบเดียวกับตอนออนไลน์ */
    {
      const { page, errors } = await openAs(browser, srv.url, "admin");
      const s = await staleDevice(page);
      const before = await page.evaluate(() => Object.fromEntries(store.data.residents.map(x => [x.id, x.year])));
      /* เครื่องอื่นให้คนหนึ่งซ้ำชั้นหลังเลื่อน (ชั้นปีกลับเป็นค่าเดิมก่อนเลื่อน) — ค่าบนคลาวด์จึงเท่ากับฐานเปรียบเทียบ
         ถ้าเครื่องนี้ส่งทะเบียนที่เลื่อนเองขึ้นไป การรวมข้อมูลจะเห็นว่า "เครื่องนี้แก้ฝั่งเดียว" แล้วทับการซ้ำชั้นเงียบ ๆ */
      const repeater = await page.evaluate(({ targetId }) => {
        const remote = JSON.parse(localStorage.getItem("__test_remote"));
        const x = remote.residents.find(r => r.active !== false && r.year === 3 && r.id !== targetId);
        x.year = 2;
        localStorage.setItem("__test_remote", JSON.stringify(remote));
        return x.id;
      }, s);
      s.remoteYears[repeater] = 2;
      await page.addInitScript(fakeCloud, { url: CLOUD, getStatus: 503 });
      await page.reload();
      await page.waitForFunction(() => store.data.meta.yearRolledAY === String(currentAY()), null, { timeout: 20000 }).catch(() => {});
      await page.waitForTimeout(3000);
      const off = await page.evaluate(({ targetId }) => {
        /* ระหว่างออฟไลน์ ผู้จัดหลักสูตรแก้ชื่อย่อของคนนั้นต่อ — ต้องอยู่รอดหลังรวมกับคลาวด์ */
        store.resident(targetId).nick = "แก้ตอนออฟไลน์หลังเลื่อน";
        suppressDirty = true; store.save(); suppressDirty = false;
        return {
          calls: JSON.parse(localStorage.getItem("__test_calls") || "[]"),
          years: Object.fromEntries(store.data.residents.map(x => [x.id, x.year])),
          cursor: store.data.meta.yearRolledAY, provisional: !!store.data.meta.provisionalRoll,
          status: syncCfg().lastStatus || "", put: !!localStorage.getItem("__test_put")
        };
      }, s);
      const onceOk = Object.entries(before).every(([id, y]) => off.years[id] === (y >= 4 ? 4 : y + 1));
      t.check("ดึงไม่ได้ก็ยังเลื่อนชั้นปีจากข้อมูลในเครื่อง (ครั้งเดียว) ให้ใช้งานได้", off.cursor === s.ay && onceOk, JSON.stringify(off.calls));
      t.check("การเลื่อนนั้นถูกจำว่าเป็นการเลื่อนชั่วคราว", off.provisional);
      t.check("ยังไม่ส่งทะเบียนที่เลื่อนจากของเก่าขึ้นคลาวด์เลย", !off.put && !off.calls.some(c => c.startsWith("PUT")), off.calls.join(" → "));
      t.check("สถานะบอกว่ายังรวมกับคลาวด์ไม่ได้ จึงยังไม่ส่ง", /ยังรวมการเลื่อนชั้นปี/.test(off.status), off.status);

      /* คลาวด์กลับมา — รอบส่งถัดไปต้องรวมก่อนแล้วค่อยส่ง */
      const on = await page.evaluate(async ({ targetId }) => {
        localStorage.setItem("__test_getStatus", "200");
        await cloudPush(true);
        const put = JSON.parse(localStorage.getItem("__test_put") || "null");
        const me = store.resident(targetId);
        return {
          calls: JSON.parse(localStorage.getItem("__test_calls") || "[]"),
          advisor: me?.advisor, nick: me?.nick, putAdvisor: put?.residents?.find(x => x.id === targetId)?.advisor,
          years: Object.fromEntries(store.data.residents.map(x => [x.id, x.year])),
          cursor: store.data.meta.yearRolledAY, provisional: !!store.data.meta.provisionalRoll
        };
      }, s);
      t.check("คลาวด์กลับมา: ดึงมารวมก่อน แล้วค่อยส่ง", on.calls.slice(-2).join(" → ") === "GET → PUT@10", on.calls.join(" → "));
      t.eq("การแก้ทะเบียนของเครื่องอื่นหลังเลื่อนชั้นปี ไม่ถูกทะเบียนที่เลื่อนจากของเก่าทับ (ทั้งในเครื่องและที่ส่งขึ้นไป)",
           [on.advisor, on.putAdvisor], ["อ.ที่แก้จากเครื่องอื่นหลังเลื่อนชั้นปี", "อ.ที่แก้จากเครื่องอื่นหลังเลื่อนชั้นปี"]);
      t.eq("สิ่งที่เครื่องนี้แก้ระหว่างออฟไลน์ยังอยู่", on.nick, "แก้ตอนออฟไลน์หลังเลื่อน");
      t.eq("ชั้นปีของทุกคนตรงกับคลาวด์ — ไม่เลื่อนซ้ำ และคนที่เครื่องอื่นให้ซ้ำชั้นยังซ้ำชั้นอยู่", on.years, s.remoteYears);
      t.eq("ตัวชี้ปีเป็นปีปัจจุบัน และเคลียร์การเลื่อนชั่วคราวแล้ว", [on.cursor, on.provisional], [s.ay, false]);
      t.check("ดึงไม่ได้แล้วกลับมา: ไม่มี error หลุดในคอนโซล", errors.filter(e => !/503|Failed to load resource/.test(e)).length === 0, errors.join(" | "));
      await page.close();
    }

    /* ---------- 3b) การเลื่อนชั่วคราว: เปิดเครื่องซ้ำ · คลาวด์ยังไม่เลื่อน · คลาวด์ตอบหน้าเว็บแทนข้อมูล ----------
       สามทางที่ผู้ตรวจรันพิสูจน์ได้ว่าทำให้เลื่อนซ้ำ/ทับข้อมูล — จำลองคลาวด์ในหน้า แล้วเรียก bootReconcile/cloudPush ตรง ๆ
       ให้ครบจังหวะ "วันแรกออฟไลน์ → วันถัดมาเปิดใหม่" โดยไม่ต้องรีโหลด */
    {
      const { page, errors } = await openAs(browser, srv.url, "admin");
      /* (ก) วันแรกออฟไลน์ → วันถัดมาเปิดเครื่องตอนออนไลน์ แล้วจึงส่ง: คนที่คลาวด์เพิ่มหลังเลื่อนต้องยังเป็นปี 1 */
      const a = await page.evaluate(async ({ url }) => {
        const ay = String(currentAY()); const cfg = syncCfg();
        Object.assign(cfg, { mode: "full", auto: true, cloudUrl: url, rev: 5, token: "" });
        store.setRolledAY(+ay - 1);
        writeBaseline(5, JSON.parse(JSON.stringify(fullPayload())));
        store.rollAcademicYear(ay, "auto");
        const remote = JSON.parse(JSON.stringify(fullPayload()));
        remote.residents.push({ ...remote.residents.find(r => r.active !== false && r.year === 2), id: "NEWCLOUD", name: "ใหม่จากคลาวด์", year: 1 });
        store.undoYearRoll();
        window.__cloud = { st: 503, rev: 10, data: remote, puts: [] };
        const real = window.fetch;
        window.fetch = async (u, o = {}) => {
          if (String(u) !== url) return real(u, o);
          const c = window.__cloud;
          if ((o.method || "GET") === "GET") return c.st !== 200 ? new Response("down", { status: c.st })
            : new Response(JSON.stringify({ rev: c.rev, data: c.data }), { status: 200 });
          const bd = JSON.parse(o.body); c.puts.push(bd);
          if (bd.baseRev !== c.rev) return new Response(JSON.stringify({ rev: c.rev, data: c.data }), { status: 409 });
          c.data = bd.data; c.rev++; return new Response(JSON.stringify({ rev: c.rev }), { status: 200 });
        };
        await bootReconcile();
        const p1 = !!store.data.meta.provisionalRoll;
        window.__cloud.st = 200;
        await bootReconcile();
        const p2 = !!store.data.meta.provisionalRoll;
        await cloudPush(true);
        return { p1, p2, local: store.resident("NEWCLOUD")?.year,
                 put: window.__cloud.puts.at(-1)?.data?.residents?.find(x => x.id === "NEWCLOUD")?.year };
      }, { url: CLOUD }).catch(e => ({ err: e.message }));
      t.check("(ก) วันแรกออฟไลน์ตั้งธงเลื่อนชั่วคราว และเปิดเครื่องครั้งถัดไปตอนออนไลน์เคลียร์ธงให้", a.p1 && a.p2 === false, JSON.stringify(a));
      t.eq("(ก) คนที่คลาวด์เพิ่มหลังเลื่อนยังเป็นปี 1 ทั้งในเครื่องและที่ส่งขึ้นไป — ไม่เลื่อนซ้ำ", [a.local, a.put], [1, 1]);
      await page.close();
    }
    {
      const { page } = await openAs(browser, srv.url, "admin");
      /* (ข) คลาวด์ยังไม่เลื่อน (ภาควิชาที่มีผู้จัดหลักสูตรคนเดียว): ระหว่างออฟไลน์ เพิ่มปี 1 รุ่นใหม่ และตั้งให้คนหนึ่งซ้ำชั้น
         พอกลับมาออนไลน์ การเลื่อนที่ตามมาต้องไม่บวกสิ่งที่ผู้ใช้ตั้งไว้แล้วซ้ำอีก */
      const b = await page.evaluate(async ({ url }) => {
        const ay = String(currentAY()); const cfg = syncCfg();
        Object.assign(cfg, { mode: "full", auto: true, cloudUrl: url, rev: 5, token: "" });
        store.setRolledAY(+ay - 1);
        const stale = JSON.parse(JSON.stringify(fullPayload()));
        writeBaseline(5, stale);
        window.__cloud = { st: 503, rev: 5, data: stale, puts: [] };
        const real = window.fetch;
        window.fetch = async (u, o = {}) => {
          if (String(u) !== url) return real(u, o);
          const c = window.__cloud;
          if ((o.method || "GET") === "GET") return c.st !== 200 ? new Response("down", { status: c.st })
            : new Response(JSON.stringify({ rev: c.rev, data: c.data }), { status: 200 });
          const bd = JSON.parse(o.body); c.puts.push(bd);
          if (bd.baseRev !== c.rev) return new Response(JSON.stringify({ rev: c.rev, data: c.data }), { status: 409 });
          c.data = bd.data; c.rev++; return new Response(JSON.stringify({ rev: c.rev }), { status: 200 });
        };
        await bootReconcile();                               /* ออฟไลน์ → เลื่อนชั่วคราว */
        const tmpl = store.data.residents.find(x => x.active !== false && x.year === 2);
        store.data.residents.push({ ...tmpl, id: "NEWLOCAL", name: "R1 ใหม่ของเครื่องนี้", year: 1, cohort: ay });
        const rep = store.data.residents.find(x => x.active !== false && x.year === 3);
        rep.year = 2;                                        /* ให้ซ้ำชั้น */
        window.__cloud.st = 200;
        await cloudPush(true);
        const put = window.__cloud.puts.at(-1)?.data;
        return { local: store.resident("NEWLOCAL")?.year, put: put?.residents?.find(x => x.id === "NEWLOCAL")?.year,
                 rep: store.resident(rep.id)?.year, repPut: put?.residents?.find(x => x.id === rep.id)?.year,
                 cursor: store.data.meta.yearRolledAY, ay, flag: !!store.data.meta.provisionalRoll };
      }, { url: CLOUD }).catch(e => ({ err: e.message }));
      t.eq("(ข) ปี 1 ที่เพิ่มระหว่างออฟไลน์ยังเป็นปี 1 หลังรวมกับคลาวด์", [b.local, b.put], [1, 1]);
      t.eq("(ข) คนที่ตั้งให้ซ้ำชั้นระหว่างออฟไลน์ยังซ้ำชั้น ไม่ถูกบวกอีก", [b.rep, b.repPut], [2, 2]);
      t.eq("(ข) ตัวชี้ปีเป็นปีปัจจุบัน และเคลียร์ธงแล้ว", [b.cursor, b.flag], [b.ay, false]);
      await page.close();
    }
    {
      const { page, errors } = await openAs(browser, srv.url, "admin");
      /* (ค) คลาวด์ตอบหน้าเว็บ (HTML) ด้วยสถานะ 200 — ต้องถือว่าดึงไม่สำเร็จ ไม่ส่ง และคงธงไว้ */
      const c = await page.evaluate(async ({ url }) => {
        const ay = String(currentAY()); const cfg = syncCfg();
        Object.assign(cfg, { mode: "full", auto: true, cloudUrl: url, rev: 5, token: "" });
        store.setRolledAY(+ay - 1);
        const stale = JSON.parse(JSON.stringify(fullPayload()));
        writeBaseline(5, stale);
        store.rollAcademicYear(ay, "auto");
        const remote = JSON.parse(JSON.stringify(fullPayload()));
        const id = remote.residents.find(x => x.active !== false && x.year === 3).id;
        remote.residents.find(x => x.id === id).year = 2;     /* เครื่องอื่นให้ซ้ำชั้นหลังเลื่อน */
        store.undoYearRoll();
        window.__cloud = { st: 503, html: false, rev: 10, data: remote, puts: [] };
        const real = window.fetch;
        window.fetch = async (u, o = {}) => {
          if (String(u) !== url) return real(u, o);
          const cl = window.__cloud;
          if ((o.method || "GET") === "GET") {
            if (cl.st !== 200) return new Response("down", { status: cl.st });
            if (cl.html) { cl.html = false; return new Response("<html>ปิดปรับปรุงระบบ</html>", { status: 200 }); }
            return new Response(JSON.stringify({ rev: cl.rev, data: cl.data }), { status: 200 });
          }
          const bd = JSON.parse(o.body); cl.puts.push(bd);
          if (bd.baseRev !== cl.rev) return new Response(JSON.stringify({ rev: cl.rev, data: cl.data }), { status: 409 });
          cl.data = bd.data; cl.rev++; return new Response(JSON.stringify({ rev: cl.rev }), { status: 200 });
        };
        await bootReconcile();
        window.__cloud.st = 200; window.__cloud.html = true;
        await cloudPush(true);
        const afterHtml = { flag: !!store.data.meta.provisionalRoll, puts: window.__cloud.puts.length, status: syncCfg().lastStatus };
        await cloudPush(true);
        return { afterHtml, local: store.resident(id).year, cloud: window.__cloud.data.residents.find(x => x.id === id).year,
                 flag: !!store.data.meta.provisionalRoll };
      }, { url: CLOUD }).catch(e => ({ err: e.message }));
      t.check("(ค) คลาวด์ตอบหน้าเว็บแทนข้อมูล → ไม่ส่ง คงธงไว้ และบอกในสถานะ",
              c.afterHtml?.flag && c.afterHtml?.puts === 0 && /ไม่ใช่ข้อมูล/.test(c.afterHtml?.status || ""), JSON.stringify(c.afterHtml || c));
      t.eq("(ค) รอบถัดไปที่ได้ข้อมูลจริง: คนที่เครื่องอื่นให้ซ้ำชั้นยังซ้ำชั้น ทั้งในเครื่องและบนคลาวด์", [c.local, c.cloud, c.flag], [2, 2, false]);
      t.check("การเลื่อนชั่วคราวสามทาง: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }

    /* ---------- 3c) การเลื่อนชั่วคราว: ไม่มีฐานเปรียบเทียบ · คลาวด์ส่งข้อมูลผิดรูป ----------
       (ง) ไม่มีฐาน (ล้างข้อมูล/นำเข้าไฟล์) + คลาวด์เลื่อนไปแล้ว — การเลื่อนให้ทันคลาวด์ก่อนรวมต้องคืนสิ่งที่ผู้ใช้แก้ก่อนรวม
       (จ) คลาวด์ตอบเป็น object แต่ข้างในผิดรูป — รวมพัง ต้องนับว่ายังไม่เห็นคลาวด์ (ติดธง) และไม่สลับวัตถุ sync ทิ้ง */
    const mockSrc = `(url) => {
      const real = window.fetch;
      window.fetch = async (u, o = {}) => {
        if (String(u) !== url) return real(u, o);
        const c = window.__cloud;
        if ((o.method || "GET") === "GET") return c.st !== 200 ? new Response("down", { status: c.st })
          : new Response(JSON.stringify({ rev: c.rev, data: c.data }), { status: 200 });
        const bd = JSON.parse(o.body); c.puts.push(bd);
        if (bd.baseRev !== c.rev) return new Response(JSON.stringify({ rev: c.rev, data: c.data }), { status: 409 });
        c.data = bd.data; c.rev++; return new Response(JSON.stringify({ rev: c.rev }), { status: 200 });
      };
    }`;
    {
      const { page, errors } = await openAs(browser, srv.url, "admin");
      const d = await page.evaluate(async ({ url, mockSrc }) => {
        (new Function("return " + mockSrc)())(url);
        const ay = String(currentAY()); const cfg = syncCfg();
        Object.assign(cfg, { mode: "full", auto: true, cloudUrl: url, rev: 5, token: "" });
        store.setRolledAY(+ay - 1);
        store.rollAcademicYear(ay, "auto");
        const remote = JSON.parse(JSON.stringify(fullPayload()));
        store.undoYearRoll();
        localStorage.removeItem(BASELINE_KEY);              /* ไม่มีฐานเปรียบเทียบ */
        window.__cloud = { st: 503, rev: 10, data: remote, puts: [] };
        await bootReconcile();                               /* ออฟไลน์ → เลื่อนชั่วคราว */
        const tmpl = store.data.residents.find(x => x.active !== false && x.year === 2);
        store.data.residents.push({ ...tmpl, id: "NEWLOCAL", name: "R1 ใหม่ของเครื่องนี้", year: 1, cohort: ay });
        const rep = store.data.residents.find(x => x.active !== false && x.year === 3);
        rep.year = 2;
        window.__cloud.st = 200;
        await cloudPush(true);
        const put = window.__cloud.puts.at(-1)?.data;
        return { local: store.resident("NEWLOCAL")?.year, put: put?.residents?.find(x => x.id === "NEWLOCAL")?.year,
                 rep: store.resident(rep.id)?.year, repPut: put?.residents?.find(x => x.id === rep.id)?.year,
                 flag: !!store.data.meta.provisionalRoll };
      }, { url: CLOUD, mockSrc }).catch(e => ({ err: e.message }));
      t.eq("(ง) ไม่มีฐาน: ปี 1 ที่เพิ่มระหว่างออฟไลน์ยังเป็นปี 1 ทั้งในเครื่องและที่ส่งขึ้นไป", [d.local, d.put], [1, 1]);
      t.eq("(ง) ไม่มีฐาน: คนที่ตั้งให้ซ้ำชั้นยังซ้ำชั้น และเคลียร์ธงแล้ว", [d.rep, d.repPut, d.flag], [2, 2, false]);
      t.check("(ง) ไม่มีฐาน: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }
    {
      const { page, errors } = await openAs(browser, srv.url, "admin");
      const e = await page.evaluate(async ({ url, mockSrc }) => {
        (new Function("return " + mockSrc)())(url);
        const ay = String(currentAY()); const cfg0 = syncCfg();
        Object.assign(cfg0, { mode: "full", auto: true, cloudUrl: url, rev: 5, token: "", pending: false, lastStatus: "เดิม" });
        store.setRolledAY(+ay - 1);
        writeBaseline(5, JSON.parse(JSON.stringify(fullPayload())));
        window.__cloud = { st: 200, rev: 10, data: { residents: { ผิดรูป: 1 } }, puts: [] };
        await bootReconcile();
        const cfg1 = syncCfg();
        return { sameObj: cfg0 === cfg1, status: cfg1.lastStatus, flag: !!store.data.meta.provisionalRoll,
                 cursor: store.data.meta.yearRolledAY, ay };
      }, { url: CLOUD, mockSrc }).catch(err => ({ err: err.message }));
      t.check("(จ) คลาวด์ผิดรูป: เลื่อนจากในเครื่องแล้วติดธงเลื่อนชั่วคราว (ไม่ส่งทะเบียนนั้นตรง ๆ)", e.flag && e.cursor === e.ay, JSON.stringify(e));
      t.check("(จ) คลาวด์ผิดรูป: ยังใช้วัตถุ sync ตัวเดิม และสถานะบอกสาเหตุ", e.sameObj && /ดึงข้อมูลจากคลาวด์ก่อนเลื่อนชั้นปีไม่สำเร็จ/.test(e.status || ""), e.status);
      t.check("(จ) คลาวด์ผิดรูป: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }

    /* ---------- 3d) คลาวด์ตามหลังเกินหนึ่งปี · ฐานเปรียบเทียบต้องเคารพระดับข้อมูลผู้ป่วย ----------
       (ฉ) เครื่องนี้ค้างที่ปี ay-2 คลาวด์อยู่ ay-1 ไม่มีฐาน — เลื่อนให้ทันคลาวด์หนึ่งรอบแล้วเลื่อนต่ออีกรอบถึงปีปัจจุบัน
           เดิมคืนสิ่งที่ผู้ใช้แก้แล้วทิ้งไปตั้งแต่รอบแรก รอบที่สองจึงบวกปีให้ R1 ใหม่เป็นปี 2 และเลื่อนคนซ้ำชั้นไปปี 3
       (ช) เครื่องที่ตั้งไม่เก็บ HN/ข้อมูลผู้ป่วย เดิมเขียนชุดของคลาวด์ลงฐานเปรียบเทียบตรง ๆ HN อายุ เพศ จึงค้างอยู่ใน localStorage */
    {
      const { page, errors } = await openAs(browser, srv.url, "admin");
      const d = await page.evaluate(async ({ url, mockSrc }) => {
        (new Function("return " + mockSrc)())(url);
        const ay = +currentAY(); const cfg = syncCfg();
        Object.assign(cfg, { mode: "full", auto: true, cloudUrl: url, rev: 5, token: "" });
        store.setRolledAY(ay - 2);
        store.rollAcademicYear(String(ay - 1), "auto");      /* คลาวด์เลื่อนไปแค่ปีก่อน */
        const remote = JSON.parse(JSON.stringify(fullPayload()));
        store.undoYearRoll();
        localStorage.removeItem(BASELINE_KEY);
        window.__cloud = { st: 503, rev: 10, data: remote, puts: [] };
        await bootReconcile();                               /* ออฟไลน์ → เลื่อนชั่วคราวสองปี */
        const tmpl = store.data.residents.find(x => x.active !== false && x.year === 2);
        store.data.residents.push({ ...tmpl, id: "NEWLOCAL", name: "R1 ใหม่ของเครื่องนี้", year: 1, cohort: String(ay) });
        const rep = store.data.residents.find(x => x.active !== false && x.year === 3);
        rep.year = 2;
        window.__cloud.st = 200;
        await cloudPush(true);
        const put = window.__cloud.puts.at(-1)?.data;
        return { cloudAY: remote.programme?.yearRolledAY, ay: String(ay),
                 local: store.resident("NEWLOCAL")?.year, put: put?.residents?.find(x => x.id === "NEWLOCAL")?.year,
                 rep: store.resident(rep.id)?.year, repPut: put?.residents?.find(x => x.id === rep.id)?.year,
                 flag: !!store.data.meta.provisionalRoll, cursor: store.data.meta.yearRolledAY };
      }, { url: CLOUD, mockSrc }).catch(e => ({ err: e.message }));
      t.check("(ฉ) ตั้งต้น: คลาวด์ตามหลังปีปัจจุบันหนึ่งปี และสุดท้ายเลื่อนถึงปีปัจจุบัน",
        d.cloudAY === String(+d.ay - 1) && d.cursor === d.ay && d.flag === false, JSON.stringify(d));
      t.eq("(ฉ) คลาวด์ตามหลังเกินปี: R1 ที่เพิ่มระหว่างออฟไลน์ยังเป็นปี 1 ทั้งในเครื่องและที่ส่งขึ้นไป", [d.local, d.put], [1, 1]);
      t.eq("(ฉ) คลาวด์ตามหลังเกินปี: คนที่ตั้งให้ซ้ำชั้นยังซ้ำชั้น ทั้งในเครื่องและที่ส่งขึ้นไป", [d.rep, d.repPut], [2, 2]);
      t.check("(ฉ) ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }
    {
      const { page, errors } = await openAs(browser, srv.url, "admin");
      const h = await page.evaluate(() => {
        const leaks = () => Object.keys(localStorage).filter(k => /HNLEAK/.test(localStorage.getItem(k) || ""));
        /* ใช้เคสที่มีอยู่แล้วทั้งสองฝั่ง — เคสที่มีแต่บนคลาวด์ถูกรวมเข้ามาเป็นวัตถุตัวเดียวกับในชุดของคลาวด์ การลบตามระดับในเครื่อง
           จึงลบในชุดนั้นไปด้วยโดยบังเอิญ ไม่ได้ทดสอบการเขียนฐานจริง */
        const leakId = store.data.cases[0].id;
        const remoteWith = () => {
          const r = JSON.parse(JSON.stringify(fullPayload()));
          r.cases.forEach((c, i) => Object.assign(c, { hn: "HNLEAK" + i, age: 61, sex: "F" }));
          return r;
        };
        /* ระดับ minimal: รวมกับคลาวด์แล้วฐานต้องไม่มี HN อายุ เพศ */
        store.data.orQueue ||= {}; store.data.orQueue.patientData = "minimal"; applyPatientLevel(); store.save();
        syncCfg().rev = 5;
        reconcileWithCloud({ rev: 9, data: remoteWith() }); store.save();
        const b1 = readBaseline()?.data?.cases?.find(c => c.id === leakId);
        const afterMerge = { keys: leaks(), base: b1 && [b1.hn, b1.age, b1.sex], local: store.data.cases.find(c => c.id === leakId)?.hn };
        /* ระดับ full → เขียนฐานพร้อม HN → เปลี่ยนเป็น nohn ผ่านหน้าตั้งค่า ฐานเดิมต้องถูกเขียนใหม่ */
        store.data.orQueue.patientData = "full";
        writeBaseline(9, remoteWith());
        const before = leaks().length > 0;
        caseSettingsDialog();
        document.querySelector('#dlgBody [name="patientData"]').value = "nohn";
        [...document.querySelectorAll("#dlgFoot button")].find(b => b.textContent === "บันทึก").click();
        const b2 = readBaseline();
        const c2 = b2?.data?.cases?.find(c => c.id === leakId);
        return { afterMerge, before, afterLevel: leaks(), rev: b2?.rev, kept: c2 && [c2.hn, c2.age, c2.sex] };
      }).catch(e => ({ err: e.message }));
      t.check("(ช) ระดับไม่เก็บข้อมูลผู้ป่วย: รวมกับคลาวด์แล้วไม่มี HN ค้างในคีย์ใดของ localStorage",
        h.afterMerge?.keys?.length === 0 && h.afterMerge.local === "", JSON.stringify(h.afterMerge));
      t.eq("(ช) ฐานเปรียบเทียบของเคสจากคลาวด์ถูกลบ HN อายุ เพศ ตามระดับ", h.afterMerge?.base, ["", "", ""]);
      t.check("(ช) เปลี่ยนระดับเป็นไม่เก็บ HN: ฐานที่มี HN อยู่ก่อนถูกเขียนใหม่ (รุ่นเดิม) ไม่เหลือ HN แต่ยังเก็บอายุ/เพศ",
        h.before && h.afterLevel?.length === 0 && h.rev === 9 && JSON.stringify(h.kept) === JSON.stringify(["", 61, "F"]), JSON.stringify(h));
      t.check("(ช) ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }
    /* (ซ) เครื่องไม่เก็บ HN รวมกับคลาวด์ที่ยังมี HN: ต้องเทียบเคสในมุมของระดับเครื่องนี้
           เดิมเคสที่เครื่องนี้ลบถูกนับว่า "เครื่องอื่นแก้" แล้วคืนกลับมา และเคสที่แก้ถูกนับว่าชนกันทั้งที่ไม่มีใครแก้อีกฝั่ง
       (ฌ) ฐานเก่าที่ยังมี HN (เขียนโดยโค้ดรุ่นก่อน) ต้องถูกลบตอนเปิดแอป และไม่ทำให้ทุกเคสดูเหมือนเครื่องนี้แก้
           จนทับสิ่งที่เครื่องอื่นแก้ */
    {
      const { page, errors } = await openAs(browser, srv.url, "admin");
      const z = await page.evaluate(() => {
        const withHn = () => {
          const r = JSON.parse(JSON.stringify(fullPayload()));
          r.cases.forEach((c, i) => Object.assign(c, { hn: "HNZZ" + i }));
          return r;
        };
        store.data.orQueue ||= {}; store.data.orQueue.patientData = "nohn"; applyPatientLevel(); store.save();
        const cloud = withHn();                                   /* ข้อมูลเดิมบนคลาวด์ (เครื่องเดสก์ท็อปที่เก็บ HN) */
        syncCfg().rev = 5;
        reconcileWithCloud({ rev: 9, data: cloud });              /* ฐานถูกเขียนแบบไม่มี HN */
        const [del, edit] = store.data.cases;
        store.data.cases = store.data.cases.filter(c => c.id !== del.id);
        store.data.cases.find(c => c.id === edit.id).note = "แก้จากโทรศัพท์";
        store.data.syncConflicts = [];
        reconcileWithCloud({ rev: 10, data: JSON.parse(JSON.stringify(cloud)) });  /* rev ขยับจากเรื่องอื่น ข้อมูลเคสเหมือนเดิม */
        const cf = (store.data.syncConflicts || []).filter(c => c.key === "cases");
        return { delBack: store.data.cases.some(c => c.id === del.id), note: store.data.cases.find(c => c.id === edit.id)?.note,
                 conflicts: cf.map(c => c.id + ":" + c.note) };
      }).catch(e => ({ err: e.message }));
      t.check("(ซ) ไม่เก็บ HN: เคสที่ลบในเครื่องนี้ไม่ถูกคืนกลับมาหลังรวมกับคลาวด์ที่ยังมี HN", z.delBack === false, JSON.stringify(z));
      t.check("(ซ) ไม่เก็บ HN: เคสที่แก้คงค่าที่แก้ และไม่มีรายการชนกันของเคส", z.note === "แก้จากโทรศัพท์" && z.conflicts?.length === 0, JSON.stringify(z));
      t.check("(ซ) ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }
    {
      const { page, errors } = await openAs(browser, srv.url, "admin");
      const prep = await page.evaluate(() => {
        store.data.orQueue ||= {}; store.data.orQueue.patientData = "nohn"; applyPatientLevel(); store.save();
        /* ฐานแบบโค้ดรุ่นก่อน: ชุดของคลาวด์ดิบที่มี HN ครบ เขียนตรง ๆ ไม่ผ่าน writeBaseline */
        const raw = JSON.parse(JSON.stringify(fullPayload()));
        raw.cases.forEach((c, i) => Object.assign(c, { hn: "HNOLD" + i }));
        localStorage.setItem(BASELINE_KEY, JSON.stringify({ rev: 9, at: "2026-01-01", data: raw }));
        syncCfg().rev = 9; store.save();
        return { id: raw.cases[1].id };
      });
      await page.reload(); await page.waitForFunction(() => typeof store !== "undefined" && store.data);
      const q = await page.evaluate(({ id }) => {
        const hasHn = /HNOLD/.test(localStorage.getItem(BASELINE_KEY) || "");
        /* เครื่องอื่นแก้เคสหนึ่ง (คลาวด์ยังมี HN) — เครื่องนี้ไม่ได้แก้อะไร ต้องได้ของเครื่องอื่น ไม่ชนกัน */
        const cloud = JSON.parse(JSON.stringify(fullPayload()));
        cloud.cases.forEach((c, i) => Object.assign(c, { hn: "HNOLD" + i }));
        cloud.cases.find(c => c.id === id).note = "แก้จากเครื่องอื่น";
        store.data.syncConflicts = [];
        reconcileWithCloud({ rev: 10, data: cloud });
        return { hasHn, note: store.data.cases.find(c => c.id === id)?.note,
                 conflicts: (store.data.syncConflicts || []).filter(c => c.key === "cases").length };
      }, prep).catch(e => ({ err: e.message }));
      t.check("(ฌ) เปิดแอปใหม่: ฐานเก่าที่มี HN ถูกลบ HN ตามระดับของเครื่อง", q.hasHn === false, JSON.stringify(q));
      t.check("(ฌ) ฐานเก่า: สิ่งที่เครื่องอื่นแก้ในเคสเข้ามาได้ ไม่ถูกฉบับเก่าในเครื่องทับ และไม่มีรายการชนกัน",
        q.note === "แก้จากเครื่องอื่น" && q.conflicts === 0, JSON.stringify(q));
      t.check("(ฌ) ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }
    /* (ญ) เครื่องที่ไม่เก็บ HN ส่งขึ้นคลาวด์: คลาวด์ต้องเก็บ HN (และอายุ/เพศ ในระดับ minimal) ไว้ตามเดิม
           เดิมคลาวด์เขียนทับทั้งชุดตามที่ส่ง เคสทุกเคสที่ช่องเหล่านี้ว่างในเครื่องจึงทำให้ HN บนคลาวด์หายหมด
           ดึงคลาวด์ไม่ได้ต้องไม่ส่ง · ทางชนกัน (409) แล้วส่งใหม่ก็ต้องเก็บไว้เหมือนกัน · ในเครื่องต้องไม่มี HN ค้าง */
    for (const lv of ["nohn", "minimal"]) {
      const { page, errors } = await openAs(browser, srv.url, "admin");
      const p = await page.evaluate(async ({ url, mockSrc, lv }) => {
        (new Function("return " + mockSrc)())(url);
        store.data.orQueue ||= {}; store.data.orQueue.patientData = lv; applyPatientLevel(); store.save();
        const cloud = JSON.parse(JSON.stringify(fullPayload()));
        cloud.cases.forEach((c, i) => Object.assign(c, { hn: "HNKEEP" + i, age: 40 + (i % 30), sex: i % 2 ? "M" : "F" }));
        const cfg = syncCfg();
        Object.assign(cfg, { mode: "full", auto: false, cloudUrl: url, rev: 10, token: "" });
        writeBaseline(10, cloud);
        window.__cloud = { st: 200, rev: 10, data: cloud, puts: [] };
        const edited = store.data.cases[0].id;
        store.data.cases[0].note = "แก้จากเครื่องที่ไม่เก็บ HN";
        const count = (d) => (d?.cases || []).filter(c => /^HNKEEP/.test(c.hn)).length;
        const ages = (d) => (d?.cases || []).filter(c => c.age !== "" && c.age != null).length;
        /* 1) ดึงคลาวด์ไม่ได้ → ไม่ส่ง */
        window.__cloud.st = 503;
        await cloudPush(true);
        const blocked = { puts: window.__cloud.puts.length, pending: cfg.pending, status: cfg.lastStatus };
        /* 2) ส่งปกติ */
        window.__cloud.st = 200;
        await cloudPush(true);
        const put1 = window.__cloud.puts.at(-1)?.data;
        const r1 = { hn: count(put1), ages: ages(put1), n: put1?.cases?.length,
                     note: put1?.cases?.find(c => c.id === edited)?.note, editedHn: put1?.cases?.find(c => c.id === edited)?.hn };
        /* 3) เครื่องอื่นส่งขึ้นก่อน (rev ขยับ) → 409 → รวม → ส่งใหม่ */
        window.__cloud.rev += 1;
        store.data.cases[1].note = "แก้อีกเคส";
        await cloudPush(true);
        const put2 = window.__cloud.puts.at(-1)?.data;
        const r2 = { hn: count(put2), ages: ages(put2), n: put2?.cases?.length, puts: window.__cloud.puts.length };
        const leak = Object.keys(localStorage).filter(k => k !== "__cloud" && /HNKEEP/.test(localStorage.getItem(k) || ""));
        return { blocked, r1, r2, leak, localHn: store.data.cases.filter(c => c.hn).length,
                 localAge: store.data.cases.filter(c => c.age !== "" && c.age != null).length, total: cloud.cases.length };
      }, { url: CLOUD, mockSrc, lv }).catch(e => ({ err: e.message }));
      t.check(`(ญ ${lv}) ดึงคลาวด์ไม่ได้: ไม่ส่ง คงสถานะรอส่ง และบอกเหตุผล`,
        p.blocked?.puts === 0 && p.blocked.pending === true && /ยังไม่ส่ง เพื่อไม่ให้ HN บนคลาวด์หาย/.test(p.blocked.status || ""), JSON.stringify(p.blocked));
      t.check(`(ญ ${lv}) ส่งขึ้นแล้ว HN ของทุกเคสบนคลาวด์ยังอยู่ (รวมเคสที่เครื่องนี้แก้) และค่าที่แก้ขึ้นไปด้วย`,
        p.r1?.hn === p.total && p.r1.n === p.total && p.r1.note === "แก้จากเครื่องที่ไม่เก็บ HN" && /^HNKEEP/.test(p.r1.editedHn || ""), JSON.stringify(p.r1));
      t.eq(`(ญ ${lv}) อายุของทุกเคสบนคลาวด์ยังอยู่`, p.r1?.ages, p.total);
      t.check(`(ญ ${lv}) ชนกัน (409) แล้วส่งใหม่: HN และอายุบนคลาวด์ยังอยู่ครบ`,
        p.r2?.hn === p.total && p.r2.ages === p.total && p.r2.puts === 3, JSON.stringify(p.r2));
      t.check(`(ญ ${lv}) ในเครื่องไม่มี HN ค้างทั้งในเคสและใน localStorage`,
        p.localHn === 0 && p.leak?.length === 0 && (lv === "nohn" || p.localAge === 0), JSON.stringify({ leak: p.leak, localHn: p.localHn, localAge: p.localAge }));
      t.check(`(ญ ${lv}) ไม่มี error หลุดในคอนโซล`, errors.length === 0, errors.join(" | "));
      await page.close();
    }

    /* ---------- 4) เลื่อนชั้นปีแล้วย้อนกลับ ต้องได้ทะเบียนตรงตามเดิมทุกไบต์ ----------
       เดิมย้อนกลับแล้วเติม graduatedAY:"" ให้ทุกคน (ข้อมูลสาธิตไม่มีช่องนี้) ทะเบียนทั้งชุดจึงต่างจากฐานเปรียบเทียบ
       พอซิงก์ก็ถูกนับว่า "เครื่องนี้แก้ทุกคน" แล้วชนะการรวมข้อมูลทับสิ่งที่เครื่องอื่นแก้ — ต้องรันบนข้อมูลสดที่ยังไม่เคยถูกเลื่อน */
    {
      const { page, errors } = await openAs(browser, srv.url, "admin");
      const r = await page.evaluate(() => {
        const snap = JSON.stringify(store.data.residents), users = JSON.stringify(store.data.users);
        const hadGradKey = store.data.residents.some(x => "graduatedAY" in x);
        store.setRolledAY(+currentAY() - 1);
        store.rollAcademicYear(String(currentAY()), "manual");
        const changed = JSON.stringify(store.data.residents) !== snap;
        store.undoYearRoll();
        return { hadGradKey, changed, same: JSON.stringify(store.data.residents) === snap,
                 usersSame: JSON.stringify(store.data.users) === users };
      });
      t.check("ตั้งต้น: ข้อมูลสดยังไม่มีช่อง graduatedAY และการเลื่อนเปลี่ยนทะเบียนจริง", !r.hadGradKey && r.changed, JSON.stringify(r));
      t.check("เลื่อนแล้วย้อนกลับ ทะเบียนและบัญชีกลับมาตรงตามเดิมทุกไบต์ (ไม่เติมช่องที่ไม่เคยมี)", r.same && r.usersSame, JSON.stringify(r));
      t.check("ย้อนกลับตรงทุกไบต์: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }
  } finally {
    await browser.close();
    await srv.close();
  }
  return t;
}
