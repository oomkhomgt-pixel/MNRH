/* ตารางเวรมีสามชั้นซ้อนกัน: ส่วนกลางของภาควิชา · หน่วยที่วนอยู่ · สายที่ยังสังกัด
   ชุดนี้ตรวจว่าเวลามันชนกัน ระบบตัดสินถูกและไม่ตัดสินมั่วเมื่อตัดสินไม่ได้ */
import { chromium } from "playwright";
import { serve, launchOptions, openAs, suite } from "./lib.mjs";

export default async function run() {
  const t = suite("ตารางส่วนกลางและการชนกันของคาบ");
  const srv = await serve();
  const browser = await chromium.launch(launchOptions());
  try {
    const { page, errors } = await openAs(browser, srv.url, "admin");

    /* ---------- ตารางส่วนกลางใช้กับทุกคน ไม่ว่าอยู่หน่วยไหน ---------- */
    const central = await page.evaluate(() => {
      const cs = store.data.services.find(x => x.central);
      const day = cs.template[0].day;
      let iso = todayISO();
      while (new Date(iso + "T00:00:00").getDay() !== day) iso = addDaysISO(iso, 1);
      const all = sessionsForDate(iso).filter(s => s.kind === "central" && s.name === cs.template[0].name);
      /* คาบของอาจารย์ล้วนต้องไม่สร้างคาบให้แพทย์ประจำบ้านเลย — ทดสอบที่ตัวกลไก */
      cs.template.push({ day: cs.template[0].day, part:"pm", name:"คลินิกของอาจารย์ล้วน",
                         start:"14:00", end:"15:00", staffIds:[], years:[], whenAway:true, staffOnly:true });
      const staffOnlyHidden = !sessionsForDate(iso).some(s => s.name === "คลินิกของอาจารย์ล้วน");
      cs.template.pop();
      /* หนึ่งคาบมีอาจารย์ได้หลายคน — ทดสอบที่ตัวกลไก ไม่ผูกกับว่าข้อมูลจริงมีหรือไม่ */
      const two = store.data.staff.slice(0, 2).map(x => x.id);
      cs.template.push({ day: cs.template[0].day, part:"am", name:"ทดสอบอาจารย์หลายคน",
                         start:"06:00", end:"06:30", staffIds: two, years:[], whenAway:true });
      const multi = sessionsForDate(iso).find(s => s.name === "ทดสอบอาจารย์หลายคน")?.staffIds.length ?? 0;
      cs.template.pop();
      return { name: cs.name, gotIt: all.length, residents: store.data.residents.length,
               staffOnlyHidden, multiStaff: multi, multiNames: two.length };
    });
    t.check("มีตารางส่วนกลางของภาควิชาในข้อมูล", !!central.name, central.name);
    t.eq("คาบส่วนกลางเกิดกับแพทย์ประจำบ้านทุกคน", central.gotIt, central.residents);
    t.check("คลินิกของอาจารย์ล้วน ไม่สร้างคาบให้แพทย์ประจำบ้าน",
            central.staffOnlyHidden === true, String(central.staffOnlyHidden));
    t.check("หนึ่งคาบมีอาจารย์ได้หลายคน", central.multiStaff > 1, central.multiStaff + " คน");

    /* ---------- คาบส่วนกลางเฉพาะบางชั้นปี ---------- */
    const years = await page.evaluate(() => {
      const cs = store.data.services.find(x => x.central);
      const row = cs.template.find(x => x.years?.length);
      if (!row) return null;
      let iso = todayISO();
      while (new Date(iso + "T00:00:00").getDay() !== row.day) iso = addDaysISO(iso, 1);
      const got = sessionsForDate(iso).filter(s => s.name === row.name);
      return { forYears: row.years, yearsSeen: [...new Set(got.map(s => store.resident(s.residentId)?.year))] };
    });
    t.check("คาบที่จัดเฉพาะบางชั้นปี ไม่ไปโผล่กับชั้นปีอื่น",
            !years || years.yearsSeen.every(y => years.forYears.includes(y)),
            years ? "จัดให้ปี " + years.forYears + " · เห็นที่ปี " + years.yearsSeen : "ไม่มีข้อมูลสาธิต");

    /* ---------- คาบที่ระบุเวลาไม่ถือว่าชนกับคาบที่ใช้ทั้งช่วง ---------- */
    const noFalseClash = await page.evaluate(() => {
      const bad = [];
      for (let i = 0; i < 14; i++) {
        const list = sessionsForDate(addDaysISO(todayISO(), i));
        list.filter(s => s.start && s.end && (s.superseded || s.clash)).forEach(s => {
          /* ชนกับคาบที่ระบุเวลาด้วยกันถือว่าจริง — ที่ต้องไม่เกิดคือชนกับงานเต็มวันที่ไม่ระบุเวลา */
          const against = (s.overlaps || []).map(nm => list.find(x => x.name === nm && x.residentId === s.residentId));
          if (against.some(x => x && !(x.start && x.end))) bad.push(s.name + " ↔ " + s.overlaps.join("/"));
        });
      }
      return bad;
    });
    t.eq("คาบที่ระบุเวลาไว้ ไม่ขึ้นว่าชนกับงานเต็มวัน", noFalseClash.length, 0);

    /* ---------- วนหน่วยอนุสาขา = ตามลิสต์ของอนุสาขาตัวเองในทุกสาย ---------- */
    const sub = await page.evaluate(() => {
      const rot = store.data.rotations.find(r => serviceById(r.serviceId)?.subUnit);
      if (!rot) return null;
      const svc = serviceById(rot.serviceId);
      const seen = new Set(), clashes = [];
      for (let i = 0; i < 7; i++)
        sessionsForDate(addDaysISO(rot.start, i))
          .filter(s => s.residentId === rot.residentId && s.kind === "team")
          .forEach(s => { seen.add(s.serviceId); if (s.clash || s.superseded) clashes.push(s.name); });
      return { unit: svc.name, wants: svc.subspecialties, teamsSeen: seen.size,
               emptyTemplate: (svc.template || []).length === 0, clashes: clashes.length };
    });
    t.check("หน่วยอนุสาขาไม่มีตารางของตัวเอง", sub?.emptyTemplate === true, sub?.unit);
    t.check("คนวน sub ได้ลิสต์ของอนุสาขาตัวเองจากหลายสาย", (sub?.teamsSeen ?? 0) > 1,
            sub ? sub.teamsSeen + " สาย · " + sub.wants.join("/") : "ไม่มีข้อมูล");
    t.check("วันที่มีลิสต์อนุสาขาเดียวกันสองสาย ขึ้นว่าต้องเลือกเอง", (sub?.clashes ?? 0) > 0,
            (sub?.clashes ?? 0) + " คาบ");

    /* ---------- คาบที่แพ้ ไม่ถูกนับเป็นงานค้างประเมิน ---------- */
    t.check("คาบที่แพ้ไม่กลายเป็นงานค้างของอาจารย์", await page.evaluate(() =>
      pendingEvaluations(30).every(s => !s.superseded)));

    /* ---------- กิจกรรมวิชาการมาก่อนงานบริการเสมอ ---------- */
    const academic = await page.evaluate(() => {
      const cs = store.data.services.find(x => x.central);
      const row = cs.template.find(t => t.academic);
      let iso = todayISO();
      while (new Date(iso + "T00:00:00").getDay() !== row.day) iso = addDaysISO(iso, 1);
      const r = store.data.residents.find(x => !row.years?.length || row.years.includes(x.year));
      const ses = sessionsForDate(iso).find(s => s.residentId === r.id && s.name === row.name);
      /* ตั้งใจให้ชนกับคาบวิชาการ แล้วดูว่าใครแพ้ */
      cs.template.push({ day: row.day, part: row.part, name:"งานบริการซ้อนเวลาวิชาการ",
                         start: row.start, end: row.end, staffIds:[], years:[], whenAway:true });
      const after = sessionsForDate(iso).filter(s => s.residentId === r.id);
      const acad = after.find(s => s.name === row.name);
      const other = after.find(s => s.name === "งานบริการซ้อนเวลาวิชาการ");
      cs.template.pop();
      return { flagged: ses?.academic === true, prio: ses?.priority,
               acadKept: acad && !acad.superseded, otherLost: other?.superseded === true };
    });
    t.check("คาบวิชาการถูกทำเครื่องหมายไว้ และได้ลำดับสูงสุด", academic.flagged && academic.prio === 40,
            "ลำดับ " + academic.prio);
    t.check("งานบริการที่ซ้อนเวลากิจกรรมวิชาการเป็นฝ่ายแพ้", academic.acadKept && academic.otherLost);

    /* ---------- ตารางส่วนกลางไม่ใช่หน่วยที่ใครไปประจำ ---------- */
    t.check("ตารางส่วนกลางไม่อยู่ในตัวเลือกของช่วงหมุนเวียน", await page.evaluate(() =>
      rotatableServices().every(x => !x.central) && store.data.services.some(x => x.central)));
    t.check("ตัวจัดแผนหมุนเวียนไม่เอาคนไปลงตารางส่วนกลาง", await page.evaluate(() => {
      const plan = buildRotationPlan(currentAY(), store.data.residents, store.data.services);
      return plan.rotations.every(r => !serviceById(r.serviceId)?.central);
    }));

    /* ---------- การเลือกรายวันตัดสินคาบที่ลำดับเท่ากัน ---------- */
    const picked = await page.evaluate(() => {
      const rot = store.data.rotations.find(r => serviceById(r.serviceId)?.subUnit);
      let iso = null, a = null, b = null;
      for (let i = 0; i < 7 && !a; i++) {
        const day = addDaysISO(rot.start, i);
        const list = sessionsForDate(day).filter(s => s.residentId === rot.residentId && s.clash);
        if (list.length >= 2) { iso = day; a = list[0]; b = list.find(x => x.key !== a.key); }
      }
      if (!a) return null;
      const staffId = store.data.staff[0].id;
      store.data.sessionPicks.push({ id: uid("pick"), residentId: a.residentId, date: iso,
        part: a.part, key: a.key, staffId, at: new Date().toISOString(), by: "test" });
      const after = sessionsForDate(iso).filter(s => s.residentId === a.residentId);
      const mine = after.find(s => s.key === a.key);
      const theirs = after.find(s => s.key === b.key);
      const other = sessionsForDate(addDaysISO(iso, 7)).filter(s => s.residentId === a.residentId);
      store.data.sessionPicks = [];
      return { chosen: mine?.picked === true && !mine?.superseded,
               otherLost: theirs?.superseded === true,
               byPick: theirs?.supersededByPick === true,
               staffOverridden: mine?.staffIds?.[0] === staffId,
               otherDayUntouched: other.every(s => !s.picked) };
    });
    t.check("มีวันที่ต้องเลือกเองจริงในข้อมูล", picked !== null);
    t.check("บันทึกรายวันแล้ว คาบที่เลือกกลายเป็นตัวหลัก", picked?.chosen === true);
    t.check("อีกคาบที่ชนกันกลายเป็นไม่ได้เข้าในวันนั้น", picked?.otherLost === true);
    t.check("บอกได้ว่าที่แพ้เพราะคนเลือกเอง ไม่ใช่เพราะลำดับความสำคัญ", picked?.byPick === true);
    t.check("ระบุอาจารย์ของวันนั้นทับค่าในตารางได้", picked?.staffOverridden === true);
    t.check("การเลือกมีผลเฉพาะวันนั้น ไม่ลามไปสัปดาห์อื่น", picked?.otherDayUntouched === true);

    /* ---------- ตารางเวรรายเดือน: ของที่ไม่ซ้ำทุกสัปดาห์ ---------- */
    const duty = await page.evaluate(() => {
      store.data.duty = [];
      dutyMonth = "2026-08"; renderDutyTable();
      document.querySelector("#dutyFill").click();
      const rows = store.data.duty.filter(d => d.date.startsWith("2026-08"));
      const mon = rows.find(d => d.date === "2026-08-03");
      const thu = rows.find(d => d.date === "2026-08-06");
      return { filled: rows.length,
               monOpd: serviceById(mon?.opdServiceId)?.abbr || "",
               monEr: serviceById(mon?.erServiceId)?.abbr || "",
               thursdayLeftBlank: !thu };
    });
    t.check("เติมเดือนจากรูปแบบประจำสัปดาห์ได้", duty.filled > 0, duty.filled + " วัน");
    t.check("วันจันทร์ได้ OPD กับ ER ตรงกับตารางของสาย", duty.monOpd === "ฟ้า" && duty.monEr === "แดง",
            "OPD " + duty.monOpd + " · ER " + duty.monEr);
    t.check("วันพฤหัสบดีไม่ถูกเดาให้ เพราะไม่มีรูปแบบตายตัว", duty.thursdayLeftBlank);

    const erDay = await page.evaluate(() => {
      const white = store.data.services.find(x => x.abbr === "ขาว");
      const team = store.data.residents.filter(x => rotationOn(x.id, "2026-08-06")?.serviceId === white.id);
      const row = dutyRow("2026-08-06");
      row.erServiceId = white.id;
      row.erStaffIds = [store.data.staff[0].id];
      row.erResidentIds = [];
      const all = sessionsForDate("2026-08-06");
      const mine = (rid) => all.filter(s => s.residentId === rid);
      const junior = team.slice().sort((a, b) => a.year - b.year)[0];
      const er = all.find(s => s.kind === "duty");
      return { teamSize: team.length,
               everyoneOnEr: team.every(r => mine(r.id).some(s => s.kind === "duty")),
               frontlineIsJunior: all.filter(s => s.frontline).every(s => s.residentId === junior.id),
               frontlineCount: all.filter(s => s.frontline).length,
               juniorYear: junior.year,
               staff: er?.staffIds.length ?? 0,
               nobodyLosesTheatre: team.every(r => mine(r.id).every(s => !s.superseded && !s.clash)) };
    });
    t.check("ER ในเวลาเป็นความรับผิดชอบของทั้งสาย", erDay.everyoneOnEr, erDay.teamSize + " คน");
    t.check("หน้างานเป็นคนที่ชั้นปีน้อยที่สุด และมีคนเดียว",
            erDay.frontlineIsJunior && erDay.frontlineCount === 1, "ปี " + erDay.juniorYear);
    t.check("อาจารย์ผู้รับผิดชอบของวันนั้นติดมากับคาบ", erDay.staff === 1);
    t.check("คาบ ER เป็นการบอกหน้าที่ ไม่ดึงใครออกจากห้องผ่าตัด", erDay.nobodyLosesTheatre);

    /* วันหยุดลบเฉพาะคาบที่มาจากตารางประจำสัปดาห์ ส่วนที่ตารางเวรระบุไว้เองยังอยู่
       เพราะวันหยุดก็ยังต้องมีคนอยู่เวร */
    const holiday = await page.evaluate(() => {
      const kinds = (iso) => [...new Set(sessionsForDate(iso).map(s => s.kind))].sort();
      const before = kinds("2026-08-12");
      const row = dutyRow("2026-08-12");
      row.holiday = true;
      const withDuty = kinds("2026-08-12");
      row.erServiceId = ""; row.erResidentIds = [];
      const bare = sessionsForDate("2026-08-12").length;
      return { before, withDuty, bare };
    });
    t.check("ก่อนตั้งวันหยุด วันนั้นมีคาบตามตารางประจำสัปดาห์",
            holiday.before.some(k => k === "team" || k === "central"), holiday.before.join(","));
    t.check("ตั้งวันหยุดแล้ว เหลือเฉพาะสิ่งที่ตารางเวรระบุไว้เอง",
            holiday.withDuty.every(k => k === "duty"), holiday.withDuty.join(",") || "(ไม่เหลืออะไร)");
    t.eq("วันหยุดที่ไม่ได้ระบุเวรไว้ ไม่มีคาบเลย", holiday.bare, 0);

    /* ---------- อาจารย์แลกวัน OR กัน ----------
       จุดที่พลาดง่ายคือไปแก้ตารางประจำสัปดาห์ ซึ่งจะเปลี่ยนทั้งปีและทำให้ประวัติผิดย้อนหลัง
       การแลกจึงต้องมีผลเฉพาะวันนั้น และต้องไม่ทำให้ผลประเมินที่ทำไว้แล้วหลุดจากคาบ */
    const swap = await page.evaluate(() => {
      store.data.swaps = [];
      let target = null;
      for (let i = 0; i < 14 && !target; i++) {
        const iso = addDaysISO(todayISO(), -i);
        const ses = sessionsForDate(iso).find(x => (x.staffIds || []).length && x.kind === "team");
        if (ses) target = ses;
      }
      if (!target) return { none: true };
      const other = store.data.staff.find(x => x.id !== target.staffIds[0]);
      const at = (iso, key) => sessionsForDate(iso).find(x => x.key === key);
      const nextWeek = addDaysISO(target.date, 7);
      const sameSlotNextWeek = sessionsForDate(nextWeek).find(x => x.name === target.name &&
        x.part === target.part && x.serviceId === target.serviceId);
      const before = { label: sessionStaffLabel(target), nextWeek: sameSlotNextWeek ? sessionStaffLabel(sameSlotNextWeek) : "" };

      /* คำขอที่ยังไม่ตอบรับต้องไม่เปลี่ยนตาราง */
      store.data.swaps.push({ id: "sw_test", date: target.date, part: "", serviceId: "", pairId: "p_test",
        fromStaffId: target.staffIds[0], toStaffId: other.id, note: "ทดสอบ", returnDate: "", status: "pending" });
      const whilePending = at(target.date, target.key);
      const pendingLabel = whilePending ? sessionStaffLabel(whilePending) : "";
      store.data.swaps[0].status = "accepted";

      const now = at(target.date, target.key);
      const nw = sessionsForDate(nextWeek).find(x => x.name === target.name &&
        x.part === target.part && x.serviceId === target.serviceId);
      store.data.swaps = [];
      return {
        date: target.date, name: target.name,
        beforeLabel: before.label, afterLabel: now ? sessionStaffLabel(now) : "",
        keySurvived: !!now,
        subs: now?.subs?.length || 0,
        nextWeekBefore: before.nextWeek, nextWeekAfter: nw ? sessionStaffLabel(nw) : "",
        pendingLabel
      };
    });
    t.eq("คำขอที่ยังไม่ตอบรับ ตารางยังเป็นชื่อเดิม", swap.pendingLabel, swap.beforeLabel);
    t.check("ตอบรับแล้ว ชื่อผู้รับผิดชอบของวันนั้นเปลี่ยน",
            swap.afterLabel !== swap.beforeLabel, swap.beforeLabel + " → " + swap.afterLabel);
    t.check("บอกด้วยว่ามาแทนใคร ไม่ใช่เปลี่ยนชื่อเงียบ ๆ",
            swap.afterLabel.includes("แทน") && swap.subs > 0, swap.afterLabel);
    t.check("รหัสคาบไม่เปลี่ยน — ผลประเมินที่ทำไว้แล้วยังผูกอยู่กับคาบเดิม", swap.keySurvived);
    t.eq("สัปดาห์ถัดไปยังเป็นอาจารย์คนเดิม — การแลกไม่ลามไปทั้งปี",
         swap.nextWeekAfter, swap.nextWeekBefore);

    /* เส้นทางจริง: ขอ → รอตอบ → ตอบรับ แล้วอีกฝั่งของการแลกจึงเกิด
       ก่อนตอบรับต้องยังไม่มีอะไรไปแตะวันแลกกลับ เพราะยังไม่มีการแลกเกิดขึ้นจริง */
    const pair = await page.evaluate(async () => {
      store.data.swaps = [];
      const iso = todayISO(), back = addDaysISO(iso, 7);
      const a = store.data.staff[0].id, b = store.data.staff[1].id;
      const realConfirm = window.confirm; window.confirm = () => true;
      openSwap(iso, a, "", "");
      document.querySelector('#dlgBody [name="toStaffId"]').value = b;
      document.querySelector('#dlgBody [name="returnDate"]').value = back;
      [...document.querySelectorAll("#dlgFoot button")].find(x => x.textContent.includes("ส่งคำขอ")).click();
      document.querySelector("#dlg").close();
      const afterRequest = store.data.swaps.map(x => [x.date, x.fromStaffId, x.toStaffId, x.status].join(">"));
      decideSwap(store.data.swaps[0].id, true);
      window.confirm = realConfirm;
      const afterAccept = store.data.swaps.map(x => [x.date, x.fromStaffId, x.toStaffId, x.status].join(">"));
      store.data.swaps = [];
      return { afterRequest, afterAccept,
               wantRequest: [[iso, a, b, "pending"].join(">")],
               wantAccept: [[iso, a, b, "accepted"].join(">"), [back, b, a, "accepted"].join(">")] };
    });
    t.eq("ส่งคำขอแล้วได้รายการเดียวที่ยังรอตอบรับ ยังไม่แตะวันแลกกลับ",
         pair.afterRequest, pair.wantRequest);
    t.eq("ตอบรับแล้วอีกฝั่งของการแลกถูกสร้างให้เอง", pair.afterAccept, pair.wantAccept);

    /* แพทย์ประจำบ้านไม่ย้ายตามอาจารย์ที่แลกวัน — อยู่กับสายของตัวเองเสมอ */
    const stay = await page.evaluate(() => {
      store.data.swaps = [];
      let target = null;
      for (let i = 0; i < 14 && !target; i++) {
        const iso = addDaysISO(todayISO(), -i);
        const ses = sessionsForDate(iso).find(x => (x.staffIds || []).length && x.kind === "team" && x.residentId);
        if (ses) target = ses;
      }
      if (!target) return { none: true };
      const other = store.data.staff.find(x => x.id !== target.staffIds[0]);
      const who = (iso) => sessionsForDate(iso).filter(x => x.serviceId === target.serviceId)
        .map(x => x.residentId).sort();
      const before = who(target.date);
      store.data.swaps.push({ id:"sw_stay", pairId:"p_stay", date: target.date, part:"", serviceId:"",
        fromStaffId: target.staffIds[0], toStaffId: other.id, status:"accepted", note:"", returnDate:"" });
      const after = who(target.date);
      store.data.swaps = [];
      return { before, after, svc: target.serviceId };
    });
    t.eq("อาจารย์แลกวัน แพทย์ประจำบ้านยังอยู่สายเดิม ไม่ถูกย้ายตาม", stay.after, stay.before);

    t.check("ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
    await page.close();
  } finally {
    await browser.close();
    await srv.close();
  }
  return t;
}
