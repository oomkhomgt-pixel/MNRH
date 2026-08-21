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

      /* บันทึกได้ว่าตัวเองเข้าคาบไหนในวันนั้น แต่บันทึกแทนคนอื่นไม่ได้ */
      const pickPerm = await page.evaluate(() => {
        const btns = (rid) => {
          const ses = sessionsForDate(todayISO()).find(s => s.residentId === rid);
          if (!ses) return null;
          openSession(ses.key);
          const labels = [...document.querySelectorAll("#dlgFoot button")].map(b => b.textContent);
          document.querySelector("#dlg").close();
          return labels;
        };
        const mine = btns(myResidentId());
        const other = btns(store.data.residents.find(r => r.id !== myResidentId()).id);
        return { mine, other };
      });
      t.check("บันทึกได้ว่าตัวเองเข้าคาบไหนในวันนั้น",
              pickPerm.mine?.some(x => x.includes("บันทึกว่าเข้าคาบนี้")), (pickPerm.mine || []).join(" / "));
      t.check("บันทึกการเข้าคาบแทนคนอื่นไม่ได้",
              !pickPerm.other?.some(x => x.includes("บันทึกว่าเข้าคาบนี้")), (pickPerm.other || []).join(" / "));

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

    /* ---------- การแลกวัน OR: อาจารย์แลกได้เฉพาะคาบของตัวเอง ---------- */
    {
      const rows = [];
      for (const role of ["resident", "staff", "admin"]) {
        const { page } = await openAs(browser, srv.url, role);
        rows.push(await page.evaluate(r => {
          const mine = currentUser()?.staffId || "";
          const other = (store.data.staff || []).find(x => x.id !== mine)?.id || "";
          const before = (store.data.swaps || []).length;
          /* ลองบันทึกทับคาบของอาจารย์คนอื่นด้วยการเรียกฟังก์ชันตรง ๆ */
          openSwap(todayISO(), other, "", "");
          const opened = !!document.querySelector("#dlg")?.open;
          if (opened) document.querySelector("#dlg").close();
          return { role: r, mine: canSwapFor(mine), other: canSwapFor(other),
                   openedOther: opened, grew: (store.data.swaps || []).length > before };
        }, role));
        await page.close();
      }
      const [res, stf, adm] = rows;
      t.check("แพทย์ประจำบ้านบันทึกการแลกวันไม่ได้เลย",
              !res.mine && !res.other && !res.openedOther, JSON.stringify(res));
      t.check("อาจารย์แลกวันของตัวเองได้", stf.mine);
      t.check("อาจารย์แลกวันของอาจารย์คนอื่นไม่ได้ แม้เรียกฟังก์ชันตรง ๆ",
              !stf.other && !stf.openedOther && !stf.grew, JSON.stringify(stf));
      t.check("ผู้จัดหลักสูตรแลกวันแทนใครก็ได้", adm.other && adm.openedOther);

      /* ตอบรับได้เฉพาะฝ่ายที่ถูกขอ — ผู้ขอกดตอบรับให้ตัวเองไม่ได้ */
      const { page } = await openAs(browser, srv.url, "staff");
      const decide = await page.evaluate(() => {
        const me = currentUser().staffId;
        const other = store.data.staff.find(x => x.id !== me).id;
        const third = store.data.staff.find(x => x.id !== me && x.id !== other).id;
        const mk = (from, to) => ({ id: "sw_" + from + to, pairId: "p_" + from + to, date: todayISO(),
          part: "", serviceId: "", fromStaffId: from, toStaffId: to, status: "pending", note: "", returnDate: "" });
        store.data.swaps = [mk(me, other), mk(other, me), mk(other, third)];
        const [iAsked, askedMe, notMine] = store.data.swaps;
        const before = store.data.swaps.map(x => x.status).join(",");
        decideSwap(iAsked.id, true);        /* ของที่ฉันขอเอง — ต้องไม่ผ่าน */
        decideSwap(notMine.id, true);       /* ของคนอื่นสองคน — ต้องไม่ผ่าน */
        const mid = store.data.swaps.map(x => x.status).join(",");
        decideSwap(askedMe.id, true);       /* ที่ขอให้ฉันมาแทน — ต้องผ่าน */
        const after = store.data.swaps.map(x => x.status).join(",");
        store.data.swaps = [];
        return { before, mid, after };
      });
      t.eq("ผู้ขอกดตอบรับคำขอของตัวเองไม่ได้ และตอบรับแทนคู่อื่นก็ไม่ได้",
           decide.mid, decide.before);
      t.check("ฝ่ายที่ถูกขอตอบรับได้", decide.after.startsWith("pending,accepted"), decide.after);
      await page.close();
    }

    /* ---------- หน้าเข้าสู่ระบบ: รหัสสาธิตต้องคนละชุดต่อบทบาท และต้องกันรหัสผิดจริง ---------- */
    {
      const { page, errors } = await openAs(browser, srv.url, null);
      const r = await page.evaluate(async () => {
        const pick = (role) => store.data.users.find(u => u.role === role);
        const users = { admin: pick("admin"), staff: pick("staff"), resident: pick("resident") };
        const attempt = async (u, pin) => {
          localStorage.removeItem("mnrh_ortho_portfolio_session_v1");
          document.querySelector("#loginUser").value = u.id;
          document.querySelector("#loginPin").value = pin;
          document.querySelector("#loginGo").click();
          return !!currentUser();
        };
        const wrong = await attempt(users.admin, "1234");
        const crossRole = await attempt(users.admin, users.resident.pin);
        const right = await attempt(users.admin, users.admin.pin);
        /* ปุ่มเติมรหัสต้องเติมได้ตรงกับรหัสที่บัญชีนั้นใช้จริง */
        document.querySelector("#loginUser").value = users.staff.id;
        document.querySelector("#loginPin").value = "";
        document.querySelector("#loginDemo").click();
        const filled = document.querySelector("#loginPin").value;
        return {
          wrong, crossRole, right, filled, staffPin: users.staff.pin,
          pins: [users.admin.pin, users.staff.pin, users.resident.pin],
          distinct: new Set(store.data.users.map(u => u.pin)).size,
          total: store.data.users.length
        };
      });
      t.check("รหัสเดิม 1234 ใช้ไม่ได้แล้ว", r.wrong === false);
      t.check("รหัสของบทบาทอื่นใช้ข้ามบัญชีไม่ได้", r.crossRole === false);
      t.check("รหัสที่ถูกต้องเข้าได้", r.right === true, r.pins.join(" · "));
      t.check("แต่ละบทบาทได้รหัสคนละชุด",
              new Set(r.pins.map(x => x[0])).size === 3, r.pins.join(" · "));
      t.check("ทุกบัญชีสาธิตมีรหัสไม่ซ้ำกัน", r.distinct === r.total,
              r.distinct + " รหัส จาก " + r.total + " บัญชี");
      t.eq("ปุ่มเติมรหัสสาธิตเติมตรงกับรหัสของบัญชีนั้น", r.filled, r.staffPin);
      t.check("หน้าเข้าสู่ระบบ: ไม่มี error หลุดในคอนโซล", errors.length === 0, errors.join(" | "));
      await page.close();
    }
  } finally {
    await browser.close();
    await srv.close();
  }
  return t;
}
