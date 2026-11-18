/* ชุดทดสอบปฏิทินทีม — ไม่ต้องติดตั้งอะไร ไม่ยิง network: node --test team-calendar/test.mjs */
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { validate, occurrences, ruleDates, onDay, absentOn, conflicts, bangkokToday, bangkokHour, thaiDate } from "./lib.mjs";
import { buildFeed, feedList, fold, escapeText } from "./ics.mjs";
import { formatMessage, lineMessage } from "./notify.mjs";
import { loadSchedule } from "./build.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const enc = new TextEncoder();
const base = () => ({
  team: { id: "t", name: "Team T", short: "T" },
  members: [
    { id: "a", name: "อ.เอ", role: "Staff", color: "blue" },
    { id: "b", name: "หมอบี", role: "R2", color: "green" }
  ],
  task_types: { or: { label: "OR", remind_min: 30 }, leave: { label: "ลา" }, call: { label: "เวร" } },
  holidays: [], recurring: [], events: []
});

test("ไฟล์ schedule.json จริงผ่านการตรวจ และ feeds/ ไม่ค้าง", async () => {
  const s = await loadSchedule();
  assert.deepEqual(validate(s).errors, []);
  execFileSync(process.execPath, [join(here, "build.mjs"), "--check"], { stdio: "pipe" });
});

test("ตรวจข้อผิดพลาดที่คนแก้มือมักทำ แล้วบอกเป็นภาษาไทย", () => {
  const s = base();
  s.members.push({ id: "c", name: "ซี", color: "navy" });
  s.events.push({ type: "or", who: ["zz"], date: "2026-02-30", start: "8:30", end: "16:30" });
  s.recurring.push({ type: "or", who: ["a"], weekly: ["MON"], start: "08:00", end: "09:00", from: "2026-11-02" });
  const { errors } = validate(s);
  const all = errors.join("\n");
  assert.match(all, /สี "navy"/);
  assert.match(all, /ไม่รู้จักสมาชิก id "zz"/);
  assert.match(all, /date "2026-02-30"/);
  assert.match(all, /start "8:30"/);
  assert.match(all, /วัน "MON"/);
});

test("พับบรรทัดไม่เกิน 75 ไบต์ และไม่แยกสระ/วรรณยุกต์ไทยออกจากตัวหลัก", () => {
  const long = "DESCRIPTION:" + "ผู้รับผิดชอบ อ.นพ. ตัวอย่าง หนึ่ง ".repeat(8) + "🟢🔵";
  const out = fold(long);
  for (const l of out.split("\r\n")) {
    assert.ok(enc.encode(l).length <= 75, "บรรทัดยาว " + enc.encode(l).length + " ไบต์");
    assert.doesNotMatch(l, /^ [ัิ-ฺ็-๎]/, "บรรทัดต่อขึ้นต้นด้วยสระ/วรรณยุกต์ลอย");
  }
  assert.equal(out.replace(/\r\n /g, ""), long);
  assert.equal(escapeText("a,b;c\\d\ne"), "a\\,b\\;c\\\\d\\ne");
});

test("งานซ้ำ: DTSTART เป็นครั้งแรกที่ตรงกฎ · UNTIL เป็น UTC · EXDATE เวลาตรง DTSTART", () => {
  const s = base();
  s.holidays.push({ date: "2026-12-10", name: "วันรัฐธรรมนูญ" });
  s.recurring.push({ id: "or1", type: "or", who: ["a", "b"], weekly: ["TH"], start: "08:30", end: "16:30",
    from: "2026-12-01", until: "2026-12-31", cancel: ["2026-12-17"] });
  const ics = buildFeed(s, feedList(s)[0]);
  assert.match(ics, /DTSTART;TZID=Asia\/Bangkok:20261203T083000/);      // 1 ธ.ค. เป็นวันอังคาร — ครั้งแรกคือพฤหัสฯ 3 ธ.ค.
  assert.match(ics, /UNTIL=20261231T165959Z/);
  assert.match(ics, /EXDATE;TZID=Asia\/Bangkok:20261210T083000,20261217T083000/);
  assert.match(ics, /TRIGGER:-PT30M/);
  assert.ok(ics.split("\n").every(l => l.endsWith("\r") || l === ""), "ทุกบรรทัดต้องจบด้วย CRLF");
  assert.deepEqual(occurrences(s, "2026-12-01", "2026-12-31").filter(o => o.kind !== "holiday").map(o => o.date),
    ["2026-12-03", "2026-12-24", "2026-12-31"]);
});

test("สัปดาห์เว้นสัปดาห์นับจากสัปดาห์ของครั้งแรกจริง (from เป็นวันอาทิตย์)", () => {
  const r = { weekly: ["MO"], every: 2, from: "2026-11-01", until: "2026-12-01" };   // 1 พ.ย. 2026 = อาทิตย์
  assert.deepEqual(ruleDates(r, "2026-11-01", "2026-12-01"), ["2026-11-02", "2026-11-16", "2026-11-30"]);
});

