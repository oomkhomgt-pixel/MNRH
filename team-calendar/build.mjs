#!/usr/bin/env node
/* สร้างไฟล์ปฏิทิน .ics ทั้งหมดจาก schedule.json
   ใช้:  node build.mjs            เขียนไฟล์ลง feeds/
         node build.mjs --check    ไม่เขียน — ตรวจว่าไฟล์ใน feeds/ ตรงกับ schedule.json หรือไม่ (ใช้ใน CI)
   ไม่ต้อง npm install อะไร ใช้ Node 20+ เปล่า ๆ */
import { readFile, writeFile, readdir, mkdir, unlink } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { validate, conflicts, describeConflict, bangkokToday, addDays } from "./lib.mjs";
import { buildFeed, feedList } from "./ics.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const FEEDS = join(here, "feeds");

export async function loadSchedule(file = join(here, "schedule.json")) {
  const raw = await readFile(file, "utf8");
  try { return JSON.parse(raw); }
  catch (e) {
    /* ข้อผิดพลาดที่พบบ่อยที่สุดของคนแก้ JSON มือ — ลืมจุลภาค / จุลภาคเกินตัวสุดท้าย / ใช้เครื่องหมายคำพูดแบบโค้ง */
    const m = /position (\d+)/.exec(e.message);
    const line = m ? raw.slice(0, +m[1]).split("\n").length : "?";
    throw new Error(`schedule.json อ่านไม่ได้ (ประมาณบรรทัดที่ ${line}): ${e.message}\n` +
      `  ตรวจ: จุลภาค , ระหว่างรายการ · ไม่มี , หลังรายการสุดท้าย · ใช้ " ตรง ๆ ไม่ใช่ “ ”`);
  }
}

async function main() {
  const check = process.argv.includes("--check");
  const s = await loadSchedule();
  const { errors, warnings } = validate(s);
  warnings.forEach(w => console.warn("⚠️  " + w));
  if (errors.length) {
    console.error("\n❌ schedule.json มีจุดที่ต้องแก้ " + errors.length + " จุด — ยังไม่สร้างปฏิทิน:\n");
    errors.forEach(e => console.error("  • " + e));
    process.exit(1);
  }

  const today = bangkokToday();
  const cs = conflicts(s, today, addDays(today, 90));
  if (cs.length) {
    console.warn("\n⚠️  งานชนกันใน 90 วันข้างหน้า " + cs.length + " รายการ (ไม่หยุดการสร้าง แต่ควรแก้):");
    cs.forEach(c => console.warn("  • " + describeConflict(s, c)));
  }

  const feeds = feedList(s);
  const want = new Map(feeds.map(f => [f.id + ".ics", buildFeed(s, f)]));
  await mkdir(FEEDS, { recursive: true });
  const have = (await readdir(FEEDS)).filter(f => f.endsWith(".ics"));

  if (check) {
    const stale = [];
    for (const [name, body] of want) {
      const cur = await readFile(join(FEEDS, name), "utf8").catch(() => null);
      if (cur !== body) stale.push(name);
    }
    have.filter(n => !want.has(n)).forEach(n => stale.push(n + " (ไม่ใช้แล้ว)"));
    if (stale.length) {
      console.error("\n❌ ไฟล์ปฏิทินใน feeds/ ไม่ตรงกับ schedule.json: " + stale.join(", ") + "\n   รัน: node team-calendar/build.mjs");
      process.exit(1);
    }
    console.log("✅ feeds/ ตรงกับ schedule.json (" + want.size + " ไฟล์)");
    return;
  }

  for (const [name, body] of want) await writeFile(join(FEEDS, name), body);
  for (const n of have.filter(n => !want.has(n))) await unlink(join(FEEDS, n));   // สมาชิกที่ถูกลบออก
  console.log("✅ สร้างปฏิทิน " + want.size + " ไฟล์ใน feeds/: " + [...want.keys()].join(", "));
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  main().catch(e => { console.error("❌ " + e.message); process.exit(1); });
}
