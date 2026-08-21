#!/usr/bin/env node
/* ตัวจำลอง API ของระบบคิวห้องผ่าตัด — ใช้พัฒนาและทดสอบหน้าแฟ้มสะสมงานโดยไม่ต้องต่อ intranet ของโรงพยาบาล
 *
 *   node or-queue-mock/server.js            เปิดที่พอร์ต 8088
 *   PORT=9000 node or-queue-mock/server.js
 *
 * แล้วตั้งที่หน้า "ตั้งค่าการเชื่อมต่อ" ของแอป: ที่อยู่ API = http://127.0.0.1:8088
 *
 * ไม่มี dependency ตั้งใจให้รันได้ด้วย node เปล่า ๆ เหมือน sync-server
 * ข้อมูลที่คืนเป็นข้อมูลสมมติทั้งหมด ไม่มีผู้ป่วยจริง — ชื่ออาจารย์กับวันผ่าตัดอิงตารางจริงของกลุ่มงาน
 * เพื่อให้เคสที่นำเข้าไปตรงกับตารางหมุนเวียน และการเดาผู้ร่วมผ่าตัดทำงานได้เหมือนของจริง
 */
const http = require("http");
const { URL } = require("url");

const PORT = +(process.env.PORT || 8088);
const DAYS_BACK = +(process.env.DAYS_BACK || 60);
const DAYS_AHEAD = +(process.env.DAYS_AHEAD || 14);

/* ลิสต์ผ่าตัดจริงของแต่ละสาย: [วันในสัปดาห์, สาย, ศัลยแพทย์, อนุสาขา]
   1 = จันทร์ … 5 = ศุกร์ ตรงกับตารางที่กลุ่มงานใช้ */
const LISTS = [
  [2, "ฟ้า", "นพ. มานิตา", "hand"],
  [2, "ฟ้า", "นพ. ศุภศักดิ์", "sports"],
  [3, "ฟ้า", "", "emergency"],
  [4, "ฟ้า", "นพ. ชนกันต์", "trauma"],
  [5, "ฟ้า", "นพ. คงธัช", "spine"],
  [5, "ฟ้า", "นพ. อดิศร", "foot"],
  [1, "แดง", "", "emergency"],
  [3, "แดง", "นพ. ณภัทร", "hand"],
  [3, "แดง", "นพ. ยิ่งยง", "arthroplasty"],
  [4, "แดง", "นพ. ธนัท", "arthroplasty"],
  [5, "แดง", "นพ. อุรวิศ", "spine"],
  [5, "แดง", "นพ. ธีรภัทร", "oncology"],
  [1, "เหลือง", "นพ. พาชิน", "sports"],
  [1, "เหลือง", "นพ. นฤพล", "arthroplasty"],
  [1, "เหลือง", "นพ. สุทธิ", "oncology"],
  [2, "เหลือง", "นพ. ศรุต", "spine"],
  [2, "เหลือง", "นพ. ณัฐกุล", "hand"],
  [4, "เหลือง", "นพ. มนูญ", "sports"],
  [5, "เหลือง", "", "emergency"],
  [1, "ขาว", "นพ. ธน", "trauma"],
  [1, "ขาว", "นพ. เทอดพงษ์", "spine"],
  [2, "ขาว", "", "emergency"],
  [3, "ขาว", "นพ. วรินธร", "pediatric"],
  [3, "ขาว", "นพ. จิธายุทธ", "arthroplasty"],
  [4, "ขาว", "นพ. วีระ", "spine"]
];

