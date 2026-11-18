/* เขียนไฟล์ iCalendar (RFC 5545) ที่ Apple Calendar และ Google Calendar "สมัครรับ" (subscribe) ได้
   ไม่ใช้ไลบรารี — รูปแบบไฟล์ไม่ซับซ้อน แต่มีกับดักที่ต้องทำให้ถูกเป๊ะ:
   · บรรทัดยาวเกิน 75 ไบต์ต้องพับ (ภาษาไทยหนึ่งตัวกิน 3 ไบต์ พับตามจำนวนตัวอักษรจะเกินและบางแอปอ่านไม่ออก)
   · ขึ้นบรรทัดด้วย CRLF
   · , ; \ และขึ้นบรรทัดใหม่ในข้อความต้อง escape
   · UNTIL ของ RRULE ต้องเป็น UTC (ลงท้าย Z) เมื่อ DTSTART มี TZID
   · DTSTART ของงานซ้ำต้องเป็น "ครั้งแรกที่ตรงกฎ" ไม่งั้นแอปปฏิทินจะโชว์ครั้งแรกเกินมาหนึ่งครั้ง
   · EXDATE ต้องมีเวลาเดียวกับ DTSTART ไม่งั้นแอปไม่ตัดวันนั้นออก */
import {
  PALETTE, TZ, addDays, ruleDates, excludedDates, memberMap, expandWho, titleOf, remindOf, autoId, minutes
} from "./lib.mjs";

const enc = new TextEncoder();
const SEG = new Intl.Segmenter("th", { granularity: "grapheme" });
/* ค่าคงที่ — ไฟล์ที่สร้างซ้ำจากข้อมูลเดิมต้องเหมือนเดิมทุกไบต์ (ตรวจใน CI ว่าไฟล์ใน repo ไม่ค้าง)
   แอปปฏิทินแบบสมัครรับโหลดทั้งไฟล์ใหม่ทุกรอบอยู่แล้ว ไม่ได้ใช้ DTSTAMP ตัดสินว่างานเปลี่ยนหรือไม่ */
const DTSTAMP = "20260101T000000Z";

export function escapeText(s) {
  return String(s ?? "").replace(/\\/g, "\\\\").replace(/;/g, "\\;").replace(/,/g, "\\,").replace(/\r?\n/g, "\\n");
}

export function fold(line) {
  if (enc.encode(line).length <= 75) return line;
  const parts = [];
  let cur = "", bytes = 0;
  /* พับตามขอบ "ตัวอักษรที่มองเห็น" (grapheme) ไม่ใช่ code point — สระบน/ล่างและวรรณยุกต์ไทย (ั ่ ็ ุ)
     และ emoji หลาย code point จะไม่ถูกแยกจากตัวหลักไปคนละบรรทัด (มาตรฐานยอมให้แยก แต่บางแอปแสดงเพี้ยน) */
  for (const { segment: ch } of SEG.segment(line)) {
    const b = enc.encode(ch).length;
    if (bytes + b > 75) { parts.push(cur); cur = " "; bytes = 1; }
    cur += ch; bytes += b;
  }
  parts.push(cur);
  return parts.join("\r\n");
}

const compact = d => d.replace(/-/g, "");
const local = (date, time) => compact(date) + "T" + time.replace(":", "") + "00";
/* สิ้นวัน until ตามเวลาไทย (23:59:59 +07) = 16:59:59 UTC ของวันเดียวกัน */
const untilUTC = d => compact(d) + "T165959Z";

const VTIMEZONE = [
  "BEGIN:VTIMEZONE", "TZID:" + TZ, "X-LIC-LOCATION:" + TZ,
  "BEGIN:STANDARD", "TZOFFSETFROM:+0700", "TZOFFSETTO:+0700", "TZNAME:+07", "DTSTART:19700101T000000", "END:STANDARD",
  "END:VTIMEZONE"
];

/* รายชื่อ feed ที่จะสร้าง: ปฏิทินรวมของทีม 1 อัน + ของแต่ละคน 1 อัน */
export function feedList(s) {
  return [
    { id: s.team.id, kind: "team", name: s.team.name, color: PALETTE[s.team.color]?.hex || PALETTE.blue.hex },
    ...s.members.map(m => ({ id: s.team.id + "-" + m.id, kind: "member", member: m,
      name: (s.team.short || s.team.name) + " · " + m.name, color: PALETTE[m.color].hex }))
  ];
}

function whoLine(s, ids) {
  const mm = memberMap(s);
  return ids.map(id => { const m = mm.get(id); return PALETTE[m.color].emoji + " " + m.name + (m.role ? " (" + m.role + ")" : ""); }).join(", ");
}

function teamSummary(s, item, ids) {
  const mm = memberMap(s);
  const title = titleOf(s, item);
  if (item.who.includes("all")) return "👥 " + title;
  const dots = ids.map(id => PALETTE[mm.get(id).color].emoji).join("");
  const names = ids.length <= 2 ? " — " + ids.map(id => mm.get(id).short || mm.get(id).name).join(", ") : "";
  return dots + " " + title + names;
}

