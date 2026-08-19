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
      return { name: cs.name, gotIt: all.length, residents: store.data.residents.length,
               everyoneHasStaff: all.every(s => s.staffIds.length > 0),
               multiStaff: all[0]?.staffIds.length ?? 0 };
    });
    t.check("มีตารางส่วนกลางของภาควิชาในข้อมูล", !!central.name, central.name);
    t.eq("คาบส่วนกลางเกิดกับแพทย์ประจำบ้านทุกคน", central.gotIt, central.residents);
    t.check("คาบส่วนกลางมีอาจารย์ผู้รับผิดชอบครบ", central.everyoneHasStaff);
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
      for (let i = 0; i < 14; i++)
        sessionsForDate(addDaysISO(todayISO(), i))
          .filter(s => s.kind === "central" && (s.superseded || s.clash))
          .forEach(s => bad.push(s.name));
      return bad;
    });
    t.eq("ประชุมเช้าที่ระบุเวลาไว้ ไม่ขึ้นว่าชนกับ ward round", noFalseClash.length, 0);

    /* ---------- วนหน่วยอนุสาขาแต่ยังสังกัดสาย: หน่วยชนะสายตามลำดับความสำคัญ ---------- */
    const both = await page.evaluate(() => {
      const rot = store.data.rotations.find(r => r.alsoServiceId &&
        serviceById(r.serviceId)?.subUnit && serviceById(r.alsoServiceId)?.team);
      if (!rot) return null;
      const found = [];
      for (let i = 0; i < 7; i++)
        sessionsForDate(addDaysISO(rot.start, i))
          .filter(s => s.residentId === rot.residentId && (s.superseded || s.clash))
          .forEach(s => found.push({ kind: s.kind, name: s.name, by: s.supersededBy || s.clash, sup: !!s.superseded }));
      return { found, teamLost: found.every(x => x.kind === "team" && x.sup) };
    });
    t.check("คนที่วน sub และยังสังกัดสาย มีคาบชนกันจริง", both && both.found.length > 0,
            both ? both.found.length + " คาบใน 7 วันแรก" : "ไม่มีข้อมูลสาธิต");
    t.check("หน่วยอนุสาขาชนะสาย และคาบของสายถูกทำเครื่องหมายว่าแพ้", both?.teamLost === true);

    /* ---------- คาบที่แพ้ ไม่ถูกนับเป็นงานค้างประเมิน ---------- */
    t.check("คาบที่แพ้ไม่กลายเป็นงานค้างของอาจารย์", await page.evaluate(() =>
      pendingEvaluations(30).every(s => !s.superseded)));

    /* ---------- ลำดับความสำคัญเท่ากัน = ระบบไม่ตัดสินให้ แต่บอกว่าชน ---------- */
    const tie = await page.evaluate(() => {
      store.data.programme.sessionPriority.team = store.data.programme.sessionPriority.subUnit;
      const rot = store.data.rotations.find(r => r.alsoServiceId && serviceById(r.serviceId)?.subUnit);
      const out = [];
      for (let i = 0; i < 7; i++)
        sessionsForDate(addDaysISO(rot.start, i))
          .filter(s => s.residentId === rot.residentId && (s.superseded || s.clash))
          .forEach(s => out.push({ sup: !!s.superseded, clash: !!s.clash }));
      store.data.programme.sessionPriority.team = SESSION_PRIORITY_DEFAULT.team;
      return out;
    });
    t.check("ลำดับเท่ากัน: ไม่มีคาบไหนถูกตัดสินให้แพ้", tie.length > 0 && tie.every(x => !x.sup && x.clash),
            tie.length + " คาบถูกทำเครื่องหมายว่าชนกันโดยไม่ตัดสินแทน");

    /* ---------- ตารางส่วนกลางไม่ใช่หน่วยที่ใครไปประจำ ---------- */
    t.check("ตารางส่วนกลางไม่อยู่ในตัวเลือกของช่วงหมุนเวียน", await page.evaluate(() =>
      rotatableServices().every(x => !x.central) && store.data.services.some(x => x.central)));
    t.check("ตัวจัดแผนหมุนเวียนไม่เอาคนไปลงตารางส่วนกลาง", await page.evaluate(() => {
      const plan = buildRotationPlan(currentAY(), store.data.residents, store.data.services);
      return plan.rotations.every(r => !serviceById(r.serviceId)?.central);
    }));

    t.check("ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
    await page.close();
  } finally {
    await browser.close();
    await srv.close();
  }
  return t;
}
