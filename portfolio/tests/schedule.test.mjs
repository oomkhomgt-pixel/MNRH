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

    /* ---------- B8: free elective ของปี 3 ต้องเป็นเดือนติดกันจริงในปีการศึกษาเดียวกัน ----------
       เดิมวนหาช่วงว่างด้วย mod 12 ทำให้ [10,11,0] ถูกนับว่า "3 เดือนติดกัน" ทั้งที่ index 0
       คือ ก.ค. ต้นปีเดียวกัน ไม่ใช่เดือนถัดจาก index 11 (มิ.ย.) จริง — ข้อมูลสาธิตมีปี 3 น้อยเกินไปที่จะ
       บีบให้ตัวค้นหาต้องเดินไปชนขอบเขตนี้เอง จึงเติมปี 3 ชั่วคราวให้ความจุใกล้เต็ม (2 คน/เดือน x 3 เดือน) */
    const b8 = await page.evaluate(() => {
      const backupResidents = store.data.residents;
      const extra = Array.from({ length: 6 }, (_, i) => ({ id: "res_b8_" + i, name: "ทดสอบปี3-" + i,
        nick: "b8-" + i, year: 3, cohort: "2567", advisor: "", email: "" }));
      store.data.residents = [...store.data.residents, ...extra];
      const plan = buildRotationPlan(currentAY(), store.data.residents, store.data.services);
      const electiveSvc = store.data.services.find(x => x.elective);
      const r3 = store.data.residents.filter(r => r.year === 3);
      const bad = [];
      r3.forEach(r => {
        /* ที่ระบบรู้ตัวแล้วว่าจัดติดกันไม่ได้ (เพดานเต็มจริง) มีคำเตือนกำกับไว้แล้ว ข้ามการเช็คนี้ได้ */
        if (plan.warnings.some(w => w.includes(r.name) && w.includes("ไม่ติดกัน"))) return;
        const starts = plan.rotations.filter(x => x.residentId === r.id && x.serviceId === electiveSvc.id).map(x => x.start);
        const idxs = starts.map(s => plan.months.findIndex(mm => monthStartISO(mm) === s)).sort((a, b) => a - b);
        if (idxs.length < 2) return;
        const contiguous = idxs.every((v, i) => i === 0 || v === idxs[i - 1] + 1);
        if (!contiguous) bad.push(r.name + ":" + idxs.join(","));
      });
      store.data.residents = backupResidents;
      return { bad, r3Count: r3.length, hasElective: !!electiveSvc };
    });
    t.check("มีข้อมูลปี 3 และหน่วย elective ให้ตรวจจริง", b8.r3Count > 0 && b8.hasElective);
    t.eq("ทุกคนปี 3 ที่ไม่มีคำเตือนว่าจัดไม่ติดกัน ได้เดือนที่ติดกันจริงในปีการศึกษาเดียวกัน ไม่ข้ามขอบเขตปี",
         b8.bad, []);

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

    /* ---------- B6: วันหยุดราชการ คำขอไปเข้าคาบของสายอื่นที่อนุมัติแล้ว ต้องไม่สร้างคาบผี ----------
       เดิม out.length=0 (ล้างวันหยุด) รันก่อนชั้นคำขอไปเข้าคาบของสายอื่น คำขอเดิมจึงรอดจากการล้าง
       ทั้งที่ตารางประจำสัปดาห์ของวันนั้นไม่ได้เกิดขึ้นจริงแล้ว (ต่างจากเวร ER ที่ยังต้องมีคนคุมทุกวัน) */
    const b6 = await page.evaluate(() => {
      const iso = "2026-08-12";
      const dow = new Date(iso + "T00:00:00").getDay();
      let svc = null, idx = -1;
      for (const s of store.data.services) {
        idx = (s.template || []).findIndex(t => t.day === dow);
        if (idx >= 0) { svc = s; break; }
      }
      if (!svc) return { none: true };
      store.data.visits = [{ id: "v_holiday_test", residentId: store.data.residents[0].id, date: iso,
        serviceId: svc.id, index: idx, reasonType: "research", reason: "ทดสอบ", status: "approved" }];
      const row = dutyRow(iso);
      row.holiday = false;
      const normalCount = sessionsForDate(iso).filter(s => s.visitId === "v_holiday_test").length;
      row.holiday = true;
      const holidayCount = sessionsForDate(iso).filter(s => s.visitId === "v_holiday_test").length;
      store.data.visits = [];
      return { none: false, normalCount, holidayCount };
    });
    if (!b6.none) {
      t.check("วันปกติ คำขอไปเข้าคาบของสายอื่นที่อนุมัติแล้ว สร้างคาบขึ้นจริง (พิสูจน์ว่าทดสอบตรงเงื่อนไข)", b6.normalCount > 0);
      t.eq("วันหยุดราชการ คำขอเดิมไม่สร้างคาบผีที่ไม่มีตารางประจำสัปดาห์รองรับ", b6.holidayCount, 0);
    }

    /* ---------- B7: ตัวเลือก "หน้างาน" ต้องจำกัดเฉพาะคนในสาย ER ของวันนั้นจริง ----------
       เดิมเลือกได้จากรายชื่อแพทย์ประจำบ้านทั้งหมด เลือกคนนอกสายได้แต่ไม่มีคาบเกิดขึ้นจริง ไม่มีเตือน */
    const b7 = await page.evaluate(() => {
      const white = store.data.services.find(x => x.abbr === "ขาว");
      const iso = "2026-08-06";
      const row = dutyRow(iso);
      row.erServiceId = white.id;
      dutyMonth = "2026-08"; renderDutyTable();
      const sel = document.querySelector('[data-d="' + iso + '|erResidentIds"]');
      const optIds = sel ? [...sel.options].map(o => o.value) : [];
      const teamIds = new Set(store.data.residents.filter(r => rotationOn(r.id, iso)?.serviceId === white.id).map(r => r.id));
      return { optCount: optIds.length, outsiders: optIds.filter(id => !teamIds.has(id)), teamSize: teamIds.size };
    });
    t.eq("ตัวเลือกหน้างานไม่มีคนนอกสาย ER ของวันนั้นปนมา", b7.outsiders, []);
    t.check("มีตัวเลือกให้จริง ไม่ใช่ว่างเปล่า", b7.optCount === b7.teamSize && b7.optCount > 0,
            b7.optCount + " จากทีม " + b7.teamSize + " คน");

    /* ---------- B4: สร้างรอบหมุนเวียนใหม่ ช่องอาจารย์ผู้กำกับต้องเริ่มที่ว่าง ไม่ใช่คนแรกในรายชื่อ ----------
       เดิม select ไม่มีตัวเลือกว่าง เบราว์เซอร์จึงเลือกคนแรกในรายชื่อให้อัตโนมัติโดยไม่มีใครตั้งใจเลือก
       และเปลี่ยนหน่วยแล้วไม่มีอะไรช่วยเดาอาจารย์ผู้กำกับตามค่าเริ่มต้นของหน่วยนั้นให้เลย */
    const b4 = await page.evaluate(() => {
      editRotation(null);
      const supDefault = document.querySelector('#dlgBody [name="supervisorId"]').value;
      const svcSel = document.querySelector('#dlgBody [name="serviceId"]');
      const svc = rotatableServices().find(x => x.id !== svcSel.value) || rotatableServices()[0];
      svcSel.value = svc.id;
      svcSel.dispatchEvent(new Event("change"));
      const supAfter = document.querySelector('#dlgBody [name="supervisorId"]').value;
      const expected = defaultSupervisorFor(svc.id, store.data.services, store.data.staff) || "";
      document.querySelector("#dlg")?.close();
      return { supDefault, supAfter, expected };
    });
    t.eq("สร้างรอบหมุนเวียนใหม่ ช่องอาจารย์ผู้กำกับเริ่มที่ว่าง ไม่ใช่คนแรกในรายชื่อโดยไม่ตั้งใจ", b4.supDefault, "");
    t.eq("เลือกหน่วยใหม่แล้วช่วยเดาอาจารย์ผู้กำกับตามค่าเริ่มต้นของหน่วยนั้นให้", b4.supAfter, b4.expected);

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
      /* คำถามยืนยันเป็นกล่องของแอปแล้ว (ไม่ใช่ window.confirm) — stub ให้ตอบ "ตกลง" ทั้งแบบกล่องและแบบแทรกในกล่อง */
      const realCD = confirmDialog, realCI = confirmInline;
      confirmDialog = async () => true; confirmInline = async () => true;
      openSwap(iso, a, "", "");
      document.querySelector('#dlgBody [name="toStaffId"]').value = b;
      document.querySelector('#dlgBody [name="returnDate"]').value = back;
      [...document.querySelectorAll("#dlgFoot button")].find(x => x.textContent.includes("ส่งคำขอ")).click();
      await new Promise(r => setTimeout(r, 30));   /* ปุ่มส่งคำขอเป็น async แล้ว */
      document.querySelector("#dlg").close();
      const afterRequest = store.data.swaps.map(x => [x.date, x.fromStaffId, x.toStaffId, x.status].join(">"));
      await decideSwap(store.data.swaps[0].id, true);
      confirmDialog = realCD; confirmInline = realCI;
      const afterAccept = store.data.swaps.map(x => [x.date, x.fromStaffId, x.toStaffId, x.status].join(">"));
      store.data.swaps = [];
      return { afterRequest, afterAccept,
               wantRequest: [[iso, a, b, "pending"].join(">")],
               wantAccept: [[iso, a, b, "accepted"].join(">"), [back, b, a, "accepted"].join(">")] };
    });
    t.eq("ส่งคำขอแล้วได้รายการเดียวที่ยังรอตอบรับ ยังไม่แตะวันแลกกลับ",
         pair.afterRequest, pair.wantRequest);
    t.eq("ตอบรับแล้วอีกฝั่งของการแลกถูกสร้างให้เอง", pair.afterAccept, pair.wantAccept);

    /* ---------- B3: แลกกลับวันเดียวกับที่ขอพอดี (returnDate === date) ก็ต้องสร้างขาคืนได้ ----------
       เดิม .some() หาการชนกันของ pairId+date รวม sw เองด้วย (เพราะ date กับ returnDate เท่ากัน)
       จึงคิดว่ามีขาคืนอยู่แล้ว ทั้งที่ยังไม่เคยสร้างเลย — ขาคืนไม่ถูกสร้างขึ้นมาเลยในกรณีนี้ */
    const selfCollision = await page.evaluate(async () => {
      store.data.swaps = [];
      const iso = todayISO();
      const a = store.data.staff[0].id, b = store.data.staff[1].id;
      const realCD = confirmDialog; confirmDialog = async () => true;
      store.data.swaps.push({ id: "sw_self", pairId: "p_self", date: iso, part: "", serviceId: "",
        fromStaffId: a, toStaffId: b, note: "", returnDate: iso, status: "pending",
        requestedBy: "", requestedAt: "", decidedBy: "", decidedAt: "" });
      await decideSwap("sw_self", true);
      confirmDialog = realCD;
      const legs = store.data.swaps.map(x => [x.date, x.fromStaffId, x.toStaffId, x.status].join(">"));
      store.data.swaps = [];
      return { legs };
    });
    t.eq("แลกกลับวันเดียวกับที่ขอ ก็ยังสร้างขาคืนให้ครบทั้งสองขา ไม่หายไปเงียบ ๆ", selfCollision.legs.length, 2);

    /* ---------- B3: ตอบรับการแลกที่มีวันแลกกลับ ต้องเช็คว่าวันแลกกลับชนคาบเดิมของผู้ขอด้วย ----------
       เดิมเช็ค staffBusyOn แค่วันของขาแรก (sw.date) วันแลกกลับไม่เคยถูกเช็คเลย */
    const returnCheck = await page.evaluate(async () => {
      store.data.swaps = [];
      const a = store.data.staff[0].id, b = store.data.staff[1].id;
      const iso = todayISO(), back = addDaysISO(iso, 7);
      const calls = [];
      const real = staffBusyOn;
      staffBusyOn = (...args) => { calls.push(args); return real(...args); };
      const realCD = confirmDialog; confirmDialog = async () => true;
      store.data.swaps.push({ id: "sw_spy", pairId: "p_spy", date: iso, part: "", serviceId: "",
        fromStaffId: a, toStaffId: b, note: "", returnDate: back, status: "pending",
        requestedBy: "", requestedAt: "", decidedBy: "", decidedAt: "" });
      await decideSwap("sw_spy", true);
      staffBusyOn = real; confirmDialog = realCD;
      store.data.swaps = [];
      return { checkedDates: calls.map(c => c[1]), back };
    });
    t.check("ตอบรับการแลกที่มีวันแลกกลับ เช็ควันแลกกลับด้วย ไม่ใช่แค่วันของขาแรก",
            returnCheck.checkedDates.includes(returnCheck.back), JSON.stringify(returnCheck.checkedDates));

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

    /* ---------- รายละเอียดเซสชัน: เปิดแล้วไม่มีฟอร์มประเมิน มีแต่ข้อมูลอ่านอย่างเดียว + ปุ่มเข้าคาบ/แลกวัน ---------- */
    const sessDetail = await page.evaluate(async () => {
      let ses = null;
      for (let i = 1; i < 15 && !ses; i++)
        ses = sessionsForDate(addDaysISO(todayISO(), -i)).find(x => x.residentId && !x.advisory);
      if (!ses) return { none: true };
      openSession(ses.key);
      const hasScoreField = !!document.querySelector('#dlgBody [name^="sc_"], #dlgBody [name="entrust"], #dlgBody [name^="epa_"]');
      const title = document.querySelector("#dlgTitle")?.textContent || "";
      document.querySelector("#dlg")?.close();
      return { hasScoreField, title };
    });
    if (!sessDetail.none) {
      t.check("เปิดรายละเอียดเซสชันแล้วไม่มีช่องให้คะแนน (ประเมินท้ายเซสชันถูกตัดออกแล้ว)", !sessDetail.hasScoreField);
      t.eq("หัวกล่องเป็น 'รายละเอียดเซสชัน'", sessDetail.title, "รายละเอียดเซสชัน");
    }

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
        /* ข้อให้คะแนนเป็นปุ่ม radio แล้ว — ติ๊กตัวที่มี value ตรง ไม่ใช่ตั้ง .value ของ select */
        document.querySelector("#dlgBody [name=\"sc_knowledge\"][value=\"4\"]").checked = true;
        document.querySelector("#dlgBody [name=\"sc_plan\"][value=\"3\"]").checked = true;
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

      /* ---------- กติกาชั้นปีของหน่วย และชื่ออาจารย์จริง ---------- */
      const rule = await page.evaluate(() => {
        const d = store.data;
        const bad = rotationYearWarnings(d.rotations, d.services, d.residents);
        /* ปี 1 ต้องไปวน Trauma Surgery ของศัลยกรรมอุบัติเหตุ ไม่ใช่หน่วย trauma ของออร์โธฯ */
        const r1 = d.residents.find(r => r.name.includes("อัฐท์"));
        const aug = d.rotations.find(x => x.residentId === r1?.id && (x.start || "").startsWith("2026-08"));
        const augSvc = d.services.find(x => x.id === aug?.serviceId);
        /* ยัดรอบผิดกติกาเข้าไปหนึ่งรายการ ต้องได้คำเตือนที่ระบุตัวคนและหน่วย */
        const sub = d.services.find(x => x.subUnit);
        const planted = rotationYearWarnings(
          [{ residentId:r1.id, serviceId:sub.id, start:"2026-09-01", end:"2026-09-30" }], d.services, d.residents);
        return { bad, augAbbr: augSvc?.abbr, augExternal: !!augSvc?.external, augYears: augSvc?.years,
                 ext: externalByYear(d.services),
                 planted: planted.length === 1 && planted[0].includes(r1.name) && planted[0].includes(sub.name) };
      });
      t.eq("ไม่มีรอบหมุนเวียนใดขัดกติกาชั้นปีของหน่วย", rule.bad, []);
      t.eq("เดือน ส.ค. ของปี 1 คือ Trauma Surgery ซึ่งเป็นการวนนอกกลุ่มงานของชั้นปี 1",
           [rule.augAbbr, rule.augExternal, rule.augYears], ["TRS", true, [1]]);
      t.eq("รายชื่อหน่วยนอกกลุ่มงานมาจาก services[].years ตรงตามหลักสูตร",
           rule.ext, { 1:["svc_anesth","svc_rheum","svc_traumasurg"], 2:["svc_pmr"] });
      t.check("ยัดรอบที่ผิดชั้นปีเข้าไป ได้คำเตือนที่ระบุตัวคนและหน่วย", rule.planted);

      const names = await page.evaluate(() => {
        const d = store.data;
        const roster = new Set((d.staff || []).map(x => x.name));
        const off = [];
        (d.activities || []).forEach(a => {
          if (a.assessment?.by && !roster.has(a.assessment.by)) off.push("ผู้ประเมิน: " + a.assessment.by);
          if (a.verifiedBy && !roster.has(a.verifiedBy)) off.push("ผู้รับรอง: " + a.verifiedBy);
        });
        (d.research || []).forEach(x => { if (x.advisor && !roster.has(x.advisor)) off.push("ที่ปรึกษาวิจัย: " + x.advisor); });
        (d.residents || []).forEach(r => { if (r.advisor && !roster.has(r.advisor)) off.push("ที่ปรึกษา: " + r.advisor); });
        /* เคสผ่าตัดกับผลประเมิน EPA ก็อ้างชื่ออาจารย์เหมือนกัน เดิมยังไม่มีเทสต์ตรวจจุดนี้ */
        (d.cases || []).forEach(c => {
          if (c.primarySurgeon && !roster.has(c.primarySurgeon)) off.push("ศัลยแพทย์หลัก: " + c.primarySurgeon);
          (c.participants || []).forEach(p => {
            if (p.verifiedBy && !roster.has(p.verifiedBy)) off.push("ผู้รับรองเคส: " + p.verifiedBy);
          });
        });
        (d.epaAssessments || []).forEach(e => { if (e.by && !roster.has(e.by)) off.push("ผู้ประเมิน EPA: " + e.by); });
        const noAdvisor = (d.residents || []).filter(r => !r.advisor).map(r => r.name);
        /* ที่ปรึกษางานวิจัยควรถืออนุสาขาตรงกับโครงการ */
        const mismatch = (d.research || []).filter(x => {
          const st = (d.staff || []).find(y => y.name === x.advisor);
          const mine = st?.subspecialties?.length ? st.subspecialties : [st?.subspecialty].filter(Boolean);
          return !mine.includes(x.subspecialty);
        }).map(x => x.subspecialty);
        return { off: [...new Set(off)], noAdvisor, mismatch };
      });
      t.eq("ทุกชื่ออาจารย์ในข้อมูลสาธิตมาจากทะเบียนจริง ไม่มีชื่อสมมติหลงเหลือ", names.off, []);
      t.eq("แพทย์ประจำบ้านทุกคนมีอาจารย์ที่ปรึกษา", names.noAdvisor, []);
      t.eq("อาจารย์ที่ปรึกษางานวิจัยถืออนุสาขาตรงกับโครงการ", names.mismatch, []);

      /* ---------- ชุดข้อตั้งต้น: 8 ข้อ อ้างอิง WFME ---------- */
      const def = await page.evaluate(() => {
        const f = rotationForm();
        const scale = f.items.filter(x => x.kind === "scale");
        const bad = f.items.flatMap(x => x.wfme || []).filter(w => !WFME_BY_ID[w]);
        const ev = wfmeEvidence();
        const cited = [...new Set(f.items.flatMap(x => x.wfme || []))];
        return {
          scale: scale.length,
          scaleNoWfme: scale.filter(x => !(x.wfme || []).length).map(x => x.id),
          kinds: f.items.map(x => x.kind).join(","),
          bad, version: f.version,
          /* หน้ามาตรฐาน WFME ต้องอ้างหลักฐานได้ทุกหมวดที่ฟอร์มบอกว่าตัวเองเป็นหลักฐานให้ */
          uncited: cited.filter(w => !(ev[w]?.sources || []).some(sc => /แบบประเมินการทำงานในสาย/.test(sc.label))),
          /* แบบประเมินการนำเสนอก็ต้องถูกอ้างในหน้ามาตรฐานครบทุกหมวดที่ข้อของมันระบุ
             (รวมข้อเฉพาะประเภท — เฉพาะประเภทที่มีกิจกรรมถูกให้คะแนนแล้ว ตามเงื่อนไขของ wfmeEvidence) */
          talkUncited: [...new Set([...new Set(store.data.activities.filter(a => a.assessment?.scores && Object.keys(a.assessment.scores).length).map(a => a.type))]
              .flatMap(t => talkEvalItemsFor(t)).flatMap(x => x.wfme || []))]
            .filter(w => !(ev[w]?.sources || []).some(sc => /แบบประเมินการนำเสนอ/.test(sc.label))),
          talkBadWfme: ACTIVITY_TYPES.flatMap(t => talkEvalItemsFor(t.id)).flatMap(x => x.wfme || []).filter(w => !WFME_BY_ID[w]),
          /* ข้อมูลสาธิตต้องไม่มีคำตอบไร้ข้อถามเลย */
          orphans: (store.data.rotationEvals || []).reduce((n, x) => n + rotationOrphanAnswers(x).length, 0)
        };
      });
      t.eq("ชุดตั้งต้นมีข้อให้คะแนน 8 ข้อ", def.scale, 8);
      t.eq("ทุกข้อให้คะแนนผูกกับหมวด WFME", def.scaleNoWfme, []);
      t.eq("ไม่มีรหัส WFME ที่ไม่มีอยู่จริง", def.bad, []);
      t.check("มีทั้งหัวข้อคั่น entrustment ผลโดยรวม และสองช่องข้อความ",
              /section/.test(def.kinds) && /entrust/.test(def.kinds) && /choice/.test(def.kinds)
              && def.kinds.split(",").filter(k => k === "paragraph").length === 2, def.kinds);
      t.eq("หน้ามาตรฐาน WFME อ้างหลักฐานครบทุกหมวดที่ฟอร์มระบุ", def.uncited, []);
      t.eq("หน้ามาตรฐาน WFME อ้างแบบประเมินการนำเสนอครบทุกหมวดที่ข้อของมันระบุ", def.talkUncited, []);
      t.eq("รหัส WFME ในแบบประเมินการนำเสนอมีอยู่จริงทุกตัว", def.talkBadWfme, []);
      t.eq("ข้อมูลสาธิตสร้างจากนิยามของฟอร์ม ไม่มีคำตอบไร้ข้อถาม", def.orphans, 0);

      /* ---------- รหัสข้อที่ชนกันหลังตัดที่ 40 ตัวอักษร ต้องไม่วนซ้ำไม่รู้จบ ----------
         เดิมต่อท้ายเลขกันซ้ำแล้วค่อยตัดที่ 40 ตัวอักษร ถ้ารหัสเดิมยาว 40 ตัวพอดีอยู่แล้ว
         ส่วนต่อท้ายจะถูกตัดทิ้งจนรหัสไม่เปลี่ยนเลย — วนซ้ำไม่รู้จบจริง (ยืนยันด้วยสคริปต์แยกแล้ว)
         ที่นี่ทดสอบว่าโค้ดที่แก้แล้ววิ่งจบเร็วและได้รหัสที่ไม่ซ้ำกันจริง ไม่ใช่แค่ไม่ค้าง */
      const dedupe = await page.evaluate(() => {
        /* store.data ถูกแทนที่ทั้งก้อนชั่วคราว ต้องคืนของเดิมกลับก่อนออกจากบล็อกนี้เสมอ
           ไม่งั้นฟอร์มทดสอบ 4 ข้อนี้จะไปทับของจริง แล้วเทสต์ถัดไปในไฟล์นี้พังหมด */
        const backup = store.data;
        try {
          const longId = "a".repeat(40);
          const d1 = { ...store.data, rotationForm: { title:"ทดสอบชนกัน", scale:{ min:1, max:5 }, items: [
            { id: longId, kind:"text", th:"ข้อที่ 1" },
            { id: longId, kind:"text", th:"ข้อที่ 2" },
            { id: longId, kind:"text", th:"ข้อที่ 3" },
            { id: longId, kind:"text", th:"ข้อที่ 4" },
          ] } };
          const t0 = Date.now();
          store.data = d1; store.migrate();
          const ms = Date.now() - t0;
          const ids = store.data.rotationForm.items.map(x => x.id);
          return { ms, ids, unique: new Set(ids).size, tooLong: ids.some(x => x.length > 40) };
        } finally {
          store.data = backup;
        }
      });
      t.eq("ทุกข้อได้รหัสไม่ซ้ำกันแม้รหัสเดิมยาวชนขอบเขต 40 ตัวอักษรพอดี", dedupe.unique, 4);
      t.check("ไม่มีรหัสไหนยาวเกิน 40 ตัวอักษร", !dedupe.tooLong, dedupe.ids.join(", "));
      t.check("แก้เสร็จเร็ว ไม่ค้าง (ต่ำกว่า 1 วินาที)", dedupe.ms < 1000, dedupe.ms + " ms");

      /* ---------- ตัวเลือกของข้อแบบเลือกหนึ่งข้อในหน้าแก้ฟอร์ม ต้องขึ้นบรรทัดใหม่จริง ----------
         เดิม join/split ใช้ "\\n" (แบ็กสแลชกับตัว n สองตัวอักษร) แทนตัวขึ้นบรรทัดจริง
         ทำให้ตัวเลือกทุกตัวไปกองอยู่บรรทัดเดียว และพิมพ์ตัวเลือกหลายบรรทัดแล้วบันทึกไม่แยกข้อ */
      const optsBug = await page.evaluate(() => {
        const f = rotationForm();
        f.items.push({ id:"opts_nl_test", kind:"choice", th:"ทดสอบขึ้นบรรทัด",
          options: [{ v:"1", th:"หนึ่ง" }, { v:"2", th:"สอง" }, { v:"3", th:"สาม" }] });
        editRotationItem("opts_nl_test");
        const ta = document.querySelector('#dlgBody [name="options"]');
        const rendered = ta.value;
        ta.value = "4=สี่\n5=ห้า";
        [...document.querySelectorAll("#dlgFoot button")].find(b => b.textContent === "บันทึก").click();
        const saved = f.items.find(x => x.id === "opts_nl_test").options;
        f.items = f.items.filter(x => x.id !== "opts_nl_test");
        return { rendered, savedCount: saved.length, savedFirst: saved[0] };
      });
      t.eq("ตัวเลือกที่ขึ้นแสดงในกล่องแก้ฟอร์ม แยกกันคนละบรรทัดจริง (ไม่ใช่ \\\\n ดิบ)",
           optsBug.rendered, "1=หนึ่ง\n2=สอง\n3=สาม");
      t.eq("พิมพ์ตัวเลือกหลายบรรทัดแล้วบันทึก แยกออกมาได้ครบทุกข้อ", optsBug.savedCount, 2);
      t.eq("ตัวเลือกแรกอ่านค่า/ป้ายถูกต้อง", optsBug.savedFirst, { v:"4", th:"สี่" });

      /* ---------- C5: คะแนนเดิมนอกช่วงตัวเลือกปกติ (เช่น ทศนิยม) ต้องไม่หายเมื่อบันทึกซ้ำ ---------- */
      const c5 = await page.evaluate(() => {
        const f = rotationForm();
        const scaleItem = f.items.find(x => x.kind === "scale");
        const ev = { scores: { [scaleItem.id]: 3.5 }, answers: {}, entrust: "", comment: "" };
        const html = rotationFormBodyHtml(ev);
        const escId = scaleItem.id.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        const hasOption = new RegExp('name="sc_' + escId + '"[\\s\\S]*?value="3\\.5"[^>]*checked').test(html);
        return { hasOption };
      });
      t.check("ปุ่มคะแนนมีปุ่ม 'ค่าเดิม' ที่ติ๊กอยู่สำหรับคะแนนทศนิยมเดิม ไม่เด้งไปที่ว่าง", c5.hasOption);

      /* ---------- C5b: เปิดผลลงกองสาธิตที่คะแนนเป็นทศนิยม แล้วบันทึกซ้ำโดยไม่แตะอะไร คะแนนต้องเท่าเดิมทุกตัว ---------- */
      const c5b = await page.evaluate(async () => {
        const ev = (store.data.rotationEvals || []).find(e => Object.values(e.scores || {}).some(v => !Number.isInteger(v)));
        if (!ev) return null;
        const before = JSON.stringify(ev.scores);
        openRotationEval(ev.rotationId);
        await new Promise(r => setTimeout(r, 120));
        [...document.querySelectorAll("#dlgFoot button")].find(b => /บันทึก/.test(b.textContent))?.click();
        await new Promise(r => setTimeout(r, 200));
        return { before, after: JSON.stringify(rotationEvalFor(ev.rotationId).scores), open: document.querySelector("#dlg").open };
      });
      if (c5b) t.check("บันทึกซ้ำโดยไม่แตะ คะแนนทศนิยมเดิมยังอยู่ครบทุกข้อ", c5b.before === c5b.after && !c5b.open, c5b.before + " → " + c5b.after);

      /* ---------- C6: choice ที่ scored:true แต่ option value ไม่ใช่ตัวเลข ต้องไม่ทำให้ค่าเฉลี่ยกลายเป็น NaN ---------- */
      const c6 = await page.evaluate(() => {
        const ev = { scores: { good: 4, bad_choice: NaN } };
        return { mean: evalMean(ev) };
      });
      t.eq("ค่า NaN ที่ปนอยู่ใน scores ไม่ทำให้ค่าเฉลี่ยทั้งก้อนกลายเป็น NaN", c6.mean, 4);

      /* ---------- C7: entrust/comment เดิมต้องไม่หาย ถ้าฟอร์มปัจจุบันไม่มีข้อนั้นแล้ว ---------- */
      const c7 = await page.evaluate(() => {
        const f = rotationForm();
        const backup = f.items;
        f.items = []; /* จำลองว่าข้อ entrust และช่องข้อเสนอแนะถูกลบออกจากฟอร์มไปแล้ว */
        const ev = { entrust: "4", comment: "ข้อความเดิมที่เคยบันทึกไว้", scores: {}, answers: {} };
        const result = readRotationForm(ev);
        f.items = backup;
        return result;
      });
      t.eq("entrust เดิมไม่หายแม้ฟอร์มปัจจุบันไม่มีข้อ entrust แล้ว", c7.entrust, 4);
      t.eq("ข้อเสนอแนะเดิมไม่หายแม้ฟอร์มปัจจุบันไม่มีช่องนั้นแล้ว", c7.comment, "ข้อความเดิมที่เคยบันทึกไว้");

      /* ---------- C8: เปลี่ยนชนิดข้อจากให้คะแนนเป็นข้อความ คะแนนเก่าต้องไม่ค้างบังคำตอบใหม่ ---------- */
      const c8 = await page.evaluate(() => {
        const f = rotationForm();
        const backup = f.items;
        f.items = [{ id: "c8_item", kind: "text", th: "ทดสอบเปลี่ยนชนิด" }]; /* เดิมเป็น scale */
        const ev = { scores: { c8_item: 4 }, answers: {}, entrust: "", comment: "" };
        const result = readRotationForm(ev);
        f.items = backup;
        return result;
      });
      t.check("เปลี่ยนชนิดข้อจากให้คะแนนเป็นข้อความแล้ว คะแนนเดิมไม่ค้างในระบบ", !("c8_item" in c8.scores));

      /* ---------- C9: นำเข้าไฟล์ JSON ที่ตัวเลือกเป็น array ของสตริงล้วน ต้องไม่ได้ค่าว่างทุกตัวเลือก ---------- */
      {
        const c9 = await page.evaluate(async () => {
          confirmDialog = async () => true;   /* คำถามยืนยันเป็นกล่องของแอปแล้ว — ตอบ "แทนที่ฟอร์ม" ให้ */
          const backup = JSON.parse(JSON.stringify(store.data.rotationForm));
          const data = { items: [
            { id: "c9item", kind: "choice", question: "ทดสอบตัวเลือกสตริงล้วน", options: ["ดี", "กลาง", "แย่"], scored: true }
          ] };
          const file = new File([JSON.stringify(data)], "form.json", { type: "application/json" });
          importRotationFormFile(file);
          await new Promise((res) => setTimeout(res, 150));
          const it = store.data.rotationForm.items.find(x => x.th === "ทดสอบตัวเลือกสตริงล้วน");
          const values = (it?.options || []).map(o => o.v);
          /* importRotationFormFile บันทึกลง localStorage เองระหว่างทาง (store.save() ภายใน)
             คืนค่าฟอร์มเดิมกลับใน store.data เฉย ๆ ไม่พอ ต้อง save() ซ้ำเพื่อล้างร่องรอยที่เพิ่งเขียนทับไว้
             ไม่งั้นฟอร์มทดสอบชั่วคราวนี้จะติดค้างใน localStorage ไปกระทบเทสต์ถัดไปในไฟล์นี้ */
          store.data.rotationForm = backup;
          store.save();
          return { values };
        });
        t.eq("นำเข้า JSON ที่ตัวเลือกเป็น array ของสตริงล้วน ได้ค่าตัวเลือกไม่ว่างสักตัว",
             c9.values.filter(v => v === ""), []);
        t.eq("ได้ครบ 3 ตัวเลือกตามไฟล์", c9.values.length, 3);
      }

      /* ---------- อัปเกรดชุดตั้งต้นให้เฉพาะฟอร์มที่ยังไม่เคยถูกแก้ ---------- */
      const upg = await page.evaluate(() => {
        const v1 = { title:"เดิม", scale:{ min:1, max:5 },
          items:[{ id:"perf", kind:"section", th:"ผลการปฏิบัติงานตลอดรอบ" },
                 { id:"knowledge", kind:"scale", th:"ความรู้" }, { id:"skill", kind:"scale", th:"ทักษะ" },
                 { id:"professional", kind:"scale", th:"วิชาชีพ" },
                 { id:"entrust", kind:"entrust", th:"entrust" },
                 { id:"comment", kind:"paragraph", role:"comment", th:"ข้อเสนอแนะ" }] };
        const d1 = { ...store.data, rotationForm: JSON.parse(JSON.stringify(v1)) };
        store.data = d1; store.migrate();
        const upgraded = store.data.rotationForm.version;
        /* ฟอร์มที่แก้เองแล้ว (เพิ่มข้อหนึ่งข้อ) ต้องไม่ถูกทับ */
        const edited = JSON.parse(JSON.stringify(v1));
        edited.items.push({ id:"mine", kind:"text", th:"ข้อที่กลุ่มงานเพิ่มเอง" });
        store.data = { ...store.data, rotationForm: edited }; store.migrate();
        return { upgraded, keptMine: store.data.rotationForm.items.some(x => x.id === "mine"),
                 keptVersion: store.data.rotationForm.version };
      });
      t.eq("ฟอร์มรุ่นเดิมที่ยังไม่เคยแก้ ถูกอัปเกรดเป็นชุดใหม่", upg.upgraded, 2);
      t.check("ฟอร์มที่กลุ่มงานแก้เองแล้ว ไม่ถูกทับ",
              upg.keptMine && !upg.keptVersion, JSON.stringify(upg));
      await page.reload();
      await page.waitForFunction(() => typeof store !== "undefined" && store.data?.rotationForm);

      /* ---------- แบบประเมินลงกองเป็นข้อมูลที่ผู้จัดหลักสูตรแก้ได้ ---------- */
      const form = await page.evaluate(async () => {
        const rot = rotationsToAssess(lastClosedMonth())[0];
        const out = {};
        /* ค่าตั้งต้นต้องใช้ id เดิมสามตัว ผลประเมินที่บันทึกไว้แล้วจึงอ่านได้ */
        openRotationEval(rot.id);
        await new Promise(r => setTimeout(r, 120));
        out.legacyField = !!document.querySelector('#dlgBody [name="sc_knowledge"]');
        closeDialog();

        /* เพิ่มข้อความยาวเข้าไปในฟอร์ม แล้วต้องมีช่องกรอกโผล่ */
        store.data.rotationForm.items.push({ id:"nextplan", kind:"paragraph", th:"แผนการพัฒนารอบหน้า" });
        store.save();
        openRotationEval(rot.id);
        await new Promise(r => setTimeout(r, 120));
        out.newField = !!document.querySelector('#dlgBody [name="an_nextplan"]');
        document.querySelector('#dlgBody [name="an_nextplan"]').value = "ฝึกอ่านฟิล์มเพิ่ม";
        document.querySelector('#dlgBody [name="sc_knowledge"][value="4"]').checked = true;
        [...document.querySelectorAll("#dlgFoot button")].find(b => /บันทึก/.test(b.textContent))?.click();
        await new Promise(r => setTimeout(r, 200));
        let ev = rotationEvalFor(rot.id);
        out.answer = ev.answers?.nextplan;
        out.notScored = ev.scores?.nextplan === undefined;
        out.scaleMax = ev.scaleMax;

        /* ลบข้อนั้นออกจากฟอร์ม — คำตอบเดิมต้องไม่หาย */
        store.data.rotationForm.items = store.data.rotationForm.items.filter(x => x.id !== "nextplan");
        store.save();
        openRotationEval(rot.id);
        await new Promise(r => setTimeout(r, 120));
        out.orphanShown = /แผนการพัฒนา|nextplan/.test(document.querySelector("#dlgBody .notice.warn")?.textContent || "");
        [...document.querySelectorAll("#dlgFoot button")].find(b => /บันทึก/.test(b.textContent))?.click();
        await new Promise(r => setTimeout(r, 200));
        ev = rotationEvalFor(rot.id);
        out.keptAfterResave = ev.answers?.nextplan;
        out.inCsv = rotationEvalCsvRows().some(row => row.some(c => String(c).includes("nextplan=")));
        return out;
      });
      t.check("ค่าตั้งต้นของฟอร์มยังใช้รหัสข้อเดิม ผลประเมินที่บันทึกไว้แล้วจึงอ่านได้", form.legacyField);
      t.check("เพิ่มข้อในฟอร์มแล้วมีช่องกรอกโผล่ในใบประเมิน", form.newField);
      t.eq("คำตอบที่เป็นข้อความเก็บแยกจากคะแนน", [form.answer, form.notScored], ["ฝึกอ่านฟิล์มเพิ่ม", true]);
      t.eq("ประทับสเกลไว้ในผลประเมิน เปลี่ยนสเกลปีหน้าแล้วผลเก่าไม่ถูกอ่านผิด", form.scaleMax, 5);
      t.check("ลบข้อออกจากฟอร์มแล้ว คำตอบเดิมยังโชว์เป็นบล็อกเตือน", form.orphanShown);
      t.eq("บันทึกซ้ำแล้วคำตอบของข้อที่ถูกลบยังอยู่ ไม่ถูกกลืนหาย", form.keptAfterResave, "ฝึกอ่านฟิล์มเพิ่ม");
      t.check("และยังส่งออกไปกับ CSV", form.inCsv);

      /* ---------- ฟอร์มที่ไม่มีข้อให้คะแนนเลย ---------- */
      const noScore = await page.evaluate(async () => {
        store.data.rotationForm.items = [{ id:"c", kind:"paragraph", role:"comment", th:"ข้อเสนอแนะ" }];
        store.data.rotationEvals = store.data.rotationEvals.map(ev => ({ ...ev, scores:{}, entrust:null, comment:"ดีขึ้นมาก" }));
        /* บล็อกก่อนหน้าพาไปหน้างานนำเสนอไว้ ต้องกลับมาหน้าลงกองก่อนถึงจะอ่านตารางถูกใบ */
        assessView.page = "month"; assessView.mineOnly = false;
        store.save(); renderAssess();
        await new Promise(r => setTimeout(r, 200));
        const cells = [...document.querySelectorAll("#assessBody tbody td")].map(td => td.textContent.trim());
        return { label: cells.find(c => /ประเมินแล้ว|เฉลี่ย/.test(c)) || "", any5: cells.some(c => c.includes("—/5")) };
      });
      t.check("ฟอร์มที่ไม่มีข้อให้คะแนน ตารางขึ้นว่าประเมินแล้ว ไม่ใช่ —/5",
              /ประเมินแล้ว/.test(noScore.label) && !noScore.any5, noScore.label);

      /* ---------- นำเข้าฟอร์มจากไฟล์ CSV ---------- */
      const imp = await page.evaluate(async () => {
        confirmDialog = async () => true;   /* คำถามยืนยันเป็นกล่องของแอปแล้ว — ตอบ "แทนที่ฟอร์ม" ให้ */
        const before = store.data.rotationEvals.length;
        const csv = ["order,id,kind,question,options,minLabel,maxLabel,required,scored,wfme",
          "1,,section,ด้านการดูแลผู้ป่วย,,,,,",
          "2,,Linear scale,ซักประวัติได้ครบถ้วน,,ต้องปรับปรุงมาก,ดีเยี่ยม,1,",
          "3,,Multiple choice,ระดับการดูแลที่มอบหมายได้,1=ต้องกำกับ|2=ทำเองบางส่วน|3=ทำเองได้,,,,1",
          "4,,paragraph,ข้อเสนอแนะ,,,,,"].join("\n");
        importRotationFormFile(new File([csv], "form.csv", { type:"text/csv" }));
        await new Promise(r => setTimeout(r, 400));
        const f = rotationForm();
        const back = rotationFormCsvRows();
        return { kinds: f.items.map(x => x.kind), maxLabel: f.scale.maxLabel,
                 opts: f.items.find(x => x.kind === "choice")?.options?.length,
                 commentRole: f.items.filter(x => x.role === "comment").length,
                 evalsUnchanged: store.data.rotationEvals.length === before,
                 headerRoundTrip: back[0].join(",") };
      });
      t.eq("นำเข้า CSV ได้ครบทุกชนิดข้อ", imp.kinds, ["section", "scale", "choice", "paragraph"]);
      t.eq("ป้ายปลายสเกลจากไฟล์ถูกนำมาใช้", imp.maxLabel, "ดีเยี่ยม");
      t.eq("ตัวเลือกของข้อแบบเลือกหนึ่งข้อถูกแยกออกมาครบ", imp.opts, 3);
      t.eq("ข้อความยาวข้อสุดท้ายถูกใช้เป็นช่องข้อเสนอแนะให้เอง", imp.commentRole, 1);
      t.check("นำเข้าฟอร์มใหม่ไม่ลบผลประเมินที่บันทึกไว้", imp.evalsUnchanged);
      t.eq("ส่งออก CSV ใช้คอลัมน์ชุดเดียวกับตอนนำเข้า",
           imp.headerRoundTrip, "order,id,kind,question,options,minLabel,maxLabel,required,scored,wfme");

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
        const sels = [...document.querySelectorAll('#dlgBody .scale-pick[data-field^="tv_"]')];
        const expected = talkEvalItemsFor(a.type).length;
        /* ให้คะแนนแค่สองข้อ เพื่อพิสูจน์ว่าค่าเฉลี่ยคิดจากข้อที่กรอกเท่านั้น ไม่นับข้อว่างเป็นศูนย์ */
        sels[0].querySelector('input[value="5"]').checked = true;
        sels[1].querySelector('input[value="3"]').checked = true;
        document.querySelector('#dlgBody [name="tvOutcome"]').value = "advice";
        document.querySelector('#dlgBody [name="assessBy"]').value = "อ.ทดสอบ";
        document.querySelector('#dlgBody [name="tvGood"]').value = "เตรียมตัวมาดี";
        document.querySelector('#dlgBody [name="assessComment"]').value = "คุมเวลาให้ดีขึ้น";
        [...document.querySelectorAll("#dlgFoot button")].find(b => /^บันทึก(ผลประเมิน|การแก้ไข)$/.test(b.textContent))?.click();
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

      /* ---------- ขั้นตอนของอาจารย์: รับรองฟอร์มว่างไม่ได้ · ค่าเฉลี่ยสดแนะนำผลโดยรวม · แก้ทับได้ ---------- */
      const flow = await page.evaluate(async () => {
        const a = visibleActivities().find(x => !x.assessment && !x.verified);
        if (!a) return null;
        const out = { id: a.id };
        openActivity(a.id);
        await new Promise(r => setTimeout(r, 150));
        /* แบบประเมินต้องมาก่อนช่องแก้ชื่อเรื่อง (ช่องยังอยู่ แต่พับไว้) */
        const body = document.querySelector("#dlgBody");
        out.rubricFirst = body.innerHTML.indexOf("data-talkform") < body.innerHTML.indexOf('name="title"');
        out.metaCollapsed = !!body.querySelector("details:not([open]) [name=\"title\"]");
        /* กดรับรองทั้งที่ยังไม่ให้คะแนน → ต้องไม่ผ่าน กล่องยังเปิด และช่องผลโดยรวมถูกทำเครื่องหมาย */
        [...document.querySelectorAll("#dlgFoot button")].find(b => b.textContent === "อาจารย์รับรอง")?.click();
        await new Promise(r => setTimeout(r, 100));
        out.stillOpen = document.querySelector("#dlg").open;
        out.notVerified = !store.data.activities.find(x => x.id === a.id).verified;
        out.outcomeInvalid = document.querySelector('#dlgBody [name="tvOutcome"]').classList.contains("invalid");
        /* ติ๊กสองข้อ 5 กับ 3 ผ่านเหตุการณ์ change จริง → เฉลี่ย 4 → แนะนำ "ผ่าน" */
        const picks = [...document.querySelectorAll('#dlgBody .scale-pick[data-field^="tv_"]')];
        const tick = (i, v) => { const el = picks[i].querySelector('input[value="' + v + '"]'); el.checked = true; el.dispatchEvent(new Event("change", { bubbles: true })); };
        tick(0, 5); tick(1, 3);
        out.meanText = document.querySelector("#dlgBody [data-talk-mean]").textContent;
        out.suggested = document.querySelector('#dlgBody [name="tvOutcome"]').value;
        tick(0, 1); tick(1, 2);
        out.suggestedLow = document.querySelector('#dlgBody [name="tvOutcome"]').value;
        /* อาจารย์เลือกเองแล้ว ระบบต้องเลิกเติมทับ */
        const sel = document.querySelector('#dlgBody [name="tvOutcome"]');
        sel.value = "advice"; sel.dispatchEvent(new Event("change", { bubbles: true }));
        tick(0, 5); tick(1, 5);
        out.keptManual = sel.value;
        document.querySelector("#dlg").close();
        return out;
      });
      if (flow) {
        t.check("แบบประเมินอยู่ก่อนช่องแก้รายละเอียด และช่องรายละเอียดพับไว้ (ยังอยู่ครบ)", flow.rubricFirst && flow.metaCollapsed);
        t.check("รับรองฟอร์มว่างไม่ได้: กล่องยังเปิด ยังไม่รับรอง และช่องผลโดยรวมถูกทำเครื่องหมาย",
                flow.stillOpen && flow.notVerified && flow.outcomeInvalid);
        t.check("ให้คะแนน 5 กับ 3 → โชว์ค่าเฉลี่ย 4 และแนะนำ 'ผ่าน'", /เฉลี่ย 4\//.test(flow.meanText) && flow.suggested === "pass", flow.meanText);
        t.eq("ให้คะแนน 1 กับ 2 → แนะนำ 'ต้องนำเสนอซ้ำ'", flow.suggestedLow, "redo");
        t.eq("อาจารย์เลือกผลเองแล้ว ระบบไม่เติมทับอีก", flow.keptManual, "advice");
      }

      /* ---------- ลงกอง: บันทึกแล้วเปิดคนถัดไป · ลบแล้วเลิกทำได้ ---------- */
      const nextFlow = await page.evaluate(async () => {
        const month = lastClosedMonth();
        const pend = rotationsToAssess(month).filter(x => !rotationEvalFor(x.id));
        if (pend.length < 2) return null;
        const first = pend[0];
        /* เปิดผ่านปุ่มในตารางจริง เพื่อให้ได้ opts.next เหมือนผู้ใช้กด */
        assessView.page = "month"; assessView.month = month; renderAssess();
        document.querySelector('#assessBody [data-rotev="' + first.id + '"]').click();
        await new Promise(r => setTimeout(r, 150));
        const out = { title1: document.querySelector("#dlgTitle").textContent };
        const nextBtn = [...document.querySelectorAll("#dlgFoot button")].find(b => /แล้วเปิดคนถัดไป/.test(b.textContent));
        out.hasNext = !!nextBtn;
        out.context = /รอบก่อนหน้า/.test(document.querySelector("#dlgBody").textContent);
        const sc = document.querySelector('#dlgBody .scale-pick[data-field^="sc_"] input[value="4"]');
        sc.checked = true; sc.dispatchEvent(new Event("change", { bubbles: true }));
        out.meanShown = /เฉลี่ย 4\//.test(document.querySelector("#dlgBody [data-rot-mean]").textContent);
        nextBtn?.click();
        await new Promise(r => setTimeout(r, 150));
        out.savedFirst = !!rotationEvalFor(first.id);
        out.openAgain = document.querySelector("#dlg").open;
        out.title2 = document.querySelector("#dlgTitle").textContent;
        document.querySelector("#dlg").close();
        return out;
      });
      if (nextFlow) {
        t.check("กล่องลงกองจากคิวมีปุ่ม 'บันทึก แล้วเปิดคนถัดไป' และมีข้อมูลประกอบ (รอบก่อนหน้า)", nextFlow.hasNext && nextFlow.context);
        t.check("ติ๊กคะแนนแล้วค่าเฉลี่ยขึ้นทันที", nextFlow.meanShown);
        t.check("กดแล้วบันทึกคนแรก และเปิดกล่องของคนถัดไปโดยอัตโนมัติ",
                nextFlow.savedFirst && nextFlow.openAgain && nextFlow.title1 !== nextFlow.title2, nextFlow.title1 + " → " + nextFlow.title2);
      }

      /* ---------- งานลงกองที่ค้าง ต้องขึ้นหน้า "วันนี้" ของอาจารย์ ข้ามทุกเดือนที่ปิดแล้ว และกดแล้วพาไปเดือนนั้น ---------- */
      const backlog = await page.evaluate(async () => {
        showView("today"); renderToday();
        const text = document.querySelector("#todayBody").textContent;
        const n = rotationBacklogFor(myStaffId()).length;
        const m = text.match(/ประเมินลงกองที่ค้าง\s*(\d+) รอบ/);
        const out = { shown: !!m, n, count: m ? +m[1] : null, hasBtn: !!document.querySelector("#todayBody [data-tgo-rot]") };
        const btn = document.querySelector("#todayBody [data-tgo-rot]");
        if (btn) {
          btn.click();
          await new Promise(r => setTimeout(r, 100));
          out.view = currentViewName(); out.page = assessView.page; out.month = assessView.month; out.btnMonth = btn.dataset.tgoRot;
          out.optionHasCount = [...document.querySelectorAll("#assessMonth option")].some(o => /ค้าง \d+/.test(o.textContent));
        }
        return out;
      });
      t.check("หน้าวันนี้ของอาจารย์มีการ์ดประเมินลงกองที่ค้าง และตัวเลขตรงกับ rotationBacklogFor()", backlog.shown && backlog.count === backlog.n, backlog.count + " / " + backlog.n);
      if (backlog.n > 0) {
        t.check("กดแถวที่ค้างแล้วไปหน้าประเมิน แท็บลงกอง เดือนของรอบนั้น",
                backlog.hasBtn && backlog.view === "assess" && backlog.page === "month" && backlog.month === backlog.btnMonth, JSON.stringify(backlog));
        t.check("ตัวเลือกเดือนบอกจำนวนที่ค้างต่อเดือน", backlog.optionHasCount);
      }

      /* ---------- C11: เปลี่ยนประเภทกิจกรรมพร้อมให้คะแนนในการบันทึกครั้งเดียวกัน
         คะแนนข้อเฉพาะประเภทเดิม (ที่พิมพ์ไว้ตอนกล่องยังวาดตามประเภทเดิม) ต้องไม่หาย ---------- */
      const c11 = await page.evaluate(async () => {
        const a = visibleActivities()[0];
        const originalType = a.type;
        const otherType = ACTIVITY_TYPES.find(t => t.id !== originalType).id;
        openActivity(a.id);
        await new Promise(r => setTimeout(r, 150));
        const items = talkEvalItemsFor(originalType);
        const extraItem = items[items.length - 1];
        const sel = document.querySelector('#dlgBody [name="tv_' + extraItem.id + '"][value="5"]');
        if (sel) sel.checked = true;
        const typeSel = document.querySelector('#dlgBody [name="type"]');
        typeSel.value = otherType;
        [...document.querySelectorAll("#dlgFoot button")].find(b => /^บันทึก(ผลประเมิน|การแก้ไข)$/.test(b.textContent))?.click();
        await new Promise(r => setTimeout(r, 200));
        const saved = store.data.activities.find(x => x.id === a.id);
        return { originalType, otherType, extraId: extraItem.id, hadSel: !!sel,
                 newType: saved.type, keptExtraScore: saved.assessment?.scores?.[extraItem.id] };
      });
      t.check("มีข้อเฉพาะประเภทเดิมให้กรอกจริง (พิสูจน์ว่าทดสอบตรงเงื่อนไข)", c11.hadSel);
      t.eq("ประเภทกิจกรรมเปลี่ยนไปตามที่เลือกในกล่องจริง", c11.newType, c11.otherType);
      t.eq("เปลี่ยนประเภทพร้อมให้คะแนนข้อเฉพาะประเภทเดิมในการบันทึกครั้งเดียวกัน คะแนนนั้นไม่หาย",
           c11.keptExtraScore, 5);

      /* pre-op กับ post-op conference ถูกยุบเป็นคาบเดียวกัน ของเก่าต้องย้ายตามให้ครบ */
      const merged = await page.evaluate(async () => {
        const d = store.data;
        const a = d.activities[0];
        a.type = "postop";
        /* ข้อมูลสาธิตไม่ลงตาราง F/P ล่วงหน้าแล้ว — สร้างแถว postop เองเพื่อพิสูจน์ว่า migration ย้ายแถวในตารางด้วย */
        const t0 = { id: "talk_postop_test", date: todayISO(), start: "09:30", end: "10:00", slot: "Post-op", type: "postop",
                     residentId: a.residentId, title: "ทดสอบ post-op", subspecialty: "trauma", location: "", moderatorId: "", activityId: null, note: "" };
        d.schedule.push(t0);
        Object.values(d.requirements).forEach(req => { req.preop = 10; req.postop = 12; });
        localStorage.setItem("mnrh_ortho_portfolio_v1", JSON.stringify(d));
        return { actId: a.id, talkId: t0?.id };
      });
      await page.reload();
      await page.waitForFunction(() => typeof store !== "undefined" && store.data?.activities?.length);
      const after = await page.evaluate((ids) => ({
        types: ACTIVITY_TYPES.map(x => x.id),
        label: TYPE_BY_ID.preop?.th,
        desc: TYPE_BY_ID.preop?.desc,
        act: store.data.activities.find(x => x.id === ids.actId)?.type,
        talk: store.data.schedule.find(x => x.id === ids.talkId)?.type,
        req: store.data.requirements[1]?.preop,
        reqOld: store.data.requirements[1]?.postop ?? null
      }), merged);
      t.check("ไม่มีประเภท post-op แยกอีกแล้ว", !after.types.includes("postop"), after.types.join(", "));
      t.eq("ชื่อที่แสดงคือ Pre/post-op conference", after.label, "Pre/post-op conference");
      t.check("มีคำอธิบายกำกับว่าคาบเดียวทำทั้งวางแผนและวิจารณ์ผล",
              /วางแผน/.test(after.desc || "") && /วิจารณ์ผล/.test(after.desc || ""), after.desc);
      t.eq("กิจกรรมเก่าที่เป็น post-op ย้ายมาอยู่ประเภทเดียวกัน", after.act, "preop");
      t.eq("รายการในตารางนำเสนอย้ายตามด้วย", after.talk, "preop");
      t.eq("เกณฑ์ของสองประเภทเดิมถูกรวมเข้าด้วยกัน ไม่ใช่ทิ้งไปข้างหนึ่ง", after.req, 22);
      t.eq("ไม่เหลือเกณฑ์ของประเภทที่ไม่มีแล้ว", after.reqOld, null);
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

    /* ---------- เลขวันที่ต้องถูกต้องในเขตเวลาไทย (UTC+7) ไม่ใช่แค่ตอนรันบนเครื่องที่ตั้ง UTC ----------
       เดิม addDaysISO/mondayOf/todayISO() แปลงวันที่ผ่าน .toISOString() ซึ่งคืนวันที่ตาม UTC เสมอ
       ในเขตเวลา UTC+ ทุกเขต ผลลัพธ์จะเพี้ยนถอยหลังไปหนึ่งวันตลอดเวลา ไม่ใช่แค่ช่วงใกล้เที่ยงคืน
       ทดสอบตรงนี้เปิดหน้าด้วย timezoneId ไทยโดยตรง ไม่พึ่ง TZ ของเครื่องที่รันเทสต์ */
    {
      const { page, errors } = await openAs(browser, srv.url, "admin", { timezoneId: "Asia/Bangkok" });
      const r = await page.evaluate(() => {
        const d = new Date();
        const wantToday = d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
        return {
          tz: Intl.DateTimeFormat().resolvedOptions().timeZone,
          identity: addDaysISO("2026-08-28", 0),
          plusOne: addDaysISO("2026-08-28", 1),
          minusOne: addDaysISO("2026-08-28", -1),
          monday: mondayOf("2026-08-28"),
          todayMatchesLocalCalendar: todayISO() === wantToday,
          today: todayISO(), wantToday
        };
      });
      t.eq("เปิดหน้าด้วยเขตเวลาไทยจริง", r.tz, "Asia/Bangkok");
      t.eq("addDaysISO บวก 0 วันได้วันเดิม แม้อยู่ในเขตเวลา UTC+7", r.identity, "2026-08-28");
      t.eq("addDaysISO บวก 1 วันถูกต้อง", r.plusOne, "2026-08-29");
      t.eq("addDaysISO ลบ 1 วันถูกต้อง", r.minusOne, "2026-08-27");
      t.eq("mondayOf หาวันจันทร์ของสัปดาห์ถูกต้องในเขตเวลาไทย (28 ส.ค. 69 เป็นวันศุกร์)", r.monday, "2026-08-24");
      t.eq("todayISO() ตรงกับปฏิทินท้องถิ่น ไม่ใช่ปฏิทิน UTC", r.today, r.wantToday);
      t.check("ทดสอบเขตเวลาไทย: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }

    /* ---------- สำรองแผนหมุนเวียนอัตโนมัติก่อนเขียนทับ + กู้คืนได้จากประวัติ ----------
       เดิม "สร้างแผนอัตโนมัติ" มีแค่ confirm + toast เลิกทำ 6 วินาที ซึ่งเป็นแค่ตัวแปรใน memory
       รีเฟรชหน้าแล้วหายทันที — เพิ่มสแนปช็อตที่เก็บลง store.data เอง จึงรอดรีเฟรชและกู้คืนทีหลังได้ */
    {
      const { page, errors } = await openAs(browser, srv.url, "admin");
      const r = await page.evaluate(async () => {
        showView("rotation");
        const ay = ayView || currentAY();
        const from = monthStartISO(ayMonths(ay)[0]), to = monthEndISO(ayMonths(ay)[11]);
        const inYearCount = () => store.data.rotations.filter(x => x.start >= from && x.start <= to).length;

        const before = inYearCount();
        const beforeBk = (store.data.rotationPlanBackups || []).length;

        document.querySelector("#btnGeneratePlan").click();
        await new Promise(res => setTimeout(res, 100));
        document.querySelector("#dlgFoot .btn-primary").click();
        await new Promise(res => setTimeout(res, 100));

        const backups = store.data.rotationPlanBackups || [];
        const created = backups[backups.length - 1];
        const genBkCreated = backups.length === beforeBk + 1 && created.source === "generate" && created.rotations.length === before;

        /* สำเนาที่เก็บไว้ต้องเป็น deep copy จริง — แก้ store.data.rotations ต่อจากนั้นไม่ควรกระทบ */
        const beforeMutateLen = created.rotations.length;
        store.data.rotations.push({ id: "rot_planbk_mutate_test", residentId: store.data.residents[0].id,
          serviceId: store.data.services[0].id, start: from, end: from, note: "" });
        const isolatedFromMutation = created.rotations.length === beforeMutateLen;
        store.data.rotations = store.data.rotations.filter(x => x.id !== "rot_planbk_mutate_test");

        /* จำลอง "รีเฟรชหน้า" ด้วย save แล้วโหลดใหม่ — พิสูจน์ว่าไม่ใช่แค่ตัวแปรใน closure เหมือน toastUndo เดิม */
        store.save();
        store.load();
        const survivedReload = (store.data.rotationPlanBackups || []).some(x => x.id === created.id);

        /* เปิดกล่องประวัติ แล้วกู้คืนรายการที่เพิ่งสร้าง */
        document.querySelector("#btnPlanHistory").click();
        await new Promise(res => setTimeout(res, 100));
        const dlgOpenAfterHistory = document.querySelector("#dlg")?.open === true;
        const rowsShown = document.querySelectorAll("#dlgBody [data-restore-plan]").length;
        document.querySelector("#dlgBody [data-restore-plan]").click();
        await new Promise(res => setTimeout(res, 100));
        /* confirmAny ต้องถามแทรกในกล่องเดิม (confirmInline) ไม่ใช่เปิด <dialog> ซ้อน — ไม่งั้น showModal() จะพัง */
        const inlineConfirmShown = !!document.querySelector(".confirm-inline");
        document.querySelector(".confirm-inline [data-ok]").click();
        await new Promise(res => setTimeout(res, 150));

        const afterRestoreCount = inYearCount();
        const afterRestoreBk = store.data.rotationPlanBackups || [];
        const restoreBkCreated = afterRestoreBk[afterRestoreBk.length - 1].source === "restore";
        const dlgClosedAfterRestore = document.querySelector("#dlg")?.open !== true;

        /* เก็บสำรองไว้ไม่เกิน 10 ชุดล่าสุดต่อปีการศึกษา */
        store.data.rotationPlanBackups = [];
        for (let i = 0; i < 12; i++)
          applyRotationPlanForAY(ay, structuredClone(store.data.rotations.filter(x => x.start >= from && x.start <= to)), "generate");
        const capped = store.data.rotationPlanBackups.length;

        return {
          before, genBkCreated, isolatedFromMutation, survivedReload,
          dlgOpenAfterHistory, rowsShown, inlineConfirmShown,
          afterRestoreCount, restoreBkCreated, dlgClosedAfterRestore, capped
        };
      });
      t.check("สร้างแผนอัตโนมัติแล้วมีสำรองใหม่ตรงจำนวนช่วงหมุนเวียนเดิม", r.genBkCreated, JSON.stringify(r));
      t.check("สำเนาที่เก็บไว้เป็น deep copy จริง ไม่กระทบเมื่อแก้ข้อมูลปัจจุบันต่อ", r.isolatedFromMutation);
      t.check("สำรองรอดจากการจำลองรีเฟรชหน้า (save แล้วโหลดใหม่)", r.survivedReload);
      t.check("เปิด 'ประวัติแผนอัตโนมัติ' เห็นรายการที่เพิ่งสร้าง", r.dlgOpenAfterHistory && r.rowsShown === 1, r.rowsShown);
      t.check("กดกู้คืนถามยืนยันแทรกในกล่องเดิม ไม่พังเพราะซ้อน dialog", r.inlineConfirmShown);
      t.eq("กู้คืนแล้วจำนวนช่วงหมุนเวียนกลับไปตรงกับก่อนสร้างแผน", r.afterRestoreCount, r.before);
      t.check("กู้คืนก็ยังสร้างสำรองใหม่ไว้ (กู้คืนผิดก็กู้คืนกลับไปอีกทีได้)", r.restoreBkCreated);
      t.check("กล่องประวัติปิดเองหลังกู้คืนเสร็จ", r.dlgClosedAfterRestore);
      t.eq("เก็บสำรองไว้สูงสุด 10 ชุดล่าสุดต่อปีการศึกษา ตัดชุดเก่าสุดทิ้ง", r.capped, 10);

      t.check("สำรองแผนอัตโนมัติ: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }

    /* ---------- staff (ไม่ใช่ผู้จัดหลักสูตร) ไม่เห็นปุ่มประวัติแผน เหมือนปุ่มสร้างแผนอัตโนมัติ ---------- */
    {
      const { page, errors } = await openAs(browser, srv.url, "staff");
      const hidden = await page.evaluate(() => {
        showView("rotation");
        return document.querySelector("#btnPlanHistory")?.hidden;
      });
      t.check("staff ไม่เห็นปุ่ม 'ประวัติแผนอัตโนมัติ'", hidden === true);
      t.check("สิทธิ์ประวัติแผน: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }

  } finally {
    await browser.close();
    await srv.close();
  }
  return t;
}
