/**
 * ปฏิทินอาจารย์ออร์โธปิดิกส์ สายฟ้า — Google Calendar ที่แชร์กัน + แจ้งเตือนเข้ากลุ่ม LINE
 *
 * สคริปต์นี้อยู่ในบัญชี Google ของ "เจ้าของปฏิทิน" คนเดียว ไม่เกี่ยวกับระบบอื่นของแผนก
 * วิธีใช้ทีละขั้น: ดู README.md ในโฟลเดอร์เดียวกัน
 *
 * ห้ามใส่ชื่อผู้ป่วย HN หรือข้อมูลผู้ป่วยใด ๆ ในปฏิทิน
 */

// ══════════════════════════════════════════════════════════════════════════════
//  ส่วนที่ 1 — ตั้งค่า (แก้เฉพาะส่วนนี้)
// ══════════════════════════════════════════════════════════════════════════════
const CONFIG = {
  prefix: 'สายฟ้า',          // ชื่อปฏิทินจะเป็น "สายฟ้า – มานิตา" ฯลฯ
  teamName: 'ทุกคน',         // ปฏิทินรวมสำหรับงานที่ทุกคนทำพร้อมกัน เช่น OPD วันจันทร์

  // color: สีเริ่มต้นของปฏิทิน ใช้ตอนสร้างครั้งแรกเท่านั้น — เปลี่ยนสีทีหลังได้ในหน้า Google Calendar ของเจ้าของ
  //        แล้วจุดสีในข้อความ LINE จะเปลี่ยนตามเอง (คนอื่นตั้งสีในเครื่องตัวเองครั้งเดียว เพราะ Google เก็บสีแยกรายคน)
  // dot:   เว้นว่าง = ใช้จุดสีที่ใกล้กับสีปฏิทินที่สุด (🔴🟠🟡🟢🔵🟣🟤⚫) · หรือกำหนดเอง เช่น '🟣'
  // email: Gmail ของแต่ละท่าน ใช้ตอนแชร์ปฏิทิน (ขั้นที่ 4) — เว้นว่างไว้ได้ถ้าจะแชร์เองในหน้า Google Calendar
  people: [
    { name: 'มานิตา',    color: '#D50000', dot: '', email: '' },
    { name: 'ศุภศักดิ์',  color: '#3F51B5', dot: '', email: '' },
    { name: 'คงธัช',     color: '#0B8043', dot: '', email: '' },
    { name: 'อดิศร',     color: '#EF6C00', dot: '', email: '' },
    { name: 'ชนกันต์',   color: '#8E24AA', dot: '', email: '' }
  ],
  teamColor: '#616161',
  deputy: '',                // ชื่อ (ตาม name ข้างบน) ของผู้ที่ให้สิทธิ์ "จัดการการแชร์" เป็นสำรองของเจ้าของ — เว้นว่างได้

  // ── งานประจำ (routine) ──────────────────────────────────────────────────────
  routineFrom: '',           // '' = เริ่มจากวันที่กดรัน · หรือใส่วันที่ เช่น '2026-12-01'
  routineUntil: '2027-09-30',
  // day: MO TU WE TH FR SA SU · who: 'ALL' = ลงปฏิทิน "ทุกคน" รายการเดียว หรือรายชื่อ
  routine: [
    { key: 'opd-mon', title: 'OPD', day: 'MO', start: '09:00', end: '16:00', who: 'ALL', skipHolidays: true },
    { key: 'or-tue',  title: 'OR',  day: 'TU', start: '08:00', end: '16:00', who: ['มานิตา', 'ศุภศักดิ์'], skipHolidays: true },
    { key: 'or-thu',  title: 'OR',  day: 'TH', start: '08:00', end: '16:00', who: ['ชนกันต์'], skipHolidays: true },
    { key: 'or-fri',  title: 'OR',  day: 'FR', start: '08:00', end: '16:00', who: ['คงธัช', 'อดิศร'], skipHolidays: true }
  ],
  // งานที่วนกันสัปดาห์ละคน: คนแรกใน order ทำวันที่ firstDate แล้ววนตามลำดับทุกสัปดาห์
  // ถ้าตรงวันหยุดราชการ สัปดาห์นั้นงด และ "คนนั้นเลื่อนไปสัปดาห์ถัดไป" (ทุกคนที่อยู่ถัดไปเลื่อนตาม)
  // เวรแต่ละสัปดาห์ลงเป็นรายการเดี่ยว (ไม่ใช่รายการซ้ำ) สร้างในขั้นที่ 3 หลังรู้วันหยุด
  rotations: [
    { key: 'wed', day: 'WE', firstDate: '2026-11-25',
      order: ['ชนกันต์', 'มานิตา', 'ศุภศักดิ์', 'อดิศร', 'คงธัช'],
      tasks: [
        { title: 'ER',       start: '08:00', end: '16:00' },
        { title: 'OPD ปกส.', start: '13:00', end: '15:00' }
      ] },
    // พฤหัสบดี: ER และ OPD วนกันระหว่างสาย — สายฟ้าได้ทุก 4 สัปดาห์ (everyWeeks: 4) แล้ววนคนในสายตามลำดับชื่อเดิม
    // พฤหัสที่ตรงวันหยุด: ทั้งคิวเลื่อนไปสัปดาห์ถัดไป (ไม่ใช่รออีก 4 สัปดาห์)
    { key: 'thu-er', day: 'TH', firstDate: '2026-12-03', everyWeeks: 4,
      order: ['คงธัช', 'ชนกันต์', 'มานิตา', 'ศุภศักดิ์', 'อดิศร'],
      tasks: [{ title: 'ER', start: '08:00', end: '16:00' }] },
    { key: 'thu-opd', day: 'TH', firstDate: '2026-12-17', everyWeeks: 4,
      order: ['มานิตา', 'ศุภศักดิ์', 'อดิศร', 'คงธัช', 'ชนกันต์'],
      tasks: [{ title: 'OPD', start: '09:00', end: '16:00' }] }
  ],

  // ── วันหยุดราชการ ───────────────────────────────────────────────────────────
  // ดึงจากปฏิทิน "วันหยุดในไทย" ของ Google (เฉพาะที่ระบุว่า วันหยุดนักขัตฤกษ์ รวมวันหยุดชดเชยและวันหยุดพิเศษ)
  // รายการของ Google ไม่ตรงกับวันหยุดราชการทุกวัน สคริปต์จึงปรับให้ 2 อย่าง: ตัดวันที่ชื่อมีคำใน notHolidayNames
  // และเติม "วันเข้าพรรษา" (วันถัดจากอาสาฬหบูชา ซึ่ง Google ไม่มี) — ที่เหลือให้ตรวจรายการใน log แล้วแก้สองบรรทัดล่างนี้
  notHolidayNames: ['วันแรงงาน'],   // ราชการไม่หยุดวันแรงงาน
  extraHolidays: [],         // เพิ่มเอง เช่น [{ date: '2027-07-20', name: 'ชดเชยวันอาสาฬหบูชา' }]
  notHolidays: [],           // วันที่ไม่หยุดจริง เช่น ['2026-12-31']
  // กฎ: ตรวจทุกเช้า ถ้ามีวันหยุดประกาศเพิ่ม ให้งดงานประจำและเลื่อนคิวเวรพุธ/พฤหัสไปสัปดาห์ถัดไปเอง แล้วแจ้งใน LINE (false = แจ้งเจ้าของอย่างเดียว)
  autoApplyNewHolidays: true,

  // ── LINE ───────────────────────────────────────────────────────────────────
  // โควตา: บัญชี LINE ฟรีส่งได้ 300 ข้อความ/เดือน และการส่งเข้ากลุ่มนับ "ตามจำนวนคนในกลุ่ม" (กลุ่ม 5 คน = ครั้งละ 5)
  //        สคริปต์เช็กโควตาก่อนส่งทุกครั้ง ถ้าเหลือน้อยจะงดรอบเย็นก่อนเพื่อเก็บไว้ให้รอบเช้า · การตอบเมื่อมีคนพิมพ์ถามไม่นับโควตา
  line: {
    morning: { hour: 6,  minute: 30 },   // งานวันนี้ + รายการที่เพิ่ง​เพิ่ม/แก้ (เวลาจริงคลาดได้ ±15 นาที)
    evening: { hour: 18, minute: 30 },   // งานพรุ่งนี้ · ใส่ null เพื่อปิดรอบเย็น
    skipEmptyDays: true,                  // วันที่ไม่มีงานของใครเลย ไม่ส่ง (ประหยัดโควตา)
    replyCommands: true,                  // ตอบเมื่อมีคนพิมพ์ "วันนี้" "พรุ่งนี้" "สัปดาห์นี้" ในกลุ่ม
    changesLookAheadDays: 60              // รอบเช้าแจ้งรายการที่เพิ่ง​เพิ่ม/แก้ ที่อยู่ในช่วงกี่วันข้างหน้า
  },
  // รายการ "ทั้งวัน" ที่ชื่อขึ้นต้น/มีคำเหล่านี้ นับว่า "ไม่อยู่"
  absentStartsWith: ['ลาพัก', 'ลากิจ', 'ลาป่วย', 'ลาคลอด', 'ลาบวช', 'ลาศึกษา', 'ลาไป', 'ลา ', 'ลา('],   // และชื่อ "ลา" คำเดียว
  absentContains: ['ประชุม', 'อบรม', 'สัมมนา', 'ดูงาน', 'conference', 'meeting', 'leave']
};

// ══════════════════════════════════════════════════════════════════════════════
//  ส่วนที่ 2 — ไม่ต้องแก้
// ══════════════════════════════════════════════════════════════════════════════
const TZ = 'Asia/Bangkok';
const TZ_OFFSET = '+07:00';   // ไทยไม่มี daylight saving
const PROP = {
  CAL_IDS: 'CAL_IDS', ROUTINE: 'ROUTINE_SERIES', HOLIDAYS: 'HOLIDAYS', ROTATION: 'ROTATION_STATE',
  HOL_SEEN: 'HOLIDAYS_SEEN', HOL_APPLIED: 'HOLIDAYS_APPLIED', REMOVED: 'ROUTINE_REMOVED', LINK_CODE: 'LINE_LINK_CODE', SWAP_PENDING: 'SWAP_PENDING', LINE_USERS: 'LINE_USERS', NOTICE: 'HOLIDAY_NOTICE',
  TOKEN: 'LINE_TOKEN', GROUP: 'LINE_GROUP_ID', HOOK_KEY: 'WEBHOOK_KEY', LAST_MORNING: 'LAST_MORNING_AT'
};
const HOLIDAY_ICS = 'https://calendar.google.com/calendar/ical/th.th%23holiday%40group.v.calendar.google.com/public/basic.ics';
const DAY_CODES = ['SU', 'MO', 'TU', 'WE', 'TH', 'FR', 'SA'];
const TH_DAYS = ['อาทิตย์', 'จันทร์', 'อังคาร', 'พุธ', 'พฤหัสบดี', 'ศุกร์', 'เสาร์'];
const TH_DAYS_SHORT = ['อา.', 'จ.', 'อ.', 'พ.', 'พฤ.', 'ศ.', 'ส.'];
const TH_MONTHS = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.'];
const LINE_API = 'https://api.line.me/v2/bot';

// ── วันที่: ใช้สตริง 'yyyy-MM-dd' ตามปฏิทินไทย คำนวณบน UTC ล้วน ไม่ขึ้นกับเขตเวลาของสคริปต์ ──────────
function isYmd_(s) {
  if (typeof s !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(s)) return false;
  const d = new Date(s + 'T00:00:00Z');
  return !isNaN(d.getTime()) && d.toISOString().slice(0, 10) === s;
}
function addDays_(s, n) { const d = new Date(s + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); }
function weekday_(s) { return new Date(s + 'T00:00:00Z').getUTCDay(); }
function daysBetween_(a, b) { return Math.round((new Date(b + 'T00:00:00Z') - new Date(a + 'T00:00:00Z')) / 86400000); }
function nextWeekday_(fromYmd, dayCode) {
  const want = DAY_CODES.indexOf(dayCode);
  if (want < 0) throw new Error('วัน "' + dayCode + '" ไม่ถูก ใช้ ' + DAY_CODES.join(' '));
  let d = fromYmd;
  while (weekday_(d) !== want) d = addDays_(d, 1);
  return d;
}
/** เวลาไทย → Date (ระบุ +07:00 ตรง ๆ จึงถูกเสมอไม่ว่าสคริปต์ตั้งเขตเวลาอะไร) */
function at_(ymd, hm) { return new Date(ymd + 'T' + hm + ':00' + TZ_OFFSET); }
function ymd_(date) { return Utilities.formatDate(date, TZ, 'yyyy-MM-dd'); }
function hm_(date) { return Utilities.formatDate(date, TZ, 'HH:mm'); }
/** วันของรายการ "ทั้งวัน": Apps Script คืนเป็นเที่ยงคืนตามเขตเวลาของสคริปต์ จึงต้องอ่านกลับด้วยเขตเวลาเดียวกัน */
function ymdAllDay_(date) { return Utilities.formatDate(date, Session.getScriptTimeZone(), 'yyyy-MM-dd'); }
function today_() { return ymd_(new Date()); }
function thaiDate_(s, opt) {
  const o = opt || {};
  const d = new Date(s + 'T00:00:00Z');
  const wd = o.day === false ? '' : (o.short ? TH_DAYS_SHORT : TH_DAYS)[d.getUTCDay()] + ' ';
  return wd + d.getUTCDate() + ' ' + TH_MONTHS[d.getUTCMonth()] + (o.year === false ? '' : ' ' + (d.getUTCFullYear() + 543));
}

