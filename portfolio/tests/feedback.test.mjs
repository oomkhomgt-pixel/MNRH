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

    /* ---------- ลบผลประเมินลงกองแล้วเลิกทำ (ผู้จัดหลักสูตร) ---------- */
    const revUndo = await page.evaluate(async () => {
      const ev = (store.data.rotationEvals || [])[0];
      if (!ev) return null;
      const n = store.data.rotationEvals.length;
      openRotationEval(ev.rotationId);
      await new Promise(r => setTimeout(r, 120));
      [...document.querySelectorAll("#dlgFoot button")].find(b => b.textContent === "ลบผลประเมิน")?.click();
      await new Promise(r => setTimeout(r, 100));
      const gone = !rotationEvalFor(ev.rotationId);
      const btn = document.querySelector("#toasts .toast button");
      const hasUndo = btn?.textContent === "เลิกทำ";
      btn?.click();
      return { gone, hasUndo, back: !!rotationEvalFor(ev.rotationId), count: store.data.rotationEvals.length === n };
    });
    if (revUndo) t.check("ลบผลประเมินลงกองแล้วมี 'เลิกทำ' และกู้คืนได้", revUndo.gone && revUndo.hasUndo && revUndo.back && revUndo.count);

    /* ---------- ผู้จัดหลักสูตรเห็นงานลงกองค้างทั้งกลุ่มงานบนหน้าวันนี้ · แพทย์ประจำบ้านเห็นผลลงกองรายข้อ ไม่ใช่ id ดิบ ---------- */
    const vis = await page.evaluate(() => {
      showView("today"); renderToday();
      const adminStat = /ผลประเมินลงกองค้าง/.test(document.querySelector("#todayBody").textContent);
      const ev = (store.data.rotationEvals || []).find(x => Object.keys(x.scores || {}).length && x.answers?.outcome);
      if (!ev) return { adminStat, noEval: true };
      selectedResident = ev.residentId; renderResidentDetail(); showView("resident");
      const box = document.querySelector("#residentDetail");
      const sec = box.textContent;
      const label = rotationOutcomeLabel(ev);
      return { adminStat, hasSection: /ผลประเมินลงกอง \(\d+ รอบ\)/.test(sec), hasLabel: !!label && sec.includes(label),
               rawId: /\b(pass|advice|watch)\b/.test(sec), tags: box.querySelectorAll(".tag[title]").length > 0 };
    });
    t.check("หน้าวันนี้ของผู้จัดหลักสูตรมีตัวเลขผลประเมินลงกองค้างทั้งกลุ่มงาน", vis.adminStat);
    if (!vis.noEval) {
      t.check("หน้าแพทย์ประจำบ้านมีตารางผลประเมินลงกอง พร้อมป้ายผลโดยรวม (ไม่ใช่ pass/advice/watch ดิบ) และคะแนนรายข้อ",
              vis.hasSection && vis.hasLabel && !vis.rawId && vis.tags, JSON.stringify(vis));
    }

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

    /* ---------- การ์ดพับได้ (data-fold) และ "แสดงเพิ่ม" (data-more) — ซ่อนบนจอเท่านั้น ไม่มีอะไรหายจาก DOM ---------- */
    const fold = await page.evaluate(async () => {
      const r = {};
      showView("settings");
      const cards = [...document.querySelectorAll("#view-settings .card[data-fold]")];
      r.foldable = cards.length;
      r.foldedByDefault = cards.filter(c => c.classList.contains("folded")).length;
      r.checklistOpen = !document.querySelector('[data-fold="set-เตรียมปีการศึกษา"]').classList.contains("folded");
      /* ปุ่มข้างในการ์ดที่พับอยู่ยังอยู่ครบ แค่มองไม่เห็น */
      const users = document.querySelector('[data-fold="set-บัญชีผู้ใช้"]');
      r.hiddenButtons = users.querySelectorAll("#userTable button").length;
      r.hiddenNotVisible = !users.querySelector("#userTable").offsetParent;
      r.sumTag = users.querySelector("h2 .fold-sum")?.textContent || "";
      r.aria = users.querySelector("h2").getAttribute("aria-expanded");
      /* กดหัวข้อ → ขยาย และจำไว้ */
      users.querySelector("h2").click();
      r.openedByClick = !users.classList.contains("folded") && !!users.querySelector("#userTable").offsetParent;
      r.stored = JSON.parse(localStorage.getItem("ortho-folds") || "{}")["set-บัญชีผู้ใช้"];
      /* render ใหม่ทั้งแอป (innerHTML แทนที่) สถานะต้องกลับมาเหมือนเดิม */
      renderAll(); await new Promise(res => requestAnimationFrame(() => setTimeout(res, 30)));
      r.survivesRender = !document.querySelector('[data-fold="set-บัญชีผู้ใช้"]').classList.contains("folded")
        && document.querySelector('[data-fold="set-อาจารย์"]').classList.contains("folded");
      /* ปุ่มบนดัชนีเปิดการ์ดที่พับอยู่ให้ */
      const staffIdx = [...document.querySelectorAll("#settingsNav [data-goto]")].find(b => b.textContent === "อาจารย์");
      staffIdx.click();
      r.navOpens = !document.querySelector('[data-fold="set-อาจารย์"]').classList.contains("folded");
      /* คีย์บอร์ด: Enter บนหัวข้อ */
      const h = document.querySelector('[data-fold="set-อาจารย์"] h2');
      h.focus(); h.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
      r.keyboardFolds = document.querySelector('[data-fold="set-อาจารย์"]').classList.contains("folded");
      /* กดปุ่มในบล็อกหัว (เช่น + เพิ่มบัญชี) ต้องไม่พับ/ขยาย */
      const before = users.classList.contains("folded");
      users.querySelector("#btnAddUser").click(); document.querySelector("#dlg").close();
      r.buttonNoToggle = users.classList.contains("folded") === before;
      return r;
    });
    /* พิมพ์ = เห็นครบ — จำลอง media print แล้ววัดว่าตารางในการ์ดที่พับอยู่กลับมามองเห็น */
    await page.emulateMedia({ media: "print" });
    fold.printExpands = await page.evaluate(() => {
      const c = document.querySelector('[data-fold="set-อาจารย์"]');
      const hints = [...document.querySelectorAll("[data-fold] > details.hint")];
      return c.classList.contains("folded") && getComputedStyle(c.querySelector("#staffTable")).display !== "none"
        && hints.length > 0 && hints.every(h => getComputedStyle(h).display === "none");   /* คำอธิบาย ⓘ ไม่พิมพ์ ไม่ว่าการ์ดพับหรือกาง */
    });
    await page.emulateMedia({ media: "screen" });
    t.check("หน้าตั้งค่า: การ์ดทุกใบพับได้ พับไว้ก่อนยกเว้น checklist เตรียมปี", fold.foldable >= 15 && fold.foldedByDefault === fold.foldable - 1 && fold.checklistOpen, JSON.stringify(fold));
    t.check("การ์ดที่พับอยู่ยังมีปุ่มครบใน DOM แค่มองไม่เห็น และมีป้ายจำนวนกับ aria-expanded=false",
            fold.hiddenButtons > 0 && fold.hiddenNotVisible && /รายการ/.test(fold.sumTag) && fold.aria === "false", JSON.stringify(fold));
    t.check("กดหัวข้อแล้วขยาย จำสถานะไว้ในเครื่อง และรอดจากการ render ใหม่", fold.openedByClick && fold.stored === "open" && fold.survivesRender);
    t.check("ปุ่มดัชนีเปิดการ์ดที่พับอยู่ · Enter บนหัวข้อพับได้ · ปุ่มในบล็อกหัวไม่ไปสลับการพับ", fold.navOpens && fold.keyboardFolds && fold.buttonNoToggle);
    t.check("ตอนพิมพ์ ทุกส่วนที่พับถูกขยายด้วย CSS", fold.printExpands);

    const more = await page.evaluate(async () => {
      showView("logbook");
      const r = {};
      r.cases = document.querySelectorAll("#caseTable tbody tr").length;
      r.caseTotal = filterCases().length;
      return r;
    });
    t.check("เคสทั้งหมดใน logbook เริ่มที่ 30 แถว", more.cases === Math.min(30, more.caseTotal), JSON.stringify(more));

    /* ---------- ช่วงหมุนเวียนทั้งหมด: ตารางแยกถูกตัดออก แก้ไข/ลบยังทำได้ผ่านคลิกเซลล์ในตารางรายเดือน (มีเทสต์อยู่แล้วใน schedule.test.mjs) ---------- */
    const rotEdit = await page.evaluate(async () => {
      showView("rotation");
      return { noTable: !document.querySelector("#rotationTable"), noWeekGrid: !document.querySelector("#weekGrid") };
    });
    t.check("ตาราง 'ช่วงหมุนเวียนทั้งหมด' และตารางประจำสัปดาห์ถูกเอาออกแล้ว", rotEdit.noTable && rotEdit.noWeekGrid, JSON.stringify(rotEdit));

    /* ---------- รายชื่อกับแฟ้มรายบุคคลเป็นคนละหน้า ---------- */
    const split = await page.evaluate(async () => {
      const r = {};
      showView("residents");
      r.listHasNoDetail = !document.querySelector("#view-residents #residentDetail") && !/ความก้าวหน้าตามเกณฑ์/.test(document.querySelector("#view-residents").textContent);
      r.rows = document.querySelectorAll("#residentList tbody tr").length;
      const second = document.querySelectorAll("#residentList [data-res]")[1];
      second.click();
      r.viewAfterOpen = currentViewName(); r.hash = location.hash;
      r.detailName = document.querySelector("#residentDetail h2")?.textContent.includes(store.resident(second.dataset.res).name);
      const pick = document.querySelector("#resPick");
      r.pickShown = !pick.hidden && pick.options.length === visibleResidents().length && pick.value === second.dataset.res;
      pick.value = pick.options[0].value; pick.dispatchEvent(new Event("change", { bubbles: true }));
      r.pickSwitches = document.querySelector("#residentDetail h2")?.textContent.includes(store.resident(pick.options[0].value).name);
      document.querySelector("#btnResidentBack").click();
      r.backToList = currentViewName() === "residents";
      r.printBtnOnDetail = !!document.querySelector("#view-resident #btnPrintPortfolio");
      return r;
    });
    t.check("หน้ารายชื่อมีแต่ตาราง ไม่ต่อท้ายด้วยแฟ้มของใคร", split.listHasNoDetail && split.rows > 1, JSON.stringify(split));
    t.check("กด 'เปิดแฟ้ม' แล้วไปหน้า 'แฟ้มรายบุคคล' ของคนนั้น (hash ตาม) มีตัวเลือกคนไว้สลับ และปุ่มกลับ",
            split.viewAfterOpen === "resident" && split.hash === "#resident" && split.detailName && split.pickShown && split.pickSwitches && split.backToList && split.printBtnOnDetail, JSON.stringify(split));

    /* ---------- อาจารย์: อนุสาขาหลายสายเห็นและแก้ได้ · ข้อมูลสาธิตเก่าในเครื่องถูกแก้คำนำหน้า ---------- */
    const staff = await page.evaluate(() => {
      const r = {};
      const row = [...document.querySelectorAll("#staffTable tbody tr")].find(tr => /นฤพล/.test(tr.textContent));
      r.traumaTag = !!row && [...row.querySelectorAll(".tag")].some(t => /Trauma/.test(t.textContent)) && [...row.querySelectorAll(".tag")].some(t => /Arthroplasty/.test(t.textContent));
      /* แก้ไขอาจารย์คนหนึ่งให้มีสองสาย */
      const st = store.data.staff.find(x => x.id === "st_1");
      editStaff(st.id);
      const boxes = [...document.querySelectorAll('#dlgBody input[type="checkbox"][name^="sub_"]')];
      r.checkboxes = boxes.length;
      boxes.forEach(b => b.checked = false);
      document.querySelector('#dlgBody [name="sub_spine"]').checked = true;
      document.querySelector('#dlgBody [name="sub_hand"]').checked = true;
      document.querySelector("#dlgFoot .btn-primary").click();
      r.saved = JSON.stringify([st.subspecialty, st.subspecialties]);
      /* ไม่ติ๊กเลย → error ที่ช่อง กล่องไม่ปิด */
      editStaff(st.id);
      [...document.querySelectorAll('#dlgBody input[type="checkbox"][name^="sub_"]')].forEach(b => b.checked = false);
      document.querySelector("#dlgFoot .btn-primary").click();
      r.emptyRefused = document.querySelector("#dlg").open && !!document.querySelector("#dlgBody .err");
      document.querySelector("#dlg").close();
      /* migration: จำลองข้อมูลสาธิตเก่าที่ยังเป็น นพ. และไม่มี trauma */
      const d = store.data;
      d.staff.find(x => x.id === "st_1").name = "นพ. มานิตา";
      d.users.filter(u => u.staffId === "st_1").forEach(u => u.displayName = "นพ. มานิตา");
      d.cases[0].primarySurgeon = "นพ. มานิตา";
      const s12 = d.staff.find(x => x.id === "st_12"); delete s12.subspecialties; s12.subspecialty = "arthroplasty";
      store.migrate();
      r.migrated = d.staff.find(x => x.id === "st_1").name === "พญ. มานิตา"
        && d.users.filter(u => u.staffId === "st_1").every(u => u.displayName === "พญ. มานิตา")
        && d.cases[0].primarySurgeon === "พญ. มานิตา"
        && JSON.stringify(s12.subspecialties) === JSON.stringify(["arthroplasty", "trauma"]);
      /* ชื่อที่ผู้ใช้แก้เองไม่ถูกแตะ */
      d.staff.find(x => x.id === "st_19").name = "นพ. สมชาย"; store.migrate();
      r.customKept = d.staff.find(x => x.id === "st_19").name === "นพ. สมชาย";
      return r;
    });
    t.check("ตารางอาจารย์แสดงทุกอนุสาขา (นพ. นฤพล มีทั้ง Arthroplasty และ Trauma)", staff.traumaTag);

    /* ---------- ภาพรวมก่อน แล้วค่อยเลือกคน (อาจารย์/ผู้จัดหลักสูตร) ---------- */
    const overview = await page.evaluate(() => {
      const r = {};
      showView("epa");
      const cards = [...document.querySelectorAll("#view-epa > .card")].filter(c => !c.hidden);
      r.epaOrder = cards.map(c => c.dataset.fold);
      r.epaMatrixOpen = !cards[0].classList.contains("folded") && !!document.querySelector("#epaMatrix table");
      r.epaPersonFolded = cards[1].classList.contains("folded");
      const sel = document.querySelector("#epaResident"); sel.value = sel.options[1].value; sel.dispatchEvent(new Event("change"));
      r.epaPersonOpensOnPick = !cards[1].classList.contains("folded") && epaResidentId === sel.options[1].value;
      showView("calendar");
      r.calNoOneChosen = calResidentId === "" && !!document.querySelector("#calGrid .empty") && document.querySelector("#calResidentPick").value === "";
      document.querySelector("#calGrid [data-goto-roster]").click();
      r.calGotoRoster = currentViewName() === "rotation" && !document.querySelector('[data-segview="month"]').hidden;
      return r;
    });
    t.check("EPA ของอาจารย์: ภาพรวมทั้งกลุ่มงานมาก่อนและเปิดอยู่ · รายบุคคลพับไว้จนกว่าจะเลือกคน",
            overview.epaOrder[0] === "epa-matrix" && overview.epaMatrixOpen && overview.epaPersonFolded && overview.epaPersonOpensOnPick, JSON.stringify(overview));
    t.check("ปฏิทินของอาจารย์: ยังไม่เดาเอาคนแรก ต้องเลือกก่อน และมีทางไปตารางรวมของทุกคน",
            overview.calNoOneChosen && overview.calGotoRoster, JSON.stringify(overview));
    t.check("กล่องแก้ไขอาจารย์ติ๊กได้หลายสาย บันทึกเป็น subspecialties และสายแรกเป็น subspecialty · ไม่ติ๊กเลยถูกปฏิเสธที่ช่อง",
            staff.checkboxes > 3 && staff.saved === JSON.stringify(["spine", ["spine", "hand"]]) && staff.emptyRefused, JSON.stringify(staff));
    t.check("ข้อมูลสาธิตเก่าในเครื่อง: นพ. มานิตา → พญ. (รวมบัญชีและศัลยแพทย์หลักในเคส) · นพ. นฤพล ได้ Trauma · ชื่อที่แก้เองไม่ถูกแตะ",
            staff.migrated && staff.customKept, JSON.stringify(staff));

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