/* ชุด diagnosis/operation ต่ออนุสาขา — สมมติทั้งหมด แต่เขียนอย่างที่หมอจะเขียนจริง */
const OPS = {
  trauma: [
    ["Closed fracture shaft of femur, right", "Closed reduction and intramedullary nailing, right femur"],
    ["Closed fracture distal radius, left", "Open reduction internal fixation with volar plate, left distal radius"],
    ["Open fracture tibia Gustilo IIIA, left", "Debridement and external fixation, left tibia"],
    ["Intertrochanteric fracture, right", "Proximal femoral nail antirotation, right hip"],
    ["Closed fracture both bones forearm, left", "Open reduction internal fixation with plates, left forearm"]
  ],
  spine: [
    ["Lumbar spinal stenosis L4-L5", "Decompressive laminectomy L4-L5"],
    ["Degenerative spondylolisthesis L4-L5", "Transforaminal lumbar interbody fusion L4-L5"],
    ["Herniated nucleus pulposus L5-S1", "Microdiscectomy L5-S1"],
    ["Cervical spondylotic myelopathy C5-C6", "Anterior cervical discectomy and fusion C5-C6"]
  ],
  arthroplasty: [
    ["Primary osteoarthritis of knee, bilateral", "Total knee arthroplasty, right"],
    ["Avascular necrosis femoral head, left", "Total hip arthroplasty, left"],
    ["Periprosthetic joint infection, right knee", "Two-stage revision: resection and spacer, right knee"],
    ["Femoral neck fracture, right", "Bipolar hemiarthroplasty, right hip"]
  ],
  sports: [
    ["Anterior cruciate ligament tear, right knee", "Arthroscopic ACL reconstruction with hamstring autograft, right"],
    ["Medial meniscus tear, left knee", "Arthroscopic partial medial meniscectomy, left"],
    ["Rotator cuff tear, right shoulder", "Arthroscopic rotator cuff repair, right"],
    ["Recurrent anterior shoulder dislocation, left", "Arthroscopic Bankart repair, left"]
  ],
  hand: [
    ["Carpal tunnel syndrome, right", "Open carpal tunnel release, right"],
    ["Flexor tendon laceration zone II, left index", "Primary flexor tendon repair, left index"],
    ["Scaphoid nonunion, right", "Bone grafting and headless screw fixation, right scaphoid"],
    ["Trigger finger, right ring", "A1 pulley release, right ring finger"]
  ],
  foot: [
    ["Hallux valgus, left", "Scarf osteotomy with Akin osteotomy, left"],
    ["Achilles tendon rupture, right", "Open repair of Achilles tendon, right"],
    ["Diabetic foot ulcer with osteomyelitis, left", "Debridement and partial ray amputation, left foot"],
    ["Ankle fracture bimalleolar, right", "Open reduction internal fixation, right ankle"]
  ],
  pediatric: [
    ["Supracondylar humerus fracture Gartland III, left", "Closed reduction and percutaneous pinning, left elbow"],
    ["Developmental dysplasia of the hip, right", "Open reduction and Salter osteotomy, right hip"],
    ["Congenital talipes equinovarus, bilateral", "Percutaneous Achilles tenotomy, bilateral"],
    ["Slipped capital femoral epiphysis, left", "In-situ pinning, left hip"]
  ],
  oncology: [
    ["Osteosarcoma distal femur, right", "Wide excision and endoprosthetic reconstruction, right distal femur"],
    ["Giant cell tumour proximal tibia, left", "Curettage, high-speed burr and cement packing, left"],
    ["Metastatic bone disease femur, right", "Prophylactic intramedullary nailing, right femur"],
    ["Soft tissue sarcoma thigh, left", "Wide local excision, left thigh"]
  ],
  emergency: [
    ["Open fracture tibia, right", "Emergency debridement and external fixation, right tibia"],
    ["Septic arthritis of knee, left", "Arthroscopic irrigation and debridement, left knee"],
    ["Compartment syndrome of leg, right", "Emergency fasciotomy, right leg"],
    ["Necrotising fasciitis of thigh, left", "Radical debridement, left thigh"],
    ["Traumatic amputation of finger, right", "Revision amputation and stump closure, right"]
  ]
};

/* สุ่มแบบกำหนดเมล็ดได้ ผลลัพธ์เหมือนเดิมทุกครั้งที่รัน จะได้ทดสอบซ้ำได้ */
function rng(seed) {
  let x = seed >>> 0 || 1;
  return () => { x ^= x << 13; x ^= x >>> 17; x ^= x << 5; return ((x >>> 0) % 100000) / 100000; };
}
const iso = (d) => d.toISOString().slice(0, 10);
const pad = (n, w) => String(n).padStart(w, "0");