/** สีปฏิทิน (#rrggbb) → จุดสีที่ใกล้ที่สุด (ฟังก์ชันล้วน) */
function dotForHex_(hex) {
  const m = /^#?([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(String(hex || '').trim());
  if (!m) return '⚪';
  const r = parseInt(m[1], 16) / 255, g = parseInt(m[2], 16) / 255, b = parseInt(m[3], 16) / 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b), l = (max + min) / 2, d = max - min;
  const sat = d === 0 ? 0 : d / (1 - Math.abs(2 * l - 1));
  if (sat < 0.15) return l > 0.8 ? '⚪' : '⚫';
  let h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  h = (h * 60 + 360) % 360;
  if (h >= 10 && h < 45 && l < 0.45 && sat < 0.5) return '🟤';
  if (h < 10 || h >= 325) return '🔴';
  if (h < 42) return '🟠';
  if (h < 70) return '🟡';
  if (h < 180) return '🟢';
  if (h < 255) return '🔵';
  return '🟣';
}
/** จำนวนวันจันทร์–ศุกร์ที่เหลือในเดือนเดียวกัน หลังวันที่ให้มา (ฟังก์ชันล้วน) */
function weekdaysLeftInMonth_(ymd) {
  let n = 0;
  for (let d = addDays_(ymd, 1); d.slice(0, 7) === ymd.slice(0, 7); d = addDays_(d, 1)) { const wd = weekday_(d); if (wd >= 1 && wd <= 5) n++; }
  return n;
}

// ── ตรวจการตั้งค่า ─────────────────────────────────────────────────────────────
function checkConfig_(cfg) {
  const errs = [];
  const names = cfg.people.map(function (p) { return p.name; });
  const hm = /^([01]\d|2[0-3]):[0-5]\d$/;
  if (!names.length) errs.push('people ว่าง');
  names.forEach(function (n, i) { if (!n) errs.push('people[' + i + '] ไม่มี name'); if (names.indexOf(n) !== i) errs.push('ชื่อ "' + n + '" ซ้ำ'); });
  if (names.indexOf(cfg.teamName) >= 0) errs.push('teamName ซ้ำกับชื่อคน');
  if (cfg.deputy && names.indexOf(cfg.deputy) < 0) errs.push('deputy "' + cfg.deputy + '" ไม่อยู่ใน people');
  if (!isYmd_(cfg.routineUntil)) errs.push('routineUntil ต้องเป็น yyyy-MM-dd');
  if (cfg.routineFrom && !isYmd_(cfg.routineFrom)) errs.push('routineFrom ต้องเป็น yyyy-MM-dd หรือเว้นว่าง');
  const keys = {};
  const checkTime = function (w, t) {
    if (!hm.test(t.start) || !hm.test(t.end)) errs.push(w + ': เวลาต้องเป็น HH:mm เช่น 08:00');
    else if (t.end <= t.start) errs.push(w + ': end ต้องหลัง start');
  };
  (cfg.routine || []).forEach(function (r, i) {
    const w = 'routine[' + i + '] ' + (r.title || '');
    if (!r.key || keys[r.key]) errs.push(w + ': key ว่างหรือซ้ำ'); keys[r.key] = 1;
    if (!r.title) errs.push(w + ': ไม่มี title');
    if (DAY_CODES.indexOf(r.day) < 0) errs.push(w + ': day ต้องเป็น ' + DAY_CODES.join(' '));
    checkTime(w, r);
    if (r.who !== 'ALL') {
      if (!Array.isArray(r.who) || !r.who.length) errs.push(w + ": who ต้องเป็น 'ALL' หรือรายชื่อ");
      else r.who.forEach(function (n) { if (names.indexOf(n) < 0) errs.push(w + ': ไม่รู้จัก "' + n + '"'); });
    }
  });
  (cfg.rotations || []).forEach(function (r, i) {
    const w = 'rotations[' + i + ']';
    if (!r.key || keys[r.key]) errs.push(w + ': key ว่างหรือซ้ำ'); keys[r.key] = 1;
    if (DAY_CODES.indexOf(r.day) < 0) errs.push(w + ': day ต้องเป็น ' + DAY_CODES.join(' '));
    if (!isYmd_(r.firstDate)) errs.push(w + ': firstDate ต้องเป็น yyyy-MM-dd');
    else if (DAY_CODES[weekday_(r.firstDate)] !== r.day) errs.push(w + ': firstDate ' + r.firstDate + ' เป็นวัน' + TH_DAYS[weekday_(r.firstDate)] + ' ไม่ตรงกับ day ' + r.day);
    if (!Array.isArray(r.order) || !r.order.length) errs.push(w + ': order ว่าง');
    else r.order.forEach(function (n, j) { if (names.indexOf(n) < 0) errs.push(w + ': ไม่รู้จัก "' + n + '"'); if (r.order.indexOf(n) !== j) errs.push(w + ': "' + n + '" ซ้ำใน order'); });
    (r.tasks || []).forEach(function (t, j) { if (!t.title) errs.push(w + '.tasks[' + j + ']: ไม่มี title'); checkTime(w + ' ' + (t.title || ''), t); });
    if (!r.tasks || !r.tasks.length) errs.push(w + ': tasks ว่าง');
    if (r.everyWeeks != null && !(r.everyWeeks >= 1 && r.everyWeeks <= 12 && Math.floor(r.everyWeeks) === r.everyWeeks)) errs.push(w + ': everyWeeks ต้องเป็นจำนวนเต็ม 1–12');
  });
  if (errs.length) throw new Error('CONFIG มีจุดที่ต้องแก้:\n• ' + errs.join('\n• '));
}

/**
 * แผนงานประจำ → รายการ "ชุดรายการซ้ำ" ที่ต้องสร้าง (ฟังก์ชันล้วน ไม่แตะปฏิทิน ทดสอบได้)
 * คืน [{ key, calendar, title, first, start, end, intervalWeeks, until, skipHolidays }]
 */
function routinePlan_(cfg, fromYmd) {
  const out = [];
  const from = cfg.routineFrom && cfg.routineFrom > fromYmd ? cfg.routineFrom : fromYmd;
  (cfg.routine || []).forEach(function (r) {
    const first = nextWeekday_(from, r.day);
    if (first > cfg.routineUntil) return;
    const cals = r.who === 'ALL' ? [cfg.teamName] : r.who;
    cals.forEach(function (c) {
      out.push({ key: r.key + '|' + c, calendar: c, title: r.title, first: first, start: r.start, end: r.end,
        intervalWeeks: 1, until: cfg.routineUntil, skipHolidays: r.skipHolidays !== false, location: r.location || '' });
    });
  });
  return out;
}

/**
 * แผนเวรวน (ฟังก์ชันล้วน): ไล่ทีละสัปดาห์จาก firstDate — สัปดาห์ที่ตรงวันหยุดถูกข้ามและคิวไม่เดิน
 * (ใช้กับคิวระหว่างสายด้วย: วันหยุดเลื่อนทั้งคิวไปหนึ่งสัปดาห์ สายเราจึงได้สัปดาห์ถัดไป ไม่ใช่รออีกรอบ)
 * holidayDates = { 'yyyy-MM-dd': 1 } · คืน [{ date, name }] เฉพาะวันที่ >= from
 */
function rotationPlan_(rot, holidayDates, from, until) {
  const out = [];
  const every = rot.everyWeeks || 1;   // everyWeeks: 4 = สายนี้ได้ทุกรอบที่ 4 ของ "สัปดาห์ที่ไม่ใช่วันหยุด"
  let slot = 0;                         // นับเฉพาะสัปดาห์ที่ไม่ตรงวันหยุด — วันหยุดทำให้ทุกรอบถัดไปเลื่อนหนึ่งสัปดาห์
  for (let d = rot.firstDate; d <= until; d = addDays_(d, 7)) {
    if (holidayDates[d]) continue;
    if (slot % every === 0) {
      const name = rot.order[(slot / every) % rot.order.length];
      if (d >= from) out.push({ date: d, name: name });
    }
    slot++;
  }
  return out;
}
const ROT_TAG = 'sayfa';

// ── ที่เก็บค่า (Script Properties) ──────────────────────────────────────────────
function props_() { return PropertiesService.getScriptProperties(); }
function getJson_(key, fallback) { const v = props_().getProperty(key); if (!v) return fallback; try { return JSON.parse(v); } catch (e) { return fallback; } }
function setJson_(key, obj) { props_().setProperty(key, JSON.stringify(obj)); }
function calName_(shortName) { return CONFIG.prefix + ' – ' + shortName; }
function allCalNames_() { return CONFIG.people.map(function (p) { return p.name; }).concat([CONFIG.teamName]); }
function getCal_(shortName) {
  const ids = getJson_(PROP.CAL_IDS, {});
  const cal = ids[shortName] ? CalendarApp.getCalendarById(ids[shortName]) : null;
  if (!cal) throw new Error('ยังไม่มีปฏิทิน "' + calName_(shortName) + '" — รัน step1_createCalendars ก่อน');
  return cal;
}

// ══════════════════════════════════════════════════════════════════════════════
//  ขั้นที่ 1 — สร้างปฏิทิน (รันซ้ำได้ ไม่สร้างซ้ำ)
// ══════════════════════════════════════════════════════════════════════════════
function step1_createCalendars() {
  checkConfig_(CONFIG);
  const ids = getJson_(PROP.CAL_IDS, {});
  const owned = CalendarApp.getAllOwnedCalendars();
  const wanted = CONFIG.people.map(function (p) { return { name: p.name, color: p.color }; })
    .concat([{ name: CONFIG.teamName, color: CONFIG.teamColor }]);
  wanted.forEach(function (w) {
    const full = calName_(w.name);
    let cal = ids[w.name] ? CalendarApp.getCalendarById(ids[w.name]) : null;
    let how = 'มีอยู่แล้ว';
    if (!cal) {
      cal = owned.filter(function (c) { return c.getName() === full; })[0] || null;
      how = 'พบปฏิทินชื่อเดียวกัน ใช้อันเดิม';
    }
    if (!cal) {
      cal = CalendarApp.createCalendar(full, { timeZone: TZ, color: w.color });
      how = 'สร้างใหม่';
    }
    if (how === 'สร้างใหม่' && ids[w.name]) {
      // ปฏิทินเดิมหายไป (ถูกลบ): ล้างบันทึกงานประจำ/เวรของปฏิทินนั้น เพื่อให้ขั้นที่ 2 และ 3 ลงให้ใหม่
      const made = getJson_(PROP.ROUTINE, {});
      Object.keys(made).forEach(function (k) { if (made[k].cal === w.name) delete made[k]; });
      setJson_(PROP.ROUTINE, made);
      props_().deleteProperty(PROP.ROTATION);
      props_().deleteProperty(PROP.HOL_SEEN);
      how = 'ปฏิทินเดิมหาย สร้างใหม่ — รัน step2 และ step3a/3b อีกครั้งเพื่อลงงานคืน';
    }
    ids[w.name] = cal.getId();
    console.log('✅ ' + full + ' — ' + how);
  });
  setJson_(PROP.CAL_IDS, ids);
  console.log('เสร็จ: ปฏิทิน ' + wanted.length + ' อัน · ต่อไปรัน step2_createRoutine');
}

// ══════════════════════════════════════════════════════════════════════════════
//  ขั้นที่ 2 — ลงงานประจำเป็นรายการซ้ำ (รันซ้ำได้: ชุดที่สร้างแล้วจะถูกข้าม)
//  ข้อควรรู้: ถ้าแก้งานประจำในแอปปฏิทินด้วย "รายการนี้และรายการต่อจากนี้" Google จะแตกเป็นชุดใหม่ที่สคริปต์ไม่รู้จัก
//  ชุดใหม่นั้นจะไม่ถูกงดในวันหยุดเอง (ขั้น 3ก จะเตือนให้เห็น) — เปลี่ยนถาวรให้แก้ CONFIG.routine ด้วย key ใหม่แล้วรันขั้น 2
// ══════════════════════════════════════════════════════════════════════════════
function step2_createRoutine() {
  checkConfig_(CONFIG);
  const plan = routinePlan_(CONFIG, today_());
  const made = getJson_(PROP.ROUTINE, {});
  let created = 0, skipped = 0;
  plan.forEach(function (s) {
    if (made[s.key]) { skipped++; return; }
    const cal = getCal_(s.calendar);
    const rule = CalendarApp.newRecurrence().addWeeklyRule().interval(s.intervalWeeks).until(at_(s.until, '23:59'));
    const series = cal.createEventSeries(s.title, at_(s.first, s.start), at_(s.first, s.end), rule,
      s.location ? { location: s.location } : {});
    made[s.key] = { id: series.getId(), cal: s.calendar, skip: s.skipHolidays ? 1 : 0 };
    setJson_(PROP.ROUTINE, made);   // บันทึกทุกชุด — ถ้าหมดเวลากลางทาง รันซ้ำแล้วทำต่อจากที่ค้าง
    created++;
    console.log('➕ ' + calName_(s.calendar) + ': ' + s.title + ' ' + s.start + '–' + s.end + ' เริ่ม ' + thaiDate_(s.first) +
      (s.intervalWeeks > 1 ? ' ทุก ' + s.intervalWeeks + ' สัปดาห์' : ' ทุกสัปดาห์'));
  });
  console.log('เสร็จ: สร้าง ' + created + ' ชุด · ข้าม (มีแล้ว) ' + skipped + ' ชุด · ต่อไปรัน step3a_previewHolidays (ดูวันหยุดและลำดับเวรก่อน ยังไม่แก้อะไร)');
}

