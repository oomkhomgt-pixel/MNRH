# Displacement Finder

Measures how far a fractured pelvis is out of place on CT: which pieces
moved, and the rigid transform that carries each one back to anatomical
position. The same per-fragment transform is what Corridor Finder's virtual
reduction applies before it plans screws (corridor-finder DECISIONS 8.4).

**Research software under development. Not for clinical use.** Nothing here
has been validated against a surgeon's reading of fragments, and the status
below says plainly what does not work yet.

> ระบบวัดการเคลื่อนของกระดูกเชิงกรานหักจาก CT — ยังอยู่ระหว่างการพัฒนา
> ไม่ใช้ในทางคลินิก (ดูสถานะด้านล่าง)

The clinical spec is `DECISIONS.md`; it outranks everything else here.

## Architecture

One engine with Corridor Finder (DECISIONS 7a). The core is new modules in
`corridor-finder/corridor_engine/`, pure numpy/scipy, tested headlessly with
synthetic phantoms:

- **`ctpelvic1k.py`**: reads a CTPelvic1K case into engine label ids. The
  file's ids clash with the engine's (its sacrum is the engine's left hip),
  so every id is remapped explicitly. Each hip's side is taken from world x,
  file by file, because the subsets disagree on which id is which. A CT with
  metal is refused (DECISIONS 5.3). `segmentation.LUMBAR = 6` is the one
  constant added to the engine's ids.
- **`mirror.py`**: the reference of DECISIONS 2.1/2.1a. It fits the mirror
  plane both ways (L5 alone, and L5 with the central sacrum), pre-selects
  "sacrum fractured" from the penalty, and refuses to be used until the
  surgeon confirms. It gates each plane on its tilt off the inter-hip axis
  (15 degrees), and carries an uncertainty from the spread between the two
  references.
- **`register.py`**: the closed-form rigid fit, trimmed ICP, RANSAC over
  correspondence pairs, and a point-to-plane step.
- **`fragments.py`**: `find_fragments` returns a `FragmentSet`. For each
  body it gives the mask, `to_reference` (4x4, where it is to where the
  mirrored intact side puts it), `to_parent` (4x4, fragment-relative), the
  residual, the travel, the plane uncertainty and a below-floor flag. Every
  number is measured over the surface of the mask that is reported.
  Bone that no body carries home onto the intact side, in pieces at least
  the smallest fragment for where they lie, is returned as `unexplained`
  (mask, cm3, pieces, and the share of the surface no body explains) and
  named in the warnings and the sentence, never folded silently into "one
  body". `reduce_labels` is the virtual reduction Corridor Finder calls; it
  refuses unless the caller passes `accept_unvalidated=True`, because
  `to_reference` has no validated error bound (see the status below), and
  it refuses outright while any bone is unexplained.
- **`phantoms.fractured_pelvis`**: a symmetric synthetic pelvis with a
  lumbar spine, one hemipelvis cut along a plane and the piece moved by a
  known rigid transform (DECISIONS 6.2).

This directory keeps only what is this project's own: `DECISIONS.md`, this
README, and `tools/measure_cases.py`, which runs the engine over the real
CTPelvic1K cases on this workstation and prints what it finds. Nothing it
reads or prints is committed (DECISIONS 8.1).

## Status

Slice 1 of the plan. What is built and verified, and what is not:

- [x] **Label remap and sides.** Tested for both CTPelvic1K conventions
      (id 2 on the patient's left, as in CLINIC, and on the right, as in
      ABDOMEN and most of CERVIX). The sacrum can never land on the engine's
      left hip, and the lumbar spine can never land on the left femur. Hips
      that are not one on each side of the sacrum are refused. With a CT,
      the body outline gives a second midline
      (`segmentation.check_hip_sides`). On the real files, CLINIC reads id 3
      as the patient's right and ABDOMEN reads id 2.
- [x] **Metal refused.** Any CT with 0.1 cm3 or more above 2500 HU is
      refused, with the metal's volume and its distance to the pelvic bones.
      Cortical bone on the four CLINIC CTs peaks at 1608-1779 HU, so none
      was refused. Not done: the distance to the *fracture* (DECISIONS 5.3
      asks for it) needs the fracture surfaces of slice 1b.
- [x] **The mirror plane reproduces the DECISIONS 2.1a calibration
      exactly.** It uses the same reference sets, the same 4000-point draw
      and the same cost. Penalties on the four CLINIC cases: 0.73, 0.99,
      0.87 and 0.82 mm. Fit costs, L5 alone vs L5 + central sacrum:
      1.31/2.04, 1.61/2.60, 1.42/2.29 and 1.38/2.19 mm. **The pre-selection
      agrees with the surgeon's reading on all four** (all have a sacral
      fracture, so L5 alone). Every plane passed the tilt gate (1.3-4.6
      degrees off the inter-hip axis; the L5 planes used, 2.0-4.6). Nothing is used until
      `mirror.confirm` is given `sacrum_fractured`, and every result records
      the reference and whether it was the pre-selection or an override.
      When the gate refuses the rule's plane, the other one is pre-selected
      with a warning (tested).
