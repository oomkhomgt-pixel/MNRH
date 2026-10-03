/* เข้ารหัสข้อมูลทั้งชุดบนเครื่องก่อนขึ้นคลาวด์ + ปลายทาง Apps Script บน Drive ของภาควิชา
   - ตรรกะของ Code.gs (โทเคน รุ่น 409 สำเนารุ่นเก่า ไม่ให้เขียนข้อมูลเปิดทับข้อมูลที่เข้ารหัส)
   - แอปคุยกับ Code.gs ตัวจริง (รันใน Node ผ่าน page.route) ด้วยรูปแบบที่ Apps Script รับได้
   - หลายเครื่อง: เปิดใช้ → ส่ง → เครื่องที่ยังไม่ปลดล็อกส่งไม่ได้ → ปลดล็อกด้วยรหัสชั่วคราว → บังคับเปลี่ยน
     → ถอดผู้ดูแล (ออกกุญแจใหม่) → กุญแจกู้คืน · การปลอมรายชื่อ / เอาสำเนาเก่ามาวาง / ข้อมูลเปิดทับ ต้องถูกปฏิเสธ
   ทุกข้อคือสิ่งที่ทำให้ข้อมูลผู้ป่วยหลุดหรือหายได้ อย่าลบโดยไม่เข้าใจว่ามันกันอะไรอยู่ */
import { chromium } from "playwright";
import { serve, launchOptions, openAs, suite } from "./lib.mjs";
import { loadGas } from "./gas.mjs";

const GAS_URL = "https://script.google.com/macros/s/TESTDEPLOY/exec";
const PII = /DEMO-\d|นพ\.|พญ\./;                                   /* HN สาธิตและชื่อแพทย์ในข้อมูลสาธิต */

/* hold.p: ถ้าตั้งไว้ คำขอ put จะค้างจนกว่าจะปล่อย — จำลองคลาวด์ตอบช้า (ระหว่างนั้นผู้ใช้ยังกดอย่างอื่นได้) */
async function attachGas(page, gas, token, reqLog, hold = {}) {
  await page.route(GAS_URL, async (route) => {
    const r = route.request();
    const body = r.postData() || "";
    reqLog?.push({ method: r.method(), ct: r.headers()["content-type"] || "", auth: r.headers()["authorization"] || "", body });
    if (hold.p && /"action":"put"/.test(body)) { hold.arrived = true; await hold.p; }
    const out = r.method() === "POST" ? gas.post(body) : { status: 405 };
    await route.fulfill({ status: 200, contentType: "application/json", headers: { "Access-Control-Allow-Origin": "*" }, body: JSON.stringify(out) });
  });
  await page.evaluate(({ url, token }) => { Object.assign(syncCfg(), { mode: "full", auto: false, cloudUrl: url, rev: 0, token }); store.save(); }, { url: GAS_URL, token });
}
const dlgOpen = (page, title) => page.waitForFunction(t => $("#dlg").open && $("#dlgTitle").textContent === t, title, { timeout: 30000 });
const click = (page, label) => page.evaluate(l => { const b = [...document.querySelectorAll("#dlgFoot button")].find(x => x.textContent === l);
  if (!b) throw new Error("ไม่พบปุ่ม " + l + " ใน: " + [...document.querySelectorAll("#dlgFoot button")].map(x => x.textContent).join(" | ")); b.click(); }, label);
const fill = (page, name, v) => page.evaluate(({ name, v }) => { $('#dlgBody [name="' + name + '"]').value = v; }, { name, v });
const cloudDoc = (gas) => JSON.parse(gas.files.get("dataset.json")?.text || "{}");
/* สถานะคลาวด์อยู่ฝั่ง Node — รอจนเงื่อนไขเป็นจริง (การส่งขึ้นเป็นงาน async ที่หน้าจอไม่รอ) */
async function until(fn, ms = 30000) { const t0 = Date.now(); while (Date.now() - t0 < ms) { try { if (fn()) return true; } catch {} await new Promise(r => setTimeout(r, 100)); } return false; }

