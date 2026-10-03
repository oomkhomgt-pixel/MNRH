/* รัน sync-server/apps-script/Code.gs ใน Node — จำลอง DriveApp / LockService / PropertiesService / ContentService / Utilities
   ขั้นต่ำเท่าที่สคริปต์ใช้ ให้ทดสอบตรรกะของปลายทางจริงได้ทั้งแบบเรียกตรงและต่อกับแอปในเบราว์เซอร์ (page.route) */
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import crypto from "node:crypto";
import { ROOT } from "./lib.mjs";

export function loadGas(props = {}) {
  const src = fs.readFileSync(path.join(ROOT, "sync-server/apps-script/Code.gs"), "utf8");
  const propMap = new Map(Object.entries({ FOLDER_ID: "F1", ...props }));
  const files = new Map();                                   /* name → { text, trashed } */
  const iter = (arr) => { let i = 0; return { hasNext: () => i < arr.length, next: () => arr[i++] }; };
  const fileObj = (name) => ({
    getName: () => name,
    getBlob: () => ({ getDataAsString: () => files.get(name).text }),
    setContent: (t) => { files.get(name).text = t; },
    setTrashed: (v) => { if (v) files.delete(name); }
  });
  const folder = {
    getFilesByName: (n) => iter(files.has(n) ? [fileObj(n)] : []),
    getFiles: () => iter([...files.keys()].map(fileObj)),
    createFile: (n, t) => { files.set(n, { text: t }); return fileObj(n); }
  };
  const locks = { held: 0, max: 0 };
  const logs = [];
  const context = {
    DriveApp: { getFolderById: (id) => { if (id !== propMap.get("FOLDER_ID") && id !== "F1") throw new Error("no folder " + id); return folder; } },
    LockService: { getScriptLock: () => ({ waitLock: () => { locks.held++; locks.max = Math.max(locks.max, locks.held); }, releaseLock: () => { locks.held--; } }) },
    PropertiesService: { getScriptProperties: () => ({ getProperty: (k) => propMap.has(k) ? propMap.get(k) : null, setProperty: (k, v) => { propMap.set(k, String(v)); } }) },
    ContentService: { MimeType: { JSON: "json" }, createTextOutput: (s) => ({ text: s, setMimeType() { return this; } }) },
    Utilities: {
      DigestAlgorithm: { SHA_256: "sha256" }, Charset: { UTF_8: "utf8" },
      computeDigest: (alg, s) => [...crypto.createHash("sha256").update(String(s), "utf8").digest()].map(b => (b > 127 ? b - 256 : b)),
      getUuid: () => crypto.randomUUID()
    },
    console: { log: (...a) => logs.push(a.join(" ")) },
    JSON, Date, Number, String, Object, Array, Math, Error
  };
  vm.createContext(context);
  vm.runInContext(src, context, { filename: "Code.gs" });
  const post = (req) => JSON.parse(context.doPost({ postData: { contents: typeof req === "string" ? req : JSON.stringify(req) } }).text);
  return { ctx: context, post, files, props: propMap, locks, logs };
}