- [x] **On the phantom** turned 6 degrees, the plane comes out 0.15 degrees
      (L5) and 0.34 degrees (L5 + central sacrum) off the true plane.
- [x] **Fragment transform recovery on the phantom**, turned 6 degrees so
      the two sides are not voxel-identical, 1.5 mm voxels. The mask
      columns say how much of the true fragment was found and how much of
      what was found is true:

      | Fragment moved | Mask found / true | `to_reference` error (centroid, rotation, worst point) | `to_parent` error |
      | --- | --- | --- | --- |
      | 10 mm / 8 degrees (15.7 mm worst-point travel) | 1.00 / 1.00 | 1.11 mm, 0.47 deg, 1.36 mm | 0.10 mm, 0.25 deg, 0.26 mm |
      | 5 mm, no rotation | 1.00 / 0.95 | 1.07 mm, 0.45 deg, 1.35 mm | 0.18 mm, 0.23 deg, 0.26 mm |
      | 5 mm with 3 degrees (not in the suite) | 0.87 / 1.00 | 1.49 mm, 1.23 deg, 2.20 mm | not measured |
      | 20 mm, no rotation | 1.00 / 1.00 | 1.42 mm, 0.76 deg, 1.99 mm | 0.23 mm, 0.12 deg, 0.32 mm |
      | 30 mm, no rotation | 1.00 / 1.00 | 1.49 mm, 0.69 deg, 1.88 mm | 0.06 mm, 0.06 deg, 0.08 mm |
      | 5, 5, 18 mm and 10 degrees (23.3 mm worst-point travel) | 1.00 / 1.00 | 1.11 mm, 0.89 deg, 1.77 mm | 0.09 mm, 0.35 deg, 0.36 mm |

      For scale, Zeng et al. (Med Image Anal 2024) report 2.88 mm and 3.18
      degrees on real cases. Most of the `to_reference` error is the
      plane's own: `to_parent` cancels it. The reported travel of the 10 mm
      fragment is 15.7 mm, the truth. (Before the numbers were measured over
      the reported mask it read 17.0 mm: surface points in small islands
      that had been carried to the main body still counted, and being far
      from the fragment, the rotation moved them further.)
- [x] **A large displacement is no longer reported as "one body".** Found
      in review: the search for each next body started only from the main
      body's transform, and nearest-neighbour pairing finds only a
      transform it starts near. The 58 cm3 wing fragment was found at 10
      and 15 mm, and at 20, 25 mm and the 23.3 mm turned case the search
      ended with no candidate, no warning, and the whole fragment inside
      the main body, whose residual and travel looked healthy because
      unexplained points are not measured. Widening the pair cap from 20
      to 40 mm changed nothing. Two changes:
      - when the search from the main body finds nothing while bone is
        left that no body carries home, it starts again from the main body
        shifted by how far that bone's surface lies from the mirrored
        surface no body reaches. That finds the fragment at 20-30 mm
        (table above). Tried every time instead, those starts fitted a
        3 cm3 fracture face 40 mm away on the 5 mm phantom and promoted it
        (fact 3 again); preferred to the main body's start whenever they
        explained more, they took the 5 mm fragment from 95% to 90% pure.
        So they are a fallback, and the 5 and 10 mm results are unchanged.
        On real anatomy they still invented one body: on normal pelvis
        dataset4_case_00022 (right) an 8.3 cm3 body 51.8 mm off, only 21% of
        it bone that had been unexplained, where the phantom's 20 mm
        fragment was 89% and the body found on CLINIC_0012 94%. So a body
        found from these starts must be mostly (`FROM_UNEXPLAINED_SHARE =
        0.5`) the unexplained bone it was started from. The value is "most
        of it"; anything from 0.22 to 0.88 separates the three, and it was
        added after seeing that one normal, so it is checked on nothing
        else yet. No synthetic test exercises it;
      - whatever the search misses is reported. With the new starts
        switched off (the old search), the 25 mm case now says "one body
        found; 54.9 cm3 in 1 piece that no body carries home (31% of the
        surface unexplained)". That region is 100% true fragment and holds
        94% of it (89% at 20 mm, 96% at the turned case), and
        `reduce_labels` refuses. On the undisplaced phantom, the own-mirror
        case, and every phantom where the fragment is found, it reads 0 cm3
        (0.5% of the surface unexplained with no fragment, 5.9-6.2% with
        one, which is the fracture faces). **On real anatomy it is not
        specific:** on the 20 normal pelvises it fires on 6 of the 36
        hemipelvises that come back as one body, with 2.5-6.2 cm3, against
        11.6-19.0 cm3 on CLINIC_0023 and 0025 and 52-56 cm3 for the
        phantom's missed fragment. Its wording says so ("or asymmetry the
        mirror does not have").
