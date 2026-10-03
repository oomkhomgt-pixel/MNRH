/* ปลายทางคลาวด์ของแฟ้มสะสมงาน บน Google Drive ของภาควิชา (Google Apps Script web app)
 *
 * เก็บข้อมูลทั้งชุดเป็นไฟล์ JSON ไฟล์เดียวในโฟลเดอร์ที่กำหนด + สำเนารุ่นก่อนหน้า (KEEP_VERSIONS รุ่น)
 * ทำสัญญาเดียวกับ sync-server/server.js (rev / baseRev / 409) แต่คุยผ่าน POST แบบ text/plain
 * เพราะ Apps Script ไม่ตอบคำขอตรวจล่วงหน้า (preflight) ของเบราว์เซอร์ และตอบ HTTP 200 เสมอ
 * — สถานะจริงจึงอยู่ในช่อง status ของคำตอบ
 *
 * คำขอ:  { action: "get" | "put", token, baseRev?, data?, device?, updatedAt? }
 * คำตอบ: { status: 200|401|409|413|422|400, rev, updatedAt, data?, bytes?, error? }
 *
 * ความปลอดภัย
 * - ต้องตั้งการเข้าถึงเป็น "Anyone" (เบราว์เซอร์เรียกข้ามโดเมนพร้อมการล็อกอิน Google ไม่ได้) จึงใช้โทเคนต่อผู้ดูแล
 *   เก็บเป็นค่าแฮช SHA-256 ใน Script Properties (ไม่เก็บโทเคนจริง) · ถอนสิทธิ์รายคนได้ด้วย revokeToken()
 * - เมื่อเปิดการเข้ารหัสในแอปแล้ว ไฟล์บน Drive เป็นข้อมูลที่อ่านไม่ออก สคริปต์นี้ไม่มีกุญแจและไม่ต้องมี
 * - รับเฉพาะข้อมูลที่เข้ารหัสแล้วเป็นค่าเริ่มต้น — ข้อมูลทั้งชุดมี HN ห้ามขึ้น Drive แบบอ่านได้แม้แต่ครั้งเดียว
 *   (สำเนารุ่นก่อนและประวัติรุ่นของไฟล์บน Drive จะเก็บมันไว้ต่อ) · ALLOW_PLAINTEXT = "1" เฉพาะการทดสอบที่ไม่มีข้อมูลจริง
 * - เมื่อชุดบนคลาวด์เข้ารหัสแล้ว ไม่ยอมให้เขียนทับด้วยข้อมูลที่ไม่ได้เข้ารหัสเสมอ (กันแอปรุ่นเก่า/การตั้งค่าผิด)
 *
 * ตั้งค่า (Project Settings › Script Properties)
 *   FOLDER_ID           รหัสโฟลเดอร์บน Drive ของภาควิชา (จาก URL ของโฟลเดอร์)
 *   KEEP_VERSIONS       จำนวนสำเนารุ่นก่อนหน้าที่เก็บไว้ (ค่าเริ่มต้น 20)
 *   ALLOW_PLAINTEXT     "1" = ยอมรับข้อมูลที่ไม่ได้เข้ารหัส (อย่าตั้งเมื่อมีข้อมูลจริง)
 *   TOKENS              (สร้างเองด้วย createToken — อย่าแก้ด้วยมือ)
 */
const ENC_VER = "mnrh-e2e-v1";
const MAX_BYTES = 10 * 1024 * 1024;                   /* ขนาดไฟล์ที่ DriveApp เขียนด้วยข้อความได้อย่างปลอดภัย */
const CURRENT = "dataset.json";

function doPost(e) {
  let out;
  try { out = handle_(JSON.parse(e.postData.contents)); }
  catch (err) { out = { status: 400, error: String((err && err.message) || err) }; }
  return ContentService.createTextOutput(JSON.stringify(out)).setMimeType(ContentService.MimeType.JSON);
}
function doGet() {
  return ContentService.createTextOutput(JSON.stringify({ status: 405, error: "use POST" })).setMimeType(ContentService.MimeType.JSON);
}

