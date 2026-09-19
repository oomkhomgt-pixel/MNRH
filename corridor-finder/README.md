# Corridor Finder

Percutaneous screw corridor planning for the pelvis and acetabulum. Given a
pelvis CT, it segments the bones, auto-suggests the widest safe corridor for
each named screw, lets the surgeon adjust entry/target by hand with live
cortical-clearance checking, and reports skin-entry guidance, trajectory
angles, simulated fluoroscopy views, a printable plan, and a 3D model.

**Intended for preoperative planning; always verify against intraoperative
imaging.** This is not a substitute for clinical judgment or intraoperative
fluoroscopy/navigation.

> ระบบวางแผนเส้นทางสกรูผ่านผิวหนัง (percutaneous screw) สำหรับกระดูกเชิงกราน
> และ acetabulum จาก CT — ใช้เพื่อวางแผนก่อนผ่าตัดเท่านั้น ต้องตรวจสอบซ้ำกับ
> ภาพเอกซเรย์ระหว่างผ่าตัดเสมอ ยังอยู่ระหว่างการพัฒนา (ดูสถานะด้านล่าง)

## Corridors covered (v1)

- Anterior column (antegrade and retrograde)
- Posterior column
- Supra-acetabular / LC-2
- Iliosacral S1 and S2
- Transiliac-transsacral S1

## Architecture

- **`corridor_engine/`** — pure numpy/scipy Python package with no Slicer,
  Qt, or VTK imports. This is where all the actual geometry lives (volume
  resampling, segmentation fallback, landmark detection, the anterior
  pelvic plane frame, the corridor search, live clearance validation, skin
  entry, DRR projection, plan/report/export). It is unit tested headlessly
  with pytest and synthetic phantom volumes (no real CT needed to run the
  tests), so it can be developed and verified in CI or any plain Python
  environment.
- **`CorridorFinder/`** — a 3D Slicer scripted module. This is the only
  place that talks to Slicer's MRML scene, TotalSegmentator, and Qt; it
  converts volumes/segmentations to plain arrays, calls into
  `corridor_engine`, and drives the UI, PDF/STL export, and DICOM import.
- **`viewer/`** — a self-contained Three.js HTML viewer that the Slicer
  module exports per plan: a translucent 3D bone model with draggable
  screw handles and a coarse embedded distance field, so anyone can open
  the exported file (no install) to review or teach from a plan, and even
  drag a screw and see the clearance re-check live in the browser.
- **`corridors.json`** / **`screws.json`** — editable data: anatomical
  entry/exit region definitions per corridor, and the screw diameter/length
  library. Tuning corridor anchors for a specific population or catalog is
  a data change, not a code change.

## Status

This is under active development. What's implemented and unit tested today:

- [x] Volume/resampling, HU-threshold fallback segmentation
- [x] Distance-transform corridor search + auto-suggestion + ranking
- [x] Live per-screw clearance validation
- [x] Bony landmark detection (ASIS, PSIS, iliac crest, pubic tubercle,
      ischial tuberosity, greater trochanter, SI joint, S1/S2 body centers)
- [x] Anterior pelvic plane frame + trajectory angle reporting
- [x] Skin entry point + landmark-relative incision offsets
- [x] DRR (simulated fluoroscopy) rendering, per the view angles in
      `corridors.json`
- [x] Plan JSON schema, PHI stripping, printable HTML report
- [x] Mesh export (marching cubes, binary STL) and the self-contained
      Three.js viewer export, with a live in-browser clearance check that
      mirrors `validate.py`'s safety rule exactly (breach if clearance is
      below the screw's own margin, not merely below zero)

- [x] `CorridorFinder/CorridorFinder.py`, the 3D Slicer scripted module,
      is written and was smoke-tested end-to-end (segmentation ->
      landmarks -> APP frame -> corridor search -> plan -> validation ->
      handle-drag update -> plan JSON / report / STL / viewer export, all
      producing schema-valid output with no exceptions) against a
      synthetic phantom, using a lightweight stand-in for the `slicer`/
      `vtk` modules this environment doesn't have. **It has not been run
      inside real 3D Slicer** and needs that before it can be trusted —
      see Status below for what specifically to check first.

