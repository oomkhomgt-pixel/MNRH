import * as THREE from "three";
import { clearanceAlongAxis } from "clearance";

// World coordinates are RAS in mm (x = patient right, y = anterior,
// z = superior), as everywhere in Corridor Finder.

const planEl = document.getElementById("plan");
const payloadEl = document.getElementById("payload");
const statusEl = document.getElementById("hud-status");
const screwsEl = document.getElementById("hud-screws");

const plan = JSON.parse(planEl.textContent);

window.CF = {
  ready: false,
  screws: (plan.screws || []).map((s) => ({
    screw_id: s.screw_id,
    entry_xyz: s.entry_xyz.slice(),
    target_xyz: s.target_xyz.slice(),
    diameter_mm: s.diameter_mm,
    margin_mm: s.margin_mm,
    clearance_mm: null,
    breach: null,
  })),
  // screw_id -> that screw's own distance field, exactly the one Slicer
  // validated it against (cropped around the screw, rounded down):
  // {shape:[nz,ny,nx], spacing:[sx,sy,sz], origin:[ox,oy,oz], scale_mm, data}
  _edts: {},
  clearanceFor,
  moveHandle,
};

// The breach decision itself lives in clearance.js (mirrors validate.py).
// A screw without an exported distance field is "not checked" (breach
// null), never "safe".
function clearanceFor(screwId, entryXyz, targetXyz, diameterMm, marginMm) {
  const screw = window.CF.screws.find((sc) => sc.screw_id === screwId);
  const edt = window.CF._edts[screwId];
  if (!edt) {
    if (screw) {
      screw.clearance_mm = null;
      screw.breach = null;
    }
    return null;
  }
  const margin = marginMm != null ? marginMm : screw ? screw.margin_mm : 0;
  const result = clearanceAlongAxis(edt, entryXyz, targetXyz, diameterMm, margin);
  if (screw) {
    screw.clearance_mm = result.clearance_mm;
    screw.breach = result.breach;
  }
  return result;
}

// TODO: pointer dragging of the handles; for now handles move only through
// this hook, which re-checks the clearance and redraws.
function moveHandle(screwId, which, xyz) {
  const screw = window.CF.screws.find((sc) => sc.screw_id === screwId);
  if (!screw) return null;
  if (which === "entry") screw.entry_xyz = xyz.slice();
  else if (which === "target") screw.target_xyz = xyz.slice();
  const result = clearanceFor(screwId, screw.entry_xyz, screw.target_xyz, screw.diameter_mm, screw.margin_mm);
  if (window.CF._redraw) window.CF._redraw();
  return result;
}

async function decodePayload() {
  const b64 = payloadEl.textContent.trim();
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);

  const ds = new DecompressionStream("gzip");
  const stream = new Blob([bytes]).stream().pipeThrough(ds);
  const buf = await new Response(stream).arrayBuffer();
  const view = new DataView(buf);

  const headerLen = view.getUint32(0, true);
  const header = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 4, headerLen)));
  const bodyStart = 4 + headerLen;

  const meshes = [];
  for (const m of header.meshes) {
    const vertBytes = m.n_vertices * 3 * 4;
    const faceBytes = m.n_faces * 3 * 4;
    const vertOffset = bodyStart + m.offset;
    const vertices = new Float32Array(buf.slice(vertOffset, vertOffset + vertBytes));
    const faces = new Uint32Array(buf.slice(vertOffset + vertBytes, vertOffset + vertBytes + faceBytes));
    meshes.push({ label: m.label, name: m.name, vertices, faces });
  }

  for (const e of header.edts || []) {
    const start = bodyStart + e.offset;
    window.CF._edts[e.screw_id] = {
      shape: e.shape,
      spacing: e.spacing,
      origin: e.origin,
      scale_mm: e.scale_mm,
      data: new Uint8Array(buf.slice(start, start + e.n_bytes)),
    };
  }
  return meshes;
}

const COLOR = { safe: 0x22c55e, breach: 0xef4444, unchecked: 0xf59e0b };

function screwColor(screw) {
  if (screw.breach === null) return COLOR.unchecked;
  return screw.breach ? COLOR.breach : COLOR.safe;
}

function buildBones(meshes) {
  const group = new THREE.Group();
  for (const m of meshes) {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(m.vertices, 3));
    geometry.setIndex(new THREE.BufferAttribute(m.faces, 1));
    geometry.computeVertexNormals();
    const material = new THREE.MeshPhongMaterial({
      color: 0xd8c9a8,
      transparent: true,
      opacity: 0.35,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    group.add(new THREE.Mesh(geometry, material));
  }
  return group;
}

// One cylinder of the screw's diameter from entry to target, plus a small
// sphere on each handle, coloured by the current clearance verdict.
function buildScrews() {
  const group = new THREE.Group();
  for (const s of window.CF.screws) {
    const a = new THREE.Vector3(...s.entry_xyz);
    const b = new THREE.Vector3(...s.target_xyz);
    const axis = new THREE.Vector3().subVectors(b, a);
    const material = new THREE.MeshPhongMaterial({ color: screwColor(s) });
    const shaft = new THREE.Mesh(new THREE.CylinderGeometry(s.diameter_mm / 2, s.diameter_mm / 2, axis.length(), 24), material);
    shaft.position.copy(a).addScaledVector(axis, 0.5);
    shaft.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), axis.clone().normalize());
    group.add(shaft);
    for (const p of [a, b]) {
      const handle = new THREE.Mesh(new THREE.SphereGeometry(Math.max(2.0, s.diameter_mm * 0.5), 16, 12), material);
      handle.position.copy(p);
      group.add(handle);
    }
  }
  return group;
}

