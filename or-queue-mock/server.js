#!/usr/bin/env node
/* ตัวจำลอง API ของระบบคิวห้องผ่าตัด — ใช้พัฒนาและทดสอบหน้าแฟ้มสะสมงานโดยไม่ต้องต่อ intranet ของโรงพยาบาล
 *
 *   node or-queue-mock/server.js            เปิดที่พอร์ต 8088
 *   PORT=9000 node or-queue-mock/server.js
 *   PORT=0    ให้ระบบเลือกพอร์ตว่างเอง แล้วอ่านพอร์ตจากบรรทัดที่พิมพ์ออกมา
 *
 * แล้วตั้งที่หน้า "ตั้งค่าการเชื่อมต่อ" ของแอป: ที่อยู่ API = http://127.0.0.1:8088
 *
 * รูปร่างข้อมูลและชื่อฟิลด์ ทาบมาจากหน้าสาธิตของระบบคิวจริงในที่เก็บนี้ (index.html ที่ราก)
 * โดยอ่านจาก __ORQ_SNAPSHOT__ ของจริง ไม่ได้เดาเอา — รวมถึงค่าที่เป็น null ได้ และฟิลด์ที่
 * หน้าแฟ้มสะสมงานตั้งใจไม่อ่าน เช่น patientName ซึ่งมีอยู่จริงในระบบคิว
 *
 * ไม่มี dependency ตั้งใจให้รันได้ด้วย node เปล่า ๆ เหมือน sync-server
 * ผู้ป่วยเป็นข้อมูลสมมติทั้งหมด — ชื่ออาจารย์กับวันผ่าตัดอิงตารางจริงของกลุ่มงาน
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

/* ชื่อผู้ป่วยสมมติ — ระบบคิวจริงเก็บชื่อไว้ หน้าแฟ้มสะสมงานตั้งใจไม่อ่านฟิลด์นี้
   ใส่ไว้ในตัวจำลองด้วย เพื่อให้พิสูจน์ได้ว่ามันไม่ถูกนำเข้าจริง ๆ ไม่ใช่เพราะไม่มีข้อมูลให้อ่าน */
const TITLES = ["นาย", "นาง", "นางสาว"];
const GIVEN = ["สมบัติ", "บุญมี", "ประหยัด", "วิไล", "สมพงษ์", "จันทร์เพ็ญ", "อุดม", "รัตนา"];
const FAMILY = ["วงศ์ใหญ่", "ศรีสุข", "ทองดี", "แก้วมณี", "พูนทรัพย์", "ใจงาม"];

/* ระบบคิวใช้คำของตัวเอง: foot_ankle และ tumour ไม่ใช่ foot/oncology
   หน้าแฟ้มสะสมงานมี QUEUE_SUB_MAP แปลงให้อยู่แล้ว ตัวจำลองจึงส่งคำของระบบคิวไปตรง ๆ */
const QUEUE_SUB = { hand:"hand", sports:"sports", trauma:"trauma", spine:"spine",
                    foot:"foot_ankle", arthroplasty:"arthroplasty", oncology:"tumour",
                    pediatric:"pediatric", emergency:"trauma" };
const ANAES = ["ga", "spinal", "regional_block", "local_sedation", null];