// ══════════════════════════════════════════════════════════════════════════════
//  ขั้นที่ 3 — ตัดงานประจำออกในวันหยุดราชการ (รันซ้ำได้ · ตั้งให้รันเองทุกเดือนในขั้นที่ 6)
// ══════════════════════════════════════════════════════════════════════════════
/** อ่านไฟล์ปฏิทินวันหยุดของ Google → [{date, name}] เฉพาะ "วันหยุดนักขัตฤกษ์" (ฟังก์ชันล้วน) */
function parseHolidayIcs_(text) {
  const out = [];
  const unfolded = String(text).replace(/\r?\n[ \t]/g, '').replace(/\r\n/g, '\n');
  unfolded.split('BEGIN:VEVENT').slice(1).forEach(function (blk) {
    const get = function (name) { const m = new RegExp('^' + name + '[^:\\n]*:(.*)$', 'm').exec(blk); return m ? m[1] : ''; };
    const start = get('DTSTART'), end = get('DTEND');
    const desc = get('DESCRIPTION'), sum = get('SUMMARY');
    if (!/^\d{8}$/.test(start)) return;
    if (desc.indexOf('วันหยุดนักขัตฤกษ์') !== 0 && desc.indexOf('Public holiday') !== 0) return;
    const name = sum.replace(/\\([,;\\])/g, '$1').replace(/\\n/gi, ' ').replace(/[​‌‍﻿]/g, '').trim();
    const iso = function (s) { return s.slice(0, 4) + '-' + s.slice(4, 6) + '-' + s.slice(6, 8); };
    let d = iso(start);
    const stop = /^\d{8}$/.test(end) ? iso(end) : addDays_(d, 1);   // DTEND ของรายการทั้งวันเป็นวันถัดจากวันสุดท้าย
    for (let i = 0; d < stop && i < 14; i++, d = addDays_(d, 1)) out.push({ date: d, name: name });
  });
  return out;
}
/**
 * ปรับรายการของ Google ให้ใกล้วันหยุดราชการ (ฟังก์ชันล้วน) · คืน { list, notes }
 *  − ตัดวันที่ชื่อมีคำใน notHolidayNames (เช่น วันแรงงาน — ธนาคาร/เอกชนหยุด ราชการไม่หยุด)
 *  + เติมวันเข้าพรรษา = วันถัดจากวันอาสาฬหบูชา (ราชการหยุด แต่ไม่อยู่ในรายการของ Google)
 *  ! ไม่เดาวันหยุดชดเชยที่ต้องเลื่อนเพราะชนกัน — เตือนให้ตรวจกับประกาศ ครม. แทน
 *    (เดาผิดแล้วลบงานของวันทำงานจริง เสียหายกว่าปล่อยงานค้างไว้ในวันหยุด)
 */
function civilServiceAdjust_(fromGoogle, cfg) {
  const notes = [];
  const drop = cfg.notHolidayNames || [];
  const list = fromGoogle.filter(function (h) { return !drop.some(function (w) { return w && h.name.indexOf(w) >= 0; }); });
  const byDate = {};
  list.forEach(function (h) { byDate[h.date] = h; });
  fromGoogle.forEach(function (h) {
    if (h.name.indexOf('อาสาฬหบูชา') < 0 || h.name.indexOf('ชดเชย') >= 0) return;
    const kp = addDays_(h.date, 1);
    const clash = byDate[kp];
    if (clash) clash.name = 'วันเข้าพรรษา'; else { const n = { date: kp, name: 'วันเข้าพรรษา' }; list.push(n); byDate[kp] = n; }
    const wd = weekday_(kp), wdA = weekday_(h.date);
    if (clash || wd === 0 || wd === 6 || wdA === 0 || wdA === 6)
      notes.push('ปี ' + (Number(kp.slice(0, 4)) + 543) + ': วันอาสาฬหบูชา/เข้าพรรษา (' + thaiDate_(h.date, { short: true, year: false }) + ' – ' + thaiDate_(kp, { short: true, year: false }) +
        ') ตรงกับเสาร์–อาทิตย์หรือชนวันหยุดชดเชย — ตรวจประกาศ ครม. ว่าวันหยุดชดเชยเป็นวันไหน แล้วเติมใน extraHolidays ถ้ายังไม่มีในรายการ');
  });
  return { list: list, notes: notes };
}
/** วันหยุดในช่วง [from, to] หลังรวม extraHolidays และตัด notHolidays (ฟังก์ชันล้วน) */
function mergeHolidays_(fromGoogle, cfg, from, to) {
  const map = {};
  fromGoogle.concat(cfg.extraHolidays || []).forEach(function (h) {
    if (!h || !isYmd_(h.date) || h.date < from || h.date > to) return;
    if ((cfg.notHolidays || []).indexOf(h.date) >= 0) return;
    if (!map[h.date]) map[h.date] = String(h.name || 'วันหยุด').slice(0, 45);   // ที่เก็บค่าจำกัด 9 KB ต่อค่า (อักษรไทยตัวละ 3 ไบต์)
  });
  return Object.keys(map).sort().map(function (d) { return { date: d, name: map[d] }; });
}
/** ดึงและปรับรายการวันหยุด · คืน { hol (แสดงผล/LINE), allHol (ตั้งแต่เวรวนแรก), notes } — ผิดปกติให้ throw ไม่แก้อะไร */
function loadHolidays_(today) {
  const res = UrlFetchApp.fetch(HOLIDAY_ICS, { muteHttpExceptions: true });
  if (res.getResponseCode() !== 200) throw new Error('ดึงปฏิทินวันหยุดของ Google ไม่ได้ (HTTP ' + res.getResponseCode() + ') — ลองรันใหม่ภายหลัง');
  const fromGoogle = parseHolidayIcs_(res.getContentText('UTF-8'));
  if (fromGoogle.length < 5) throw new Error('ปฏิทินวันหยุดของ Google อ่านได้ ' + fromGoogle.length + ' วัน ซึ่งน้อยผิดปกติ — ไม่แก้อะไร เพื่อความปลอดภัย');
  const adjusted = civilServiceAdjust_(fromGoogle, CONFIG);
  const firsts = (CONFIG.rotations || []).map(function (r) { return r.firstDate; }).sort();
  return {
    hol: mergeHolidays_(adjusted.list, CONFIG, addDays_(today, -7), CONFIG.routineUntil),
    allHol: mergeHolidays_(adjusted.list, CONFIG, firsts[0] || today, CONFIG.routineUntil),
    notes: adjusted.notes.filter(function (n) { return Number(/ปี (\d{4})/.exec(n)[1]) - 543 >= Number(today.slice(0, 4)); })
  };
}
/** ลายเซ็นของรายการวันหยุดตั้งแต่วันนี้ — ใช้ยืนยันว่า "ที่จะลบ" ตรงกับ "ที่เจ้าของตรวจแล้ว" */
function holidaySig_(hol, today) { return hol.filter(function (h) { return h.date >= today; }).map(function (h) { return h.date; }).join(','); }
/** งานประจำ (รายการซ้ำ) ที่ตรงวันหยุด และยังอยู่ในปฏิทิน → [{ cal, date, ev }] */
function routineOnHolidays_(hol, today) {
  const made = getJson_(PROP.ROUTINE, {});
  const skipIds = {};
  Object.keys(made).forEach(function (k) { if (made[k].skip) skipIds[made[k].id] = 1; });
  const ids = getJson_(PROP.CAL_IDS, {});
  const out = [];
  hol.filter(function (h) { return h.date >= today; }).forEach(function (h) {
    allCalNames_().forEach(function (n) {
      const cal = ids[n] ? CalendarApp.getCalendarById(ids[n]) : null;
      if (!cal) throw new Error('เข้าปฏิทิน "' + calName_(n) + '" ไม่ได้ — ตรวจว่ายังไม่ถูกลบ แล้วรัน step1_createCalendars');
      cal.getEvents(at_(h.date, '00:00'), at_(addDays_(h.date, 1), '00:00')).forEach(function (ev) {
        if (!skipIds[ev.getId()] || ev.isAllDayEvent() || ymd_(ev.getStartTime()) !== h.date) return;
        out.push({ calName: n, cal: cal, date: h.date, ev: ev });
      });
    });
  });
  return out;
}

/**
 * ขั้นที่ 3ก — ดูก่อน ไม่แก้อะไรในปฏิทิน: แสดงรายการวันหยุด งานประจำที่จะถูกงด และลำดับเวรวน
 * ตรวจแล้วถูก จึงรัน step3b_applyHolidays · ไม่ถูก แก้ extraHolidays / notHolidays ใน CONFIG แล้วรันขั้นนี้ใหม่
 */
function step3a_previewHolidays() {
  checkConfig_(CONFIG);
  const today = today_();
  const h = loadHolidays_(today);
  const future = h.hol.filter(function (x) { return x.date >= today; });
  console.log('วันหยุดราชการถึง ' + thaiDate_(CONFIG.routineUntil) + ' (' + future.length + ' วัน) — โปรดเทียบกับประกาศวันหยุดราชการ:');
  future.forEach(function (x) { console.log('  🎌 ' + thaiDate_(x.date, { short: true }) + ' — ' + x.name); });
  h.notes.forEach(function (n) { console.warn('⚠️ ' + n); });
  console.log('(รายการมาจาก Google แล้วปรับ: ตัด ' + (CONFIG.notHolidayNames || []).join(', ') + ' · เติม วันเข้าพรรษา)');
  const hits = routineOnHolidays_(h.hol, today);
  console.log('งานประจำที่จะถูกงด ' + hits.length + ' รายการ:');
  hits.forEach(function (x) { console.log('  ✂️ ' + thaiDate_(x.date, { short: true, year: false }) + ' ' + calName_(x.calName) + ': ' + x.ev.getTitle()); });
  // รายการซ้ำอื่นที่ตรงวันหยุด (เช่น งานประจำที่ถูกแก้ด้วย "รายการนี้และรายการต่อจากนี้" หรือที่ลงเอง) — สคริปต์ไม่รู้จัก จึงไม่งดให้
  const known = {};
  hits.forEach(function (x) { known[x.calName + '|' + x.date + '|' + x.ev.getId()] = 1; });
  const idsAll = getJson_(PROP.CAL_IDS, {});
  const others = [];
  future.forEach(function (x) {
    allCalNames_().forEach(function (n) {
      const cal = idsAll[n] ? CalendarApp.getCalendarById(idsAll[n]) : null;
      if (!cal) return;
      cal.getEvents(at_(x.date, '00:00'), at_(addDays_(x.date, 1), '00:00')).forEach(function (ev) {
        if (ev.isAllDayEvent() || !ev.isRecurringEvent() || ymd_(ev.getStartTime()) !== x.date || known[n + '|' + x.date + '|' + ev.getId()]) return;
        others.push('  ❗ ' + thaiDate_(x.date, { short: true, year: false }) + ' ' + calName_(n) + ': ' + ev.getTitle());
      });
    });
  });
  if (others.length) {
    console.warn('รายการซ้ำที่ตรงวันหยุดแต่สคริปต์ "ไม่ได้งดให้" ' + others.length + ' รายการ — ถ้าวันนั้นไม่ทำจริง ลบเองในปฏิทิน (เลือกเฉพาะรายการนี้):');
    others.forEach(function (l) { console.warn(l); });
  }
  const holSet = {};
  h.allHol.forEach(function (x) { holSet[x.date] = 1; });
  (CONFIG.rotations || []).forEach(function (rot) {
    const from = today > rot.firstDate ? today : rot.firstDate;
    console.log('เวรวน "' + rot.key + '" (' + rot.tasks.map(function (t) { return t.title; }).join(' + ') + ') 8 รอบแรก: ' +
      rotationPlan_(rot, holSet, from, CONFIG.routineUntil).slice(0, 8).map(function (p) { return thaiDate_(p.date, { day: false, year: false }) + ' ' + p.name; }).join(' · '));
  });
  props_().setProperty(PROP.HOL_SEEN, holidaySig_(h.hol, today));
  console.log('ยังไม่ได้แก้อะไรในปฏิทิน · ถ้ารายการถูกต้อง รัน step3b_applyHolidays · ถ้าไม่ถูก แก้ extraHolidays / notHolidays แล้วรันขั้นนี้ใหม่');
}