Not yet implemented (tracked in the project plan):

- [ ] Demo CT download script and a real-anatomy sample plan
- [ ] TotalSegmentator integration (the fallback segmenter above is a
      coarse stand-in and does not reliably separate bones at a joint —
      it must not be relied on for real planning without manual review)
- [ ] A browser (Playwright) test harness for `viewer/app.js` — the
      viewer's clearance logic is currently verified only by careful
      review against `validate.py`, not by an automated test; a golden
      test comparing the two on identical inputs is the next priority
      before the viewer is trusted unsupervised
- [ ] Pointer-dragging of screw handles in the viewer (handles currently
      move only via the `window.CF.moveHandle` test hook, not the mouse)

## Development

```
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt -e .
pytest -q
```

## Getting the Slicer module running

`CorridorFinder/CorridorFinder.py` was written and reasoned through
carefully, but this development environment has no 3D Slicer, so it has
never actually been loaded into one. Expect to debug it. In rough order
of likely first failure:

1. **Extension loading.** In Slicer: Edit > Application Settings >
   Modules > Additional module paths, add this repo's `corridor-finder/
   CorridorFinder/` directory, restart. If it doesn't appear under
   Orthopedics, check the Python console for an import traceback first —
   most likely `corridor_engine`'s dependencies (numpy/scipy/scikit-image/
   jsonschema) aren't installed for Slicer's bundled Python. Install them
   with `slicer.util.pip_install("numpy scipy scikit-image jsonschema")`
   in the Python console, or point Slicer at this project's `.venv`.
2. **Volume orientation.** `volume_node_to_engine_volume()` in
   `CorridorFinder.py` deliberately raises rather than guessing if the
   loaded CT isn't axis-aligned RAS (no gantry tilt). If a real DICOM
   import trips this, that's the first thing to fix — either resample the
   volume in Slicer first, or extend the conversion to handle a general
   direction matrix (the current code only handles the common case).
3. **TotalSegmentator.** `_run_total_segmentator()` guesses at the
   installed SlicerTotalSegmentator extension's Python API (module name,
   logic class, `process()` signature, and the lowercase structure names
   it expects like `"hip_left"`). This is the part most likely to need
   adjusting to match whatever version you install — check
   `slicer.modules.totalsegmentator.widgetRepresentation().self().logic`
   in the Python console to see the real API if the call fails, and the
   fallback segmenter will kick in automatically (flagged "unverified" in
   the UI) in the meantime so you can keep testing everything else.
4. **Everything past segmentation** (landmarks, corridor search, plan,
   validation, exports) was smoke-tested outside Slicer against a
   synthetic phantom with the `slicer`/`vtk` modules stubbed out, and ran
   end to end with no exceptions — so a failure there is more likely a
   real-anatomy edge case (e.g. a landmark heuristic failing on unusual
   anatomy) than a wiring bug. Report back what you see and it can be
   diagnosed from the traceback plus the CT that triggered it.

## Safety

- The HU-threshold fallback segmentation cannot reliably separate bones
  that touch (hip/sacrum at the SI joint, hip/femur at the joint space).
  Always confirm segmentation — ideally with TotalSegmentator, and by eye —
  before trusting a suggested corridor.
- Corridor anchor points in `corridors.json` are initial estimates and
  should be reviewed against real anatomy before clinical use.
- Simulated fluoroscopy is a parallel projection, not a true cone-beam
  C-arm image; angles will not exactly match the OR.
- The exported HTML viewer's safety check is a coarse (3 mm) re-sampling
  of the same distance field Slicer computes at full resolution. Treat a
  "safe" reading in the viewer as informative, not as a substitute for the
  Slicer-side validation it was exported from.
