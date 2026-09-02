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
  if (kind === "slot" || kind === "info") return { kind, type: id.slice(0, id.indexOf(":")), date: id.slice(id.indexOf(":") + 1), residentId: "" };
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
        /* พฤหัสฯ ไม่มีช่อง F/P */
        let thu = addDaysISO(todayISO(), 1);
        while (new Date(thu + "T00:00:00").getDay() !== 4) thu = addDaysISO(thu, 1);
        const thuSlots = presentationsForDate(thu).filter(p => p.kind === "slot").length;
        /* บ่ายพฤหัสฯ มี Inter-hospital conference แสดงเฉย ๆ (kind "info") ไม่มีผู้นำเสนอ */
        const thuInfo = presentationsForDate(thu).filter(p => p.kind === "info");
        const infoOk = thuInfo.length === 1 && thuInfo[0].type === "interhospital" && thuInfo[0].start === "13:00" && !thuInfo[0].residentId;
        const infoOnlyThu = presentationsForDate(iso).every(p => p.kind !== "info");

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
        const fullName = named.length > 0 && named.every(b => {
          const rec = recOf(b); return b.querySelector(".nm")?.textContent === store.resident(rec.residentId)?.name;
        });
        const titled = named.filter(b => recOf(b)?.title).every(b => !!b.querySelector(".ttl"));
        const slotChips = chips.filter(b => recOf(b)?.kind === "slot");
        const slotLabelOk = slotChips.length > 0 && slotChips.every(b => b.classList.contains("slot") &&
          /ยังไม่ระบุผู้นำเสนอ|ไม่มีสไลด์ส่ง/.test(b.querySelector(".nm")?.textContent || ""));
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
        const infoChip = chips.find(b => recOf(b)?.kind === "info");
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
      t.eq("วันพฤหัสบดีไม่มีช่อง F/P (เป็น Topic/Journal ที่ลงตารางล่วงหน้า)", r.thuSlots, 0);
      t.check("บ่ายพฤหัสฯ มี Inter-hospital conference แสดงเฉย ๆ 13:00 ไม่มีผู้นำเสนอ และไม่โผล่วันอื่น", r.infoOk && r.infoOnlyThu);
      t.check("กด I: กล่องบอกว่าแสดงเฉย ๆ ไม่มีการประเมิน และไม่มีปุ่มทำอะไร",
        !!r.info && r.info.title === "กิจกรรมประจำ" && r.info.noEval && r.info.foot.length === 1, JSON.stringify(r.info));
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
        const mineOwners = [...document.querySelectorAll("#calGrid [data-pres]")].map(b => recOf(b)?.residentId);
        return { hasMine: !!anyOfMine, toggleShown, defaultAll, seesOthers, mineN: mineOwners.length, allMine: mineOwners.every(x => x === me), otherFoot };
      }, REC_OF);
      t.check("resident: มีปุ่มสลับ และเปิดมาเป็น 'ทั้งกลุ่มงาน' ก่อน", r.toggleShown && r.defaultAll);
      t.check("resident: ตารางรวมเห็นของคนอื่นด้วย (ตารางนำเสนอเป็นของทั้งภาควิชา)", r.seesOthers);
      if (r.otherFoot) t.check("resident: เปิดกล่องของคนอื่นดูได้ แต่ไม่มีปุ่ม 'เปิดกิจกรรม'", r.otherFoot.open && !r.otherFoot.foot.includes("เปิดกิจกรรม"), r.otherFoot.foot.join(" / "));
      t.check("resident: กด 'ของฉัน' แล้วเหลือแต่ของตัวเอง ไม่มีช่องประจำเปล่าปน", r.hasMine && r.mineN > 0 && r.allMine, JSON.stringify(r));
      t.check("resident: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
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
