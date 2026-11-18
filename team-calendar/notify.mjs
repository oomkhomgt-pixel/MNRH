#!/usr/bin/env node
/* ส่งสรุปงานของแต่ละคนเข้ากลุ่ม LINE ของทีม
   ใช้:  node notify.mjs [--mode=today|tomorrow|auto] [--date=YYYY-MM-DD] [--dry-run]
     --mode=auto (ค่าเริ่มต้น)  ก่อนเที่ยงตามเวลาไทย = งานวันนี้ · หลังเที่ยง = งานพรุ่งนี้
     --date=...                 ส่งของวันที่ระบุ (ใช้ทดสอบ)
     --dry-run                  ไม่ส่งจริง พิมพ์ข้อความออกมาดู

   ค่าลับมาจาก environment variable เท่านั้น (GitHub Secrets) ห้ามเขียนลงไฟล์ใดในโปรเจกต์:
     LINE_CHANNEL_ACCESS_TOKEN   token ของบอท (ใช้ตัวเดียวกับ line-alert/ ได้ — บอทเดียวอยู่ได้หลายกลุ่ม)
     TEAM_LINE_GROUP_ID          group ID ของกลุ่ม LINE ทีมฟ้า
     TEAM_LINE_USER_IDS          (ไม่บังคับ) JSON จับคู่ id สมาชิก → LINE userId เพื่อ @แท็กชื่อ
                                 เช่น {"r2":"U1234...","staff-a":"Uabcd..."} — คนที่ถูกแท็กได้แจ้งเตือนแม้ปิดเสียงกลุ่ม */
import { fileURLToPath } from "node:url";
import { PALETTE, validate, onDay, absentOn, conflicts, describeConflict, memberMap, thaiDate,
  bangkokToday, bangkokHour, addDays, holidayMap } from "./lib.mjs";

const LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push";
const MAX_LEN = 4900;   // LINE จำกัด 5000 ตัวอักษรต่อข้อความ

/* textV2: {key} คือจุดแทนที่ (ใช้ @แท็ก) จึงต้องหนีวงเล็บปีกกาที่อยู่ในข้อความจริงเป็น {{ }} */
const esc = s => String(s).replace(/\{/g, "{{").replace(/\}/g, "}}");

function timeLabel(o) {
  if (o.allDay) return o.date < o.endDate ? "ทั้งวัน (ถึง " + thaiDate(o.endDate, { year: false }) + ")" : "ทั้งวัน";
  return o.start + "–" + o.end + (o.overnight ? " (+1)" : "");
}
const line = o => "  • " + timeLabel(o) + " " + o.title + (o.location ? " · " + o.location : "");

/* คืน { text, substitution, isEmpty } — แยกจากการส่ง เพื่อทดสอบได้โดยไม่ยิง network */
export function formatMessage(s, date, { mode = "today", userIds = {} } = {}) {
  const mm = memberMap(s);
  const hol = holidayMap(s).get(date);
  /* ไม่นับเวรข้ามคืนที่เริ่มเมื่อวาน (คนอยู่เวรรู้อยู่แล้ว) — นับงานที่เริ่มวันนี้ และงานทั้งวันที่คร่อมวันนี้ */
  const occ = onDay(s, date).filter(o => o.kind !== "holiday" && (o.date === date || o.allDay));
  const absent = absentOn(s, date);

  const substitution = {};
  let n = 0;
  const who = id => {
    const m = mm.get(id);
    const dot = PALETTE[m.color].emoji;
    if (userIds[id]) {
      const key = "m" + (n++);
      substitution[key] = { type: "mention", mentionee: { type: "user", userId: userIds[id] } };
      return dot + " {" + key + "}";
    }
    return dot + " " + esc(m.name);
  };

  const head = (mode === "tomorrow" ? "🗓 พรุ่งนี้" : "📅 วันนี้") + " · " + esc(s.team.short || s.team.name) + "\n" + thaiDate(date, { long: true });
  const parts = [head];
  if (hol) parts.push("🎌 วันหยุด: " + esc(hol));

  const teamWide = occ.filter(o => o.item.who.includes("all"));
  if (teamWide.length) parts.push("👥 ทั้งทีม\n" + teamWide.map(o => esc(line(o))).join("\n"));

  for (const m of s.members) {
    if (absent.has(m.id)) continue;
    const mine = occ.filter(o => !o.item.who.includes("all") && o.who.includes(m.id));
    if (mine.length) parts.push(who(m.id) + " " + esc(m.role ? "(" + m.role + ")" : "") + "\n" + mine.map(o => esc(line(o))).join("\n"));
  }

  if (absent.size) {
    parts.push("🏖 ไม่อยู่\n" + [...absent].map(([id, o]) =>
      "  " + who(id) + " — " + esc(o.title + (o.endDate > date ? " ถึง " + thaiDate(o.endDate, { year: false }) : ""))).join("\n"));
  }

  const cs = conflicts(s, date, date).filter(c => c.date === date);
  if (cs.length) parts.push("⚠️ งานชนกัน — ผู้ประสานงานโปรดตรวจ\n" + cs.map(c => "  • " + esc(describeConflict(s, c))).join("\n"));

  if (s.team.page_url) parts.push("ดูปฏิทินทั้งหมด: " + s.team.page_url);

  let text = parts.join("\n\n");
  if (text.length > MAX_LEN) text = text.slice(0, MAX_LEN - 30) + "\n… (ตัดเพราะยาวเกิน ดูต่อในปฏิทิน)";
  return { text, substitution, isEmpty: occ.length === 0 };
}

