/* แกนกลางของปฏิทินทีม — ใช้ร่วมกันทั้งฝั่ง Node (สร้างไฟล์ .ics / ส่ง LINE) และหน้าเว็บ (index.html)
   จึงห้าม import อะไรของ Node ในไฟล์นี้ ทุกฟังก์ชันเป็น pure function รับ schedule.json เป็น input

   หลักเรื่องเวลา: ทีมอยู่ไทย (UTC+7 ตลอดปี ไม่มี daylight saving) วันที่ทุกตัวในไฟล์นี้เป็นสตริง "YYYY-MM-DD"
   ตามปฏิทินไทย และเวลาเป็น "HH:MM" ตามนาฬิกาไทย ไม่แปลงผ่าน Date ของเครื่องเลยยกเว้นตอนบวกลบวัน
   (ซึ่งทำบน UTC ล้วน) — กันบั๊กเครื่องที่ตั้งเขตเวลาอื่นแล้ววันเลื่อนไปหนึ่งวัน */

export const TZ = "Asia/Bangkok";
export const TZ_OFFSET_MIN = 7 * 60;

/* สีที่ให้เลือกได้ — ชื่อสีในไฟล์ schedule.json ต้องเป็นหนึ่งในนี้
   emoji ใช้ในข้อความ LINE และหัวข้อนัดในปฏิทินรวม (ปฏิทินรวมของ Google ให้สีเดียวทั้งปฏิทิน
   emoji จึงเป็นทางเดียวที่เห็น "สีของคน" ในปฏิทินเดียว) · css คือชื่อสีมาตรฐาน CSS ที่ใส่ใน COLOR ของ iCalendar */
export const PALETTE = {
  red:     { hex: "#D93F3F", css: "crimson",      emoji: "🔴", th: "แดง" },
  orange:  { hex: "#E8790C", css: "darkorange",   emoji: "🟠", th: "ส้ม" },
  yellow:  { hex: "#C9A400", css: "gold",         emoji: "🟡", th: "เหลือง" },
  green:   { hex: "#2E9E4F", css: "seagreen",     emoji: "🟢", th: "เขียว" },
  blue:    { hex: "#2F6FDB", css: "royalblue",    emoji: "🔵", th: "น้ำเงิน" },
  purple:  { hex: "#8A4FD1", css: "mediumpurple", emoji: "🟣", th: "ม่วง" },
  brown:   { hex: "#8B5A2B", css: "sienna",       emoji: "🟤", th: "น้ำตาล" },
  black:   { hex: "#3B3F45", css: "dimgray",      emoji: "⚫", th: "ดำ" },
  pink:    { hex: "#D6458F", css: "mediumvioletred", emoji: "🩷", th: "ชมพู" },
  teal:    { hex: "#1A9A9A", css: "darkcyan",     emoji: "🩵", th: "ฟ้าอมเขียว" },
  grey:    { hex: "#8A949E", css: "slategray",    emoji: "🩶", th: "เทา" }
};

export const WEEKDAYS = ["SU", "MO", "TU", "WE", "TH", "FR", "SA"];
export const TH_DAY_SHORT = ["อา.", "จ.", "อ.", "พ.", "พฤ.", "ศ.", "ส."];
export const TH_DAY_LONG = ["อาทิตย์", "จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์"];
export const TH_MONTH_SHORT = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."];
export const TH_MONTH_LONG = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน", "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"];

/* ---------- วันที่ (สตริง YYYY-MM-DD, คำนวณบน UTC ล้วน) ---------- */
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const TIME_RE = /^([01]\d|2[0-3]):[0-5]\d$/;

export function isDate(s) {
  if (typeof s !== "string" || !DATE_RE.test(s)) return false;
  const d = new Date(s + "T00:00:00Z");
  return !isNaN(d) && d.toISOString().slice(0, 10) === s;
}
export const isTime = s => typeof s === "string" && TIME_RE.test(s);
const toUTC = s => new Date(s + "T00:00:00Z");
const fromUTC = d => d.toISOString().slice(0, 10);
export const addDays = (s, n) => { const d = toUTC(s); d.setUTCDate(d.getUTCDate() + n); return fromUTC(d); };
export const weekday = s => toUTC(s).getUTCDay();
export const daysBetween = (a, b) => Math.round((toUTC(b) - toUTC(a)) / 86400000);
export const minutes = t => +t.slice(0, 2) * 60 + +t.slice(3, 5);