function handle_(req) {
  if (!req || typeof req !== "object") return { status: 400, error: "bad request" };
  const user = userForToken_(req.token);
  if (!user) return { status: 401, error: "unauthorised" };
  const folder = DriveApp.getFolderById(prop_("FOLDER_ID"));

  if (req.action === "get") {
    const doc = readDoc_(folder);
    console.log("get", user, "rev", doc.rev);
    return { status: 200, rev: doc.rev || 0, updatedAt: doc.updatedAt || "", device: doc.device || "", data: doc.data || null };
  }

  if (req.action === "put") {
    if (!req.data || typeof req.data !== "object" || Array.isArray(req.data)) return { status: 400, error: "missing data" };
    if (prop_("ALLOW_PLAINTEXT") !== "1" && !isEnc_(req.data)) return { status: 422, error: "encryption required — turn on encryption in the app first" };
    const text0 = JSON.stringify(req.data);
    if (text0.length > MAX_BYTES) return { status: 413, error: "payload too large" };
    const lock = LockService.getScriptLock();
    lock.waitLock(20000);                                   /* อ่าน-เทียบรุ่น-เขียน ต้องเป็นจังหวะเดียว */
    try {
      const doc = readDoc_(folder);
      const rev = doc.rev || 0;
      const baseRev = Number(req.baseRev);
      if (rev > 0 && baseRev !== rev) {
        console.log("put rejected (409)", user, "baseRev", baseRev, "rev", rev);
        return { status: 409, rev, updatedAt: doc.updatedAt || "", device: doc.device || "", data: doc.data || null };
      }
      if (isEnc_(doc.data) && !isEnc_(req.data)) {
        console.log("put rejected (422 plaintext over encrypted)", user);
        return { status: 422, error: "dataset is encrypted; refusing an unencrypted write" };
      }
      const next = { rev: rev + 1, updatedAt: new Date().toISOString(), device: String(req.device || "").slice(0, 200), by: user, data: req.data };
      const text = JSON.stringify(next);
      if (doc.rev) writeFile_(folder, "dataset-r" + doc.rev + ".json", JSON.stringify(doc));   /* สำเนารุ่นก่อนหน้า */
      writeFile_(folder, CURRENT, text);
      pruneVersions_(folder, Number(prop_("KEEP_VERSIONS") || 20));
      console.log("put", user, "rev", next.rev, text.length, "bytes");
      return { status: 200, ok: true, rev: next.rev, updatedAt: next.updatedAt, bytes: text.length };
    } finally { lock.releaseLock(); }
  }
  return { status: 400, error: "unknown action" };
}

const isEnc_ = (d) => !!d && typeof d === "object" && d.enc === ENC_VER;
const prop_ = (k) => PropertiesService.getScriptProperties().getProperty(k) || "";

function readDoc_(folder) {
  const it = folder.getFilesByName(CURRENT);
  if (!it.hasNext()) return { rev: 0 };
  try { return JSON.parse(it.next().getBlob().getDataAsString()); } catch (e) { throw new Error("dataset.json อ่านไม่ได้: " + e.message); }
}
function writeFile_(folder, name, text) {
  const it = folder.getFilesByName(name);
  if (it.hasNext()) it.next().setContent(text);
  else folder.createFile(name, text, "application/json");
}
function pruneVersions_(folder, keep) {
  const files = [], it = folder.getFiles();
  while (it.hasNext()) { const f = it.next(); const m = /^dataset-r(\d+)\.json$/.exec(f.getName()); if (m) files.push({ f, rev: +m[1] }); }
  files.sort((a, b) => b.rev - a.rev).slice(Math.max(0, keep)).forEach(x => x.f.setTrashed(true));
}

/* --- โทเคนต่อผู้ดูแล: เก็บแค่ค่าแฮช --- */
const sha256Hex_ = (s) => Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, String(s), Utilities.Charset.UTF_8)
  .map(b => ((b + 256) % 256).toString(16).padStart(2, "0")).join("");
function tokens_() { try { return JSON.parse(prop_("TOKENS") || "{}"); } catch (e) { return {}; } }
function userForToken_(token) {
  if (!token || typeof token !== "string" || token.length < 20) return "";
  const h = sha256Hex_(token), all = tokens_();
  return Object.keys(all).find(u => all[u] === h) || "";
}
/* รันจากหน้าแก้สคริปต์: เลือก createToken แล้วกด Run หลังใส่ชื่อบัญชีในบรรทัดล่าง — โทเคนจะแสดงใน Execution log ครั้งเดียว */
function createToken(user) {
  user = String(user || "").trim();
  if (!user) throw new Error("ระบุชื่อบัญชี เช่น createToken('admin')");
  const token = Utilities.getUuid().replace(/-/g, "") + Utilities.getUuid().replace(/-/g, "");
  const all = tokens_(); all[user] = sha256Hex_(token);
  PropertiesService.getScriptProperties().setProperty("TOKENS", JSON.stringify(all));
  console.log("token for " + user + ": " + token + "  (คัดลอกไปใส่ในแอปของคนนี้ — ระบบไม่เก็บตัวจริงไว้ จะไม่แสดงอีก)");
  return token;
}
function revokeToken(user) {
  const all = tokens_(); delete all[String(user || "")];
  PropertiesService.getScriptProperties().setProperty("TOKENS", JSON.stringify(all));
  console.log("revoked " + user);
}
/* ตัวช่วยสำหรับกด Run จากหน้าแก้สคริปต์ (Run รับพารามิเตอร์ไม่ได้) — แก้ชื่อแล้วกด Run */
function createTokenForAdmin() { return createToken("admin"); }
