/* Service worker ของหน้าแฟ้มสะสมงาน — ทำให้ติดตั้งลงมือถือและเปิดใช้แบบออฟไลน์ได้
   ขอบเขตอยู่ที่โฟลเดอร์ /portfolio/ เท่านั้น จึงไม่ไปยุ่งกับหน้าระบบคิวหรือ API ใด ๆ */
const CACHE = "ortho-portfolio-v1";
const SHELL = [
  "./", "./index.html", "./manifest.webmanifest",
  "./icon-192.png", "./icon-512.png", "./icon-maskable-512.png", "./apple-touch-icon.png"
];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

self.addEventListener("message", (e) => { if (e.data === "skip-waiting") self.skipWaiting(); });

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;          /* ปล่อยให้ API ของระบบคิววิ่งตรงเสมอ */

  /* เปิดหน้าเว็บ: เอาของใหม่ก่อน ถ้าออฟไลน์ค่อยใช้ของที่เก็บไว้
     เก็บลง cache เฉพาะตอบกลับที่ปกติดี (res.ok) — คำตอบพัง (captive portal, 5xx) ไม่ควรทับของเดิมที่ใช้งานได้ */
  if (req.mode === "navigate") {
    e.respondWith(fetch(req).then(res => {
      if (res.ok) caches.open(CACHE).then(c => c.put("./index.html", res.clone()));
      return res;
    }).catch(() => caches.match("./index.html")));
    return;
  }

  /* ไฟล์ประกอบของแอป: ใช้ของที่เก็บไว้ก่อน แล้วค่อยอัปเดตเบื้องหลัง */
  const path = url.pathname.replace(/^.*\//, "./");
  if (SHELL.includes(path)) {
    e.respondWith(caches.match(req).then(hit => {
      const net = fetch(req).then(res => {
        if (res.ok) caches.open(CACHE).then(c => c.put(req, res.clone()));
        return res;
      /* ออฟไลน์และไม่เคยมีของเก่าเก็บไว้เลย (hit เป็น undefined) ต้องไม่ resolve เป็น undefined
         เพราะ respondWith ต้องได้ Response เสมอ ไม่งั้น TypeError ทันที */
      }).catch(() => hit || new Response("", { status: 503, statusText: "offline" }));
      return hit || net;
    }));
  }
});
