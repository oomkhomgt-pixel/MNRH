/* หน้าปฏิทิน — ปฏิทินรวมการนำเสนอ (Trauma film, Pre/post-op conference, Topic conference, Journal club)
   ไม่มีโหมดรายคน: ทุกคนเห็นชุดเดียวกัน แพทย์ประจำบ้านเห็นเฉพาะของตัวเองผ่านตัวกรองสิทธิ์
   chip ในช่องวันเป็นตัวย่อประเภท + ชื่อสั้น สีตามประเภท — รายละเอียดเต็ม (รวมผู้นิเทศวันพฤหัสฯ) อยู่ในกล่องตอนกด */
import { chromium } from "playwright";
import { serve, launchOptions, openAs, suite } from "./lib.mjs";

const RESIDENT_OF = `(b) => {
  const i = b.dataset.pres.indexOf(":");
  const kind = b.dataset.pres.slice(0, i), id = b.dataset.pres.slice(i + 1);
  const list = kind === "schedule" ? store.data.schedule : store.data.activities;
  return list.find(x => x.id === id);
}`;

export default async function run() {
  const t = suite("ปฏิทินรวมการนำเสนอ");
  const srv = await serve();
  const browser = await chromium.launch(launchOptions());
  try {
    /* ---------- resident: ไม่มีตัวเลือกเปลี่ยนคน/สลับโหมด · chip ทั้งหมดเป็นของตัวเองตรงกับ presentationsForDate ---------- */
    {
      const { page, errors } = await openAs(browser, srv.url, "resident");
      const r = await page.evaluate(() => {
        showView("calendar");
        const noControls = !document.querySelector("#calScopeAll") && !document.querySelector("#calResidentPick");
        const rid = myResidentId();
        const anyOfMine = store.data.schedule.find(x => x.residentId === rid) ||
          store.data.activities.find(x => x.residentId === rid);
        if (!anyOfMine) return { none: true, noControls };
        calMonth = anyOfMine.date.slice(0, 7);
        renderCalendar();
        const cells = [...document.querySelectorAll("#calGrid .gcal-cell")];
        const first = calMonth + "-01";
        const leadDays = (new Date(first + "T00:00:00").getDay() + 6) % 7;
        const gridStart = addDaysISO(first, -leadDays);
        const isos = Array.from({ length: 42 }, (_, i) => addDaysISO(gridStart, i));
        /* presentationsForDate กรองด้วย canSeeResident อยู่แล้ว — สำหรับ resident จึงมีแต่ของตัวเอง */
        const want = new Set(isos.flatMap(iso => presentationsForDate(iso).map(p => p.kind + ":" + p.id)));
        const got = new Set([...document.querySelectorAll("#calGrid [data-pres]")].map(b => b.dataset.pres));
        const wantAllMine = isos.flatMap(iso => presentationsForDate(iso)).every(p => p.residentId === rid);
        return { none: false, noControls, cellCount: cells.length, wantSize: want.size, wantAllMine,
                 extra: [...got].filter(k => !want.has(k)), missing: [...want].filter(k => !got.has(k)) };
      });
      t.check("resident: ไม่มีตัวเลือกสลับตารางรวม/รายคน และไม่มีตัวเลือกเปลี่ยนคน", r.noControls);
      if (r.none) {
        t.check("resident: ข้ามชุดนี้ — ข้อมูลสาธิตไม่มีการนำเสนอของบัญชีนี้เลย", false);
      } else {
        t.check("resident: กริดเดือนมี 42 ช่อง (6 สัปดาห์ x 7 วัน)", r.cellCount === 42, r.cellCount);
        t.check("resident: มีรายการให้ตรวจจริง และทุกรายการที่ระบบคืนมาเป็นของตัวเอง", r.wantSize > 0 && r.wantAllMine, r.wantSize);
        t.eq("resident: ไม่มี chip เกินมาที่ไม่ใช่ของฉัน", r.extra, []);
        t.eq("resident: ไม่มี chip ของฉันตกหล่นไปจากกริด", r.missing, []);
      }
      t.check("resident: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }

    /* ---------- staff/admin: ปฏิทินรวมเห็นหลายคน · chip ย่อ+สี · กดแล้วเห็นตัวเต็ม ปุ่มตามสิทธิ์ ---------- */
    for (const role of ["staff", "admin"]) {
      const { page, errors } = await openAs(browser, srv.url, role);
      const r = await page.evaluate(async (recOfSrc) => {
        const recOf = new Function("return " + recOfSrc)();
        showView("calendar");
        const chips = [...document.querySelectorAll("#calGrid [data-pres]")];
        const residentIds = new Set(chips.map(b => recOf(b)?.residentId).filter(Boolean));
        const abbrOk = chips.every(b => {
          const rec = recOf(b);
          const abbr = b.querySelector(".abbr")?.textContent.trim();
          return rec && abbr === TYPE_BY_ID[rec.type].icon && b.classList.contains("pres-" + rec.type);
        });
        const compact = chips.every(b => !b.querySelector(".tc-info") && !b.querySelector(".tag") &&
          b.textContent.trim().length < 40);
        const noneClickableDivs = !document.querySelector("#calGrid div[data-pres]");

        /* กด chip ของ topic conference → กล่องรายละเอียดมีชื่อเต็ม หัวข้อ และบรรทัดผู้นิเทศ */
        const topicChip = chips.find(b => recOf(b)?.type === "topic");
        let topic = null;
        if (topicChip) {
          const rec = recOf(topicChip);
          topicChip.click();
          await new Promise(res => setTimeout(res, 50));
          const body = document.querySelector("#dlgBody")?.textContent || "";
          const foot = [...document.querySelectorAll("#dlgFoot button")].map(x => x.textContent);
          topic = { open: document.querySelector("#dlg")?.open === true, title: document.querySelector("#dlgTitle")?.textContent,
                    fullName: body.includes(store.resident(rec.residentId).name), hasTitle: body.includes(rec.title),
                    tcLine: !!document.querySelector("#dlgBody .tc-info"), foot };
          document.querySelector("#dlg").close();
        }
        /* กด chip ของ trauma film → ไม่มีบรรทัดผู้นิเทศ */
        const filmChip = chips.find(b => recOf(b)?.type === "traumafilm");
        let film = null;
        if (filmChip) {
          filmChip.click();
          await new Promise(res => setTimeout(res, 50));
          film = { open: document.querySelector("#dlg")?.open === true, tcLine: !!document.querySelector("#dlgBody .tc-info") };
          document.querySelector("#dlg").close();
        }
        return { chips: chips.length, residentCount: residentIds.size, abbrOk, compact, noneClickableDivs, topic, film };
      }, RESIDENT_OF);
      t.check(role + ": ปฏิทินรวมเห็นของหลายคนพร้อมกันในเดือนเดียว", r.residentCount > 1, r.residentCount);
      t.check(role + ": chip ทุกอันมีตัวย่อ T/P/F/J ตรงประเภท และ class pres-{type}", r.chips > 0 && r.abbrOk, r.chips);
      t.check(role + ": chip กระชับ — ไม่มีป้ายสถานะ/บรรทัดผู้นิเทศ/หัวข้อยัดลงช่องวัน", r.compact);
      t.check(role + ": chip ทุกอันกดได้ (ไม่มี <div> ที่กดไม่ได้อีกแล้ว)", r.noneClickableDivs);
      if (r.topic) {
        t.check(role + ": กด chip Topic conference เปิดกล่องรายละเอียดที่มีชื่อเต็ม หัวข้อ และผู้นิเทศวันพฤหัสฯ",
                r.topic.open && r.topic.title === "รายละเอียดการนำเสนอ" && r.topic.fullName && r.topic.hasTitle && r.topic.tcLine,
                JSON.stringify(r.topic));
        t.check(role + (role === "admin" ? ": ผู้จัดหลักสูตรเห็นปุ่ม 'แก้ไขรายการ'" : ": อาจารย์ทั่วไปไม่เห็นปุ่ม 'แก้ไขรายการ'"),
                r.topic.foot.includes("แก้ไขรายการ") === (role === "admin"), r.topic.foot.join(" / "));
      } else t.check(role + ": ไม่มีคาบ Topic conference ในเดือนนี้ให้ทดสอบ", false);
      if (r.film) t.check(role + ": กล่องของ Trauma film ไม่มีบรรทัดผู้นิเทศ", r.film.open && !r.film.tcLine);
      t.check(role + ": ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }

    /* ---------- ผู้นิเทศที่กำหนดไว้จริงโผล่ในกล่องของวันนั้น ---------- */
    {
      const { page, errors } = await openAs(browser, srv.url, "admin");
      const r = await page.evaluate(async () => {
        showView("calendar");
        const tcEntry = store.data.schedule.find(x => x.type === "topic");
        if (!tcEntry) return { none: true };
        store.data.topicConf = [{ id: "tc_cal_test", date: tcEntry.date, staffId: store.data.staff[0].id, teamServiceId: "" }];
        calMonth = tcEntry.date.slice(0, 7);
        renderCalendar();
        document.querySelector(`#calGrid [data-pres="schedule:${tcEntry.id}"]`).click();
        await new Promise(res => setTimeout(res, 50));
        const line = document.querySelector("#dlgBody .tc-info")?.textContent || "";
        document.querySelector("#dlg").close();
        store.data.topicConf = [];
        return { none: false, line, staff: store.data.staff[0].name };
      });
      if (r.none) t.check("ข้ามชุดนี้ — ข้อมูลสาธิตไม่มีคาบ topic conference เลย", false);
      else t.check("กำหนดผู้นิเทศแล้ว กล่องของวันนั้นบอกชื่ออาจารย์ที่กำหนด", r.line.includes(r.staff), r.line);
      t.check("Topic conference: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }
  } finally {
    await browser.close();
    await srv.close();
  }
  return t;
}
