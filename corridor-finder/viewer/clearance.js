// Clearance check for the exported viewer: the one place the viewer decides
// "breach". It mirrors corridor_engine/validate.py and must stay identical
// to it (and to report.py's reading of it):
//   - samples every ~1 mm from entry to target, both ends included, with the
//     same sample count validate.py computes;
//   - clearance = distance field (mm) - screw radius, trilinear-sampled;
//   - breach when the minimum clearance is below the screw's own margin,
//     NOT merely below zero.
// tests/python/test_viewer_clearance_golden.py runs this file under Node
// against validate.py on identical screws.
//
// edt: { shape: [nz, ny, nx], spacing: [sx, sy, sz], origin: [ox, oy, oz],
//        scale_mm, data: Uint8Array } -- the screw's own distance field as
// exported by corridor_engine/export_viewer.py (cropped, rounded down).

// Python's round() sends halves to the even neighbour; match it so both
// sides sample exactly the same points.
function pyRound(x) {
  const f = Math.floor(x);
  const d = x - f;
  if (d > 0.5) return f + 1;
  if (d < 0.5) return f;
  return f % 2 === 0 ? f : f + 1;
}

export function worldToIjk(edt, xyz) {
  const [ox, oy, oz] = edt.origin;
  const [sx, sy, sz] = edt.spacing;
  return [(xyz[0] - ox) / sx, (xyz[1] - oy) / sy, (xyz[2] - oz) / sz];
}

// Trilinear sample in mm. Outside the grid returns 0 (which reads as a
// breach): stricter than scipy's partial blend with its zero border, and it
// never reports "safe" for a point outside the exported field.
export function sampleTrilinear(edt, ijk) {
  const [nz, ny, nx] = edt.shape;
  const [i, j, k] = ijk;
  if (!(i >= 0 && i <= nx - 1 && j >= 0 && j <= ny - 1 && k >= 0 && k <= nz - 1)) {
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
  return (c0 * (1 - tz) + c1 * tz) * edt.scale_mm;
}

export function clearanceAlongAxis(edt, entry, target, diameterMm, marginMm, stepMm = 1.0) {
  const d = [target[0] - entry[0], target[1] - entry[1], target[2] - entry[2]];
  const length = Math.hypot(d[0], d[1], d[2]);
  const n = Math.max(2, pyRound(length / stepMm) + 1);
  const radius = diameterMm / 2.0;
  let minClearance = Infinity;
  for (let s = 0; s < n; s++) {
    const t = s / (n - 1);
    const p = [entry[0] + t * d[0], entry[1] + t * d[1], entry[2] + t * d[2]];
    const clearance = sampleTrilinear(edt, worldToIjk(edt, p)) - radius;
    if (clearance < minClearance) minClearance = clearance;
  }
  return { clearance_mm: minClearance, breach: minClearance < marginMm };
}
