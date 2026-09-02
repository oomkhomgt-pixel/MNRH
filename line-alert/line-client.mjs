/* ส่งข้อความเข้ากลุ่ม LINE ผ่าน push API แบบกลุ่มเดียว (ไม่ใช่ multicast เพราะข้อความเป็นสรุปเดียวกัน
   ไม่ personalized ต่อคน) — token/groupId ต้องมาจาก environment variable เท่านั้น ห้ามอยู่ในไฟล์ไหนในโค้ด
   เด็ดขาด เพราะ token นี้ยิงข้อความแทนบอทในกลุ่มได้ทันทีถ้าหลุด */
const LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push";

/* { token, groupId, text, dryRun } — dryRun:true ไม่ยิง network จริงเลย แค่ log ข้อความที่จะส่งออกมาดู
   ใช้ตอนยังไม่มี credential จริง หรือทดสอบข้อความก่อนเปิดใช้งานจริง */
export async function sendLineMessage({ token, groupId, text, dryRun }) {
  if (dryRun) {
    console.log("[dry-run] จะส่งข้อความนี้เข้ากลุ่ม LINE (groupId=" + (groupId || "— ยังไม่ได้ตั้งค่า —") + "):\n");
    console.log(text);
    return { dryRun: true };
  }
  if (!token) throw new Error("ไม่มี LINE_CHANNEL_ACCESS_TOKEN — ตั้งค่าเป็น environment variable หรือ GitHub Secret ก่อน");
  if (!groupId) throw new Error("ไม่มี LINE_GROUP_ID — ตั้งค่าเป็น environment variable หรือ GitHub Secret ก่อน");

  const res = await fetch(LINE_PUSH_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Authorization": "Bearer " + token },
    body: JSON.stringify({ to: groupId, messages: [{ type: "text", text }] })
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error("LINE API ตอบกลับ HTTP " + res.status + ": " + body);
  }
  return { ok: true };
}
