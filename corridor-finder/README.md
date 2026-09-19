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

**Coordinates.** Everything, from engine and plan JSON to STL and viewer,
uses 3D Slicer's RAS world coordinates: x = patient right+, y = anterior+,
z = superior+ (in mm). After segmentation, a side ("left"/"right") comes
from the label a structure belongs to. TotalSegmentator labels sides by
anatomy; the HU-threshold fallback labels them by position (patient right
= +x). The APP frame used for reported angles is anatomical: x = patient
left, y = anterior, z = cephalad.

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
      `vtk` modules. It now loads in real 3D Slicer; the workflow is being
      verified there step by step (next section).

### Verified inside real 3D Slicer

On 3D Slicer 5.12.4, Windows 11 (Python 3.12.10, numpy 2.4.6, scipy
1.17.1, scikit-image 0.26.0 — newer than the versions pinned for CI).
Slicer was driven headlessly (`--no-main-window --python-script`), so
these checks exercise the module's code paths, not a person clicking
through the GUI:

- [x] The module loads, is listed under Orthopedics, its panel builds, and
      its self-test passes.
- [x] With a required package missing (jsonschema or scikit-image), the
      module still loads and its panel lists what is missing with an
      install button. Before, it silently vanished from the module list.
- [x] All `corridor_engine` pytest tests pass on Slicer's own Python and
      library versions, as well as on the pinned CI versions.
- [x] CT-to-engine volume conversion puts every voxel where Slicer itself
      places it, for all 8 axis-aligned orientations with anisotropic
      spacing (module self-test, checked against Slicer's IJK-to-RAS
      matrix). Oblique, sagittal/coronal and transformed volumes are
      rejected with an explanation. Before this, every realistic CT was
      rejected and the one layout accepted was mirrored left-right.
- [x] Workflow mechanics, driven through the panel's own widgets by
      `tests/slicer/workflow_check.py`, with no error dialogs or exceptions:
      - on a synthetic pelvis CT stored in the standard DICOM layout:
        segment (HU fallback; the patient's right hip is labelled right),
        detect landmarks (APP axes anatomical; dragging a landmark rebuilds
        the frame), suggest for every corridor and side, add to the plan
        (markups line at the planned entry/target), drag the target handle
        (plan, audit trail and clearance label update; the label turns red
        exactly on breach), export plan JSON (reloads and validates),
        report (shows BREACH exactly when breached), STL and viewer;
      - on a real CT (Sample Data "CTAAbdomenPanoramix", lower chest to
        upper pelvis): segment, detect landmarks, suggest for every
        corridor and side.
- [ ] **At the default 2 mm margin no suggestion fits, on either CT.**
      Add/drag/export above were exercised with the margin set to 0 mm and,
      in the test only, no minimum corridor length. See "Open design
      question" below: this needs a clinical decision, not a code tweak.

### Open design question: the entry (and exit) cortex

The corridor search picks entry and target points on the bone *surface*,
and both the search and `validate.py` take the minimum clearance over the
whole entry-to-target segment. At the surface the distance to the nearest
non-bone voxel is about zero, so by the current rule any screw that starts
at the cortex is a breach. Suggestions end at clearance of about -2.0 or
-0.5 mm and never fit. The iliosacral corridors return no candidates at
all: their target region is "sacrum *surface* within 12 mm of the S1 body
centre", and on real anatomy the cortex is further than that from the
centre.

What the breach rule should exempt at the planned entry (and at the far
cortex for transiliac-transsacral screws) is a clinical decision. The
rule stays unchanged until that decision is made.

### Known issues found in Slicer, not yet fixed

- **Simulated fluoroscopy views are wrong.** Every view with `rotate_x = 0`
  (AP, lateral, iliac and obturator obliques) projects along the body's
  long axis, giving an axial silhouette. Inlet/outlet are tilted 45 degrees
  from that. Soft tissue also washes out the bone. Do not rely on the
  report's DRR images yet.
- The viewer does not draw the screws, and its camera orbits the world
  origin rather than the model. It embeds the full-resolution distance
  field, so a larger CT may exceed its 8 MB size limit.
- TotalSegmentator is not installed on the test workstation, so
  `_run_total_segmentator()` has not been exercised. The fallback runs
  instead and is flagged UNVERIFIED in the panel.

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

`CorridorFinder/CorridorFinder.py` loads in 3D Slicer 5.12.4 (see
"Verified inside real 3D Slicer" above for what else has been checked).
In rough order of likely first failure:

1. **Extension loading.** In Slicer: Edit > Application Settings >
   Modules > Additional module paths, add this repo's `corridor-finder/
   CorridorFinder/` directory, restart. It appears under Orthopedics. On
   a fresh Slicer the panel will say that scikit-image and jsonschema are
   missing (Slicer bundles numpy, scipy and Pillow) and offer a button
   that installs them; restart Slicer afterwards. If the module does not
   appear at all, run `tools/diagnose.py` in the Python console (usage at
   the top of that file). It prints the configured paths, the dependency
   status and the full import traceback that Slicer's UI hides. Keep
   helper scripts out of `CorridorFinder/`: Slicer tries to load every
   `.py` file in a module directory as a module of its own.
2. **Volume orientation.** `volume_node_to_engine_volume()` accepts any
   axial CT whose voxel axes run along left-right, anterior-posterior and
   superior-inferior, in either direction. It refuses, with an
   explanation, gantry-tilted or oblique volumes, sagittal/coronal
   reformats, and volumes under a transform (harden the transform first).
   Resample such a volume onto an axis-aligned grid in Slicer, or extend
   the conversion to a general direction matrix.
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
- The exported HTML viewer's safety check samples the distance field
  Slicer computed, rounded to whole millimetres (so up to 0.5 mm off
  either way), along the axis every 1 mm. Treat a "safe" reading in the
  viewer as informative, not as a substitute for the Slicer-side
  validation it was exported from.