/** ขั้นที่ 3ข — ลงมือ: งดงานประจำในวันหยุด คืนงานของวันที่ไม่หยุดแล้ว และลง/จัดเวรวน (ทำได้เฉพาะรายการวันหยุดที่ดูแล้วในขั้น 3ก) */
function step3b_applyHolidays() {
  checkConfig_(CONFIG);
  const today = today_();
  const h = loadHolidays_(today);
  const sig = holidaySig_(h.hol, today);
  if (props_().getProperty(PROP.HOL_SEEN) !== sig) {
    throw new Error('รายการวันหยุดตอนนี้ไม่ตรงกับที่ดูไว้ในขั้น 3ก (หรือยังไม่ได้รันขั้น 3ก) — รัน step3a_previewHolidays ตรวจรายการก่อน แล้วค่อยรันขั้นนี้');
  }
  const ids = getJson_(PROP.CAL_IDS, {});
  const isHol = {};
  h.hol.forEach(function (x) { isHol[x.date] = 1; });

  // คืนงานประจำของวันที่เคยงดไว้ แต่ตอนนี้ไม่ใช่วันหยุดแล้ว (เช่น ใส่ notHolidays ทีหลัง)
  let log = getJson_(PROP.REMOVED, []).filter(function (r) { return r.d >= today; });
  let restored = 0;
  log = log.filter(function (r) {
    if (isHol[r.d]) return true;
    const cal = ids[r.c] ? CalendarApp.getCalendarById(ids[r.c]) : null;
    if (cal) { cal.createEvent(r.t, at_(r.d, r.s), at_(r.d, r.e)).setTag(ROT_TAG, 'restored'); restored++; }
    return false;
  });

  let removed = 0, checked = false;
  const countSeries = function (cal, id, fromYmd) {   // นับครั้งที่เหลือของชุดนั้นใน 200 วันข้างหน้า
    return cal.getEvents(at_(fromYmd, '00:00'), at_(addDays_(fromYmd, 200), '00:00')).filter(function (e) { return e.getId() === id; }).length;
  };
  routineOnHolidays_(h.hol, today).forEach(function (x) {
    const id = x.ev.getId();
    const before = checked ? 0 : countSeries(x.cal, id, x.date);
    log.push({ c: x.calName, d: x.date, t: x.ev.getTitle(), s: hm_(x.ev.getStartTime()), e: hm_(x.ev.getEndTime()) });
    x.ev.deleteEvent();   // ลบเฉพาะครั้งของวันนั้น ไม่ใช่ทั้งชุด
    removed++;
    setJson_(PROP.REMOVED, log);
    if (!checked) {
      // ตรวจครั้งแรกของทุกรอบว่าการลบ "ครั้งเดียว" ไม่ได้ทำให้ครั้งอื่นของชุดหายไปด้วย — ถ้าหาย หยุดทันทีก่อนเสียหายเพิ่ม
      checked = true;
      const after = countSeries(x.cal, id, x.date);
      if (after < before - 1) throw new Error('หยุด: ลบงานประจำของวันหยุด ' + x.date + ' แล้วครั้งอื่นของชุดเดียวกันหายไปด้วย (' + before + ' → ' + after +
        ') — ไม่ทำต่อ กรุณาแจ้งผู้พัฒนา · กู้คืนได้จากถังขยะของปฏิทิน "' + calName_(x.calName) + '"');
    }
  });
  setJson_(PROP.REMOVED, log);
  setJson_(PROP.HOLIDAYS, h.hol);
  console.log('งดงานประจำที่ตรงวันหยุด ' + removed + ' รายการ · คืนงานของวันที่ไม่หยุดแล้ว ' + restored + ' รายการ');
  syncRotations_(h.allHol, today);
  props_().setProperty(PROP.HOL_APPLIED, sig);
  ensureHolidayTrigger_();
}

/**
 * กฎวันหยุดประกาศเพิ่ม — รันเองทุกเช้า: เทียบรายการวันหยุดกับที่ลงมือไว้ครั้งก่อน
 *  • มีวันหยุด "เพิ่ม" ไม่เกิน 3 วัน: งดงานประจำวันนั้น และเลื่อนคิวเวรพุธ/พฤหัสไปสัปดาห์ถัดไปให้เอง แล้วแจ้งในข้อความ LINE รอบเช้าถัดไป
 *  • วันหยุด "หายไป" จากรายการ, เพิ่มทีเดียวเกิน 3 วัน, หรือไฟล์ผิดปกติ: ไม่แตะปฏิทิน แจ้งเจ้าของทางอีเมลให้ตรวจเอง (กันข้อมูลต้นทางเพี้ยน)
 * แหล่งข้อมูลคือปฏิทิน "วันหยุดในไทย" ของ Google — สคริปต์อ่านข่าวเองไม่ได้ ถ้ารู้ข่าวก่อน ให้เติมวันที่ใน extraHolidays
 */
function holidayWatch() {
  const applied = props_().getProperty(PROP.HOL_APPLIED);
  if (applied === null) return;
  const today = today_();
  const h = loadHolidays_(today);
  const sig = holidaySig_(h.hol, today);
  const now = sig.split(',').filter(String);
  const was = applied.split(',').filter(function (d) { return d >= today; });
  const added = now.filter(function (d) { return was.indexOf(d) < 0; }), gone = was.filter(function (d) { return now.indexOf(d) < 0; });
  if (!added.length && !gone.length) { console.log('วันหยุดไม่เปลี่ยน'); return; }
  if (CONFIG.autoApplyNewHolidays !== false && !gone.length && added.length <= 3) {
    props_().setProperty(PROP.HOL_SEEN, sig);
    step3b_applyHolidays();
    const names = added.map(function (d) {
      const x = h.hol.filter(function (y) { return y.date === d; })[0];
      return thaiDate_(d, { short: true }) + (x ? ' ' + x.name : '');
    });
    props_().setProperty(PROP.NOTICE, '🎌 วันหยุดราชการประกาศเพิ่ม: ' + names.join(' · ') +
      '\nงดงานประจำวันนั้น และเลื่อนเวรพุธ/พฤหัสไปสัปดาห์ถัดไปแล้ว — เวรที่แลกกันไว้หลังวันนั้นต้องแลกใหม่ โปรดดูปฏิทิน');
    console.log('วันหยุดเพิ่ม ' + added.join(', ') + ' — ปรับปฏิทินให้แล้ว');
    return;
  }
  throw new Error('รายการวันหยุดราชการเปลี่ยน — ยังไม่ได้แก้อะไรในปฏิทิน · เพิ่ม: ' + (added.join(', ') || '-') + ' · หายไป: ' + (gone.join(', ') || '-') +
    ' · เปิดสคริปต์ปฏิทิน' + CONFIG.prefix + ' แล้วรัน step3a_previewHolidays ตรวจรายการ ตามด้วย step3b_applyHolidays');
}

/**
 * ลง/จัดเวรวนใหม่ให้ตรงกับวันหยุดล่าสุด
 * - ครั้งแรก: ลงตั้งแต่วันนี้ถึง routineUntil
 * - ครั้งถัดไป: ถ้าวันหยุดที่ตรงวันเวรไม่เปลี่ยน ไม่แตะอะไรเลย (การแลกเวรที่ทำเองในปฏิทินยังอยู่)
 *   ถ้าเปลี่ยน: จัดใหม่ตั้งแต่สัปดาห์แรกที่ลำดับเปลี่ยนเป็นต้นไป — การแลกเวรที่ทำเองหลังจุดนั้นจะถูกจัดทับ
 */
function syncRotations_(holidays, today) {
  const state = getJson_(PROP.ROTATION, {});
  const ids = getJson_(PROP.CAL_IDS, {});
  // เวรของชุดที่ถูกลบ/เปลี่ยนชื่อ key ใน CONFIG: ลบของอนาคตทิ้ง ไม่ให้มีสองคนในเวรเดียว
  const liveKeys = {};
  (CONFIG.rotations || []).forEach(function (r) { liveKeys['rot:' + r.key] = 1; });
  Object.keys(state).forEach(function (k) {
    if (liveKeys['rot:' + k]) return;
    let n = 0;
    CONFIG.people.forEach(function (p) {
      const cal = ids[p.name] ? CalendarApp.getCalendarById(ids[p.name]) : null;
      if (!cal) return;
      cal.getEvents(at_(today, '00:00'), at_(addDays_(state[k].until || CONFIG.routineUntil, 1), '00:00')).forEach(function (ev) {
        if (ev.getTag(ROT_TAG) === 'rot:' + k) { ev.deleteEvent(); n++; }
      });
    });
    delete state[k];
    setJson_(PROP.ROTATION, state);
    console.log('เวรวน "' + k + '" ไม่อยู่ใน CONFIG แล้ว — ลบเวรที่เหลือ ' + n + ' รายการ');
  });
  (CONFIG.rotations || []).forEach(function (rot) {
    const until = CONFIG.routineUntil;
    const holSet = {};
    holidays.forEach(function (h) { if (h.date >= rot.firstDate && h.date <= until && DAY_CODES[weekday_(h.date)] === rot.day) holSet[h.date] = 1; });
    // ไม่รวม routineUntil ในลายเซ็น: การต่ออายุปีถัดไปต้องไม่จัดเวรที่ลงไว้แล้ว (และที่แลกกันเอง) ใหม่ทั้งหมด
    const cfgSig = JSON.stringify([rot.firstDate, rot.order, rot.tasks, rot.everyWeeks || 1]);
    const old = state[rot.key];
    if (old && old.cfg === cfgSig) {
      // สัปดาห์ที่ผ่านไปแล้วยึดตามที่เคยบันทึก — ถ้ารายการของ Google ตกหล่นวันหยุดเก่า คิวปัจจุบันต้องไม่เลื่อน
      Object.keys(holSet).forEach(function (d) { if (d < today) delete holSet[d]; });
      (old.hol || []).forEach(function (d) { if (d < today) holSet[d] = 1; });
    }
    let from = today > rot.firstDate ? today : rot.firstDate;
    if (old && old.cfg === cfgSig) {
      const oldSet = {};
      (old.hol || []).forEach(function (d) { oldSet[d] = 1; });
      const a = rotationPlan_(rot, oldSet, from, old.until || until), b = rotationPlan_(rot, holSet, from, until);
      const key = function (x) { return x ? x.date + '|' + x.name : ''; };
      let k = 0;
      while (k < Math.max(a.length, b.length) && key(a[k]) === key(b[k])) k++;
      if (k >= Math.max(a.length, b.length)) { console.log('เวรวน "' + rot.key + '": วันหยุดไม่กระทบ ไม่เปลี่ยนอะไร'); return; }
      const d1 = a[k] ? a[k].date : b[k].date, d2 = b[k] ? b[k].date : a[k].date;
      from = d1 < d2 ? d1 : d2;
    }
    const want = {};   // 'date|title' → { name, task }
    rotationPlan_(rot, holSet, from, until).forEach(function (p) {
      rot.tasks.forEach(function (t) { want[p.date + '|' + t.title] = { date: p.date, name: p.name, task: t }; });
    });
    let kept = 0, removed = 0, created = 0;
    CONFIG.people.forEach(function (p) {   // ทุกคน ไม่ใช่เฉพาะคนใน order — คนที่ถูกถอดออกจากเวรต้องไม่เหลือเวรค้าง
      const name = p.name;
      const cal = ids[name] ? CalendarApp.getCalendarById(ids[name]) : null;
      if (!cal) throw new Error('เข้าปฏิทิน "' + calName_(name) + '" ไม่ได้ — ตรวจว่ายังไม่ถูกลบ แล้วรัน step1_createCalendars');
      cal.getEvents(at_(from, '00:00'), at_(addDays_(until, 1), '00:00')).forEach(function (ev) {
        const tag = ev.getTag(ROT_TAG);
        // เวรที่แลกผ่าน LINE (ป้าย swap:) ในช่วงที่ต้องจัดคิวใหม่: ลบทิ้ง แล้วลงตามคิวใหม่ — ต้องแลกกันใหม่
        if (tag === 'swap:rot:' + rot.key) { ev.deleteEvent(); removed++; return; }
        if (tag !== 'rot:' + rot.key || ev.isAllDayEvent()) return;
        const k = ymd_(ev.getStartTime()) + '|' + ev.getTitle();
        const w = want[k];
        if (w && w.name === name && !w.found && hm_(ev.getStartTime()) === w.task.start && hm_(ev.getEndTime()) === w.task.end) { w.found = true; kept++; }
        else { ev.deleteEvent(); removed++; }
      });
    });
    Object.keys(want).sort().forEach(function (k) {
      const w = want[k];
      if (w.found) return;
      const ev = CalendarApp.getCalendarById(ids[w.name]).createEvent(w.task.title, at_(w.date, w.task.start), at_(w.date, w.task.end));
      // ป้ายคือสิ่งเดียวที่บอกว่ารายการนี้เป็นของสคริปต์ — ติดไม่สำเร็จให้ลบทิ้ง ไม่ปล่อยรายการไร้ป้ายค้างไว้ (รันซ้ำแล้วจะซ้อน)
      try { ev.setTag(ROT_TAG, 'rot:' + rot.key); }
      catch (e) { try { ev.deleteEvent(); } catch (e2) { /* ลบไม่ได้ก็รายงานข้อผิดพลาดแรก */ } throw new Error('ลงเวรไม่สำเร็จที่ ' + w.date + ' — รันขั้นนี้ซ้ำได้ ปลอดภัย: ' + e.message); }
      created++;
      if (created % 10 === 0) Utilities.sleep(1000);   // เว้นจังหวะ กัน Google ตัดเพราะเรียกถี่เกิน
    });
    state[rot.key] = { cfg: cfgSig, hol: Object.keys(holSet).sort(), until: until };
    setJson_(PROP.ROTATION, state);
    console.log('เวรวน "' + rot.key + '" ตั้งแต่ ' + thaiDate_(from, { short: true }) + ': ลงใหม่ ' + created + ' · ลบ ' + removed + ' · คงเดิม ' + kept +
      ' (สัปดาห์ที่ตรงวันหยุดถูกข้าม คนนั้นเลื่อนไปสัปดาห์ถัดไป)');
    rotationPlan_(rot, holSet, from, until).slice(0, 8).forEach(function (p) { console.log('   ' + thaiDate_(p.date, { short: true, year: false }) + ' — ' + p.name); });
  });
}
/** ตั้งให้ตรวจวันหยุดใหม่เองทุกวันที่ 1 (ครม. ประกาศวันหยุดพิเศษระหว่างปีได้) — ไม่ขึ้นกับการตั้งค่า LINE */
function ensureHolidayTrigger_() {
  const has = ScriptApp.getProjectTriggers().some(function (t) { return t.getHandlerFunction() === 'holidayWatch'; });
  if (has) return;
  ScriptApp.newTrigger('holidayWatch').timeBased().atHour(5).everyDays(1).inTimezone(TZ).create();
  console.log('ตั้งให้ตรวจวันหยุดประกาศเพิ่มเองทุกเช้าแล้ว');
}