export default async function run() {
  const t = suite("เข้ารหัสข้อมูลบนคลาวด์ · ปลายทาง Apps Script");

  /* ---------- 1) Code.gs ล้วน ---------- */
  {
    const gas = loadGas({ KEEP_VERSIONS: "2", ALLOW_PLAINTEXT: "1" });
    const tok = gas.ctx.createToken("admin");
    t.check("createToken: เก็บแค่ค่าแฮช ไม่เก็บโทเคนจริง", tok.length >= 40 && !gas.props.get("TOKENS").includes(tok) && /admin/.test(gas.props.get("TOKENS")));
    t.eq("ไม่มีโทเคน / โทเคนผิด → 401", [gas.post({ action: "get" }).status, gas.post({ action: "get", token: "x".repeat(40) }).status], [401, 401]);
    t.eq("ยังไม่มีข้อมูล → rev 0 data null", (({ status, rev, data }) => [status, rev, data])(gas.post({ action: "get", token: tok })), [200, 0, null]);
    const p1 = gas.post({ action: "put", token: tok, baseRev: 0, data: { residents: [] } });
    const p2 = gas.post({ action: "put", token: tok, baseRev: 0, data: { residents: [1] } });
    t.eq("ส่งครั้งแรกได้รุ่น 1 · ส่งด้วยรุ่นเก่าได้ 409 พร้อมของปัจจุบัน", [p1.status, p1.rev, p2.status, p2.rev, JSON.stringify(p2.data)], [200, 1, 409, 1, '{"residents":[]}']);
    const env = { enc: "mnrh-e2e-v1", epoch: 1, kid: "k", iv: "", ct: "", slots: [] };
    const p3 = gas.post({ action: "put", token: tok, baseRev: 1, data: env });
    const p4 = gas.post({ action: "put", token: tok, baseRev: 2, data: { residents: [] } });
    t.eq("ชุดบนคลาวด์เข้ารหัสแล้ว: ส่งข้อมูลไม่เข้ารหัสทับได้ 422 และของเดิมไม่เปลี่ยน", [p3.status, p4.status, cloudDoc(gas).data.enc], [200, 422, "mnrh-e2e-v1"]);
    for (let i = 0; i < 3; i++) gas.post({ action: "put", token: tok, baseRev: 2 + i, data: env });
    const vers = [...gas.files.keys()].filter(k => /^dataset-r\d+\.json$/.test(k)).sort();
    t.check("เก็บสำเนารุ่นก่อนหน้าตาม KEEP_VERSIONS (2) และเป็นรุ่นล่าสุด", vers.length === 2 && vers.includes("dataset-r4.json") && vers.includes("dataset-r3.json"), JSON.stringify(vers));
    t.check("เขียนภายใต้ล็อกทุกครั้ง และปล่อยล็อกครบ", gas.locks.max === 1 && gas.locks.held === 0, JSON.stringify(gas.locks));
    gas.ctx.revokeToken("admin");
    t.eq("ถอนโทเคนแล้ว → 401", gas.post({ action: "get", token: tok }).status, 401);
    const g2 = loadGas(); const t2 = g2.ctx.createToken("a");
    t.check("ค่าเริ่มต้น: ไม่รับข้อมูลที่ไม่ได้เข้ารหัสเลยตั้งแต่ครั้งแรก (ไม่มีไฟล์ถูกเขียน)",
      g2.post({ action: "put", token: t2, baseRev: 0, data: { residents: [] } }).status === 422 && g2.files.size === 0);
    t.eq("คำขอไม่ใช่ JSON → 400", g2.post("<html>").status, 400);
  }

  const srv = await serve();
  const browser = await chromium.launch(launchOptions());
  try {
    const gas = loadGas();
    const tokA = gas.ctx.createToken("admin"), tokB = gas.ctx.createToken("admin2"), tokC = gas.ctx.createToken("head");
    const reqLog = [];

    /* ---------- 2) เครื่อง A: เปิดการเข้ารหัสผ่านหน้าจอ แล้วส่งขึ้น ---------- */
    const A = await openAs(browser, srv.url, "admin");
    const holdA = {};
    await attachGas(A.page, gas, tokA, reqLog, holdA);
    /* ตั้งที่อยู่ Apps Script แล้วกด "บันทึกและซิงก์เลย" ทั้งที่ยังไม่เปิดการเข้ารหัส → ต้องไม่ส่งอะไรขึ้นไป แล้วพาไปตั้งการเข้ารหัส */
    await A.page.evaluate(() => syncSettingsDialog());
    await click(A.page, "บันทึกและซิงก์เลย");
    await dlgOpen(A.page, "เปิดการเข้ารหัสข้อมูลบนคลาวด์");
    const plainTry = await A.page.evaluate(async () => { await cloudPush(true); return syncCfg().lastStatus; });
    t.check("ยังไม่เปิดการเข้ารหัส: กดบันทึกและซิงก์ หรือสั่งส่ง ไม่มีข้อมูลขึ้น Drive เลย และพาไปตั้งการเข้ารหัส",
      !gas.files.has("dataset.json") && !reqLog.some(x => /"action":"put"/.test(x.body)) && /ต้องเปิดการเข้ารหัส/.test(plainTry), plainTry);
    await fill(A.page, "pass", "สั้น"); await fill(A.page, "pass2", "สั้น");
    await click(A.page, "ต่อไป — ออกกุญแจกู้คืน");
    const shortErr = await A.page.evaluate(() => $("#dlgBody .err").textContent);
    t.check("รหัสผ่านสั้นเกินไปถูกปฏิเสธ", /อย่างน้อย 12/.test(shortErr), shortErr);
    await fill(A.page, "pass", "รหัสผ่านของแอดมิน-A-2569"); await fill(A.page, "pass2", "รหัสผ่านของแอดมิน-A-2569");
    await click(A.page, "ต่อไป — ออกกุญแจกู้คืน");
    await dlgOpen(A.page, "กุญแจกู้คืน");
    const rk = await A.page.evaluate(() => $("#dlgBody .mono").textContent.trim());
    t.check("กุญแจกู้คืน 32 ตัว (base32) แบ่งกลุ่มละ 4", /^([A-Z2-7]{4}-){7}[A-Z2-7]{4}$/.test(rk), rk);
    await fill(A.page, "last4", "ZZZZ"); await click(A.page, "จดแล้ว — เปิดการเข้ารหัส");
    t.check("ยืนยัน 4 ตัวสุดท้ายผิด → ยังไม่เปิด", await A.page.evaluate(() => !syncCfg().e2e && /ไม่ตรง/.test($("#dlgBody .err").textContent)));
    await fill(A.page, "last4", rk.slice(-4).toLowerCase()); await click(A.page, "จดแล้ว — เปิดการเข้ารหัส");
    await dlgOpen(A.page, "การเข้ารหัสข้อมูลบนคลาวด์");
    const doc1 = cloudDoc(gas);
    t.check("บน Drive เป็นข้อมูลเข้ารหัส มีผู้ถือกุญแจ = admin + กุญแจกู้คืน",
      doc1.data?.enc === "mnrh-e2e-v1" && JSON.stringify(doc1.data.slots.map(s => s.id)) === '["admin","recovery"]', JSON.stringify(doc1.data?.slots?.map(s => s.id)));
    t.check("ไฟล์บน Drive ไม่มี HN ชื่อแพทย์ หรือชื่อเครื่องเป็นข้อความอ่านได้", !PII.test(gas.files.get("dataset.json").text) && doc1.device === "", "device=" + doc1.device);
    const r0 = reqLog.find(x => /"action":"put"/.test(x.body));
    t.check("คุยกับ Apps Script แบบที่รับได้: POST text/plain ไม่มี header Authorization โทเคนอยู่ในเนื้อหา",
      r0 && r0.method === "POST" && /^text\/plain/.test(r0.ct) && !r0.auth && r0.body.includes(tokA), JSON.stringify({ ...r0, body: undefined }));
    t.check("ในเครื่อง A เก็บกุญแจส่วนตัวแบบส่งออกไม่ได้", await A.page.evaluate(async () => { const s = await e2eReadPriv(); return s?.slotId === "admin" && s.key.extractable === false; }));

    /* A เพิ่ม admin2 ด้วยรหัสชั่วคราว */
    const temp = await A.page.evaluate(() => $('#dlgBody [name="tempPass"]').value);
    await A.page.evaluate(() => { if (!store.data.users.some(u => u.username === "admin2")) store.data.users.push({ id: "u_admin2", username: "admin2", displayName: "Admin 2", role: "admin", pin: "1111" }); store.save(); });
    await A.page.evaluate(() => { $("#dlg").close(); }); await A.page.evaluate(() => e2eDialog());
    await dlgOpen(A.page, "การเข้ารหัสข้อมูลบนคลาวด์");
    await A.page.evaluate(() => { const s = $('#dlgBody [name="addUser"]'); s.value = "admin2"; });
    await fill(A.page, "tempPass", temp);
    await click(A.page, "ตั้งรหัสชั่วคราวให้บัญชีที่เลือก");
    await until(() => cloudDoc(gas).data.slots.some(x => x.id === "admin2"));
    t.check("เพิ่ม admin2 ด้วยรหัสชั่วคราวแล้ว ส่งขึ้นคลาวด์", JSON.stringify(cloudDoc(gas).data.slots.map(s => s.id + (s.temp ? "*" : ""))) === '["admin","recovery","admin2*"]',
      JSON.stringify(cloudDoc(gas).data.slots.map(s => s.id)));

    /* ---------- 3) เครื่อง B (admin2): ยังไม่ปลดล็อก → ส่งไม่ได้ · ปลดล็อกด้วยรหัสชั่วคราว → บังคับเปลี่ยน ---------- */
    const B = await openAs(browser, srv.url, "admin");
    await B.page.evaluate(() => { store.data.users.push({ id: "u_admin2", username: "admin2", displayName: "Admin 2", role: "admin", pin: "1111" }); store.save();
      localStorage.setItem("mnrh_ortho_portfolio_session_v1", JSON.stringify({ userId: "u_admin2", at: new Date().toISOString() })); });
    await B.page.reload(); await B.page.waitForFunction(() => typeof currentUser === "function" && currentUser()?.username === "admin2");
    await attachGas(B.page, gas, tokB, null);
    const revBefore = cloudDoc(gas).rev;
    const bLocked = await B.page.evaluate(async () => { await cloudPush(true); const first = syncCfg().lastStatus; await cloudPush(true); return { first, second: syncCfg().lastStatus, pending: syncCfg().pending }; });
    t.check("เครื่องที่ยังไม่ปลดล็อก: ไม่ส่งข้อมูลเปิดทับ (รุ่นบนคลาวด์ไม่ขยับ) และบอกให้ปลดล็อก",
      cloudDoc(gas).rev === revBefore && /ยังไม่ได้ปลดล็อก/.test(bLocked.second) && bLocked.pending === true, JSON.stringify(bLocked));
    await B.page.evaluate(() => e2eDialog()); await dlgOpen(B.page, "การเข้ารหัสข้อมูลบนคลาวด์");
    await fill(B.page, "pass", "ผิดรหัส-ผิดรหัส"); await click(B.page, "ปลดล็อกเครื่องนี้");
    await B.page.waitForFunction(() => /ไม่ถูกต้อง/.test($("#dlgBody .err")?.textContent || ""), null, { timeout: 30000 });
    t.check("รหัสผ่านผิด → บอกว่าไม่ถูกต้อง และไม่เก็บกุญแจ", await B.page.evaluate(async () => !(await e2eReadPriv())));
    await fill(B.page, "pass", temp); await click(B.page, "ปลดล็อกเครื่องนี้");
    await dlgOpen(B.page, "เปลี่ยนรหัสผ่านการเข้ารหัส");
    t.check("ปลดล็อกด้วยรหัสชั่วคราว → บังคับเปลี่ยนรหัสผ่าน", await B.page.evaluate(() => /รหัสผ่านชั่วคราว/.test($("#dlgBody").textContent)));
    /* ยังไม่เปลี่ยน → ส่งข้อมูลไม่ได้ (คนที่ตั้งรหัสชั่วคราวให้ยังแกะกุญแจของ B ได้) */
    const tempSlot = cloudDoc(gas).data.slots.find(s => s.id === "admin2");
    const revT = cloudDoc(gas).rev;
    const bTemp = await B.page.evaluate(async () => { await cloudPush(true); return syncCfg().lastStatus; });
    t.check("ยังใช้รหัสชั่วคราว: ส่งข้อมูลไม่ได้ และบอกให้ตั้งรหัสของตัวเอง", cloudDoc(gas).rev === revT && /รหัสผ่านชั่วคราว/.test(bTemp), bTemp);
    await fill(B.page, "old", temp); await fill(B.page, "pass", "รหัสของแอดมินสอง-ยาวพอ"); await fill(B.page, "pass2", "รหัสของแอดมินสอง-ยาวพอ");
    await click(B.page, "บันทึกรหัสผ่านใหม่");
    await B.page.waitForFunction(() => !$("#dlg").open, null, { timeout: 30000 });
    await until(() => cloudDoc(gas).data.slots.some(s => s.id === "admin2" && !s.temp));
    const newSlot = cloudDoc(gas).data.slots.find(s => s.id === "admin2");
    t.check("เปลี่ยนรหัสแล้ว ช่องของ admin2 ไม่ใช่รหัสชั่วคราวอีก (ส่งขึ้นคลาวด์แล้ว)", newSlot && !newSlot.temp,
      JSON.stringify(cloudDoc(gas).data.slots.map(s => s.id + (s.temp ? "*" : ""))));
    const oldKeyOpens = await A.page.evaluate(async ({ slot, temp }) => e2eOpenPriv(slot, temp).then(() => "เปิดได้", e => e.message), { slot: newSlot, temp });
    t.check("เปลี่ยนรหัส = ออกคู่กุญแจใหม่: กุญแจสาธารณะเปลี่ยน และรหัสชั่วคราวเปิดช่องใหม่ไม่ได้ (คนที่ตั้งรหัสให้หมดสิทธิ์จริง)",
      newSlot.pub.x !== tempSlot.pub.x && /ไม่ถูกต้อง/.test(oldKeyOpens), oldKeyOpens);
    const bStill = await B.page.evaluate(async () => { const s = await fetchCloudSnapshot(); return s.data.residents.length > 0 && !!(await e2eReadPriv()) && !(await e2eReadPriv(true)); });
    t.check("B สลับมาใช้กุญแจใหม่หลังคลาวด์รับแล้ว ยังถอดข้อมูลได้ และไม่มีกุญแจค้างรอสลับ", bStill);
    /* ข้อมูลไปถึงกันจริง: A แก้ → B ดึงมาเห็น */
    await A.page.evaluate(async () => { store.data.residents[0].advisor = "แก้จาก A หลังเข้ารหัส"; await cloudPush(true); });
    const bSees = await B.page.evaluate(async () => { const s = await fetchCloudSnapshot(); return s.data.residents[0].advisor; });
    t.eq("ข้อมูลที่ A ส่ง (เข้ารหัส) B ถอดอ่านได้ตรงกัน", bSees, "แก้จาก A หลังเข้ารหัส");
    /* B ตั้ง "ไม่เก็บ HN" แล้วแก้เคสส่งขึ้น — HN บนคลาวด์ (ในก้อนที่เข้ารหัส) ต้องยังอยู่ครบ และในเครื่อง B ไม่มี HN */
    const nohn = await B.page.evaluate(async () => {
      store.data.orQueue ||= {}; store.data.orQueue.patientData = "nohn"; applyPatientLevel();
      const id = store.data.cases[0].id; store.data.cases[0].note = "แก้จาก B ที่ไม่เก็บ HN";
      await cloudPush(true);
      return { id, status: syncCfg().lastStatus, localHn: store.data.cases.filter(c => c.hn).length };
    });
    const aView = await A.page.evaluate(async (id) => { const s = await fetchCloudSnapshot();
      return { total: s.data.cases.length, withHn: s.data.cases.filter(c => c.hn).length, note: s.data.cases.find(c => c.id === id)?.note }; }, nohn.id);
    t.check("เครื่องไม่เก็บ HN ส่งข้อมูลเข้ารหัสขึ้นไป: HN ของทุกเคสยังอยู่ ค่าที่แก้ขึ้นไปด้วย และในเครื่องไม่มี HN",
      /ส่งขึ้นคลาวด์แล้ว/.test(nohn.status) && aView.total > 0 && aView.withHn === aView.total && aView.note === "แก้จาก B ที่ไม่เก็บ HN" && nohn.localHn === 0,
      JSON.stringify({ nohn, aView }));

    /* ---------- 3b) เครื่องเดียวกัน คนละบัญชี: กุญแจผูกกับบัญชีที่ล็อกอิน ---------- */
    const asUser = async (page, uid) => { await page.evaluate(id => localStorage.setItem("mnrh_ortho_portfolio_session_v1", JSON.stringify({ userId: id, at: new Date().toISOString() })), uid);
      await page.reload(); await page.waitForFunction(id => typeof currentUser === "function" && currentUser()?.id === id, uid); };
    const adminId = await A.page.evaluate(() => currentUser().id);
    await asUser(A.page, "u_admin2");
    const revS = cloudDoc(gas).rev;
    const other = await A.page.evaluate(async () => { const can = await e2eEnsureMem(); await cloudPush(true);
      let add; try { await e2eSetAdmin("x9", "x", "รหัสชั่วคราวยาวพอแล้ว"); add = "เพิ่มได้"; } catch (e) { add = e.message; }
      return { can, status: syncCfg().lastStatus, add }; });
    t.check("อีกบัญชีล็อกอินเครื่องที่ admin ปลดล็อกไว้: ใช้กุญแจของ admin ไม่ได้ ส่งไม่ได้ จัดการผู้ถือกุญแจไม่ได้",
      other.can === false && cloudDoc(gas).rev === revS && /admin2 ยังไม่ได้ปลดล็อก/.test(other.status) && /ต้องปลดล็อก/.test(other.add), JSON.stringify(other));
    /* เครื่องที่ยังล็อก: ลดบทบาทผู้ถือกุญแจ → บอกว่าถอดไม่ได้ก่อน ไม่ถามให้ยืนยันการถอด */
    const lockedAsk = await A.page.evaluate(async () => {
      const msgs = []; const real = confirmDialog; confirmDialog = async (m, o) => { msgs.push((o?.okLabel || "") + "|" + m); return true; };
      const u = store.data.users.find(x => x.username === "admin"); u.role = "staff";
      try { await e2eRevokeIfNotAdmin("admin"); } finally { confirmDialog = real; u.role = "admin"; }
      return msgs;
    });
    t.check("เครื่องที่ยังล็อก: บอกว่าถอดไม่ได้ก่อน ไม่ถามยืนยันการถอด", lockedAsk.length === 1 && /ถอดให้ไม่ได้/.test(lockedAsk[0]) && !/^ถอดและออกกุญแจใหม่/.test(lockedAsk[0]), JSON.stringify(lockedAsk));

    await asUser(A.page, adminId);
    t.check("กลับมาเป็น admin บนเครื่องเดิม: ใช้กุญแจของตัวเองได้ทันทีโดยไม่ต้องใส่รหัสใหม่ (แม้ยังไม่ได้ซิงก์)", await A.page.evaluate(() => e2eEnsureMem()));
    /* ลดบทบาท admin2 ในทะเบียน → หน้าการเข้ารหัสต้องเตือนว่ายังถือกุญแจอยู่ */
    const warn = await A.page.evaluate(async () => { store.data.users.find(u => u.username === "admin2").role = "staff"; await e2eDialog();
      const txt = $("#dlgBody").textContent; $("#dlg").close(); return txt; });
    t.check("ผู้ถือกุญแจที่ไม่ได้เป็นผู้ดูแลแล้ว: หน้าการเข้ารหัสเตือนให้ถอด", /ไม่ได้เป็นผู้ดูแลที่ใช้งานอยู่แล้ว: Admin 2/.test(warn) && /ไม่ใช่ผู้ดูแลแล้ว/.test(warn), warn.slice(0, 200));

    /* ---------- 4) ถอด admin2 ระหว่างที่การส่งอีกรอบค้างอยู่ → ต้องไม่หาย และออกกุญแจใหม่ · B อ่านรุ่นใหม่ไม่ได้ ---------- */
    const kid0 = cloudDoc(gas).data.kid;
    let release; holdA.p = new Promise(r => { release = r; }); holdA.arrived = false;
    const inflight = A.page.evaluate(async () => { store.data.residents[1].advisor = "แก้ระหว่างรอ"; await cloudPush(true); });
    await until(() => holdA.arrived);
    await A.page.evaluate(() => e2eRemoveAdmin("admin2"));      /* สั่งถอดขณะคลาวด์ยังไม่ตอบรอบแรก */
    holdA.p = null; release(); await inflight;
    await until(() => cloudDoc(gas).data.epoch === 2);
    const d4 = cloudDoc(gas).data;
    t.check("สั่งถอดระหว่างการส่งค้าง: ไม่ถูกล้างทิ้ง ส่งต่อเองทันที (ซิงก์อัตโนมัติปิดอยู่)", d4.epoch === 2, "epoch=" + d4.epoch);
    t.check("ถอด admin2 แล้ว: กุญแจข้อมูลใหม่ (kid เปลี่ยน epoch +1) และไม่มีช่องของ admin2", d4.kid !== kid0 && d4.epoch === 2 && !d4.slots.some(s => s.id === "admin2"),
      JSON.stringify({ kid0, kid: d4.kid, epoch: d4.epoch }));
    const bAfter = await B.page.evaluate(async () => { try { await fetchCloudSnapshot(); return "อ่านได้"; } catch (e) { return e.message; } });
    t.check("B ที่ถูกถอดอ่านข้อมูลรุ่นใหม่ไม่ได้", /ไม่อยู่ในรายชื่อผู้ถือกุญแจ/.test(bAfter), bAfter);

    /* ---------- 4b) ลดบทบาทผู้ถือกุญแจในหน้าบัญชีผู้ใช้ → ถามแล้วถอดทันที · ช่องรหัสชั่วคราวที่ค้างไม่ได้กุญแจรุ่นใหม่ ----------
       ช่องรหัสชั่วคราวคนที่ตั้งให้รู้รหัส — ถ้าคนตั้งคือคนที่ถูกถอด แล้วกุญแจรุ่นใหม่ยังถูกห่อให้ช่องนั้น การถอดก็ไม่มีผล */
    await A.page.evaluate(async () => {
      ["admin3", "admin4"].forEach(n => store.data.users.push({ id: "u_" + n, username: n, displayName: n, role: "admin", pin: "1234" }));
      await e2eSetAdmin("admin3", "admin3", "รหัสชั่วคราวของสาม-1"); await e2eSetAdmin("admin4", "admin4", "รหัสชั่วคราวของสี่-1");
      await cloudPush(true);
    });
    const ep0 = cloudDoc(gas).data.epoch;
    t.check("ตั้งต้น: admin3 และ admin4 มีช่องรหัสชั่วคราวบนคลาวด์", ["admin3", "admin4"].every(n => cloudDoc(gas).data.slots.some(s => s.id === n && s.temp)));
    await A.page.evaluate(() => { window.__realCD = confirmDialog; confirmDialog = async () => true; editUser("u_admin3"); $('#dlgBody [name="role"]').value = "staff"; });
    await click(A.page, "บันทึก");
    await until(() => !cloudDoc(gas).data.slots.some(s => s.id === "admin3"));
    await A.page.evaluate(() => { confirmDialog = window.__realCD; });
    const d4b = cloudDoc(gas).data;
    t.check("ลดบทบาท admin3 ในหน้าบัญชีผู้ใช้: ถามแล้วถอดออกจากผู้ถือกุญแจ ออกกุญแจใหม่ทันที", !d4b.slots.some(s => s.id === "admin3") && d4b.epoch === ep0 + 1,
      JSON.stringify({ epoch: d4b.epoch, slots: d4b.slots.map(s => s.id + (s.temp ? "*" : "")) }));
    t.check("ออกกุญแจใหม่แล้ว: ช่องรหัสชั่วคราวที่ค้าง (admin4) ถูกยกเลิก ไม่ได้กุญแจรุ่นใหม่", !d4b.slots.some(s => s.id === "admin4"),
      JSON.stringify(d4b.slots.map(s => s.id)));

    /* ---------- 6a) ลบแพทย์ประจำบ้าน → บัญชีผู้ดูแลที่ผูกอยู่ถูกลบตาม → ต้องถามถอดกุญแจด้วย ---------- */
    const rid = await A.page.evaluate(async () => {
      const r = store.data.residents.find(x => x.active !== false);
      store.data.users.push({ id: "u_chief", username: "chief", displayName: "หัวหน้าแพทย์ประจำบ้าน", role: "admin", pin: "4321", residentId: r.id });
      await e2eSetAdmin("chief", "chief", "รหัสชั่วคราวหัวหน้า-1"); await cloudPush(true);
      window.__realCD = confirmDialog; window.__realCI = confirmInline; confirmDialog = async () => true; confirmInline = async () => true;
      editResident(r.id); return r.id;
    });
    const ep6 = cloudDoc(gas).data.epoch;
    await click(A.page, "ลบรายชื่อนี้");
    await until(() => cloudDoc(gas).data.epoch > ep6);
    await A.page.evaluate(() => { confirmDialog = window.__realCD; confirmInline = window.__realCI; });
    t.check("ลบแพทย์ประจำบ้านที่มีบัญชีผู้ดูแลผูกอยู่: ถอดกุญแจของบัญชีนั้นและออกกุญแจใหม่", !cloudDoc(gas).data.slots.some(s => s.id === "chief") && cloudDoc(gas).data.epoch === ep6 + 1,
      JSON.stringify({ rid, epoch: cloudDoc(gas).data.epoch, slots: cloudDoc(gas).data.slots.map(s => s.id) }));
    /* ส่งเปิดใช้/ส่งสำเร็จแต่ไม่ได้รับคำตอบ (published ยังเป็น false) แล้วคลาวด์ส่งชุดของเครื่องนี้เองกลับมา → ต้องไม่ทิ้งกุญแจของตัวเอง */
    const own = await A.page.evaluate(async () => { const raw = await fetchCloudRaw(); syncCfg().e2e.published = false; e2eMem = null;
      try { await e2eIncoming(raw); } catch (e) { return { err: e.message }; } return { priv: !!(await e2eReadPriv()), published: syncCfg().e2e.published }; });
    t.check("ชุดกุญแจของเครื่องนี้เองที่ส่งสำเร็จแต่ไม่ได้รับคำตอบ: ใช้ต่อได้ ไม่ทิ้งกุญแจในเครื่อง", own.priv === true && own.published === true, JSON.stringify(own));
    /* ---------- 5) การโจมตีด้วยการแก้ไฟล์บน Drive (คนที่มีโทเคนหรือสิทธิ์ในโฟลเดอร์) ---------- */
    const good = gas.files.get("dataset.json").text;
    const tamper = async (mut) => { const d = JSON.parse(good); mut(d); gas.files.get("dataset.json").text = JSON.stringify(d);
      const r = await A.page.evaluate(async () => { try { await fetchCloudSnapshot(); return "รับ"; } catch (e) { return e.message; } });
      gas.files.get("dataset.json").text = good; return r; };
    const inj = await tamper(d => d.data.slots.push({ ...d.data.slots[0], id: "attacker" }));
    t.check("เติมช่องกุญแจของคนนอกเข้าไป → ไม่รับ", /ถูกแก้โดยไม่มีกุญแจ/.test(inj), inj);
    const old = JSON.parse(gas.files.get("dataset-r" + (cloudDoc(gas).rev - 1) + ".json")?.text || "null");
    const rb = await tamper(d => { d.data = old.data; });
    t.check("เอาสำเนาเก่า (กุญแจรุ่นก่อน ยังมีคนที่ถูกถอด) มาวางทับ → ไม่รับ", old?.data?.epoch < cloudDoc(gas).data.epoch && /รุ่นเก่ากว่า/.test(rb), rb);
    const plain = await tamper(d => { d.data = { residents: [], activities: [] }; });
    t.check("วางข้อมูลไม่เข้ารหัสแทน → ไม่รับ", /ไม่ได้เข้ารหัส/.test(plain), plain);
    const flip = await tamper(d => { d.data.ct = d.data.ct.slice(0, -8) + "AAAAAAA="; });
    t.check("แก้เนื้อข้อมูลที่เข้ารหัส → ไม่รับ", /ถอดรหัสข้อมูลบนคลาวด์ไม่ได้/.test(flip), flip);
    const oldApp = gas.post({ action: "put", token: tokA, baseRev: cloudDoc(gas).rev, data: { residents: [] } });
    t.eq("แอปรุ่นเก่า (ส่งข้อมูลเปิด) ทับชุดที่เข้ารหัส → Apps Script ปฏิเสธ 422", oldApp.status, 422);

    /* ---------- 6) กุญแจกู้คืน: เครื่อง C ตั้งรหัสชั่วคราวใหม่ให้ admin ที่ลืมรหัส ---------- */
    const C = await openAs(browser, srv.url, "admin");
    await attachGas(C.page, gas, tokC, null);
    /* เครื่องใหม่ที่โทเคนผิด: ตรวจคลาวด์ไม่ได้ → ต้องไม่พาไป "เปิดการเข้ารหัส" ใหม่ (จะแทนกุญแจกู้คืนจริงทิ้ง) */
    const probe = await C.page.evaluate(async () => { const good = syncCfg().token; syncCfg().token = "x".repeat(40);
      await e2eDialog(); const r = { title: $("#dlgTitle").textContent, body: $("#dlgBody").textContent }; $("#dlg").close(); syncCfg().token = good; return r; });
    t.check("ตรวจคลาวด์ไม่ได้ (โทเคนผิด): ไม่พาไปเปิดการเข้ารหัสใหม่ บอกให้ตรวจที่อยู่/โทเคน", probe.title !== "เปิดการเข้ารหัสข้อมูลบนคลาวด์" && /ตรวจไม่ได้/.test(probe.body), JSON.stringify(probe));
    /* เครื่องที่เคยกด "เปิดใช้" ค้างไว้ (ยังไม่เคยส่งสำเร็จ) ทั้งที่คลาวด์เข้ารหัสอยู่แล้ว → ชุดกุญแจที่เตรียมไว้ต้องถูกทิ้ง ไม่ทับกุญแจกู้คืนจริง */
    const recPub = cloudDoc(gas).data.slots.find(s => s.kind === "recovery").pub.x;
    const stray = await C.page.evaluate(async () => { await e2eEnable("เปิดซ้ำโดยไม่ตั้งใจ-1234", e2eNewRecoveryKey()); await cloudPush(true);
      return { pending: syncCfg().e2e.pending.length, status: syncCfg().lastStatus }; });
    t.check("เปิดใช้ซ้ำบนเครื่องที่ไม่รู้ว่าคลาวด์เข้ารหัสแล้ว: ไม่ส่ง ทิ้งชุดกุญแจที่เตรียมไว้ และกุญแจกู้คืนบนคลาวด์ไม่เปลี่ยน",
      stray.pending === 0 && cloudDoc(gas).data.slots.find(s => s.kind === "recovery").pub.x === recPub, JSON.stringify(stray));
    const c1 = await C.page.evaluate(async (rk) => {
      try { await e2eRecover("AAAA-" + rk.slice(5)); } catch (e) { var wrong = e.message; }
      await e2eRecover(rk.toLowerCase());
      await e2eSetAdmin("admin", "Admin", "รหัสชั่วคราวจากหัวหน้า", { replace: true });
      await cloudPush(true);
      return { wrong, status: syncCfg().lastStatus, persisted: !!(await e2eReadPriv()) };
    }, rk);
    t.check("กุญแจกู้คืนผิด → ปฏิเสธ", /กุญแจกู้คืนไม่ถูกต้อง/.test(c1.wrong || ""), c1.wrong);
    t.check("ใช้กุญแจกู้คืน (ไม่สนตัวเล็ก/ใหญ่) ตั้งรหัสชั่วคราวให้ admin แล้วส่งขึ้น · ไม่เก็บกุญแจกู้คืนลงเครื่อง",
      /ส่งขึ้นคลาวด์แล้ว/.test(c1.status) && cloudDoc(gas).data.slots.find(s => s.id === "admin")?.temp === true && !c1.persisted, JSON.stringify(c1));

    /* ---------- 6b) ล็อกเครื่องนี้: ลบเฉพาะกุญแจของบัญชีตัวเอง (เทียบชื่อคีย์ทั้งสตริง) และกุญแจรูปแบบรุ่นแรก ---------- */
    const lk = await A.page.evaluate(async () => {
      const k = (await e2eReadPriv()).key;
      await idb("readwrite", st => { st.put({ slotId: "x", key: k }, "e2ePriv"); st.put({ slotId: "x:admin", key: k }, "e2ePriv:x:admin"); return null; });
      await e2eForgetDevice(false);
      const has = (name) => idb("readonly", st => st.get(name)).then(v => !!v);
      return { mine: await has("e2ePriv:" + currentUser().username), legacy: await has("e2ePriv"), other: await has("e2ePriv:x:admin") };
    });
    t.eq("ล็อกเครื่องนี้: ลบกุญแจของตัวเองและรูปแบบรุ่นแรก ไม่แตะบัญชีอื่นที่ชื่อลงท้ายคล้ายกัน", lk, { mine: false, legacy: false, other: true });

    /* ---------- 7) ล้างข้อมูลในเครื่อง → กุญแจของเครื่องหายไปด้วย ---------- */
    const w = await A.page.evaluate(async () => { store.wipe(); await new Promise(r => setTimeout(r, 200)); return !!(await e2eReadPriv()); });
    t.check("ล้างข้อมูลในเครื่อง: ลบกุญแจถอดรหัสคลาวด์ของเครื่องนี้ด้วย", w === false);

    const errs = [...A.errors, ...B.errors, ...C.errors].filter(x => !/409|Conflict/.test(x));
    t.check("ไม่มี error หลุดในคอนโซล (ทั้งสามเครื่อง)", errs.length === 0, errs.join(" | "));
    await A.page.close(); await B.page.close(); await C.page.close();
  } finally {
    await browser.close();
    await srv.close();
  }
  return t;
}