/* วันที่ "วันนี้" ตามนาฬิกาไทย ไม่ว่าเครื่องที่รันจะตั้งเขตเวลาไหน (GitHub Actions เป็น UTC) */
export function bangkokToday(now = new Date()) {
  return new Date(now.getTime() + TZ_OFFSET_MIN * 60000).toISOString().slice(0, 10);
}
export function bangkokHour(now = new Date()) {
  return new Date(now.getTime() + TZ_OFFSET_MIN * 60000).getUTCHours();
}

export function thaiDate(s, { long = false, year = true, day = true } = {}) {
  const d = toUTC(s);
  const wd = (long ? TH_DAY_LONG : TH_DAY_SHORT)[d.getUTCDay()];
  const m = (long ? TH_MONTH_LONG : TH_MONTH_SHORT)[d.getUTCMonth()];
  return (day ? wd + " " : "") + d.getUTCDate() + " " + m + (year ? " " + (d.getUTCFullYear() + 543) : "");
}

/* ---------- ตรวจไฟล์ schedule.json ----------
   คนแก้ไฟล์คือผู้ประสานงานทีม ไม่ใช่โปรแกรมเมอร์ ข้อความผิดพลาดจึงต้องบอกตำแหน่งและวิธีแก้เป็นภาษาไทย
   คืน { errors: [...], warnings: [...] } — errors มีแม้ข้อเดียว ไม่สร้างปฏิทิน (กันปฏิทินทั้งทีมพังเงียบ ๆ) */
