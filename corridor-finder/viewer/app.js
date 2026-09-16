import * as THREE from "three";

const planEl = document.getElementById("plan");
const payloadEl = document.getElementById("payload");
const statusEl = document.getElementById("hud-status");

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
  _edt: null, // {shape:[nz,ny,nx], spacing:[sx,sy,sz], origin:[ox,oy,oz], data:Uint8Array}
  clearanceFor,
  moveHandle,
};

function worldToIjk(xyz) {
  const edt = window.CF._edt;
  const [ox, oy, oz] = edt.origin;
  const [sx, sy, sz] = edt.spacing;
  return [(xyz[0] - ox) / sx, (xyz[1] - oy) / sy, (xyz[2] - oz) / sz];
}

function sampleTrilinear(ijk) {
  const edt = window.CF._edt;
  const [nz, ny, nx] = edt.shape;
  const [i, j, k] = ijk; // i=x, j=y, k=z index space

  // Match scipy's map_coordinates(mode="constant", cval=0.0) used by
  // validate.py's Volume.sample_trilinear: any point outside the grid
  // bounds [0, dim-1] on any axis returns 0.0 rather than the nearest
  // edge voxel value. Clamping here would falsely report "safe" for a
  // point that has actually left the sampled volume.
  if (i < 0 || i > nx - 1 || j < 0 || j > ny - 1 || k < 0 || k > nz - 1) {
    return 0.0;
  }

  const x0 = Math.floor(i);
  const y0 = Math.floor(j);
  const z0 = Math.floor(k);
  const x1 = Math.min(x0 + 1, nx - 1);
  const y1 = Math.min(y0 + 1, ny - 1);
  const z1 = Math.min(z0 + 1, nz - 1);
  const tx = i - x0;
  const ty = j - y0;
  const tz = k - z0;

  const at = (x, y, z) => edt.data[z * ny * nx + y * nx + x];

  const c00 = at(x0, y0, z0) * (1 - tx) + at(x1, y0, z0) * tx;
  const c10 = at(x0, y1, z0) * (1 - tx) + at(x1, y1, z0) * tx;
  const c01 = at(x0, y0, z1) * (1 - tx) + at(x1, y0, z1) * tx;
  const c11 = at(x0, y1, z1) * (1 - tx) + at(x1, y1, z1) * tx;
  const c0 = c00 * (1 - ty) + c10 * ty;
  const c1 = c01 * (1 - ty) + c11 * ty;
  return c0 * (1 - tz) + c1 * tz;
}

// Mirrors the min-clearance logic in corridor_engine/validate.py:
// clearance = edt(mm) - radius, min over samples along the axis.
// breach = min_clearance < margin_mm (NOT < 0) -- same rule as validate.py.
function clearanceFor(screwId, entryXyz, targetXyz, diameterMm, marginMm) {
  if (!window.CF._edt) return null;
  const entry = new THREE.Vector3(...entryXyz);
  const target = new THREE.Vector3(...targetXyz);
  const length = entry.distanceTo(target);
  const stepMm = 1.0;
  const n = Math.max(2, Math.round(length / stepMm) + 1);
  const radius = diameterMm / 2.0;
  let minClearance = Infinity;
  for (let s = 0; s < n; s++) {
    const t = s / (n - 1);
    const p = [
      entry.x + t * (target.x - entry.x),
      entry.y + t * (target.y - entry.y),
      entry.z + t * (target.z - entry.z),
    ];
    const ijk = worldToIjk(p);
    const edtVal = sampleTrilinear(ijk);
    const clearance = edtVal - radius;
    if (clearance < minClearance) minClearance = clearance;
  }
  const screw = window.CF.screws.find((sc) => sc.screw_id === screwId);
  const effectiveMargin = marginMm != null ? marginMm : screw ? screw.margin_mm : 0;
  const breach = minClearance < effectiveMargin;
  if (screw) {
    screw.clearance_mm = minClearance;
    screw.breach = breach;
  }
  return { clearance_mm: minClearance, breach };
}

