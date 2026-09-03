/* หน้าปฏิทิน — ปฏิทินรวมการนำเสนอ (Trauma film, Pre/post-op conference, Topic conference, Journal club)
   · ตารางนำเสนอเป็นของทั้งภาควิชา ทุกบทบาทเห็นชุดเดียวกัน แพทย์ประจำบ้านสลับ "ของฉัน" ได้ อาจารย์/ผู้จัดหลักสูตรไม่มีปุ่มสลับ
   · F/P ไม่ fix ผู้นำเสนอล่วงหน้า: วันข้างหน้าเป็นช่องประจำเปล่า (kind "slot") ตามรูปแบบ morning conference
     ชื่อโผล่เมื่อมีกิจกรรมจากสไลด์ในวันนั้น · วันหยุดราชการไม่มีช่อง
   · chip = ตัวย่อ + ชื่อเต็ม + หัวข้อย่อ รายละเอียดเต็ม (รวมผู้นิเทศวันพฤหัสฯ) อยู่ในกล่องตอนกด */
import { chromium } from "playwright";
import { serve, launchOptions, openAs, suite } from "./lib.mjs";

/* อ่านเรคคอร์ดต้นทางของ chip — ใส่เป็นสตริงแล้ว new Function ในหน้า เพราะ page.evaluate ส่งฟังก์ชันข้ามไม่ได้ */
const REC_OF = `(b) => {
  const i = b.dataset.pres.indexOf(":");
  const kind = b.dataset.pres.slice(0, i), id = b.dataset.pres.slice(i + 1);
  /* id ของ slot/info = "type:วันที่" (ช่อง T ที่สองของพฤหัสฯ ต่อท้าย "#2" · การประชุมภายนอกเป็น "external:<id>") */
  if (kind === "slot" || kind === "info") return { kind, type: id.slice(0, id.indexOf(":")), date: id.slice(id.indexOf(":") + 1, id.indexOf(":") + 11), residentId: "" };
  const rec = (kind === "schedule" ? store.data.schedule : store.data.activities).find(x => x.id === id);
  return rec ? { kind, ...rec } : null;
}`;

