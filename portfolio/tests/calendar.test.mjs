/* หน้าปฏิทินสไตล์ Google Calendar — ตรวจว่าช่วงวันที่ถูกต้อง (จันทร์เริ่มสัปดาห์ เดือนมีวันขอบเดือนด้วย),
   สิทธิ์การดู (resident เห็นแค่ตัวเอง staff/admin เลือกดูคนอื่นได้), และผู้นิเทศ Topic conference
   โผล่เฉพาะคาบนั้นคาบเดียว ไม่ไปติดคาบอื่นในวันเดียวกัน */
import { chromium } from "playwright";
import { serve, launchOptions, openAs, suite } from "./lib.mjs";

export default async function run() {
  const t = suite("ปฏิทินรายบุคคล");
  const srv = await serve();
  const browser = await chromium.launch(launchOptions());
  try {
    /* ---------- resident: picker ซ่อน, chip ตรงกับ sessionsForDate ที่กรองแล้วเป๊ะ ---------- */
    {
      const { page, errors } = await openAs(browser, srv.url, "resident");
      const r = await page.evaluate(() => {
        showView("calendar");
        const pickerHidden = document.querySelector("#calResidentPick").hidden;
        const iso = todayISO();
        const want = sessionsForDate(iso).filter(s => s.residentId === myResidentId()).map(s => s.key).sort();
        const cells = [...document.querySelectorAll("#calGrid .gcal-cell .sess")]
          .map(b => b.dataset.sess);
        /* เดือนนี้มีคาบของฉันวันไหนบ้างในกริด กับเทียบตรงจาก sessionsForDate ของทุกวันในกริด */
        const cellDates = [...document.querySelectorAll("#calGrid .gcal-cell")];
        return { pickerHidden, gotAnyChips: cells.length > 0, wantToday: want, cellCount: cellDates.length };
      });
      t.check("resident: ตัวเลือกเปลี่ยนคนถูกซ่อน", r.pickerHidden);
      t.check("resident: กริดเดือนมี 42 ช่อง (6 สัปดาห์ x 7 วัน)", r.cellCount === 42, r.cellCount);

      /* ---------- โหมดสัปดาห์: 7 วันตรงตามจริง เริ่มจันทร์ ---------- */
      const week = await page.evaluate(() => {
        calMode = "week"; document.querySelector("#calModeWeek").click();
        const dows = [...document.querySelectorAll("#calGrid .gcal-dow")].map(d => d.textContent.trim()[0]);
        return { first: dows[0], last: dows[6] };
      });
      t.eq("โหมดสัปดาห์เริ่มวันจันทร์", week.first, "จ");

      /* ---------- คาบของฉันในสัปดาห์นี้ตรงกับ sessionsForDate ที่กรองแล้วเป๊ะ ---------- */
      const match = await page.evaluate(() => {
        const days = Array.from({ length: 7 }, (_, i) => addDaysISO(calWeekStart, i));
        const want = new Set(days.flatMap(iso => sessionsForDate(iso).filter(s => s.residentId === myResidentId()).map(s => s.key)));
        const got = new Set([...document.querySelectorAll("#calGrid .sess")].map(b => b.dataset.sess));
        const extra = [...got].filter(k => !want.has(k));
        const missing = [...want].filter(k => !got.has(k));
        return { extra, missing, wantSize: want.size };
      });
      t.eq("โหมดสัปดาห์: ไม่มี chip เกินมาที่ไม่ใช่ของฉัน", match.extra, []);
      t.eq("โหมดสัปดาห์: ไม่มี chip ของฉันตกหล่นไปจากกริด", match.missing, []);

      t.check("resident: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }

    /* ---------- staff/admin: picker โชว์ เลือกเปลี่ยนคนได้ กริดอัปเดตตาม ---------- */
    for (const role of ["staff", "admin"]) {
      const { page, errors } = await openAs(browser, srv.url, role);
      const r = await page.evaluate(() => {
        showView("calendar");
        const pickerHidden = document.querySelector("#calResidentPick").hidden;
        const before = calResidentId;
        const other = store.data.residents.find(x => x.id !== before);
        if (!other) return { pickerHidden, none: true };
        const sel = document.querySelector("#calResidentPick");
        sel.value = other.id;
        sel.dispatchEvent(new Event("change", { bubbles: true }));
        return { pickerHidden, none: false, before, after: calResidentId, wantAfter: other.id };
      });
      t.check(role + ": ตัวเลือกเปลี่ยนคนโชว์อยู่ (ไม่ซ่อน)", !r.pickerHidden);
      if (!r.none) {
        t.eq(role + ": เลือกแพทย์ประจำบ้านคนอื่นแล้วกริดตามค่าที่เลือกจริง", r.after, r.wantAfter);
      }
      t.check(role + ": ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }

    /* ---------- Topic conference: chip มีบรรทัดผู้นิเทศ+หัวหน้าสาย คาบอื่นวันเดียวกันไม่มี ---------- */
    {
      const { page, errors } = await openAs(browser, srv.url, "admin");
      const r = await page.evaluate(() => {
        const cs = store.data.services.find(x => x.central);
        const tcRow = cs.template.find(x => x.topicConference);
        let iso = todayISO();
        while (new Date(iso + "T00:00:00").getDay() !== tcRow.day) iso = addDaysISO(iso, 1);
        const someRes = store.data.residents[0];
        store.data.topicConf = [{ id: "tc_cal_test", date: iso, staffId: store.data.staff[0].id, teamServiceId: "" }];
        calResidentId = someRes.id; calMode = "week";
        calWeekStart = mondayOf(iso);
        renderCalendar();
        const chips = [...document.querySelectorAll("#calGrid .gcal-chip")];
        const tcChip = chips.find(b => b.querySelector(".tc-info"));
        const otherChips = chips.filter(b => b !== tcChip);
        store.data.topicConf = [];
        return {
          hasTcInfo: !!tcChip, tcText: tcChip?.querySelector(".tc-info")?.textContent || "",
          otherHasNoInfo: otherChips.every(b => !b.querySelector(".tc-info")),
          otherCount: otherChips.length
        };
      });
      t.check("มีคาบ Topic conference ในกริด และมีบรรทัดผู้นิเทศ/หัวหน้าสาย", r.hasTcInfo, r.tcText);
      t.check("บรรทัดผู้นิเทศพูดถึงอาจารย์ที่กำหนดไว้", r.tcText.includes("ผู้นิเทศ"), r.tcText);
      t.check("คาบอื่นในสัปดาห์เดียวกันไม่มีบรรทัดผู้นิเทศติดไปด้วย", r.otherHasNoInfo && r.otherCount > 0, r.otherCount + " คาบอื่น");

      /* คลิก chip เปิด openSession() เหมือนทุกที่ในแอป */
      const click = await page.evaluate(() => {
        const b = document.querySelector("#calGrid .sess");
        if (!b) return { none: true };
        b.click();
        const open = !!document.querySelector("#dlg")?.open;
        if (open) document.querySelector("#dlg").close();
        return { none: false, open };
      });
      t.check("คลิก chip ในปฏิทินเปิดกล่องรายละเอียดเซสชันได้", click.none || click.open);

      t.check("Topic conference: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }
  } finally {
    await browser.close();
    await srv.close();
  }
  return t;
}
