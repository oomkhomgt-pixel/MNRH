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
  module exports per plan: a translucent 3D bone model with the planned
  screws (green, or red on breach) and, per screw, the distance field
  Slicer validated it against, so anyone can open the exported file (no
  install) to review or teach from a plan. `viewer/clearance.js` holds
  its breach check, which mirrors `validate.py` and is golden-tested
  against it.
- **`corridors.json`** / **`screws.json`** — editable data: anatomical
  entry/exit region definitions per corridor, and the screw diameter/length
  library. Tuning corridor anchors for a specific population or catalog is
  a data change, not a code change.

**Coordinates.** Everything, from engine and plan JSON to STL and viewer,
uses 3D Slicer's RAS world coordinates: x = patient right+, y = anterior+,
z = superior+ (in mm). Plan files say so (`"coordinate_system": "RAS"`),
and the STL header says `SPACE=RAS`, which Slicer reads. Software that
ignores that header may assume LPS and show the model turned 180 degrees
about the long axis; for 3D printing this makes no difference. After segmentation, a side ("left"/"right") comes
from the label a structure belongs to. TotalSegmentator labels sides by
anatomy; the HU-threshold fallback labels them by position (patient right
= +x). The APP frame used for reported angles is anatomical: x = patient
left, y = anterior, z = cephalad.

## Status

This is under active development. What's implemented and unit tested today:

- [x] Volume/resampling, HU-threshold fallback segmentation
- [x] Distance-transform corridor search + auto-suggestion + ranking; a
      suggestion "fits" only if it validates exactly as the plan will
      validate it
- [x] Live per-screw validation with the surgeon's screw rules
      (DECISIONS.md section 1):
      - the screw starts where its axis crosses the outer cortex and has a
        catalogue length;
      - its tip stays inside bone, or passes the far cortex for transiliac
        and LC-2 screws;
      - only the cortex being crossed is exempted, not gaps inside the bone.
- [x] Bony landmark detection (ASIS, PSIS, iliac crest, pubic tubercle,
      ischial tuberosity, greater trochanter, SI joint, S1/S2 body centers)
- [x] Anterior pelvic plane frame + trajectory angle reporting
- [x] Skin entry point + landmark-relative incision offsets
- [x] DRR (simulated fluoroscopy) rendering, per the view angles in
      `corridors.json`