// ══════════════════════════════════════════════════════════════════════════════
//  ขั้นที่ 4 — แชร์ปฏิทินให้ทุกท่าน (ต้องเปิดบริการ "Google Calendar API" ในเมนู Services ก่อน)
//  ทางเลือก: ไม่รันขั้นนี้ แล้วแชร์เองในหน้า Google Calendar ก็ได้ — ดู README
// ══════════════════════════════════════════════════════════════════════════════
function step4_shareCalendars() {
  checkConfig_(CONFIG);
  if (typeof Calendar === 'undefined' || !Calendar.Acl) {
    throw new Error('ยังไม่ได้เปิดบริการ Google Calendar API: แถบซ้ายของหน้านี้ → Services (+) → Google Calendar API → Add แล้วรันใหม่');
  }
  const targets = CONFIG.people.filter(function (p) { return p.email && p.email.indexOf('@') > 0; });
  if (!targets.length) throw new Error('ยังไม่ได้ใส่ email ใน CONFIG.people — ใส่ Gmail ของแต่ละท่านแล้วรันใหม่ (ของตัวเองไม่ต้องใส่)');
  const me = Session.getEffectiveUser().getEmail().toLowerCase();
  const ids = getJson_(PROP.CAL_IDS, {});
  let n = 0;
  allCalNames_().forEach(function (calShort) {
    if (!ids[calShort]) throw new Error('ยังไม่มีปฏิทิน "' + calName_(calShort) + '" — รัน step1_createCalendars ก่อน');
    targets.forEach(function (p) {
      const email = p.email.trim().toLowerCase();
      if (email === me) return;   // เจ้าของมีสิทธิ์อยู่แล้ว
      const role = CONFIG.deputy === p.name ? 'owner' : 'writer';   // writer = แก้ไขกิจกรรมได้ · owner = จัดการการแชร์ได้ด้วย
      Calendar.Acl.insert({ role: role, scope: { type: 'user', value: email } }, ids[calShort], { sendNotifications: true });
      n++;
    });
  });
  console.log('เสร็จ: แชร์ ' + n + ' รายการ · แต่ละท่านจะได้อีเมลจาก Google ปฏิทินละ 1 ฉบับ ต้องกดลิงก์ในอีเมลเพื่อเพิ่มปฏิทิน');
}

// ══════════════════════════════════════════════════════════════════════════════
//  LINE — อ่านปฏิทิน → จัดข้อความ → ส่ง
// ══════════════════════════════════════════════════════════════════════════════
function isAbsentTitle_(title) {
  const t = String(title || '').trim().toLowerCase();
  if (t === 'ลา') return true;
  return (CONFIG.absentStartsWith || []).some(function (w) { return t.indexOf(w.toLowerCase()) === 0; }) ||
    (CONFIG.absentContains || []).some(function (w) { return t.indexOf(w.toLowerCase()) >= 0; });
}

/** รายการปฏิทินหนึ่งรายการ → ข้อมูลธรรมดาสำหรับวันนั้น (null = ไม่นับในวันนั้น) */
function toItem_(ev, dateYmd, now, routineIds) {
  const title = String(ev.getTitle() || '(ไม่มีชื่อ)').trim();
  const location = String(ev.getLocation() || '').trim();
  const updated = ev.getLastUpdated(), created = ev.getDateCreated();
  const fresh = updated && updated.getTime() > FRESH_SINCE_.t;
  // งานประจำที่เพิ่งถูกสร้างพร้อมกันทั้งชุดไม่นับว่า "ใหม่" — นับเฉพาะที่มีคนแก้ทีหลัง
  const untouchedRoutine = (routineIds[ev.getId()] || ev.getTag(ROT_TAG)) && created && updated && Math.abs(updated.getTime() - created.getTime()) < 5 * 60 * 1000;
  const isNew = !!fresh && !untouchedRoutine;
  if (ev.isAllDayEvent()) {
    const first = ymdAllDay_(ev.getAllDayStartDate());
    const last = addDays_(ymdAllDay_(ev.getAllDayEndDate()), -1);   // วันจบของรายการทั้งวันเป็นวันถัดจากวันสุดท้าย
    if (dateYmd < first || dateYmd > last) return null;
    return { allDay: true, title: title, first: first, last: last, location: location, isNew: isNew };
  }
  const s = ev.getStartTime(), e = ev.getEndTime();
  if (ymd_(s) < dateYmd) {
    // เริ่มก่อนวันนี้: เวรข้ามคืนที่จบเช้านี้ไม่นับซ้ำ — แต่รายการหลายวัน (เช่น ไปประชุม 3 วันแบบมีเวลา) ต้องขึ้นทุกวันที่คร่อม
    const long = e.getTime() - s.getTime() >= 24 * 3600 * 1000;
    if (ymd_(e) > dateYmd) return { allDay: false, cont: 'ต่อเนื่องทั้งวัน', title: title, start: '00:00', end: '', plusDays: 0, location: location, isNew: isNew };
    if (long && ymd_(e) === dateYmd && hm_(e) !== '00:00') return { allDay: false, cont: 'ต่อเนื่องถึง ' + hm_(e), title: title, start: '00:00', end: hm_(e), plusDays: 0, location: location, isNew: isNew };
    return null;
  }
  if (ymd_(s) !== dateYmd) return null;
  return { allDay: false, title: title, start: hm_(s), end: hm_(e), plusDays: daysBetween_(ymd_(s), ymd_(e)), location: location, isNew: isNew };
}

/** อ่านทุกปฏิทินของวันนั้น → { date, holiday, team:[item], people:[{name,dot,items}] } */
const FRESH_SINCE_ = { t: 0 };   // 🆕 = แก้หลังรอบเช้าที่ส่งครั้งก่อน (อย่างน้อย 24 ชม.) — วันที่ไม่ได้ส่งจะไม่ทำให้ของใหม่ตกหล่น
function collectDay_(dateYmd) {
  const lastSent = props_().getProperty(PROP.LAST_MORNING);
  const dayAgo = new Date().getTime() - 24 * 3600 * 1000;
  FRESH_SINCE_.t = lastSent ? Math.min(dayAgo, new Date(lastSent).getTime()) : dayAgo;
  const ids = getJson_(PROP.CAL_IDS, {});
  const made = getJson_(PROP.ROUTINE, {});
  const routineIds = {};
  Object.keys(made).forEach(function (k) { routineIds[made[k].id] = 1; });
  const now = new Date();
  const read = function (shortName) {
    const cal = ids[shortName] ? CalendarApp.getCalendarById(ids[shortName]) : null;
    // เงียบแล้วแสดงว่า "ว่าง" อันตรายกว่าล้มให้เห็น — ปฏิทินหายต้องรู้
    if (!cal) throw new Error('เข้าปฏิทิน "' + calName_(shortName) + '" ไม่ได้ (ถูกลบ หรือยังไม่ได้รัน step1_createCalendars) — ตารางไม่ครบ จึงไม่ส่ง');
    return cal.getEvents(at_(dateYmd, '00:00'), at_(addDays_(dateYmd, 1), '00:00'))
      .map(function (ev) { return toItem_(ev, dateYmd, now, routineIds); })
      .filter(function (x) { return x; })
      .sort(function (a, b) { return (a.allDay === b.allDay ? 0 : a.allDay ? -1 : 1) || String(a.start || '').localeCompare(String(b.start || '')) || a.title.localeCompare(b.title); });
  };
  const hol = getJson_(PROP.HOLIDAYS, []).filter(function (h) { return h.date === dateYmd; })[0];
  return {
    date: dateYmd,
    holiday: hol ? hol.name : null,
    team: read(CONFIG.teamName),
    people: CONFIG.people.map(function (p) { return { name: p.name, dot: dotOf_(p, ids), items: read(p.name) }; })
  };
}
/** จุดสีของคน: ที่กำหนดเองใน CONFIG ก่อน ไม่งั้นตามสีปฏิทินปัจจุบันของเจ้าของ */
function dotOf_(person, ids) {
  if (person.dot) return person.dot;
  const cal = ids[person.name] ? CalendarApp.getCalendarById(ids[person.name]) : null;
  let hex = person.color;
  try { if (cal && cal.getColor()) hex = cal.getColor(); } catch (e) { /* ใช้สีเริ่มต้น */ }
  return dotForHex_(hex);
}

/**
 * รายการในอนาคตที่มีคนเพิ่ม/แก้ตั้งแต่รอบเช้าครั้งก่อน (ไม่รวมของวันนี้ ซึ่งมี 🆕 กำกับในรายการอยู่แล้ว)
 * ตรวจการลบไม่ได้ — รายการที่ถูกลบจะหายไปเฉย ๆ
 */
function collectChanges_(todayYmd, sinceDate) {
  const ids = getJson_(PROP.CAL_IDS, {});
  const made = getJson_(PROP.ROUTINE, {});
  const routineIds = {};
  Object.keys(made).forEach(function (k) { routineIds[made[k].id] = 1; });
  const from = at_(addDays_(todayYmd, 1), '00:00'), to = at_(addDays_(todayYmd, 1 + (CONFIG.line.changesLookAheadDays || 60)), '00:00');
  const out = [];
  const scan = function (shortName, dot) {
    const cal = ids[shortName] ? CalendarApp.getCalendarById(ids[shortName]) : null;
    if (!cal) return;
    const seen = {};
    cal.getEvents(from, to).forEach(function (ev) {
      const upd = ev.getLastUpdated(), cre = ev.getDateCreated();
      if (!upd || upd.getTime() <= sinceDate.getTime()) return;
      const id = ev.getId();
      if ((routineIds[id] || ev.getTag(ROT_TAG)) && cre && Math.abs(upd.getTime() - cre.getTime()) < 5 * 60 * 1000) return;   // งานประจำ/เวรวนที่ไม่มีใครแตะ
      const allDay = ev.isAllDayEvent();
      const first = allDay ? ymdAllDay_(ev.getAllDayStartDate()) : ymd_(ev.getStartTime());
      const last = allDay ? addDays_(ymdAllDay_(ev.getAllDayEndDate()), -1) : first;
      const key = id + (ev.isRecurringEvent() ? '' : '|' + first);
      if (seen[key]) return;   // รายการซ้ำรายสัปดาห์ขึ้นครั้งเดียว
      seen[key] = 1;
      out.push({ who: shortName, dot: dot, title: String(ev.getTitle() || '(ไม่มีชื่อ)').trim(), first: first, last: last, allDay: allDay,
        start: allDay ? '' : hm_(ev.getStartTime()), end: allDay ? '' : hm_(ev.getEndTime()), recurring: ev.isRecurringEvent() });
    });
  };
  CONFIG.people.forEach(function (p) { scan(p.name, dotOf_(p, ids)); });
  scan(CONFIG.teamName, '👥');
  return out.sort(function (a, b) { return a.first.localeCompare(b.first) || a.who.localeCompare(b.who); });
}
/** → ข้อความส่วน "เพิ่ม/แก้ไขล่าสุด" ('' ถ้าไม่มี) (ฟังก์ชันล้วน) */
function formatChanges_(changes) {
  if (!changes.length) return '';
  const max = 8;
  const lines = ['🆕 เพิ่ม/แก้ไขล่าสุด'];
  changes.slice(0, max).forEach(function (c) {
    const when = c.last > c.first
      ? thaiDate_(c.first, { day: false, year: false }) + '–' + thaiDate_(c.last, { day: false, year: false })
      : thaiDate_(c.first, { short: true, year: false }) + (c.allDay ? '' : ' ' + c.start + '–' + c.end);
    lines.push(c.dot + ' ' + c.who + ' · ' + when + ' ' + c.title + (c.recurring ? ' (รายการซ้ำ)' : ''));
  });
  if (changes.length > max) lines.push('… และอีก ' + (changes.length - max) + ' รายการ ดูในปฏิทิน');
  return lines.join('\n');
}

