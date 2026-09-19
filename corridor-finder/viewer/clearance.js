// Screw validation for the exported viewer: the one place the viewer decides
// "breach". It repeats corridor_engine/validate.py and cortex.py operation
// for operation (same sample points, nearest-voxel lookups, integer voxel
// sums and an exact distance transform), so it reaches the same verdict as
// Slicer; keep them identical. The rule (DECISIONS.md section 1):
//   - the screw starts where its axis crosses the outer cortex and runs a
//     catalogue length: the longest ending before the target handle
//     ("inside"), or the shortest reaching past the far cortex ("through");
//   - clearance = distance field (mm) - screw radius, trilinear-sampled
//     every ~1 mm; breach when the minimum is below the screw's OWN margin,
//     NOT merely below zero;
//   - near a crossed cortex only the non-bone outside it is ignored.
// The only difference from validate.py: the plain distance field arrives
// rounded down to 0.1 mm, so the viewer's clearance can be up to 0.1 mm
// lower (stricter), never higher. A computation that needs voxels outside
// the exported crop is refused ("out of region"), never guessed.
// tests/python/test_viewer_clearance_golden.py runs this file under Node
// against validate.py on identical screws.
//
// field: { shape: [nz, ny, nx], index_offset: [i0, j0, k0], full_shape,
//          full_origin: [ox, oy, oz], spacing: [sx, sy, sz], scale_mm,
//          data: Uint8Array } -- the screw's own distance field as exported
// by corridor_engine/export_viewer.py: a crop (C order) of the CT-sized
// field whose voxel (0, 0, 0) is full-grid voxel index_offset.

export const CROSSING_STEP_MM = 0.1;
export const MAX_SEARCH_MM = 20.0;
export const NORMAL_RADIUS_MM = 4.0;
export const COS_OBLIQUE = 0.5;
export const CORTEX_DEPTH_TOLERANCE_MM = 1.5; // PROVISIONAL, DECISIONS.md 1.2a
export const MAX_PROTRUSION_MM = 5.0;
export const HANDLE_OFF_CORTEX_WARN_MM = 2.0;
export const UNCHECKED_ENTRY_CODES = ["entry_cortex_not_found", "entry_not_outer"];
const LENGTH_EPS_MM = 1e-9;
// The viewer calls a breach this much before validate.py would: its exact
// distance transform can round differently from scipy's in the last bit,
// and it must never be the more lenient of the two.
const BREACH_EPS_MM = 1e-9;

class OutOfRegion extends Error {}

// Python's round() sends halves to the even neighbour; match it so both
// sides sample exactly the same points.
function pyRound(x) {
  const f = Math.floor(x);
  const d = x - f;
  if (d > 0.5) return f + 1;
  if (d < 0.5) return f;
  return f % 2 === 0 ? f : f + 1;
}

const dot3 = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const sub3 = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];

function unit3(v) {
  const n = Math.sqrt(dot3(v, v));
  return n > 0 ? [v[0] / n, v[1] / n, v[2] / n] : v.slice();
}

// ---- the exported field ------------------------------------------------------

// Quantized value (0.1 mm steps) at full-grid voxel (i, j, k); null outside
// the CT, OutOfRegion outside the exported crop.
function stepsAt(f, i, j, k) {
  const [NZ, NY, NX] = f.full_shape;
  if (i < 0 || i >= NX || j < 0 || j >= NY || k < 0 || k >= NZ) return null;
  const [nz, ny, nx] = f.shape;
  const a = i - f.index_offset[0];
  const b = j - f.index_offset[1];
  const c = k - f.index_offset[2];
  if (a < 0 || a >= nx || b < 0 || b >= ny || c < 0 || c >= nz) throw new OutOfRegion();
  return f.data[(c * ny + b) * nx + a];
}

function isBone(f, i, j, k) {
  const v = stepsAt(f, i, j, k);
  return v !== null && v > 0;
}

function nearestVoxel(f, p) {
  const o = f.full_origin;
  const s = f.spacing;
  return [
    Math.floor((p[0] - o[0]) / s[0] + 0.5),
    Math.floor((p[1] - o[1]) / s[1] + 0.5),
    Math.floor((p[2] - o[2]) / s[2] + 0.5),
  ];
}

function inside(f, p) {
  const [i, j, k] = nearestVoxel(f, p);
  return isBone(f, i, j, k);
}

