/* ทดสอบ Code.gs โดยจำลองบริการของ Google Apps Script (CalendarApp, UrlFetchApp, PropertiesService ฯลฯ) ในเครื่อง
   ไม่แตะบัญชี Google หรือ LINE จริง ไม่ยิง network:  node --test team-calendar/google-calendar/test.mjs
   สิ่งที่ชุดนี้พิสูจน์ได้คือ "ตรรกะของสคริปต์" (วันที่ การวนเวร การตัดวันหยุด ข้อความ การจำกลุ่ม)
   สิ่งที่พิสูจน์ไม่ได้คือพฤติกรรมจริงของ Google/LINE — ต้องทดสอบบนบัญชีจริงตาม README */
import { test } from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const SOURCE = readFileSync(join(here, "Code.gs"), "utf8");
const TZ = "Asia/Bangkok";
const bkk = (ymd, hm = "00:00") => new Date(`${ymd}T${hm}:00+07:00`);
const fmt = (date, tz, pattern) => {
  const p = Object.fromEntries(new Intl.DateTimeFormat("en-GB", { timeZone: tz, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" })
    .formatToParts(date).map(x => [x.type, x.value]));
  if (pattern === "yyyy-MM-dd") return `${p.year}-${p.month}-${p.day}`;
  if (pattern === "HH:mm") return `${p.hour}:${p.minute}`;
  throw new Error("mock formatDate: รูปแบบที่ไม่รองรับ " + pattern);
};

const G1 = "C" + "a1".repeat(16), G2 = "C" + "b2".repeat(16);   // รูปแบบ group ID ของ LINE: C + เลขฐานสิบหก 32 ตัว

const HOLIDAY_FIXTURE = [
  "BEGIN:VCALENDAR", "VERSION:2.0",
  ...[["20261205", "20261206", "วันคล้ายวันพระบรมราชสมภพ ร.9", "วันหยุดนักขัตฤกษ์"],
    ["20261207", "20261208", "วันหยุดชดเชยวันคล้ายวันพระบรมราช\r\n สมภพ ร.9", "วันหยุดนักขัตฤกษ์"],
    ["20261210", "20261211", "​วันรัฐธรรมนูญ", "วันหยุดนักขัตฤกษ์"],
    ["20261216", "20261217", "พระราชพิธีฯ", "วันหยุดนักขัตฤกษ์"],
    ["20261225", "20261226", "วันคริสต์มาส", "วันสำคัญ\\nหากต้องการซ่อนวันสำคัญ ให้ไปที่การตั้งค่า"],
    ["20261231", "20270101", "วันสิ้นปี", "วันหยุดนักขัตฤกษ์"],
    ["20270101", "20270102", "วันขื้นปีใหม่", "วันหยุดนักขัตฤกษ์"]]
    .flatMap(([s, e, sum, desc]) => ["BEGIN:VEVENT", `DTSTART;VALUE=DATE:${s}`, `DTEND;VALUE=DATE:${e}`, `DESCRIPTION:${desc}`, `SUMMARY:${sum}`, "END:VEVENT"]),
  "END:VCALENDAR"
].join("\r\n");

/* สร้าง "บัญชี Google จำลอง" หนึ่งบัญชี แล้วโหลด Code.gs เข้าไป */
function makeWorld(nowIso = "2026-11-18T10:00:00+07:00") {
  const w = { now: new Date(nowIso), props: new Map(), calendars: [], fetches: [], triggers: [], acl: [], seq: 0, cache: new Map(),
    quota: { type: "limited", value: 300, used: 0 }, members: 5, botGroups: new Set([G1]), pushScript: [], tokenOk: true };

  class Event {
    constructor(cal, o) { Object.assign(this, o); this.cal = cal; }
    getId() { return this.id; }
    getTitle() { return this.title; }
    getLocation() { return this.location || ""; }
    isAllDayEvent() { return !!this.allDay; }
    getStartTime() { return this.start; }
    getEndTime() { return this.end; }
    getAllDayStartDate() { if (!this.allDay) throw new Error("not all-day"); return this.start; }
    getAllDayEndDate() { if (!this.allDay) throw new Error("not all-day"); return this.end; }   // วันถัดจากวันสุดท้าย เหมือนของจริง
    getLastUpdated() { return this.updated; }
    getDateCreated() { return this.created; }
    isRecurringEvent() { return !!this.seriesRef; }
    getTag(k) { const o = this.ref || this.seriesRef || {}; return (o.tags && o.tags[k]) || null; }
    setTag(k, v) { const o = this.ref || this.seriesRef; o.tags = o.tags || {}; o.tags[k] = v; return this; }
    deleteEvent() {
      if (this.seriesRef) this.seriesRef.deleted.add(fmt(this.start, TZ, "yyyy-MM-dd"));
      else this.cal.singles = this.cal.singles.filter(s => s.id !== this.id);
    }
  }
  class Cal {
    constructor(name, opt = {}) { this.name = name; this.id = "cal" + (++w.seq) + "@group.calendar.google.com"; this.color = opt.color; this.series = []; this.singles = []; }
    getName() { return this.name; } getId() { return this.id; }
    getColor() { return this.color; } getTimeZone() { return TZ; }
    setColor(c) { this.color = c; return this; }
    createEventSeries(title, start, end, rule, opt = {}) {
      const s = { id: "series" + (++w.seq) + "@google.com", title, start, end, interval: rule._interval || 1, until: rule._until, location: opt.location, deleted: new Set(), created: w.now, updated: w.now };
      this.series.push(s);
      return { getId: () => s.id };
    }
    add(o) { const e = { id: "single" + (++w.seq) + "@google.com", created: w.now, updated: w.now, ...o }; this.singles.push(e); return e; }
    createAllDayEvent(title, date, endOrOpt, opt) { const d = fmt(date, TZ, "yyyy-MM-dd"); const hasEnd = endOrOpt instanceof Date || (endOrOpt && typeof endOrOpt.getTime === "function");
      const end = hasEnd ? bkk(fmt(endOrOpt, TZ, "yyyy-MM-dd")) : new Date(bkk(d).getTime() + 864e5);
      const e = this.add({ title, allDay: true, start: bkk(d), end, description: ((hasEnd ? opt : endOrOpt) || {}).description }); return new Event(this, { ...e, ref: e }); }
    createEvent(title, start, end, opt = {}) { const e = this.add({ title, start, end, location: opt.location }); return new Event(this, { ...e, ref: e }); }
    getEvents(from, to) {
      const out = [];
      for (const s of this.series) {
        for (let k = 0; k < 400; k++) {
          const st = new Date(s.start.getTime() + k * s.interval * 7 * 86400000);
          if (s.until && st > s.until) break;
          const en = new Date(s.end.getTime() + k * s.interval * 7 * 86400000);
          if (st < to && en > from && !s.deleted.has(fmt(st, TZ, "yyyy-MM-dd")))
            out.push(new Event(this, { id: s.id, title: s.title, start: st, end: en, location: s.location, created: s.created, updated: s.updated, seriesRef: s }));
        }
      }
      for (const e of this.singles) if (e.start < to && e.end > from) out.push(new Event(this, { ...e, ref: e }));
      return out;
    }
  }
  const rule = () => ({ _interval: 1, addWeeklyRule() { return this; }, interval(n) { this._interval = n; return this; }, until(d) { this._until = d; return this; } });

  const NowDate = class extends Date { constructor(...a) { if (a.length) super(...a); else super(w.now.getTime()); } static now() { return w.now.getTime(); } };
  const ctx = vm.createContext({
    Date: NowDate, JSON, Math, console: { log() {}, warn(m) { if (w.onWarn) w.onWarn(String(m)); }, error() {} },
    CalendarApp: {
      getAllOwnedCalendars: () => w.calendars.slice(),
      getCalendarById: id => w.calendars.find(c => c.id === id) || null,
      createCalendar: (name, opt) => { const c = new Cal(name, opt); w.calendars.push(c); return c; },
      newRecurrence: rule
    },
    PropertiesService: { getScriptProperties: () => ({
      getProperty: k => (w.props.has(k) ? w.props.get(k) : null), setProperty: (k, v) => { w.props.set(k, String(v)); }, deleteProperty: k => { w.props.delete(k); } }) },
    Utilities: { formatDate: fmt, getUuid: () => "11111111-2222-3333-4444-" + String(++w.seq).padStart(12, "0"), sleep() {} },
    Infinity, Number, String, parseInt,
    Session: { getScriptTimeZone: () => TZ, getEffectiveUser: () => ({ getEmail: () => "owner@example.com" }) },
    UrlFetchApp: { fetch: (url, opt = {}) => {
      w.fetches.push({ url, method: opt.method || "get", body: opt.payload ? JSON.parse(opt.payload) : null,
        auth: opt.headers && opt.headers.Authorization, retryKey: opt.headers && opt.headers["X-Line-Retry-Key"] });
      const reply = (code, obj) => ({ getResponseCode: () => code, getContentText: () => (typeof obj === "string" ? obj : JSON.stringify(obj)) });
      if (url.includes("calendar.google.com/calendar/ical")) return reply(200, w.holidayIcs ?? HOLIDAY_FIXTURE);
      if (url.includes("generativelanguage.googleapis.com")) { w.geminiReq = { key: opt.headers["x-goog-api-key"], body: JSON.parse(opt.payload) }; return reply(w.geminiStatus || 200, w.gemini); }
      const path = url.replace("https://api.line.me/v2/bot", "");
      if (!w.tokenOk) return reply(401, { message: "Authentication failed" });
      if (path === "/info") return reply(200, { displayName: "ปฏิทินสายฟ้า", basicId: "@000test" });
      if (path === "/message/quota") return reply(200, w.quota.type === "limited" ? { type: "limited", value: w.quota.value } : { type: "none" });
      if (path === "/message/quota/consumption") return reply(200, { totalUsage: w.quota.used });
      const g = /^\/group\/([^/]+)\/(summary|members\/count)$/.exec(path);
      if (g) return !w.botGroups.has(g[1]) ? reply(404, { message: "Not found" }) : reply(200, g[2] === "summary" ? { groupId: g[1], groupName: "อ.สายฟ้า" } : { count: w.members });
      if (path === "/message/reply") return reply(200, {});
      if (path === "/message/push") {
        let code = w.pushScript.length ? w.pushScript.shift() : (w.quota.type === "limited" && w.quota.used + w.members > w.quota.value ? 429 : 200);
        if (code === "throw") throw new Error("Address unavailable");
        if (code === 200) w.quota.used += w.members;
        return reply(code, code === 429 ? { message: w.rateLimited ? "The API rate limit has been exceeded." : "You have reached your monthly limit." } : {});
      }
      return reply(404, {});
    } },
    ScriptApp: {
      getProjectTriggers: () => w.triggers.slice(),
      deleteTrigger: t => { w.triggers = w.triggers.filter(x => x !== t); },
      WeekDay: { MONDAY: "MONDAY" },
      newTrigger: fn => { const t = { fn, getHandlerFunction: () => fn }; const b = { onWeekDay: d => (t.weekDay = d, b), timeBased: () => b, atHour: h => (t.hour = h, b), nearMinute: m => (t.minute = m, b), everyDays: () => b, onMonthDay: d => (t.monthDay = d, b), inTimezone: z => (t.tz = z, b), create: () => { w.triggers.push(t); return t; } }; return b; }
    },
    LockService: { getScriptLock: () => ({ waitLock() {}, tryLock: () => true, releaseLock() {} }) },
    CacheService: { getScriptCache: () => ({ get: k => (w.cache.has(k) ? w.cache.get(k) : null), put: (k, v) => { w.cache.set(k, v); } }) },
    HtmlService: { createHtmlOutput: t => ({ html: t }) },
    Calendar: { Acl: { insert: (res, calId, opt) => { w.acl.push({ ...res, calId, opt }); } } }
  });
  vm.runInContext(SOURCE, ctx, { filename: "Code.gs" });
  w.run = code => vm.runInContext(code, ctx);
  w.json = code => JSON.parse(vm.runInContext(`JSON.stringify(${code})`, ctx));
  w.cal = short => w.calendars.find(c => c.name === "สายฟ้า – " + short);
  w.titlesOn = (short, ymd) => w.cal(short).getEvents(bkk(ymd), bkk(ymd, "23:59")).map(e => e.title).sort();
  w.lineCalls = () => w.fetches.filter(f => f.url.includes("api.line.me"));
  w.pushes = () => w.fetches.filter(f => f.url.endsWith("/message/push"));
  w.replies = () => w.fetches.filter(f => f.url.endsWith("/message/reply"));
  w.linked = () => { w.props.set("LINE_TOKEN", "tok"); w.props.set("LINE_GROUP_ID", G1); return w; };
  // ตั้งค่าครบ: ปฏิทิน + งานประจำ + เวรวน (ยังไม่รู้วันหยุด — step3 จะมาจัดใหม่เมื่อรู้)
  w.setup = () => { w.run("step1_createCalendars(); step2_createRoutine(); syncRotations_([], today_());"); return w; };
  w.erOn = ymd => PEOPLE.filter(p => w.titlesOn(p, ymd).includes("ER"));
  return w;
}
const PEOPLE = ["มานิตา", "ศุภศักดิ์", "คงธัช", "อดิศร", "ชนกันต์"];

test("แผนงานประจำ (รายการซ้ำรายสัปดาห์) ตรงกับที่ทีมกำหนด (เริ่ม 18 พ.ย. 2569)", () => {
  const w = makeWorld();
  w.run("checkConfig_(CONFIG)");
  const plan = w.json('routinePlan_(CONFIG, "2026-11-18")');
  assert.equal(plan.length, 6);   // OPD รวม 1 + OR อังคาร 2 + พฤหัส 1 + ศุกร์ 2 (เวรพุธลงแยกเป็นรายสัปดาห์)
  const pick = (title, cal) => plan.filter(s => s.title === title && s.calendar === cal).map(s => [s.first, s.start, s.end, s.intervalWeeks]);
  assert.deepEqual(pick("OPD", "ทุกคน"), [["2026-11-23", "09:00", "16:00", 1]]);
  assert.deepEqual(pick("OR", "มานิตา"), [["2026-11-24", "08:00", "16:00", 1]]);
  assert.deepEqual(pick("OR", "ศุภศักดิ์"), [["2026-11-24", "08:00", "16:00", 1]]);
  assert.deepEqual(pick("OR", "ชนกันต์"), [["2026-11-19", "08:00", "16:00", 1]]);
  assert.deepEqual(pick("OR", "คงธัช"), [["2026-11-20", "08:00", "16:00", 1]]);
  assert.deepEqual(pick("OR", "อดิศร"), [["2026-11-20", "08:00", "16:00", 1]]);
});

test("เวรวันพุธ: ชนกันต์ → มานิตา → ศุภศักดิ์ → อดิศร → คงธัช · ตรงวันหยุด คนนั้นเลื่อนไปสัปดาห์ถัดไป", () => {
  const w = makeWorld();
  const plan = (hol, from) => w.json(`rotationPlan_(CONFIG.rotations[0], ${JSON.stringify(hol)}, "${from}", "2027-01-20")`).map(p => p.date.slice(5) + " " + p.name);
  assert.deepEqual(plan({}, "2026-11-18"), ["11-25 ชนกันต์", "12-02 มานิตา", "12-09 ศุภศักดิ์", "12-16 อดิศร", "12-23 คงธัช", "12-30 ชนกันต์", "01-06 มานิตา", "01-13 ศุภศักดิ์", "01-20 อดิศร"]);
  // 16 ธ.ค. เป็นวันหยุด: อดิศรเลื่อนไป 23 ธ.ค. และทุกคนถัดไปเลื่อนตาม
  assert.deepEqual(plan({ "2026-12-16": 1 }, "2026-11-18"), ["11-25 ชนกันต์", "12-02 มานิตา", "12-09 ศุภศักดิ์", "12-23 อดิศร", "12-30 คงธัช", "01-06 ชนกันต์", "01-13 มานิตา", "01-20 ศุภศักดิ์"]);
  // เริ่มดูกลางคัน ลำดับยังต่อเนื่องจากต้นทาง
  assert.deepEqual(plan({ "2026-12-16": 1 }, "2027-01-01"), ["01-06 ชนกันต์", "01-13 มานิตา", "01-20 ศุภศักดิ์"]);
});

test("ตรวจ CONFIG: จับชื่อผิด วันไม่ตรง เวลาผิด", () => {
  const w = makeWorld();
  w.run('CONFIG.routine[1].who = ["มานิตา", "ไม่มีคนนี้"]; CONFIG.rotations[0].firstDate = "2026-11-26"; CONFIG.routine[0].start = "9:00";');
  assert.throws(() => w.run("checkConfig_(CONFIG)"), e => /ไม่รู้จัก "ไม่มีคนนี้"/.test(e.message) && /ไม่ตรงกับ day WE/.test(e.message) && /เวลาต้องเป็น HH:mm/.test(e.message));
});

test("พฤหัสบดี: ER และ OPD ของสายฟ้าทุก 4 สัปดาห์ วนคนตามลำดับ · พฤหัสที่ตรงวันหยุด ทั้งคิวเลื่อนหนึ่งสัปดาห์", () => {
  const w = makeWorld().setup();
  const on = (title, ymd) => PEOPLE.filter(p => w.cal(p).getEvents(bkk(ymd), bkk(ymd, "23:59")).some(e => e.title === title && e.getTag("sayfa"))).join();
  assert.deepEqual(["2026-12-03", "2026-12-10", "2026-12-31", "2027-01-28", "2027-02-25"].map(d => on("ER", d)), ["คงธัช", "", "ชนกันต์", "มานิตา", "ศุภศักดิ์"]);
  assert.deepEqual(["2026-12-17", "2026-12-24", "2027-01-14", "2027-02-11", "2027-03-11", "2027-04-08"].map(d => on("OPD", d)), ["มานิตา", "", "ศุภศักดิ์", "อดิศร", "คงธัช", "ชนกันต์"]);
  assert.deepEqual(w.titlesOn("ชนกันต์", "2026-12-31").sort(), ["ER", "OR"]);     // ซ้อนกับ OR ประจำวันพฤหัสของชนกันต์
  // วันหยุดพฤหัส 10 ธ.ค. และ 31 ธ.ค.: ทั้งคิวเลื่อนไปสัปดาห์ถัดไป ไม่ใช่รออีก 4 สัปดาห์
  w.run("step3a_previewHolidays(); step3b_applyHolidays()");
  assert.deepEqual(["2026-12-03", "2026-12-31", "2027-01-07", "2027-01-14", "2027-01-28", "2027-02-11"].map(d => on("ER", d)), ["คงธัช", "", "", "ชนกันต์", "", "มานิตา"]);
  assert.deepEqual(["2026-12-17", "2027-01-14", "2027-01-21", "2027-02-18"].map(d => on("OPD", d)), ["มานิตา", "", "ศุภศักดิ์", "อดิศร"]);
  assert.match(w.run('formatDigest_(collectDay_("2026-12-03"), "today").text'), /🟢 คงธัช · 08:00–16:00 ER\n🟣 ชนกันต์ · 08:00–16:00 OR/);
});

test("ตั้งค่าครั้งแรก: ปฏิทิน 6 อัน งานประจำ และเวรพุธ · รันซ้ำไม่สร้างซ้ำ", () => {
  const w = makeWorld().setup();
  assert.deepEqual(w.calendars.map(c => c.name), [...PEOPLE.map(p => "สายฟ้า – " + p), "สายฟ้า – ทุกคน"]);
  assert.equal(w.cal("มานิตา").color, "#D50000");
  const series = () => w.calendars.reduce((n, c) => n + c.series.length, 0);
  const singles = () => w.calendars.reduce((n, c) => n + c.singles.length, 0);
  assert.equal(series(), 6);
  const n = singles();
  assert.equal(n, 45 * 2 + 11 + 11);                                          // พุธ 45 สัปดาห์ × 2 งาน + ER พฤหัส 11 รอบ + OPD พฤหัส 11 รอบ (ทุก 4 สัปดาห์)
  w.run("step1_createCalendars(); step2_createRoutine(); syncRotations_([], today_());");
  assert.equal(w.calendars.length, 6);
  assert.equal(series(), 6);
  assert.equal(singles(), n);

  assert.deepEqual(w.titlesOn("ทุกคน", "2026-11-23"), ["OPD"]);
  assert.deepEqual(w.titlesOn("มานิตา", "2026-11-24"), ["OR"]);
  assert.deepEqual(w.titlesOn("ชนกันต์", "2026-11-25"), ["ER", "OPD ปกส."]);   // ER 08–16 และ OPD ปกส. 13–15 ซ้อนกันในวันเดียว
  assert.deepEqual(w.titlesOn("ชนกันต์", "2026-11-26"), ["OR"]);
  assert.deepEqual(w.titlesOn("ชนกันต์", "2027-09-30"), ["OR"]);               // วันสุดท้ายยังมี
  assert.deepEqual(w.titlesOn("ชนกันต์", "2027-10-07"), []);                   // เลยกำหนดแล้วไม่มี
  assert.deepEqual(["2026-11-25", "2026-12-02", "2026-12-09", "2026-12-16", "2026-12-23", "2026-12-30"].map(d => w.erOn(d).join()),
    ["ชนกันต์", "มานิตา", "ศุภศักดิ์", "อดิศร", "คงธัช", "ชนกันต์"]);
});

test("ปฏิทินชื่อเดียวกันที่มีอยู่แล้วถูกนำมาใช้ ไม่สร้างซ้อน", () => {
  const w = makeWorld();
  w.run('CalendarApp.createCalendar("สายฟ้า – มานิตา", {})');
  w.run("step1_createCalendars()");
  assert.equal(w.calendars.filter(c => c.name === "สายฟ้า – มานิตา").length, 1);
  assert.equal(w.calendars.length, 6);
});

test("ขั้น 3: อ่านวันหยุดของ Google ถูก (ไม่นับวันสำคัญ · ต่อบรรทัดที่พับ · ตัดอักขระล่องหน)", () => {
  const w = makeWorld();
  const hol = w.json(`parseHolidayIcs_(${JSON.stringify(HOLIDAY_FIXTURE)})`);
  assert.deepEqual(hol.map(h => h.date), ["2026-12-05", "2026-12-07", "2026-12-10", "2026-12-16", "2026-12-31", "2027-01-01"]);
  assert.equal(hol[1].name, "วันหยุดชดเชยวันคล้ายวันพระบรมราชสมภพ ร.9");
  assert.equal(hol[2].name, "วันรัฐธรรมนูญ");
  w.run('CONFIG.extraHolidays = [{ date: "2027-01-04", name: "หยุดพิเศษ" }]; CONFIG.notHolidays = ["2026-12-31"];');
  const merged = w.json(`mergeHolidays_(parseHolidayIcs_(${JSON.stringify(HOLIDAY_FIXTURE)}), CONFIG, "2026-12-08", "2027-09-30")`);
  assert.deepEqual(merged.map(h => h.date), ["2026-12-10", "2026-12-16", "2027-01-01", "2027-01-04"]);
});

test("ปรับรายการของ Google ให้ใกล้วันหยุดราชการ: ตัดวันแรงงาน · เติมวันเข้าพรรษา · ไม่เดาวันชดเชยที่เลื่อน แต่เตือน", () => {
  const w = makeWorld();
  const google = [
    { date: "2027-05-01", name: "วันแรงงานแห่งชาติ" }, { date: "2027-05-03", name: "วันหยุดชดเชยวันแรงงานแห่งชาติ" }, { date: "2027-05-04", name: "วันฉัตรมงคล" },
    { date: "2027-07-18", name: "วันอาสาฬหบูชา" }, { date: "2027-07-19", name: "วันหยุดชดเชยวันอาสาฬหบูชา" },   // อาทิตย์ + จันทร์ (ตามแบบธนาคาร)
    { date: "2026-07-29", name: "วันอาสาฬหบูชา" }                                                                // พุธ → เข้าพรรษาพฤหัส ไม่ชนอะไร
  ];
  const r = w.json(`civilServiceAdjust_(${JSON.stringify(google)}, CONFIG)`);
  const byDate = Object.fromEntries(r.list.map(h => [h.date, h.name]));
  assert.deepEqual(byDate, { "2027-05-04": "วันฉัตรมงคล", "2027-07-18": "วันอาสาฬหบูชา", "2027-07-19": "วันเข้าพรรษา", "2026-07-29": "วันอาสาฬหบูชา", "2026-07-30": "วันเข้าพรรษา" });
  assert.equal(byDate["2027-07-20"], undefined);            // ไม่เดาวันชดเชยที่เลื่อนไปวันอังคาร
  assert.equal(r.notes.length, 1);
  assert.match(r.notes[0], /ปี 2570.*ตรวจประกาศ ครม\./);
  w.run('CONFIG.extraHolidays = [{ date: "2027-07-20", name: "ชดเชยวันอาสาฬหบูชา" }];');   // เจ้าของเติมเองหลังตรวจประกาศ
  assert.deepEqual(w.json(`mergeHolidays_(civilServiceAdjust_(${JSON.stringify(google)}, CONFIG).list, CONFIG, "2027-07-01", "2027-07-31")`).map(h => h.date), ["2027-07-18", "2027-07-19", "2027-07-20"]);
});

test("ขั้น 3: ตัดงานประจำเฉพาะครั้งที่ตรงวันหยุด · เวรพุธเลื่อนคน · งานที่คนลงเองไม่ถูกแตะ · รันซ้ำได้", () => {
  const w = makeWorld().setup();
  w.cal("ชนกันต์").add({ title: "OR เคสด่วน", start: bkk("2026-12-10", "08:00"), end: bkk("2026-12-10", "12:00") });
  w.cal("อดิศร").add({ title: "เวรนอกเวลา", start: bkk("2026-12-16", "16:00"), end: bkk("2026-12-17", "08:00") });
  w.run("step3a_previewHolidays(); step3b_applyHolidays()");
  assert.deepEqual(w.titlesOn("ทุกคน", "2026-12-07"), []);                     // จันทร์ ชดเชย → OPD งด
  assert.deepEqual(w.titlesOn("ทุกคน", "2026-12-14"), ["OPD"]);                // จันทร์ปกติยังอยู่
  assert.deepEqual(w.titlesOn("ชนกันต์", "2026-12-10"), ["OR เคสด่วน"]);        // OR ประจำงด แต่ที่ลงเองยังอยู่
  assert.deepEqual(w.titlesOn("อดิศร", "2026-12-16"), ["เวรนอกเวลา"]);          // พุธ วันหยุดพิเศษ: ER/OPD ปกส. งด เวรนอกเวลายังอยู่
  // อดิศรเลื่อนไปพุธถัดไป และทุกคนถัดไปเลื่อนตาม · ก่อนวันหยุดไม่ถูกแตะ
  assert.deepEqual(["2026-11-25", "2026-12-02", "2026-12-09", "2026-12-16", "2026-12-23", "2026-12-30", "2027-01-06", "2027-01-13"].map(d => w.erOn(d).join()),
    ["ชนกันต์", "มานิตา", "ศุภศักดิ์", "", "อดิศร", "คงธัช", "ชนกันต์", "มานิตา"]);
  assert.deepEqual(w.titlesOn("อดิศร", "2026-12-23"), ["ER", "OPD ปกส."]);
  assert.deepEqual(w.titlesOn("ชนกันต์", "2026-12-31"), []);
  assert.deepEqual(w.titlesOn("คงธัช", "2027-01-01"), []);
  assert.deepEqual(w.titlesOn("คงธัช", "2027-01-08"), ["OR"]);
  assert.deepEqual(w.titlesOn("คงธัช", "2026-12-25"), ["OR"]);                 // ศุกร์ 25 ธ.ค. คริสต์มาสเป็น "วันสำคัญ" ไม่ใช่วันหยุดราชการ
  assert.equal(w.calendars.reduce((n, c) => n + c.series.length, 0), 6);       // ไม่มีชุดไหนถูกลบทั้งชุด
  for (let d = "2026-11-25", i = 0; i < 44; i++, d = new Date(Date.parse(d) + 7 * 864e5).toISOString().slice(0, 10))
    assert.equal(w.erOn(d).length, d === "2026-12-16" ? 0 : 1, d);             // ทุกพุธมีคนเดียว ยกเว้นวันหยุด

  // แลกเวรเองในปฏิทิน: คงธัช (30 ธ.ค.) ให้มานิตาอยู่แทน — รันตรวจวันหยุดรอบถัดไปต้องไม่จัดทับ
  const kc = w.cal("คงธัช"); kc.singles = kc.singles.filter(e => !(e.title === "ER" && e.start.getTime() === bkk("2026-12-30", "08:00").getTime()));
  w.cal("มานิตา").add({ title: "ER", start: bkk("2026-12-30", "08:00"), end: bkk("2026-12-30", "16:00") });
  w.run("step3a_previewHolidays(); step3b_applyHolidays()");
  assert.deepEqual(w.erOn("2026-12-30"), ["มานิตา"]);
  assert.deepEqual(w.titlesOn("ทุกคน", "2026-12-14"), ["OPD"]);
  // ตั้งตรวจวันหยุดรายเดือนให้เอง ครั้งเดียว แม้ยังไม่ได้ตั้งค่า LINE
  assert.deepEqual(w.triggers.map(t => [t.fn, t.monthDay, t.hour]), [["holidayWatch", undefined, 5]]);
  assert.ok(new TextEncoder().encode(w.props.get("HOLIDAYS")).length < 9000);

  // ครม. ประกาศวันหยุดพิเศษเพิ่ม พุธ 13 ม.ค. 2570: จัดใหม่ตั้งแต่สัปดาห์นั้น ก่อนหน้าคงเดิม (รวมที่แลกเวรไว้)
  w.run('CONFIG.extraHolidays = [{ date: "2027-01-13", name: "วันหยุดพิเศษ" }]; step3a_previewHolidays(); step3b_applyHolidays();');
  assert.deepEqual(["2026-12-30", "2027-01-06", "2027-01-13", "2027-01-20", "2027-01-27"].map(d => w.erOn(d).join()), ["มานิตา", "ชนกันต์", "", "มานิตา", "ศุภศักดิ์"]);
});

test("ขั้น 3ก ดูอย่างเดียวไม่แก้อะไร · 3ข ทำได้เฉพาะรายการที่ดูแล้ว · วันที่ไม่หยุดแล้วได้งานคืน · ตรวจรายเดือนไม่ลบเอง", () => {
  const w = makeWorld().setup();
  const snap = () => JSON.stringify(w.calendars.map(c => [c.singles.length, c.series.map(s => [...s.deleted])]));
  const before = snap();
  assert.throws(() => w.run("step3b_applyHolidays()"), /รัน step3a_previewHolidays/);   // ยังไม่ได้ดู: ไม่ยอมลบ
  w.run("step3a_previewHolidays()");
  assert.equal(snap(), before);                                                          // ดูแล้ว ปฏิทินยังเหมือนเดิมทุกรายการ
  assert.deepEqual(w.titlesOn("ทุกคน", "2026-12-07"), ["OPD"]);
  w.run('CONFIG.extraHolidays = [{ date: "2026-12-21", name: "เพิ่มทีหลัง" }];');          // รายการเปลี่ยนหลังดู: ต้องดูใหม่
  assert.throws(() => w.run("step3b_applyHolidays()"), /ไม่ตรงกับที่ดูไว้/);
  assert.equal(snap(), before);
  w.run("CONFIG.extraHolidays = []; step3a_previewHolidays(); step3b_applyHolidays();");
  assert.deepEqual(w.titlesOn("ทุกคน", "2026-12-07"), []);
  assert.deepEqual(w.titlesOn("ชนกันต์", "2026-12-31"), []);

  // เจ้าของพบว่า 31 ธ.ค. ไม่หยุด: ใส่ notHolidays แล้วรันใหม่ งานของวันนั้นกลับมา วันหยุดอื่นยังงดอยู่
  w.run('CONFIG.notHolidays = ["2026-12-31"]; step3a_previewHolidays(); step3b_applyHolidays();');
  assert.deepEqual(w.titlesOn("ชนกันต์", "2026-12-31"), ["OR"]);
  assert.deepEqual(w.titlesOn("ทุกคน", "2026-12-07"), []);
  w.run("step3a_previewHolidays(); step3b_applyHolidays();");                             // รันซ้ำ: ไม่คืนซ้อน
  assert.deepEqual(w.titlesOn("ชนกันต์", "2026-12-31"), ["OR"]);

  // ตรวจรายเดือน: ไม่เปลี่ยน = เงียบ · เปลี่ยน = แจ้งเจ้าของ (throw → อีเมล) โดยไม่แตะปฏิทิน
  w.run("holidayWatch()");
  const s2 = snap();
  // กฎ: วันหยุดประกาศเพิ่ม (พุธ 13 ม.ค.) → งดงานประจำ เลื่อนคิวเวรพุธไปสัปดาห์ถัดไปเอง และแจ้งใน LINE รอบเช้าถัดไป
  const before13 = w.erOn("2027-01-13"), before20 = w.erOn("2027-01-20");
  w.run('CONFIG.extraHolidays = [{ date: "2027-01-13", name: "วันหยุดพิเศษ" }]; holidayWatch();');
  assert.deepEqual(w.erOn("2027-01-13"), []);
  assert.deepEqual(w.erOn("2027-01-20"), before13);                                       // คนของ 13 ม.ค. เลื่อนมา 20 ม.ค.
  assert.deepEqual(w.erOn("2027-01-27"), before20);
  assert.match(w.props.get("HOLIDAY_NOTICE"), /วันหยุดราชการประกาศเพิ่ม: พ\. 13 ม\.ค\. 2570 วันหยุดพิเศษ\nงดงานประจำ.*เลื่อนเวรพุธ\/พฤหัส/);
  w.linked(); w.now = new Date("2026-11-24T06:30:00+07:00");
  w.run("sendMorning()");
  assert.match(w.pushes().at(-1).body.messages[0].text, /^🎌 วันหยุดราชการประกาศเพิ่ม: พ\. 13 ม\.ค\./);
  assert.equal(w.props.get("HOLIDAY_NOTICE"), undefined);                                 // แจ้งครั้งเดียว
  w.run("holidayWatch()");                                                                // รอบถัดไป: ไม่มีอะไรใหม่
  // วันหยุดหายไปจากรายการ หรือเพิ่มทีเดียวมากผิดปกติ: ไม่แตะปฏิทิน แจ้งเจ้าของ
  const s3 = snap();
  w.run("CONFIG.extraHolidays = [];");
  assert.throws(() => w.run("holidayWatch()"), /หายไป: 2027-01-13.*step3a_previewHolidays/);
  w.run('CONFIG.extraHolidays = ["2027-01-13","2027-02-01","2027-02-02","2027-02-03","2027-02-04"].map(d => ({ date: d, name: "x" }));');
  assert.throws(() => w.run("holidayWatch()"), /เพิ่ม: 2027-02-01/);
  assert.equal(snap(), s3);
  w.run('CONFIG.extraHolidays = [{ date: "2027-01-13", name: "วันหยุดพิเศษ" }];');
  w.holidayIcs = "BEGIN:VCALENDAR\r\nEND:VCALENDAR";                                     // ไฟล์ของ Google เสีย: แจ้ง ไม่แตะปฏิทิน
  assert.throws(() => w.run("holidayWatch()"), /น้อยผิดปกติ/);
  assert.equal(snap(), s3);
});

test("เพิ่มวันหยุดโดยไม่แก้โค้ด: ลงรายการทั้งวัน 'วันหยุดราชการ: …' ในปฏิทินรวม แล้วกฎจัดการต่อเอง", () => {
  const w = makeWorld().setup();
  w.run("step3a_previewHolidays(); step3b_applyHolidays();");
  const before = w.erOn("2027-01-13");
  assert.equal(before.length, 1);
  w.cal("ทุกคน").add({ title: "วันหยุดราชการ: วันหยุดพิเศษตามมติ ครม.", allDay: true, start: bkk("2027-01-13"), end: bkk("2027-01-14") });
  w.cal("ทุกคน").add({ title: "ประชุมสาย", allDay: true, start: bkk("2027-01-20"), end: bkk("2027-01-21") });   // ชื่ออื่นไม่นับ
  w.run("holidayWatch()");
  assert.deepEqual(w.erOn("2027-01-13"), []);
  assert.deepEqual(w.erOn("2027-01-20"), before);
  assert.match(w.props.get("HOLIDAY_NOTICE"), /พ\. 13 ม\.ค\. 2570 วันหยุดพิเศษตามมติ ครม\./);
  const day = w.run('formatDigest_(collectDay_("2027-01-13"), "today").text');
  assert.match(day, /🎌 วันหยุดราชการ: วันหยุดพิเศษตามมติ ครม\./);
  assert.doesNotMatch(day, /ทั้งวัน วันหยุดราชการ/);                              // ไม่ขึ้นซ้ำเป็นงานของทุกคน
});

test("Gemini เช็กข่าววันหยุด: เสนอในกลุ่ม LINE ก่อน · คนยืนยันจึงลง · คำตอบผิดรูปแบบหรือมากผิดปกติไม่ทำอะไร", () => {
  const w = makeWorld("2026-11-23T05:00:00+07:00").setup();
  w.run("step3a_previewHolidays(); step3b_applyHolidays();");
  const answer = arr => ({ steps: [{ type: "thought" }, { type: "model_output", content: [{ type: "text", text: "```json\n" + JSON.stringify(arr) + "\n```" }] }] });
  assert.throws(() => w.run("geminiHolidayCheck()"), /GEMINI_API_KEY/);
  assert.throws(() => w.run("step7_startGeminiCheck()"), /GEMINI_API_KEY/);
  w.props.set("GEMINI_API_KEY", "gk");
  w.run("step7_startGeminiCheck(); step7_startGeminiCheck();");
  assert.deepEqual(w.triggers.filter(t => t.fn === "geminiHolidayCheck").map(t => [t.weekDay, t.hour]), [["MONDAY", 5]]);

  // 10 ธ.ค. รู้อยู่แล้ว (ไม่เสนอซ้ำ) · 13 ม.ค. ใหม่ · วันที่ผ่านไปแล้วและรูปแบบผิดถูกทิ้ง
  w.gemini = answer([{ date: "2026-12-10", name: "วันรัฐธรรมนูญ", source: "https://a" }, { date: "2027-01-13", name: "วันหยุดพิเศษ", source: "https://thaigov.go.th/x" }, { date: "2026-01-01", name: "เก่า" }, { date: "13/01/2570", name: "ผิดรูปแบบ" }]);
  w.run("geminiHolidayCheck()");
  assert.equal(w.geminiReq.key, "gk");
  assert.deepEqual(w.geminiReq.body.tools, [{ type: "google_search" }]);
  assert.equal(w.geminiReq.body.model, "gemini-4-hydrogen");
  assert.match(w.props.get("HOLIDAY_NOTICE"), /Gemini พบข่าววันหยุดราชการประกาศเพิ่ม \(ยังไม่ได้ปรับตาราง\):\n• พ\. 13 ม\.ค\. 2570 วันหยุดพิเศษ\n  https:\/\/thaigov\.go\.th\/x\nถ้าถูกต้อง พิมพ์: ยืนยันวันหยุด 13 ม\.ค\./);
  assert.equal(w.erOn("2027-01-13").length, 1);                                  // ยังไม่ปรับตาราง
  assert.deepEqual(w.titlesOn("ทุกคน", "2027-01-13"), []);
  w.props.delete("HOLIDAY_NOTICE"); w.run("geminiHolidayCheck()");               // สัปดาห์ถัดไปตอบเหมือนเดิม: ไม่ถามซ้ำ
  assert.equal(w.props.get("HOLIDAY_NOTICE"), undefined);

  w.props.set("LINE_TOKEN", "tok"); w.run("step5_prepareLine()");
  const key = w.props.get("WEBHOOK_KEY"); let n = 0;
  const say = text => { w.run(`doPost(${JSON.stringify({ parameter: { k: key }, postData: { contents: JSON.stringify({ events: [{ type: "message", mode: "active", webhookEventId: "G" + (++n), replyToken: "r" + n, source: { type: "group", groupId: G1, userId: "Ua" }, message: { type: "text", text } }] }) } })})`); return w.replies().at(-1).body.messages[0].text; };
  say("เชื่อมปฏิทิน " + w.props.get("LINE_LINK_CODE"));
  assert.match(say("ยืนยันวันหยุด 20 ม.ค."), /ไม่มีวันนี้ในรายการที่รอยืนยัน — ที่รออยู่: 13 ม\.ค\./);
  assert.match(say("ยืนยันวันหยุด 13 ม.ค."), /บันทึก พ\. 13 ม\.ค\. 2570 วันหยุดพิเศษ เป็นวันหยุดราชการแล้ว/);
  assert.deepEqual(w.titlesOn("ทุกคน", "2027-01-13"), ["วันหยุดราชการ: วันหยุดพิเศษ"]);
  const before = w.erOn("2027-01-13");
  w.run("holidayWatch()");                                                       // เช้าวันถัดไป: กฎวันหยุดประกาศเพิ่มทำงาน
  assert.deepEqual(w.erOn("2027-01-13"), []);
  assert.deepEqual(w.erOn("2027-01-20"), before);

  // ไม่ใช่วันหยุด: ทิ้ง ไม่ลงอะไร
  w.gemini = answer([{ date: "2027-02-03", name: "ข่าวลือ", source: "" }]);
  w.run("geminiHolidayCheck()");
  assert.match(say("ไม่ใช่วันหยุด 3 ก.พ."), /ไม่นับ พ\. 3 ก\.พ\. 2570 เป็นวันหยุด/);
  assert.deepEqual(w.titlesOn("ทุกคน", "2027-02-03"), []);

  // คำตอบเพี้ยน: ไม่ทำอะไร แจ้งเจ้าของ
  w.gemini = { steps: [{ type: "model_output", content: [{ type: "text", text: "ขออภัย ไม่พบข้อมูล" }] }] };
  assert.throws(() => w.run("geminiHolidayCheck()"), /ไม่ได้ตอบเป็นรายการ/);
  w.gemini = answer(["2027-03-01", "2027-03-02", "2027-03-03", "2027-03-04"].map(d => ({ date: d, name: "x" })));
  assert.throws(() => w.run("geminiHolidayCheck()"), /มากผิดปกติ/);
  w.geminiStatus = 429;
  assert.throws(() => w.run("geminiHolidayCheck()"), /Gemini ตอบ HTTP 429/);
  assert.deepEqual(w.titlesOn("ทุกคน", "2027-03-01"), ["OPD"]);                   // จันทร์ปกติ: OPD ยังอยู่ ไม่มีรายการวันหยุดถูกลง
});

test("ถาม Gemini ในกลุ่ม: ปิดไว้เป็นค่าเริ่มต้น · เปิดแล้วส่งตารางให้ ไม่ให้ค้นเว็บ ไม่แก้ปฏิทิน · ล้มแล้วตอบสุภาพ", () => {
  const w = makeWorld("2026-11-24T09:00:00+07:00").setup();
  w.props.set("LINE_TOKEN", "tok"); w.run("step5_prepareLine()");
  const key = w.props.get("WEBHOOK_KEY"); let n = 0;
  const say = text => { w.run(`doPost(${JSON.stringify({ parameter: { k: key }, postData: { contents: JSON.stringify({ events: [{ type: "message", mode: "active", webhookEventId: "Q" + (++n), replyToken: "r" + n, source: { type: "group", groupId: G1, userId: "Ua" }, message: { type: "text", text } }] }) } })})`); return w.replies().at(-1).body.messages[0].text; };
  say("เชื่อมปฏิทิน " + w.props.get("LINE_LINK_CODE"));
  const nRep = w.replies().length;
  say("ถาม พุธนี้ใครอยู่ ER");
  assert.equal(w.replies().length, nRep);                                        // ปิดอยู่: เป็นข้อความคุยธรรมดา ไม่ตอบ ไม่เรียก Gemini
  assert.equal(w.geminiReq, undefined);

  w.run("CONFIG.gemini.chat = true;");
  assert.match(say("ถาม พุธนี้ใครอยู่ ER"), /ยังไม่ได้ตั้งค่า Gemini/);
  w.props.set("GEMINI_API_KEY", "gk");
  w.gemini = { steps: [{ type: "model_output", content: [{ type: "text", text: "พุธ 25 พ.ย. ชนกันต์อยู่ ER 08:00–16:00" }] }] };
  const snap = JSON.stringify(w.calendars.map(c => [c.singles.length, c.series.length]));
  assert.equal(say("ถาม พุธนี้ใครอยู่ ER"), "🤖 พุธ 25 พ.ย. ชนกันต์อยู่ ER 08:00–16:00\n(คำตอบจาก Gemini อาจผิดได้ — ยืนยันกับปฏิทิน)");
  assert.equal(w.geminiReq.body.tools, undefined);                               // ไม่ให้ค้นเว็บ
  assert.match(w.geminiReq.body.input, /▪️ พ\. 25 พ\.ย\.\n🟣 ชนกันต์\n   • 08:00–16:00 ER/);
  assert.match(w.geminiReq.body.input, /คำถาม: พุธนี้ใครอยู่ ER$/);
  assert.equal(JSON.stringify(w.calendars.map(c => [c.singles.length, c.series.length])), snap);
  w.geminiStatus = 500;
  assert.match(say("ถาม อะไรก็ได้"), /Gemini ไม่ตอบ \(HTTP 500\)/);
});

test("คำสั่ง LINE ลา: ลงวันลา + งด OR ของตัวเองรอบเดียว · เวรวนไม่ลบแต่แจ้งหาคนแทน · ยกเลิกลาคืนงาน", () => {
  const w = makeWorld("2026-11-24T09:00:00+07:00").setup();
  const p = (s, word = "ลา") => w.json(`parseLeave_(${JSON.stringify(s)}, "${word}", "2026-11-24", CONFIG.people.map(x => x.name))`);
  assert.deepEqual(p("ลา 14-18 ธ.ค. คงธัช พักร้อน"), { d1: "2026-12-14", d2: "2026-12-18", name: "คงธัช", reason: "พักร้อน" });
  assert.deepEqual(p("ลา 14 ธ.ค. คงธัช"), { d1: "2026-12-14", d2: "2026-12-14", name: "คงธัช", reason: "" });
  assert.deepEqual(p("ลา 30 ธ.ค. - 2 ม.ค. อดิศร ไปต่างประเทศ"), { d1: "2026-12-30", d2: "2027-01-02", name: "อดิศร", reason: "ไปต่างประเทศ" });
  assert.deepEqual(p("ลา 14/12 ถึง 18/12 คงธัช"), { d1: "2026-12-14", d2: "2026-12-18", name: "คงธัช", reason: "" });
  assert.equal(p("ลา ก่อนนะครับ"), null);                                        // คุยธรรมดา ไม่ใช่คำสั่ง
  assert.match(p("ลา 14-18 ธ.ค. หมอใหม่").error, /ไม่รู้จักชื่อ/);
  assert.match(p("ลา 18-14 ธ.ค. คงธัช").error, /วันสิ้นสุดมาก่อนวันเริ่ม/);

  w.props.set("LINE_TOKEN", "tok"); w.run("step5_prepareLine()");
  const key = w.props.get("WEBHOOK_KEY"); let n = 0;
  const say = text => { w.run(`doPost(${JSON.stringify({ parameter: { k: key }, postData: { contents: JSON.stringify({ events: [{ type: "message", mode: "active", webhookEventId: "L" + (++n), replyToken: "r" + n, source: { type: "group", groupId: G1, userId: "Ua" }, message: { type: "text", text } }] }) } })})`); return w.replies().at(-1).body.messages[0].text; };
  say("เชื่อมปฏิทิน " + w.props.get("LINE_LINK_CODE"));
  const nRep = w.replies().length; say("ลา ก่อนนะครับ"); assert.equal(w.replies().length, nRep);

  // คงธัช ลา 21–25 ธ.ค.: OR ศุกร์ 25 ถูกงด · เวร ER/OPD ปกส. พุธ 23 ยังอยู่และถูกแจ้ง · งานสอนที่ลงเองยังอยู่
  w.cal("คงธัช").add({ title: "สอน นศพ.", start: bkk("2026-12-22", "13:00"), end: bkk("2026-12-22", "15:00") });
  const out = say("ลา 21-25 ธ.ค. คงธัช พักร้อน");
  assert.match(out, /^🏖 ลงว่าไม่อยู่แล้ว: คงธัช · ลาพักร้อน · 21 ธ\.ค\. – 25 ธ\.ค\. 2569\nงดงานของตัวเอง 1 รายการ:\n  ✂️ ศ\. 25 ธ\.ค\. 08:00–16:00 OR\n⚠️ เวรที่ต้องหาคนแทน \(ยังอยู่ในตาราง\):\n  • พ\. 23 ธ\.ค\. 08:00–16:00 ER\n  • พ\. 23 ธ\.ค\. 13:00–15:00 OPD ปกส\.\nใช้คำสั่ง: แลกเวร <วันที่> คงธัช <ชื่อคนแทน>\nรายการที่ลงเอง ยังค้างอยู่ \(จัดการเองในปฏิทิน\):\n  • อ\. 22 ธ\.ค\. 13:00–15:00 สอน นศพ\./);
  assert.deepEqual(w.titlesOn("คงธัช", "2026-12-25"), ["ลาพักร้อน"]);
  assert.deepEqual(w.titlesOn("คงธัช", "2026-12-23"), ["ER", "OPD ปกส.", "ลาพักร้อน"]);
  assert.deepEqual(w.titlesOn("คงธัช", "2027-01-08"), ["OR"]);                   // สัปดาห์นอกช่วงลาไม่กระทบ
  assert.deepEqual(w.titlesOn("อดิศร", "2026-12-25"), ["OR"]);                   // OR ของคนอื่นวันเดียวกันไม่ถูกแตะ
  assert.match(w.run('formatDigest_(collectDay_("2026-12-23"), "today").text'), /🏖 ไม่อยู่\n🟢 คงธัช — ลาพักร้อน \(ถึง ศ\. 25 ธ\.ค\.\).*\n   ⚠️ ยังมีงานในตาราง: 08:00–16:00 ER · 13:00–15:00 OPD ปกส\./);
  assert.match(say("ลา 21-25 ธ.ค. คงธัช"), /ลงวันลาช่วงนี้ของคงธัชไว้แล้ว/);
  assert.equal(w.pushes().length, 0);

  // ยกเลิกลา: วันลาหาย OR กลับมา
  assert.match(say("ยกเลิกลา 21-25 ธ.ค. คงธัช"), /ยกเลิกวันลาของคงธัชแล้ว · คืนงานของตัวเอง 1 รายการ/);
  assert.deepEqual(w.titlesOn("คงธัช", "2026-12-25"), ["OR"]);
  assert.deepEqual(w.titlesOn("คงธัช", "2026-12-23"), ["ER", "OPD ปกส."]);
  assert.match(say("ยกเลิกลา 21-25 ธ.ค. คงธัช"), /ไม่พบวันลาช่วงนี้/);
  assert.match(say("ลา 2 ธ.ค. มานิตา"), /มานิตา · ลา · พ\. 2 ธ\.ค\. 2569/);        // ไม่ใส่เหตุผล
});

test("ขั้น 3: skipHolidays:false ไม่ถูกตัด · ไฟล์วันหยุดผิดปกติไม่แก้อะไร", () => {
  const w = makeWorld();
  w.run("CONFIG.routine[2].skipHolidays = false;");                            // OR พฤหัสของชนกันต์
  w.setup();
  w.run("step3a_previewHolidays(); step3b_applyHolidays()");
  assert.deepEqual(w.titlesOn("ชนกันต์", "2026-12-10"), ["OR"]);

  const w2 = makeWorld().setup();
  w2.holidayIcs = "BEGIN:VCALENDAR\r\nEND:VCALENDAR";
  assert.throws(() => w2.run("step3a_previewHolidays(); step3b_applyHolidays()"), /น้อยผิดปกติ/);
  assert.deepEqual(w2.titlesOn("ทุกคน", "2026-12-07"), ["OPD"]);
  assert.deepEqual(w2.erOn("2026-12-16"), ["อดิศร"]);
});

test("ข้อความ LINE: งานรายคน · เวรสองงานขึ้นเป็นหัวข้อย่อย · งานรวม · วันว่าง", () => {
  const w = makeWorld().setup();
  assert.equal(w.run('formatDigest_(collectDay_("2026-11-24"), "today").text'),
    "📅 วันนี้ อังคาร 24 พ.ย. 2569\n🔴 มานิตา · 08:00–16:00 OR\n🔵 ศุภศักดิ์ · 08:00–16:00 OR");
  assert.equal(w.run('formatDigest_(collectDay_("2026-11-25"), "tomorrow").text'),
    "🗓 พรุ่งนี้ พุธ 25 พ.ย. 2569\n🟣 ชนกันต์\n   • 08:00–16:00 ER\n   • 13:00–15:00 OPD ปกส.");
  assert.equal(w.run('formatDigest_(collectDay_("2026-11-23"), "today").text'), "📅 วันนี้ จันทร์ 23 พ.ย. 2569\n👥 ทุกคน · 09:00–16:00 OPD");
  assert.equal(w.run('formatDigest_(collectDay_("2026-11-28"), "today").isEmpty'), true);
});

test("ข้อความ LINE: ลาหลายวัน · เตือนเมื่อยังมีงานค้าง · ประชุมแบบมีเวลาไม่นับว่าไม่อยู่ · เวรข้ามคืนไม่นับซ้ำ", () => {
  const w = makeWorld().setup();
  w.cal("คงธัช").add({ title: "ลาพักร้อน", allDay: true, start: bkk("2026-11-25"), end: bkk("2026-11-28") });   // 25–27 พ.ย. (วันจบเป็นวันถัดไป)
  w.cal("อดิศร").add({ title: "ประชุมกรรมการ", start: bkk("2026-11-26", "13:30"), end: bkk("2026-11-26", "15:00"), location: "ห้องประชุม 2" });
  w.cal("มานิตา").add({ title: "Staff on call", start: bkk("2026-11-26", "16:00"), end: bkk("2026-11-27", "08:00") });
  w.cal("ศุภศักดิ์").add({ title: "ไปประชุมวิชาการ", allDay: true, start: bkk("2026-11-26"), end: bkk("2026-11-27") });

  assert.equal(w.run('formatDigest_(collectDay_("2026-11-26"), "today").text'), [
    "📅 วันนี้ พฤหัสบดี 26 พ.ย. 2569",
    "🔴 มานิตา · 16:00–08:00 (+1) Staff on call 🆕",
    "🟠 อดิศร · 13:30–15:00 ประชุมกรรมการ @ห้องประชุม 2 🆕",
    "🟣 ชนกันต์ · 08:00–16:00 OR",
    "🏖 ไม่อยู่",
    "🔵 ศุภศักดิ์ — ไปประชุมวิชาการ 🆕",
    "🟢 คงธัช — ลาพักร้อน (ถึง ศ. 27 พ.ย.) 🆕"].join("\n"));

  const fri = w.run('formatDigest_(collectDay_("2026-11-27"), "today").text');
  assert.match(fri, /🟢 คงธัช — ลาพักร้อน 🆕\n   ⚠️ ยังมีงานในตาราง: 08:00–16:00 OR/);
  assert.doesNotMatch(fri, /Staff on call/);                                    // เวรที่เริ่มเมื่อวานไม่ขึ้นซ้ำ
  assert.doesNotMatch(w.run('formatDigest_(collectDay_("2026-11-28"), "today").text'), /คงธัช/);   // วันถัดจากวันสุดท้ายไม่นับ
});

test("🆕 ขึ้นเฉพาะรายการที่มีคนเพิ่ม/แก้ใน 24 ชม. ไม่ใช่งานประจำที่สร้างพร้อมกันทั้งชุด", () => {
  const w = makeWorld().setup();
  assert.doesNotMatch(w.run('formatDigest_(collectDay_("2026-11-24"), "today").text'), /🆕/);
  w.now = new Date("2026-11-23T18:30:00+07:00");
  w.cal("ศุภศักดิ์").series[0].updated = new Date("2026-11-23T12:00:00+07:00");   // มีคนแก้งานประจำเมื่อเที่ยง
  w.cal("มานิตา").add({ title: "สอน นศพ.", start: bkk("2026-11-24", "13:00"), end: bkk("2026-11-24", "15:00"), updated: new Date("2026-11-20T09:00:00+07:00"), created: new Date("2026-11-20T09:00:00+07:00") });
  const t = w.run('formatDigest_(collectDay_("2026-11-24"), "tomorrow").text');
  assert.match(t, /🔵 ศุภศักดิ์ · 08:00–16:00 OR 🆕/);
  assert.match(t, /🔴 มานิตา\n   • 08:00–16:00 OR\n   • 13:00–15:00 สอน นศพ\./);
  assert.doesNotMatch(t, /สอน นศพ\. 🆕/);
});

test("ส่ง LINE: เช้า=วันนี้ เย็น=พรุ่งนี้ · วันว่างไม่ส่ง · ยังไม่ตั้งค่าแจ้งชัด", () => {
  const w = makeWorld("2026-11-24T06:30:00+07:00").setup();
  assert.throws(() => w.run("sendMorning()"), /เชื่อมกลุ่ม/);
  w.props.set("LINE_GROUP_ID", G1);
  assert.throws(() => w.run("sendMorning()"), /LINE_TOKEN/);
  w.props.set("LINE_TOKEN", "tok");
  w.run("sendMorning()");
  let c = w.pushes();
  assert.equal(c.length, 1);
  assert.equal(c[0].url, "https://api.line.me/v2/bot/message/push");
  assert.equal(c[0].auth, "Bearer tok");
  assert.match(c[0].retryKey, /^[0-9a-f-]{36}$/);
  assert.equal(c[0].body.to, G1);
  assert.equal(c[0].body.messages[0].text, "📅 วันนี้ อังคาร 24 พ.ย. 2569\n🔴 มานิตา · 08:00–16:00 OR\n🔵 ศุภศักดิ์ · 08:00–16:00 OR");
  assert.equal(w.quota.used, 5);                    // กลุ่ม 5 คน = 5 ข้อความ
  w.run("sendEvening()");
  assert.match(w.pushes()[1].body.messages[0].text, /^🗓 พรุ่งนี้ พุธ 25 พ\.ย\. 2569/);

  w.now = new Date("2026-11-28T06:30:00+07:00");   // เสาร์ ไม่มีงาน
  w.run("sendMorning()");
  assert.equal(w.pushes().length, 2);
  w.now = new Date("2026-11-27T18:30:00+07:00");   // ศุกร์เย็น: พรุ่งนี้ (เสาร์) ว่าง
  w.run("sendEvening()");
  assert.equal(w.pushes().length, 2);
});

test("ส่ง LINE: ลองใหม่เมื่อ LINE ล่มชั่วคราวด้วยกุญแจเดิม · 409 = ส่งถึงแล้ว · 4xx ไม่ลองใหม่", () => {
  const w = makeWorld("2026-11-24T06:30:00+07:00").setup().linked();
  w.pushScript = [500, 200];
  w.run("sendMorning()");
  assert.equal(w.pushes().length, 2);
  assert.equal(w.pushes()[0].retryKey, w.pushes()[1].retryKey);   // กุญแจเดิม → LINE ไม่นับโควตาซ้ำ

  w.pushScript = ["throw", 409];
  w.run("sendEvening()");                                          // 409 = ครั้งแรกถึงแล้ว ถือว่าสำเร็จ
  assert.equal(w.pushes().length, 4);

  w.pushScript = [400];
  assert.throws(() => w.run("sendMorning()"), /HTTP 400.*บอทไม่ได้อยู่ในกลุ่ม/s);
  assert.equal(w.pushes().length, 5);
  w.pushScript = [500, 500];
  assert.throws(() => w.run("sendMorning()"), /HTTP 500/);
  w.pushScript = [429];
  w.run("sendMorning()");                                          // โควตาหมด: ไม่ throw
});

test("คุมโควตา: เย็นถูกงดก่อนเมื่อเหลือน้อย เช้ายังส่ง · หมดจริงไม่ยิง · บัญชีไม่จำกัดส่งปกติ", () => {
  const w = makeWorld("2026-11-24T18:30:00+07:00").setup().linked();   // อังคาร 24 พ.ย.: เหลือวันทำการอีก 4 วัน (25, 26, 27, 30)
  assert.equal(w.run('weekdaysLeftInMonth_("2026-11-24")'), 4);
  w.quota.used = 300 - 34;                                             // เหลือ 34: หลังส่งเหลือ 29 < กันไว้ 5×(4+2)=30
  w.run("sendEvening()");
  assert.equal(w.pushes().length, 0);
  w.quota.used = 300 - 35;                                             // เหลือ 35: พอดี ส่งได้
  w.run("sendEvening()");
  assert.equal(w.pushes().length, 1);

  w.now = new Date("2026-11-25T06:30:00+07:00");
  w.quota.used = 300 - 5;                                              // เหลือ 5: เช้ายังส่งได้
  w.run("sendMorning()");
  assert.equal(w.pushes().length, 2);
  w.now = new Date("2026-11-26T06:30:00+07:00");
  w.run("sendMorning()");                                              // เหลือ 0: ไม่ยิง push เลย
  assert.equal(w.pushes().length, 2);

  w.members = 12; w.quota.used = 0;                                    // กลุ่มใหญ่: ครั้งละ 12
  w.run("sendMorning()");
  assert.equal(w.quota.used, 12);
  w.quota = { type: "none", value: 0, used: 0 };
  w.run("sendMorning()");
  assert.equal(w.pushes().length, 4);
});

test("จำลองทั้งเดือน 31 วัน (ธ.ค. 2569) ส่งเช้า+เย็น กลุ่ม 5 คน: ไม่เกิน 300 และรอบเช้าไม่เคยถูกงด", () => {
  const w = makeWorld("2026-11-30T12:00:00+07:00").setup().linked();
  w.run("step3a_previewHolidays(); step3b_applyHolidays()");
  let mornings = 0, evenings = 0, morningsWanted = 0;
  for (let d = 1; d <= 31; d++) {
    const ymd = "2026-12-" + String(d).padStart(2, "0");
    w.now = bkk(ymd, "06:30");
    const wanted = !w.run(`formatDigest_(collectDay_("${ymd}"), "today").isEmpty`);
    let n = w.pushes().length; w.run("sendMorning()");
    if (wanted) morningsWanted++;
    if (w.pushes().length > n) mornings++;
    w.now = bkk(ymd, "18:30");
    n = w.pushes().length; w.run("sendEvening()");
    if (w.pushes().length > n) evenings++;
  }
  assert.equal(mornings, morningsWanted);
  assert.ok(mornings >= 18 && evenings >= 15, `เช้า ${mornings} เย็น ${evenings}`);
  assert.ok(w.quota.used <= 300, "ใช้ไป " + w.quota.used);
  // กลุ่ม 7 คน: เกินโควตาถ้าส่งครบ — ต้องงดเย็นบางวัน แต่เช้าครบ
  const w7 = makeWorld("2026-11-30T12:00:00+07:00").setup().linked();
  w7.members = 7; w7.run("step3a_previewHolidays(); step3b_applyHolidays()");
  let m7 = 0, want7 = 0;
  for (let d = 1; d <= 31; d++) {
    const ymd = "2026-12-" + String(d).padStart(2, "0");
    w7.now = bkk(ymd, "06:30");
    if (!w7.run(`formatDigest_(collectDay_("${ymd}"), "today").isEmpty`)) want7++;
    const n = w7.pushes().length; w7.run("sendMorning()"); if (w7.pushes().length > n) m7++;
    w7.now = bkk(ymd, "18:30"); w7.run("sendEvening()");
  }
  assert.equal(m7, want7);
  assert.ok(w7.quota.used <= 300, "ใช้ไป " + w7.quota.used);
});

test("รอบเช้าแจ้งรายการที่เพิ่ง​เพิ่ม/แก้ (เช่น วันลาเดือนหน้า) ครั้งเดียว ไม่แจ้งซ้ำ", () => {
  const w = makeWorld("2026-11-23T06:30:00+07:00").setup().linked();
  w.run("sendMorning()");                                               // จันทร์: ยังไม่มีอะไรใหม่
  assert.doesNotMatch(w.pushes()[0].body.messages[0].text, /เพิ่ม\/แก้ไขล่าสุด/);

  w.now = new Date("2026-11-23T14:00:00+07:00");                        // บ่ายวันจันทร์ มีคนลงวันลาและนัดสอน
  w.cal("คงธัช").add({ title: "ลาพักร้อน", allDay: true, start: bkk("2026-12-14"), end: bkk("2026-12-19") });
  w.cal("อดิศร").add({ title: "สอน นศพ.", start: bkk("2026-12-03", "13:00"), end: bkk("2026-12-03", "15:00") });
  w.cal("ศุภศักดิ์").series[0].updated = w.now;                           // แก้ OR ประจำทั้งชุด
  w.now = new Date("2026-11-24T06:30:00+07:00");
  w.run("sendMorning()");
  const t = w.pushes()[1].body.messages[0].text;
  assert.match(t, /\n\n🆕 เพิ่ม\/แก้ไขล่าสุด\n🔵 ศุภศักดิ์ · อ\. 1 ธ\.ค\. 08:00–16:00 OR \(รายการซ้ำ\)\n🟠 อดิศร · พฤ\. 3 ธ\.ค\. 13:00–15:00 สอน นศพ\.\n🟢 คงธัช · 14 ธ\.ค\.–18 ธ\.ค\. ลาพักร้อน$/);
  assert.equal(t.match(/ศุภศักดิ์ · อ\./g).length, 1);                   // รายการซ้ำขึ้นครั้งเดียว ไม่ใช่ทุกสัปดาห์

  w.now = new Date("2026-11-25T06:30:00+07:00");
  w.run("sendMorning()");
  assert.doesNotMatch(w.pushes()[2].body.messages[0].text, /เพิ่ม\/แก้ไขล่าสุด/);   // แจ้งไปแล้ว ไม่ซ้ำ
});

test("จุดสีตามสีปฏิทิน: ครบชุดสีของ Google Calendar · เปลี่ยนสีปฏิทินแล้วข้อความเปลี่ยนตาม", () => {
  const w = makeWorld().setup();
  const dots = Object.fromEntries(Object.entries({
    Tomato: "#D50000", Flamingo: "#E67C73", Tangerine: "#F4511E", Pumpkin: "#EF6C00", Mango: "#F09300", Banana: "#F6BF26", Citron: "#E4C441",
    Avocado: "#C0CA33", Pistachio: "#7CB342", Basil: "#0B8043", Sage: "#33B679", Eucalyptus: "#009688", Peacock: "#039BE5", Cobalt: "#4285F4",
    Blueberry: "#3F51B5", Lavender: "#7986CB", Wisteria: "#B39DDB", Amethyst: "#9E69AF", Grape: "#8E24AA", Radicchio: "#AD1457",
    CherryBlossom: "#D81B60", Cocoa: "#795548", Graphite: "#616161", Birch: "#A79B8E", bad: "blue"
  }).map(([k, v]) => [k, w.run(`dotForHex_("${v}")`)]));
  assert.deepEqual(dots, {
    Tomato: "🔴", Flamingo: "🔴", Tangerine: "🟠", Pumpkin: "🟠", Mango: "🟠", Banana: "🟡", Citron: "🟡", Avocado: "🟡", Pistachio: "🟢",
    Basil: "🟢", Sage: "🟢", Eucalyptus: "🟢", Peacock: "🔵", Cobalt: "🔵", Blueberry: "🔵", Lavender: "🔵", Wisteria: "🟣", Amethyst: "🟣",
    Grape: "🟣", Radicchio: "🔴", CherryBlossom: "🔴", Cocoa: "🟤", Graphite: "⚫", Birch: "⚫", bad: "⚪" });
  w.cal("มานิตา").setColor("#F6BF26");              // เจ้าของเปลี่ยนสีปฏิทินของมานิตาเป็นเหลืองในหน้า Google Calendar
  assert.match(w.run('formatDigest_(collectDay_("2026-11-24"), "today").text'), /🟡 มานิตา · 08:00–16:00 OR/);
  w.run('CONFIG.people[0].dot = "🩷";');             // กำหนดเองใน CONFIG ชนะ
  assert.match(w.run('formatDigest_(collectDay_("2026-11-24"), "today").text'), /🩷 มานิตา/);
});

test("เวลาเที่ยงคืน–7 โมงเช้าไทยยังนับเป็นวันไทย ไม่ใช่วัน UTC", () => {
  const w = makeWorld("2026-11-23T17:30:00Z").setup();   // = 00:30 น. วันอังคาร 24 พ.ย. เวลาไทย
  assert.equal(w.run("today_()"), "2026-11-24");
  assert.match(w.run('digestText_(0, "today").text'), /อังคาร 24 พ\.ย\./);
});

test("webhook: กุญแจผิดถูกทิ้ง · จำกลุ่มเมื่อ LINE ยืนยันว่าบอทอยู่จริง · กลุ่มอื่นไม่ตอบ · ตอบเฉพาะคำสั่ง", () => {
  const w = makeWorld("2026-11-24T09:00:00+07:00").setup();
  w.props.set("LINE_TOKEN", "tok");
  w.run("step5_prepareLine()");
  const key = w.props.get("WEBHOOK_KEY");
  assert.match(key, /^[0-9a-f]{32}$/);
  let seq = 0;
  const post = (k, events) => w.run(`doPost(${JSON.stringify({ parameter: { k }, postData: { contents: JSON.stringify({ events }) } })})`);
  const msg = (groupId, text, type = "group") => ({ type: "message", mode: "active", webhookEventId: "E" + (++seq), replyToken: "rt" + seq, source: { type, groupId, userId: "U1" }, message: { type: "text", text } });

  post("wrong", [msg(G1, "วันนี้")]);
  post(key, [msg(undefined, "วันนี้", "user")]);                  // แชต 1:1 ไม่ใช้
  post(key, [msg("Cg1", "วันนี้")]);                              // group ID รูปแบบผิด
  post(key, [msg(G2, "เชื่อมปฏิทิน " + w.props.get("LINE_LINK_CODE"))]);   // คำขอปลอมที่รู้รหัส: LINE บอกว่าบอทไม่ได้อยู่ในกลุ่มนี้
  post(key, [{ ...msg(G1, "สวัสดี"), mode: "standby" }]);
  assert.equal(w.props.get("LINE_GROUP_ID"), undefined);
  assert.equal(w.replies().length, 0);

  const code = w.props.get("LINE_LINK_CODE");
  assert.match(code, /^\d{6}$/);
  post(key, [{ type: "join", mode: "active", webhookEventId: "J1", replyToken: "rtj", source: { type: "group", groupId: G1 } }]);
  post(key, [msg(G1, "สวัสดี")]);                                 // ถูกเชิญเข้ากลุ่มและมีคนคุย: ยังไม่เชื่อม
  post(key, [msg(G1, "เชื่อมปฏิทิน 000000")]);                     // รหัสผิด
  w.botGroups.add(G2);
  post(key, [msg(G2, "วันนี้")]);                                 // กลุ่มอื่นที่บอทอยู่ก่อน ถามตาราง: ไม่ได้อะไร
  assert.equal(w.props.get("LINE_GROUP_ID"), undefined);
  assert.equal(w.replies().length, 0);
  post(key, [msg(G1, " เชื่อมปฏิทิน  " + code + " ")]);
  assert.equal(w.props.get("LINE_GROUP_ID"), G1);
  assert.equal(w.props.get("LINE_LINK_CODE"), undefined);         // รหัสใช้ได้ครั้งเดียว
  assert.equal(w.replies().length, 1);
  assert.match(w.replies()[0].body.messages[0].text, /เชื่อมกลุ่มนี้/);
  assert.equal(w.replies()[0].retryKey, undefined);               // reply ห้ามมี X-Line-Retry-Key

  post(key, [msg(G2, "วันนี้")]);                                 // กลุ่มอื่น: ไม่เปลี่ยนกลุ่ม ไม่ตอบ
  post(key, [msg(G1, "เดี๋ยวเจอกันที่ OR นะ")]);                   // คุยกันปกติ
  post(key, [{ type: "message", mode: "active", replyToken: "x", source: { type: "group", groupId: G1 }, message: { type: "image" } }]);
  assert.equal(w.props.get("LINE_GROUP_ID"), G1);
  assert.equal(w.replies().length, 1);

  const today = msg(G1, " วันนี้ ");
  post(key, [today, msg(G1, "พรุ่งนี้")]);                         // หลายเหตุการณ์ในคำขอเดียว
  assert.equal(w.replies().length, 3);
  assert.equal(w.replies()[1].body.replyToken, today.replyToken);
  assert.match(w.replies()[1].body.messages[0].text, /^📅 วันนี้ อังคาร 24 พ\.ย\. 2569\n🔴 มานิตา/);
  assert.match(w.replies()[2].body.messages[0].text, /^🗓 พรุ่งนี้ พุธ 25 พ\.ย\./);
  post(key, [today]);                                             // LINE ส่งเหตุการณ์เดิมซ้ำ: ไม่ตอบซ้ำ
  assert.equal(w.replies().length, 3);
  post(key, [msg(G1, "สัปดาห์นี้")]);
  assert.match(w.replies()[3].body.messages[0].text, /^🗓 7 วันข้างหน้า\n\n▪️ อ\. 24 พ\.ย\.\n🔴 มานิตา · 08:00–16:00 OR/);
  assert.equal(w.pushes().length, 0);                             // webhook ไม่เคยใช้ push (ไม่กินโควตา)

  assert.equal(w.run("doPost(undefined)"), undefined);            // ไม่คืน ContentService (จะกลายเป็น HTTP 302)
  assert.equal(w.run(`doPost({ parameter: { k: "${key}" }, postData: { contents: "not json" } })`), undefined);
  assert.equal(w.run(`doPost({ parameter: { k: "${key}" }, postData: { contents: '{"events":[]}' } })`), undefined);   // ปุ่ม Verify ของ LINE
  assert.doesNotMatch(SOURCE.replace(/\/\*[\s\S]*?\*\/|\/\/.*$/gm, ""), /ContentService/);
});

test("webhook: ปิด replyCommands แล้วยังจำกลุ่มได้ แต่ไม่ตอบคำสั่ง", () => {
  const w = makeWorld("2026-11-24T09:00:00+07:00").setup();
  w.props.set("LINE_TOKEN", "tok"); w.run("step5_prepareLine(); CONFIG.line.replyCommands = false;");
  const key = w.props.get("WEBHOOK_KEY");
  const post = ev => w.run(`doPost(${JSON.stringify({ parameter: { k: key }, postData: { contents: JSON.stringify({ events: [ev] }) } })})`);
  post({ type: "message", replyToken: "a", source: { type: "group", groupId: G1 }, message: { type: "text", text: "เชื่อมปฏิทิน " + w.props.get("LINE_LINK_CODE") } });
  assert.equal(w.props.get("LINE_GROUP_ID"), G1);
  post({ type: "message", replyToken: "b", source: { type: "group", groupId: G1 }, message: { type: "text", text: "วันนี้" } });
  assert.equal(w.replies().length, 1);                            // มีแค่ข้อความยืนยันการเชื่อมกลุ่ม
});

test("แก้ตามผลตรวจโค้ด: รายการหลายวันแบบมีเวลา · ปฏิทินหายต้องล้มให้เห็น · เวลาเวรเปลี่ยน · ถอดเวรชุดเก่า · ต่ออายุไม่ทับการแลกเวร", () => {
  const w = makeWorld("2026-11-23T06:30:00+07:00").setup();
  // ไปประชุม 3 วันแบบมีเวลา: ต้องขึ้นทุกวันที่คร่อม ไม่ใช่วันแรกวันเดียว · เวรข้ามคืนธรรมดายังไม่ขึ้นซ้ำเช้าวันถัดไป
  w.cal("อดิศร").add({ title: "ประชุมวิชาการ", start: bkk("2026-11-24", "09:00"), end: bkk("2026-11-26", "16:00"), updated: bkk("2026-11-01"), created: bkk("2026-11-01") });
  w.cal("คงธัช").add({ title: "เวรนอกเวลา", start: bkk("2026-11-24", "16:00"), end: bkk("2026-11-25", "08:00"), updated: bkk("2026-11-01"), created: bkk("2026-11-01") });
  const day = d => w.run(`formatDigest_(collectDay_("${d}"), "today").text`);
  assert.match(day("2026-11-24"), /🟠 อดิศร · 09:00–16:00 \(\+2\) ประชุมวิชาการ/);
  assert.match(day("2026-11-25"), /🟠 อดิศร · ต่อเนื่องทั้งวัน ประชุมวิชาการ/);
  assert.match(day("2026-11-26"), /🟠 อดิศร · ต่อเนื่องถึง 16:00 ประชุมวิชาการ/);
  assert.doesNotMatch(day("2026-11-25"), /เวรนอกเวลา/);
  assert.doesNotMatch(day("2026-11-27"), /ประชุมวิชาการ/);

  // ชื่อที่ขึ้นต้นด้วย "ลา" แต่ไม่ใช่การลา ไม่นับว่าไม่อยู่ · ลาสองรายการแสดงครบ
  w.cal("มานิตา").add({ title: "ลาดพร้าว ออกหน่วย", allDay: true, start: bkk("2026-11-27"), end: bkk("2026-11-28") });
  w.cal("ศุภศักดิ์").add({ title: "ลากิจ", allDay: true, start: bkk("2026-11-27"), end: bkk("2026-11-28") });
  w.cal("ศุภศักดิ์").add({ title: "ไปประชุม กทม.", allDay: true, start: bkk("2026-11-27"), end: bkk("2026-11-28") });
  assert.match(day("2026-11-27"), /🔴 มานิตา · ทั้งวัน ลาดพร้าว ออกหน่วย/);
  assert.match(day("2026-11-27"), /🔵 ศุภศักดิ์ — (ลากิจ 🆕 · ไปประชุม กทม\. 🆕|ไปประชุม กทม\. 🆕 · ลากิจ 🆕)/);

  // ปฏิทินของท่านหนึ่งหาย: ต้องล้มพร้อมข้อความ ไม่ใช่แสดงว่าว่าง · step1 สร้างใหม่แล้วขั้นถัดไปลงงานคืน
  const lost = w.cal("คงธัช");
  w.calendars = w.calendars.filter(c => c !== lost);
  assert.throws(() => day("2026-11-27"), /เข้าปฏิทิน "สายฟ้า – คงธัช" ไม่ได้/);
  w.run("step1_createCalendars(); step2_createRoutine(); step3a_previewHolidays(); step3b_applyHolidays();");
  assert.deepEqual(w.titlesOn("คงธัช", "2026-11-27"), ["OR"]);
  assert.deepEqual(w.erOn("2026-12-30"), ["คงธัช"]);
  assert.equal(w.cal("มานิตา").color, "#D50000");

  // เจ้าของเปลี่ยนสีเอง แล้วรัน step1 ซ้ำ: สีไม่ถูกตั้งกลับ
  w.cal("มานิตา").setColor("#F6BF26");
  w.run("step1_createCalendars()");
  assert.equal(w.cal("มานิตา").color, "#F6BF26");

  // แลกเวร 6 ม.ค. (ชนกันต์ → มานิตา) แล้วต่ออายุ routineUntil: เวรที่ลงไว้และที่แลกไว้ต้องคงเดิม มีแต่ของใหม่ต่อท้าย
  const cc = w.cal("ชนกันต์"); const moved = cc.singles.filter(e => e.start.getTime() >= bkk("2027-01-06").getTime() && e.start.getTime() < bkk("2027-01-07").getTime());
  cc.singles = cc.singles.filter(e => !moved.includes(e));
  w.cal("มานิตา").add({ title: "ER", start: bkk("2027-01-06", "08:00"), end: bkk("2027-01-06", "16:00") });
  w.run('CONFIG.routineUntil = "2027-10-31"; step3a_previewHolidays(); step3b_applyHolidays();');
  assert.deepEqual(w.erOn("2027-01-06"), ["มานิตา"]);
  assert.equal(w.erOn("2027-10-06").length, 1);

  // เปลี่ยนเวลา OPD ปกส.: รายการเดิมถูกแทนด้วยเวลาใหม่ (เปลี่ยนการตั้งค่าเวร = จัดใหม่ตั้งแต่วันนี้)
  w.run('CONFIG.rotations[0].tasks[1].end = "16:00"; step3a_previewHolidays(); step3b_applyHolidays();');
  const pks = w.cal("มานิตา").getEvents(bkk("2026-12-02"), bkk("2026-12-03")).filter(e => e.title === "OPD ปกส.");
  assert.equal(pks.length, 1);
  assert.equal(pks[0].end.getTime(), bkk("2026-12-02", "16:00").getTime());

  // ถอดเวรพฤหัส OPD ออกจาก CONFIG: เวรที่เหลือของชุดนั้นถูกลบ ไม่ค้างเป็นเวรผี
  w.run("CONFIG.rotations.pop(); step3a_previewHolidays(); step3b_applyHolidays();");
  assert.deepEqual(w.titlesOn("มานิตา", "2026-12-17"), []);
  assert.deepEqual(w.titlesOn("คงธัช", "2026-12-03"), ["ER"]);
});

test("แก้ตามผลตรวจโค้ด: ขั้น 3ก เตือนรายการซ้ำที่สคริปต์ไม่ได้งด · 429 ที่ไม่ใช่โควตาเดือนต้องล้ม · บอทถูกนำออกจากกลุ่ม", () => {
  const w = makeWorld("2026-11-24T06:30:00+07:00").setup().linked();
  // งานประจำที่ถูกแก้แบบ "รายการนี้และรายการต่อจากนี้" = ชุดใหม่ที่สคริปต์ไม่รู้จัก
  w.run('CalendarApp.getCalendarById(' + JSON.stringify(w.cal("ทุกคน").id) + ').createEventSeries("OPD (เวลาใหม่)", new Date("2026-11-30T09:00:00+07:00"), new Date("2026-11-30T15:00:00+07:00"), CalendarApp.newRecurrence().addWeeklyRule().until(new Date("2027-09-30T23:59:00+07:00")))');
  const warns = [];
  w.run("0"); w.onWarn = m => warns.push(m);
  w.run("step3a_previewHolidays()");
  assert.ok(warns.some(m => /ไม่ได้งดให้/.test(m)));
  assert.ok(warns.some(m => /จ\. 7 ธ\.ค\. สายฟ้า – ทุกคน: OPD \(เวลาใหม่\)/.test(m)));

  w.pushScript = [429];
  const realFetch = w.rateLimited = true;
  assert.throws(() => w.run("sendMorning()"), /เรียกถี่เกิน/);

  const key = (w.run("step5_prepareLine()"), w.props.get("WEBHOOK_KEY"));
  w.run(`doPost(${JSON.stringify({ parameter: { k: key }, postData: { contents: JSON.stringify({ events: [{ type: "leave", source: { type: "group", groupId: G1 } }] }) } })})`);
  assert.equal(w.props.get("LINE_GROUP_ID"), undefined);
});

test("คำสั่ง LINE แลกเวร: อ่านวันที่ไทย · อยู่แทนวันเดียว · แลกสองวัน · งานที่ลงเองไม่ถูกแตะ · ข้อความผิดได้คำแนะนำ · อีกฝ่ายต้องตอบรับก่อน", () => {
  const w = makeWorld("2026-11-24T09:00:00+07:00").setup();
  const d = s => w.run(`parseThaiDate_(${JSON.stringify(s)}, "2026-11-24")`);
  assert.deepEqual(["2 ธ.ค.", "2ธค", "2 ธ.ค. 69", "2 ธ.ค. 2569", "2/12", "02/12/2569", "2026-12-02", "5 ม.ค.", "5 มี.ค.", "24 พ.ย.", "23 พ.ย.", "31 ก.พ.", "2 xx"].map(d),
    ["2026-12-02", "2026-12-02", "2026-12-02", "2026-12-02", "2026-12-02", "2026-12-02", "2026-12-02", "2027-01-05", "2027-03-05", "2026-11-24", "2027-11-23", null, null]);

  w.props.set("LINE_TOKEN", "tok"); w.run("step5_prepareLine()");
  const key = w.props.get("WEBHOOK_KEY"); let n = 0;
  const say = (text, uid = "Ua") => { w.run(`doPost(${JSON.stringify({ parameter: { k: key }, postData: { contents: JSON.stringify({ events: [{ type: "message", mode: "active", webhookEventId: "S" + (++n), replyToken: "r" + n, source: { type: "group", groupId: G1, userId: uid }, message: { type: "text", text } }] }) } })})`); return w.replies().at(-1).body.messages[0].text; };
  const swap = text => { say(text, "Ua"); return say("ตกลง", "Ub"); };
  say("เชื่อมปฏิทิน " + w.props.get("LINE_LINK_CODE"));
  w.cal("มานิตา").add({ title: "สอน นศพ.", start: bkk("2026-12-02", "13:00"), end: bkk("2026-12-02", "15:00") });

  // อยู่แทนวันเดียว: พุธ 2 ธ.ค. เวรของมานิตา (ER + OPD ปกส.) ไปอยู่กับชนกันต์ · งานสอนที่ลงเองอยู่ที่เดิม
  const ask = say("แลกเวร 2 ธ.ค. มานิตา ชนกันต์", "Ua");
  assert.match(ask, /^⏳ ขอแลกเวร — ยังไม่ได้ย้าย\nพ\. 2 ธ\.ค\. · มานิตา → ชนกันต์: 08:00–16:00 ER, 13:00–15:00 OPD ปกส\.\n\nรอ มานิตา หรือ ชนกันต์ พิมพ์ "ตกลง"/);
  assert.deepEqual(w.titlesOn("ชนกันต์", "2026-12-02"), []);                      // ขอแล้ว ยังไม่ย้าย
  assert.match(say("ตกลง", "Ua"), /ผู้ขอแลกตอบรับเองไม่ได้/);
  assert.match(say("แลกเวร 9 ธ.ค. ศุภศักดิ์ คงธัช", "Uc"), /มีคำขอแลกเวรค้างอยู่/);
  assert.deepEqual(w.titlesOn("ชนกันต์", "2026-12-02"), []);
  const r1 = say("ตกลง", "Ub");
  assert.match(r1, /^✅ แลกเวรแล้ว\nพ\. 2 ธ\.ค\. · มานิตา → ชนกันต์: 08:00–16:00 ER, 13:00–15:00 OPD ปกส\./);
  assert.deepEqual(w.titlesOn("มานิตา", "2026-12-02"), ["สอน นศพ."]);
  assert.deepEqual(w.titlesOn("ชนกันต์", "2026-12-02"), ["ER", "OPD ปกส."]);
  assert.equal(w.pushes().length, 0);                                           // ตอบด้วย reply ไม่กินโควตา
  // ยกเลิก: พิมพ์คำสั่งเดิมสลับชื่อ
  swap("แลกเวร 2 ธ.ค. ชนกันต์ มานิตา");
  assert.deepEqual(w.titlesOn("มานิตา", "2026-12-02"), ["ER", "OPD ปกส.", "สอน นศพ."]);
  assert.deepEqual(w.titlesOn("ชนกันต์", "2026-12-02"), []);

  // แลกสองวัน: OR อังคาร 1 ธ.ค. ของศุภศักดิ์ (รายการซ้ำ) ↔ OR ศุกร์ 4 ธ.ค. ของอดิศร — สัปดาห์อื่นไม่กระทบ
  // ไม่ตกลง: ยกเลิก ปฏิทินไม่เปลี่ยน · "ตกลง" ตอนไม่มีคำขอค้างเป็นคำคุยธรรมดา บอทไม่ตอบ
  say("แลกเวร 1/12 ศุภศักดิ์ 4/12 อดิศร", "Ua");
  assert.match(say("ไม่ตกลง", "Ub"), /ยกเลิกคำขอแลกเวรแล้ว/);
  assert.deepEqual(w.titlesOn("ศุภศักดิ์", "2026-12-01"), ["OR"]);
  const nRep = w.replies().length; say("ตกลง", "Ub"); assert.equal(w.replies().length, nRep);
  // รู้ว่าใครเป็นใครแล้ว: ต้องเป็นอีกฝ่ายเท่านั้นที่ตอบรับ
  assert.match(say("ฉันคือ ศุภศักดิ์", "Us"), /จำแล้ว: บัญชีนี้คือ ศุภศักดิ์/);
  assert.match(say("ฉันคือ อดิศร", "Uo"), /อดิศร/);
  assert.match(say("ฉันคือ คงธัช", "Uk"), /คงธัช/);
  assert.match(say("แลกเวร 1/12 ศุภศักดิ์ 4/12 อดิศร", "Us"), /รอ อดิศร พิมพ์ "ตกลง"/);
  assert.match(say("ตกลง", "Uk"), /ต้องให้ อดิศร เป็นผู้ตอบรับ/);
  assert.deepEqual(w.titlesOn("ศุภศักดิ์", "2026-12-01"), ["OR"]);
  const r2 = say("ตกลง", "Uo");
  assert.match(r2, /แลกเวรแล้ว \(อดิศร ตอบรับ\)\nอ\. 1 ธ\.ค\. · ศุภศักดิ์ → อดิศร: 08:00–16:00 OR\nศ\. 4 ธ\.ค\. · อดิศร → ศุภศักดิ์: 08:00–16:00 OR/);
  assert.deepEqual([w.titlesOn("ศุภศักดิ์", "2026-12-01"), w.titlesOn("อดิศร", "2026-12-01"), w.titlesOn("อดิศร", "2026-12-04"), w.titlesOn("ศุภศักดิ์", "2026-12-04")], [[], ["OR"], [], ["OR"]]);
  assert.deepEqual([w.titlesOn("ศุภศักดิ์", "2026-12-08"), w.titlesOn("อดิศร", "2026-12-11")], [["OR"], ["OR"]]);
  assert.match(w.run('formatDigest_(collectDay_("2026-12-01"), "today").text'), /🟠 อดิศร · 08:00–16:00 OR/);

  // ข้อความผิด: ได้คำแนะนำ ไม่แก้อะไร
  assert.match(say("แลกเวร"), /พิมพ์แบบนี้/);
  assert.match(say("แลกเวร 2 ธ.ค. มานิตา หมอใหม่"), /ไม่รู้จักชื่อ "หมอใหม่"/);
  assert.match(say("แลกเวร 2 ธ.ค. มานิตา มานิตา"), /ต้องไม่ซ้ำกัน/);
  assert.match(say("แลกเวร 5 ธ.ค. มานิตา ชนกันต์"), /ไม่พบเวรที่ระบบลงให้/);                    // เสาร์ ไม่มีเวร
  assert.match(say("แลกเวร 9 ธ.ค. ศุภศักดิ์ 12 ธ.ค. อดิศร"), /อดิศร ส\. 12 ธ\.ค\. ไม่มีเวรที่ระบบลงให้/);
  assert.deepEqual(w.titlesOn("ศุภศักดิ์", "2026-12-09"), ["ER", "OPD ปกส."]);

  // วันหยุดประกาศใหม่ทำให้คิวพุธต้องจัดใหม่: เวรที่แลกผ่าน LINE หลังจุดนั้นถูกจัดตามคิวใหม่ ไม่ค้างซ้อน
  swap("แลกเวร 23 ธ.ค. คงธัช อดิศร");
  assert.deepEqual(w.erOn("2026-12-23"), ["อดิศร"]);
  w.run("step3a_previewHolidays(); step3b_applyHolidays();");                    // 16 ธ.ค. เป็นวันหยุด → คิวเลื่อน
  for (const day of ["2026-12-23", "2026-12-30", "2027-01-06"]) assert.equal(w.erOn(day).length, 1, day);
  assert.deepEqual(w.erOn("2026-12-23"), ["อดิศร"]);                             // ตามคิวใหม่ (อดิศรเลื่อนมาจาก 16 ธ.ค.)
});

test("แลกเวรระบุงาน: เฉพาะ ER · ER + OPD ปกส · งานสอนที่ลงเอง · ชื่องานไม่เจอไม่ทำอะไร — ลา ระบุประชุม", () => {
  const w = makeWorld("2026-11-24T09:00:00+07:00").setup();
  w.props.set("LINE_TOKEN", "tok"); w.run("step5_prepareLine()");
  const key = w.props.get("WEBHOOK_KEY"); let n = 0;
  const say = (text, uid = "Ua") => { w.run(`doPost(${JSON.stringify({ parameter: { k: key }, postData: { contents: JSON.stringify({ events: [{ type: "message", mode: "active", webhookEventId: "F" + (++n), replyToken: "r" + n, source: { type: "group", groupId: G1, userId: uid }, message: { type: "text", text } }] }) } })})`); return w.replies().at(-1).body.messages[0].text; };
  const swap = text => { const ask = say(text, "Ua"); return [ask, say("ตกลง", "Ub")]; };
  say("เชื่อมปฏิทิน " + w.props.get("LINE_LINK_CODE"));
  w.cal("มานิตา").add({ title: "สอน นศพ.", start: bkk("2026-12-02", "16:00"), end: bkk("2026-12-02", "17:00") });

  // เฉพาะ ER: OPD ปกส. ยังอยู่กับมานิตา
  const [ask1] = swap("แลกเวร 2 ธ.ค. มานิตา ชนกันต์ ER");
  assert.match(ask1, /พ\. 2 ธ\.ค\. · มานิตา → ชนกันต์: 08:00–16:00 ER\n\nรอ/);
  assert.deepEqual(w.titlesOn("ชนกันต์", "2026-12-02"), ["ER"]);
  assert.deepEqual(w.titlesOn("มานิตา", "2026-12-02"), ["OPD ปกส.", "สอน นศพ."]);
  // งานที่ลงเอง + เวร พร้อมกัน (พิมพ์ "ปกส" ไม่มีจุดก็เจอ)
  swap("แลกเวร 2 ธ.ค. มานิตา ศุภศักดิ์ OPD ปกส + สอน");
  assert.deepEqual(w.titlesOn("ศุภศักดิ์", "2026-12-02"), ["OPD ปกส.", "สอน นศพ."]);
  assert.deepEqual(w.titlesOn("มานิตา", "2026-12-02"), []);
  // ชื่องานไม่เจอ: ไม่ตั้งคำขอ ไม่ย้ายอะไร
  assert.match(say("แลกเวร 9 ธ.ค. ศุภศักดิ์ คงธัช ER + วิจัย"), /ไม่พบงานชื่อ "วิจัย"/);
  assert.deepEqual(w.titlesOn("ศุภศักดิ์", "2026-12-09"), ["ER", "OPD ปกส."]);
  // สองวัน ระบุงาน: ER พุธ 9 ธ.ค. ของศุภศักดิ์ ↔ ER พุธ 23 ธ.ค. ของคงธัช (OPD ปกส. อยู่ที่เดิม)
  swap("แลกเวร 9 ธ.ค. ศุภศักดิ์ 23 ธ.ค. คงธัช ER");
  assert.deepEqual([w.titlesOn("ศุภศักดิ์", "2026-12-09"), w.titlesOn("คงธัช", "2026-12-09"), w.titlesOn("คงธัช", "2026-12-23"), w.titlesOn("ศุภศักดิ์", "2026-12-23")],
    [["OPD ปกส."], ["ER"], ["OPD ปกส."], ["ER"]]);

  // ลา ระบุว่าไปประชุม: ชื่อรายการเป็นตามที่พิมพ์ ไม่มีคำว่า "ลา" นำหน้า และนับว่าไม่อยู่
  const out = say("ลา 3-4 ธ.ค. อดิศร ประชุมวิชาการ RCOST");
  assert.match(out, /^🏖 ลงว่าไม่อยู่แล้ว: อดิศร · ประชุมวิชาการ RCOST · 3 ธ\.ค\. – 4 ธ\.ค\. 2569\nงดงานของตัวเอง 1 รายการ:\n  ✂️ ศ\. 4 ธ\.ค\. 08:00–16:00 OR/);
  assert.deepEqual(w.titlesOn("อดิศร", "2026-12-04"), ["ประชุมวิชาการ RCOST"]);
  assert.match(w.run('formatDigest_(collectDay_("2026-12-04"), "today").text'), /🏖 ไม่อยู่\n🟠 อดิศร — ประชุมวิชาการ RCOST/);
  // งานสอนที่ย้ายมาแล้ว (ที่มา = ลงเอง) ไม่ถูกคำสั่งลาลบ
  say("ลา 2 ธ.ค. ศุภศักดิ์");
  assert.deepEqual(w.titlesOn("ศุภศักดิ์", "2026-12-02"), ["OPD ปกส.", "ลา", "สอน นศพ."]);
});

test("ตั้งชื่อด้วยการแท็ก: คนเดียวตั้งให้ทุกท่านได้ · ไม่แท็ก/ไม่มีรหัส ได้คำแนะนำ", () => {
  const w = makeWorld("2026-11-24T09:00:00+07:00").setup();
  w.props.set("LINE_TOKEN", "tok"); w.run("step5_prepareLine()");
  const key = w.props.get("WEBHOOK_KEY"); let n = 0;
  const say = (text, mentionees) => { w.run(`doPost(${JSON.stringify({ parameter: { k: key }, postData: { contents: JSON.stringify({ events: [{ type: "message", mode: "active", webhookEventId: "N" + (++n), replyToken: "r" + n, source: { type: "group", groupId: G1, userId: "Uowner" }, message: { type: "text", text, ...(mentionees ? { mention: { mentionees } } : {}) } }] }) } })})`); return w.replies().at(-1).body.messages[0].text; };
  say("เชื่อมปฏิทิน " + w.props.get("LINE_LINK_CODE"));
  assert.match(say("ตั้งชื่อ @Manita มานิตา", [{ index: 9, length: 7, type: "user", userId: "Um" }]), /จำแล้ว: บัญชีที่แท็กคือ มานิตา\nยังไม่ได้ตั้ง: ศุภศักดิ์, คงธัช, อดิศร, ชนกันต์/);
  assert.match(say("ตั้งชื่อ @Chon ชนกันต์", [{ index: 9, length: 5, type: "user", userId: "Uc" }]), /ชนกันต์/);
  assert.deepEqual(JSON.parse(w.props.get("LINE_USERS")), { Um: "มานิตา", Uc: "ชนกันต์" });
  assert.match(say("ตั้งชื่อ มานิตา"), /ต้องแท็ก \(@\) หนึ่งบัญชี/);
  assert.match(say("ตั้งชื่อ @X หมอใหม่", [{ type: "user", userId: "Ux" }]), /คำสุดท้ายต้องเป็นชื่อตามปฏิทิน/);
  assert.match(say("ตั้งชื่อ @Y อดิศร", [{ type: "user" }]), /LINE ไม่ส่งรหัสของบัญชีที่แท็กมา.*ฉันคือ อดิศร/);
  // ผลต่อการแลกเวร: มานิตา (Um) ขอ → ต้องเป็นชนกันต์ (Uc) ตอบรับ
  const as = (uid, text) => { w.run(`doPost(${JSON.stringify({ parameter: { k: key }, postData: { contents: JSON.stringify({ events: [{ type: "message", mode: "active", webhookEventId: "N" + (++n), replyToken: "r" + n, source: { type: "group", groupId: G1, userId: uid }, message: { type: "text", text } }] }) } })})`); return w.replies().at(-1).body.messages[0].text; };
  assert.match(as("Um", "แลกเวร 2 ธ.ค. มานิตา ชนกันต์"), /รอ ชนกันต์ พิมพ์ "ตกลง"/);
  assert.match(as("Uowner", "ตกลง"), /แลกเวรแล้ว/);                             // บัญชีที่ยังไม่ได้ตั้งชื่อ: ระบบยังรับ (ตรวจได้แค่ว่าไม่ใช่ผู้ขอ)
});

test("ขั้น 4: แชร์ทุกปฏิทินให้ทุกคน · ผู้ช่วยได้สิทธิ์จัดการ · ข้ามอีเมลของเจ้าของ", () => {
  const w = makeWorld().setup();
  assert.throws(() => w.run("step4_shareCalendars()"), /ยังไม่ได้ใส่ email/);
  w.run('CONFIG.people[0].email = "Owner@Example.com"; CONFIG.people[1].email = "b@example.com"; CONFIG.people[2].email = " c@example.com "; CONFIG.deputy = "คงธัช";');
  w.run("step4_shareCalendars()");
  assert.equal(w.acl.length, 12);   // 6 ปฏิทิน × 2 คน (ไม่รวมเจ้าของ)
  assert.ok(w.acl.every(a => a.scope.type === "user" && a.opt.sendNotifications === true));
  assert.deepEqual([...new Set(w.acl.filter(a => a.scope.value === "b@example.com").map(a => a.role))], ["writer"]);
  assert.deepEqual([...new Set(w.acl.filter(a => a.scope.value === "c@example.com").map(a => a.role))], ["owner"]);
  assert.equal(w.acl.filter(a => a.scope.value.includes("owner@")).length, 0);
});

test("ขั้น 6: ตั้งเวลา 3 ตัว · รันซ้ำไม่ซ้อน · หยุดได้", () => {
  const w = makeWorld();
  assert.throws(() => w.run("step6_startDailyLine()"), /LINE_TOKEN/);
  w.props.set("LINE_TOKEN", "tok");
  assert.throws(() => w.run("step6_startDailyLine()"), /เชื่อมกลุ่ม/);
  assert.equal(w.triggers.length, 0);              // LINE ยังไม่พร้อม: ไม่สร้างตัวตั้งเวลา (กันอีเมลแจ้งล้มเหลวทุกวัน)
  w.linked();
  w.run("step6_startDailyLine(); step6_startDailyLine();");
  assert.deepEqual(w.triggers.map(t => [t.fn, t.hour, t.minute ?? null, t.tz]).sort(), [
    ["holidayWatch", 5, null, TZ], ["sendEvening", 18, 30, TZ], ["sendMorning", 6, 30, TZ]]);
  assert.equal(w.triggers.find(t => t.fn === "holidayWatch").hour, 5);
  w.run("stopDailyLine()");
  assert.deepEqual(w.triggers.map(t => t.fn), ["holidayWatch"]);
  w.run("CONFIG.line.evening = null; step6_startDailyLine();");   // ปิดรอบเย็น
  assert.deepEqual(w.triggers.map(t => t.fn).sort(), ["holidayWatch", "sendMorning"]);
});
