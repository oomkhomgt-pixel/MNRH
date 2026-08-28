/* ตรวจตรรกะของ sw.js แยกจากเบราว์เซอร์จริง — จำลอง self/caches ขั้นต่ำในบริบท vm ของ Node
   การติดตั้ง service worker จริงในเบราว์เซอร์ทดสอบซับซ้อนเกินความจำเป็นสำหรับสองบั๊กนี้
   (D1: เก็บ response ที่พังลง cache, D4: respondWith(undefined) เมื่อออฟไลน์และไม่มี cache เดิม) */
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { suite, ROOT } from "./lib.mjs";

function loadSW(fetchImpl, caches) {
  const src = fs.readFileSync(path.join(ROOT, "portfolio/sw.js"), "utf8");
  const listeners = {};
  const self = {
    addEventListener: (type, fn) => { (listeners[type] ||= []).push(fn); },
    location: { origin: "http://localhost" },
    clients: { claim: async () => {} },
    skipWaiting: () => {}
  };
  /* caches ต้องอยู่ใน context ของ vm โดยตรง — vm.createContext สร้าง global แยกจาก globalThis
     ของ Node จริง การตั้ง globalThis.caches ในสคริปต์ทดสอบภายนอกจะไม่ถูกมองเห็นจากในนี้เลย */
  const context = { self, caches, URL, Response, Request, console, fetch: fetchImpl };
  vm.createContext(context);
  vm.runInContext(src, context, { filename: "sw.js" });
  return listeners;
}

const fireFetch = (listeners, request) => {
  let responded = null;
  listeners.fetch[0]({ request, respondWith: (p) => { responded = p; } });
  return responded;
};

export default async function run() {
  const t = suite("service worker (sw.js) — ตรรกะแยกจากเบราว์เซอร์");

  /* ---------- D1: response ที่ไม่ ok ต้องไม่ถูกเก็บลง cache (ไฟล์ประกอบของแอป) ---------- */
  {
    const puts = [];
    const cache = { put: async (req, res) => puts.push(req), match: async () => undefined };
    const caches = { open: async () => cache, match: async () => undefined };
    const listeners = loadSW(async () => new Response("err", { status: 500, statusText: "Internal Error" }), caches);
    const req = new Request("http://localhost/portfolio/manifest.webmanifest");
    const p = fireFetch(listeners, req);
    await p;
    await new Promise(r => setTimeout(r, 20)); /* ให้ caches.open().then(c=>c.put(...)) วิ่งจบ */
    t.eq("ไฟล์ประกอบ: response พัง (500) ไม่ถูกเก็บลง cache", puts.length, 0);
  }

  /* ---------- D1: response ปกติ (ok) ยังถูกเก็บลง cache เหมือนเดิม (ไม่ใช่ปิดการแคชไปเลย) ---------- */
  {
    const puts = [];
    const cache = { put: async (req, res) => puts.push(req), match: async () => undefined };
    const caches = { open: async () => cache, match: async () => undefined };
    const listeners = loadSW(async () => new Response("ok body", { status: 200 }), caches);
    const req = new Request("http://localhost/portfolio/manifest.webmanifest");
    const p = fireFetch(listeners, req);
    await p;
    await new Promise(r => setTimeout(r, 20));
    t.eq("ไฟล์ประกอบ: response ปกติยังถูกเก็บลง cache ตามเดิม", puts.length, 1);
  }

  /* ---------- D4: ออฟไลน์และไม่มี cache เดิมเลย ต้องได้ Response จริง ไม่ใช่ undefined ---------- */
  {
    const cache = { put: async () => {}, match: async () => undefined }; /* ไม่มีของเก่าเก็บไว้เลย */
    const caches = { open: async () => cache, match: async () => undefined };
    const listeners = loadSW(async () => { throw new Error("offline"); }, caches); /* จำลองออฟไลน์ */
    const req = new Request("http://localhost/portfolio/manifest.webmanifest");
    const p = fireFetch(listeners, req);
    let threw = "", result = null;
    try { result = await p; } catch (e) { threw = e.message; }
    t.eq("ออฟไลน์ + ไม่มี cache เดิม: respondWith ไม่โยน error", threw, "");
    t.check("ออฟไลน์ + ไม่มี cache เดิม: ได้ Response จริง ไม่ใช่ undefined", result instanceof Response,
            String(result));
  }

  return t;
}