function updateHud(meshCount) {
  const breaches = window.CF.screws.filter((s) => s.breach === true).length;
  const unchecked = window.CF.screws.filter((s) => s.breach === null).length;
  let text = `${meshCount} bone mesh(es), ${window.CF.screws.length} screw(s)`;
  if (breaches > 0) text += ` — ${breaches} BREACH`;
  if (unchecked > 0) text += ` — ${unchecked} not checked`;
  statusEl.textContent = text;
  statusEl.classList.toggle("breach", breaches > 0);
  screwsEl.replaceChildren(
    ...window.CF.screws.map((s) => {
      const row = document.createElement("div");
      if (s.breach === null) {
        row.className = "unchecked";
        row.textContent = `${s.screw_id}: not checked (no distance field)`;
      } else {
        row.className = s.breach ? "breach" : "ok";
        row.textContent = `${s.screw_id}: clearance ${s.clearance_mm.toFixed(1)} mm, margin ${s.margin_mm.toFixed(1)} mm${s.breach ? " — BREACH" : ""}`;
      }
      return row;
    })
  );
}

// Orbit around the model with superior (+z) up, starting from the front
// (anterior) so the patient's right is on the screen's left, as in an AP
// radiograph. Drag rotates, the wheel zooms.
function setupCamera(canvas, center, size) {
  const camera = new THREE.PerspectiveCamera(40, canvas.clientWidth / canvas.clientHeight, 1, 20 * size);
  camera.up.set(0, 0, 1);
  const state = { dragging: false, lastX: 0, lastY: 0, radius: 1.8 * size, theta: Math.PI / 2, phi: Math.PI / 2 };

  function update() {
    camera.position.set(
      center.x + state.radius * Math.sin(state.phi) * Math.cos(state.theta),
      center.y + state.radius * Math.sin(state.phi) * Math.sin(state.theta),
      center.z + state.radius * Math.cos(state.phi)
    );
    camera.lookAt(center);
  }

  canvas.addEventListener("mousedown", (e) => {
    state.dragging = true;
    state.lastX = e.clientX;
    state.lastY = e.clientY;
  });
  window.addEventListener("mouseup", () => (state.dragging = false));
  window.addEventListener("mousemove", (e) => {
    if (!state.dragging) return;
    state.theta -= (e.clientX - state.lastX) * 0.005;
    state.phi = Math.min(Math.max(state.phi - (e.clientY - state.lastY) * 0.005, 0.05), Math.PI - 0.05);
    state.lastX = e.clientX;
    state.lastY = e.clientY;
    update();
  });
  canvas.addEventListener("wheel", (e) => {
    state.radius = Math.max(0.2 * size, state.radius * (1 + e.deltaY * 0.001));
    update();
  });
  update();
  return camera;
}

async function main() {
  const canvas = document.getElementById("viewer-canvas");
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setSize(canvas.clientWidth || window.innerWidth, canvas.clientHeight || window.innerHeight);

  const meshes = await decodePayload();
  for (const s of window.CF.screws) {
    clearanceFor(s.screw_id, s.entry_xyz, s.target_xyz, s.diameter_mm, s.margin_mm);
  }

  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x101418);
  scene.add(new THREE.AmbientLight(0xffffff, 0.5));
  const bones = buildBones(meshes);
  scene.add(bones);
  let screws = buildScrews();
  scene.add(screws);

  const box = new THREE.Box3().setFromObject(bones).union(new THREE.Box3().setFromObject(screws));
  const center = box.isEmpty() ? new THREE.Vector3() : box.getCenter(new THREE.Vector3());
  const size = box.isEmpty() ? 200 : Math.max(...box.getSize(new THREE.Vector3()).toArray(), 50);
  const camera = setupCamera(canvas, center, size);
  const headlight = new THREE.DirectionalLight(0xffffff, 1.0);
  camera.add(headlight);
  scene.add(camera);

  window.CF._redraw = () => {
    scene.remove(screws);
    screws = buildScrews();
    scene.add(screws);
    updateHud(meshes.length);
  };

  window.addEventListener("resize", () => {
    renderer.setSize(window.innerWidth, window.innerHeight);
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
  });

  updateHud(meshes.length);
  window.CF.ready = true;

  function animate() {
    requestAnimationFrame(animate);
    renderer.render(scene, camera);
  }
  animate();
}

main().catch((err) => {
  statusEl.textContent = "error: " + err.message;
  throw err;
});
