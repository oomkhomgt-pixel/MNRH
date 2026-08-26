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
        /* ตารางมีเฉพาะจันทร์–ศุกร์ — เดินย้อนไปหาวันทำการที่มีคาบจริง */
        const sessionFor = (rid) => {
          for (let i = 0; i < 14; i++) {
            const hit = sessionsForDate(addDaysISO(todayISO(), -i)).find(s => s.residentId === rid);
            if (hit) return hit;
          }
          return null;
        };
        const btns = (rid) => {
          const ses = sessionFor(rid);
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
      {
        /* อาจารย์กรอกแบบประเมินลงกองได้ แต่แก้ตัวแบบประเมินไม่ได้ */
        const { page: sp } = await openAs(browser, srv.url, "staff");
        const seen = await sp.evaluate(() => {
          const card = document.querySelector("#rotationFormEditor")?.closest(".card");
          return { hidden: card?.hidden, canManage: canManage(), canAssess: canAssess() };
        });
        t.check("อาจารย์แก้แบบประเมินลงกองไม่ได้ แต่ยังประเมินได้",
                seen.hidden === true && !seen.canManage && seen.canAssess, JSON.stringify(seen));
        await sp.close();
      }

      const { page } = await openAs(browser, srv.url, "staff");
      /* ถ้าวันนั้นอาจารย์มีคาบอื่นอยู่แล้ว แอปจะถามยืนยันก่อน — playwright ปิดกล่องให้เองโดยตอบ "ไม่"
         ซึ่งทำให้การตอบรับไม่เกิดขึ้นและข้อทดสอบแดงโดยไม่เกี่ยวกับสิทธิ์ ตรงนี้จึงตอบ "ใช่" ให้ชัด */
      page.on("dialog", d => d.accept());
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

    /* ---------- ขอไปเข้าคาบของสายอื่น: ต้องผ่านอาจารย์ผู้กำกับ ---------- */
    {
      const { page } = await openAs(browser, srv.url, "resident");
      const asRes = await page.evaluate(() => {
        store.data.visits = [];
        const me = myResidentId(), iso = todayISO();
        const other = store.data.residents.find(x => x.id !== me).id;
        /* ขอแทนคนอื่นต้องไม่ได้ */
        openVisit(other, iso);
        const openedOther = !!document.querySelector("#dlg")?.open;
        if (openedOther) document.querySelector("#dlg").close();
        /* ขอของตัวเองได้ */
        openVisit(me, iso);
        const openedMine = !!document.querySelector("#dlg")?.open;
        if (openedMine) document.querySelector("#dlg").close();
        /* อนุมัติให้ตัวเองไม่ได้ */
        store.data.visits.push({ id: "v_p", residentId: me, date: iso, serviceId: "", index: 0,
          reasonType: "research", reason: "x", status: "pending" });
        decideVisit("v_p", true);
        const status = store.data.visits[0].status;
        store.data.visits = [];
        return { openedOther, openedMine, status };
      });
      t.check("แพทย์ประจำบ้านขอแทนคนอื่นไม่ได้", !asRes.openedOther);
      t.check("แพทย์ประจำบ้านขอของตัวเองได้", asRes.openedMine);
      t.eq("แพทย์ประจำบ้านอนุมัติคำขอของตัวเองไม่ได้", asRes.status, "pending");
      await page.close();

      const { page: sp } = await openAs(browser, srv.url, "staff");
      const asStaff = await sp.evaluate(() => {
        store.data.visits = [];
        const me = currentUser().staffId, iso = todayISO();
        let mine = store.data.residents.find(r => visitApprovers(r.id, iso).includes(me));
        if (!mine) {
          /* วันนั้นอาจารย์คนนี้ไม่มีคาบกับใครเลย — ตั้งเป็นอาจารย์ผู้กำกับของช่วงหมุนเวียนแทน
             เพื่อให้ทดสอบสิทธิ์ได้จริง ไม่ใช่ข้ามไปเงียบ ๆ */
          const rot = (store.data.rotations || []).find(x =>
            (!x.start || iso >= x.start) && (!x.end || iso <= x.end));
          if (rot) { rot.supervisorId = me; mine = store.resident(rot.residentId); }
        }
        const notMine = store.data.residents.find(r => mine && r.id !== mine.id &&
          !visitApprovers(r.id, iso).includes(me));
        const mk = (id, rid) => store.data.visits.push({ id, residentId: rid, date: iso,
          serviceId: "", index: 0, reasonType: "research", reason: "x", status: "pending" });
        if (mine) mk("v_mine", mine.id);
        if (notMine) mk("v_not", notMine.id);
        decideVisit("v_mine", true);
        decideVisit("v_not", true);
        const out = Object.fromEntries(store.data.visits.map(v => [v.id, v.status]));
        store.data.visits = [];
        return { out, hasMine: !!mine, hasNotMine: !!notMine };
      });
      if (asStaff.hasMine)
        t.eq("อาจารย์ที่คุมเขาอยู่ อนุมัติได้", asStaff.out.v_mine, "approved");
      if (asStaff.hasNotMine)
        t.eq("อาจารย์ที่ไม่ได้คุมเขา อนุมัติไม่ได้", asStaff.out.v_not, "pending");
      await sp.close();
    }

    /* ---------- ทางลัดที่ต้องปิด: บันทึกการเข้าคาบรายวันแล้วระบุอาจารย์นอกสาย ----------
       ถ้าทำได้ มันจะเป็นการบันทึกการปฏิบัติงานนอกสายโดยไม่ผ่านการอนุมัติ ซึ่งกติกาบอกว่าต้องผ่านเสมอ */
    {
      const { page } = await openAs(browser, srv.url, "resident");
      const r = await page.evaluate(() => {
        const me = myResidentId();
        store.data.sessionPicks = [];
        let iso = todayISO(), ses = null;
        for (let i = 0; i < 14 && !ses; i++) {
          iso = addDaysISO(todayISO(), -i);
          ses = sessionsForDate(iso).find(x => x.residentId === me && !x.advisory);
        }
        if (!ses) return { none: true };
        const mine = new Set();
        sessionsForDate(iso).filter(x => x.residentId === me)
          .forEach(x => (x.staffIds || []).forEach(id => id && mine.add(id)));
        const outsider = (store.data.staff || []).find(x => !mine.has(x.id))?.id;
        const insider = [...mine][0];
        const trySave = (staffId) => {
          openSession(ses.key);
          const sel = document.querySelector('#dlgBody [name="staffId"]');
          if (sel) sel.value = staffId;
          const btn = [...document.querySelectorAll("#dlgFoot button")]
            .find(x => x.textContent.includes("บันทึกว่าเข้าคาบนี้") || x.textContent.includes("แก้อาจารย์"));
          if (btn) btn.click();
          document.querySelector("#dlg")?.close();
          return (store.data.sessionPicks || [])[0]?.staffId || "";
        };
        const afterOutsider = trySave(outsider);
        const afterInsider = insider ? trySave(insider) : "";
        store.data.sessionPicks = [];
        return { outsider, insider, afterOutsider, afterInsider };
      });
      if (!r.none) {
        t.eq("ระบุอาจารย์นอกสายในการเข้าคาบรายวันไม่ได้ — ต้องผ่านการอนุมัติ", r.afterOutsider, "");
        if (r.insider) t.eq("ระบุอาจารย์ที่อยู่ในตารางของตัวเองวันนั้นได้", r.afterInsider, r.insider);
      }
      await page.close();
    }

    /* ---------- แดชบอร์ดที่ส่งออก ต้องเคารพสิทธิ์เหมือนหน้าจอ ---------- */
    {
      const { page } = await openAs(browser, srv.url, "resident");
      const r = await page.evaluate(() => {
        const html = dashboardHtml();
        const me = store.resident(myResidentId());
        const others = store.data.residents.filter(x => x.id !== myResidentId());
        return { len: html.length, mine: html.includes(me.name),
                 leaked: others.filter(o => html.includes(o.name)).map(o => o.name),
                 external: /(src|href)\s*=\s*["']https?:/i.test(html),
                 script: /<script/i.test(html) };
      });
      t.check("แดชบอร์ดของแพทย์ประจำบ้านมีชื่อตัวเอง", r.mine, r.len + " ตัวอักษร");
      t.check("แดชบอร์ดไม่หลุดชื่อแพทย์ประจำบ้านคนอื่น",
              r.leaked.length === 0, r.leaked.join(", ") || "ไม่หลุด");
      t.check("แดชบอร์ดไม่อ้าง asset จากภายนอก เปิดออฟไลน์ได้", !r.external);
      t.check("แดชบอร์ดไม่มีสคริปต์ — เป็นภาพนิ่งล้วน", !r.script);
      await page.close();

      const { page: ap } = await openAs(browser, srv.url, "admin");
      const a = await ap.evaluate(() => {
        const html = dashboardHtml();
        return { all: store.data.residents.every(x => html.includes(x.name)),
                 hasHn: /MOCK-\d/.test(html) };
      });
      /* ตัวแก้แบบประเมินลงกองเป็นของผู้จัดหลักสูตร อาจารย์กรอกได้แต่แก้ฟอร์มไม่ได้ */
      const rf = await ap.evaluate(() => {
        const card = document.querySelector("#rotationFormEditor")?.closest(".card");
        return { perm: card?.dataset.perm, hidden: card?.hidden };
      });
      t.eq("การ์ดแก้แบบประเมินลงกองจำกัดไว้ที่ผู้จัดหลักสูตร", rf.perm, "admin");
      t.check("ผู้จัดหลักสูตรเห็นการ์ดนี้", rf.hidden === false);

      t.check("แดชบอร์ดของผู้จัดหลักสูตรมีครบทุกคน", a.all);
      t.check("แดชบอร์ดไม่มี HN หรือข้อมูลผู้ป่วยรายบุคคล", !a.hasHn);
      await ap.close();
    }

    /* ---------- แดชบอร์ดรายบุคคล ที่แนบไปกับการส่งออกข้อมูลของคนคนเดียว ---------- */
    {
      const { page } = await openAs(browser, srv.url, "admin");
      const a = await page.evaluate(() => {
        const r = store.data.residents[0];
        const html = residentDashboardFile(r.id);
        const others = store.data.residents.filter(x => x.id !== r.id);
        /* รายงานที่สั่งพิมพ์ต้องมีส่วนแดชบอร์ดอยู่หัวรายงานด้วย ไม่ใช่มีแต่ตาราง */
        window.print = () => {};
        printPortfolio(r.id);
        const body = document.querySelector("#reportBody");
        return { len: html.length, name: r.name, mine: html.includes(r.name),
                 leaked: others.filter(o => html.includes(o.name)).map(o => o.name),
                 external: /(src|href)\s*=\s*["']https?:/i.test(html),
                 script: /<script/i.test(html),
                 hasHn: /MOCK-\d/.test(html),
                 inReport: body.querySelectorAll(".dash").length,
                 reportBars: body.querySelectorAll(".dash svg").length };
      });
      t.check("แดชบอร์ดรายบุคคลมีชื่อเจ้าของ", a.mine, a.name + " · " + a.len + " ตัวอักษร");
      t.check("แดชบอร์ดรายบุคคลไม่มีชื่อแพทย์ประจำบ้านคนอื่นปนมา",
              a.leaked.length === 0, a.leaked.join(", ") || "ไม่มี");
      t.check("แดชบอร์ดรายบุคคลไม่อ้าง asset ภายนอกและไม่มีสคริปต์", !a.external && !a.script);
      t.check("แดชบอร์ดรายบุคคลไม่มี HN หรือข้อมูลผู้ป่วย", !a.hasHn);
      t.eq("รายงานรายบุคคลที่สั่งพิมพ์มีส่วนแดชบอร์ดนำหน้าตาราง", a.inReport, 1);
      t.check("แดชบอร์ดในรายงานมีกราฟจริง ไม่ใช่ตารางล้วน", a.reportBars > 0, a.reportBars + " รูป");
      await page.close();

      /* แพทย์ประจำบ้านต้องดึงแดชบอร์ดของคนอื่นไม่ได้ ทั้งทางไฟล์และทางปุ่ม */
      const { page: rp } = await openAs(browser, srv.url, "resident");
      const b2 = await rp.evaluate(() => {
        const me = myResidentId();
        const other = store.data.residents.find(x => x.id !== me);
        const grabbed = [];
        const real = window.download; window.download = (n) => grabbed.push(n);
        /* กดของตัวเองก่อน เพื่อพิสูจน์ว่าดักการดาวน์โหลดได้จริง ไม่งั้นข้อถัดไปผ่านฟรี */
        exportResidentDashboard(me);
        const own = grabbed.length;
        exportResidentDashboard(other.id);
        window.download = real;
        return { otherName: other.name, own, total: grabbed.length, files: grabbed };
      });
      t.check("ดักการดาวน์โหลดได้จริง — กดของตัวเองแล้วมีไฟล์ออกมา", b2.own === 1, b2.files.join(", "));
      t.check("แพทย์ประจำบ้านกดส่งออกแดชบอร์ดของคนอื่นไม่ได้",
              b2.total === b2.own, b2.files.join(", ") || "ไม่มีไฟล์ถูกสร้าง");
      await rp.close();
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