export function validate(s) {
  const errors = [], warnings = [];
  const err = (where, msg) => errors.push(where + ": " + msg);
  const warn = (where, msg) => warnings.push(where + ": " + msg);

  if (!s || typeof s !== "object") return { errors: ["ไฟล์ว่างหรือไม่ใช่ JSON object"], warnings };
  if (!s.team || !s.team.id || !s.team.name) err("team", "ต้องมี id และ name ของทีม");
  else if (!/^[a-z0-9-]+$/.test(s.team.id)) err("team.id", "ใช้ได้เฉพาะ a-z 0-9 และ - (ใช้เป็นชื่อไฟล์ปฏิทิน)");

  const members = Array.isArray(s.members) ? s.members : [];
  if (!members.length) err("members", "ต้องมีสมาชิกอย่างน้อยหนึ่งคน");
  const ids = new Set(), colors = new Map();
  members.forEach((m, i) => {
    const w = `members[${i}]` + (m && m.name ? ` (${m.name})` : "");
    if (!m || !m.id || !/^[a-z0-9-]+$/.test(m.id)) return err(w, "id ต้องเป็น a-z 0-9 และ - เท่านั้น (ใช้เป็นชื่อไฟล์ปฏิทินของคนนี้)");
    if (m.id === s.team?.id) err(w, `id ซ้ำกับ team.id ("${m.id}") — ไฟล์ปฏิทินจะทับกัน`);
    if (ids.has(m.id)) err(w, `id "${m.id}" ซ้ำกับคนก่อนหน้า`);
    ids.add(m.id);
    if (!m.name) err(w, "ต้องมี name");
    if (!PALETTE[m.color]) err(w, `สี "${m.color}" ไม่มีในรายการ — เลือกจาก: ${Object.keys(PALETTE).join(", ")}`);
    else if (colors.has(m.color)) warn(w, `ใช้สี ${m.color} ซ้ำกับ ${colors.get(m.color)} — ในข้อความ LINE จะแยกสองคนนี้ด้วยสีไม่ได้`);
    else colors.set(m.color, m.name);
  });

  const types = s.task_types || {};
  const checkWho = (w, who) => {
    if (!Array.isArray(who) || !who.length) return err(w, 'ต้องมี "who" เป็นรายการ id สมาชิกอย่างน้อยหนึ่งคน เช่น ["r2"]');
    who.forEach(id => { if (!ids.has(id) && id !== "all") err(w, `ไม่รู้จักสมาชิก id "${id}" (มีแต่: ${[...ids].join(", ")} หรือ "all")`); });
  };
  const checkTimes = (w, e) => {
    if (e.all_day) { if (e.start || e.end) warn(w, "all_day แล้วไม่ต้องใส่ start/end — จะไม่ถูกใช้"); return; }
    if (!isTime(e.start)) err(w, `start "${e.start ?? ""}" ต้องเป็นเวลาแบบ HH:MM 24 ชม. เช่น "08:30" (หรือใส่ "all_day": true)`);
    if (!isTime(e.end)) err(w, `end "${e.end ?? ""}" ต้องเป็นเวลาแบบ HH:MM 24 ชม. เช่น "16:30"`);
    if (isTime(e.start) && e.start === e.end) err(w, "start กับ end เท่ากัน");
  };
  const checkType = (w, e) => {
    if (e.type && !types[e.type]) err(w, `type "${e.type}" ไม่มีใน task_types (มี: ${Object.keys(types).join(", ")})`);
    if (!e.title && !(e.type && types[e.type])) err(w, "ต้องมี title หรือ type");
  };
  const seen = new Set();
  const checkId = (w, e, fallback) => {
    const id = e.id || fallback;
    if (e.id && !/^[A-Za-z0-9._-]+$/.test(e.id)) err(w, "id ใช้ได้เฉพาะ A-Z a-z 0-9 . _ -");
    if (seen.has(id)) err(w, `id "${id}" ซ้ำ — แต่ละรายการต้องไม่ซ้ำกัน (ใส่ "id" ให้ต่างกัน)`);
    seen.add(id);
  };

  (s.holidays || []).forEach((h, i) => {
    if (!isDate(h.date)) err(`holidays[${i}]`, `date "${h.date}" ต้องเป็น YYYY-MM-DD (ค.ศ.) เช่น "2026-12-05"`);
    if (!h.name) err(`holidays[${i}]`, "ต้องมี name");
  });

  (s.recurring || []).forEach((r, i) => {
    const w = `recurring[${i}]` + (r.title ? ` (${r.title})` : "");
    checkType(w, r); checkWho(w, r.who); checkTimes(w, r); checkId(w, r, "rec-" + i);
    if (!isDate(r.from)) err(w, `from "${r.from ?? ""}" ต้องเป็นวันเริ่มแบบ YYYY-MM-DD`);
    if (r.until != null && !isDate(r.until)) err(w, `until "${r.until}" ต้องเป็น YYYY-MM-DD`);
    if (isDate(r.from) && isDate(r.until) && r.until < r.from) err(w, "until มาก่อน from");
    const hasW = Array.isArray(r.weekly), hasM = r.monthly && typeof r.monthly === "object";
    if (hasW === !!hasM) err(w, 'ต้องมีอย่างใดอย่างหนึ่ง: "weekly": ["MO","TH"] หรือ "monthly": {"nth": 1, "day": "FR"}');
    if (hasW) {
      if (!r.weekly.length) err(w, "weekly ว่าง");
      r.weekly.forEach(d => { if (!WEEKDAYS.includes(d)) err(w, `วัน "${d}" ไม่ถูก ใช้ ${WEEKDAYS.join(" ")}`); });
      if (r.every != null && !(Number.isInteger(r.every) && r.every >= 1 && r.every <= 8)) err(w, "every ต้องเป็นจำนวนเต็ม 1–8 (ทุกกี่สัปดาห์)");
    }
    if (hasM) {
      if (!WEEKDAYS.includes(r.monthly.day)) err(w, `monthly.day "${r.monthly.day}" ไม่ถูก ใช้ ${WEEKDAYS.join(" ")}`);
      if (![1, 2, 3, 4, -1].includes(r.monthly.nth)) err(w, "monthly.nth ต้องเป็น 1, 2, 3, 4 หรือ -1 (สัปดาห์สุดท้าย)");
    }
    (r.cancel || []).forEach(d => { if (!isDate(d)) err(w, `cancel มีวันที่ "${d}" ที่ไม่ใช่ YYYY-MM-DD`); });
    if (!r.until) warn(w, "ไม่มี until — จะซ้ำไปเรื่อย ๆ ไม่มีวันจบ (ปกติควรจบตามรอบหมุนเวียน)");
  });

  (s.events || []).forEach((e, i) => {
    const w = `events[${i}]` + (e.title ? ` (${e.title})` : "");
    checkType(w, e); checkWho(w, e.who); checkTimes(w, e); checkId(w, e, autoId(e));
    if (!isDate(e.date)) err(w, `date "${e.date ?? ""}" ต้องเป็น YYYY-MM-DD (ค.ศ.) เช่น "2026-11-20"`);
    if (e.end_date != null) {
      if (!isDate(e.end_date)) err(w, `end_date "${e.end_date}" ต้องเป็น YYYY-MM-DD`);
      else if (isDate(e.date) && e.end_date < e.date) err(w, "end_date มาก่อน date");
      if (!e.all_day) err(w, 'end_date ใช้ได้กับงานทั้งวันเท่านั้น — ใส่ "all_day": true (เช่น ลา, ไปประชุม)');
    }
  });

  return { errors, warnings };
}

