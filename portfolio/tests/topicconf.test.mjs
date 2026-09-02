/* Topic conference (คาบส่วนกลางวันพฤหัสฯ 09:00-12:00) ต้องแยกออกจากคาบอื่นได้ชัดเจนด้วยธง topicConference
   ไม่ใช่การเทียบชื่อ string — และตารางกำหนดผู้นิเทศ+สายที่อยู่เวรต้องแก้ได้เฉพาะผู้จัดหลักสูตร */
import { chromium } from "playwright";
import { serve, launchOptions, openAs, suite } from "./lib.mjs";

export default async function run() {
  const t = suite("ผู้นิเทศ Topic conference รายสัปดาห์");
  const srv = await serve();
  const browser = await chromium.launch(launchOptions());
  try {
    const { page, errors } = await openAs(browser, srv.url, "admin");

    /* ---------- ธง topicConference ติดเฉพาะคาบ Topic conference วันพฤหัสฯ เท่านั้น ---------- */
    const flag = await page.evaluate(() => {
      const cs = store.data.services.find(x => x.central);
      const tcRow = cs.template.find(x => x.topicConference);
      const others = cs.template.filter(x => x !== tcRow);
      let iso = todayISO();
      while (new Date(iso + "T00:00:00").getDay() !== tcRow.day) iso = addDaysISO(iso, 1);
      const sessions = sessionsForDate(iso).filter(s => s.kind === "central");
      const tcSessions = sessions.filter(s => s.topicConference);
      const otherSessions = sessions.filter(s => !s.topicConference);
      return {
        templateFlagOk: !!tcRow && others.every(x => !x.topicConference),
        tcSessionNames: [...new Set(tcSessions.map(s => s.name))],
        otherHasNoFlag: otherSessions.every(s => !s.topicConference),
        sawOther: otherSessions.length > 0
      };
    });
    t.check("ธง topicConference:true มีเฉพาะคาบ Topic conference ในตารางประจำสัปดาห์", flag.templateFlagOk);
    t.check("เซสชันที่คำนวณออกมา ธงติดเฉพาะคาบ Topic conference จริง",
            flag.tcSessionNames.length === 1 && flag.tcSessionNames[0].startsWith("Topic conference"),
            JSON.stringify(flag.tcSessionNames));
    t.check("คาบอื่นวันเดียวกัน (เช่น Inter-hospital conference) ไม่ติดธงไปด้วย",
            flag.sawOther && flag.otherHasNoFlag);

    /* ---------- migration backfill: ข้อมูลเก่าไม่มีธง ต้องได้ธงคืนหลัง migrate() ครั้งเดียว ---------- */
    const backfill = await page.evaluate(() => {
      const cs = store.data.services.find(x => x.central);
      const tcRow = cs.template.find(x => x.name.startsWith("Topic conference"));
      const other = cs.template.find(x => x.day === 4 && x !== tcRow);
      delete tcRow.topicConference;
      if (other) delete other.topicConference;
      store.migrate();
      const result = { tc: tcRow.topicConference, other: other ? other.topicConference : null };
      /* migrate ครั้งที่สองต้องไม่ทับค่าที่ถูกแก้เองภายหลัง (เช่นปิดคาบนี้ชั่วคราว) เพราะเช็คด้วย == null */
      tcRow.topicConference = false;
      store.migrate();
      result.staysAfterManualOverride = tcRow.topicConference;
      tcRow.topicConference = true;
      return result;
    });
    t.eq("backfill: คาบ Topic conference ได้ธง true หลัง migrate() ครั้งเดียว", backfill.tc, true);
    t.check("backfill: คาบอื่นวันพฤหัสฯ ไม่ถูกเดาว่าเป็น Topic conference", !backfill.other, backfill.other);
    t.eq("migrate() ไม่ทับค่าที่ถูกแก้เองภายหลัง (== null เท่านั้นที่ backfill)",
         backfill.staysAfterManualOverride, false);

    /* ---------- topicConfInfo(): ไม่มีการกำหนด = "ยังไม่ได้กำหนด" เสมอ ไม่เคยเดา ---------- */
    const unset = await page.evaluate(() => {
      store.data.topicConf = [];
      const info = topicConfInfo(todayISO());
      return info;
    });
    t.eq("ยังไม่ได้กำหนดผู้นิเทศ/สาย → ทั้งสามช่องขึ้น \"ยังไม่ได้กำหนด\"",
         [unset.staffLabel, unset.teamLabel, unset.chiefLabel],
         ["ยังไม่ได้กำหนด", "ยังไม่ได้กำหนด", "ยังไม่ได้กำหนด"]);

    /* ---------- topicConfInfo(): กำหนดสายที่มีหัวหน้าสายจริง ต้องตรงกับ isChiefOn() เป๊ะ ---------- */
    const withChief = await page.evaluate(() => {
      const iso = todayISO();
      const staff = store.data.staff[0];
      let found = null;
      for (const rot of store.data.rotations) {
        const svc = serviceById(rot.serviceId);
        if (!svc?.team) continue;
        const r = store.resident(rot.residentId);
        if (r?.year === 3 && isChiefOn(r.id, rot.start)) { found = { serviceId: svc.id, iso: rot.start, chiefName: r.name }; break; }
      }
      if (!found) return { none: true };
      store.data.topicConf = [{ id: "tc_test", date: found.iso, staffId: staff.id, teamServiceId: found.serviceId }];
      const info = topicConfInfo(found.iso);
      store.data.topicConf = [];
      return { none: false, info, expectStaff: staff.name, expectChief: found.chiefName };
    });
    if (withChief.none) {
      t.check("ไม่มีสายที่มีหัวหน้าสายในข้อมูลสาธิต (ข้ามการเทียบค่า)", true, "ไม่มีข้อมูลให้ทดสอบ");
    } else {
      t.eq("กำหนดอาจารย์แล้ว topicConfInfo คืนชื่ออาจารย์ถูกต้อง", withChief.info.staffLabel, withChief.expectStaff);
      t.eq("หัวหน้าสายที่คำนวณได้ตรงกับ isChiefOn() เป๊ะ — ไม่เก็บชื่อไว้ตรง ๆ คำนวณสดทุกครั้ง",
           withChief.info.chiefLabel, withChief.expectChief);
    }

    /* ---------- ตารางในหน้าตั้งค่า: admin แก้ได้จริง ---------- */
    const adminEdit = await page.evaluate(() => {
      const cs = store.data.services.find(x => x.central);
      const tcRow = cs.template.find(x => x.topicConference);
      let iso = todayISO();
      while (new Date(iso + "T00:00:00").getDay() !== tcRow.day) iso = addDaysISO(iso, 1);
      store.data.topicConf = [];
      tcMonth = iso.slice(0, 7);
      renderTopicConfTable();
      const sel = document.querySelector('#tcTable [data-tc="' + iso + '|staffId"]');
      if (!sel) return { found: false };
      const staffId = store.data.staff[0].id;
      sel.value = staffId;
      sel.dispatchEvent(new Event("change", { bubbles: true }));
      return { found: true, saved: (store.data.topicConf.find(x => x.date === iso) || {}).staffId };
    });
    t.check("แถวของวันพฤหัสฯ ปรากฏในตาราง #tcTable", adminEdit.found);
    if (adminEdit.found) {
      const staffId = await page.evaluate(() => store.data.staff[0].id);
      t.eq("ผู้จัดหลักสูตร (admin) แก้ผู้นิเทศได้จริง", adminEdit.saved, staffId);
    }

    /* ---------- ตารางในหน้าตั้งค่า: staff แก้ไม่ได้ (toast + ข้อมูลไม่เปลี่ยน) ---------- */
    const { page: staffPage } = await openAs(browser, srv.url, "staff");
    const staffEdit = await staffPage.evaluate(() => {
      const cs = store.data.services.find(x => x.central);
      const tcRow = cs.template.find(x => x.topicConference);
      let iso = todayISO();
      while (new Date(iso + "T00:00:00").getDay() !== tcRow.day) iso = addDaysISO(iso, 1);
      store.data.topicConf = [];
      tcMonth = iso.slice(0, 7);
      renderTopicConfTable();
      const sel = document.querySelector('#tcTable [data-tc="' + iso + '|staffId"]');
      if (!sel) return { found: false };
      const before = document.querySelectorAll(".toast").length;
      sel.value = store.data.staff[0].id;
      sel.dispatchEvent(new Event("change", { bubbles: true }));
      const toastMsg = document.querySelector(".toast:last-child")?.textContent || "";
      return { found: true, toastShown: document.querySelectorAll(".toast").length > before, toastMsg,
               saved: (store.data.topicConf.find(x => x.date === iso) || {}).staffId };
    });
    t.check("staff ไม่ใช่ผู้จัดหลักสูตร: แถวยังปรากฏให้ดู (view-only ไม่ใช่ซ่อนทั้งการ์ด)", staffEdit.found);
    if (staffEdit.found) {
      t.check("staff แก้แล้วขึ้น toast บอกว่าเป็นสิทธิ์ผู้จัดหลักสูตร", staffEdit.toastShown && staffEdit.toastMsg.includes("สิทธิ์"), staffEdit.toastMsg);
      t.check("staff แก้แล้วข้อมูลไม่เปลี่ยนจริง — ไม่ใช่พึ่งการซ่อนปุ่มอย่างเดียว", !staffEdit.saved, JSON.stringify(staffEdit.saved));
    }

    t.eq("ไม่มี error หลุดในคอนโซลระหว่างทดสอบทั้งหมด", errors.length, 0);
  } finally {
    await browser.close();
    await srv.close();
  }
  return t;
}