function trilinear(at, tx, ty, tz, x0, y0, z0, x1, y1, z1) {
  const c00 = at(x0, y0, z0) * (1 - tx) + at(x1, y0, z0) * tx;
  const c10 = at(x0, y1, z0) * (1 - tx) + at(x1, y1, z0) * tx;
  const c01 = at(x0, y0, z1) * (1 - tx) + at(x1, y0, z1) * tx;
  const c11 = at(x0, y1, z1) * (1 - tx) + at(x1, y1, z1) * tx;
  const c0 = c00 * (1 - ty) + c10 * ty;
  const c1 = c01 * (1 - ty) + c11 * ty;
  return c0 * (1 - tz) + c1 * tz;
}

// Trilinear sample (mm) of the exported field. Outside the CT returns 0
// (which reads as a breach), at most scipy's partial blend with its zero
// border, so never more lenient than validate.py.
function samplePlain(f, p) {
  const [NZ, NY, NX] = f.full_shape;
  const o = f.full_origin;
  const s = f.spacing;
  const i = (p[0] - o[0]) / s[0];
  const j = (p[1] - o[1]) / s[1];
  const k = (p[2] - o[2]) / s[2];
  if (!(i >= 0 && i <= NX - 1 && j >= 0 && j <= NY - 1 && k >= 0 && k <= NZ - 1)) return 0.0;
  const x0 = Math.floor(i);
  const y0 = Math.floor(j);
  const z0 = Math.floor(k);
  const at = (x, y, z) => stepsAt(f, x, y, z);
  return trilinear(at, i - x0, j - y0, k - z0, x0, y0, z0, Math.min(x0 + 1, NX - 1), Math.min(y0 + 1, NY - 1), Math.min(z0 + 1, NZ - 1)) * f.scale_mm;
}

// ---- cortex.py ---------------------------------------------------------------

// cortex._outer_surface: no bone within MAX_SEARCH_MM beyond a crossing,
// otherwise the crossing is a gap inside the bone and is not exempted.
function outerSurface(f, crossing, outward) {
  const n = Math.floor(MAX_SEARCH_MM / CROSSING_STEP_MM + 1e-9) + 1;
  for (let s = 1; s < n; s++) {
    const t = s * CROSSING_STEP_MM;
    if (inside(f, [crossing[0] + t * outward[0], crossing[1] + t * outward[1], crossing[2] + t * outward[2]])) return false;
  }
  return true;
}

function entryCrossing(f, entry, target) {
  const u = unit3(sub3(target, entry));
  const back = [-u[0], -u[1], -u[2]];
  let point = null;
  let offset = 0.0;
  if (!inside(f, entry)) {
    const d = sub3(target, entry);
    const n = Math.floor(Math.sqrt(dot3(d, d)) / CROSSING_STEP_MM + 1e-9) + 1;
    for (let s = 0; s < n && point === null; s++) {
      const t = s * CROSSING_STEP_MM;
      const p = [entry[0] + t * u[0], entry[1] + t * u[1], entry[2] + t * u[2]];
      if (inside(f, p)) {
        point = p;
        offset = t;
      }
    }
    if (point === null) return { point: null, offset: 0.0, problem: "no_bone" };
  } else {
    const n = Math.floor(MAX_SEARCH_MM / CROSSING_STEP_MM + 1e-9) + 1;
    let prev = null;
    let prevT = 0.0;
    for (let s = 0; s < n && point === null; s++) {
      const t = s * CROSSING_STEP_MM;
      const p = [entry[0] + t * back[0], entry[1] + t * back[1], entry[2] + t * back[2]];
      if (!inside(f, p)) {
        point = prev;
        offset = -prevT;
      }
      prev = p;
      prevT = t;
    }
    if (point === null) return { point: null, offset: -MAX_SEARCH_MM, problem: "cortex_not_found" };
  }
  return { point, offset, problem: outerSurface(f, point, back) ? null : "entry_not_outer" };
}