function buildCases() {
  const out = [];
  const today = new Date();
  today.setUTCHours(0, 0, 0, 0);
  let id = 1000;
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
        const past = off < 0;
        /* บางเคสยังไม่ได้ลงตาราง — ระบบคิวจริงปล่อย scheduledDate กับ orRoomName เป็น null */
        const unscheduled = !past && r() < 0.12;
        out.push({
          id: ++id,
          scheduledDate: unscheduled ? null : day,
          orRoomId: unscheduled ? null : 1 + ((listIdx + k) % 8),
          orRoomName: unscheduled ? null : "OR " + (1 + ((listIdx + k) % 8)),
          orderIndex: k,
          caseClass: sub === "emergency" ? "emergency" : "elective",
          status: past ? "done" : "booked",
          readiness: past ? "green" : ["green", "amber", "red"][Math.floor(r() * 3)],
          subspecialty: QUEUE_SUB[sub] || "trauma",
          diagnosisText: diagnosis,
          diagnoses: [],
          operationText: operation,
          procedures: [],
          operativeSide: /right/i.test(operation) ? "right" : /left/i.test(operation) ? "left" : "",
          lateralityWarning: null,
          anesthesiaType: ANAES[Math.floor(r() * ANAES.length)],
          asaClass: String(1 + Math.floor(r() * 3)),
          estimatedDurationMin: 45 + Math.floor(r() * 8) * 15,
          position: "supine",
          tourniquetRequired: r() < 0.4,
          cArmRequired: r() < 0.6,
          npoStatus: "NPO หลังเที่ยงคืน",
          consentSigned: past || r() < 0.8,
          labsDone: past || r() < 0.9,
          imagingAvailable: true,
          antibioticOrdered: past || r() < 0.7,
          /* ข้อมูลผู้ป่วย — สมมติทั้งหมด HN ขึ้นต้นด้วย MOCK- ให้เห็นชัดว่าไม่ใช่ของจริง */
          hn: "MOCK-" + pad(100000 + Math.floor(r() * 899999), 6),
          patientName: TITLES[Math.floor(r() * 3)] + " " + GIVEN[Math.floor(r() * GIVEN.length)] +
                       " " + FAMILY[Math.floor(r() * FAMILY.length)],
          age: 8 + Math.floor(r() * 80),
          sex: r() < 0.5 ? "male" : "female",
          wardId: 1 + Math.floor(r() * 6),
          wardName: sub === "emergency" ? "ห้องฉุกเฉิน" : "หอผู้ป่วยออร์โธปิดิกส์",
          primarySurgeonId: 1 + listIdx,
          primarySurgeonName: surgeon || "แพทย์เวรห้องผ่าตัดฉุกเฉิน",
          assistantSurgeonIds: [],
          assistantSurgeonNames: [],                      /* ระบบคิวจริงยังไม่บันทึกผู้ช่วยผ่าตัด */
          createdById: 5,
          createdByName: "ห้องผ่าตัด (ข้อมูลจำลอง)",
          complications: [],
          complicationReviewStatus: "not_reviewed",
          implants: [], bloodRequests: [], consultations: [],
          notes: "", statusReason: "", sourceRef: "", sourceSystem: "",
          isHistorical: past, redacted: false,
          team,
          createdAt: day + "T07:30:00Z",
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

  /* ระบบคิวจริงมีเส้นทางเหล่านี้ ใส่ไว้ให้ครบเผื่อทดสอบ */
  if (p === "/api/auth/me")
    return send(res, 200, { user: { id: 5, username: "mock", fullName: "ผู้ใช้จำลอง",
                                    role: "resident", isAdmin: false }, demoMode: true }, origin);

  const hist = p.match(/^\/api\/cases\/(\d+)\/history$/);
  if (hist) {
    const c = ALL.find(x => String(x.id) === hist[1]);
    if (!c) return send(res, 404, { error: "not found" }, origin);
    return send(res, 200, { caseId: c.id, history: [
      { at: c.createdAt, action: "created", byName: c.createdByName },
      { at: c.updatedAt, action: c.status === "done" ? "marked done" : "booked", byName: c.primarySurgeonName }
    ] }, origin);
  }

  const one = p.match(/^\/api\/cases\/(\d+)$/);
  if (one) {
    const hit = ALL.find(c => String(c.id) === one[1]);
    return hit ? send(res, 200, hit, origin) : send(res, 404, { error: "not found" }, origin);
  }

  if (p === "/api/cases") {
    const includeClosed = u.searchParams.get("includeClosed") !== "false";
    const scope = u.searchParams.get("scope") || "all";
    const from = u.searchParams.get("from"), to = u.searchParams.get("to");
    const today = iso(new Date());
    let list = ALL
      .filter(c => includeClosed || c.status !== "done")
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
