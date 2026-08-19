#!/usr/bin/env node
/* เซิร์ฟเวอร์อ้างอิงสำหรับซิงก์ logbook ของแฟ้มสะสมงานแพทย์ประจำบ้าน
 *
 * เก็บเฉพาะข้อมูลที่ตกลงกันไว้: วันที่ผ่าตัด / diagnosis / operation (และ role ถ้าฝั่งแอปเปิดไว้)
 * ฟิลด์อื่นที่ส่งมาจะถูกตัดทิ้งที่ฝั่งเซิร์ฟเวอร์อีกชั้นหนึ่ง เพื่อกันข้อมูลผู้ป่วยหลุดออกมาโดยไม่ตั้งใจ
 *
 * ตัวอย่างการใช้งาน — ไม่ใช่ของพร้อมใช้จริง: ยังไม่มี TLS, ยังไม่ผูกกับบัญชีของโรงพยาบาล
 * และเก็บลงไฟล์ JSON ไฟล์เดียว ให้ใช้เป็นสัญญาข้อมูล (contract) เวลาไปทำของจริง
 *
 *   node server.js                 # ฟังที่ 8090 เก็บไฟล์ที่ ./data.json
 *   PORT=9000 TOKENS='{"resident01":"secret"}' ALLOW_ORIGIN='https://portfolio.hospital.local' node server.js
 */
const http = require("http");
const fs = require("fs");
const path = require("path");

const PORT = +(process.env.PORT || 8090);
const FILE = process.env.DATA_FILE || path.join(__dirname, "data.json");
const ALLOW_ORIGIN = process.env.ALLOW_ORIGIN || "*";
const TOKENS = JSON.parse(process.env.TOKENS || "{}");        /* { user: token } — ว่างไว้ = ไม่ตรวจ */
const ROUTE = process.env.ROUTE || "/api/portfolio/logbook";
const ALLOWED_FIELDS = ["ref", "date", "diagnosis", "operation", "role"];
const MAX_BODY = 2 * 1024 * 1024;

const load = () => { try { return JSON.parse(fs.readFileSync(FILE, "utf8")); } catch { return {}; } };
const save = (db) => fs.writeFileSync(FILE, JSON.stringify(db, null, 1));

const clean = (item) => {
  const out = {};
  for (const k of ALLOWED_FIELDS) if (item && item[k] != null) out[k] = String(item[k]).slice(0, 500);
  return out.date || out.operation ? out : null;
};

const send = (res, code, body, origin) => {
  res.writeHead(code, {
    "Content-Type": "application/json; charset=utf-8",
    /* เบราว์เซอร์ไม่ยอมให้ใช้ "*" คู่กับ credentials จึงสะท้อน Origin กลับเมื่อยังไม่ได้ระบุไว้
       ของจริงควรตั้ง ALLOW_ORIGIN ให้ชี้โดเมนของแฟ้มสะสมงานโดยตรง */
    "Access-Control-Allow-Origin": ALLOW_ORIGIN === "*" ? (origin || "*") : ALLOW_ORIGIN,
    "Vary": "Origin",
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
    "Access-Control-Allow-Methods": "GET, PUT, OPTIONS",
    "Cache-Control": "no-store"
  });
  res.end(JSON.stringify(body));
};

const authorised = (req, user) => {
  if (!Object.keys(TOKENS).length) return true;             /* โหมดทดลอง: ไม่ตรวจโทเคน */
  const header = req.headers.authorization || "";
  const token = header.replace(/^Bearer\s+/i, "");
  return !!user && TOKENS[user] && TOKENS[user] === token;
};

http.createServer((req, res) => {
  const origin = req.headers.origin || "";
  const url = new URL(req.url, "http://localhost");
  if (req.method === "OPTIONS") return send(res, 204, {}, origin);
  if (url.pathname !== ROUTE) return send(res, 404, { error: "not found" }, origin);

  if (req.method === "GET") {
    const user = url.searchParams.get("user") || "";
    if (!authorised(req, user)) return send(res, 401, { error: "unauthorised" }, origin);
    const db = load();
    return send(res, 200, { user, updatedAt: db[user]?.updatedAt || "", items: db[user]?.items || [] }, origin);
  }

  if (req.method === "PUT") {
    let body = "", tooBig = false;
    req.on("data", (chunk) => {
      body += chunk;
      if (body.length > MAX_BODY) { tooBig = true; req.destroy(); }
    });
    req.on("end", () => {
      if (tooBig) return send(res, 413, { error: "payload too large" }, origin);
      let parsed;
      try { parsed = JSON.parse(body); } catch { return send(res, 400, { error: "bad json" }, origin); }
      const user = String(parsed.user || "");
      if (!user) return send(res, 400, { error: "missing user" }, origin);
      if (!authorised(req, user)) return send(res, 401, { error: "unauthorised" }, origin);
      const items = (Array.isArray(parsed.items) ? parsed.items : []).map(clean).filter(Boolean);
      const db = load();
      db[user] = { updatedAt: new Date().toISOString(), items };
      save(db);
      console.log(new Date().toISOString(), "PUT", user, items.length, "items");
      return send(res, 200, { ok: true, stored: items.length }, origin);
    });
    return;
  }
  return send(res, 405, { error: "method not allowed" }, origin);
}).listen(PORT, () => console.log("logbook sync server on :" + PORT + " route " + ROUTE + " file " + FILE));