function itemLabel_(it, dateYmd) {
  let s;
  if (it.allDay) s = 'ทั้งวัน ' + it.title + (it.last > dateYmd ? ' (ถึง ' + thaiDate_(it.last, { short: true, year: false }) + ')' : '');
  else if (it.cont) s = it.cont + ' ' + it.title;
  else s = it.start + '–' + it.end + (it.plusDays > 0 ? ' (+' + it.plusDays + ')' : '') + ' ' + it.title;
  return s + (it.location ? ' @' + it.location : '') + (it.isNew ? ' 🆕' : '');
}

/** ข้อมูลของวัน → ข้อความ (ฟังก์ชันล้วน) · คืน { text, isEmpty } */
function formatDigest_(day, mode) {
  const head = mode === 'tomorrow' ? '🗓 พรุ่งนี้ ' : mode === 'plain' ? '▪️ ' : '📅 วันนี้ ';
  const lines = [head + thaiDate_(day.date, mode === 'plain' ? { short: true, year: false } : {})];
  if (day.holiday) lines.push('🎌 วันหยุดราชการ: ' + day.holiday);
  day.team.forEach(function (it) { lines.push('👥 ' + CONFIG.teamName + ' · ' + itemLabel_(it, day.date)); });

  const away = [];
  let count = day.team.length;
  day.people.forEach(function (p) {
    const absent = p.items.filter(function (it) { return it.allDay && isAbsentTitle_(it.title); });
    const rest = p.items.filter(function (it) { return absent.indexOf(it) < 0; });
    count += p.items.length;
    if (absent.length) {
      away.push(p.dot + ' ' + p.name + ' — ' + absent.map(function (a) {
        return a.title + (a.last > day.date ? ' (ถึง ' + thaiDate_(a.last, { short: true, year: false }) + ')' : '') + (a.isNew ? ' 🆕' : '');
      }).join(' · '));
      if (rest.length) away.push('   ⚠️ ยังมีงานในตาราง: ' + rest.map(function (it) { return itemLabel_(it, day.date); }).join(' · '));
      return;
    }
    if (rest.length === 1) lines.push(p.dot + ' ' + p.name + ' · ' + itemLabel_(rest[0], day.date));
    else if (rest.length > 1) {
      lines.push(p.dot + ' ' + p.name);
      rest.forEach(function (it) { lines.push('   • ' + itemLabel_(it, day.date)); });
    }
  });
  if (away.length) { lines.push('🏖 ไม่อยู่'); away.forEach(function (l) { lines.push(l); }); }
  return { text: lines.join('\n'), isEmpty: count === 0 };
}

function digestText_(offsetDays, mode) { return formatDigest_(collectDay_(addDays_(today_(), offsetDays)), mode); }

function weekText_() {
  const today = today_();
  const parts = ['🗓 7 วันข้างหน้า'];
  for (let i = 0; i < 7; i++) {
    const d = formatDigest_(collectDay_(addDays_(today, i)), 'plain');
    if (!d.isEmpty || d.text.indexOf('🎌') >= 0) parts.push(d.text);
  }
  return parts.length > 1 ? parts.join('\n\n') : '🗓 7 วันข้างหน้า — ยังไม่มีรายการ';
}

// ── เรียก LINE ────────────────────────────────────────────────────────────────
function lineCall_(method, path, body) {
  const token = props_().getProperty(PROP.TOKEN);
  if (!token) throw new Error('ยังไม่ได้ใส่ LINE_TOKEN ใน Project Settings → Script properties (ดู README ขั้น LINE)');
  const opt = { method: method, headers: { Authorization: 'Bearer ' + token }, muteHttpExceptions: true };
  if (body) { opt.contentType = 'application/json'; opt.payload = JSON.stringify(body); }
  const res = UrlFetchApp.fetch(LINE_API + path, opt);
  const code = res.getResponseCode();
  let json = {};
  try { json = JSON.parse(res.getContentText() || '{}'); } catch (e) { json = {}; }
  return { code: code, json: json, text: res.getContentText() };
}
function clip_(text) {
  if (text.length <= 4900) return text;
  return Array.from(text).slice(0, 4400).join('') + '\n… (ยาวเกิน ดูต่อในปฏิทิน)';   // ตัดทีละตัวอักษรเต็ม ไม่ผ่ากลาง emoji
}
/** ส่งเข้ากลุ่ม · คืน true ถ้าส่งแล้ว false ถ้าโควตาหมด · ผิดพลาดอย่างอื่น throw (Google จะส่งอีเมลแจ้งเจ้าของ) */
function linePush_(text) {
  const group = props_().getProperty(PROP.GROUP);
  if (!group) throw new Error('ยังไม่ได้เชื่อมกลุ่ม LINE — เชิญบอทเข้ากลุ่มแล้วพิมพ์ "เชื่อมปฏิทิน <รหัสจากขั้นที่ 5>" (ดู README)');
  const token = props_().getProperty(PROP.TOKEN);
  if (!token) throw new Error('ยังไม่ได้ใส่ LINE_TOKEN ใน Project Settings → Script properties (ดู README ขั้น LINE)');
  // กุญแจกันส่งซ้ำ: ถ้าครั้งแรกส่งถึงแล้วแต่เราไม่ได้คำตอบ การลองใหม่ด้วยกุญแจเดิมจะไม่ถูกนับโควตาซ้ำ (LINE ตอบ 409)
  const retryKey = Utilities.getUuid();
  const send = function () {
    return UrlFetchApp.fetch(LINE_API + '/message/push', {
      method: 'post', contentType: 'application/json', muteHttpExceptions: true,
      headers: { Authorization: 'Bearer ' + token, 'X-Line-Retry-Key': retryKey },
      payload: JSON.stringify({ to: group, messages: [{ type: 'text', text: clip_(text) }] })
    });
  };
  let code = 0, body = '';
  for (let attempt = 0; attempt < 2; attempt++) {
    try { const res = send(); code = res.getResponseCode(); body = res.getContentText(); }
    catch (e) { code = 0; body = String(e && e.message); }
    if (code === 200 || code === 409) return true;
    if (code !== 0 && code < 500) break;   // 4xx ไม่ลองใหม่
    Utilities.sleep(1500);
  }
  if (code === 429 && !/monthly limit/i.test(body)) throw new Error('LINE ปฏิเสธเพราะเรียกถี่เกิน (HTTP 429 ไม่ใช่โควตาเดือน): ' + body);
  if (code === 429) {   // โควตาข้อความฟรีของเดือนนี้หมด — ไม่ถือว่าสคริปต์พัง
    console.warn('LINE แจ้งว่าโควตาข้อความของเดือนนี้หมดแล้ว — ข้ามการส่งครั้งนี้ (ยังพิมพ์ "วันนี้" ในกลุ่มให้บอทตอบได้): ' + body);
    return false;
  }
  throw new Error('ส่งเข้า LINE ไม่ได้ (HTTP ' + code + '): ' + body +
    (code === 400 ? ' — มักแปลว่าบอทไม่ได้อยู่ในกลุ่มแล้ว หรือ group ID ผิด (รัน resetLineGroup แล้วเชื่อมใหม่)' : ''));
}
function lineReply_(replyToken, text) {
  const r = lineCall_('post', '/message/reply', { replyToken: replyToken, messages: [{ type: 'text', text: clip_(text) }] });
  if (r.code !== 200) console.warn('ตอบกลับ LINE ไม่ได้ HTTP ' + r.code + ': ' + r.text);
}

/** โควตาที่เหลือของเดือนนี้ · คืน { limited, remaining, perPush } — อ่านไม่ได้ให้ถือว่าไม่จำกัด (ปล่อยให้ LINE ตัดสินตอนส่ง) */
function lineBudget_() {
  try {
    const q = lineCall_('get', '/message/quota');
    if (q.code !== 200 || q.json.type !== 'limited') return { limited: false, remaining: Infinity, perPush: 0 };
    const used = lineCall_('get', '/message/quota/consumption');
    const cnt = lineCall_('get', '/group/' + props_().getProperty(PROP.GROUP) + '/members/count');
    if (used.code !== 200 || cnt.code !== 200) return { limited: false, remaining: Infinity, perPush: 0 };
    return { limited: true, remaining: Number(q.json.value) - Number(used.json.totalUsage), perPush: Math.max(1, Number(cnt.json.count) || 1) };
  } catch (e) {
    console.warn('อ่านโควตา LINE ไม่ได้: ' + e.message);
    return { limited: false, remaining: Infinity, perPush: 0 };
  }
}
/** ตัดสินว่าส่งรอบนี้ได้ไหม (ฟังก์ชันล้วน) — รอบเย็นต้องเหลือพอให้รอบเช้าของวันทำการที่เหลือในเดือนก่อน */
function canAfford_(budget, mode, todayYmd) {
  if (!budget.limited) return { ok: true, why: '' };
  if (budget.remaining < budget.perPush) return { ok: false, why: 'โควตา LINE เดือนนี้เหลือ ' + budget.remaining + ' ไม่พอส่ง (ครั้งละ ' + budget.perPush + ')' };
  if (mode === 'tomorrow') {
    const reserve = budget.perPush * (weekdaysLeftInMonth_(todayYmd) + 2);
    if (budget.remaining - budget.perPush < reserve) return { ok: false, why: 'งดรอบเย็นเพื่อเก็บโควตาไว้ให้รอบเช้า (เหลือ ' + budget.remaining + ' · กันไว้ ' + reserve + ')' };
  }
  return { ok: true, why: '' };
}

function sendDigest_(offsetDays, mode) {
  if (props_().getProperty(PROP.TOKEN) && !props_().getProperty(PROP.GROUP) && ScriptApp.getProjectTriggers().some(function (t) { return t.getHandlerFunction() === 'sendMorning'; }) && props_().getProperty(PROP.LAST_MORNING)) {
    console.warn('ไม่มีกลุ่ม LINE ที่เชื่อมไว้ (บอทอาจถูกนำออกจากกลุ่ม) — ไม่ส่ง · รัน resetLineGroup เพื่อเชื่อมใหม่'); return;
  }
  if (!props_().getProperty(PROP.GROUP)) throw new Error('ยังไม่ได้เชื่อมกลุ่ม LINE — เชิญบอทเข้ากลุ่มแล้วพิมพ์ "เชื่อมปฏิทิน <รหัสจากขั้นที่ 5>" (ดู README)');
  const today = today_();
  const d = digestText_(offsetDays, mode);
  if (d.isEmpty && CONFIG.line.skipEmptyDays && !(mode === 'today' && props_().getProperty(PROP.NOTICE))) { console.log('ไม่มีรายการ — ไม่ส่ง'); return; }
  let text = d.text;
  const notice = mode === 'today' ? props_().getProperty(PROP.NOTICE) : null;
  if (notice) text = notice + '\n\n' + text;
  const startedAt = new Date();
  if (mode === 'today') {
    const last = props_().getProperty(PROP.LAST_MORNING);
    const since = last ? new Date(last) : new Date(startedAt.getTime() - 24 * 3600 * 1000);
    const ch = formatChanges_(collectChanges_(today, since));
    if (ch) text += '\n\n' + ch;
  }
  const afford = canAfford_(lineBudget_(), mode, today);
  if (!afford.ok) { console.warn(afford.why + ' — ไม่ส่ง'); return; }
  if (linePush_(text)) {
    if (mode === 'today') props_().setProperty(PROP.LAST_MORNING, startedAt.toISOString());
    if (notice) props_().deleteProperty(PROP.NOTICE);
    console.log('ส่งแล้ว:\n' + text);
  }
}
/** ตัวตั้งเวลาเรียกสองฟังก์ชันนี้ */
function sendMorning() { sendDigest_(0, 'today'); }
function sendEvening() { sendDigest_(1, 'tomorrow'); }

// ── ปุ่มทดสอบ (เลือกแล้วกด Run) ─────────────────────────────────────────────────
function previewToday() { console.log(digestText_(0, 'today').text); }
function previewTomorrow() { console.log(digestText_(1, 'tomorrow').text); }
function previewWeek() { console.log(weekText_()); }
function sendTestToLine() { if (linePush_('✅ ทดสอบจากปฏิทินสายฟ้า\n\n' + digestText_(0, 'today').text)) console.log('ส่งข้อความทดสอบเข้ากลุ่มแล้ว'); }