function buildCases() {
  const out = [];
  const today = new Date();
  today.setUTCHours(0, 0, 0, 0);
  for (let off = -DAYS_BACK; off <= DAYS_AHEAD; off++) {
    const d = new Date(today.getTime() + off * 86400000);
    const dow = d.getUTCDay();
    if (dow < 1 || dow > 5) continue;
    const day = iso(d);
    const r = rng(Number(day.replace(/-/g, "")));
    LISTS.filter(l => l[0] === dow).forEach(([, team, surgeon, sub], listIdx) => {
      const n = 2 + Math.floor(r() * 3);                  /* ลิสต์ละ 2–4 เคส */
      for (let k = 0; k < n; k++) {
        const pool = OPS[sub] || OPS.trauma;
        const [diagnosis, operation] = pool[(Math.floor(r() * pool.length) + k) % pool.length];
        const future = off > 0;
        out.push({
          id: "OR-" + day.replace(/-/g, "") + "-" + pad(listIdx, 2) + pad(k, 2),
          scheduledDate: day,
          orRoomName: "OR " + (1 + ((listIdx + k) % 8)),
          caseClass: sub === "emergency" ? "emergency" : "elective",
          status: future ? "scheduled" : "completed",
          subspecialty: sub === "emergency" ? "trauma" : sub,
          diagnosisText: diagnosis,
          operationText: operation,
          operativeSide: /right/i.test(operation) ? "right" : /left/i.test(operation) ? "left" : "",
          anesthesiaType: r() < 0.7 ? "general" : "regional",
          asaClass: 1 + Math.floor(r() * 3),
          estimatedDurationMin: 45 + Math.floor(r() * 8) * 15,
          hn: "MOCK-" + pad(100000 + Math.floor(r() * 899999), 6),
          age: 8 + Math.floor(r() * 80),
          sex: r() < 0.5 ? "male" : "female",
          primarySurgeonName: surgeon || "แพทย์เวรห้องผ่าตัดฉุกเฉิน",
          assistantSurgeonNames: [],                      /* ระบบคิวจริงยังไม่บันทึกผู้ช่วยผ่าตัด */
          createdByName: "ห้องผ่าตัด (ข้อมูลจำลอง)",
          complications: [],
          team,
          updatedAt: day + "T09:00:00Z"
        });
      }
    });
  }
  return out;
}

const ALL = buildCases();

function send(res, code, body, origin) {
  const payload = typeof body === "string" ? body : JSON.stringify(body);
  res.writeHead(code, {
    "Content-Type": "application/json; charset=utf-8",
    "Access-Control-Allow-Origin": origin || "*",
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Allow-Headers": "Content-Type, Accept, Authorization",
    "Cache-Control": "no-store"
  });
  res.end(payload);
}

const server = http.createServer(async (req, res) => {
  const origin = req.headers.origin || "*";
  if (req.method === "OPTIONS") return send(res, 204, "", origin);

  const u = new URL(req.url, "http://localhost");
  const p = u.pathname.replace(/\/$/, "") || "/";

  /* จำลองอาการเสียของระบบจริง ไว้ทดสอบว่าหน้าเว็บรับมืออย่างไร */
  const fail = u.searchParams.get("_fail");
  if (fail === "500")     return send(res, 500, { error: "internal error (จำลอง)" }, origin);
  if (fail === "401")     return send(res, 401, { error: "unauthorised (จำลอง)" }, origin);
  if (fail === "empty")   return send(res, 200, { cases: [] }, origin);
  if (fail === "garbage") return send(res, 200, { note: "ไม่มีเคสในคำตอบ (จำลอง)" }, origin);
  if (fail === "slow")    await new Promise(r => setTimeout(r, 30000));

  if (p === "/" || p === "/health")
    return send(res, 200, { ok: true, service: "or-queue-mock", cases: ALL.length,
                            range: [ALL[0]?.scheduledDate, ALL[ALL.length - 1]?.scheduledDate] }, origin);

  const one = p.match(/^\/api\/cases\/(.+)$/);
  if (one) {
    const hit = ALL.find(c => c.id === decodeURIComponent(one[1]));
    return hit ? send(res, 200, hit, origin) : send(res, 404, { error: "not found" }, origin);
  }

  if (p === "/api/cases") {
    const includeClosed = u.searchParams.get("includeClosed") !== "false";
    const scope = u.searchParams.get("scope") || "all";
    const from = u.searchParams.get("from"), to = u.searchParams.get("to");
    const today = iso(new Date());
    let list = ALL
      .filter(c => includeClosed || c.status !== "completed")
      .filter(c => scope !== "today" || c.scheduledDate === today)
      .filter(c => !from || c.scheduledDate >= from)
      .filter(c => !to || c.scheduledDate <= to);
    const limit = +(u.searchParams.get("limit") || 0);
    if (limit > 0) list = list.slice(0, limit);
    return send(res, 200, { scope, includeClosed, count: list.length, cases: list }, origin);
  }

  send(res, 404, { error: "unknown path", tried: p }, origin);
});

server.listen(PORT, "127.0.0.1", () => {
  /* พิมพ์พอร์ตที่ผูกได้จริง เพื่อให้ตั้ง PORT=0 แล้วให้ระบบเลือกพอร์ตว่างได้ */
  console.log("or-queue-mock: http://127.0.0.1:" + server.address().port + "  ·  " + ALL.length + " เคสจำลอง");
  console.log("  GET /api/cases?scope=all&includeClosed=true");
  console.log("  ทดสอบอาการเสีย: ?_fail=500 | 401 | empty | garbage | slow");
});