function eventLines(s, feed, item, kind) {
  const ids = expandWho(s, item.who);
  if (feed.kind === "member" && !ids.includes(feed.member.id)) return null;

  const L = ["BEGIN:VEVENT"];
  const id = item.id || autoId(item);
  L.push("UID:" + id + "." + feed.id + "@" + s.team.id + ".mnrh-ortho");
  L.push("DTSTAMP:" + DTSTAMP);

  let firstDate = item.date;
  if (kind === "recurring") {
    firstDate = ruleDates(item, item.from, addDays(item.from, 400))[0];
    if (!firstDate) return null;   // กฎนี้ไม่มีครั้งไหนเกิดจริงในช่วงที่กำหนด
  }

  if (item.all_day) {
    const last = item.end_date || firstDate;
    L.push("DTSTART;VALUE=DATE:" + compact(firstDate));
    L.push("DTEND;VALUE=DATE:" + compact(addDays(last, 1)));   // DTEND ของงานทั้งวันเป็นวัน "ถัดจาก" วันสุดท้าย
  } else {
    const overnight = minutes(item.end) <= minutes(item.start);
    L.push("DTSTART;TZID=" + TZ + ":" + local(firstDate, item.start));
    L.push("DTEND;TZID=" + TZ + ":" + local(overnight ? addDays(firstDate, 1) : firstDate, item.end));
  }

  if (kind === "recurring") {
    const parts = item.weekly
      ? ["FREQ=WEEKLY", "WKST=MO", ...(item.every > 1 ? ["INTERVAL=" + item.every] : []), "BYDAY=" + item.weekly.join(",")]
      : ["FREQ=MONTHLY", "BYDAY=" + item.monthly.nth + item.monthly.day];
    if (item.until) parts.push("UNTIL=" + (item.all_day ? compact(item.until) : untilUTC(item.until)));
    L.push("RRULE:" + parts.join(";"));
    const ex = excludedDates(s, item);
    if (ex.length) L.push(item.all_day
      ? "EXDATE;VALUE=DATE:" + ex.map(compact).join(",")
      : "EXDATE;TZID=" + TZ + ":" + ex.map(d => local(d, item.start)).join(","));
  }

  const summary = feed.kind === "team" ? teamSummary(s, item, ids) : titleOf(s, item);
  L.push("SUMMARY:" + escapeText(summary));
  if (item.location) L.push("LOCATION:" + escapeText(item.location));
  const desc = ["ผู้รับผิดชอบ: " + whoLine(s, ids)];
  if (item.note) desc.push(item.note);
  if (s.team.page_url) desc.push("ปฏิทินทีม: " + s.team.page_url);
  L.push("DESCRIPTION:" + escapeText(desc.join("\n")));
  if (item.type) L.push("CATEGORIES:" + escapeText(s.task_types?.[item.type]?.label || item.type));
  /* COLOR (RFC 7986) — ใส่สีของคนแรกไว้ให้แอปที่รองรับ; Apple/Google ไม่อ่านค่านี้ในปฏิทินแบบสมัครรับ
     สีจริงที่เห็นจึงมาจาก "แยก feed ต่อคน" (สีทั้งปฏิทิน) + emoji ในหัวข้อของปฏิทินรวม */
  const colorMember = feed.kind === "member" ? feed.member : memberMap(s).get(ids[0]);
  if (colorMember) L.push("COLOR:" + PALETTE[colorMember.color].css);
  L.push("TRANSP:" + (item.type === "leave" ? "TRANSPARENT" : "OPAQUE"));

  const remind = remindOf(s, item);
  if (remind && !item.all_day) {
    L.push("BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:" + escapeText(titleOf(s, item)), "TRIGGER:-PT" + remind + "M", "END:VALARM");
  }
  L.push("END:VEVENT");
  return L;
}

function holidayLines(s, feed, h) {
  return [
    "BEGIN:VEVENT",
    "UID:hol-" + h.date + "." + feed.id + "@" + s.team.id + ".mnrh-ortho",
    "DTSTAMP:" + DTSTAMP,
    "DTSTART;VALUE=DATE:" + compact(h.date),
    "DTEND;VALUE=DATE:" + compact(addDays(h.date, 1)),
    "SUMMARY:" + escapeText("🎌 " + h.name),
    "CATEGORIES:" + escapeText("วันหยุด"),
    "TRANSP:TRANSPARENT",
    "END:VEVENT"
  ];
}

export function buildFeed(s, feed) {
  const L = [
    "BEGIN:VCALENDAR", "VERSION:2.0",
    "PRODID:-//MNRH Ortho//Team calendar//TH",
    "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
    "X-WR-CALNAME:" + escapeText(feed.name),
    "X-WR-CALDESC:" + escapeText(feed.kind === "team" ? "ปฏิทินรวมของ " + s.team.name : "งานของ " + feed.member.name + " — " + s.team.name),
    "X-WR-TIMEZONE:" + TZ,
    "X-APPLE-CALENDAR-COLOR:" + feed.color,
    "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
    "X-PUBLISHED-TTL:PT1H",
    ...VTIMEZONE
  ];
  (s.recurring || []).forEach((r, i) => { const x = eventLines(s, feed, r.id ? r : { ...r, id: "rec-" + i }, "recurring"); if (x) L.push(...x); });
  (s.events || []).forEach(e => { const x = eventLines(s, feed, e, "event"); if (x) L.push(...x); });
  if (feed.kind === "team" || s.team.holidays_in_member_feeds !== false) (s.holidays || []).forEach(h => L.push(...holidayLines(s, feed, h)));
  L.push("END:VCALENDAR");
  return L.map(fold).join("\r\n") + "\r\n";
}
