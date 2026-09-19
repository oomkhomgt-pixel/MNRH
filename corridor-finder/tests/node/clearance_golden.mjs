// Runs the viewer's screw check (viewer/clearance.js) on cases written by
// tests/python/test_viewer_clearance_golden.py and prints the results as
// JSON, so the test can compare them with corridor_engine/validate.py.
// Usage: node clearance_golden.mjs <cases.json>
//
// cases.json: { volume: { full_shape, full_origin, spacing, scale_mm,
// data_b64 (the whole field in viewer steps) }, screws: [{ entry, target,
// diameter_mm, margin_mm, tip_rule, catalog_lengths_mm, index_offset,
// shape }], edts: [{ shape, spacing, solid_b64 }] }. Each screw gets the
// crop export_viewer.py would embed for it: index_offset/shape of the
// whole field -- or, when a screw has its own "field" (a payload header
// entry of an exported viewer plus data_b64), exactly that.
import { readFileSync } from "node:fs";

import { edt3d, validateScrew } from "../../viewer/clearance.js";

const input = JSON.parse(readFileSync(process.argv[2], "utf8"));
const out = {};

if (input.screws) {
  const vol = input.volume;
  const full = vol ? Uint8Array.from(Buffer.from(vol.data_b64, "base64")) : null;
  const [, NY, NX] = vol ? vol.full_shape : [0, 0, 0];
  out.screws = input.screws.map((c) => {
    const opts = { tipRule: c.tip_rule, catalogLengthsMm: c.catalog_lengths_mm };
    if (c.field) {
      const field = { ...c.field, data: Uint8Array.from(Buffer.from(c.field.data_b64, "base64")) };
      return validateScrew(field, c.entry, c.target, c.diameter_mm, c.margin_mm, opts);
    }
    const [nz, ny, nx] = c.shape;
    const [i0, j0, k0] = c.index_offset;
    const data = new Uint8Array(nz * ny * nx);
    for (let k = 0; k < nz; k++)
      for (let j = 0; j < ny; j++)
        for (let i = 0; i < nx; i++) data[(k * ny + j) * nx + i] = full[((k0 + k) * NY + (j0 + j)) * NX + (i0 + i)];
    const field = {
      shape: c.shape,
      index_offset: c.index_offset,
      full_shape: vol.full_shape,
      full_origin: vol.full_origin,
      spacing: vol.spacing,
      scale_mm: vol.scale_mm,
      data,
    };
    return validateScrew(field, c.entry, c.target, c.diameter_mm, c.margin_mm, opts);
  });
}

if (input.edts) {
  out.edts = input.edts.map((c) => {
    const solid = Uint8Array.from(Buffer.from(c.solid_b64, "base64"));
    const [nz, ny, nx] = c.shape;
    const [sx, sy, sz] = c.spacing;
    return Array.from(edt3d(solid, nz, ny, nx, sx, sy, sz));
  });
}

console.log(JSON.stringify(out));
