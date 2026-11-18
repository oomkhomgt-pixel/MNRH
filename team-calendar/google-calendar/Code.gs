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
  rotations: [
    { key: 'wed', day: 'WE', firstDate: '2026-11-25', skipHolidays: true,
      order: ['มานิตา', 'ศุภศักดิ์', 'คงธัช', 'อดิศร', 'ชนกันต์'],
      tasks: [
        { title: 'ER',       start: '08:00', end: '16:00' },
        { title: 'OPD ปกส.', start: '13:00', end: '15:00' }
      ] }
  ],

  // ── วันหยุดราชการ ───────────────────────────────────────────────────────────
  // ดึงจากปฏิทิน "วันหยุดในไทย" ของ Google (เฉพาะที่ระบุว่า วันหยุดนักขัตฤกษ์ รวมวันหยุดชดเชยและวันหยุดพิเศษ)
  // รายการของ Google ไม่ตรงกับวันหยุดราชการทุกวัน สคริปต์จึงปรับให้ 2 อย่าง: ตัดวันที่ชื่อมีคำใน notHolidayNames
  // และเติม "วันเข้าพรรษา" (วันถัดจากอาสาฬหบูชา ซึ่ง Google ไม่มี) — ที่เหลือให้ตรวจรายการใน log แล้วแก้สองบรรทัดล่างนี้
  notHolidayNames: ['วันแรงงาน'],   // ราชการไม่หยุดวันแรงงาน
  extraHolidays: [],         // เพิ่มเอง เช่น [{ date: '2027-07-20', name: 'ชดเชยวันอาสาฬหบูชา' }]
  notHolidays: [],           // วันที่ไม่หยุดจริง เช่น ['2026-12-31']

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
  absentStartsWith: ['ลา'],
  absentContains: ['ประชุม', 'อบรม', 'สัมมนา', 'ดูงาน', 'conference', 'meeting', 'leave']
};

// ══════════════════════════════════════════════════════════════════════════════
//  ส่วนที่ 2 — ไม่ต้องแก้
// ══════════════════════════════════════════════════════════════════════════════
const TZ = 'Asia/Bangkok';
const TZ_OFFSET = '+07:00';   // ไทยไม่มี daylight saving
const PROP = {
  CAL_IDS: 'CAL_IDS', ROUTINE: 'ROUTINE_SERIES', HOLIDAYS: 'HOLIDAYS',
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
  (cfg.rotations || []).forEach(function (r) {
    const n = r.order.length;
    r.order.forEach(function (name, i) {
      // วันของคนที่ i = firstDate + 7·(i + n·k) — หา k น้อยสุดที่ไม่ก่อนวันเริ่ม
      let first = addDays_(r.firstDate, 7 * i);
      while (first < from) first = addDays_(first, 7 * n);
      if (first > cfg.routineUntil) return;
      r.tasks.forEach(function (t, j) {
        out.push({ key: r.key + '.' + j + '|' + name, calendar: name, title: t.title, first: first, start: t.start, end: t.end,
          intervalWeeks: n, until: cfg.routineUntil, skipHolidays: r.skipHolidays !== false, location: t.location || '' });
      });
    });
  });
  return out;
}

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
    try { cal.setColor(w.color); } catch (e) { console.warn('ตั้งสี ' + full + ' ไม่ได้: ' + e.message); }
    ids[w.name] = cal.getId();
    console.log('✅ ' + full + ' — ' + how);
  });
  setJson_(PROP.CAL_IDS, ids);
  console.log('เสร็จ: ปฏิทิน ' + wanted.length + ' อัน · ต่อไปรัน step2_createRoutine');
}

// ══════════════════════════════════════════════════════════════════════════════
//  ขั้นที่ 2 — ลงงานประจำเป็นรายการซ้ำ (รันซ้ำได้: ชุดที่สร้างแล้วจะถูกข้าม)
//  หลังจากนี้ การเปลี่ยนงานประจำให้แก้ในแอปปฏิทินได้เลย (เลือก "รายการนี้และรายการต่อจากนี้")
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
  console.log('เสร็จ: สร้าง ' + created + ' ชุด · ข้าม (มีแล้ว) ' + skipped + ' ชุด · ต่อไปรัน step3_syncHolidays');
}

