/* จัดข้อความแจ้งเตือนภาษาไทยสำหรับส่งเข้ากลุ่ม LINE — รับผลลัพธ์ที่คำนวณแล้วจาก compute.mjs
   (sessions/topicConf มาจากฟังก์ชันจริงในแอป) มาจัดรูปแบบข้อความเฉย ๆ ไม่มีตรรกะจัดตารางในไฟล์นี้เลย */

/* ลิมิตข้อความของ LINE push API: ประมาณ 5000 ตัวอักษรต่อข้อความ */
export const LINE_TEXT_LIMIT = 5000;

const THAI_DOW = ["อาทิตย์", "จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์"];
const THAI_MONTHS = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."];

function fmtDateTh(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return String(d) + " " + THAI_MONTHS[m - 1] + " " + (y + 543);
}

function timeLabel(ses) {
  return ses.start && ses.end ? ses.start + "–" + ses.end : "";
}

function truncate(text) {
  if (text.length <= LINE_TEXT_LIMIT) return text;
  const suffix = "\n…(ตัดข้อความ เนื่องจากยาวเกินขีดจำกัด " + LINE_TEXT_LIMIT + " ตัวอักษรของ LINE)";
  return text.slice(0, LINE_TEXT_LIMIT - suffix.length) + suffix;
}

/* { iso, sessions, topicConf, residents } — residents คือ data.residents จาก dataset ทั้งก้อน
   ใช้แค่หาชื่อ/ชั้นปีมาแสดงเท่านั้น ไม่ได้ใช้คำนวณอะไร */
export function formatDailyAlert({ iso, sessions, topicConf, residents }) {
  const byId = new Map((residents || []).map(r => [r.id, r]));
  const dow = new Date(iso + "T00:00:00").getDay();
  const lines = [];
  lines.push("📅 สรุปกิจกรรมประจำวัน — วัน" + THAI_DOW[dow] + "ที่ " + fmtDateTh(iso));
  lines.push("");

  /* เฉพาะคาบ Topic conference เท่านั้นที่โชว์ผู้นิเทศ+หัวหน้าสาย — คาบอื่นไม่มีบรรทัดนี้เลย
     ตรงตามกติกาเดียวกับหน้าปฏิทินในแอป (ดู portfolio/index.html: calChip()) */
  const tcSessions = (sessions || []).filter(s => s.topicConference);
  if (tcSessions.length) {
    const t = timeLabel(tcSessions[0]);
    lines.push("🎓 Topic conference / Journal club / Staff lecture" + (t ? " (" + t + ")" : ""));
    lines.push("   ผู้นิเทศ: " + (topicConf?.staffLabel || "ยังไม่ได้กำหนด") +
      " · สาย: " + (topicConf?.teamLabel || "ยังไม่ได้กำหนด") +
      " · หัวหน้าสาย: " + (topicConf?.chiefLabel || "ยังไม่ได้กำหนด"));
    lines.push("");
  }

  const byResident = new Map();
  (sessions || []).forEach(s => {
    if (!byResident.has(s.residentId)) byResident.set(s.residentId, []);
    byResident.get(s.residentId).push(s);
  });

  if (byResident.size) {
    lines.push("รายกิจกรรมของแพทย์ประจำบ้าน:");
    [...byResident.entries()]
      .sort((a, b) => (byId.get(a[0])?.name || "").localeCompare(byId.get(b[0])?.name || "", "th"))
      .forEach(([rid, list]) => {
        const r = byId.get(rid);
        lines.push("• " + (r ? r.name + " (ปี " + r.year + ")" : "ไม่ทราบชื่อ"));
        list.forEach(s => {
          const t = timeLabel(s);
          lines.push("   - " + (t ? t + " " : "") + s.name);
        });
      });
  } else {
    lines.push("วันนี้ไม่มีกิจกรรมของแพทย์ประจำบ้านตามตาราง");
  }

  return truncate(lines.join("\n"));
}