- [x] Plan JSON schema, PHI stripping, printable HTML report
- [x] Mesh export (marching cubes, binary STL) and the self-contained
      Three.js viewer export. Its in-browser check (`viewer/clearance.js`)
      repeats `validate.py` step for step, including the breach rule
      (clearance below the screw's own margin, not merely below zero). It is
      golden-tested against `validate.py` under Node and can only be
      stricter: at most 0.1 mm, from the field's rounding.

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
- [x] The whole workflow, driven through the panel's own widgets by
      `tests/slicer/workflow_check.py` (no error dialogs or exceptions):
      - **Real CT, TotalSegmentator, default 2 mm margin, nothing relaxed**
        (Sample Data "CTAAbdomenPanoramix", lower chest to upper pelvis).
        The steps:
        - segment: hips and sacrum, shown as the "CF bones" segmentation;
        - detect landmarks and suggest for every corridor and side;
        - add a fitting screw (posterior column right, 7.3 x 85 mm);
        - drag the target handle: the plan, audit trail, screw length and
          clearance label update, and the label turns red exactly on breach;
        - erase bone around the screw in the segmentation: the screw is
          re-validated as a breach, and restoring the bone restores it;
        - export plan JSON (reloads and validates), report (DRR images;
          BREACH shown exactly when breached), STL and viewer.
      - Synthetic pelvis CT in the standard DICOM layout: the same steps
        with the HU fallback, adding an anterior column screw (7.3 x 75 mm)
        at the default margin.
- [x] TotalSegmentator (extension revision 270cac2 with TotalSegmentator
      2.14.0; PyTorch 2.14 with CUDA on an RTX 4060) segments the real CT in
      about 50 s. It labels sides by anatomy, and its right hip comes out at
      RAS x = +80 mm, its left at -78 mm: an end-to-end check that this
      module puts the patient's right on the right. Its output is checked
      for plausibility. On the synthetic phantom it returned two "hips",
      both on the patient's right; that is rejected and the fallback runs,
      with the reason shown. A right hip clearly on the patient's left
      stops segmentation outright, because the scan's left/right
      orientation may be wrong.
- [x] Simulated fluoroscopy: each named view now projects along the right
      beam for a supine patient (AP, lateral, inlet/outlet, Judet
      obliques) and shows bone rather than soft tissue. Checked by eye on
      the real CT. The view angles in corridors.json are unchanged.
- [x] Exports: the STL loads back into Slicer exactly where the bones
      are (before, a header-less RAS file was read as LPS and landed
      turned 180 degrees about the long axis). The plan JSON records its
      coordinate system, and the report names the direction of each
      skin-offset column (right/left, anterior/posterior,
      superior/inferior).
- [x] In Slicer's GUI (main window, screenshots): the panel lays out
      fully. After TotalSegmentator, the "CF bones" segmentation shows
      the right hip (orange) under Slicer's own "R" orientation marker and
      the left (blue) under "L". One cosmetic issue: landmark labels
      overlap in small views.
- [x] Screw rules (DECISIONS.md section 1), in the same headless runs:
      - **Suggestions.** Every fitting suggestion, for every corridor and
        side, starts on the cortex (entry handle within 0.1 mm of the
        crossing). It has a catalogue length within the corridor's range
        and no breach. Adding it to the plan re-validates it to exactly the
        same length and clearance.
      - **Results on the real CT** (mechanics only: this CT stops above the
        acetabulum, so the anchors are not anatomical):
        - posterior column: 7.3 x 85 mm on both sides;
        - LC-2 left: 4.5 x 110 mm, tip 0.1 mm past the far cortex;
        - iliosacral S1 left 4.5 x 80 mm and S2 left 3.5 x 80 mm;
        - LC-2 right and iliosacral S1/S2 right: too narrow;
        - transiliac: its far cortex is 144 mm from the entry cortex,
          below the corridor's 150 mm minimum;
        - anterior column: no axis of the corridor's length exists.
      - **Slicer display.** The screw is shown as a model from its cortex
        crossing to its tip. Dragging a handle recomputes its length. The
        report states where the screw starts, its entry angle, tip rule,
        protrusion and warnings, and its DRRs draw that same screw.
      - **Viewer, run under Node on the exported file.** Its JavaScript
        places every exported screw exactly where Slicer does (start, tip,
        length, warnings). It agrees on the verdict, with clearance at most
        0.1 mm lower.
      - **Viewer, in a browser.** It draws the checked screw. A handle
        dragged far away, or both handles on one point, reads "not
        checked", never "safe".

### What still blocks real planning

- **The HU-threshold fallback cannot be used for corridor search.** Its
  250 HU threshold keeps cortex but misses most cancellous bone, so its
  "bone" is a shell with near-zero clearance inside and no screw fits at
  the default margin. Treat TotalSegmentator (or a corrected
  segmentation) as required, not optional.
- **The entry rule has one provisional value awaiting the surgeon's
  decision** (DECISIONS.md 1.2a). The agreed rule exempts only the part of
  the screw's envelope beyond the entry cortex's tangent plane. On the
  real CT that flagged 91-100% of good entries as breaches, because a
  segmented cortex is rough and curved. The implementation therefore also
  ignores non-bone less than 1.5 mm inside that plane. DECISIONS.md 1.2a
  gives the share of entries still flagged for 0-2.5 mm. Until the
  surgeon confirms a value, treat 1.5 mm as provisional.
- **Iliosacral and transiliac-transsacral screws are still limited by the
  SI joint** on the real CT. Only the left S1 and S2 corridors take a
  screw (4.5 and 3.5 mm), and the right side is too narrow. Confirmed
  cause: the SI joint. Before the screw rules (step 1), for every best
  candidate the minimum clearance lay within 0-1.5 mm of both the hip and
  the sacrum.
  `sacral_gap_allowance_mm` (2 mm) was applied only to the containment
  test; the clearance now also counts the joint space up to that width
  as bone (`segmentation.sacroiliac_gap_fill`), which raised the best
  clearances (e.g. S1 right from -0.3 to 0.6 mm) but not enough. In these
  labels the gap from the hip's joint surface to the sacrum has a median
  of about 4 mm, and only 11-15% of it is within 2 mm. **Decided**
  (DECISIONS.md section 2): the bridged width becomes patient-specific,
  taken from the intact joint (editable, capped at 4 mm; 4 mm when both
  joints are disrupted), once the surgeon has confirmed which side is
  disrupted. Not implemented yet (step 2).
- The corridor anchors, textbook directions and DRR view angles in
  corridors.json have not been reviewed against real anatomy. The Sample
  Data CT stops above the acetabulum, so the anterior column, posterior
  column and supra-acetabular results on it are not anatomically
  meaningful: they only prove the mechanics. Planned (DECISIONS.md
  sections 4-5): review on public full-pelvis CTs, then a 5-case pilot
  and a 20-case blinded validation on hospital cases.
- **Post-reduction corridors** (planning on virtually reduced anatomy,
  the corridor actually drilled after intra-operative reduction) are
  designed in DECISIONS.md section 3; not implemented yet (step 5).

Not yet implemented (tracked in the project plan):

- [ ] Demo CT download script and a real-anatomy sample plan
- [ ] An automated browser test of the viewer's rendering. Its screw
      check (`viewer/clearance.js`) is golden-tested against `validate.py`
      under Node, and the Slicer harness runs it on each exported viewer;
      the rendering has only been checked by eye.
- [ ] Pointer-dragging of screw handles in the viewer (handles currently
      move only via the `window.CF.moveHandle` test hook, not the mouse)

## Development

```
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt -e .
pytest -q
```

`tests/python/test_viewer_clearance_golden.py` runs the viewer's screw
check under Node (`node` on the PATH) against `validate.py` and is skipped
without it, unless `CF_REQUIRE_NODE=1`, which makes a missing Node a
failure. The CI workflow (`.github/workflows/corridor-finder.yml` at the
repo root) installs Node 22 and sets it.
The Slicer-side checks run inside Slicer:

```
Slicer --no-splash --no-main-window --python-script tests/slicer/workflow_check.py
```

It writes its exports and `workflow_check_report.txt` to `CF_OUT_DIR`.
It also runs each exported viewer's own check under Node, found from
`CF_NODE` or the PATH.

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
3. **TotalSegmentator.** Install the TotalSegmentator extension from the
   Extensions Manager (it brings PyTorch and NNUNet). The first
   segmentation installs PyTorch, nnU-Net and the TotalSegmentator package
   after asking (several GB), then downloads the model weights.
   `_run_total_segmentator()` calls the extension's
   `TotalSegmentatorLogic.process()` with the "total" task limited to the
   hips, sacrum and femurs, at "normal" quality (the 1.5 mm model; the
   3 mm "fast" model is too coarse for corridors about 10 mm wide).
   Written against extension revision 270cac2 (TotalSegmentator 2.14.0);
   if a later version changes that API, the panel falls back and shows
   the error. With an NVIDIA GPU it takes about a minute; without one,
   "normal" quality can take 5-50 minutes.
4. **Past segmentation**, `tests/slicer/workflow_check.py` drives every
   step inside Slicer (see "Verified inside real 3D Slicer"). Run it after
   changing the module, and when a real CT misbehaves, save the traceback
   from the Python console together with the case.

## Safety

- The HU-threshold fallback segmentation cannot reliably separate bones
  that touch (hip/sacrum at the SI joint, hip/femur at the joint space),
  and it misses most cancellous bone. Always confirm the "CF bones"
  segmentation by eye (left and right are coloured differently) before
  trusting a suggested corridor, and correct it in Segment Editor if
  needed: edits are read back before landmarks, suggestions, adding a
  screw and every export, and screws already in the plan are re-validated.
- Corridor anchor points in `corridors.json` are initial estimates and
  should be reviewed against real anatomy before clinical use.
- Simulated fluoroscopy is a parallel projection, not a true cone-beam
  C-arm image; angles will not exactly match the OR.
- The exported HTML viewer checks each screw against the same distance
  field Slicer validated it with, cropped to 30 mm around the screw and
  rounded down to 0.1 mm, with the same breach rule. So it can be up to
  0.1 mm stricter than Slicer but never more lenient (golden-tested). A
  handle moved outside the embedded region reads as a breach. Still treat
  the viewer as a review aid, not as a substitute for the Slicer-side
  validation it was exported from.