function exitCrossing(f, start, target) {
  const u = unit3(sub3(target, start));
  let point = null;
  if (inside(f, target)) {
    const n = Math.floor(MAX_SEARCH_MM / CROSSING_STEP_MM + 1e-9) + 1;
    let prev = null;
    for (let s = 0; s < n && point === null; s++) {
      const t = s * CROSSING_STEP_MM;
      const p = [target[0] + t * u[0], target[1] + t * u[1], target[2] + t * u[2]];
      if (!inside(f, p)) point = prev;
      prev = p;
    }
  } else {
    const d = sub3(target, start);
    const n = Math.floor(Math.sqrt(dot3(d, d)) / CROSSING_STEP_MM + 1e-9) + 1;
    for (let s = 0; s < n && point === null; s++) {
      const t = s * CROSSING_STEP_MM;
      const p = [target[0] + t * -u[0], target[1] + t * -u[1], target[2] + t * -u[2]];
      if (inside(f, p)) point = p;
    }
  }
  if (point === null) return { point: null, problem: null };
  return { point, problem: outerSurface(f, point, u) ? null : "exit_not_outer" };
}

function inwardNormal(f, point) {
  const o = f.full_origin;
  const sp = f.spacing;
  const [NZ, NY, NX] = f.full_shape;
  const c = nearestVoxel(f, point);
  const h = [Math.ceil(NORMAL_RADIUS_MM / sp[0]), Math.ceil(NORMAL_RADIUS_MM / sp[1]), Math.ceil(NORMAL_RADIUS_MM / sp[2])];
  const lo = [Math.max(c[0] - h[0], 0), Math.max(c[1] - h[1], 0), Math.max(c[2] - h[2], 0)];
  const hi = [Math.min(c[0] + h[0], NX - 1), Math.min(c[1] + h[1], NY - 1), Math.min(c[2] + h[2], NZ - 1)];
  if (hi[0] < lo[0] || hi[1] < lo[1] || hi[2] < lo[2]) return null;
  const r2 = NORMAL_RADIUS_MM * NORMAL_RADIUS_MM;
  let count = 0;
  let si = 0;
  let sj = 0;
  let sk = 0;
  for (let k = lo[2]; k <= hi[2]; k++) {
    const dz = o[2] + k * sp[2] - point[2];
    for (let j = lo[1]; j <= hi[1]; j++) {
      const dy = o[1] + j * sp[1] - point[1];
      for (let i = lo[0]; i <= hi[0]; i++) {
        const dx = o[0] + i * sp[0] - point[0];
        if (dx * dx + dy * dy + dz * dz <= r2 && isBone(f, i, j, k)) {
          count++;
          si += i;
          sj += j;
          sk += k;
        }
      }
    }
  }
  if (count === 0) return null;
  const d = [o[0] + (si / count) * sp[0] - point[0], o[1] + (sj / count) * sp[1] - point[1], o[2] + (sk / count) * sp[2] - point[2]];
  const n = Math.sqrt(dot3(d, d));
  return n > 1e-9 ? [d[0] / n, d[1] / n, d[2] / n] : null;
}

function zoneLength(radius, margin, cos) {
  return (radius + margin + CORTEX_DEPTH_TOLERANCE_MM) / Math.max(cos, COS_OBLIQUE);
}

function angleDeg(cos) {
  return (Math.acos(Math.min(Math.max(cos, -1.0), 1.0)) * 180.0) / Math.PI;
}

function boxHalf(radius, margin, spacing) {
  const diag = Math.sqrt(dot3(spacing, spacing));
  return 3.0 * (radius + margin) + 2.0 * CORTEX_DEPTH_TOLERANCE_MM + MAX_PROTRUSION_MM + 2.0 * diag;
}

// Exact 1-D squared distance transform (Felzenszwalb & Huttenlocher) of f
// with sample spacing s: d[q] = min over p of ((q - p) s)^2 + f[p].
function dt1d(f, n, s, d, v, z) {
  let k = -1;
  for (let q = 0; q < n; q++) {
    if (f[q] === Infinity) continue;
    const fq = f[q] + q * s * (q * s);
    if (k < 0) {
      k = 0;
      v[0] = q;
      z[0] = -Infinity;
      z[1] = Infinity;
      continue;
    }
    let r = v[k];
    let x = (fq - (f[r] + r * s * (r * s))) / (2 * s * (q - r));
    while (x <= z[k]) {
      k--;
      r = v[k];
      x = (fq - (f[r] + r * s * (r * s))) / (2 * s * (q - r));
    }
    k++;
    v[k] = q;
    z[k] = x;
    z[k + 1] = Infinity;
  }
  if (k < 0) {
    for (let q = 0; q < n; q++) d[q] = Infinity;
    return;
  }
  k = 0;
  for (let q = 0; q < n; q++) {
    while (z[k + 1] < q * s) k++;
    const dq = (q - v[k]) * s;
    d[q] = dq * dq + f[v[k]];
  }
}

