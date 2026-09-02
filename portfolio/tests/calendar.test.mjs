/* หน้าปฏิทิน — ตอนนี้เป็นปฏิทินการนำเสนอเท่านั้น (Trauma film, Pre/post-op conference, Topic conference,
   Journal club) รวมมาจากตารางนำเสนอเดิม ตรวจว่าช่วงวันที่ถูกต้อง (จันทร์เริ่มสัปดาห์ เดือนมีวันขอบเดือนด้วย),
   สิทธิ์การดู (resident เห็นแค่ตัวเอง ไม่มีตัวเลือกตารางรวม · staff/admin เปิดมาเป็นตารางรวมก่อน สลับไปรายคนได้),
   และผู้นิเทศ Topic conference โผล่เฉพาะคาบ topic/journal เท่านั้น ไม่ติดคาบอื่นในวันเดียวกัน */
import { chromium } from "playwright";
import { serve, launchOptions, openAs, suite } from "./lib.mjs";

export default async function run() {
  const t = suite("ปฏิทินการนำเสนอ");
  const srv = await serve();
  const browser = await chromium.launch(launchOptions());
  try {
    /* ---------- resident: ตัวเลือกตารางรวม/รายคนถูกซ่อน, chip ตรงกับ presentationsForDate ที่กรองแล้วเป๊ะ ---------- */
    {
      const { page, errors } = await openAs(browser, srv.url, "resident");
      const r = await page.evaluate(() => {
        showView("calendar");
        const scopeHidden = document.querySelector("#calScopeAll").closest("[data-perm]").hidden;
        const pickerHidden = document.querySelector("#calResidentPick").hidden;
        const rid = myResidentId();
        /* หาเดือนที่มีของฉันแน่ ๆ จากข้อมูลสาธิต (17 สัปดาห์ วนผู้นำเสนอทุกคน) แทนที่จะหวังเดือนปัจจุบันเฉย ๆ */
        const anyOfMine = store.data.schedule.find(x => x.residentId === rid) ||
          store.data.activities.find(x => x.residentId === rid);
        if (!anyOfMine) return { none: true, scopeHidden, pickerHidden };
        calMonth = anyOfMine.date.slice(0, 7);
        renderCalendar();
        const cells = [...document.querySelectorAll("#calGrid .gcal-cell")];
        const first = calMonth + "-01";
        const leadDays = (new Date(first + "T00:00:00").getDay() + 6) % 7;
        const gridStart = addDaysISO(first, -leadDays);
        const isos = Array.from({ length: 42 }, (_, i) => addDaysISO(gridStart, i));
        const want = new Set(isos.flatMap(iso =>
          presentationsForDate(iso).filter(p => p.residentId === rid).map(p => p.kind + ":" + p.id)));
        const got = new Set([...document.querySelectorAll("#calGrid [data-pres]")].map(b => b.dataset.pres));
        const extra = [...got].filter(k => !want.has(k));
        const missing = [...want].filter(k => !got.has(k));
        return { none: false, scopeHidden, pickerHidden, cellCount: cells.length, extra, missing, wantSize: want.size };
      });
      t.check("resident: ตัวเลือกตารางรวม/รายคนถูกซ่อน", r.scopeHidden);
      t.check("resident: ตัวเลือกเปลี่ยนคนถูกซ่อน", r.pickerHidden);
      if (r.none) {
        t.check("resident: ข้ามชุดนี้ — ข้อมูลสาธิตไม่มีการนำเสนอของบัญชีนี้เลย", false);
      } else {
        t.check("resident: กริดเดือนมี 42 ช่อง (6 สัปดาห์ x 7 วัน)", r.cellCount === 42, r.cellCount);
        t.check("resident: มีรายการให้ตรวจจริง (ไม่ใช่ทดสอบว่าง)", r.wantSize > 0, r.wantSize);
        t.eq("resident: ไม่มี chip เกินมาที่ไม่ใช่ของฉัน", r.extra, []);
        t.eq("resident: ไม่มี chip ของฉันตกหล่นไปจากกริด", r.missing, []);
      }
      t.check("resident: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }

    /* ---------- staff/admin: เปิดมาเป็น "ตารางรวม" ก่อน เห็นของหลายคนพร้อมกัน ไม่ต้องเลือกใคร
       สลับไป "รายคน" แล้วยังไม่เดาเอาคนแรก ต้องเลือกก่อนเหมือนเดิม ---------- */
    for (const role of ["staff", "admin"]) {
      const { page, errors } = await openAs(browser, srv.url, role);
      const r = await page.evaluate(() => {
        const residentIdOf = (b) => {
          const i = b.dataset.pres.indexOf(":");
          const kind = b.dataset.pres.slice(0, i), id = b.dataset.pres.slice(i + 1);
          const list = kind === "schedule" ? store.data.schedule : store.data.activities;
          return list.find(x => x.id === id)?.residentId;
        };
        showView("calendar");
        const scopeAllCurrent = document.querySelector("#calScopeAll").getAttribute("aria-current") === "true";
        const pickerHiddenOnAll = document.querySelector("#calResidentPick").hidden;
        const residentIds = new Set([...document.querySelectorAll("#calGrid [data-pres]")].map(residentIdOf).filter(Boolean));

        document.querySelector("#calScopeMine").click();
        const pickerShownOnMine = !document.querySelector("#calResidentPick").hidden;
        const emptyBeforePick = !!document.querySelector("#calGrid .empty");

        const other = store.data.residents[0];
        const sel = document.querySelector("#calResidentPick");
        sel.value = other.id; sel.dispatchEvent(new Event("change", { bubbles: true }));
        const afterPickResident = calResidentId;
        const chipsMatchPicked = [...document.querySelectorAll("#calGrid [data-pres]")].every(b => residentIdOf(b) === other.id);
        return {
          scopeAllCurrent, pickerHiddenOnAll, residentCount: residentIds.size,
          pickerShownOnMine, emptyBeforePick, afterPickResident, wantAfter: other.id, chipsMatchPicked
        };
      });
      t.check(role + ": เปิดหน้ามาเป็นตารางรวมก่อน (ไม่ต้องเลือกใคร)", r.scopeAllCurrent);
      t.check(role + ": โหมดตารางรวมซ่อนตัวเลือกคน", r.pickerHiddenOnAll);
      t.check(role + ": ตารางรวมเห็นของหลายคนพร้อมกันในเดือนเดียว", r.residentCount > 1, r.residentCount);
      t.check(role + ": สลับมารายคนแล้วโชว์ตัวเลือกคน", r.pickerShownOnMine);
      t.check(role + ": รายคนที่ยังไม่เลือกใครขึ้นว่างไว้ก่อน ไม่เดาเอาคนแรก", r.emptyBeforePick);
      t.eq(role + ": เลือกแพทย์ประจำบ้านคนอื่นแล้วกริดตามค่าที่เลือกจริง", r.afterPickResident, r.wantAfter);
      t.check(role + ": ทุก chip ที่เห็นเป็นของคนที่เลือกเท่านั้น", r.chipsMatchPicked);
      t.check(role + ": ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }

    /* ---------- Topic conference: chip มีบรรทัดผู้นิเทศ+หัวหน้าสาย เฉพาะ topic/journal คาบอื่นไม่มี ---------- */
    {
      const { page, errors } = await openAs(browser, srv.url, "admin");
      const r = await page.evaluate(() => {
        showView("calendar");
        const tcEntry = store.data.schedule.find(x => x.type === "topic");
        if (!tcEntry) return { none: true };
        store.data.topicConf = [{ id: "tc_cal_test", date: tcEntry.date, staffId: store.data.staff[0].id, teamServiceId: "" }];
        calMonth = tcEntry.date.slice(0, 7); calScope = "all";
        renderCalendar();
        const chips = [...document.querySelectorAll("#calGrid .gcal-chip")];
        const tcChip = chips.find(b => b.dataset.pres === "schedule:" + tcEntry.id);
        const otherChips = chips.filter(b => {
          if (b === tcChip) return false;
          const i = b.dataset.pres.indexOf(":");
          const kind = b.dataset.pres.slice(0, i), id = b.dataset.pres.slice(i + 1);
          if (kind !== "schedule") return true;
          const rec = store.data.schedule.find(x => x.id === id);
          return rec && rec.type !== "topic" && rec.type !== "journal";
        });
        store.data.topicConf = [];
        return {
          none: false,
          hasTcInfo: !!tcChip?.querySelector(".tc-info"), tcText: tcChip?.querySelector(".tc-info")?.textContent || "",
          otherHasNoInfo: otherChips.every(b => !b.querySelector(".tc-info")),
          otherCount: otherChips.length
        };
      });
      if (r.none) {
        t.check("ข้ามชุดนี้ — ข้อมูลสาธิตไม่มีคาบ topic conference เลย", false);
      } else {
        t.check("มีคาบ Topic conference ในกริด และมีบรรทัดผู้นิเทศ/หัวหน้าสาย", r.hasTcInfo, r.tcText);
        t.check("บรรทัดผู้นิเทศพูดถึงอาจารย์ที่กำหนดไว้", r.tcText.includes("ผู้นิเทศ"), r.tcText);
        t.check("คาบ trauma film/pre-post-op ในเดือนเดียวกันไม่มีบรรทัดผู้นิเทศติดไปด้วย",
          r.otherHasNoInfo && r.otherCount > 0, r.otherCount + " คาบอื่น");
      }

      /* คลิก chip ที่มาจากตารางที่ลงล่วงหน้า (schedule) เปิด editTalk() */
      const click = await page.evaluate(() => {
        const b = document.querySelector('#calGrid button[data-pres^="schedule:"]');
        if (!b) return { none: true };
        b.click();
        const open = !!document.querySelector("#dlg")?.open;
        const title = document.querySelector("#dlgTitle")?.textContent || "";
        if (open) document.querySelector("#dlg").close();
        return { none: false, open, title };
      });
      t.check("คลิก chip ที่มาจากตารางนำเสนอเปิดกล่องแก้ไขรายการได้",
        click.none || (click.open && click.title.includes("ตารางนำเสนอ")), JSON.stringify(click));

      t.check("Topic conference: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }
  } finally {
    await browser.close();
    await srv.close();
  }
  return t;
}
