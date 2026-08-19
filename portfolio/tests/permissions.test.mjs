/* ชุดนี้สำคัญที่สุดในสามชุด
   ข้อมูลของทั้งภาควิชาอยู่ใน localStorage ก้อนเดียวกันของเครื่องที่ดึงจากคลาวด์มา
   การกรองตามบทบาทจึงต้องครบทุกทาง ทางไหนที่ลืมกรอง = ข้อมูลของทุกคนโผล่ทันที
   ทุกข้อที่ตรวจในนี้เคยเป็นช่องโหว่จริงมาแล้ว อย่าลบออกโดยไม่เข้าใจว่ามันกันอะไรอยู่ */
import { chromium } from "playwright";
import { serve, launchOptions, openAs, suite } from "./lib.mjs";

export default async function run() {
  const t = suite("สิทธิ์การเข้าถึงข้อมูล");
  const srv = await serve();
  const browser = await chromium.launch(launchOptions());
  try {
    /* ---------- แพทย์ประจำบ้าน: เห็นและแก้ได้เฉพาะของตัวเอง ---------- */
    {
      const { page, errors } = await openAs(browser, srv.url, "resident");
      const r = await page.evaluate(() => ({
        mine: myResidentId(),
        allActivities: store.data.activities.length,
        seenActivities: visibleActivities().length,
        allResidents: store.data.residents.length,
        seenResidents: visibleResidents().length,
        othersInMyView: visibleActivities().filter(a => a.residentId !== myResidentId()).length
      }));
      t.check("เห็นกิจกรรมเฉพาะของตัวเอง",
              r.othersInMyView === 0 && r.seenActivities < r.allActivities,
              r.seenActivities + " จาก " + r.allActivities);
      t.check("เห็นรายชื่อเฉพาะของตัวเอง", r.seenResidents === 1,
              r.seenResidents + " จาก " + r.allResidents);

      /* เปิดกิจกรรมของคนอื่นด้วยการเรียกฟังก์ชันตรง ๆ ต้องไม่เปิด */
      t.check("เปิดกิจกรรมของคนอื่นไม่ได้", await page.evaluate(() => {
        const a = store.data.activities.find(x => x.residentId !== myResidentId());
        openActivity(a.id);
        const open = !!document.querySelector("#dlg")?.open;
        if (open) document.querySelector("#dlg").close();
        return !open;
      }));

      /* logbook เป็นของรายบุคคล — ไม่ระบุเจ้าของต้องไม่ส่งอะไรเลย
         เดิมช่องว่างแปลว่า "ทุกเคสในเครื่อง" ซึ่งส่งเคสของคนอื่นออกไปได้ */
      const sync = await page.evaluate(() => {
        const cfg = syncCfg();
        cfg.mode = "full"; cfg.cloudUrl = "https://example.invalid/x"; cfg.residentId = "";
        return { leaked: syncPayloadItems().length, mode: syncMode(), cases: store.data.cases.length };
      });
      t.eq("logbook ที่ไม่ระบุเจ้าของ ส่งรายการเปล่า", sync.leaked, 0);
      t.eq("บังคับกลับมาที่โหมดเฉพาะ logbook แม้ตั้งค่าเป็นข้อมูลทั้งชุด", sync.mode, "logbook");

      /* ส่งข้อมูลทั้งชุดออกนอกเครื่องต้องถูกปฏิเสธก่อนถึงขั้นเรียก fetch */
      t.check("ส่งข้อมูลทั้งชุดขึ้นคลาวด์ไม่ได้", await page.evaluate(async () => {
        let called = false;
        const real = window.fetch;
        window.fetch = (...a) => { called = true; return real(...a); };
        await cloudPush(true).catch(() => {});
        window.fetch = real;
        return !called;
      }));

      /* หน้าตั้งค่าซิงก์ต้องเป็นแบบอ่านอย่างเดียว ไม่มีช่องให้แก้ปลายทาง */
      const dlg = await page.evaluate(() => {
        syncSettingsDialog();
        const editable = document.querySelectorAll(
          "#dlgBody input:not([disabled]), #dlgBody select:not([disabled]), #dlgBody textarea:not([disabled])").length;
        document.querySelector("#dlg").close();
        return editable;
      });
      t.eq("หน้าตั้งค่าซิงก์เป็นแบบอ่านอย่างเดียว", dlg, 0);

      /* ทะเบียนแพทย์ประจำบ้านเป็นของผู้จัดหลักสูตร */
      t.check("แก้ทะเบียนแพทย์ประจำบ้านไม่ได้", await page.evaluate(() => {
        editResident(store.data.residents[0].id);
        const open = !!document.querySelector("#dlg")?.open;
        if (open) document.querySelector("#dlg").close();
        return !open;
      }));

      /* ช่อง "อาจารย์รับรอง" คือสิ่งที่ใช้อ้างอิงตอนพิมพ์ logbook ส่งราชวิทยาลัย
         ต้องรับรองตัวเองไม่ได้ แม้จะปลดล็อกช่องใน DOM เอง */
      const cert = await page.evaluate(() => {
        const mine = myResidentId(), other = store.data.residents.find(r => r.id !== mine).id;
        const c = { id: "case_perm_test", date: "2026-08-01", diagnosis: "dx", operation: "op", source: "test",
          participants: [{ residentId: mine, role: "assistant", verified: false, verifiedBy: "", rcost: { done: false, at: "" } },
                         { residentId: other, role: "surgeon", verified: true, verifiedBy: "อ.", rcost: { done: true, at: "2026-08-02" } }] };
        store.data.cases.push(c);
        editCaseParticipants("case_perm_test");
        const box = document.querySelector('#dlgBody [data-ver="' + mine + '"]');
        const wasDisabled = box.disabled;
        box.disabled = false; box.checked = true;
        document.querySelector('#dlgBody [data-role="' + mine + '"]').value = "surgeon";
        [...document.querySelectorAll("#dlgFoot button")].find(b => b.textContent === "บันทึก").click();
        const me = c.participants.find(x => x.residentId === mine);
        const them = c.participants.find(x => x.residentId === other);
        return { wasDisabled, stillUnverified: me.verified === false, myRole: me.role,
                 otherKept: them?.role === "surgeon" && them.verified === true && them.rcost.done === true,
                 canDelete: [...document.querySelectorAll("#dlgFoot button")].some(b => b.textContent === "ลบเคสนี้") };
      });
      t.check('ช่อง "อาจารย์รับรอง" ถูกปิดไว้', cert.wasDisabled);
      t.check("รับรองเคสของตัวเองไม่ได้แม้แก้ DOM ตรง ๆ", cert.stillUnverified);
      t.eq("ระบุบทบาทของตัวเองในเคสได้", cert.myRole, "surgeon");
      t.check("แถวของคนอื่นไม่ถูกเขียนทับ", cert.otherKept);
      t.check("ลบเคสออกจาก logbook ไม่ได้", !cert.canDelete);

      t.check("แพทย์ประจำบ้าน: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }

    /* ---------- อาจารย์: ดูได้ทุกคนเพื่อประเมิน แต่ไม่ได้ดูแลทะเบียน ---------- */
    {
      const { page, errors } = await openAs(browser, srv.url, "staff");
      const r = await page.evaluate(() => ({
        seesAll: visibleActivities().length === store.data.activities.length
              && visibleResidents().length === store.data.residents.length,
        canAssess: canAssess(),
        canManage: canManage(),
        editResident: (() => { editResident(store.data.residents[0].id);
          const o = !!document.querySelector("#dlg")?.open; if (o) document.querySelector("#dlg").close(); return o; })(),
        openOther: (() => { openActivity(store.data.activities[0].id);
          const o = !!document.querySelector("#dlg")?.open; if (o) document.querySelector("#dlg").close(); return o; })()
      }));
      t.check("อาจารย์เห็นข้อมูลของแพทย์ประจำบ้านทุกคน", r.seesAll);
      t.check("อาจารย์เปิดกิจกรรมของแพทย์ประจำบ้านได้", r.openOther);
      t.eq("อาจารย์ประเมินได้ แต่ไม่ได้ดูแลทะเบียน", [r.canAssess, r.canManage, r.editResident], [true, false, false]);
      t.check("อาจารย์ส่งข้อมูลทั้งชุดขึ้นคลาวด์ไม่ได้", await page.evaluate(async () => {
        let called = false; const real = window.fetch;
        window.fetch = (...a) => { called = true; return real(...a); };
        syncCfg().cloudUrl = "https://example.invalid/x";
        await cloudPush(true).catch(() => {});
        window.fetch = real; return !called;
      }));
      t.check("อาจารย์: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }

    /* ---------- ผู้จัดหลักสูตร: ต้องยังทำงานได้ครบ ไม่ใช่ปิดจนใช้ไม่ได้ ---------- */
    {
      const { page, errors } = await openAs(browser, srv.url, "admin");
      const r = await page.evaluate(() => {
        const open = fn => { fn(); const o = !!document.querySelector("#dlg")?.open;
                             if (o) document.querySelector("#dlg").close(); return o; };
        return {
          editResident: open(() => editResident(store.data.residents[0].id)),
          editUser: open(() => editUser(store.data.users[0].id)),
          syncEditable: (() => { syncSettingsDialog();
            const n = document.querySelectorAll("#dlgBody input:not([disabled]), #dlgBody select:not([disabled])").length;
            document.querySelector("#dlg").close(); return n; })(),
          canDeleteCase: (() => { const c = store.data.cases.find(x => (x.participants || []).length);
            editCaseParticipants(c.id);
            const yes = [...document.querySelectorAll("#dlgFoot button")].some(b => b.textContent === "ลบเคสนี้");
            document.querySelector("#dlg").close(); return yes; })()
        };
      });
      t.check("ผู้จัดหลักสูตรแก้ทะเบียนแพทย์ประจำบ้านได้", r.editResident);
      t.check("ผู้จัดหลักสูตรแก้บัญชีผู้ใช้ได้", r.editUser);
      t.check("ผู้จัดหลักสูตรตั้งค่าซิงก์ได้", r.syncEditable > 0, r.syncEditable + " ช่อง");
      t.check("ผู้จัดหลักสูตรลบเคสได้", r.canDeleteCase);
      t.check("ผู้จัดหลักสูตร: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }

    /* ---------- ข้อความจากสไลด์ต้องถูกล้างตัวระบุตัวผู้ป่วยก่อนเก็บ ---------- */
    {
      const { page } = await openAs(browser, srv.url, "admin");
      const out = await page.evaluate(() => scrubPatientText(
        "ผู้ป่วย นาย สมชาย ใจดี HN 1234567 เลขบัตร 1234567890123 · นางสาว สมหญิง รักดี · Mr John Smith AN 987654"));
      const leaks = ["สมชาย", "ใจดี", "1234567", "1234567890123", "สมหญิง", "John", "987654"].filter(x => out.includes(x));
      t.check("ล้าง HN เลขบัตร เลขเวชระเบียน และชื่อที่มีคำนำหน้าออกจากข้อความสไลด์",
              leaks.length === 0, leaks.length ? "ยังหลุด: " + leaks.join(", ") + " → " + out : out);
      await page.close();
    }
  } finally {
    await browser.close();
    await srv.close();
  }
  return t;
}