// Exact Euclidean distance (mm) from each solid voxel to the nearest
// non-solid one (0 on non-solid voxels), like scipy's distance_transform_edt.
// Exported for tests/node/clearance_golden.mjs.
export function edt3d(solid, nz, ny, nx, sx, sy, sz) {
  const g = new Float64Array(nz * ny * nx);
  for (let t = 0; t < g.length; t++) g[t] = solid[t] ? Infinity : 0.0;
  const m = Math.max(nx, ny, nz);
  const f = new Float64Array(m);
  const d = new Float64Array(m);
  const v = new Int32Array(m);
  const z = new Float64Array(m + 1);
  for (let k = 0; k < nz; k++)
    for (let j = 0; j < ny; j++) {
      const base = (k * ny + j) * nx;
      for (let i = 0; i < nx; i++) f[i] = g[base + i];
      dt1d(f, nx, sx, d, v, z);
      for (let i = 0; i < nx; i++) g[base + i] = d[i];
    }
  for (let k = 0; k < nz; k++)
    for (let i = 0; i < nx; i++) {
      for (let j = 0; j < ny; j++) f[j] = g[(k * ny + j) * nx + i];
      dt1d(f, ny, sy, d, v, z);
      for (let j = 0; j < ny; j++) g[(k * ny + j) * nx + i] = d[j];
    }
  for (let j = 0; j < ny; j++)
    for (let i = 0; i < nx; i++) {
      for (let k = 0; k < nz; k++) f[k] = g[(k * ny + j) * nx + i];
      dt1d(f, nz, sz, d, v, z);
      for (let k = 0; k < nz; k++) g[(k * ny + j) * nx + i] = Math.sqrt(d[k]);
    }
  return g;
}

// cortex.exempt_field: distance to the nearest non-bone voxel that is not
// outside (or less than the tolerance inside) any of the planes, in a box
// around the first plane's point plus a one-voxel border.
function exemptField(f, planes, half) {
  const o = f.full_origin;
  const sp = f.spacing;
  const [NZ, NY, NX] = f.full_shape;
  const c = nearestVoxel(f, planes[0].point);
  const h = [Math.ceil(half / sp[0]), Math.ceil(half / sp[1]), Math.ceil(half / sp[2])];
  const lo = [Math.max(c[0] - h[0], 0), Math.max(c[1] - h[1], 0), Math.max(c[2] - h[2], 0)];
  const hi = [Math.min(c[0] + h[0], NX - 1), Math.min(c[1] + h[1], NY - 1), Math.min(c[2] + h[2], NZ - 1)];
  const nx = hi[0] - lo[0] + 3;
  const ny = hi[1] - lo[1] + 3;
  const nz = hi[2] - lo[2] + 3;
  const solid = new Uint8Array(nz * ny * nx);
  for (let k = 1; k < nz - 1; k++)
    for (let j = 1; j < ny - 1; j++)
      for (let i = 1; i < nx - 1; i++)
        if (isBone(f, lo[0] - 1 + i, lo[1] - 1 + j, lo[2] - 1 + k)) solid[(k * ny + j) * nx + i] = 1;
  for (const { point: p, normal: n } of planes) {
    const hx = new Float64Array(nx);
    const hy = new Float64Array(ny);
    const hz = new Float64Array(nz);
    for (let i = 0; i < nx; i++) hx[i] = (o[0] + (lo[0] - 1 + i) * sp[0] - p[0]) * n[0];
    for (let j = 0; j < ny; j++) hy[j] = (o[1] + (lo[1] - 1 + j) * sp[1] - p[1]) * n[1];
    for (let k = 0; k < nz; k++) hz[k] = (o[2] + (lo[2] - 1 + k) * sp[2] - p[2]) * n[2];
    for (let k = 0; k < nz; k++)
      for (let j = 0; j < ny; j++)
        for (let i = 0; i < nx; i++) if (hx[i] + hy[j] + hz[k] > -CORTEX_DEPTH_TOLERANCE_MM) solid[(k * ny + j) * nx + i] = 1;
  }
  return {
    shape: [nz, ny, nx],
    origin: [o[0] + (lo[0] - 1) * sp[0], o[1] + (lo[1] - 1) * sp[1], o[2] + (lo[2] - 1) * sp[2]],
    data: edt3d(solid, nz, ny, nx, sp[0], sp[1], sp[2]),
  };
}