test("รายเดือน: ศุกร์สุดท้ายของเดือน และจันทร์แรกของเดือน", () => {
  assert.deepEqual(ruleDates({ monthly: { nth: -1, day: "FR" }, from: "2026-11-01", until: "2027-01-31" }, "2026-11-01", "2027-01-31"),
    ["2026-11-27", "2026-12-25", "2027-01-29"]);
  assert.deepEqual(ruleDates({ monthly: { nth: 1, day: "MO" }, from: "2026-11-01", until: "2027-01-31" }, "2026-11-01", "2027-01-31"),
    ["2026-11-02", "2026-12-07", "2027-01-04"]);
});

test("เวรข้ามคืน: DTEND เป็นวันถัดไป · งานทั้งวันหลายวัน: DTEND เป็นวันถัดจากวันสุดท้าย", () => {
  const s = base();
  s.events.push({ id: "c1", type: "call", who: ["b"], date: "2026-11-20", start: "16:00", end: "08:00" });
  s.events.push({ id: "l1", type: "leave", who: ["b"], date: "2026-12-14", end_date: "2026-12-18", all_day: true });
  const ics = buildFeed(s, feedList(s).find(f => f.member?.id === "b"));
  assert.match(ics, /DTEND;TZID=Asia\/Bangkok:20261121T080000/);
  assert.match(ics, /DTSTART;VALUE=DATE:20261214\r\nDTEND;VALUE=DATE:20261219/);
  assert.match(ics, /TRANSP:TRANSPARENT/);   // ลา ไม่บล็อกเวลาว่างในปฏิทิน
});

test("feed ของแต่ละคนมีเฉพาะงานของคนนั้น · ปฏิทินรวมมี emoji สีของทุกคนในหัวข้อ", () => {
  const s = base();
  s.events.push({ id: "x", type: "or", who: ["a"], date: "2026-11-20", start: "08:00", end: "12:00" });
  s.events.push({ id: "y", type: "or", who: ["a", "b"], date: "2026-11-21", start: "08:00", end: "12:00" });
  const [team, fa, fb] = feedList(s).map(f => buildFeed(s, f));
  assert.match(team, /SUMMARY:🔵🟢 OR — อ.เอ\\, หมอบี/);
  assert.match(fa, /UID:x\./); assert.match(fa, /UID:y\./);
  assert.doesNotMatch(fb, /UID:x\./); assert.match(fb, /UID:y\./);
  assert.match(fb, /X-APPLE-CALENDAR-COLOR:#2E9E4F/);
});

test("วันนี้ตามเวลาไทย ไม่ใช่ UTC ของเครื่อง", () => {
  assert.equal(bangkokToday(new Date("2026-11-18T17:30:00Z")), "2026-11-19");   // 00:30 น. ไทย
  assert.equal(bangkokToday(new Date("2026-11-18T16:59:00Z")), "2026-11-18");
  assert.equal(bangkokHour(new Date("2026-11-18T23:45:00Z")), 6);              // รอบเช้า 06:45 → โหมด today
  assert.equal(thaiDate("2026-11-19"), "พฤ. 19 พ.ย. 2569");
});

test("LINE: แท็กชื่อด้วย textV2 · หนีวงเล็บปีกกา · คนลาไม่ขึ้นในงานทั้งทีม", () => {
  const s = base();
  s.recurring.push({ id: "w", type: "or", title: "ราวด์ {เช้า}", who: ["all"], weekly: ["FR"], start: "07:00", end: "08:00", from: "2026-11-01", until: "2026-12-31" });
  s.events.push({ id: "o", type: "or", who: ["a"], date: "2026-11-20", start: "08:30", end: "16:30" });
  s.events.push({ id: "l", type: "leave", who: ["b"], date: "2026-11-20", all_day: true });
  const msg = formatMessage(s, "2026-11-20", { userIds: { a: "Uaaaa" } });
  assert.match(msg.text, /ราวด์ \{\{เช้า\}\}/);
  assert.match(msg.text, /🔵 \{m0\} \(Staff\)/);
  assert.deepEqual(msg.substitution.m0, { type: "mention", mentionee: { type: "user", userId: "Uaaaa" } });
  assert.match(msg.text, /🏖 ไม่อยู่\n  🟢 หมอบี — ลา/);
  assert.equal(lineMessage(msg).type, "textV2");
  const plain = lineMessage(formatMessage(s, "2026-11-20"));
  assert.equal(plain.type, "text");
  assert.match(plain.text, /ราวด์ \{เช้า\}/);
  assert.ok(absentOn(s, "2026-11-20").has("b"));
});

test("ตรวจงานชน: ลาแต่มีชื่อในงาน · เวรข้ามคืนชนงานเช้า", () => {
  const s = base();
  s.events.push({ id: "l", type: "leave", who: ["b"], date: "2026-11-20", all_day: true });
  s.events.push({ id: "o", type: "or", who: ["b"], date: "2026-11-20", start: "08:30", end: "12:00" });
  s.events.push({ id: "c", type: "call", who: ["a"], date: "2026-11-21", start: "16:00", end: "09:00" });
  s.events.push({ id: "o2", type: "or", who: ["a"], date: "2026-11-22", start: "08:30", end: "12:00" });
  const cs = conflicts(s, "2026-11-20", "2026-11-30");
  assert.deepEqual(cs.map(c => [c.member, c.reason]), [["b", "absent"], ["a", "overlap"]]);
  assert.equal(onDay(s, "2026-11-22").some(o => o.id === "c"), true);   // เวรเมื่อวานยังแตะวันนี้
});