// TODO(round-4): pointer drag on the camera-facing plane to move handles
// interactively; for now this just recomputes clearance for a given target.
function moveHandle(screwId, which, xyz) {
  const screw = window.CF.screws.find((sc) => sc.screw_id === screwId);
  if (!screw) return null;
  if (which === "entry") screw.entry_xyz = xyz.slice();
  else if (which === "target") screw.target_xyz = xyz.slice();
  return clearanceFor(screwId, screw.entry_xyz, screw.target_xyz, screw.diameter_mm, screw.margin_mm);
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
  const headerJson = new TextDecoder().decode(new Uint8Array(buf, 4, headerLen));
  const header = JSON.parse(headerJson);
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

  if (header.edt) {
    const edtOffset = bodyStart + header.edt.offset;
    const data = new Uint8Array(buf.slice(edtOffset, edtOffset + header.edt.n_bytes));
    window.CF._edt = {
      shape: header.edt.shape,
      spacing: header.edt.spacing,
      origin: header.edt.origin,
      data,
    };
  }

  return meshes;
}

function buildScene(meshes) {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x101418);

  const light1 = new THREE.DirectionalLight(0xffffff, 1.2);
  light1.position.set(1, 1, 1);
  scene.add(light1);
  scene.add(new THREE.AmbientLight(0xffffff, 0.4));

  const group = new THREE.Group();
  for (const m of meshes) {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(m.vertices, 3));
    geometry.setIndex(new THREE.BufferAttribute(m.faces, 1));
    geometry.computeVertexNormals();
    const material = new THREE.MeshPhongMaterial({
      color: 0xd8c9a8,
      transparent: true,
      opacity: 0.55,
      side: THREE.DoubleSide,
    });
    const mesh = new THREE.Mesh(geometry, material);
    group.add(mesh);
  }
  scene.add(group);
  return { scene, group };
}

function setupCamera(canvas) {
  const camera = new THREE.PerspectiveCamera(45, canvas.clientWidth / canvas.clientHeight, 0.1, 5000);
  camera.position.set(150, 150, 300);

  // Minimal hand-rolled orbit: drag rotates around origin, wheel zooms.
  const state = { dragging: false, lastX: 0, lastY: 0, radius: camera.position.length(), theta: Math.PI / 4, phi: Math.PI / 3 };

  function updateCameraPosition() {
    camera.position.set(
      state.radius * Math.sin(state.phi) * Math.cos(state.theta),
      state.radius * Math.cos(state.phi),
      state.radius * Math.sin(state.phi) * Math.sin(state.theta)
    );
    camera.lookAt(0, 0, 0);
  }

  canvas.addEventListener("mousedown", (e) => {
    state.dragging = true;
    state.lastX = e.clientX;
    state.lastY = e.clientY;
  });
  window.addEventListener("mouseup", () => (state.dragging = false));
  window.addEventListener("mousemove", (e) => {
    if (!state.dragging) return;
    const dx = e.clientX - state.lastX;
    const dy = e.clientY - state.lastY;
    state.lastX = e.clientX;
    state.lastY = e.clientY;
    state.theta -= dx * 0.005;
    state.phi = Math.min(Math.max(state.phi - dy * 0.005, 0.05), Math.PI - 0.05);
    updateCameraPosition();
  });
  canvas.addEventListener("wheel", (e) => {
    state.radius = Math.max(10, state.radius + e.deltaY * 0.2);
    updateCameraPosition();
  });

  updateCameraPosition();
  return camera;
}

async function main() {
  const canvas = document.getElementById("viewer-canvas");
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setSize(canvas.clientWidth || window.innerWidth, canvas.clientHeight || window.innerHeight);

  const camera = setupCamera(canvas);

  window.addEventListener("resize", () => {
    const w = window.innerWidth;
    const h = window.innerHeight;
    renderer.setSize(w, h);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  });

  const meshes = await decodePayload();
  const { scene } = buildScene(meshes);

  for (const screw of window.CF.screws) {
    clearanceFor(screw.screw_id, screw.entry_xyz, screw.target_xyz, screw.diameter_mm, screw.margin_mm);
  }

  window.CF.ready = true;
  const breachCount = window.CF.screws.filter((s) => s.breach).length;
  statusEl.textContent = `${meshes.length} mesh(es) loaded`;
  statusEl.classList.toggle("breach", breachCount > 0);
  if (breachCount > 0) {
    statusEl.textContent += ` — ${breachCount} screw(s) BREACH`;
  }

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