// Trilinear sample (mm) of an exemption field; 0 outside its grid.
function sampleBox(box, spacing, p) {
  const [nz, ny, nx] = box.shape;
  const i = (p[0] - box.origin[0]) / spacing[0];
  const j = (p[1] - box.origin[1]) / spacing[1];
  const k = (p[2] - box.origin[2]) / spacing[2];
  if (!(i >= 0 && i <= nx - 1 && j >= 0 && j <= ny - 1 && k >= 0 && k <= nz - 1)) return 0.0;
  const x0 = Math.floor(i);
  const y0 = Math.floor(j);
  const z0 = Math.floor(k);
  const at = (x, y, z) => box.data[(z * ny + y) * nx + x];
  return trilinear(at, i - x0, j - y0, k - z0, x0, y0, z0, Math.min(x0 + 1, nx - 1), Math.min(y0 + 1, ny - 1), Math.min(z0 + 1, nz - 1));
}

// ---- validate.py -------------------------------------------------------------

export function chooseImplantLength(distanceMm, tipRule, lengthsMm) {
  let best = null;
  for (const l of lengthsMm) {
    if (tipRule === "through") {
      if (l >= distanceMm - LENGTH_EPS_MM && (best === null || l < best)) best = l;
    } else if (l <= distanceMm + LENGTH_EPS_MM && (best === null || l > best)) {
      best = l;
    }
  }
  return best;
}