// ══════════════════════════════════════════════════════════════════════════════
//  ขั้นที่ 5 — เตรียม LINE: ตรวจ token + ออกกุญแจของ webhook
// ══════════════════════════════════════════════════════════════════════════════
function step5_prepareLine() {
  const info = lineCall_('get', '/info');
  if (info.code !== 200) throw new Error('LINE_TOKEN ใช้ไม่ได้ (HTTP ' + info.code + ') — ตรวจว่าคัดลอก Channel access token มาครบ: ' + info.text);
  let key = props_().getProperty(PROP.HOOK_KEY);
  if (!key) { key = Utilities.getUuid().replace(/-/g, ''); props_().setProperty(PROP.HOOK_KEY, key); }
  console.log('✅ token ใช้ได้ — บอท: ' + (info.json.displayName || '?') + ' (' + (info.json.basicId || '?') + ')');
  console.log('ต่อไป: Deploy → New deployment → Web app แล้วนำ URL ที่ได้ (ลงท้าย /exec) ต่อท้ายด้วยข้อความข้างล่างนี้ ไปใส่เป็น Webhook URL ใน LINE:');
  console.log('?k=' + key);
  if (props_().getProperty(PROP.GROUP)) console.log('เชื่อมกลุ่มไว้แล้ว (ย้ายกลุ่ม: รัน resetLineGroup)');
  else console.log('หลังตั้ง Webhook และเชิญบอทเข้ากลุ่มแล้ว ให้พิมพ์ข้อความนี้ในกลุ่มเพื่อเชื่อม (ใช้ได้ครั้งเดียว):  ' + LINK_WORD + ' ' + newLinkCode_());
  checkLineQuota();
}
const LINK_WORD = 'เชื่อมปฏิทิน';
function newLinkCode_() {
  const code = String(Math.floor(Math.random() * 900000) + 100000);
  props_().setProperty(PROP.LINK_CODE, code);
  return code;
}
function checkLineQuota() {
  const q = lineCall_('get', '/message/quota'), used = lineCall_('get', '/message/quota/consumption');
  if (q.code !== 200 || used.code !== 200) { console.log('อ่านโควตาไม่ได้: ' + q.text + ' ' + used.text); return; }
  if (q.json.type !== 'limited') { console.log('โควตาข้อความ: ไม่จำกัด'); return; }
  let line = 'โควตาข้อความเดือนนี้: ใช้ไป ' + used.json.totalUsage + ' จาก ' + q.json.value;
  const group = props_().getProperty(PROP.GROUP);
  if (group) {
    const cnt = lineCall_('get', '/group/' + group + '/members/count');
    if (cnt.code === 200) {
      const per = Number(cnt.json.count);
      line += ' · กลุ่มมี ' + per + ' คน = ส่งครั้งละ ' + per + ' ข้อความ → ส่งได้อีก ' + Math.floor((q.json.value - used.json.totalUsage) / Math.max(1, per)) + ' ครั้งในเดือนนี้';
    }
  }
  console.log(line);
}
/** ดูว่าสคริปต์เห็นปฏิทินอะไรบ้าง สีอะไร (ใช้ตรวจตอนมีปัญหา) */
function listCalendars() {
  const ids = getJson_(PROP.CAL_IDS, {});
  allCalNames_().forEach(function (n) {
    const cal = ids[n] ? CalendarApp.getCalendarById(ids[n]) : null;
    console.log(cal ? calName_(n) + ' · สี ' + cal.getColor() + ' ' + dotForHex_(cal.getColor()) + ' · เขตเวลา ' + cal.getTimeZone() : calName_(n) + ' — ไม่พบ (รัน step1_createCalendars)');
  });
}
/** ถ้าต้องการย้ายไปกลุ่มอื่น: รันฟังก์ชันนี้ แล้วเชิญบอทเข้ากลุ่มใหม่และพิมพ์ข้อความ 1 ครั้ง */
function resetLineGroup() {
  props_().deleteProperty(PROP.GROUP);
  console.log('ล้างกลุ่มที่เชื่อมไว้แล้ว · เชิญบอทเข้ากลุ่มใหม่ แล้วพิมพ์ในกลุ่มนั้น:  ' + LINK_WORD + ' ' + newLinkCode_());
}

// ══════════════════════════════════════════════════════════════════════════════
//  Webhook ของ LINE — ใช้ (1) จำกลุ่มให้เองตอนเชิญบอท (2) ตอบเมื่อมีคนพิมพ์ "วันนี้" "พรุ่งนี้" "สัปดาห์นี้"
//  ข้อความอื่นในกลุ่มถูกทิ้งทันที ไม่บันทึก ไม่เก็บ
// ══════════════════════════════════════════════════════════════════════════════
const COMMANDS = {
  'วันนี้':     function () { return digestText_(0, 'today').text; },
  'พรุ่งนี้':   function () { return digestText_(1, 'tomorrow').text; },
  'สัปดาห์นี้': function () { return weekText_(); },
  'ปฏิทิน':    function () { return 'พิมพ์คำใดคำหนึ่งนี้ในกลุ่ม:\n• วันนี้\n• พรุ่งนี้\n• สัปดาห์นี้\n• แลกเวร 2 ธ.ค. มานิตา ชนกันต์\n• แลกเวร 2 ธ.ค. มานิตา 9 ธ.ค. ศุภศักดิ์\n   (อีกฝ่ายต้องพิมพ์ ตกลง ก่อนจึงย้าย)\n• ฉันคือ <ชื่อ>  (ครั้งเดียว ให้ระบบรู้ว่าใครเป็นใคร)\n\nเพิ่ม/แก้งาน วันลา ประชุม ได้ในแอปปฏิทินของเครื่อง (ปฏิทินชื่อขึ้นต้นว่า ' + CONFIG.prefix + ')'; }
};

// ── แลกเวรผ่าน LINE ─────────────────────────────────────────────────────────────
//   แลกเวร 2 ธ.ค. มานิตา ชนกันต์              → วันนั้น เวรของสองท่านสลับกัน (ท่านที่ไม่มีเวรวันนั้น = มาอยู่แทนเฉย ๆ)
//   แลกเวร 2 ธ.ค. มานิตา 9 ธ.ค. ศุภศักดิ์      → เวร 2 ธ.ค. ของมานิตา ↔ เวร 9 ธ.ค. ของศุภศักดิ์
// ย้ายเฉพาะ "เวร/งานประจำที่สคริปต์ลงให้" (ER, OPD ปกส., OPD พฤหัส, OR, OPD) — วันลา ประชุม งานที่ลงเองไม่ถูกแตะ
const SWAP_WORD = 'แลกเวร';
const TH_MONTH_KEYS = ['มค', 'กพ', 'มีค', 'เมย', 'พค', 'มิย', 'กค', 'สค', 'กย', 'ตค', 'พย', 'ธค'];
const DATE_RE_SRC = '(\\d{4}-\\d{2}-\\d{2}|\\d{1,2}/\\d{1,2}(?:/\\d{2,4})?|\\d{1,2}\\s*(?:ม\\.?ค\\.?|ก\\.?พ\\.?|มี\\.?ค\\.?|เม\\.?ย\\.?|พ\\.?ค\\.?|มิ\\.?ย\\.?|ก\\.?ค\\.?|ส\\.?ค\\.?|ก\\.?ย\\.?|ต\\.?ค\\.?|พ\\.?ย\\.?|ธ\\.?ค\\.?)(?:\\s*\\d{2,4})?)';

/** "2 ธ.ค." "2 ธค 70" "2/12" "2/12/2569" "2026-12-02" → 'yyyy-MM-dd' หรือ null · ไม่ใส่ปี = วันนั้นครั้งถัดไปนับจากวันนี้ (ฟังก์ชันล้วน) */
function parseThaiDate_(text, todayYmd) {
  const t = String(text).trim();
  if (isYmd_(t)) return t;
  let d, m, y = null, mm;
  if ((mm = /^(\d{1,2})\/(\d{1,2})(?:\/(\d{2,4}))?$/.exec(t))) { d = Number(mm[1]); m = Number(mm[2]); y = mm[3] || null; }
  else if ((mm = /^(\d{1,2})\s*([^\d\s]+?)(?:\s*(\d{2,4}))?$/.exec(t))) {
    d = Number(mm[1]); m = TH_MONTH_KEYS.indexOf(mm[2].replace(/\./g, '')) + 1; y = mm[3] || null;
  } else return null;
  if (!(m >= 1 && m <= 12)) return null;
  const pad = function (n) { return ('0' + n).slice(-2); };
  if (y !== null) {
    let yy = Number(y);
    if (yy < 100) yy += 2500;        // 69 → 2569
    if (yy > 2400) yy -= 543;        // พ.ศ. → ค.ศ.
    const out = yy + '-' + pad(m) + '-' + pad(d);
    return isYmd_(out) ? out : null;
  }
  const thisYear = Number(todayYmd.slice(0, 4));
  for (let k = 0; k < 2; k++) {
    const out = (thisYear + k) + '-' + pad(m) + '-' + pad(d);
    if (isYmd_(out) && out >= todayYmd) return out;
  }
  return null;
}
/** แยกคำสั่ง → { d1, a, d2, b } หรือ { error } (ฟังก์ชันล้วน) */
function parseSwap_(text, todayYmd, names) {
  const t = String(text).replace(/\s+/g, ' ').trim();
  const usage = 'พิมพ์แบบนี้:\n• ' + SWAP_WORD + ' 2 ธ.ค. มานิตา ชนกันต์\n   (วันเดียวกัน สลับเวรของสองท่าน หรืออยู่แทน)\n• ' + SWAP_WORD + ' 2 ธ.ค. มานิตา 9 ธ.ค. ศุภศักดิ์\n   (เวรคนละวัน แลกกัน)';
  let m = new RegExp('^' + SWAP_WORD + ' ' + DATE_RE_SRC + ' (\\S+) ' + DATE_RE_SRC + ' (\\S+)$').exec(t);
  let r;
  if (m) r = { d1: m[1], a: m[2], d2: m[3], b: m[4] };
  else if ((m = new RegExp('^' + SWAP_WORD + ' ' + DATE_RE_SRC + ' (\\S+) (\\S+)$').exec(t))) r = { d1: m[1], a: m[2], d2: m[1], b: m[3] };
  else return { error: usage };
  r.d1 = parseThaiDate_(r.d1, todayYmd); r.d2 = parseThaiDate_(r.d2, todayYmd);
  if (!r.d1 || !r.d2) return { error: 'อ่านวันที่ไม่ออก หรือเป็นวันที่ผ่านไปแล้ว\n' + usage };
  if (r.d1 < todayYmd || r.d2 < todayYmd) return { error: 'แลกได้เฉพาะวันนี้หรือวันข้างหน้า' };
  const bad = [r.a, r.b].filter(function (n) { return names.indexOf(n) < 0; });
  if (bad.length) return { error: 'ไม่รู้จักชื่อ "' + bad.join('", "') + '" — ใช้ชื่อตามปฏิทิน: ' + names.join(', ') };
  if (r.a === r.b) return { error: 'ชื่อสองท่านต้องไม่ซ้ำกัน' };
  return r;
}
/** เวร/งานประจำที่สคริปต์ลงให้ ของคนนั้นในวันนั้น */
function dutiesOn_(name, ymd, ids, routineIds) {
  const cal = ids[name] ? CalendarApp.getCalendarById(ids[name]) : null;
  if (!cal) throw new Error('เข้าปฏิทิน "' + calName_(name) + '" ไม่ได้');
  return cal.getEvents(at_(ymd, '00:00'), at_(addDays_(ymd, 1), '00:00')).filter(function (ev) {
    if (ev.isAllDayEvent() || ymd_(ev.getStartTime()) !== ymd) return false;
    return !!ev.getTag(ROT_TAG) || !!routineIds[ev.getId()];
  });
}
function moveDuties_(events, toName, ids) {
  const toCal = CalendarApp.getCalendarById(ids[toName]);
  if (!toCal) throw new Error('เข้าปฏิทิน "' + calName_(toName) + '" ไม่ได้');
  return events.map(function (ev) {
    const tag = ev.getTag(ROT_TAG);
    const origin = !tag ? 'routine' : tag.indexOf('swap:') === 0 ? tag.slice(5) : tag;
    // ลงของใหม่ก่อน แล้วค่อยลบของเดิม — ถ้าล้มกลางทาง เวรไม่หาย (อย่างมากซ้ำ ซึ่งเห็นได้)
    const made = toCal.createEvent(ev.getTitle(), ev.getStartTime(), ev.getEndTime(), ev.getLocation() ? { location: ev.getLocation() } : {});
    made.setTag(ROT_TAG, 'swap:' + origin);
    const label = hm_(ev.getStartTime()) + '–' + hm_(ev.getEndTime()) + ' ' + ev.getTitle();
    ev.deleteEvent();   // รายการซ้ำ: ลบเฉพาะวันนั้น
    return label;
  });
}
/** ตรวจคำสั่งและหาเวรที่จะย้าย · คืน { error } หรือ { r, fromA, fromB, ids } */
function planSwap_(text) {
  const today = today_();
  const names = CONFIG.people.map(function (p) { return p.name; });
  const r = parseSwap_(text, today, names);
  if (r.error) return { error: r.error };
  const ids = getJson_(PROP.CAL_IDS, {});
  const made = getJson_(PROP.ROUTINE, {});
  const routineIds = {};
  Object.keys(made).forEach(function (k) { routineIds[made[k].id] = 1; });
  const fromA = dutiesOn_(r.a, r.d1, ids, routineIds), fromB = dutiesOn_(r.b, r.d2, ids, routineIds);
  const day = function (d) { return thaiDate_(d, { short: true, year: false }); };
  if (!fromA.length && !fromB.length) {
    return { error: 'ไม่พบเวรที่ระบบลงให้ ของ' + r.a + ' ' + day(r.d1) + (r.d1 === r.d2 ? ' และ' + r.b : ' และของ' + r.b + ' ' + day(r.d2)) + '\n(งานที่ลงเองในปฏิทิน ให้ย้ายเองในแอป)' };
  }
  if (r.d1 !== r.d2 && (!fromA.length || !fromB.length)) {
    const none = !fromA.length ? r.a + ' ' + day(r.d1) : r.b + ' ' + day(r.d2);
    return { error: none + ' ไม่มีเวรที่ระบบลงให้ จึงแลกสองวันไม่ได้\nถ้าต้องการให้อยู่แทนวันเดียว พิมพ์: ' + SWAP_WORD + ' <วันที่> <ชื่อเดิม> <ชื่อคนแทน>' };
  }
  const label = function (ev) { return hm_(ev.getStartTime()) + '–' + hm_(ev.getEndTime()) + ' ' + ev.getTitle(); };
  const lines = [];
  if (fromA.length) lines.push(day(r.d1) + ' · ' + r.a + ' → ' + r.b + ': ' + fromA.map(label).join(', '));
  if (fromB.length) lines.push(day(r.d2) + ' · ' + r.b + ' → ' + r.a + ': ' + fromB.map(label).join(', '));
  return { r: r, fromA: fromA, fromB: fromB, ids: ids, lines: lines };
}
const SWAP_TTL_MS = 24 * 3600 * 1000;
const YES_WORD = 'ตกลง', NO_WORD = 'ไม่ตกลง', IAM_WORD = 'ฉันคือ';
function pendingSwap_() {
  const p = getJson_(PROP.SWAP_PENDING, null);
  if (!p) return null;
  if (new Date().getTime() - p.at > SWAP_TTL_MS) { props_().deleteProperty(PROP.SWAP_PENDING); return null; }
  return p;
}
/** ขั้นขอ: ยังไม่ย้ายอะไร เก็บคำขอไว้รออีกฝ่ายตอบรับ */
function requestSwap_(text, uid) {
  const old = pendingSwap_();
  if (old) return '⏳ มีคำขอแลกเวรค้างอยู่:\n' + old.lines.join('\n') + '\nให้ ' + old.need.join(' หรือ ') + ' พิมพ์ "' + YES_WORD + '" หรือ "' + NO_WORD + '" ก่อน';
  const p = planSwap_(text);
  if (p.error) return '❌ ' + p.error;
  const who = getJson_(PROP.LINE_USERS, {})[uid || ''];
  // ผู้ต้องตอบรับ = อีกฝ่ายของผู้ขอ · ถ้าไม่รู้ว่าผู้ขอเป็นใคร (ยังไม่ได้พิมพ์ "ฉันคือ …") ให้คนใดคนหนึ่งในสองท่านที่ไม่ใช่ผู้พิมพ์ตอบรับ
  const need = who === p.r.a ? [p.r.b] : who === p.r.b ? [p.r.a] : [p.r.a, p.r.b];
  setJson_(PROP.SWAP_PENDING, { text: text, by: uid || '', byName: who || '', need: need, lines: p.lines, at: new Date().getTime() });
  return '⏳ ขอแลกเวร — ยังไม่ได้ย้าย\n' + p.lines.join('\n') + '\n\nรอ ' + need.join(' หรือ ') + ' พิมพ์ "' + YES_WORD + '" เพื่อตอบรับ หรือ "' + NO_WORD + '" เพื่อยกเลิก (ภายใน 24 ชม.)';
}
/** ขั้นตอบรับ: ต้องเป็นคนละคนกับผู้ขอ และถ้ารู้ชื่อ ต้องเป็นอีกฝ่ายของการแลก */
function answerSwap_(yes, uid) {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(15000)) return '❌ ระบบกำลังทำรายการอื่นอยู่ ลองใหม่อีกครั้ง';
  try {
    const p = pendingSwap_();
    if (!p) return null;   // ไม่มีคำขอค้าง: "ตกลง" เป็นคำคุยธรรมดา ไม่ตอบ
    if (!yes) { props_().deleteProperty(PROP.SWAP_PENDING); return '🚫 ยกเลิกคำขอแลกเวรแล้ว ปฏิทินไม่เปลี่ยน'; }
    const who = getJson_(PROP.LINE_USERS, {})[uid || ''];
    if (uid && p.by && uid === p.by) return '⏳ ผู้ขอแลกตอบรับเองไม่ได้ — รอ ' + p.need.join(' หรือ ') + ' พิมพ์ "' + YES_WORD + '"';
    if (who && p.need.indexOf(who) < 0) return '⏳ ต้องให้ ' + p.need.join(' หรือ ') + ' เป็นผู้ตอบรับ';
    const plan = planSwap_(p.text);   // ตรวจใหม่ ณ ตอนตอบรับ เผื่อปฏิทินเปลี่ยนไประหว่างรอ
    props_().deleteProperty(PROP.SWAP_PENDING);
    if (plan.error) return '❌ แลกไม่ได้แล้ว (ปฏิทินเปลี่ยนไประหว่างรอ): ' + plan.error;
    if (plan.fromA.length) moveDuties_(plan.fromA, plan.r.b, plan.ids);
    if (plan.fromB.length) moveDuties_(plan.fromB, plan.r.a, plan.ids);
    return '✅ แลกเวรแล้ว' + (who ? ' (' + who + ' ตอบรับ)' : '') + '\n' + plan.lines.join('\n') + '\nปฏิทินอัปเดตแล้ว';
  } finally { lock.releaseLock(); }
}
/** "ฉันคือ มานิตา" — จำว่าบัญชี LINE นี้คือใคร เพื่อให้ระบบรู้ว่าใครต้องเป็นผู้ตอบรับ */
function registerUser_(text, uid) {
  const name = text.slice(IAM_WORD.length).trim();
  const names = CONFIG.people.map(function (p) { return p.name; });
  if (names.indexOf(name) < 0) return '❌ ไม่รู้จักชื่อ "' + name + '" — ใช้: ' + names.join(', ');
  if (!uid) return '❌ LINE ไม่ส่งรหัสผู้ใช้มา จึงจำไม่ได้';
  const users = getJson_(PROP.LINE_USERS, {});
  Object.keys(users).forEach(function (k) { if (users[k] === name) delete users[k]; });
  users[uid] = name;
  setJson_(PROP.LINE_USERS, users);
  return '👤 จำแล้ว: บัญชีนี้คือ ' + name;
}