export default async function run() {
  const t = suite("ปฏิทินรวมการนำเสนอ");
  const srv = await serve();
  const browser = await chromium.launch(launchOptions());
  try {
    /* ---------- ช่องประจำ F/P · วันหยุด · ชื่อโผล่จากสไลด์ · chip สองบรรทัด (admin) ---------- */
    {
      const { page, errors } = await openAs(browser, srv.url, "admin");
      const r = await page.evaluate(async (recOfSrc) => {
        const recOf = new Function("return " + recOfSrc)();
        showView("calendar");
        const mc = store.data.programme.morningConference;
        /* วันข้างหน้าที่อยู่ในรูปแบบ (ไม่ใช่พฤหัสฯ) และไม่มีแถว/กิจกรรมใด ๆ */
        let iso = addDaysISO(todayISO(), 1);
        while (!mc.days.includes(new Date(iso + "T00:00:00").getDay())) iso = addDaysISO(iso, 1);
        const future = presentationsForDate(iso);
        const slotTypes = future.filter(p => p.kind === "slot").map(p => p.type);
        const orderOk = future.map(p => p.start).every((s, i, a) => i === 0 || a[i - 1] <= s);
        /* วันหยุดราชการ: ตั้ง duty ของวันนั้นเป็นวันหยุดแล้วช่องต้องหาย */
        (store.data.duty ||= []).push({ id: "duty_cal_test", date: iso, holiday: true });
        const onHoliday = presentationsForDate(iso).filter(p => p.kind === "slot").length;
        store.data.duty = store.data.duty.filter(d => d.id !== "duty_cal_test");
        /* วันที่มีกิจกรรม F จากสไลด์ ต้องไม่มีช่อง slot F ซ้ำ */
        const filmAct = store.data.activities.find(a => a.type === "traumafilm" && !a.scheduleId);
        const withFilm = filmAct ? presentationsForDate(filmAct.date) : [];
        const noDupFilm = !!filmAct && withFilm.some(p => p.kind === "activity" && p.type === "traumafilm") &&
          !withFilm.some(p => p.kind === "slot" && p.type === "traumafilm");
        /* พฤหัสฯ ไม่มีช่อง F/P (มีแต่โครง 4 ช่วงของเช้าพฤหัสฯ) */
        let thu = addDaysISO(todayISO(), 1);
        while (new Date(thu + "T00:00:00").getDay() !== 4) thu = addDaysISO(thu, 1);
        const thuSlots = presentationsForDate(thu).filter(p => p.kind === "slot" && (p.type === "traumafilm" || p.type === "preop")).length;
        /* บ่ายพฤหัสฯ มี Inter-hospital conference แสดงเฉย ๆ (kind "info") ไม่มีผู้นำเสนอ */
        const thuInfo = presentationsForDate(thu).filter(p => p.kind === "info" && p.type === "interhospital");
        const infoOk = thuInfo.length === 1 && thuInfo[0].start === "13:00" && !thuInfo[0].residentId;
        const infoOnlyThu = presentationsForDate(iso).every(p => p.type !== "interhospital");

        /* chip บนกริดเดือนปัจจุบัน */
        calMonth = todayISO().slice(0, 7); renderCalendar();
        const chips = [...document.querySelectorAll("#calGrid [data-pres]")];
        const noToggle = document.querySelector("#calScopeWrap").hidden === true;
        const abbrOk = chips.every(b => {
          const rec = recOf(b);
          return rec && b.querySelector(".abbr")?.textContent.trim() === presTypeOf(rec.type).icon && b.classList.contains("pres-" + rec.type);
        });
        const compact = chips.every(b => !b.querySelector(".tag") && !b.querySelector(".tc-info"));
        const named = chips.filter(b => recOf(b)?.residentId);
        /* Topic แสดง "ผู้นำเสนอ / chief" — ชื่อผู้นำเสนอเต็มต้องขึ้นต้น */
        const fullName = named.length > 0 && named.every(b => {
          const rec = recOf(b); return (b.querySelector(".nm")?.textContent || "").startsWith(store.resident(rec.residentId)?.name);
        });
        const titled = named.filter(b => recOf(b)?.title).every(b => !!b.querySelector(".ttl"));
        const slotChips = chips.filter(b => recOf(b)?.kind === "slot");
        const slotLabelOk = slotChips.length > 0 && slotChips.every(b => b.classList.contains("slot") &&
          /ยังไม่ระบุผู้นำเสนอ|ไม่มีสไลด์ส่ง|ยังไม่ลงตาราง/.test(b.querySelector(".nm")?.textContent || ""));
        const residentIds = new Set(named.map(b => recOf(b).residentId));

        /* กดช่องประจำ → กล่องมีปุ่มไปหน้ารับสไลด์ และ admin มีปุ่มลงตารางล่วงหน้า */
        const futureSlot = slotChips.find(b => recOf(b).date >= todayISO());
        let slot = null;
        if (futureSlot) {
          futureSlot.click(); await new Promise(res => setTimeout(res, 50));
          slot = { title: document.querySelector("#dlgTitle")?.textContent,
                   foot: [...document.querySelectorAll("#dlgFoot button")].map(x => x.textContent) };
          document.querySelector("#dlg").close();
        }
        /* กด T → กล่องมีชื่อเต็ม หัวข้อ ผู้นิเทศ และปุ่มแก้ไข */
        const topicChip = chips.find(b => recOf(b)?.type === "topic" && recOf(b)?.kind === "schedule");
        let topic = null;
        if (topicChip) {
          const rec = recOf(topicChip);
          topicChip.click(); await new Promise(res => setTimeout(res, 50));
          const body = document.querySelector("#dlgBody")?.textContent || "";
          topic = { title: document.querySelector("#dlgTitle")?.textContent, fullName: body.includes(store.resident(rec.residentId).name),
                    hasTitle: body.includes(rec.title), tcLine: !!document.querySelector("#dlgBody .tc-info"),
                    foot: [...document.querySelectorAll("#dlgFoot button")].map(x => x.textContent) };
          document.querySelector("#dlg").close();
        }
        /* กด I → กล่องบอกว่าแสดงเฉย ๆ ไม่มีปุ่มอะไรนอกจากปิด */
        const infoChip = chips.find(b => recOf(b)?.kind === "info" && recOf(b)?.type === "interhospital");
        let info = null;
        if (infoChip) {
          infoChip.click(); await new Promise(res => setTimeout(res, 50));
          info = { title: document.querySelector("#dlgTitle")?.textContent, noEval: /ไม่มีการประเมิน/.test(document.querySelector("#dlgBody")?.textContent || ""),
                   foot: [...document.querySelectorAll("#dlgFoot button")].map(x => x.textContent) };
          document.querySelector("#dlg").close();
        }
        return { slotTypes, orderOk, onHoliday, hasFilmAct: !!filmAct, noDupFilm, thuSlots, infoOk, infoOnlyThu, info, chips: chips.length, noToggle,
                 abbrOk, compact, fullName, titled, slotLabelOk, residentCount: residentIds.size, slot, topic };
      }, REC_OF);
      t.eq("วันราชการข้างหน้าที่ยังไม่มีอะไรลง มีช่องประจำ F แล้ว P เรียงตามเวลา", r.slotTypes, ["traumafilm", "preop"]);
      t.check("รายการในวันเรียงตามเวลาเริ่ม", r.orderOk);
      t.eq("วันหยุดราชการไม่มีช่องประจำ", r.onHoliday, 0);
      t.check("วันที่มีกิจกรรม Trauma film จากสไลด์ ไม่มีช่องประจำ F ซ้ำ", r.hasFilmAct && r.noDupFilm);
      t.eq("วันพฤหัสบดีไม่มีช่อง F/P (เป็นโครง 4 ช่วง Topic/Journal ที่ลงตารางล่วงหน้า)", r.thuSlots, 0);
      t.check("บ่ายพฤหัสฯ มี Inter-hospital conference แสดงเฉย ๆ 13:00 ไม่มีผู้นำเสนอ และไม่โผล่วันอื่น", r.infoOk && r.infoOnlyThu);
      t.check("กด I: กล่องบอกว่าเป็นกิจกรรมบังคับทั้งรุ่น ไม่มีการประเมิน และไม่มีปุ่มทำอะไร",
        !!r.info && r.info.title === "กิจกรรมบังคับเข้าทั้งรุ่น" && r.info.noEval && r.info.foot.length === 1, JSON.stringify(r.info));
      t.check("admin ไม่มีปุ่มสลับ ทั้งกลุ่มงาน/ของฉัน", r.noToggle);
      t.check("admin: ตารางรวมเห็นของหลายคนในเดือนเดียว", r.residentCount > 1, r.residentCount);
      t.check("chip ทุกอันมีตัวย่อ T/P/F/J ตรงประเภท และ class pres-{type}", r.chips > 0 && r.abbrOk, r.chips);
      t.check("chip ไม่มีป้ายสถานะ/บรรทัดผู้นิเทศยัดลงช่องวัน", r.compact);
      t.check("chip ที่มีผู้นำเสนอแสดงชื่อเต็มพร้อมคำนำหน้า และมีหัวข้อย่อเมื่อมีหัวข้อ", r.fullName && r.titled);
      t.check("ช่องประจำที่ยังไม่มีคนเป็นเส้นประ บอกว่ายังไม่ระบุผู้นำเสนอ/ไม่มีสไลด์ส่ง", r.slotLabelOk);
      if (r.slot) t.check("กดช่องประจำ: กล่องมีปุ่มไปหน้ารับสไลด์ และผู้จัดหลักสูตรมีปุ่มลงตารางล่วงหน้า",
        r.slot.title === "ช่องนำเสนอประจำวัน" && r.slot.foot.includes("ไปหน้ารับสไลด์") && r.slot.foot.includes("ลงตารางล่วงหน้าสำหรับวันนี้"), JSON.stringify(r.slot));
      else t.check("ไม่มีช่องประจำในเดือนนี้ให้ทดสอบ", false);
      if (r.topic) t.check("กด T: กล่องรายละเอียดมีชื่อเต็ม หัวข้อ ผู้นิเทศวันพฤหัสฯ และปุ่มแก้ไขรายการ (admin)",
        r.topic.title === "รายละเอียดการนำเสนอ" && r.topic.fullName && r.topic.hasTitle && r.topic.tcLine && r.topic.foot.includes("แก้ไขรายการ"), JSON.stringify(r.topic));
      else t.check("ไม่มีคาบ Topic conference ในเดือนนี้ให้ทดสอบ", false);
      t.check("admin: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }

    /* ---------- staff: ไม่มีปุ่มสลับ · ไม่มีปุ่มแก้ไขรายการ ---------- */
    {
      const { page, errors } = await openAs(browser, srv.url, "staff");
      const r = await page.evaluate(async (recOfSrc) => {
        const recOf = new Function("return " + recOfSrc)();
        showView("calendar");
        const chips = [...document.querySelectorAll("#calGrid [data-pres]")];
        const topicChip = chips.find(b => recOf(b)?.kind === "schedule");
        let foot = null;
        if (topicChip) { topicChip.click(); await new Promise(res => setTimeout(res, 50));
          foot = [...document.querySelectorAll("#dlgFoot button")].map(x => x.textContent); document.querySelector("#dlg").close(); }
        return { noToggle: document.querySelector("#calScopeWrap").hidden === true, chips: chips.length, foot };
      }, REC_OF);
      t.check("staff ไม่มีปุ่มสลับ และเห็นตารางรวม", r.noToggle && r.chips > 0, r.chips);
      t.check("staff ไม่เห็นปุ่ม 'แก้ไขรายการ' ในกล่อง", !!r.foot && !r.foot.includes("แก้ไขรายการ"), (r.foot || []).join(" / "));
      t.check("staff: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }

    /* ---------- resident: เปิดมาเห็นทั้งกลุ่มงาน สลับ "ของฉัน" แล้วเหลือแต่ของตัวเอง (และไม่มีช่องประจำ) ---------- */
    {
      const { page, errors } = await openAs(browser, srv.url, "resident");
      const r = await page.evaluate(async (recOfSrc) => {
        const recOf = new Function("return " + recOfSrc)();
        showView("calendar");
        const me = myResidentId();
        const anyOfMine = store.data.schedule.find(x => x.residentId === me) ||
          store.data.activities.find(x => x.residentId === me && ["traumafilm", "preop"].includes(x.type));
        if (anyOfMine) calMonth = anyOfMine.date.slice(0, 7);
        renderCalendar();
        const toggleShown = document.querySelector("#calScopeWrap").hidden === false;
        const defaultAll = document.querySelector("#calScopeAll").getAttribute("aria-current") === "true";
        const owners = [...document.querySelectorAll("#calGrid [data-pres]")].map(b => recOf(b)?.residentId);
        const seesOthers = owners.some(x => x && x !== me);
        /* กล่องของคนอื่น: ดูได้ แต่ไม่มีปุ่มเปิดกิจกรรม */
        const other = [...document.querySelectorAll("#calGrid [data-pres]")].find(b => { const rec = recOf(b); return rec?.kind === "activity" && rec.residentId !== me; });
        let otherFoot = null;
        if (other) { other.click(); await new Promise(res => setTimeout(res, 50));
          otherFoot = { open: document.querySelector("#dlg")?.open === true, foot: [...document.querySelectorAll("#dlgFoot button")].map(x => x.textContent) };
          document.querySelector("#dlg").close(); }
        document.querySelector("#calScopeMine").click();
        const mineRecs = [...document.querySelectorAll("#calGrid [data-pres]")].map(recOf);
        /* "ของฉัน" = ผู้นำเสนอ หรือ chief ผู้กำกับ / ผู้จัดร่วม */
        const mineOwners = mineRecs.filter(x => x?.kind !== "info").map(x => x?.chiefId === me || x?.coResidentId === me ? me : x?.residentId);
        const noSlotInMine = mineRecs.every(x => x?.kind !== "slot");
        /* กิจกรรมบังคับทั้งรุ่น: โผล่ใน "ของฉัน" ก็ต่อเมื่อชั้นปีของฉันต้องเข้า — ทดสอบทั้งสองทางด้วยการสลับชั้นปีของบัญชีนี้ */
        const mc = store.data.programme.morningConference;
        const myYear = +store.resident(me).year, ihYears = (mc.interHospital.years || []).map(Number);
        const infoWhenMine = (yrs) => { mc.interHospital.years = yrs; renderCalendar();
          return [...document.querySelectorAll("#calGrid [data-pres]")].some(b => recOf(b)?.kind === "info"); };
        const infoShownWhenMyYear = infoWhenMine([myYear]);
        const infoHiddenWhenOtherYear = !infoWhenMine([myYear === 4 ? 3 : 4]);
        mc.interHospital.years = ihYears; renderCalendar();
        /* chief ผู้กำกับเห็นแถวที่ตนกำกับใน "ของฉัน" ด้วย — ยืมแถว topic ของคนอื่นมาตั้ง chiefId = ฉัน */
        const otherTopic = store.data.schedule.find(x => x.type === "topic" && x.residentId !== me && x.date.slice(0, 7) === calMonth);
        let chiefSeen = null;
        if (otherTopic) {
          const keep = otherTopic.chiefId; otherTopic.chiefId = me; renderCalendar();
          chiefSeen = !!document.querySelector(`#calGrid [data-pres="schedule:${otherTopic.id}"]`);
          otherTopic.chiefId = keep; renderCalendar();
        }
        /* การประชุมภายนอกของ ส.ค. 2569 (ปี 4) โผล่ใน "ของฉัน" เฉพาะเมื่อฉันอยู่ปี 4 */
        const meRec = store.resident(me), keepYear = meRec.year;
        const extWhenYear = (y) => { meRec.year = y; calMonth = "2026-08"; renderCalendar();
          return [...document.querySelectorAll("#calGrid [data-pres]")].some(b => recOf(b)?.type === "external"); };
        const extShownY4 = extWhenYear(4), extHiddenY2 = !extWhenYear(2);
        meRec.year = keepYear; renderCalendar();
        return { hasMine: !!anyOfMine, toggleShown, defaultAll, seesOthers, mineN: mineOwners.length, allMine: mineOwners.every(x => x === me),
                 noSlotInMine, infoShownWhenMyYear, infoHiddenWhenOtherYear, otherFoot, chiefSeen, extShownY4, extHiddenY2 };
      }, REC_OF);
      t.check("resident: มีปุ่มสลับ และเปิดมาเป็น 'ทั้งกลุ่มงาน' ก่อน", r.toggleShown && r.defaultAll);
      t.check("resident: ตารางรวมเห็นของคนอื่นด้วย (ตารางนำเสนอเป็นของทั้งภาควิชา)", r.seesOthers);
      if (r.otherFoot) t.check("resident: เปิดกล่องของคนอื่นดูได้ แต่ไม่มีปุ่ม 'เปิดกิจกรรม'", r.otherFoot.open && !r.otherFoot.foot.includes("เปิดกิจกรรม"), r.otherFoot.foot.join(" / "));
      t.check("resident: กด 'ของฉัน' แล้วเหลือแต่ของตัวเอง ไม่มีช่องประจำเปล่าปน", r.hasMine && r.mineN > 0 && r.allMine && r.noSlotInMine, JSON.stringify(r));
      t.check("resident: Inter-hospital (บังคับทั้งรุ่น) โผล่ใน 'ของฉัน' เฉพาะเมื่อชั้นปีของฉันต้องเข้า", r.infoShownWhenMyYear && r.infoHiddenWhenOtherYear, JSON.stringify(r));
      t.check("resident: แถว Topic ที่ฉันเป็น chief ผู้กำกับ โผล่ใน 'ของฉัน'", r.chiefSeen === true, String(r.chiefSeen));
      t.check("resident: การประชุมภายนอกของปี 4 โผล่ใน 'ของฉัน' เฉพาะเมื่อฉันอยู่ปี 4", r.extShownY4 && r.extHiddenY2, JSON.stringify([r.extShownY4, r.extHiddenY2]));
      t.check("resident: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }

    /* ---------- เช้าวันพฤหัสฯ 4 ช่วง · ธีมรายสัปดาห์ · chief กำกับ · Kahoot quiz · Staff lecture · การประชุมภายนอก (ส.ค. 2569 ตามตารางจริง) ---------- */
    {
      const { page, errors } = await openAs(browser, srv.url, "admin");
      const r = await page.evaluate(async () => {
        const wait = (ms) => new Promise(res => setTimeout(res, ms));
        showView("calendar"); calMonth = "2026-08"; renderCalendar();
        const badges = [...document.querySelectorAll("#calGrid .gcal-week-sub:not(.holiday)")].slice(0, 4).map(b => b.textContent);
        const badgeIsButton = document.querySelector("#calGrid .gcal-week-sub:not(.holiday)")?.tagName === "BUTTON";
        /* 30 ก.ค. ที่ค้างอยู่หัวตารางเดือน ส.ค. ขึ้นป้ายวันหยุดแทนป้ายธีม */
        const holidayBadge = document.querySelector("#calGrid .gcal-week-sub.holiday")?.textContent || "";
        const seq = (d) => presentationsForDate(d).filter(p => p.kind !== "activity").map(p => p.kind + ":" + p.type);
        const aug6 = seq("2026-08-06"), aug13 = seq("2026-08-13");
        const t6 = presentationsForDate("2026-08-06").filter(p => p.type === "topic");
        const chiefNames = t6.map(p => [store.resident(p.residentId)?.name, store.resident(p.chiefId)?.name]);
        const chip6 = t6[0] ? document.querySelector(`#calGrid [data-pres="schedule:${t6[0].id}"] .nm`)?.textContent || "" : "";
        const quiz = presentationsForDate("2026-08-13").find(p => p.type === "quiz");
        const quizChip = quiz ? document.querySelector(`#calGrid [data-pres="schedule:${quiz.id}"] .nm`)?.textContent || "" : "";
        const lecture = presentationsForDate("2026-08-13").find(p => p.type === "lecture");
        const lectureChip = lecture ? document.querySelector(`#calGrid [data-pres="info:${lecture.id}"] .nm`)?.textContent || "" : "";
        const ext = ["2026-08-20", "2026-08-21", "2026-08-26", "2026-08-28"].map(d => presentationsForDate(d).filter(p => p.type === "external").map(p => p.title).join("|"));
        const noExt19 = presentationsForDate("2026-08-19").every(p => p.type !== "external");
        const note = document.querySelector(".gcal-month-note")?.textContent || "";
        /* ช่องเปล่าของพฤหัสฯ ข้างหน้า: T ×2 + J */
        let thu = addDaysISO(todayISO(), 1);
        while (new Date(thu + "T00:00:00").getDay() !== 4) thu = addDaysISO(thu, 1);
        store.data.schedule = store.data.schedule.filter(x => x.date !== thu);
        const emptyThu = presentationsForDate(thu).filter(p => p.kind === "slot").map(p => p.type + ":" + p.start);
        store.load();
        /* ผู้นำเสนอบันทึกแล้ว chief ได้ "กำกับการนำเสนอ" อัตโนมัติ */
        const open = store.data.schedule.find(t => t.date === "2026-08-27" && t.type === "topic" && !t.activityId && t.chiefId);
        let sup = null;
        if (open) {
          const before = store.data.activities.length;
          recordFromTalk(open.id);
          const chiefAct = store.data.activities.find(a => a.id === open.chiefActivityId);
          sup = { created: store.data.activities.length - before, chiefType: chiefAct?.type, chiefOwner: chiefAct?.residentId === open.chiefId,
                  status: talkStatus(open), linked: chiefAct?.scheduleId === open.id };
          store.data.activities = store.data.activities.filter(a => a.id !== open.activityId);
          sup.statusAfterDelete = talkStatus(open);
          store.load();
        }
        const quizActs = quiz ? { host: store.data.activities.some(a => a.id === quiz.activityId && a.type === "quiz"),
                                  co: (quiz.coResidentIds || []).length > 0 && (quiz.coResidentIds || []).every((rid, i) =>
                                    store.data.activities.some(a => a.id === (quiz.coActivityIds || [])[i] && a.type === "quiz" && a.residentId === rid)) } : null;
        /* กล่องจัดการวันพฤหัสฯ: เปลี่ยนช่วงเปิดเป็น Staff lecture */
        thursdayDialog("2026-08-06"); await wait(50);
        const dlgTitle = document.querySelector("#dlgTitle").textContent;
        const op = document.querySelector('#dlgBody [name="opening"]'); op.value = "lecture"; op.dispatchEvent(new Event("change"));
        const lectureFieldsShown = !document.querySelector("#dlgBody [data-lecture-only]").hidden;
        document.querySelector('#dlgBody [name="lectureTitle"]').value = "Pelvic ring injuries";
        document.querySelector("#dlgFoot .btn-primary").click(); await wait(100);
        const after6 = presentationsForDate("2026-08-06").find(p => p.kind === "info" && (p.type === "lecture" || p.type === "caseconf"));
        const row6 = store.data.topicConf.find(x => x.date === "2026-08-06");
        row6.theme = "Hand"; const themeOverride = thursdayThemeLabel("2026-08-06"); row6.theme = "";
        const themeAuto = thursdayThemeLabel("2026-08-06");
        store.load();
        /* การประชุมภายนอก: เพิ่มจากกล่อง แล้วขึ้นปฏิทินตามชั้นปี */
        externalConfsDialog(); await wait(50);
        const extRows = document.querySelectorAll("#dlgBody [data-ext-edit]").length;
        document.querySelector("#dlgFoot .btn-primary").click(); await wait(50);
        document.querySelector('#dlgBody [name="title"]').value = "Test Conf";
        document.querySelector('#dlgBody [name="start"]').value = "2026-08-03";
        document.querySelector('#dlgBody [name="end"]').value = "2026-08-04";
        document.querySelector('#dlgBody [name="years"]').value = "2";
        document.querySelector("#dlgFoot .btn-primary").click(); await wait(100);
        const added = store.data.externalConfs.find(x => x.title === "Test Conf");
        const addedShown = !!added && presentationsForDate("2026-08-04").some(p => p.type === "external" && p.extId === added.id) && JSON.stringify(added.years) === "[2]";
        store.load(); renderAll();
        /* ประเภทใหม่โผล่ในตารางความครอบคลุม */
        showView("coverage"); await wait(50);
        const covText = document.querySelector("#view-coverage")?.textContent || "";
        return { badges, badgeIsButton, aug6, aug13, chiefNames, chip6, quizChip, lectureChip, ext, noExt19, note, emptyThu, sup, quizActs,
                 holidayBadge, dlgTitle, lectureFieldsShown, after6: after6 && { type: after6.type, title: after6.title }, themeOverride, themeAuto, extRows, addedShown,
                 covHasQuiz: covText.includes("Kahoot quiz"), covHasSup: covText.includes("กำกับการนำเสนอ") };
      });
      t.eq("ป้ายธีม 4 สัปดาห์ของ ส.ค. 2569 ตรงตารางจริง (Trauma → Spine → Metabolic bone → Shoulder & Sports)", r.badges, ["Trauma", "Spine", "Metabolic bone", "Shoulder & Sports"]);
      t.check("admin: ป้ายธีมกดได้ (เปิดกล่องจัดการวันพฤหัสฯ)", r.badgeIsButton);
      t.eq("6 ส.ค.: Interesting case → Topic ×2 → Journal → Inter-hospital เรียงตามเวลา", r.aug6, ["info:caseconf", "schedule:topic", "schedule:topic", "schedule:journal", "info:interhospital"]);
      t.eq("13 ส.ค.: Staff lecture → Topic ×2 → Kahoot quiz (แทน Journal) → Inter-hospital", r.aug13, ["info:lecture", "schedule:topic", "schedule:topic", "schedule:quiz", "info:interhospital"]);
      t.eq("6 ส.ค. Topic แรก: ผู้นำเสนอ พัชรพล / chief ชญา", r.chiefNames[0], ["นพ. พัชรพล", "พญ. ชญา"]);
      t.check("chip T แสดงผู้นำเสนอและ chief คู่กัน", r.chip6.includes("พัชรพล") && r.chip6.includes("ชญา"), r.chip6);
      t.check("chip K แสดงผู้จัดทั้งสองคน (ฐาปกร / กนกขวัญ)", r.quizChip.includes("ฐาปกร") && r.quizChip.includes("กนกขวัญ"), r.quizChip);
      t.check("chip L บอกหัวข้อ Staff lecture และอาจารย์ (TL spine injuries · คงธัช)", r.lectureChip.includes("TL spine injuries") && r.lectureChip.includes("คงธัช"), r.lectureChip);
      t.eq("การประชุมภายนอกขึ้นทุกวันในช่วง (20–21 Regional Hand · 26–28 THOFAS) และไม่ขึ้นวันอื่น", [...r.ext, r.noExt19], ["Regional Hand", "Regional Hand", "THOFAS", "THOFAS", true]);
      t.check("หัวเดือนสรุปคนวนนอกสายและการประชุมภายนอก", r.note.includes("ศาศวัต") && r.note.includes("Elective") && r.note.includes("Regional Hand"), r.note);
      t.eq("พฤหัสฯ ที่ยังไม่ลงตารางมีช่องเปล่า T ×2 + J ตามเวลา 4 ช่วง", r.emptyThu, ["topic:09:00", "topic:10:00", "journal:11:00"]);
      t.check("ผู้นำเสนอบันทึกว่านำเสนอแล้ว → chief ได้กิจกรรม 'กำกับการนำเสนอ' อัตโนมัติ ผูกกับแถวเดียวกัน",
        !!r.sup && r.sup.created === 2 && r.sup.chiefType === "supervise" && r.sup.chiefOwner && r.sup.status === "done" && r.sup.linked, JSON.stringify(r.sup));
      t.check("ลบกิจกรรมของผู้นำเสนอแล้วสถานะแถวกลับเป็นยังไม่มีบันทึก (ไม่ค้าง)", r.sup?.statusAfterDelete === "missing", r.sup?.statusAfterDelete);
      t.check("Kahoot quiz: ผู้จัดทั้งสองคนมีกิจกรรมประเภท quiz คนละชุด", !!r.quizActs && r.quizActs.host && r.quizActs.co, JSON.stringify(r.quizActs));
      t.check("กล่องจัดการวันพฤหัสฯ: เลือก Staff lecture แล้วช่องหัวข้อ/อาจารย์โผล่ บันทึกแล้ว chip C กลายเป็น L",
        r.dlgTitle.startsWith("จัดการเช้าวันพฤหัสฯ") && r.lectureFieldsShown && r.after6?.type === "lecture" && r.after6?.title === "Pelvic ring injuries", JSON.stringify([r.dlgTitle, r.after6]));
      t.check("วันพฤหัสฯ ที่เป็นวันหยุดขึ้นป้ายวันหยุดแทนป้ายธีม", /วันเข้าพรรษา/.test(r.holidayBadge), r.holidayBadge);
      t.check("ธีมกำหนดทับรายสัปดาห์ได้ และกลับมาวนตามรอบเมื่อล้าง", r.themeOverride === "Hand" && r.themeAuto === "Trauma", r.themeOverride + "/" + r.themeAuto);
      t.check("กล่องการประชุมภายนอก: มี 4 รายการจากตารางจริง (Regional Hand · THOFAS · KOKU · RCOST) เพิ่มรายการใหม่ (ปี 2) แล้วขึ้นปฏิทินทุกวันในช่วง",
        r.extRows === 4 && r.addedShown, r.extRows + " " + r.addedShown);
      t.check("ประเภทใหม่ Kahoot quiz / กำกับการนำเสนอ โผล่ในหน้าความครอบคลุม", r.covHasQuiz && r.covHasSup);
      t.check("เช้าวันพฤหัสฯ: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }

    /* ---------- ตารางกิจกรรมจริง ก.ค.–ต.ค. 2569: คาบแรก 4 แบบ · จำนวนหัวข้อไม่คงที่ · quiz หลายผู้จัด ·
                  งานเต็มเช้า · วันหยุดเฉพาะวัน · ลงชื่อเข้าร่วม ---------- */
    {
      const { page, errors } = await openAs(browser, srv.url, "admin");
      const r = await page.evaluate(async () => {
        const wait = (ms) => new Promise(res => setTimeout(res, ms));
        const at = (iso) => presentationsForDate(iso);
        const sig = (iso) => at(iso).map(p => p.kind + "/" + p.type).join(" ");
        /* 16 ก.ค. คาบแรกเป็นหัวข้อของ resident → มี topic 3 ช่อง และ quiz มีผู้จัดสามคน */
        const jul16 = at("2026-07-16");
        const quiz16 = jul16.find(p => p.type === "quiz");
        const hosts16 = [quiz16?.residentId, ...(quiz16?.coResidentIds || [])].filter(Boolean).length;
        const jul16Topics = jul16.filter(p => p.type === "topic").map(p => p.start);
        const noOpeningInfo = !jul16.some(p => p.kind === "info" && ["caseconf", "lecture", "pedconf"].includes(p.type));
        /* 23 ก.ค. คาบแรกเป็น Pediatric inter-hospital conference */
        const ped = at("2026-07-23").find(p => p.kind === "info" && p.type === "pedconf");
        /* 1 ต.ค. ไม่มีหัวข้อ เหลือ case conference + ช่อง Journal */
        const oct1 = sig("2026-10-01");
        /* 30 ก.ค. วันหยุด → ไม่มีอะไรเลย */
        const jul30 = at("2026-07-30").length, jul30Note = dayNote("2026-07-30");
        /* 17 ก.ย. KOKU และ 15/29 ต.ค. งานของกลุ่มงาน → แทน 4 คาบทั้งหมด */
        const koku = at("2026-09-17").map(p => p.type);
        const oct15 = at("2026-10-15").map(p => p.type);
        const oct29 = at("2026-10-29").find(p => p.type === "interdept");
        const oct29Sessions = (store.data.thursdayEvents.find(e => e.date === "2026-10-29")?.sessions || []).length;
        /* ผู้จัด quiz ทุกคนได้กิจกรรม quiz คนละชุดเมื่อผู้จัดหลักบันทึก */
        const row = store.data.schedule.find(t => t.date === "2026-07-16" && t.type === "quiz");
        row.activityId = null;
        recordFromTalk(row.id); await wait(60);
        const after = store.data.schedule.find(t => t.id === row.id);
        const quizActs = (after.coResidentIds || []).every((rid, i) =>
          store.data.activities.some(a => a.id === (after.coActivityIds || [])[i] && a.type === "quiz" && a.residentId === rid));
        /* ติ๊กวันหยุดจากกล่องจัดการวันพฤหัสฯ (เลือก 1 ต.ค. ที่ยังไม่มีแถวลงตาราง) */
        thursdayDialog("2026-10-01"); await wait(50);
        const hol = document.querySelector('#dlgBody [name="holiday"]');
        hol.checked = true; hol.dispatchEvent(new Event("change"));
        document.querySelector('#dlgBody [name="holidayNote"]').value = "ทดสอบวันหยุด";
        document.querySelector("#dlgFoot .btn-primary").click(); await wait(100);
        const sep3After = at("2026-10-01").length, sep3Note = dayNote("2026-10-01");
        return { hosts16, jul16Topics, noOpeningInfo, pedOk: !!ped, oct1, jul30, jul30Note,
                 koku, oct15, oct29: oct29?.title || "", oct29Sessions, quizActs, sep3After, sep3Note };
      });
      t.eq("16 ก.ค. คาบแรกเป็นหัวข้อของ resident → มีช่อง Topic สามช่องตั้งแต่ 08:00", r.jul16Topics, ["08:00", "09:00", "10:00"]);
      t.check("สัปดาห์นั้นไม่มีรายการช่วงเปิดของอาจารย์ซ้อน", r.noOpeningInfo);
      t.eq("Kahoot quiz 16 ก.ค. มีผู้จัดสามคน", r.hosts16, 3);
      t.check("ผู้จัดร่วมทุกคนได้กิจกรรม Kahoot quiz คนละชุด", r.quizActs);
      t.check("23 ก.ค. คาบแรกเป็น Pediatric inter-hospital conference", r.pedOk);
      t.eq("1 ต.ค. ไม่มีหัวข้อ เหลือ Interesting case + ช่อง Journal", r.oct1, "info/caseconf slot/journal info/interhospital");
      t.check("30 ก.ค. วันหยุดนักขัตฤกษ์: ไม่มีกิจกรรมเลย และมีป้ายวันหยุด",
        r.jul30 === 0 && /วันเข้าพรรษา/.test(r.jul30Note), r.jul30 + " " + r.jul30Note);
      t.eq("17 ก.ย. KOKU 2026 แทนทั้งวัน", r.koku, ["external"]);
      t.eq("15 ต.ค. Sport PE Workshop แทนทั้งเช้า (บ่ายยังมี Inter-hospital ตามปกติ)", r.oct15, ["workshop", "interhospital"]);
      t.check("29 ต.ค. ประชุมร่วมต่างภาควิชา มีช่วงย่อยสี่ช่วง",
        /Ortho-Rehab-Anes/.test(r.oct29) && r.oct29Sessions === 4, r.oct29 + " " + r.oct29Sessions);
      t.check("ติ๊กวันหยุดในกล่องจัดการวันพฤหัสฯ แล้วกิจกรรมของวันนั้นหายหมด",
        r.sep3After === 0 && /ทดสอบวันหยุด/.test(r.sep3Note), r.sep3After + " " + r.sep3Note);
      t.check("ตารางจริงสี่เดือน: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }

    /* ---------- ลงชื่อเข้าร่วมงานเต็มวัน = กิจกรรม attend ที่ไม่มีแบบประเมิน ---------- */
    {
      const { page, errors } = await openAs(browser, srv.url, "resident");
      const r = await page.evaluate(async () => {
        const wait = (ms) => new Promise(res => setTimeout(res, ms));
        calMonth = "2026-10"; showView("calendar"); renderCalendar();
        const chip = [...document.querySelectorAll("#calGrid [data-pres]")].find(b => /^info:thev:/.test(b.dataset.pres));
        if (!chip) return { none: true };
        chip.click(); await wait(60);
        const foot = () => [...document.querySelectorAll("#dlgFoot button")].map(b => b.textContent);
        const first = foot();
        document.querySelector("#dlgFoot button").click(); await wait(120);
        const acts = store.data.activities.filter(a => a.type === "attend");
        openActivity(acts[0].id); await wait(80);
        const noForm = !document.querySelector("#dlgBody .scale-pick");
        const note = /ไม่มีแบบประเมิน/.test(document.querySelector("#dlgBody").textContent || "");
        document.querySelector("#dlg").close();
        const inQueue = talksToAssess().some(a => a.type === "attend");
        /* กดซ้ำ = ยกเลิก */
        chip.click(); await wait(60);
        const second = foot();
        document.querySelector("#dlgFoot button").click(); await wait(120);
        return { first, second, made: acts.length, mine: acts[0]?.residentId === myResidentId(),
                 noForm, note, inQueue, left: store.data.activities.filter(a => a.type === "attend").length };
      });
      if (r.none) t.check("ไม่มีงานเต็มเช้าในเดือนนี้ให้ทดสอบ", false);
      else {
        t.check("resident เห็นปุ่มลงชื่อเข้าร่วม", r.first[0] === "ลงชื่อเข้าร่วม", JSON.stringify(r.first));
        t.check("ลงชื่อแล้วได้กิจกรรม attend ของตัวเองหนึ่งชุด", r.made === 1 && r.mine, r.made + " " + r.mine);
        t.check("กิจกรรม attend ไม่มีแบบประเมิน และไม่เข้าคิวประเมิน", r.noForm && r.note && !r.inQueue,
          JSON.stringify([r.noForm, r.note, r.inQueue]));
        t.check("กดซ้ำแล้วยกเลิกการลงชื่อได้", r.second[0] === "ยกเลิกการลงชื่อ" && r.left === 0, JSON.stringify([r.second, r.left]));
      }
      t.check("ลงชื่อเข้าร่วม: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
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
