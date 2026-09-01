/* ชุดทดสอบที่ไม่ต้องมี LINE credential จริง — รันได้ทุกที่ทุกเวลา ไม่แตะ network จริงเลย
   ตั้งใจให้เป็นด่านตรวจก่อนยิงจริงทุกครั้ง (ดูการใช้งานใน .github/workflows/line-daily-alert.yml)
   ไม่ต้องมี playwright ก็รันได้ — ทดสอบเฉพาะ format.mjs / line-client.mjs / data-source.mjs
   ซึ่งเป็นตรรกะจัดข้อความ/ส่ง/อ่านไฟล์ล้วน ๆ ไม่ใช่ตรรกะจัดตารางที่ต้องเปิดเบราว์เซอร์จริง */
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { formatDailyAlert, LINE_TEXT_LIMIT } from "./format.mjs";
import { sendLineMessage } from "./line-client.mjs";
import { loadTodayDataset } from "./data-source.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
let pass = 0, fail = 0;
function check(label, ok, detail) {
  if (ok) { pass++; console.log("  ✓ " + label); }
  else { fail++; console.log("  ✗ " + label + (detail ? " — " + detail : "")); }
}
async function throws(fn) {
  try { await fn(); return null; } catch (e) { return e; }
}

console.log("▸ line-alert smoke tests");

/* ---------- format.mjs ---------- */
{
  const residents = [{ id: "r1", name: "นพ. ทดสอบ", year: 3 }, { id: "r2", name: "พญ. ตัวอย่าง", year: 4 }];
  const plain = formatDailyAlert({
    iso: "2026-09-02", residents,
    sessions: [{ residentId: "r1", name: "Morning conference", start: "09:00", end: "10:00", topicConference: false }],
    topicConf: null
  });
  check("คาบธรรมดา: ไม่มีบรรทัดผู้นิเทศ/หัวหน้าสาย", !plain.includes("ผู้นิเทศ") && !plain.includes("🎓"), plain);
  check("คาบธรรมดา: มีชื่อแพทย์ประจำบ้านและคาบ", plain.includes("นพ. ทดสอบ") && plain.includes("Morning conference"));

  const withTc = formatDailyAlert({
    iso: "2026-09-03", residents,
    sessions: [
      { residentId: "r1", name: "Topic conference / Journal club / Staff lecture", start: "09:00", end: "12:00", topicConference: true },
      { residentId: "r2", name: "Inter-hospital conference", start: "13:00", end: "15:30", topicConference: false }
    ],
    topicConf: { staffLabel: "พญ. มานิตา", teamLabel: "Blue Team", chiefLabel: "นพ. วิฑูรย์" }
  });
  check("มีคาบ Topic conference: ขึ้นบรรทัดผู้นิเทศ+สาย+หัวหน้าสาย", withTc.includes("🎓") && withTc.includes("ผู้นิเทศ: พญ. มานิตา"));
  check("บรรทัดผู้นิเทศพูดครบสามช่อง", withTc.includes("สาย: Blue Team") && withTc.includes("หัวหน้าสาย: นพ. วิฑูรย์"));
  /* เฉพาะคาบ Topic conference เท่านั้นที่มีบรรทัดนี้ — คาบ Inter-hospital ในวันเดียวกันต้องไม่มี */
  const ihcLine = withTc.split("\n").find(l => l.includes("Inter-hospital"));
  const nextLine = withTc.split("\n")[withTc.split("\n").indexOf(ihcLine) + 1] || "";
  check("คาบอื่นในวันเดียวกันไม่มีบรรทัดผู้นิเทศติดไปด้วย", !nextLine.includes("ผู้นิเทศ"), nextLine);

  const noneToday = formatDailyAlert({ iso: "2026-09-05", residents, sessions: [], topicConf: null });
  check("ไม่มีกิจกรรมวันนั้นเลย: ยังได้ข้อความที่อ่านได้ ไม่ throw", noneToday.includes("ไม่มีกิจกรรม"));

  /* ---------- ตัดความยาวไม่ให้เกินลิมิตของ LINE ---------- */
  const longSessions = Array.from({ length: 400 }, (_, i) => ({
    residentId: "r1", name: "กิจกรรมทดสอบความยาวข้อความหมายเลข " + i + " ".repeat(20), start: "09:00", end: "10:00", topicConference: false
  }));
  const long = formatDailyAlert({ iso: "2026-09-06", residents, sessions: longSessions, topicConf: null });
  check("ข้อความยาวเกินลิมิตถูกตัดให้ไม่เกิน " + LINE_TEXT_LIMIT + " ตัวอักษร", long.length <= LINE_TEXT_LIMIT, long.length + " ตัวอักษร");
  check("ข้อความที่ถูกตัดมีข้อความบอกว่าตัดไว้", long.includes("ตัดข้อความ"));
}

/* ---------- line-client.mjs ---------- */
{
  const realFetch = globalThis.fetch;
  globalThis.fetch = () => { throw new Error("ไม่ควรมีการยิง network ตอน dryRun:true"); };
  const r = await sendLineMessage({ token: "x", groupId: "y", text: "ทดสอบ", dryRun: true });
  check("dryRun:true ไม่ยิง network จริง และคืนค่าบอกว่าเป็น dry-run", r.dryRun === true);
  globalThis.fetch = realFetch;

  const errNoToken = await throws(() => sendLineMessage({ token: "", groupId: "y", text: "x", dryRun: false }));
  check("ไม่มี token: throw ข้อความชัดเจน ไม่ยิง network", !!errNoToken && errNoToken.message.includes("LINE_CHANNEL_ACCESS_TOKEN"), errNoToken?.message);

  const errNoGroup = await throws(() => sendLineMessage({ token: "x", groupId: "", text: "x", dryRun: false }));
  check("ไม่มี groupId: throw ข้อความชัดเจน ไม่ยิง network", !!errNoGroup && errNoGroup.message.includes("LINE_GROUP_ID"), errNoGroup?.message);
}

/* ---------- data-source.mjs ---------- */
{
  const errMissing = await throws(() => loadTodayDataset("/no/such/file/exists.json"));
  check("อ่านไฟล์ที่ไม่มีอยู่จริง: throw ข้อความชัดเจน บอกชื่อไฟล์", !!errMissing && errMissing.message.includes("/no/such/file/exists.json"), errMissing?.message);

  const badFile = path.join(HERE, "data", "__bad_sample_for_test.json");
  const fs = await import("node:fs");
  fs.writeFileSync(badFile, JSON.stringify({ foo: "bar" }));
  const errShape = await throws(() => loadTodayDataset(badFile));
  fs.unlinkSync(badFile);
  check("โครงสร้างไฟล์ผิด (ไม่มี residents/activities): throw ข้อความชัดเจน", !!errShape && errShape.message.includes("โครงสร้างไฟล์ไม่ถูกต้อง"), errShape?.message);

  const sample = path.join(HERE, "data", "latest-export.json");
  const data = await loadTodayDataset(sample);
  check("ไฟล์ตัวอย่างที่แนบมาด้วย (data/latest-export.json) โหลดได้จริงและมีรูปร่างถูกต้อง",
        Array.isArray(data.residents) && data.residents.length > 0 && Array.isArray(data.activities),
        data.residents?.length + " residents");
}

console.log(fail ? "\n" + fail + " ข้อไม่ผ่าน" : "\nผ่านทั้งหมด (" + pass + " ข้อ)");
process.exit(fail ? 1 : 0);
