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

    /* ---------- ขอไปเข้าคาบของสายอื่น ----------
       ต้องได้รับอนุมัติก่อนจึงมีผล ระหว่างรออนุมัติตารางต้องไม่ขยับเลย */
    const visit = await page.evaluate(() => {
      store.data.visits = [];
      /* ตารางมีเฉพาะจันทร์–ศุกร์ ถ้ารันวันเสาร์อาทิตย์ "วันนี้" จะไม่มีคาบเลย
         จึงเดินย้อนไปหาวันทำการที่มีคาบจริง แทนที่จะสมมติว่าวันนี้เป็นวันทำการ */
      /* ต้องเป็นวันที่คนนั้นมีคาบซึ่ง "ระบุชื่ออาจารย์ไว้" ด้วย ไม่ใช่แค่มีคาบ —
         วันที่คาบทั้งหมดไม่มีชื่ออาจารย์ (เช่น round ward ล้วน) จะไม่มีผู้อนุมัติให้ระบุตัวได้
         ซึ่งเป็นพฤติกรรมที่ถูกต้อง: กรณีนั้นตกไปที่ผู้จัดหลักสูตรอนุมัติ */
      let iso = todayISO(), r = null;
      for (let i = 0; i < 21 && !r; i++) {
        iso = addDaysISO(todayISO(), -i);
        r = store.data.residents.find(x => visitOptions(x.id, iso).length &&
          sessionsForDate(iso).some(s => s.residentId === x.id && (s.staffIds || []).length));
      }
      if (!r) return { none: true };
      const o = visitOptions(r.id, iso)[0];
      const names = () => sessionsForDate(iso).filter(x => x.residentId === r.id)
        .map(x => x.name + (x.superseded ? "|แพ้" : "") + (x.visit ? "|ไปสายอื่น" : ""));
      const before = names();
      store.data.visits.push({ id: "v_test", residentId: r.id, date: iso, serviceId: o.serviceId,
        index: o.index, reasonType: "research", reason: "เคสงานวิจัย", status: "pending" });
      const pending = names();
      store.data.visits[0].status = "approved";
      const approved = names();
      const ses = sessionsForDate(iso).find(x => x.residentId === r.id && x.visit);
      /* กิจกรรมวิชาการต้องยังชนะคาบที่ไปสายอื่น */
      const academic = sessionsForDate(iso).find(x => x.residentId === r.id && x.academic);
      store.data.visits[0].status = "declined";
      const declined = names();
      store.data.visits = [];
      return { before, pending, approved, declined,
               ownTeamLost: approved.some(n => n.includes("|แพ้")),
               visitPriority: ses?.priority, academicPriority: academic?.priority,
               visitSuperseded: !!ses?.superseded, approvers: visitApprovers(r.id, iso).length };
    });
    t.eq("คำขอที่ยังไม่อนุมัติ ตารางไม่ขยับเลย", visit.pending, visit.before);
    t.eq("ไม่อนุมัติ ตารางก็ไม่ขยับ", visit.declined, visit.before);
    t.check("อนุมัติแล้วคาบของสายอื่นขึ้นในตาราง",
            visit.approved.some(n => n.includes("|ไปสายอื่น")), visit.approved.join(" · "));
    t.check("คาบของสายเดิมที่ชนกันกลายเป็นคาบที่ไม่ได้เข้า", visit.ownTeamLost, visit.approved.join(" · "));
    t.check("คาบที่ไปสายอื่นยังแพ้กิจกรรมวิชาการ — วิชาการมาก่อนเสมอ",
            visit.academicPriority > visit.visitPriority,
            "วิชาการ " + visit.academicPriority + " · ไปสายอื่น " + visit.visitPriority);
    t.check("มีอาจารย์ผู้อนุมัติที่ระบุตัวได้", visit.approvers > 0, visit.approvers + " คน");

    /* ---------- ประเมินท้ายเซสชันครั้งเดียว ต้องได้ระดับ EPA ไปด้วย ----------
       สองที่นี้ใช้สเกล entrustment เดียวกัน ถ้าไม่เชื่อมกัน อาจารย์ต้องให้ระดับซ้ำสองรอบ */
    const epaFromSession = await page.evaluate(async () => {
      store.data.sessionEvals = [];
      store.data.epaAssessments = [];
      let ses = null;
      for (let i = 1; i < 15 && !ses; i++)
        ses = sessionsForDate(addDaysISO(todayISO(), -i)).find(x => x.residentId && !x.advisory);
      if (!ses) return { none: true };
      const epa = store.data.epas[0];
      openSession(ses.key);
      const box = document.querySelector('#dlgBody [name="epa_' + epa.id + '"]');
      const hasPicker = !!box;
      if (box) box.checked = true;
      document.querySelector('#dlgBody [name="entrust"]').value = "4";
      document.querySelector('#dlgBody [name="sc_knowledge"]').value = "4";
      [...document.querySelectorAll("#dlgFoot button")]
        .find(x => x.textContent.includes("บันทึกผลประเมิน")).click();
      document.querySelector("#dlg")?.close();
      const written = (store.data.epaAssessments || []).filter(a => a.epaId === epa.id);
      const level = epaLevel(ses.residentId, epa.id);

      /* แก้ผลประเมินซ้ำ ต้องไม่เกิดรายการ EPA ซ้อน */
      openSession(ses.key);
      document.querySelector('#dlgBody [name="epa_' + epa.id + '"]').checked = true;
      document.querySelector('#dlgBody [name="entrust"]').value = "5";
      [...document.querySelectorAll("#dlgFoot button")]
        .find(x => x.textContent.includes("บันทึกการแก้ไข") || x.textContent.includes("บันทึกผลประเมิน")).click();
      document.querySelector("#dlg")?.close();
      const afterEdit = (store.data.epaAssessments || []).filter(a => a.epaId === epa.id);

      /* ลบผลประเมิน ระดับ EPA ที่มาจากคาบนี้ต้องหายไปด้วย */
      openSession(ses.key);
      const realConfirm = window.confirm; window.confirm = () => true;
      [...document.querySelectorAll("#dlgFoot button")].find(x => x.textContent.includes("ลบผลประเมิน")).click();
      window.confirm = realConfirm;
      document.querySelector("#dlg")?.close();
      const afterDelete = (store.data.epaAssessments || []).filter(a => a.sessionKey === ses.key).length;

      store.data.sessionEvals = []; store.data.epaAssessments = [];
      return { hasPicker, written: written.length, level, source: written[0]?.sessionKey === ses.key,
               afterEditCount: afterEdit.length, afterEditLevel: afterEdit[0]?.level, afterDelete };
    });
    t.check("แบบประเมินท้ายเซสชันมีช่องเลือกหัวข้อ EPA", epaFromSession.hasPicker);
    t.eq("ประเมินครั้งเดียว ได้ระดับ EPA มาด้วย", [epaFromSession.written, epaFromSession.level], [1, 4]);
    t.check("ผล EPA บอกที่มาว่ามาจากคาบไหน", epaFromSession.source);
    t.eq("แก้ผลประเมินแล้วไม่เกิดรายการ EPA ซ้อน",
         [epaFromSession.afterEditCount, epaFromSession.afterEditLevel], [1, 5]);
    t.eq("ลบผลประเมินแล้วระดับ EPA ที่มาจากคาบนั้นหายไปด้วย", epaFromSession.afterDelete, 0);

    t.check("ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
    await page.close();
    /* ---------- หน้าประเมิน: งานนำเสนอ · ลงกองสิ้นเดือน · ท้ายเซสชัน ---------- */
    {
      const { page, errors } = await openAs(browser, srv.url, "staff");
      await page.evaluate(() => showView("assess"));
      await page.waitForTimeout(300);

      const r = await page.evaluate(async () => {
        const month = lastClosedMonth();
        const rots = rotationsToAssess(month);
        /* รอบที่ไปวนนอกกลุ่มงานต้องไม่อยู่ในคิว — อาจารย์ของกลุ่มงานไม่ได้คุมเดือนนั้น */
        const outsideInQueue = rots.filter(rotationOutside).length;
        /* รอบที่อยู่ในกลุ่มงานต้องมีชื่ออาจารย์ผู้กำกับทุกรอบ — เคยเป็นค่าว่างทั้งหมด
           เพราะอ่าน t.staffId ทั้งที่ตารางเก็บเป็น t.staffIds มานานแล้ว
           (รอบที่ไปวนนอกกลุ่มงานไม่มีอาจารย์ผู้กำกับในระบบนี้ ถูกต้องแล้ว) */
        const inHouse = (store.data.rotations || []).filter(x => !rotationOutside(x));
        const noSupervisor = inHouse.filter(x => !x.supervisorId).length;
        const target = rots.find(x => !rotationEvalFor(x.id)) || rots[0];
        openRotationEval(target.id);
        await new Promise(res => setTimeout(res, 120));
        const opened = !!document.querySelector("#dlgBody [name=\"sc_knowledge\"]");
        document.querySelector("#dlgBody [name=\"sc_knowledge\"]").value = "4";
        document.querySelector("#dlgBody [name=\"sc_skill\"]").value = "3";
        document.querySelector("#dlgBody [name=\"entrust\"]").value = "3";
        document.querySelector("#dlgBody [name=\"comment\"]").value = "ทดสอบข้อเสนอแนะ";
        [...document.querySelectorAll("#dlgFoot button")].find(b => /บันทึก/.test(b.textContent))?.click();
        await new Promise(res => setTimeout(res, 200));
        const ev = rotationEvalFor(target.id);
        return { month, rots: rots.length, outsideInQueue, noSupervisor, opened,
                 saved: !!ev, mean: ev ? evalMean(ev) : null, entrust: ev?.entrust ?? null,
                 rid: target.residentId, evRid: ev?.residentId,
                 stillPending: rotationsToAssess(month).filter(x => !rotationEvalFor(x.id)).length,
                 csv: rotationEvalCsvRows().length };
      });
      t.check("มีรอบหมุนเวียนให้ประเมินลงกอง", r.rots > 0, r.month + " · " + r.rots + " รอบ");
      t.eq("ทุกรอบหมุนเวียนในกลุ่มงานมีชื่ออาจารย์ผู้กำกับ", r.noSupervisor, 0);
      t.eq("รอบที่ไปวนนอกกลุ่มงานไม่อยู่ในคิวประเมินลงกอง", r.outsideInQueue, 0);
      t.check("เปิดแบบประเมินลงกองได้", r.opened);
      t.check("บันทึกผลประเมินลงกองแล้วเก็บจริง", r.saved, "เฉลี่ย " + r.mean + " · entrust " + r.entrust);
      t.eq("ผลประเมินผูกกับแพทย์ประจำบ้านคนที่ถูกประเมิน", r.evRid, r.rid);
      t.check("CSV ผลประเมินลงกองมีข้อมูลจริง", r.csv > 1, r.csv - 1 + " แถว");

      /* งานนำเสนอกับคาบท้ายเซสชันต้องมาอยู่ในหน้าเดียวกันนี้ด้วย */
      const pages = await page.evaluate(async () => {
        const out = {};
        document.querySelector('#assessNav [data-assess="talks"]').click();
        await new Promise(res => setTimeout(res, 200));
        out.talkRows = document.querySelectorAll("#activityTable tbody tr").length;
        out.hasCsv = !!document.querySelector("#btnCsvFiltered");
        out.badge = talksToAssess().length;
        out.pages = [...document.querySelectorAll("#assessNav [data-assess]")].map(b => b.dataset.assess);
        out.noActivitiesTab = !document.querySelector('#tabs [data-view="activities"]');
        return out;
      });
      t.check("หน้าประเมินมีคิวงานนำเสนอ พร้อมปุ่มดาวน์โหลด CSV เหมือนหน้ากิจกรรมเดิม",
              pages.talkRows > 0 && pages.hasCsv, pages.talkRows + " แถว");
      t.eq("ตัวเลขค้างบนป้ายตรงกับจำนวนแถวที่เห็นตอนเปิดหน้ามา", pages.talkRows, pages.badge);
      t.eq("หน้าประเมินมีสองหน้าย่อย — งานนำเสนอ กับ ลงกองสิ้นเดือน", pages.pages, ["talks", "month"]);
      t.check("แท็บกิจกรรมทั้งหมดถูกยุบเข้ามาแล้ว ไม่มีแท็บซ้ำ", pages.noActivitiesTab);

      /* แบบประเมินการนำเสนอ — คะแนนรายด้าน ผลสรุป และค่าเฉลี่ยที่รายงานอื่นอ่านต่อ */
      const talk = await page.evaluate(async () => {
        const a = visibleActivities().find(x => x.type === "journal" && !x.assessment)
               || visibleActivities().find(x => !x.assessment);
        openActivity(a.id);
        await new Promise(r => setTimeout(r, 150));
        const sels = [...document.querySelectorAll('#dlgBody select[name^="tv_"]')];
        const expected = talkEvalItemsFor(a.type).length;
        /* ให้คะแนนแค่สองข้อ เพื่อพิสูจน์ว่าค่าเฉลี่ยคิดจากข้อที่กรอกเท่านั้น ไม่นับข้อว่างเป็นศูนย์ */
        sels[0].value = "5"; sels[1].value = "3";
        document.querySelector('#dlgBody [name="tvOutcome"]').value = "advice";
        document.querySelector('#dlgBody [name="assessBy"]').value = "อ.ทดสอบ";
        document.querySelector('#dlgBody [name="tvGood"]').value = "เตรียมตัวมาดี";
        document.querySelector('#dlgBody [name="assessComment"]').value = "คุมเวลาให้ดีขึ้น";
        [...document.querySelectorAll("#dlgFoot button")].find(b => /บันทึกการแก้ไข/.test(b.textContent))?.click();
        await new Promise(r => setTimeout(r, 200));
        const saved = store.data.activities.find(x => x.id === a.id).assessment;
        /* ข้อเฉพาะประเภทต้องเปลี่ยนตามชนิดของงานนำเสนอ ไม่ใช่ชุดเดียวใช้ทุกแบบ */
        const perType = Object.fromEntries(ACTIVITY_TYPES.map(t =>
          [t.id, talkEvalItemsFor(t.id).length]));
        const base = TALK_EVAL_ITEMS.length;
        const extraIds = ACTIVITY_TYPES.map(t => talkEvalItemsFor(t.id).slice(-1)[0].id);
        const csv = activityCsvRows([store.data.activities.find(x => x.id === a.id)]);
        return { type: a.type, sels: sels.length, expected, saved, perType,
                 base, uniqueExtras: new Set(extraIds).size, nTypes: ACTIVITY_TYPES.length,
                 csvHasItem: csv[0].some(h => /^ประเมิน: /.test(h)),
                 csvOutcome: csv[1][csv[0].indexOf("ผลการประเมิน")] };
      });
      t.eq("ฟอร์มประเมินการนำเสนอมีข้อครบตามประเภทกิจกรรม", talk.sels, talk.expected);
      t.check("ทุกประเภทได้ข้อเฉพาะเพิ่มมาหนึ่งข้อ",
              Object.values(talk.perType).every(n => n === talk.base + 1), JSON.stringify(talk.perType));
      t.eq("ข้อเฉพาะประเภทไม่ซ้ำกัน — คนละประเภทดูคนละเรื่อง", talk.uniqueExtras, talk.nTypes);
      t.eq("ค่าเฉลี่ยคิดจากเฉพาะข้อที่ให้คะแนน ไม่นับข้อที่เว้นว่าง", talk.saved?.score, 4);
      t.eq("เก็บผลการประเมินโดยรวมไว้ด้วย", talk.saved?.outcome, "advice");
      t.eq("แยกช่องสิ่งที่ทำได้ดีกับสิ่งที่ควรปรับปรุง",
           [talk.saved?.strengths, talk.saved?.comment], ["เตรียมตัวมาดี", "คุมเวลาให้ดีขึ้น"]);
      t.check("CSV กิจกรรมมีคะแนนรายด้านและผลการประเมิน", talk.csvHasItem && !!talk.csvOutcome, talk.csvOutcome);
      t.check("หน้าประเมิน: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();

      /* แพทย์ประจำบ้านต้องไม่เห็นหน้าประเมิน และประเมินลงกองแทนอาจารย์ไม่ได้ */
      const { page: rp } = await openAs(browser, srv.url, "resident");
      const res = await rp.evaluate(async () => {
        const tab = document.querySelector('#tabs [data-view="assess"]');
        const rot = (store.data.rotations || []).find(x => x.residentId === myResidentId());
        const before = (store.data.rotationEvals || []).length;
        openRotationEval(rot.id);
        await new Promise(r => setTimeout(r, 120));
        const canSave = !![...document.querySelectorAll("#dlgFoot button")].find(b => /บันทึก/.test(b.textContent));
        closeDialog();
        return { tabHidden: !tab || tab.hidden, canSave, grew: (store.data.rotationEvals || []).length > before };
      });
      t.check("แพทย์ประจำบ้านไม่เห็นแท็บประเมิน", res.tabHidden);
      t.check("แพทย์ประจำบ้านบันทึกผลประเมินลงกองไม่ได้", !res.canSave && !res.grew);
      await rp.close();
    }

  } finally {
    await browser.close();
    await srv.close();
  }
  return t;
}
