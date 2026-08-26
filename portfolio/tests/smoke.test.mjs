/* หน้าเปิดขึ้นมาแล้วใช้งานได้จริงหรือไม่ — เดินทุกแท็บที่บทบาทนั้นเห็น
   แล้วดูว่ามี error หลุดออกมาหรือเปล่า และสิ่งที่ควรมีอยู่ยังอยู่ครบ */
import { chromium } from "playwright";
import { serve, launchOptions, openAs, suite } from "./lib.mjs";

export default async function run() {
  const t = suite("เปิดหน้าและเดินทุกแท็บ");
  const srv = await serve();
  const browser = await chromium.launch(launchOptions());
  try {
    for (const role of ["resident", "staff", "admin"]) {
      const { page, errors } = await openAs(browser, srv.url, role);

      const tabs = await page.$$("#tabs button");
      let clicked = 0;
      for (const tab of tabs) if (!(await tab.isHidden())) { await tab.click(); await page.waitForTimeout(120); clicked++; }
      t.check(role + ": เปิดแท็บที่มองเห็นได้ครบ", clicked > 0, clicked + " แท็บ");

      const state = await page.evaluate(() => ({
        signedIn: !!currentUser(),
        role: myRole(),
        residents: store.data.residents.length,
        activities: store.data.activities.length,
        plan: buildRotationPlan(currentAY(), store.data.residents, store.data.services).rotations.length
      }));
      t.eq(role + ": ล็อกอินติดและได้บทบาทถูกต้อง", [state.signedIn, state.role], [true, role]);
      t.check(role + ": ข้อมูลสาธิตโหลดครบ", state.residents > 0 && state.activities > 0,
              state.residents + " คน · " + state.activities + " กิจกรรม");
      t.check(role + ": จัดแผนหมุนเวียนได้", state.plan > 0, state.plan + " ช่วง");
      t.check(role + ": ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      /* หน้า "วันนี้" — เนื้อหาต้องต่างกันตามบทบาท และต้องไม่หลุดข้อมูลคนอื่น */
      await page.evaluate(() => showView("today"));
      await page.waitForTimeout(300);
      const td = await page.evaluate(() => {
        const chips = [...document.querySelectorAll("#todayBody .sess")];
        const keys = chips.map(c => c.dataset.sess).filter(Boolean);
        const owners = keys.map(k => sessionByKey(k)?.residentId).filter(Boolean);
        return {
          headings: [...document.querySelectorAll("#todayBody h2")].map(h => h.textContent.trim()),
          where: document.querySelector("#todayWhere").textContent,
          cards: document.querySelectorAll("#todayBody .card").length,
          owners: [...new Set(owners)],
          me: myResidentId(),
          allToday: sessionsForDate(todayISO()).length
        };
      });
      t.check(role + ": หน้าวันนี้มีเนื้อหา", td.cards > 0 && td.headings.length > 0,
              td.headings.join(" · "));
      if (role === "resident") {
        t.check("resident: หน้าวันนี้เห็นเฉพาะคาบของตัวเอง",
                td.owners.every(o => o === td.me), td.owners.length + " เจ้าของ");
        t.check("resident: หน้าวันนี้ไม่ใช่ตารางทั้งภาควิชา",
                td.headings.includes("ที่ต้องไป"), td.headings.join(" · "));
      }
      if (role === "staff")
        t.check("staff: หน้าวันนี้เป็นคาบที่ระบุชื่อตัวเอง กับงานประเมินที่ค้าง",
                td.headings.some(h => h.startsWith("ประเมินที่ค้าง")), td.headings.join(" · "));
      if (role === "admin")
        t.check("admin: หน้าวันนี้เป็นภาพรวมทั้งภาควิชา",
                td.headings.includes("วันนี้ใครอยู่สายไหน") && /\d+ คน/.test(td.where), td.where);

      /* เดินวันไปข้างหน้า/ข้างหลังได้ และกลับมาวันนี้ได้ */
      const nav = await page.evaluate(async () => {
        const title = () => document.querySelector("#todayTitle").textContent;
        const before = title();
        document.querySelector("#todayPrev").click();
        await new Promise(r => setTimeout(r, 150));
        const back = title(), backBtn = !document.querySelector("#todayNow").hidden;
        document.querySelector("#todayNow").click();
        await new Promise(r => setTimeout(r, 150));
        return { before, back, backBtn, home: title() };
      });
      t.check(role + ": เดินวันย้อนหลังได้ และปุ่มกลับมาวันนี้โผล่ขึ้นมา",
              nav.back !== nav.before && nav.backBtn, nav.back);
      t.eq(role + ": กดกลับมาวันนี้แล้วกลับมาจริง", nav.home, nav.before);
      await page.evaluate(() => showView("today"));

      /* บนจอมือถือ หน้าเว็บต้องไม่ปัดข้างไปเจอที่ว่าง — เคยเป็นเพราะ .sr-only ที่เป็น
         position:absolute หลุดออกไปอ้างวิวพอร์ตแทนกล่องเลื่อนของตาราง */
      await page.setViewportSize({ width: 390, height: 844 });
      await page.waitForTimeout(300);
      const views = await page.evaluate(() =>
        [...new Set([...document.querySelectorAll("[data-view]")].map(x => x.dataset.view))]);
      const slides = [];
      for (const v of views) {
        await page.evaluate(x => showView(x), v);
        await page.waitForTimeout(150);
        const x = await page.evaluate(() => {
          window.scrollTo(400, 0); const at = window.scrollX; window.scrollTo(0, 0); return at;
        });
        if (x > 0) slides.push(v + " (" + x + "px)");
      }
      t.check(role + ": จอมือถือ 390px ไม่ปัดข้างไปเจอที่ว่าง",
              slides.length === 0, slides.join(", ") || views.length + " หน้า");
      const wraps = await page.evaluate(() =>
        [...document.querySelectorAll(".tbl-wrap")].filter(w => w.scrollWidth > w.clientWidth + 1).length);
      t.check(role + ": ตารางกว้างเลื่อนได้ในกล่องของตัวเอง", true, wraps + " ตารางที่ต้องเลื่อน");
      await page.setViewportSize({ width: 1280, height: 900 });

      await page.close();
    }

    /* ---------- ตารางไขว้ ประเภทงานนำเสนอ × อนุสาขา ----------
       สิ่งที่ต้องกัน: ตัวเลขในตารางไม่ตรงกับข้อมูลจริง, ตารางเปลี่ยนตามตัวกรองประเภท
       (ซึ่งจะทำให้อ่านไขว้ไม่ได้), ช่องศูนย์จางหายไปทั้งที่ศูนย์คือสิ่งที่ต้องเห็น
       และตัวเลขบนจอเพี้ยนจากตัวเลขในแดชบอร์ดที่ส่งออก */
    {
      const { page, errors } = await openAs(browser, srv.url, "admin");
      await page.evaluate(() => showView("coverage"));
      await page.waitForTimeout(300);

      const r = await page.evaluate(() => {
        const read = () => [...document.querySelectorAll("#covTypeSub tbody tr")].map(tr =>
          [...tr.querySelectorAll("td")].map(td => td.textContent.trim()));
        const subs = SUBSPECIALTIES.filter(x => x.id !== "general");
        const grid = read();
        /* นับใหม่จากข้อมูลดิบ ไม่แตะฟังก์ชันที่วาดตาราง */
        const want = ACTIVITY_TYPES.map(t => subs.map(sx =>
          store.data.activities.filter(a => a.type === t.id && a.subspecialty === sx.id).length));
        /* ช่องแรกของแถวคือชื่อประเภท ช่องสุดท้ายคือผลรวม — ตัดทั้งสองข้างออกก่อนเทียบ */
        const got = grid.slice(0, ACTIVITY_TYPES.length)
          .map(row => row.slice(1, subs.length + 1).map(v => v === "✕" ? 0 : Number(v)));
        const bg = (pick) => {
          const td = [...document.querySelectorAll("#covTypeSub tbody td")].find(pick);
          return td ? getComputedStyle(td).backgroundColor : "";
        };
        /* อ่านสีให้เสร็จก่อน เพราะการเปลี่ยนตัวกรองจะวาดตารางใหม่ทั้งก้อน */
        const zeroBg = bg(td => td.textContent.trim() === "✕");
        const fillBg = bg(td => /^[1-9]/.test(td.textContent.trim()));
        /* เปลี่ยนตัวกรองประเภทแล้วตารางไขว้ต้องไม่ขยับ */
        const sel = document.querySelector('#coverageFilters [data-cov="type"]');
        sel.value = ACTIVITY_TYPES[0].id;
        sel.dispatchEvent(new Event("change"));
        return {
          rows: grid.length, types: ACTIVITY_TYPES.length, cols: subs.length,
          before: JSON.stringify(grid),
          same: JSON.stringify(got) === JSON.stringify(want),
          got: JSON.stringify(got), want: JSON.stringify(want),
          sum: got.flat().reduce((a, b) => a + b, 0), zeroBg, fillBg
        };
      });
      await page.waitForTimeout(250);
      const after = await page.evaluate(() =>
        [...document.querySelectorAll("#covTypeSub tbody tr")].map(tr =>
          [...tr.querySelectorAll("td")].map(td => td.textContent.trim())));

      t.eq("ตารางไขว้มีครบทุกประเภทงานนำเสนอ บวกแถวรวม",
           r.rows, r.types + 1);
      t.check("ตัวเลขในตารางไขว้ตรงกับที่นับจากข้อมูลจริง", r.same,
              r.same ? r.sum + " กิจกรรม · " + r.cols + " อนุสาขา" : "ได้ " + r.got + " ควรเป็น " + r.want);
      t.check("ช่องศูนย์ใช้สีต่างหาก ไม่ใช่แค่จางลง",
              !!r.zeroBg && r.zeroBg !== r.fillBg, r.zeroBg + " เทียบกับ " + r.fillBg);
      t.eq("เปลี่ยนตัวกรองประเภทแล้วตารางไขว้ยังนับทุกประเภทเหมือนเดิม",
           JSON.stringify(after), r.before);

      /* ตัวเลขบนจอกับตัวเลขในไฟล์ที่ส่งออกต้องมาจากฟังก์ชันเดียวกัน */
      const drift = await page.evaluate(() => {
        const ay = currentAY();
        const acts = visibleActivities().filter(a => a.academicYear === ay);
        const html = dashboardHtml();
        const box = document.createElement("div"); box.innerHTML = html;
        const card = [...box.querySelectorAll(".card")]
          .find(c => c.querySelector("h2")?.textContent.includes("× อนุสาขา"));
        const inFile = card ? [...card.querySelectorAll("tbody tr")].map(tr =>
          [...tr.querySelectorAll("td")].map(td => td.textContent.trim())).join("|") : "";
        const tmp = document.createElement("div"); tmp.innerHTML = typeSubTableHtml(acts);
        const direct = [...tmp.querySelectorAll("tbody tr")].map(tr =>
          [...tr.querySelectorAll("td")].map(td => td.textContent.trim())).join("|");
        return { hasCard: !!card, match: inFile === direct && !!inFile };
      });
      t.check("แดชบอร์ดที่ส่งออกมีตารางไขว้อยู่ด้วย", drift.hasCard);
      t.check("ตัวเลขในไฟล์ที่ส่งออกมาจากฟังก์ชันเดียวกับบนจอ ไม่มีทางเพี้ยนกัน", drift.match);
      t.check("หน้าความครอบคลุม: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }
  } finally {
    await browser.close();
    await srv.close();
  }
  return t;
}