- [x] **The null test on the phantom holds.** The undisplaced phantom, and
      an intact hemipelvis against its own mirror, each come back as one
      body. The own-mirror case reads 0.1 mm of travel, below its floor of
      0.7 mm, and is reported as a number with the flag (DECISIONS 1.4).
- [x] **Virtual reduction round trip on the phantom** (the plan's test 6,
      as the surgeon ruled on 2026-09-27). As first written, the test
      asserted that the reduced fragment lands within its residual. It
      failed: p50 1.14, **p90 1.30**, worst 1.36 mm against a residual of
      **1.13 mm**. The residual is fit quality, not an error bound, so that
      claim is no longer made. Two true claims replace it, both tested:
      - with the **exact** mirror plane, the residual alone bounds every
        voxel (worst 0.24 mm against 1.13 mm);
      - with the **fitted** plane, every voxel lands within the residual
        plus the fitted plane's own error at that point. That error is
        measured against the phantom's true plane (0.54-1.59 mm here), not
        taken from the reported plane uncertainty (0.86 mm), which
        underestimates it.

      Distances are measured before rounding onto the grid. No other bone
      is touched: a moved body never overwrites the sacrum or a femoral
      head.
- [x] Bilateral cases (CLINIC_0060) are refused a transform home with the
      reason (DECISIONS 2.4). An unconfirmed reference is refused.

What does **not** work yet, measured by `tools/measure_cases.py`:

- [ ] **The null test on real anatomy fails.** On 20 normal pelvises (the
      first 5 label files of each normal subset), each hemipelvis was
      measured against the other one mirrored. Results:
      - 36 of 38 measured hemipelvises came back as one body;
      - **2 invented a second body**: 81 cm3 moving 6.6 mm off the main
        body, and 42 cm3 moving 5.8 mm;
      - 2 could not be measured, because the mirrored side was too far off
        for any consistent pairs (floor under the plane 18.8 and 4.8 mm).
      Before every number was measured over the body's own mask, a third
      was invented (197 cm3 moving 11.5 mm); it is not promoted now. Why
      exactly was not traced; the change that removed it also stops
      islands carried to the main body counting toward a candidate's
      movement off it.
      Unchanged by the fallback search above (the one body it invented is
      now refused, and the other 36 read as before).
      This is the fact-4 failure, rarer but not gone. So **fragment
      discovery is not trustworthy on real CTs**, even though it recovers
      the phantom's fragment from 5 to 30 mm.
