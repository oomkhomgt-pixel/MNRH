/* จุดสลับแหล่งข้อมูล "วันนี้เอาข้อมูลมาจากไหน" — จุดเดียวในไปป์ไลน์ทั้งหมด
   ตอนนี้อ่านจากไฟล์ JSON ที่ export ออกมาจากแอป (ปุ่ม "สำรองข้อมูล" ในหน้าตั้งค่า) ซึ่งมีรูปร่างเดียวกับ
   store.data เป๊ะ (ดู portfolio/index.html: exportJson() — download ตรง ๆ ไม่มี envelope ห่อ)

   ทีหลังถ้าจะเปลี่ยนไปดึงจาก sync-server แบบสด แก้เฉพาะฟังก์ชัน loadTodayDataset() นี้ฟังก์ชันเดียวเป็น
     const res = await fetch(url + "/api/portfolio/dataset");
     const json = await res.json();
     return json.data;
   ส่วนที่เหลือทั้งหมด (compute.mjs / format.mjs / line-client.mjs) ไม่ต้องแตะเลย เพราะรับแค่
   "object รูปร่างเดียวกับ store.data" เป็น input ไม่สนใจว่ามันมาจากไหน */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const DEFAULT_FILE = path.join(HERE, "data", "latest-export.json");

function resolveFile(overridePath) {
  if (overridePath) return overridePath;
  const argFile = process.argv.find(a => a.startsWith("--file="));
  if (argFile) return argFile.slice("--file=".length);
  if (process.env.MNRH_DATASET_FILE) return process.env.MNRH_DATASET_FILE;
  return DEFAULT_FILE;
}

/* overridePath มีไว้ให้เทสต์เรียกตรง ๆ ได้โดยไม่ต้องยุ่งกับ process.argv/env ของทั้งโปรเซส */
export async function loadTodayDataset(overridePath) {
  const file = resolveFile(overridePath);
  let raw;
  try {
    raw = fs.readFileSync(file, "utf8");
  } catch (e) {
    throw new Error("อ่านไฟล์ข้อมูลไม่สำเร็จ (" + file + "): " + e.message);
  }
  let data;
  try {
    data = JSON.parse(raw);
  } catch (e) {
    throw new Error("ไฟล์ " + file + " ไม่ใช่ JSON ที่ถูกต้อง: " + e.message);
  }
  if (!data || !Array.isArray(data.residents) || !Array.isArray(data.activities))
    throw new Error("โครงสร้างไฟล์ไม่ถูกต้อง (" + file + ") — ต้องเป็นไฟล์ที่ได้จากปุ่ม \"สำรองข้อมูล\" ในแอป " +
      "(ต้องมี residents และ activities เป็นอาเรย์)");
  return data;
}
