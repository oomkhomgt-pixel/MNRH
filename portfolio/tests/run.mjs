/* ตัวรันชุดทดสอบทั้งหมด — ใช้ได้ทั้งบนเครื่องตัวเองและบน CI
   node portfolio/tests/run.mjs           รันทุกชุด
   node portfolio/tests/run.mjs parse     รันเฉพาะชุดที่ชื่อขึ้นต้นด้วยคำนั้น */
import parse from "./parse.test.mjs";
import smoke from "./smoke.test.mjs";
import permissions from "./permissions.test.mjs";
import schedule from "./schedule.test.mjs";
import orqueue from "./orqueue.test.mjs";
import sync from "./sync.test.mjs";
import swjs from "./swjs.test.mjs";
import topicconf from "./topicconf.test.mjs";
import calendar from "./calendar.test.mjs";

const ALL = { parse, smoke, permissions, schedule, orqueue, sync, swjs, topicconf, calendar };
const only = process.argv.slice(2);
const picked = Object.entries(ALL).filter(([k]) => !only.length || only.some(o => k.startsWith(o)));

let failed = 0;
for (const [name, fn] of picked) {
  try {
    const t = await fn();
    failed += t.report();
  } catch (e) {
    console.log("\n▸ " + name + "\n  ✗ ชุดทดสอบล้มระหว่างรัน — " + (e.stack || e.message));
    failed++;
  }
}
console.log(failed ? "\n" + failed + " ข้อไม่ผ่าน" : "\nผ่านทั้งหมด");
process.exit(failed ? 1 : 0);