- [ ] **On the four CLINIC cases one fragment is found, and it is right.**
      The surgeon read every result on fragment sheets (DECISIONS 7b):
      - CLINIC_0012 right: 18.8 cm3, one piece, 12.2 mm off the main body,
        in the right pubic body and rami. **He confirmed it is the fracture
        he read.** The search from the main body alone missed it; the
        fallback start found it;
      - on CLINIC_0023 and 0025 nothing is promoted, and each reports bone
        that no body carries home: 19.0 cm3 in 2 pieces (22% of the surface
        unexplained) and 11.6 cm3 in 2 pieces (20%). **Of the four pieces,
        two are fractures he read** (the right pubic body on 0023, the left
        pubic body and superior ramus on 0025). **One is not** (the lateral
        rim of 0023's right iliac wing, asymmetry). The fourth, the
        posterior ilium beside 0025's fractured left sacrum, is next to a
        fracture but not one he read in that bone. Candidates (25-128 cm3,
        5-55 mm off the main body) each failed at least one gate: the
        one-piece check (34-87% in one piece); the plane-uncertainty gate
        (11.6 and 6.6 mm); and for those found from the fallback start,
        being only 19-44% unexplained bone;
      - his corrected reading means only 0012 has a whole intact side to
        mirror: 0023's mirrored left has a pubic body fracture, and 0025's
        mirrored right has an acetabular fracture (so that fracture cannot
        show). Fragment discovery has therefore been tested against an
        intact reference on one real case only.
- [ ] **The absolute transform home has a floor of several millimetres on
      normal anatomy, and most of it is anatomy, not the plane.** On normal
      pelvises, which are not displaced at all, a hemipelvis "travels home"
      onto its mirrored twin by a median of 13.5 mm over the whole
      hemipelvis, **6.3 mm at the SI joint** and **11.5 mm at the symphysis**
      (40 pelvises, 80 hemipelvises; 90th percentiles 31.2, 14.6 and
      30.1 mm). Measuring relative to the sacrum cancels any rigid error of
      the plane exactly, and it still reads 4.7 and 9.6 mm; fitting only the
      bone within 30 mm of the joint, 4.4 and 6.7 mm. So most of it is
      genuine side-to-side asymmetry of normal hemipelves, and no better
      plane removes it. (This was first attributed to the plane on the
      grounds that right and left read near-identically. They always do:
      fitting the right onto the mirrored left and the left onto the
      mirrored right are mirror images of one problem.) The four CLINIC main
      bodies read 15.7-24.5 mm, inside the normal range, so that is not
      evidence of displacement.
      - **The surgeon's ruling (DECISIONS 1.5):** the outcome number is the
        local widest gap and step across each fracture surface and across
        the symphysis, measured with no reference; the transform home is
        the pre-operative manoeuvre guide, always printed with this floor.
        The floor table is in DECISIONS, under section 1.
      - **Corridor Finder must not apply `to_reference` to a real CT**: on a
        typical patient it would land the hemipelvis about 5 mm off at the
        SI joint and 7-10 mm off at the symphysis. The engine enforces this:
        every `FragmentSet` carries the reason in `to_reference_unvalidated`,
        and `reduce_labels` refuses unless called with
        `accept_unvalidated=True`, which only the phantom tests use.
- [ ] **The plane uncertainty underestimates the plane error.** It is the
      spread between the two references. On the phantom it is 0.86 mm,
      while the undisplaced main body reads 1.6 mm of travel caused by the
      plane alone. On real cases it is 1.8, 11.6, 6.6 and 16.1 mm on the
      four CLINIC cases, and 0.0-32.4 mm on the normals. On sacral fractures
      it partly measures how the fractured sacrum corrupts the L5 + central
      sacrum plane.
- [ ] **The calibrated sacrum measurement has a floor of its own.** On an
      exactly symmetric phantom its self-symmetry median is 1.2 mm (L5) and
      1.8 mm (L5 + central sacrum). That is the spacing of 4000 points drawn
      from sets of different size, not asymmetry, so part of the 0.6 mm
      "penalty" seen on normal pelvises may be the measurement itself. Two
      more properties, reported rather than changed, because the 0.70 mm
      threshold is only meaningful in the measurement it was calibrated in:
      - the penalty moves by about 0.04 mm with the draw alone, and
        CLINIC_0012 sits at 0.73 mm, right at the threshold;
      - its central-sacrum strip runs along the scanner's x axis, so a
        patient lying turned adds to the penalty.
      The plane that is *used* is refined on dense points with the strip
      taken about the plane itself (on the turned phantom the scanner strip
      alone pulled the plane 1 degree).

Engineering choices the surgeon or the lead should check:

- **DECISIONS 3.2 applied to pieces of a candidate.** On the turned
  phantom, the 5 mm fragment's own piece was exactly the fragment (recall
  1.00, purity 1.00). But voxel asymmetry left 28 islands of 0.4-1.8 cm3
  over the main body that its transform explained marginally better.
  Counted as part of it, they failed the one-piece check (85%), and the
  fragment was rejected. Pieces smaller than the minimum fragment for where
  they lie are now carried with the neighbour they touch most ("a smaller
  piece is carried with its neighbour", 3.2) before the one-piece check.
  The check itself is unchanged (90% in one piece). Every number reported
  for a body, and the movement off the main body a candidate is gated on,
  is measured over the surface of the body's mask after that step.
- `DISTINCT_TRANSFORM_FACTOR = 2.0`: the plan names the rule, not the
  factor; it was chosen before any measurement and not tuned.
- The acetabular articular surface is the hip within 6 mm of the femoral
  head, taken from a femur label. Without one, the 2 cm3 ring minimum
  applies everywhere, and the result says so. The femoral head can also be
  found from unlabelled bone of 200 HU or more in the CT, but only when
  asked for (`allow_unvalidated_ct_femur=True`). That heuristic has not been
  compared with a real femur segmentation, so it is not used for anything
  reported (agreed with Corridor Finder, whose articular margin keeps out of
  it for the same reason). The CTPelvic1K labels have no femur, so on the
  four CLINIC cases the ring minimum applied everywhere.
- Fragments of fragments are not searched; every fragment's parent is the
  main body.

Not in this slice, as planned: fracture surfaces and fitting fractures
together (slice 1b, the route for bilateral cases), the five per-point
measurements, the atlas, APP-frame reporting and the study table.

## Running it

From `corridor-finder/`, with the development venv:

    python -m pytest -q                      # the whole engine, including slice 1
    python ../displacement-finder/tools/measure_cases.py --normals 5

The tool reads the CTs and labels under `C:\Users\oom\CorridorFinderData`
read-only and prints everything. Allow about a minute per CLINIC case, and a
few minutes for the normals on 10 workers.