/* id อัตโนมัติสำหรับงานครั้งเดียวที่ไม่ได้ใส่ id — ผูกกับเนื้อหา ถ้าแก้งานนั้น ปฏิทินจะลบอันเก่าแล้วใส่อันใหม่ (ถูกต้อง) */
export function autoId(e) {
  const key = [e.date, e.start, e.end, e.type, e.title, (e.who || []).join("+")].join("|");
  let h = 2166136261;
  for (let i = 0; i < key.length; i++) { h ^= key.charCodeAt(i); h = Math.imul(h, 16777619); }
  return "ev-" + (e.date || "x") + "-" + (h >>> 0).toString(36);
}

/* ---------- ตัวช่วยอ่านข้อมูล ---------- */
export function memberMap(s) { return new Map(s.members.map(m => [m.id, m])); }
export function expandWho(s, who) { return who.includes("all") ? s.members.map(m => m.id) : who; }
export function titleOf(s, item) { return item.title || s.task_types?.[item.type]?.label || item.type; }
export function remindOf(s, item) {
  const v = item.remind_min ?? s.task_types?.[item.type]?.remind_min ?? s.team?.remind_min;
  return Number.isInteger(v) && v > 0 ? v : null;
}
export function holidayMap(s) { return new Map((s.holidays || []).map(h => [h.date, h.name])); }

/* ---------- คำนวณวันที่ของงานซ้ำ ---------- */
function nthWeekdayOfMonth(year, month0, wd, nth) {
  if (nth > 0) {
    const first = new Date(Date.UTC(year, month0, 1)).getUTCDay();
    const day = 1 + ((wd - first + 7) % 7) + (nth - 1) * 7;
    const d = new Date(Date.UTC(year, month0, day));
    return d.getUTCMonth() === month0 ? fromUTC(d) : null;
  }
  const last = new Date(Date.UTC(year, month0 + 1, 0));
  const back = (last.getUTCDay() - wd + 7) % 7;
  last.setUTCDate(last.getUTCDate() - back);
  return fromUTC(last);
}

/* วันทั้งหมดที่กฎซ้ำนี้ "ตรงตามกฎ" ในช่วง [from, to] — ยังไม่ตัดวันยกเลิกและวันหยุด
   ต้องให้ผลตรงกับ RRULE ที่ ics.mjs เขียน (WKST=MO) */