/**
 * ห้ามคืนค่าด้วย ContentService — Apps Script จะตอบเป็น HTTP 302 ซึ่ง LINE นับเป็นข้อผิดพลาด
 * ฟังก์ชันนี้จึงจบโดยไม่คืนค่าอะไร (Apps Script ตอบ 200 ให้เอง)
 */
function doPost(e) {
  try {
    const key = props_().getProperty(PROP.HOOK_KEY);
    if (key && e && e.parameter && e.parameter.k === key && e.postData && e.postData.contents) {
      const body = JSON.parse(e.postData.contents);
      (body.events || []).forEach(function (ev) {
        try { handleLineEvent_(ev); } catch (err) { console.error('webhook event: ' + (err && err.message)); }
      });
    }
  } catch (err) {
    console.error('webhook: ' + (err && err.message));
  }
}
/** เปิด URL ของ web app ในเบราว์เซอร์เพื่อดูว่า deploy แล้วทำงาน */
function doGet() { return HtmlService.createHtmlOutput('ปฏิทิน' + CONFIG.prefix + ': พร้อมใช้งาน'); }

function handleLineEvent_(ev) {
  if (!ev || (ev.mode && ev.mode !== 'active')) return;
  const src = ev.source || {};
  if (src.type !== 'group' || !/^C[0-9a-f]{32}$/.test(String(src.groupId || ''))) return;   // ใช้ในกลุ่มเท่านั้น
  if (ev.webhookEventId) {   // กันเหตุการณ์เดียวกันถูกส่งซ้ำ
    const cache = CacheService.getScriptCache();
    if (cache.get('ev' + ev.webhookEventId)) return;
    cache.put('ev' + ev.webhookEventId, '1', 600);
  }
  let linked = props_().getProperty(PROP.GROUP);
  if (!linked) {
    // เชื่อมได้เฉพาะเมื่อมีคนพิมพ์ "เชื่อมปฏิทิน <รหัส 6 หลัก>" ในกลุ่ม — รหัสอยู่ใน log ของเจ้าของเท่านั้น
    // กลุ่มอื่นที่บอทถูกเชิญเข้าไปก่อนจึงเชื่อมไม่ได้ และตารางจะไม่ไปออกผิดกลุ่ม
    const code = props_().getProperty(PROP.LINK_CODE);
    if (!code || ev.type !== 'message' || !ev.message || ev.message.type !== 'text') return;
    if (String(ev.message.text || '').replace(/\s+/g, ' ').trim() !== LINK_WORD + ' ' + code) return;
    // ยืนยันกับ LINE ว่าบอทอยู่ในกลุ่มนี้จริงก่อนจำ — กันคำขอปลอมที่แอบอ้าง group ID
    if (lineCall_('get', '/group/' + src.groupId + '/summary').code !== 200) return;
    const lock = LockService.getScriptLock();
    if (!lock.tryLock(8000)) return;
    try {
      linked = props_().getProperty(PROP.GROUP);
      if (!linked) {
        props_().setProperty(PROP.GROUP, src.groupId);
        props_().deleteProperty(PROP.LINK_CODE);   // รหัสใช้ได้ครั้งเดียว
        if (ev.replyToken) lineReply_(ev.replyToken, '✅ เชื่อมกลุ่มนี้กับปฏิทิน' + CONFIG.prefix + 'แล้ว\n\n' + COMMANDS['ปฏิทิน']());
        return;
      }
    } finally { lock.releaseLock(); }
  }
  if (src.groupId !== linked) return;                 // กลุ่มอื่นที่ไม่ได้เชื่อมไว้ — ไม่ตอบ
  if (ev.type === 'leave') {                          // บอทถูกเอาออกจากกลุ่มที่เชื่อมไว้: หยุดส่ง ไม่ปล่อยให้ล้มทุกเช้า
    props_().deleteProperty(PROP.GROUP);
    console.warn('บอทถูกนำออกจากกลุ่ม LINE ที่เชื่อมไว้ — หยุดส่งจนกว่าจะเชื่อมกลุ่มใหม่ (รัน resetLineGroup เพื่อรับรหัส)');
    return;
  }
  if (!CONFIG.line.replyCommands) return;
  if (ev.type !== 'message' || !ev.message || ev.message.type !== 'text' || !ev.replyToken) return;
  const said = String(ev.message.text || '').trim();
  const uid = src.userId || '';
  let out = null, handled = true;
  try {
    if (said.indexOf(SWAP_WORD) === 0) out = requestSwap_(said, uid);          // ขอแลก — ยังไม่ย้าย
    else if (said === YES_WORD) out = answerSwap_(true, uid);                  // อีกฝ่ายตอบรับ — ย้ายจริง
    else if (said === NO_WORD) out = answerSwap_(false, uid);
    else if (said.indexOf(IAM_WORD + ' ') === 0) out = registerUser_(said, uid);
    else handled = false;
  } catch (err) { out = '❌ ทำรายการไม่สำเร็จ: ' + (err && err.message); }
  if (handled) { if (out) lineReply_(ev.replyToken, out); return; }
  const cmd = COMMANDS[said];
  if (cmd) lineReply_(ev.replyToken, cmd());           // ข้อความอื่นถูกทิ้ง ไม่บันทึก
}

// ══════════════════════════════════════════════════════════════════════════════
//  ขั้นที่ 6 — เปิดการส่ง LINE อัตโนมัติทุกวัน (รันซ้ำได้)
// ══════════════════════════════════════════════════════════════════════════════
function step6_startDailyLine() {
  // ตรวจก่อนสร้างตัวตั้งเวลา — ถ้าเปิดทั้งที่ LINE ยังไม่พร้อม จะได้อีเมลแจ้งล้มเหลวทุกวัน
  if (!props_().getProperty(PROP.TOKEN)) throw new Error('ยังไม่ได้ใส่ LINE_TOKEN — ทำขั้นที่ 5 ก่อน');
  if (!props_().getProperty(PROP.GROUP)) throw new Error('ยังไม่ได้เชื่อมกลุ่ม LINE — เชิญบอทเข้ากลุ่มแล้วพิมพ์ "เชื่อมปฏิทิน <รหัสจากขั้นที่ 5>" จนบอทตอบว่าเชื่อมแล้วก่อน');
  const mine = { sendMorning: 1, sendEvening: 1 };
  ScriptApp.getProjectTriggers().forEach(function (t) { if (mine[t.getHandlerFunction()]) ScriptApp.deleteTrigger(t); });
  const m = CONFIG.line.morning, ev = CONFIG.line.evening;
  const pad = function (n) { return ('0' + n).slice(-2); };
  let msg = 'เปิดแล้ว:';
  if (m) { ScriptApp.newTrigger('sendMorning').timeBased().atHour(m.hour).nearMinute(m.minute).everyDays(1).inTimezone(TZ).create(); msg += ' งานวันนี้ราว ' + m.hour + ':' + pad(m.minute) + ' น. ·'; }
  if (ev) { ScriptApp.newTrigger('sendEvening').timeBased().atHour(ev.hour).nearMinute(ev.minute).everyDays(1).inTimezone(TZ).create(); msg += ' งานพรุ่งนี้ราว ' + ev.hour + ':' + pad(ev.minute) + ' น. ·'; }
  ensureHolidayTrigger_();
  console.log(msg + ' (เวลาคลาดได้ ±15 นาที)');
  try { checkLineQuota(); } catch (e) { console.warn('อ่านโควตาไม่ได้: ' + e.message); }
}
function stopDailyLine() {
  const mine = { sendMorning: 1, sendEvening: 1 };
  ScriptApp.getProjectTriggers().forEach(function (t) { if (mine[t.getHandlerFunction()]) ScriptApp.deleteTrigger(t); });
  console.log('หยุดการส่ง LINE อัตโนมัติแล้ว');
}
