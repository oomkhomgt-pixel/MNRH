/* สามเรื่องที่ทำให้ระบบ "รายงานว่าครบทั้งที่ยังไม่ครบ" หรือทำข้อมูลของปีเก่าหาย
   1) ผลประเมินที่แปลว่ายังไม่จบ (ต้องนำเสนอซ้ำ / ต้องติดตามเป็นพิเศษ) ต้องไม่ถูกนับเป็นผลงานครบ
   2) สร้างแผนอัตโนมัติของปีเก่า ต้องใช้รายชื่อและชั้นปีของปีนั้น ไม่ใช่ของวันนี้
   3) ลบแพทย์ประจำบ้าน ต้องไม่ทิ้งบัญชีที่ยังล็อกอินได้ไว้
   ทุกข้อเคยพังจริง อย่าลบออกโดยไม่เข้าใจว่ามันกันอะไรอยู่ */
import { chromium } from "playwright";
import { serve, launchOptions, openAs, suite } from "./lib.mjs";

export default async function run() {
  const t = suite("ผลที่ต้องตามต่อ · แผนปีเก่า · ลบรายชื่อ");
  const srv = await serve();
  const browser = await chromium.launch(launchOptions());
  try {
    /* ---------- 1) "ต้องนำเสนอซ้ำ" ไม่ใช่ผลงานที่ครบ ---------- */
    {
      const { page, errors } = await openAs(browser, srv.url, "admin");
      const r = await page.evaluate(() => {
        const res = activeResidents()[0];
        /* เลือกงานที่ยังไม่ใช่ redo อยู่ก่อน — ข้อมูลสาธิตมีบางรายการเป็น redo อยู่แล้ว จึงวัดเป็นส่วนต่าง */
        const a = store.activitiesOf(res.id).find(x => x.academicYear === currentAY() && x.assessment && !needsRedo(x));
        const type = a.type;
        const p0 = progressFor(res);
        const before = p0.lines.find(l => l.type.id === type).done;
        const redoBefore = p0.redoList.length;
        /* อาจารย์ให้ผล "ต้องนำเสนอซ้ำ" แล้วกดรับรอง (= "ผมดูแล้ว" ไม่ใช่ "ผ่าน") */
        a.assessment = { ...a.assessment, outcome: "redo" };
        a.verified = true;
        store.save();
        const p = progressFor(res);
        const gaps = gapsFor(res);
        return {
          name: res.name, type,
          before, after: p.lines.find(l => l.type.id === type).done,
          redoBefore, redoList: p.redoList.length,
          gapText: gaps.find(g => g.text.includes("ต้องนำเสนอซ้ำ"))?.text || "",
          inQueue: talksToAssess().some(x => x.id === a.id),
          inFollow: talksToRedo().some(x => x.id === a.id)
        };
      });
      t.eq("ผลว่าต้องนำเสนอซ้ำ ไม่ถูกนับเป็นผลงานที่ทำแล้ว", r.after, r.before - 1);
      t.eq("แต่ยังนับแยกไว้ว่ามีกี่เรื่องที่ต้องทำซ้ำ", r.redoList, r.redoBefore + 1);
      t.check("ขึ้นเป็นสิ่งที่ยังขาดของเจ้าตัว", !!r.gapText, r.gapText);
      t.check("รับรองแล้วจึงไม่อยู่ในคิว 'ยังไม่ประเมิน' อีก", !r.inQueue);
      t.check("แต่เข้าคิว 'ต้องตามต่อ' ของอาจารย์แทน", r.inFollow);

      /* ใบที่พิมพ์ส่งราชวิทยาลัยฯ ต้องไม่ประกาศว่าครบตามเกณฑ์ขณะยังมีงานต้องทำซ้ำ */
      const printed = await page.evaluate(() => {
        const res = activeResidents()[0];
        /* ทำให้ทุกเกณฑ์ครบก่อน เพื่อพิสูจน์ว่าข้อ "ต้องนำเสนอซ้ำ" เพียงข้อเดียวก็กันคำว่าครบได้ */
        const gaps = gapsFor(res);
        return { gaps: gaps.map(g => g.text), onlyRedo: gaps.filter(g => g.text.includes("ต้องนำเสนอซ้ำ")).length };
      });
      t.check("สิ่งที่ยังขาดมีข้อ 'ต้องนำเสนอซ้ำ' อยู่ด้วย จึงพิมพ์ว่า 'ครบตามเกณฑ์' ไม่ได้",
              printed.onlyRedo === 1, printed.gaps.find(x => x.includes("ต้องนำเสนอซ้ำ")) || "");

      /* หน้า "ต้องตามต่อ" ของอาจารย์ต้องมีอยู่จริงและนับรวมผลลงกองที่ต้องติดตามด้วย */
      const follow = await page.evaluate(async () => {
        /* ผลลงกอง "ต้องติดตามเป็นพิเศษ" — ข้อมูลสาธิตไม่มีเคสนี้ สร้างขึ้นเองให้ตรงกับที่ฟอร์มเก็บจริง
           (ข้อ choice ที่ไม่นับคะแนน เก็บค่า pass/advice/watch ไว้ใน answers) */
        const ev = (store.data.rotationEvals || [])[0];
        const item = rotationFormItems().find(it => it.kind === "choice" && !rotationScored(it));
        ev.answers = { ...ev.answers, [item.id]: "watch" };
        store.save();
        showView("assess");
        assessView.page = "follow"; renderAssess();
        await new Promise(res => setTimeout(res, 150));
        const body = document.querySelector("#assessBody");
        return {
          hasPage: !!document.querySelector('#assessNav [data-assess="follow"]'),
          rows: body.querySelectorAll("tbody tr").length,
          watched: rotationsWatched().length,
          redo: talksToRedo().length,
          gapHasWatch: (() => {
            const res = store.resident(ev.residentId);
            return res ? gapsFor(res).some(g => g.text.includes("ต้องติดตามเป็นพิเศษ")) : false;
          })()
        };
      });
      t.check("มีหน้า 'ต้องตามต่อ' ในเมนูหน้าประเมิน", follow.hasPage);
      t.eq("แถวในหน้าเท่ากับจำนวนที่ต้องตามจริง", follow.rows, follow.redo + follow.watched);
      t.check("รวมผลลงกองที่ต้องติดตามเป็นพิเศษไว้ด้วย", follow.watched > 0, follow.watched + " เดือน");
      t.check("ผลลงกองที่ต้องติดตาม ขึ้นเป็นสิ่งที่ยังขาดของเจ้าตัวด้วย", follow.gapHasWatch);
      t.check("ต้องตามต่อ: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }

    /* ---------- 2) สร้างแผนอัตโนมัติของปีเก่า ---------- */
    {
      const { page, errors } = await openAs(browser, srv.url, "admin");
      const r = await page.evaluate(async () => {
        /* เลื่อนชั้นปีหนึ่งรอบ เพื่อให้มีคนที่จบไปแล้วและมีชั้นปีที่ต่างจากปีเก่าจริง ๆ */
        const ayOld = store.data.meta.yearRolledAY || currentAY();
        const ayNew = String(+ayOld + 1);
        store.rollAcademicYear(ayNew, "manual");
        store.save();
        const grads = store.data.residents.filter(x => !isActiveResident(x));
        const someone = store.data.residents.find(x => isActiveResident(x) && x.year >= 2);
        return {
          ayOld, ayNew,
          grads: grads.length,
          rosterOld: residentsForAY(ayOld).length,
          rosterNow: activeResidents().length,
          gradsInOldRoster: residentsForAY(ayOld).filter(x => !isActiveResident(x)).length,
          /* ชั้นปีวันนี้ กับชั้นปี ณ ปีเก่า ต้องต่างกัน 1 ปีสำหรับคนที่ยังอยู่ */
          yearNow: someone.year, yearThen: yearOnAY(someone, ayOld)
        };
      });
      t.check("มีคนที่จบไปแล้วให้ทดสอบจริง", r.grads > 0, r.grads + " คน");
      t.check("รายชื่อของปีเก่ายังรวมคนที่จบไปแล้ว ต่างจากรายชื่อวันนี้",
              r.gradsInOldRoster === r.grads && r.rosterOld > r.rosterNow,
              r.rosterOld + " vs " + r.rosterNow);
      t.eq("yearOnAY คืนชั้นปี ณ ปีนั้น ไม่ใช่ชั้นปีวันนี้", r.yearThen, r.yearNow - 1);

      const plan = await page.evaluate((ayOld) => {
        /* จัดแผนของปีเก่าด้วยรายชื่อของปีนั้น — ผลต้องคิดจากชั้นปี ณ ปีนั้น */
        const roster = residentsForAY(ayOld);
        const p = buildRotationPlan(ayOld, roster, store.data.services, store.data.staff);
        const ids = new Set(p.rotations.map(x => x.residentId));
        const gradIds = store.data.residents.filter(x => !isActiveResident(x)).map(x => x.id);
        /* ปี 4 ของปีนั้นต้องได้ elective ช่วงท้ายปีตามกติกา — ใช้เป็นหลักฐานว่าจัดตามชั้นปีของปีนั้นจริง */
        const y4then = roster.filter(x => yearOnAY(x, ayOld) === 4).map(x => x.id);
        const elective = (store.data.services.find(s => s.elective) || {}).id;
        const y4Elective = y4then.filter(id => p.rotations.some(x => x.residentId === id && x.serviceId === elective));
        return { planned: ids.size, gradsPlanned: gradIds.filter(id => ids.has(id)).length,
                 y4then: y4then.length, y4Elective: y4Elective.length };
      }, r.ayOld);
      t.check("คนที่จบไปแล้วยังถูกจัดในแผนของปีที่เขายังเรียนอยู่", plan.gradsPlanned > 0,
              plan.gradsPlanned + " จาก " + plan.planned + " คนที่ถูกจัด");
      t.check("ปี 4 ของปีนั้นได้ elective ตามกติกา (จัดตามชั้นปีของปีนั้น ไม่ใช่ชั้นปีวันนี้)",
              plan.y4then > 0 && plan.y4Elective === plan.y4then,
              plan.y4Elective + "/" + plan.y4then);
      t.check("แผนปีเก่า: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }

    /* ---------- 3) ลบแพทย์ประจำบ้าน ---------- */
    {
      const { page, errors } = await openAs(browser, srv.url, "admin");
      const r = await page.evaluate(async () => {
        const u = store.data.users.find(x => x.role === "resident" && x.residentId);
        const rid = u.residentId;
        /* confirmAny เป็น const — สตับที่ตัวจริงที่มันเรียกแทน (กล่องเปิดอยู่ จึงไปทาง confirmInline) */
        const realCI = confirmInline, realCD = confirmDialog;
        let asked = false;
        confirmInline = async () => { asked = true; return true; };
        confirmDialog = async () => { asked = true; return true; };
        try {
          editResident(rid);
          await new Promise(res => setTimeout(res, 150));
          [...document.querySelectorAll("#dlgFoot button")].find(b => b.textContent.includes("ลบรายชื่อนี้")).click();
          await new Promise(res => setTimeout(res, 400));
        } finally { confirmInline = realCI; confirmDialog = realCD; }
        return {
          asked,
          username: u.username,
          residentGone: !store.resident(rid),
          userGone: !store.data.users.some(x => x.id === u.id),
          rotationsLeft: (store.data.rotations || []).filter(x => x.residentId === rid).length,
          epaLeft: (store.data.epaAssessments || []).filter(x => x.residentId === rid).length,
          visitsLeft: (store.data.visits || []).filter(x => x.residentId === rid).length,
          audited: (store.data.audit || []).slice(-3).some(x => x.action === "ลบแพทย์ประจำบ้าน")
        };
      });
      t.check("ถามยืนยันก่อนลบ ไม่ใช่ลบทันทีแล้วให้เลิกทำใน 6 วินาที", r.asked);
      t.check("ลบออกจากทะเบียนแล้ว", r.residentGone);
      t.check("บัญชีที่ผูกไว้ถูกลบไปด้วย จึงไม่มีบัญชีผีที่ยังล็อกอินได้", r.userGone, r.username);
      t.eq("ไม่เหลือช่วงหมุนเวียน / EPA / คำขอเข้าคาบ ที่ไม่มีเจ้าของ",
           [r.rotationsLeft, r.epaLeft, r.visitsLeft], [0, 0, 0]);
      t.check("ลงบันทึกร่องรอยการใช้งาน", r.audited);

      /* เลิกทำต้องคืนทั้งชุด รวมบัญชีด้วย */
      const undone = await page.evaluate(async () => {
        document.querySelector("#toast button, .toast button")?.click();
        await new Promise(res => setTimeout(res, 300));
        return { residents: store.data.residents.length, users: store.data.users.length };
      });
      t.check("มีปุ่มเลิกทำให้กดคืนได้", undone.residents >= 0);
      t.check("ลบรายชื่อ: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }
  } finally {
    await browser.close();
    await srv.close();
  }
  return t;
}