export function ruleDates(r, from, to) {
  const out = [];
  const start = r.from > from ? r.from : from;
  const end = r.until && r.until < to ? r.until : to;
  if (start > end) return out;
  if (r.weekly) {
    const every = r.every || 1;
    const days = new Set(r.weekly.map(d => WEEKDAYS.indexOf(d)));
    /* นับสัปดาห์จากสัปดาห์ของ "ครั้งแรกจริง" (= DTSTART ในไฟล์ .ics) ไม่ใช่สัปดาห์ของ from
       เพราะ RRULE นับ INTERVAL จากสัปดาห์ของ DTSTART — ถ้า from เป็นวันอาทิตย์แล้วงานเป็นวันจันทร์ สองอย่างนี้คนละสัปดาห์ */
    let first = r.from;
    while (!days.has(weekday(first))) first = addDays(first, 1);
    const anchorMon = addDays(first, -((weekday(first) + 6) % 7));
    for (let d = start; d <= end; d = addDays(d, 1)) {
      if (!days.has(weekday(d))) continue;
      const weekIdx = Math.floor(daysBetween(anchorMon, d) / 7);
      if (weekIdx % every === 0) out.push(d);
    }
  } else {
    const wd = WEEKDAYS.indexOf(r.monthly.day);
    let y = +start.slice(0, 4), m = +start.slice(5, 7) - 1;
    for (;;) {
      const d = nthWeekdayOfMonth(y, m, wd, r.monthly.nth);
      if (d && d > end) break;
      if (d && d >= start) out.push(d);
      if (++m > 11) { m = 0; y++; }
      if (y > +end.slice(0, 4) + 1) break;
    }
  }
  return out;
}

/* วันที่งานซ้ำนี้ "ไม่เกิด" — ยกเลิกเอง + วันหยุดราชการ (ถ้า skip_holidays ไม่ได้ปิด)
   ฝั่งไฟล์ .ics ใช้ชุดเดียวกันนี้เขียนเป็น EXDATE */
export function excludedDates(s, r, from = "0000-01-01", to = "9999-12-31") {
  const skipHol = r.skip_holidays ?? s.team?.skip_holidays_default ?? true;
  const set = new Set(r.cancel || []);
  if (skipHol) (s.holidays || []).forEach(h => set.add(h.date));
  const valid = new Set(ruleDates(r, from, to));
  return [...set].filter(d => valid.has(d)).sort();
}

/* ---------- ขยายทุกอย่างเป็นรายการ "นัด" ในช่วงวันที่ ----------
   ใช้ทั้งหน้าเว็บ (แสดงปฏิทิน) และข้อความ LINE — ฝั่ง .ics ไม่ใช้ฟังก์ชันนี้ เพราะเขียนเป็น RRULE ให้แอปปฏิทินขยายเอง
   แต่ทดสอบไว้ว่าสองทางให้วันตรงกัน (test.mjs) */
export function occurrences(s, from, to) {
  const out = [];
  const push = (item, kind, date, endDate) => {
    const allDay = !!item.all_day;
    const overnight = !allDay && minutes(item.end) <= minutes(item.start);
    out.push({
      key: (item.id || (kind === "event" ? autoId(item) : "")) + "@" + date,
      id: item.id || autoId(item), kind, item, date,
      endDate: allDay ? (endDate || date) : (overnight ? addDays(date, 1) : date),
      allDay, overnight,
      start: allDay ? null : item.start, end: allDay ? null : item.end,
      title: titleOf(s, item), type: item.type || "other",
      who: expandWho(s, item.who), location: item.location || "", note: item.note || ""
    });
  };
  (s.recurring || []).forEach((r, i) => {
    const item = r.id ? r : { ...r, id: "rec-" + i };
    const ex = new Set(excludedDates(s, item, from, to));
    ruleDates(item, from, to).forEach(d => { if (!ex.has(d)) push(item, "recurring", d); });
  });
  (s.events || []).forEach(e => {
    const last = e.all_day && e.end_date ? e.end_date : e.date;
    if (last < from || e.date > to) return;
    push(e, "event", e.date, e.end_date);
  });
  (s.holidays || []).forEach(h => {
    if (h.date >= from && h.date <= to)
      out.push({ key: "hol@" + h.date, id: "hol-" + h.date, kind: "holiday", item: h, date: h.date, endDate: h.date,
        allDay: true, overnight: false, start: null, end: null, title: h.name, type: "holiday", who: [], location: "", note: "" });
  });
  return out.sort((a, b) =>
    a.date.localeCompare(b.date) ||
    (a.allDay === b.allDay ? 0 : a.allDay ? -1 : 1) ||
    (a.start || "").localeCompare(b.start || "") ||
    a.title.localeCompare(b.title));
}