function validate(f, entry, target, diameterMm, marginMm, tipRule, catalog, stepMm) {
  const radius = diameterMm / 2.0;
  const codes = [];
  const warnings = [];
  const warn = (code, text) => {
    codes.push(code);
    warnings.push(text);
  };

  const u = unit3(sub3(target, entry));
  let { point: start, offset, problem } = entryCrossing(f, entry, target);
  if (problem === "no_bone") {
    warn("no_bone", "the screw axis does not enter bone before the target handle");
    start = entry.slice();
    offset = 0.0;
  } else if (problem === "cortex_not_found") {
    warn(
      "entry_cortex_not_found",
      `the entry handle is inside bone with no cortex within ${MAX_SEARCH_MM.toFixed(0)} mm behind it; the screw cannot be checked from its entry (move the entry handle to the bone surface)`
    );
    start = entry.slice();
    offset = 0.0;
  } else if (problem === "entry_not_outer") {
    warn(
      "entry_not_outer",
      "the axis enters this bone from a gap inside it (a joint, canal or foramen), not through its outer cortex; the gap is not exempted (move the entry handle to the outer cortex)"
    );
  } else if (Math.abs(offset) > HANDLE_OFF_CORTEX_WARN_MM) {
    warn("handle_off_cortex", `entry handle is ${Math.abs(offset).toFixed(1)} mm ${offset > 0 ? "outside" : "inside"} the cortex; the screw starts where its axis crosses it`);
  }

  const planes = {};
  let entryAngle = null;
  let exitAngle = null;
  let exitXyz = null;
  let protrusion = null;
  let sExit = null;
  let entryZone = 0.0;
  let exitZone = 0.0;
  if (problem === null) {
    let nIn = inwardNormal(f, start);
    if (nIn === null) nIn = u;
    const cosE = dot3(u, nIn);
    entryAngle = angleDeg(cosE);
    entryZone = zoneLength(radius, marginMm, cosE);
    planes.entry = { point: start, normal: [-nIn[0], -nIn[1], -nIn[2]] };
    if (cosE < COS_OBLIQUE) warn("entry_oblique", `entry too oblique: ${entryAngle.toFixed(0)} degrees to the cortex normal`);
    if (tipRule === "through") {
      const { point: x, problem: xProblem } = exitCrossing(f, start, target);
      if (x === null) {
        warn("exit_not_found", "far cortex not found near the target handle; the tip is kept inside bone");
      } else if (xProblem === "exit_not_outer") {
        warn("exit_not_outer", "the far cortex near the target handle is a gap inside the bone (a joint, canal or foramen), not its outer surface; the tip is kept inside bone");
      } else {
        const nX = inwardNormal(f, x);
        const nOut = nX === null ? [-u[0], -u[1], -u[2]] : [-nX[0], -nX[1], -nX[2]];
        const cosX = dot3(u, nOut);
        exitAngle = angleDeg(cosX);
        exitZone = zoneLength(radius, marginMm, cosX);
        planes.exit = { point: x, normal: nOut };
        exitXyz = x;
        sExit = dot3(sub3(x, start), u);
        if (cosX < COS_OBLIQUE) warn("exit_oblique", `far-cortex crossing too oblique: ${exitAngle.toFixed(0)} degrees to the cortex normal`);
      }
    }
  }

  const lengthRule = sExit !== null ? "through" : "inside";
  const toTarget = sub3(target, start);
  const distance = sExit !== null ? sExit : Math.sqrt(dot3(toTarget, toTarget));
  let length = distance;
  if (catalog !== null && catalog !== undefined) {
    const chosen = chooseImplantLength(distance, lengthRule, catalog);
    if (chosen === null) warn("no_catalog_length", `no catalogue length for ${diameterMm} mm fits ${distance.toFixed(1)} mm`);
    else length = chosen;
  }
  const tip = [start[0] + length * u[0], start[1] + length * u[1], start[2] + length * u[2]];
  if (sExit !== null) protrusion = length - sExit;

  const n = Math.max(2, pyRound(length / stepMm) + 1);
  const half = boxHalf(radius, marginMm, f.spacing);
  const boxes = {};
  const boxFor = (names) => {
    const key = names.join("+");
    if (!boxes[key]) boxes[key] = exemptField(f, names.map((name) => planes[name]), half);
    return boxes[key];
  };
  let minClearance = Infinity;
  let worst = null;
  for (let q = 0; q < n; q++) {
    const s = (length * q) / (n - 1);
    const p = [start[0] + s * u[0], start[1] + s * u[1], start[2] + s * u[2]];
    const inEntry = planes.entry !== undefined && s < entryZone;
    const inExit = planes.exit !== undefined && s > sExit - exitZone && s <= sExit + MAX_PROTRUSION_MM;
    let value;
    if (inEntry && inExit) value = sampleBox(boxFor(["entry", "exit"]), f.spacing, p);
    else if (inEntry) value = sampleBox(boxFor(["entry"]), f.spacing, p);
    else if (inExit) value = sampleBox(boxFor(["exit"]), f.spacing, p);
    else value = samplePlain(f, p);
    const clearance = value - radius;
    if (clearance < minClearance) {
      minClearance = clearance;
      worst = p;
    }
  }

  return {
    out_of_region: false,
    min_clearance_mm: minClearance,
    worst_point_xyz: worst,
    breach: minClearance < marginMm + BREACH_EPS_MM || codes.some((c) => UNCHECKED_ENTRY_CODES.includes(c)),
    length_mm: length,
    tip_rule: tipRule,
    start_xyz: start,
    tip_xyz: tip,
    entry_handle_offset_mm: offset,
    entry_angle_deg: entryAngle,
    entry_zone_mm: entryZone,
    exit_xyz: exitXyz,
    exit_angle_deg: exitAngle,
    exit_zone_mm: exitZone,
    protrusion_mm: protrusion,
    warnings,
    warning_codes: codes,
  };
}

// Validate a screw exactly as validate.validate_screw does. opts: tipRule
// ("inside" | "through"), catalogLengthsMm (the lengths this diameter comes
// in), stepMm. When the check needs voxels the export did not include (a
// handle dragged far away), the result is { out_of_region: true, breach:
// null }: not checked, never "safe".
export function validateScrew(field, entry, target, diameterMm, marginMm, opts = {}) {
  const tipRule = opts.tipRule || "inside";
  if (tipRule !== "inside" && tipRule !== "through") throw new Error(`unknown tip rule ${tipRule}`);
  const d = sub3(target, entry);
  if (!(dot3(d, d) > 0)) throw new Error("the entry and target handles must be distinct points");
  try {
    return validate(field, entry, target, diameterMm, marginMm, tipRule, opts.catalogLengthsMm ?? null, opts.stepMm || 1.0);
  } catch (err) {
    if (!(err instanceof OutOfRegion)) throw err;
    return {
      out_of_region: true,
      min_clearance_mm: null,
      breach: null,
      tip_rule: tipRule,
      warnings: ["moved beyond the region exported with this screw; check it in Slicer"],
      warning_codes: ["out_of_region"],
    };
  }
}
