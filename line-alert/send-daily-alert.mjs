#!/usr/bin/env node
/* ต่อทุกชิ้นของไปป์ไลน์เข้าด้วยกัน — จุดเริ่มที่เรียกจาก CLI/GitHub Actions
   ใช้: node send-daily-alert.mjs [--dry-run] [--file=path/to/export.json] [--date=YYYY-MM-DD]
   --dry-run       ไม่ยิงเข้า LINE จริง แค่ log ข้อความที่จะส่งออกมาดู (ใช้ตอนยังไม่มี credential)
   --file=...      ระบุไฟล์ dataset เอง (ไม่งั้นใช้ MNRH_DATASET_FILE หรือ data/latest-export.json)
   --date=...      คำนวณของวันที่ระบุแทนวันนี้ (ใช้ทดสอบ/สาธิต) */
import { loadTodayDataset } from "./data-source.mjs";
import { computeToday } from "./compute.mjs";
import { formatDailyAlert } from "./format.mjs";
import { sendLineMessage } from "./line-client.mjs";

async function main() {
  const args = process.argv.slice(2);
  const dryRun = args.includes("--dry-run") || process.env.LINE_DRY_RUN === "1";
  const dateArg = args.find(a => a.startsWith("--date="))?.slice("--date=".length);

  const data = await loadTodayDataset();
  const { iso, sessions, topicConf } = await computeToday(data, dateArg);
  const text = formatDailyAlert({ iso, sessions, topicConf, residents: data.residents });

  console.log("== ข้อความที่จะส่ง (" + iso + ") ==");
  console.log(text);
  console.log("== จบข้อความ (" + text.length + " ตัวอักษร) ==");

  await sendLineMessage({
    token: process.env.LINE_CHANNEL_ACCESS_TOKEN,
    groupId: process.env.LINE_GROUP_ID,
    text, dryRun
  });
  console.log(dryRun ? "โหมดทดสอบ (dry-run) — ไม่ได้ส่งเข้า LINE จริง" : "ส่งเข้ากลุ่ม LINE แล้ว");
}

main().catch(e => { console.error("ล้มเหลว:", e.message); process.exit(1); });