// ══════════════════════════════════════════════════════════════════════════════
//  ขั้นที่ 3 — ตัดงานประจำออกในวันหยุดราชการ (รันซ้ำได้ · ตั้งให้รันเองทุกเดือนในขั้นที่ 6)
// ══════════════════════════════════════════════════════════════════════════════
/** อ่านไฟล์ปฏิทินวันหยุดของ Google → [{date, name}] เฉพาะ "วันหยุดนักขัตฤกษ์" (ฟังก์ชันล้วน) */
function parseHolidayIcs_(text) {
  const out = [];
  const unfolded = String(text).replace(/\r\n[ \t]/g, '').replace(/\r\n/g, '\n');
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
function step3_syncHolidays() {
  checkConfig_(CONFIG);
  const today = today_();
  const res = UrlFetchApp.fetch(HOLIDAY_ICS, { muteHttpExceptions: true });
  if (res.getResponseCode() !== 200) throw new Error('ดึงปฏิทินวันหยุดของ Google ไม่ได้ (HTTP ' + res.getResponseCode() + ') — ลองรันใหม่ภายหลัง');
  const fromGoogle = parseHolidayIcs_(res.getContentText('UTF-8'));
  if (fromGoogle.length < 5) throw new Error('ปฏิทินวันหยุดของ Google อ่านได้ ' + fromGoogle.length + ' วัน ซึ่งน้อยผิดปกติ — ไม่แก้อะไร เพื่อความปลอดภัย');
  const adjusted = civilServiceAdjust_(fromGoogle, CONFIG);
  const hol = mergeHolidays_(adjusted.list, CONFIG, addDays_(today, -7), CONFIG.routineUntil);
  setJson_(PROP.HOLIDAYS, hol);

  const made = getJson_(PROP.ROUTINE, {});
  const skipIds = {};
  Object.keys(made).forEach(function (k) { if (made[k].skip) skipIds[made[k].id] = 1; });
  const ids = getJson_(PROP.CAL_IDS, {});
  let removed = 0, checked = false;
  const countSeries = function (cal, id, fromYmd) {   // นับครั้งที่เหลือของชุดนั้นใน 200 วันข้างหน้า
    return cal.getEvents(at_(fromYmd, '00:00'), at_(addDays_(fromYmd, 200), '00:00')).filter(function (e) { return e.getId() === id; }).length;
  };
  hol.filter(function (h) { return h.date >= today; }).forEach(function (h) {
    allCalNames_().forEach(function (n) {
      const cal = ids[n] ? CalendarApp.getCalendarById(ids[n]) : null;
      if (!cal) return;
      cal.getEvents(at_(h.date, '00:00'), at_(addDays_(h.date, 1), '00:00')).forEach(function (ev) {
        if (!skipIds[ev.getId()] || ev.isAllDayEvent() || ymd_(ev.getStartTime()) !== h.date) return;
        const id = ev.getId();
        const before = checked ? 0 : countSeries(cal, id, h.date);
        ev.deleteEvent();   // ลบเฉพาะครั้งของวันนั้น ไม่ใช่ทั้งชุด
        removed++;
        if (!checked) {
          // ตรวจครั้งแรกของทุกรอบว่าการลบ "ครั้งเดียว" ไม่ได้ทำให้ครั้งอื่นของชุดหายไปด้วย — ถ้าหาย หยุดทันทีก่อนเสียหายเพิ่ม
          checked = true;
          const after = countSeries(cal, id, h.date);
          if (after < before - 1) throw new Error('หยุด: ลบงานประจำของวันหยุด ' + h.date + ' แล้วครั้งอื่นของชุดเดียวกันหายไปด้วย (' + before + ' → ' + after +
            ') — ไม่ทำต่อ กรุณาแจ้งผู้พัฒนา · กู้คืนได้จากถังขยะของปฏิทิน "' + calName_(n) + '"');
        }
      });
    });
  });
  console.log('วันหยุดราชการถึง ' + thaiDate_(CONFIG.routineUntil) + ' (' + hol.filter(function (h) { return h.date >= today; }).length + ' วัน):');
  hol.filter(function (h) { return h.date >= today; }).forEach(function (h) { console.log('  🎌 ' + thaiDate_(h.date, { short: true }) + ' — ' + h.name); });
  adjusted.notes.forEach(function (n) { console.warn('⚠️ ' + n); });
  console.log('หมายเหตุ: รายการมาจาก Google แล้วปรับให้ใกล้วันหยุดราชการ (ตัด: ' + (CONFIG.notHolidayNames || []).join(', ') + ' · เติม: วันเข้าพรรษา) — โปรดเทียบกับประกาศวันหยุดราชการของปีนั้น');
  console.log('เสร็จ: ตัดงานประจำที่ตรงวันหยุดออก ' + removed + ' รายการ · ถ้ารายการวันหยุดไม่ตรง แก้ extraHolidays / notHolidays ใน CONFIG แล้วรันใหม่');
  ensureHolidayTrigger_();
}
/** ตั้งให้ตรวจวันหยุดใหม่เองทุกวันที่ 1 (ครม. ประกาศวันหยุดพิเศษระหว่างปีได้) — ไม่ขึ้นกับการตั้งค่า LINE */
function ensureHolidayTrigger_() {
  const has = ScriptApp.getProjectTriggers().some(function (t) { return t.getHandlerFunction() === 'step3_syncHolidays'; });
  if (has) return;
  ScriptApp.newTrigger('step3_syncHolidays').timeBased().onMonthDay(1).atHour(5).inTimezone(TZ).create();
  console.log('ตั้งให้ตรวจวันหยุดใหม่เองทุกวันที่ 1 ของเดือนแล้ว');
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
  return (CONFIG.absentStartsWith || []).some(function (w) { return t.indexOf(w.toLowerCase()) === 0; }) ||
    (CONFIG.absentContains || []).some(function (w) { return t.indexOf(w.toLowerCase()) >= 0; });
}

/** รายการปฏิทินหนึ่งรายการ → ข้อมูลธรรมดาสำหรับวันนั้น (null = ไม่นับในวันนั้น) */
function toItem_(ev, dateYmd, now, routineIds) {
  const title = String(ev.getTitle() || '(ไม่มีชื่อ)').trim();
  const location = String(ev.getLocation() || '').trim();
  const updated = ev.getLastUpdated(), created = ev.getDateCreated();
  const fresh = updated && (now.getTime() - updated.getTime()) < 24 * 3600 * 1000;
  // งานประจำที่เพิ่งถูกสร้างพร้อมกันทั้งชุดไม่นับว่า "ใหม่" — นับเฉพาะที่มีคนแก้ทีหลัง
  const untouchedRoutine = routineIds[ev.getId()] && created && updated && Math.abs(updated.getTime() - created.getTime()) < 5 * 60 * 1000;
  const isNew = !!fresh && !untouchedRoutine;
  if (ev.isAllDayEvent()) {
    const first = ymdAllDay_(ev.getAllDayStartDate());
    const last = addDays_(ymdAllDay_(ev.getAllDayEndDate()), -1);   // วันจบของรายการทั้งวันเป็นวันถัดจากวันสุดท้าย
    if (dateYmd < first || dateYmd > last) return null;
    return { allDay: true, title: title, first: first, last: last, location: location, isNew: isNew };
  }
  const s = ev.getStartTime(), e = ev.getEndTime();
  if (ymd_(s) !== dateYmd) return null;   // เวรข้ามคืนที่เริ่มเมื่อวาน ไม่นับซ้ำ
  return { allDay: false, title: title, start: hm_(s), end: hm_(e), plusDays: daysBetween_(ymd_(s), ymd_(e)), location: location, isNew: isNew };
}

/** อ่านทุกปฏิทินของวันนั้น → { date, holiday, team:[item], people:[{name,dot,items}] } */
function collectDay_(dateYmd) {
  const ids = getJson_(PROP.CAL_IDS, {});
  const made = getJson_(PROP.ROUTINE, {});
  const routineIds = {};
  Object.keys(made).forEach(function (k) { routineIds[made[k].id] = 1; });
  const now = new Date();
  const read = function (shortName) {
    const cal = ids[shortName] ? CalendarApp.getCalendarById(ids[shortName]) : null;
    if (!cal) return [];
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
      if (routineIds[id] && cre && Math.abs(upd.getTime() - cre.getTime()) < 5 * 60 * 1000) return;   // งานประจำที่ไม่มีใครแตะ
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
      const a = absent[0];
      away.push(p.dot + ' ' + p.name + ' — ' + a.title + (a.last > day.date ? ' (ถึง ' + thaiDate_(a.last, { short: true, year: false }) + ')' : '') + (a.isNew ? ' 🆕' : ''));
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
function clip_(text) { return text.length > 4900 ? text.slice(0, 4850) + '\n… (ยาวเกิน ดูต่อในปฏิทิน)' : text; }
/** ส่งเข้ากลุ่ม · คืน true ถ้าส่งแล้ว false ถ้าโควตาหมด · ผิดพลาดอย่างอื่น throw (Google จะส่งอีเมลแจ้งเจ้าของ) */
function linePush_(text) {
  const group = props_().getProperty(PROP.GROUP);
  if (!group) throw new Error('ยังไม่ได้เชื่อมกลุ่ม LINE — เชิญบอทเข้ากลุ่มแล้วพิมพ์ข้อความอะไรก็ได้ 1 ครั้ง (ดู README)');
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
  if (!props_().getProperty(PROP.GROUP)) throw new Error('ยังไม่ได้เชื่อมกลุ่ม LINE — เชิญบอทเข้ากลุ่มแล้วพิมพ์ข้อความอะไรก็ได้ 1 ครั้ง (ดู README)');
  const today = today_();
  const d = digestText_(offsetDays, mode);
  if (d.isEmpty && CONFIG.line.skipEmptyDays) { console.log('ไม่มีรายการ — ไม่ส่ง'); return; }
  let text = d.text;
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
  checkLineQuota();
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
function resetLineGroup() { props_().deleteProperty(PROP.GROUP); console.log('ล้างกลุ่มที่เชื่อมไว้แล้ว'); }

// ══════════════════════════════════════════════════════════════════════════════
//  Webhook ของ LINE — ใช้ (1) จำกลุ่มให้เองตอนเชิญบอท (2) ตอบเมื่อมีคนพิมพ์ "วันนี้" "พรุ่งนี้" "สัปดาห์นี้"
//  ข้อความอื่นในกลุ่มถูกทิ้งทันที ไม่บันทึก ไม่เก็บ
// ══════════════════════════════════════════════════════════════════════════════
const COMMANDS = {
  'วันนี้':     function () { return digestText_(0, 'today').text; },
  'พรุ่งนี้':   function () { return digestText_(1, 'tomorrow').text; },
  'สัปดาห์นี้': function () { return weekText_(); },
  'ปฏิทิน':    function () { return 'พิมพ์คำใดคำหนึ่งนี้ในกลุ่ม:\n• วันนี้\n• พรุ่งนี้\n• สัปดาห์นี้\n\nเพิ่ม/แก้งาน วันลา ประชุม ได้ในแอปปฏิทินของเครื่อง (ปฏิทินชื่อขึ้นต้นว่า ' + CONFIG.prefix + ')'; }
};

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
    if (ev.type !== 'join' && ev.type !== 'message') return;
    // ยืนยันกับ LINE ว่าบอทอยู่ในกลุ่มนี้จริงก่อนจำ — กันคำขอปลอมที่แอบอ้าง group ID
    if (lineCall_('get', '/group/' + src.groupId + '/summary').code !== 200) return;
    const lock = LockService.getScriptLock();
    if (!lock.tryLock(8000)) return;
    try {
      linked = props_().getProperty(PROP.GROUP);
      if (!linked) {
        props_().setProperty(PROP.GROUP, src.groupId);
        if (ev.replyToken) lineReply_(ev.replyToken, '✅ เชื่อมกลุ่มนี้กับปฏิทิน' + CONFIG.prefix + 'แล้ว\n\n' + COMMANDS['ปฏิทิน']());
        return;
      }
    } finally { lock.releaseLock(); }
  }
  if (src.groupId !== linked) return;                 // กลุ่มอื่นที่ไม่ได้เชื่อมไว้ — ไม่ตอบ
  if (!CONFIG.line.replyCommands) return;
  if (ev.type !== 'message' || !ev.message || ev.message.type !== 'text' || !ev.replyToken) return;
  const cmd = COMMANDS[String(ev.message.text || '').trim()];
  if (cmd) lineReply_(ev.replyToken, cmd());           // ข้อความอื่นถูกทิ้ง ไม่บันทึก
}

// ══════════════════════════════════════════════════════════════════════════════
//  ขั้นที่ 6 — เปิดการส่ง LINE อัตโนมัติทุกวัน (รันซ้ำได้)
// ══════════════════════════════════════════════════════════════════════════════
function step6_startDailyLine() {
  // ตรวจก่อนสร้างตัวตั้งเวลา — ถ้าเปิดทั้งที่ LINE ยังไม่พร้อม จะได้อีเมลแจ้งล้มเหลวทุกวัน
  if (!props_().getProperty(PROP.TOKEN)) throw new Error('ยังไม่ได้ใส่ LINE_TOKEN — ทำขั้นที่ 5 ก่อน');
  if (!props_().getProperty(PROP.GROUP)) throw new Error('ยังไม่ได้เชื่อมกลุ่ม LINE — เชิญบอทเข้ากลุ่มแล้วพิมพ์ข้อความอะไรก็ได้ 1 ครั้ง จนบอทตอบว่า "เชื่อมกลุ่มนี้แล้ว" ก่อน');
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