export function lineMessage({ text, substitution }) {
  return Object.keys(substitution).length
    ? { type: "textV2", text, substitution }
    : { type: "text", text: text.replace(/\{\{/g, "{").replace(/\}\}/g, "}") };
}

export async function push({ token, groupId, message }) {
  if (!token) throw new Error("ไม่มี LINE_CHANNEL_ACCESS_TOKEN — ตั้งค่าใน GitHub Secrets ก่อน (ดู team-calendar/README.md)");
  if (!groupId) throw new Error("ไม่มี TEAM_LINE_GROUP_ID — ตั้งค่าใน GitHub Secrets ก่อน (ดู team-calendar/README.md)");
  const res = await fetch(LINE_PUSH_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: "Bearer " + token },
    body: JSON.stringify({ to: groupId, messages: [message] })
  });
  if (!res.ok) throw new Error("LINE API ตอบกลับ HTTP " + res.status + ": " + (await res.text().catch(() => "")));
}

function parseUserIds(raw) {
  if (!raw) return {};
  try { const o = JSON.parse(raw); return o && typeof o === "object" ? o : {}; }
  catch { console.warn("⚠️  TEAM_LINE_USER_IDS ไม่ใช่ JSON ที่ถูกต้อง — ส่งแบบไม่แท็กชื่อ"); return {}; }
}

async function main() {
  const { loadSchedule } = await import("./build.mjs");
  const args = Object.fromEntries(process.argv.slice(2).map(a => a.replace(/^--/, "").split("=")).map(([k, v]) => [k, v ?? true]));
  const dryRun = !!args["dry-run"] || process.env.LINE_DRY_RUN === "1";
  let mode = args.mode || "auto";
  if (mode === "auto") mode = bangkokHour() < 12 ? "today" : "tomorrow";
  const date = args.date || (mode === "tomorrow" ? addDays(bangkokToday(), 1) : bangkokToday());

  const s = await loadSchedule();
  const { errors } = validate(s);
  if (errors.length) throw new Error("schedule.json มีข้อผิดพลาด " + errors.length + " จุด — รัน node team-calendar/build.mjs เพื่อดูรายละเอียด");

  const userIds = parseUserIds(process.env.TEAM_LINE_USER_IDS);
  const unknown = Object.keys(userIds).filter(id => !s.members.some(m => m.id === id));
  if (unknown.length) console.warn("⚠️  TEAM_LINE_USER_IDS มี id ที่ไม่อยู่ใน members: " + unknown.join(", "));

  const msg = formatMessage(s, date, { mode, userIds });
  console.log("== " + mode + " " + date + " · แท็ก " + Object.keys(msg.substitution).length + " คน ==\n" + msg.text + "\n== จบ (" + msg.text.length + " ตัวอักษร) ==");
  if (msg.isEmpty) { console.log("ไม่มีงานของใครในวันนั้น — ไม่ส่งข้อความ (กันกลุ่มรก)"); return; }
  if (dryRun) { console.log("[dry-run] ไม่ได้ส่งเข้า LINE จริง"); return; }
  await push({ token: process.env.LINE_CHANNEL_ACCESS_TOKEN, groupId: process.env.TEAM_LINE_GROUP_ID, message: lineMessage(msg) });
  console.log("✅ ส่งเข้ากลุ่ม LINE แล้ว");
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  main().catch(e => { console.error("❌ " + e.message); process.exit(1); });
}
