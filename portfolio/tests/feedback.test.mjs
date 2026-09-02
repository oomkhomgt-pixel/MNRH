/* feedback และหน้าตั้งค่า — error ต้องอยู่ที่ช่อง (ไม่ใช่ toast ที่หายใน 2.6 วิ), การลบต้องเลิกทำได้,
   ไม่มี window.confirm (popup ของเบราว์เซอร์) เหลืออยู่ที่ไหนเลย, หน้าตั้งค่ามีดัชนี + checklist เตรียมปี,
   เพิ่มแพทย์ประจำบ้านแล้วได้บัญชีผูกให้ทันที, และวันที่แสดงแบบเดียวกันทั้งแอป */
import { chromium } from "playwright";
import { serve, launchOptions, openAs, suite } from "./lib.mjs";

export default async function run() {
  const t = suite("feedback · เลิกทำ · หน้าตั้งค่า · วันที่");
  const srv = await serve();
  const browser = await chromium.launch(launchOptions());
  try {
    const { page, errors } = await openAs(browser, srv.url, "admin");
    /* ถ้ามีจุดไหนยังเรียก window.confirm อยู่ จะ throw แล้วโผล่ใน errors ตอนท้าย */
    await page.evaluate(() => { window.confirm = () => { throw new Error("native confirm() ยังถูกเรียกอยู่"); }; });

    /* ---------- error ที่ช่อง ---------- */
    const fe = await page.evaluate(() => {
      manualAdd();
      const toastsBefore = document.querySelectorAll("#toasts .toast").length;
      document.querySelector("#dlgFoot .btn-primary").click();
      const inp = document.querySelector('#dlgBody [name="title"]');
      const r = { open: document.querySelector("#dlg").open, invalid: inp.getAttribute("aria-invalid"),
                  err: inp.parentElement.querySelector(".err")?.textContent || "", focused: document.activeElement === inp,
                  toastAdded: document.querySelectorAll("#toasts .toast").length > toastsBefore };
      inp.value = "พิมพ์แล้ว"; inp.dispatchEvent(new Event("input", { bubbles: true }));
      r.cleared = !inp.classList.contains("invalid") && !inp.parentElement.querySelector(".err");
      document.querySelector("#dlg").close();
      return r;
    });
    t.check("บันทึกโดยไม่ใส่ชื่อเรื่อง: กล่องยังเปิด ช่องถูกทำเครื่องหมาย aria-invalid และมีข้อความใต้ช่อง",
            fe.open && fe.invalid === "true" && fe.err.length > 0, fe.err);
    t.check("focus ย้ายไปช่องที่ผิด และไม่มี toast", fe.focused && !fe.toastAdded);
    t.check("พิมพ์แล้ว error หายเอง", fe.cleared);

    /* ---------- แบบประเมินลงกอง: ทำเครื่องหมายทุกข้อที่ขาด ไม่ใช่แค่ 3 ข้อแรก ---------- */
    const rf = await page.evaluate(() => {
      const rot = store.data.rotations.find(r => !rotationEvalFor(r.id) && serviceById(r.serviceId)?.team);
      if (!rot) return null;
      /* บังคับ 5 ข้อ (เกินสามข้อที่ toast เดิมเคยโชว์) แล้วบันทึกทั้งที่ยังว่าง */
      const asked = rotationAskItems().filter(it => it.kind !== "section").slice(0, 5);
      const was = asked.map(it => it.required);
      asked.forEach(it => { it.required = true; });
      openRotationEval(rot.id);
      const required = rotationAskItems().filter(it => it.required).length;
      document.querySelector("#dlgFoot .btn-primary").click();
      const marked = document.querySelectorAll("#dlgBody .invalid").length;
      document.querySelector("#dlg").close();
      asked.forEach((it, i) => { it.required = was[i]; });
      return { required, marked };
    });
    if (rf) t.check("ข้อบังคับที่ยังไม่ตอบถูกทำเครื่องหมายครบทุกข้อ (" + rf.required + " ข้อ)", rf.required > 0 && rf.marked === rf.required, rf.marked + "/" + rf.required);

    /* ---------- ลบแล้วเลิกทำ: กิจกรรม ---------- */
    const undo = await page.evaluate(async () => {
      const a = store.data.activities[3], idx = 3, n = store.data.activities.length;
      openActivity(a.id);
      [...document.querySelectorAll("#dlgFoot button")].find(b => b.textContent === "ลบรายการ").click();
      const gone = !store.data.activities.some(x => x.id === a.id);
      const btn = document.querySelector("#toasts .toast button");
      const hasUndo = btn?.textContent === "เลิกทำ";
      btn?.click();
      return { gone, hasUndo, back: store.data.activities.findIndex(x => x.id === a.id) === idx, count: store.data.activities.length === n };
    });
    t.check("ลบกิจกรรมแล้วหายทันที และมีปุ่ม 'เลิกทำ' ใน toast", undo.gone && undo.hasUndo);
    t.check("กดเลิกทำแล้วกลับมาที่ตำแหน่งเดิม จำนวนเท่าเดิม", undo.back && undo.count);

    /* ---------- ลบหน่วยแล้วเลิกทำ: ช่วงหมุนเวียนที่ถูกลบตามต้องกลับมาครบ ---------- */
    const cascade = await page.evaluate(() => {
      const svc = store.data.services.find(s => s.team);
      const rots = store.data.rotations.filter(r => r.serviceId === svc.id).length;
      const nS = store.data.services.length, nR = store.data.rotations.length;
      editService(svc.id);
      [...document.querySelectorAll("#dlgFoot button")].find(b => b.textContent === "ลบหน่วยนี้").click();
      const afterDel = { s: store.data.services.length, r: store.data.rotations.length };
      document.querySelector("#toasts .toast button")?.click();
      return { rots, deleted: afterDel.s === nS - 1 && afterDel.r === nR - rots,
               restored: store.data.services.length === nS && store.data.rotations.length === nR };
    });
    t.check("ลบหน่วยแล้วช่วงหมุนเวียนที่ผูกไว้หายตาม (" + cascade.rots + " ช่วง)", cascade.deleted);
    t.check("เลิกทำแล้วทั้งหน่วยและช่วงหมุนเวียนกลับมาครบ", cascade.restored);

    /* ---------- ยืนยันด้วยกล่องของแอป ไม่ใช่ popup ของเบราว์เซอร์ ---------- */
    const cd = await page.evaluate(async () => {
      showView("settings");
      const n = store.data.residents.length;
      document.querySelector("#btnWipe").click();
      await new Promise(r => setTimeout(r, 50));
      const open = document.querySelector("#dlg").open, title = document.querySelector("#dlgTitle").textContent;
      document.querySelector("#dlg").close();
      await new Promise(r => setTimeout(r, 50));
      return { open, title, intact: store.data.residents.length === n };
    });
    t.check("กดลบข้อมูลทั้งหมด → กล่องยืนยันของแอปเปิด ปิดกล่องแล้วข้อมูลยังอยู่", cd.open && cd.intact, cd.title);

    /* ---------- หน้าตั้งค่า: ดัชนี, h1 เดียว, checklist ---------- */
    const st = await page.evaluate(() => ({
      navButtons: document.querySelectorAll("#settingsNav button").length,
      anchors: document.querySelectorAll("#view-settings .card[data-anchor]").length,
      h1: document.querySelectorAll("#view-settings h1").length,
      firstCards: [...document.querySelectorAll("#view-settings .card[data-anchor]")].slice(0, 3).map(c => c.dataset.anchor),
      checklist: document.querySelectorAll("#yearChecklist li").length,
      wipeInDanger: document.querySelector("#btnWipe").closest(".card").dataset.anchor
    }));
    t.eq("ดัชนีมีปุ่มเท่าจำนวนการ์ด", st.navButtons, st.anchors);
    t.eq("หน้าตั้งค่ามี h1 เดียว", st.h1, 1);
    t.eq("การ์ดที่ใช้บ่อยอยู่บนสุด", st.firstCards, ["เตรียมปีการศึกษา", "บัญชีผู้ใช้", "สำรองข้อมูล"]);
    t.eq("checklist เตรียมปีมี 8 ข้อ", st.checklist, 8);
    t.eq("ปุ่มลบข้อมูลทั้งหมดอยู่ในโซนอันตราย", st.wipeInDanger, "โซนอันตราย");

    const ck = await page.evaluate(() => {
      const keep = store.data.rotations;
      store.data.rotations = []; renderYearChecklist();
      const rotItem = document.querySelectorAll("#yearChecklist li")[4].textContent;
      store.data.rotations = keep; renderYearChecklist();
      return { notOk: rotItem.includes("ยังไม่ครบ"), okAfter: document.querySelectorAll("#yearChecklist li")[4].textContent.includes("ครบ") };
    });
    t.check("checklist คำนวณสด: ลบช่วงหมุนเวียนแล้วข้อนั้นเป็น 'ยังไม่ครบ' คืนแล้วกลับเป็นครบ", ck.notOk && ck.okAfter);

    /* ---------- เพิ่มแพทย์ประจำบ้านพร้อมบัญชี ---------- */
    const acct = await page.evaluate(() => {
      editResident(null);
      document.querySelector('#dlgBody [name="name"]').value = "นพ. ทดสอบ บัญชีอัตโนมัติ";
      const username = document.querySelector('#dlgBody [name="username"]').value;
      document.querySelector('#dlgBody [name="pin"]').value = "4242";
      document.querySelector("#dlgFoot .btn-primary").click();
      const r = store.data.residents.find(x => x.name === "นพ. ทดสอบ บัญชีอัตโนมัติ");
      const u = store.data.users.find(x => x.residentId === r?.id);
      return { username, created: !!r, user: u && { username: u.username, role: u.role, pin: u.pin }, userId: u?.id };
    });
    t.check("เพิ่มคนใหม่แล้วมีบัญชีผูกให้ทันที บทบาทแพทย์ประจำบ้าน", acct.created && acct.user?.role === "resident" && acct.user?.username === acct.username && acct.user?.pin === "4242", JSON.stringify(acct.user));

    /* ล็อกอินด้วยบัญชีที่เพิ่งสร้าง → เห็นเฉพาะตัวเอง */
    await page.evaluate((uid) => localStorage.setItem("mnrh_ortho_portfolio_session_v1", JSON.stringify({ userId: uid, at: new Date().toISOString() })), acct.userId);
    await page.reload();
    await page.waitForFunction(() => typeof currentUser === "function" && !!currentUser());
    await page.waitForTimeout(300);
    const asNew = await page.evaluate(() => ({ role: myRole(), seen: visibleResidents().map(r => r.name) }));
    t.eq("บัญชีใหม่ล็อกอินแล้วเห็นเฉพาะตัวเอง", [asNew.role, asNew.seen], ["resident", ["นพ. ทดสอบ บัญชีอัตโนมัติ"]]);

    /* ---------- วันที่: ปี พ.ศ. 4 หลักทุกที่ และคำอ่านใต้ช่องวันที่ ---------- */
    const dt = await page.evaluate(() => {
      manualAdd();
      const hint = document.querySelector('#dlgBody input[type="date"] + .date-be')?.textContent || "";
      document.querySelector("#dlg").close();
      return { ym: ymLabel("2026-09"), ml: monthLabel({ m: 8, y: 2026 }), hint, today: fmtDate(todayISO()),
               dtime: fmtDateTime("2026-09-02T14:30:00") };
    });
    t.eq("ymLabel/monthLabel ใช้ปี พ.ศ. 4 หลัก", [dt.ym, dt.ml], ["ก.ย. 2569", "ก.ย. 2569"]);
    t.eq("ช่องวันที่มีคำอ่านแบบไทยใต้ช่อง", dt.hint, "= " + dt.today);
    t.eq("fmtDateTime ให้รูปแบบเดียวกับ fmtDate + เวลา", dt.dtime, "2 ก.ย. 2569 14:30");

    t.check("ไม่มี error หลุดในคอนโซล (รวมถึงไม่มีใครเรียก window.confirm)", errors.length === 0, errors.join(" | "));
    await page.close();
  } finally {
    await browser.close();
    await srv.close();
  }
  return t;
}