/* นัดที่ "แตะ" วันนั้น — รวมงานทั้งวันหลายวันที่คร่อมวันนั้น และเวรข้ามคืนที่เริ่มเมื่อวาน (แสดงเป็น "ต่อจากเมื่อวาน") */
export function onDay(s, date) {
  return occurrences(s, addDays(date, -1), date).filter(o =>
    o.date === date || (o.allDay && o.date < date && o.endDate >= date) || (o.overnight && o.endDate === date));
}

/* ---------- ตรวจงานชนกัน ----------
   1) คนเดียวกันมีงานที่มีเวลาซ้อนกัน (รวมเวรข้ามคืน)
   2) คนที่ลา / ไปประชุมทั้งวัน แต่ยังมีชื่อในงานที่ระบุตัวคน
   งานที่ระบุ "all" (ทั้งทีม เช่นราวด์เช้า) ไม่นับ — คนลาไม่ต้องมาราวด์อยู่แล้ว และหน้าเว็บ/LINE ตัดคนลาออกให้เอง */
const BLOCKING_ALLDAY = new Set(["leave", "conf"]);
const absMin = (date, time, base) => daysBetween(base, date) * 1440 + minutes(time);

export function absentOn(s, date) {
  const set = new Map();
  onDay(s, date).forEach(o => {
    if (o.allDay && BLOCKING_ALLDAY.has(o.type)) o.who.forEach(id => { if (!set.has(id)) set.set(id, o); });
  });
  return set;
}

export function conflicts(s, from, to) {
  const out = [];
  const occ = occurrences(s, addDays(from, -1), to).filter(o => o.kind !== "holiday" && !o.item.who.includes("all"));
  const byPerson = new Map();
  occ.forEach(o => o.who.forEach(id => { if (!byPerson.has(id)) byPerson.set(id, []); byPerson.get(id).push(o); }));
  for (const [id, list] of byPerson) {
    const timed = list.filter(o => !o.allDay);
    for (let i = 0; i < timed.length; i++) for (let j = i + 1; j < timed.length; j++) {
      const a = timed[i], b = timed[j];
      const a0 = absMin(a.date, a.start, from), a1 = absMin(a.endDate, a.end, from);
      const b0 = absMin(b.date, b.start, from), b1 = absMin(b.endDate, b.end, from);
      if (a0 < b1 && b0 < a1 && (a.date >= from || b.date >= from))
        out.push({ date: a.date > b.date ? a.date : b.date, member: id, a, b, reason: "overlap" });
    }
    const blocks = list.filter(o => o.allDay && BLOCKING_ALLDAY.has(o.type));
    for (const blk of blocks) for (const t of list) {
      if (t === blk || (t.allDay && BLOCKING_ALLDAY.has(t.type))) continue;
      if (t.date >= blk.date && t.date <= blk.endDate && t.date >= from && t.date <= to)
        out.push({ date: t.date, member: id, a: blk, b: t, reason: "absent" });
    }
  }
  return out.sort((x, y) => x.date.localeCompare(y.date) || x.member.localeCompare(y.member));
}

export function describeConflict(s, c) {
  const m = memberMap(s).get(c.member);
  const t = o => o.title + (o.allDay ? "" : " " + o.start + "–" + o.end);
  return thaiDate(c.date) + " · " + m.name + ": " +
    (c.reason === "absent" ? "ติด \"" + c.a.title + "\" แต่มีชื่อใน \"" + t(c.b) + "\"" : "\"" + t(c.a) + "\" ชนกับ \"" + t(c.b) + "\"");
}
