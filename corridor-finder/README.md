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

Not yet implemented (tracked in the project plan):

- [ ] The Slicer scripted module itself (`CorridorFinder/CorridorFinder.py`)
      — this needs to be built and tested inside 3D Slicer, which this
      development environment cannot run
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
