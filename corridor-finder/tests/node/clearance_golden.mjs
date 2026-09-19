// Runs the viewer's clearance check (viewer/clearance.js) on cases written
// by tests/python/test_viewer_clearance_golden.py and prints the results as
// JSON, so the test can compare them with corridor_engine/validate.py.
// Usage: node clearance_golden.mjs <cases.json>
import { readFileSync } from "node:fs";

import { clearanceAlongAxis } from "../../viewer/clearance.js";

const cases = JSON.parse(readFileSync(process.argv[2], "utf8"));
const results = cases.map((c) => {
  const edt = { ...c.edt, data: Uint8Array.from(Buffer.from(c.edt.data_b64, "base64")) };
  return clearanceAlongAxis(edt, c.entry, c.target, c.diameter_mm, c.margin_mm);
});
console.log(JSON.stringify(results));
