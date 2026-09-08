/* วงจรชั้นปีของแพทย์ประจำบ้าน — ทุก 1 ก.ค. เลื่อนชั้นปี +1 · ปี 4 จบ → inactive พร้อมป้ายรุ่น
   รุ่น = ปีการศึกษาที่เข้า − 2541 (ปี 4 ของปีการศึกษา 2569 เข้า 2566 = รุ่น 25)
   คนที่จบแล้วต้องหายจากหน้าปฏิบัติงาน (ตาราง ตัวเลือกคน checklist) แต่ยังเปิดแฟ้มได้ และย้อนกลับการเลื่อนได้ */
import { chromium } from "playwright";
import { serve, launchOptions, openAs, suite } from "./lib.mjs";

export default async function run() {
  const t = suite("วงจรชั้นปี · รุ่น · จบการศึกษา");
  const srv = await serve();
  const browser = await chromium.launch(launchOptions());
  try {
    const { page, errors } = await openAs(browser, srv.url, "admin");

    /* ---------- รุ่นคำนวณจากปีที่เข้า · ข้อมูลสาธิตตั้งธงปี 2569 และไม่เลื่อนถ้ายังปีเดียวกัน ---------- */
    const base = await page.evaluate(() => {
      const r4 = store.data.residents.find(r => r.year === 4), r1 = store.data.residents.find(r => r.year === 1);
      return { b4: batchOf(r4), b1: batchOf(r1), c4: r4.cohort, flag: store.data.meta.yearRolledAY, ay: String(currentAY()),
               allActive: store.data.residents.every(r => r.active === true), label: batchLabel(r4) };
    });
    t.eq("ปี 4 ของปีการศึกษา 2569 (เข้า 2566) = รุ่น 25 · ปี 1 (เข้า 2569) = รุ่น 28", [base.b4, base.b1, base.c4, base.label], [25, 28, "2566", "รุ่น 25"]);
    t.check("ข้อมูลสาธิตตั้งธงทะเบียนชั้นปีไว้ที่ปี 2569 และทุกคน active", base.flag === "2569" && base.allActive, JSON.stringify(base));
    t.check("ปีการศึกษาปัจจุบันยังเป็นปีเดียวกับธง จึงยังไม่เลื่อน (ชั้นปีตรงข้อมูลสาธิต)",
            +base.flag >= +base.ay || base.ay === "2569", base.flag + " vs " + base.ay);

    /* ---------- จำลองว่าทะเบียนเป็นของปีก่อน แล้วโหลดใหม่ → เลื่อนชั้นปีให้เองผ่าน migrate ---------- */
    const roll = await page.evaluate(() => {
      const snap = store.data.residents.map(r => ({ id: r.id, year: r.year, name: r.name }));
      const y4 = snap.filter(x => x.year === 4).map(x => x.id);
      const ay = String(currentAY());
      store.data.meta.yearRolledAY = String(+ay - 1);
      store.save(); store.load();                /* migrate() → rollAcademicYearOnce() */
      const d = store.data;
      const promotedOk = snap.filter(x => x.year < 4).every(x => d.residents.find(r => r.id === x.id).year === x.year + 1);
      const grads = y4.map(id => d.residents.find(r => r.id === id));
      const gradOk = grads.every(r => r.active === false && r.graduatedAY === String(+ay - 1) && /\(รุ่น 25\)$/.test(r.name) && r.year === 4);
      const userOk = grads.every(r => { const u = d.users.find(u => u.residentId === r.id); return !u || u.displayName === r.name; });
      const lr = d.meta.lastYearRoll;
      return { promotedOk, gradOk, userOk, nGrad: grads.length, flag: d.meta.yearRolledAY, ay,
               lrOk: !!lr && lr.fromAY === String(+ay - 1) && lr.toAY === ay && lr.before.length === snap.length && lr.how === "auto",
               notice: store.pendingNotice || "", auditOk: d.audit.some(a => /เลื่อนชั้นปี/.test(a.action)),
               activeCount: activeResidents().length, total: d.residents.length };
    });
    t.check("โหลดใหม่ข้ามปีการศึกษา → ทุกคนปี 1–3 เลื่อน +1", roll.promotedOk);
    t.check("ปี 4 จบการศึกษา: active=false · graduatedAY = ปีที่เรียนจบ · ชื่อต่อท้าย (รุ่น 25) · ชั้นปีค้างที่ 4",
            roll.gradOk && roll.nGrad === 5, JSON.stringify({ n: roll.nGrad, gradOk: roll.gradOk }));
    t.check("บัญชีผู้ใช้ที่ผูกไว้ได้ชื่อใหม่ตาม", roll.userOk);
    t.check("ธงเลื่อนเป็นปีปัจจุบัน · เก็บชุดก่อนเลื่อนไว้ (lastYearRoll) · ลง audit · มีข้อความแจ้ง",
            roll.flag === roll.ay && roll.lrOk && roll.auditOk && /จบการศึกษา 5 คน/.test(roll.notice), roll.notice);
    t.eq("activeResidents() เหลือเฉพาะคนที่ยังฝึกอบรม", [roll.activeCount, roll.total], [15, 20]);

    /* ---------- คนที่จบแล้วหายจากหน้าปฏิบัติงาน แต่ยังเปิดแฟ้มได้ ---------- */
    const vis = await page.evaluate(() => {
      const gone = store.data.residents.filter(r => r.active === false);
      showView("rotation"); renderMonthGrid();
      const gridNames = [...document.querySelectorAll("#monthGrid th.who")].map(th => th.textContent);
      const inGrid = gone.some(r => gridNames.some(n => n.includes(r.name)));
      editTalk(null, { type:"topic", date: todayISO() });
      const opts = [...document.querySelectorAll('#dlgBody [name="residentId"] option')].map(o => o.value);
      const inTalk = gone.some(r => opts.includes(r.id));
      document.querySelector("#dlg").close();
      showView("residents"); renderResidents();
      const details = document.querySelector("#residentList details");
      const detailsText = details?.querySelector("summary")?.textContent || "";
      const rowsActive = [...document.querySelectorAll("#residentList > .tbl-wrap:first-child tbody tr")].length;
      showView("settings"); renderYearChecklist(); renderYearRollPanel();   /* showView ไม่วาดใหม่ */
      const cl = document.querySelector("#yearChecklist")?.textContent || "";
      const panel = document.querySelector("#yearRollPanel")?.textContent || "";
      /* เปิดแฟ้มของคนที่จบแล้วยังได้ */
      openResident(gone[0].id);
      const detailHead = document.querySelector("#residentDetail h2")?.textContent || "";
      return { inGrid, inTalk, detailsText, rowsActive, cl, panelHasUndo: !!document.querySelector("#btnUndoRoll"),
               panel, detailHead };
    });
    t.check("ตารางหมุนเวียนรายเดือนไม่มีคนที่จบแล้ว", !vis.inGrid);
    t.check("ตัวเลือกผู้นำเสนอในกล่องลงตารางไม่มีคนที่จบแล้ว", !vis.inTalk);
    t.check("หน้ารายชื่อ: ตารางหลัก 15 คน · ส่วน 'จบการศึกษาแล้ว' 5 คน พับไว้",
            vis.rowsActive === 15 && /จบการศึกษาแล้ว.*5 คน/.test(vis.detailsText), vis.rowsActive + " · " + vis.detailsText);
    t.check("checklist เตรียมปีนับเฉพาะคนที่ฝึกอบรมอยู่ (15 คน)", /15 คนที่ฝึกอบรมอยู่/.test(vis.cl), vis.cl.slice(0, 120));
    t.check("หน้าตั้งค่ามีแผงวงจรชั้นปี บอกรุ่นและมีปุ่มย้อนกลับ", vis.panelHasUndo && /รุ่น 25/.test(vis.panel));
    t.check("แฟ้มของคนที่จบแล้วยังเปิดได้ และหัวแฟ้มบอกว่าจบแล้ว", /จบการศึกษาแล้ว/.test(vis.detailHead), vis.detailHead);

    /* ---------- ย้อนกลับ → ทุกอย่างกลับเป็นชุดก่อนเลื่อน ---------- */
    const undo = await page.evaluate(() => {
      const before = store.data.meta.lastYearRoll.before;
      const ok = store.undoYearRoll();
      const restored = before.every(b => { const r = store.data.residents.find(x => x.id === b.id);
        return r.year === b.year && (r.active !== false) === b.active && r.name === b.name && (r.graduatedAY || "") === b.graduatedAY; });
      return { ok, restored, flag: store.data.meta.yearRolledAY, ay: String(currentAY()), lrGone: !store.data.meta.lastYearRoll,
               allActive: store.data.residents.every(r => r.active !== false), noSuffix: !store.data.residents.some(r => /\(รุ่น/.test(r.name)) };
    });
    t.check("ย้อนกลับแล้ว ชั้นปี/สถานะ/ชื่อ กลับเป็นชุดก่อนเลื่อนครบทุกคน และธงกลับเป็นปีก่อน",
            undo.ok && undo.restored && undo.allActive && undo.noSuffix && undo.lrGone && undo.flag === String(+undo.ay - 1),
            JSON.stringify(undo));

    /* ---------- เลื่อนเอง (ปุ่มผู้จัดหลักสูตร) ทำงานเหมือนกัน และไม่เลื่อนซ้ำเมื่อโหลดใหม่ ---------- */
    const manual = await page.evaluate(() => {
      store.data.meta.yearRolledAY = String(currentAY());
      const to = String(+currentAY() + 1);
      const out = store.rollAcademicYear(to, "manual");
      store.save(); store.load();           /* ธงนำหน้าปีจริง → migrate ต้องไม่เลื่อนซ้ำ */
      const y1 = store.data.residents.filter(r => r.active !== false && r.year === 1).length;
      const flag = store.data.meta.yearRolledAY;
      store.undoYearRoll(); store.save();
      return { promoted: out?.promoted, grads: out?.graduated.length, flag, to, y1 };
    });
    t.check("เลื่อนเองล่วงหน้า: เลื่อน 15 จบ 5 · ธงนำหน้าปีจริง 1 ปี และโหลดใหม่ไม่เลื่อนซ้ำ (ไม่มีปี 1 เหลือ = เลื่อนรอบเดียว)",
            manual.promoted === 15 && manual.grads === 5 && manual.flag === manual.to && manual.y1 === 0, JSON.stringify(manual));

    /* ---------- เครื่องเก่าที่ไม่มีธง: ถือว่าเป็นปัจจุบัน ไม่เลื่อน ---------- */
    const legacy = await page.evaluate(() => {
      const years = store.data.residents.map(r => r.year).join(",");
      delete store.data.meta.yearRolledAY;
      store.save(); store.load();
      return { same: store.data.residents.map(r => r.year).join(",") === years, flag: store.data.meta.yearRolledAY, ay: String(currentAY()) };
    });
    t.check("ข้อมูลเก่าที่ยังไม่มีธง: ตั้งธงเป็นปีปัจจุบันโดยไม่เลื่อนชั้นปี", legacy.same && legacy.flag === legacy.ay, JSON.stringify(legacy));

    t.check("วงจรชั้นปี: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
    await page.close();
  } finally {
    await browser.close();
    await srv.close();
  }
  return t;
}
