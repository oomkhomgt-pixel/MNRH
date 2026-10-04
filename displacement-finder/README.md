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
  **`phantoms.sacral_fractured_pelvis`** (slice 1b) cuts one sacral ala and
  hinges the hemipelvis open with its lateral sacral fragment, the lower
  end still in contact, so the sacrum stays one connected label.
- **`fracture_surface.py`** (slice 1b, DECISIONS 7c.1, 7c.3, 7c.5, 7c.6):
  `find_fracture_surfaces` runs si_joint's facing test (`si_joint.facing`,
  an added helper; si_joint's own measurement is unchanged) with one bone
  label against itself, so it cannot see a joint, which always lies between
  two labels. Slots are then vetoed as tubes (canal, foramina), as too small
  (`MIN_PATCH_AREA_MM2`), as having a mirror twin (with a confirmed mirror)
  and as lined with cortex (with the CT); a missing veto is said in the
  notes. Where fragments touch, the surface is slice 1's boundary between a
  fragment's mask and its parent's, joined with any slot between them. The
  surgeon's marks keep a slot against the twin veto and flag every surface
  found far from them. Each mark point is matched on its own, only by a
  surface on the bone it lies on with a face within `MARK_MATCH_MM` (10 mm,
  Corridor Finder's warning radius `reduction.REGION_RADIUS_MM`); every
  mark point with none is flagged and kept (`unmatched_marks`). Each surface has an id (region `fracture_<id>`), two
  faces with what is on each side, points and outward normals, and the
  cortical rim. Each face is its body's whole broken surface: the face
  found is grown over the body's exposed surface continuing its plane where
  the other body no longer lies opposite it, so its rim is the body's own
  outline and not the outline of where the two overlap as scanned.
  `split_sacrum` cuts the lateral sacral fragment off along each side's
  sacral surface; every split is unconfirmed until `confirm_split`, with no
  sacral surface none is guessed, and a cut that is not lateral (plane more
  than 60 degrees from sagittal, piece past the midline or near the other
  hip, two pieces sharing bone) is refused.
- **`congruence.py`** (slice 1b, DECISIONS 7a.5, 7c): `fit_reduction`
  fits where each moving unit goes. Units: each hip bone with its lateral
  sacral fragment (the split, confirmed or not) and its femoral head when
  the labels have one, and each fragment slice 1 promoted. A unilateral
  injury starts from slice 1's `to_reference` (the mirror), a bilateral one
  from where the bones lie. All units are then fitted together by
  point-to-plane steps: fracture rims onto their partner rims (across the
  fracture, and along it against the outer cortex so a face cannot slide,
  where both ends of the pair lie on the cortex);
  a split sacral fracture as the split's whole boundary (slot where it
  gapes, contact where it touches); each SI joint and the symphysis closed
  along their own plane to the width that makes si_joint and
  `symphysis_gap` read their targets (7c.2: the intact side's width capped
  at 4 mm, or 4 mm; 7c.7: `SYMPHYSIS_TARGET_GAP_MM = 4.93`). A motion no
  surface resists is never taken. Each region (`si_right`, `si_left`,
  `symphysis`, `fracture_<id>`) reports max(90th-percentile mismatch after
  the fit, the phantom bound for its kind at its displacement,
  `phantom_bound_mm`, measured per displacement since slice 1c, and the
  mirror's floor where it rests on the mirror), or `inf` with the reason
  when it has too little rim or joint surface, its rims disagree, some
  motion no surface resists moves its two sides relative to each other,
  the fit leaves it as scanned (both faces on one unit: "NOT REDUCED"), it
  is impacted with no mirror to restore it, or the fit moves it, or a unit
  of it, further than any phantom the bound was measured on
  (`PHANTOM_TRAVEL_MM`). An impacted fracture (slice 1c, 7d.6) has its
  rims fitted along it and the length lost across it taken from the mirror
  start; it, and any region or unit only that pins
  (`unit_<name>_on_mirror`), rests on the mirror and carries its floor.
  A fracture the surgeon marked is a region too wherever a mark point has no surface matching it
  (`fracture_mark_<k>`, `inf`, at those mark points and over the marked
  plane within `fracture.NEAR_MARKS_MM` of them, on a 5 mm grid). A unit
  that some motion no trustworthy surface resists moves as a whole stays
  at its start along that motion (regions unconstrained for their own
  reasons do not count toward pinning it), so the whole unit is a region,
  `unit_<name>_unpinned`, `inf`,
  covering all its bone (one voxel per 2.9 mm cell, every voxel within
  5 mm of one), not only the joints beside it; so is a unit no region
  touches. Each
  unit that departs from its mirror start by more than the mirror's normal
  floor is flagged (7c.4), at a joint from either of its sides. `CongruenceFit.reduction()` builds Corridor Finder's
  `reduction.Reduction` directly, with `accepted_by` left None and every
  flag in its notes, first among them that it is not accepted (7c.8).
  `symphysis_gap` (the measurement the 7c.7 target was taken with) lives
  here, and `tools/symphysis_gap.py` imports it.
- **`phantoms.bilateral_sacral_fractured_pelvis`** (slice 1b): both sacral
  alae fractured, each hemipelvis hinged and slid with its own lateral
  fragment (CLINIC_0060's pattern), so nothing intact is left to mirror.

This directory keeps only what is this project's own: `DECISIONS.md`, this
README, `tools/measure_cases.py`, which runs the engine over the real
CTPelvic1K cases on this workstation and prints what it finds,
`tools/symphysis_gap.py`, which measures the symphyseal gap on the normal
pelvises (DECISIONS 7c.7) with the engine's own `congruence.symphysis_gap`,
and `tools/phantom_bound.py`, which runs the phantom family behind the
congruence fit's per-displacement bound (DECISIONS 7d.2) and prints it.
Nothing they read or print is committed (DECISIONS 8.1).

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

Not in slice 1, as planned: fracture surfaces and fitting fractures
together (slice 1b, the route for bilateral cases), the five per-point
measurements, the atlas, APP-frame reporting and the study table.

## Status: slice 1b (fracture surfaces, sacral split, symphyseal gap, reduction by congruence)

Built: `fracture_surface.py`, `congruence.py`,
`phantoms.sacral_fractured_pelvis` and
`phantoms.bilateral_sacral_fractured_pelvis`, `si_joint.facing` (an added
helper) and `tools/symphysis_gap.py`; `tools/measure_cases.py` now also
prints fracture surfaces, sacral splits and the congruence fit. Part A is
the fracture surfaces and the sacral split, part B the congruence fit.

### Part A: fracture surfaces, the sacral split, the symphyseal gap

- [x] **The facing test never sees a joint** (plan test 7). On the intact
      phantom turned 6 degrees, with and without the mirror, not one slot
      voxel of the sacrum or either hip lies in empty space within 6.75 mm
      of two different bones (both SI joints, the symphysis, both hip
      joints, L5/S1), and with the mirror nothing is accepted at all. To
      show the test can fail: with every bone given one label, the same
      search finds 1357 and 1355 slot voxels in the two SI joints, 1790 and
      1780 in the hip joints, 116 in the symphysis and 13 at L5/S1.
- [x] **A gapped fracture is found where it was cut.** The phantom's iliac
      wing moved 5 mm (gap 4.81 mm across the cut): one surface, its faces
      100% on their own side of the cut, 1.30 and 1.29 mm off the true
      plane (p90; 0.72 and 1.11 mm before the faces were grown to the whole
      broken surface), mean normal 2.4 degrees off. The gap reads 5.21 mm,
      centre to centre as si_joint reads a joint (taking a voxel off read
      3.7 mm, because the nearest bone voxels already sit at each face's
      shallow edge). Rims: 330 of 682 and 312 of 606 face voxels on the
      grown faces.
- [x] **Vetoes on the phantom.** Matching 3 mm slots cut into both upper
      ilia are removed as mirror twins and one on one side is kept; a
      transverse slot across the sacrum is kept (its own mirror image does
      not count); a surgeon's mark near one twin keeps it, flagged; with a
      synthetic CT, a cancellous face is kept and a face painted as cortex
      is removed. The phantom's tunnels and crevices are removed as tubes
      or twins.
- [x] **Where fragments touch** (the zero-width route). With the
      phantom's own fragment mask, a fragment slid 5 mm along its fracture
      gives a boundary 1.33 mm off the true plane (p90). **With slice 1's
      masks it is poor:** on the same slide, find_fragments' fragment is
      93% pure and 94% complete, and its boundary lies p50 3.7 / p90 25.5
      mm off the fracture (a 2.9 cm3 piece of fragment up to 30 mm above
      the cut was given to the main body, and 2.8 cm3 of main body below it
      to the fragment). Taken over the fragment's whole mask, islands made
      it p90 35-100 mm; only its largest piece is used now. Every such
      surface is flagged as slice 1's mask boundary. Where the fragment
      opened a gap, the slot joins its surface and it lies 0.3 / 0.6 mm off
      (p50 / p90).
- [x] **The sacral split** (plan test 8). On the hinged sacral fracture,
      one connected sacrum, the lateral fragment is cut off with recall and
      purity 1.000 on each side; the plane carries the cut across the
      contact (a slot over about 78% of it). Every split says it is
      unconfirmed until `confirm_split`; with no sacral surface on a side,
      none is guessed.
- [x] **A cut that is not lateral is refused.** A 3 mm transverse slot
      across the sacrum, its centroid right of the midline, was split as
      the right lateral fragment: the whole sacrum above it, both alae and
      both SI joints. Each of three checks now refuses it on its own: the
      plane's normal lies 90 degrees from left-right (refused past 60,
      `SPLIT_MIN_LATERAL_COS`); the piece reaches 32 mm past the midline
      (`SPLIT_MIDLINE_MM = 5`); it comes within 3.4 mm of the left hip
      (`AURICULAR_MAX_MM`). Two pieces sharing bone are both refused, and
      `fit_reduction` refuses units that share voxels. The thresholds are
      chosen, not calibrated.
- [x] **The symphyseal gap on normal pelvises** (DECISIONS 7c.7),
      `tools/symphysis_gap.py`: the facing test between the two hip bones
      (each within 8 mm, si_joint's AURICULAR_MAX_MM), the gap centre to
      centre, per axial level the median, and per pelvis the median over
      its levels. **Median 4.93 mm, range 2.43-7.65 mm (5th-95th percentile
      3.32-6.20), on 258 of the 275 normal label files**: ABDOMEN 4.63 (35),
      MSD Task 10 4.90 (155), KITS19 4.72 (27), CERVIX 5.23 (41). The other
      17, all KITS19, are scans that stop above the symphysis (the hip
      bones run off the lowest slice, 68-84 mm apart at their closest). The
      phantom's 6 mm symphysis reads 7.5 mm at 1.5 mm voxels and 7.0 mm at
      1.0 mm: centre to centre is the gap plus about a voxel, so the target
      is only meaningful measured the same way.
- [ ] **On the four CLINIC cases the sacral fractures are not found.**
      `measure_cases.py`, against the surgeon's reading (DECISIONS 7b):
      - CLINIC_0012: the right pubic body and rami fracture is found, as
        slice 1's fragment boundary (129 mm2). The right sacral fracture is
        not: the largest sacral slot, 1187 mm2 in the right ala, a sheet
        with no mirror twin (9%), is removed by the cortex test (its face
        reads 0.70 of the patient's sacral cortex, 307 HU; the veto is at
        0.60);
      - CLINIC_0023: nothing found. Right sacrum read: its slots (195 and
        84 mm2) read 0.83 and 0.66 of cortex; both pubic bodies read: their
        two slots (61 and 55 mm2) are removed as a tube and by cortex;
      - CLINIC_0025: two surfaces in the left pubic body and superior ramus
        (101 and 75 mm2, the first in bone slice 1 could not carry home),
        where he read the left superior ramus; one at the right pubic body
        (135 mm2), where he read the right acetabulum and no pubic
        fracture. Left sacrum read: its slots (251, 133 mm2) read 0.80 and
        0.61 of cortex;
      - CLINIC_0060: one 44 mm2 slot in the right ala, and it is
        **transverse**: its faces lie caudad and cephalad, its normal 86
        degrees from left-right. The right split that was cut along it
        (20.1 cm3, 98% of the cut carried on by the plane) was the
        review's transverse case on real data, and it is now refused as
        not lateral. Nothing in the left sacrum (slots of 490 and 345 mm2
        read 0.86 and 0.94 of cortex) or the anterior ring.
      **The cortex test does not separate the sides he read**: slots as
      large appear in the sacral ala he did not read as fractured (0023
      left 756 mm2, cortex 0.78; 0025 right 676 mm2, 0.94), and the
      ratios on both sides span 0.61-1.22. `CORTEX_FRACTION = 0.6` is an
      interpolation from two patients and has not been tuned to these
      cases; without it the slot route would report sacral fractures on
      the wrong side as well. What tells a sacral fracture from these
      slots is not known yet.
- [ ] Not re-measured: `MAX_FRACTURE_SLOT_MM`, `SHEET_ASPECT` and the twin
      tolerances are the slice 1 architect's values. With this detector the
      roughness count is lower than his (31-66 slots under 40 mm2 per
      sacrum, 1-17 per hip, against his 240-819 clusters with a closing
      detector), so `MIN_PATCH_AREA_MM2` was not the deciding veto here.

### Part B: reduction by congruence

All on phantoms at 1.5 mm voxels (`tests/python/test_congruence.py`).
"Lands" is the worst distance, before rounding onto the grid, between where
the fit puts a point of a region and where it belongs once the region's
other side is put where it belongs; each point's true reduction comes from
the phantom, not from the units the fit built. The worst surface point is
taken over the whole moving unit. Most fits are given the phantom's own
normal joint widths as targets, measured the way 7c.2 and 7c.7 measure
them (its 6 mm symphysis reads 7.5 mm, wider than 255 of the 258 normals
behind the 4.93 mm target; its SI joints read 4.7-4.9 mm against the 4 mm
cap). That measures the fit; what 7c's targets do to this phantom is
reported separately below.

- [x] **What the review found, and why** (2026-10-03). The right sacral
      fracture slid 6 mm up or forward (7c's targets) was fitted 5.61 mm /
      1.32 degrees and 9.41 mm / 3.33 degrees off **from the exact start**,
      the same pose as from the scanned one; the fracture reported 3.5 mm
      and landed 4.49 and 5.03 mm off, the symphysis 6.5 mm and 8.66 mm.
      Two causes, both fixed:
      - each face was only where the two bodies overlap as scanned, so its
        outline, the rim, was the outline of the overlap, and the two rims
        agreed in the scanned pose by construction (not only the split's
        plane-carried cut: the slot's faces too). Each face is now its
        body's whole broken surface (`fracture_surface._whole_faces`);
        grown without the "other body opposite" test, it spread over the
        crushed phantom's crater floor and the fit ran off 118 mm;
      - a face voxel that is a rim only because exposed fracture surface
        lies beside it gave a sliding row against the partner's cortex: on
        the left phantom slid 6 mm up such points 10 mm down the face pulled
        8-9.5 mm toward the scanned pose. A sliding row now needs both ends
        on the outer cortex.
      What remains is the evidence's error, not the search's: on the right
      phantom slid 6 mm up, the fit's own cost is 0.71 where it lands and
      0.87 at the truth. The rims resist a slide along the fracture only at
      the outline.
- [x] **Unilateral recovery** (plan test 1), hinged 3 degrees and slid
      1.5 mm (right) or 1 mm back and 1 mm up (left):
      - right, from the exact plane: 1.22 mm / 0.58 degrees off at its worst
        surface point; the fracture lands 0.82 mm, the symphysis 0.45 mm;
      - right, from a mirror start 5 mm and 3 degrees off (7.76 mm at the
        worst point): 1.25 mm / 0.59 degrees; lands 0.83 and 0.45 mm; the
        hip is flagged for departing 7.1 mm from its mirror start at the SI
        joint (over the 4.7 mm floor);
      - left, from the same wrong start (7.84 mm): 0.94 mm / 0.48 degrees
        (5.42 mm before the sliding-row fix); lands 0.56 and 0.95 mm.
- [x] **Larger slides** (plan tests 1, 2 and 6 over the family the bound is
      measured on), each from the exact start and the wrong mirror start,
      the phantom's own targets:
      - each sacral side slid 6 mm up, forward or back, or 4 mm down: the
        hip ends 0.53-3.26 mm off at its worst surface point (the right
        side slid 6 mm up: 2.27 mm from the exact start, 2.63 mm from the
        wrong one);
      - both sides slid 6 mm (right up, left forward; right back, left up
        4 mm): 1.78-4.66 mm, no mirror;
      - the iliac wing opened 2-3 mm and slid 4-6 mm along its fracture:
        the fragment 1.92-4.57 mm, except opened 2 mm and slid 4 mm from
        the wrong start, where the fit ran off 19.4 mm; that fracture reads
        `inf` (its rims disagree, 3.2 mm).
      Every region that reports a number lands within it.
- [ ] **The split's own error grows with the slide.** Where the faces
      touch, the plane carries the cut across bone with no gap in it, and
      a voxel within half a voxel of the fracture can go either way: on a
      6 mm forward or back slide the split gives 10-16 voxels of the
      lateral fragment to the central sacrum, and they stay 6.0-6.24 mm
      from home; at 10 mm, 79-83 voxels, 10.3 mm. It is the split the
      surgeon confirms (7c.5), but its error is in the fracture region's
      landing, and it is what sets the fracture bound below.
- [ ] **The error measured on phantoms, and how far it was measured.**
      (Superseded in slice 1c by a bound measured per displacement to
      30 mm; see below. As slice 1b left it:)
      `PHANTOM_BOUND_MM` was the worst landing over the family above where
      the region reported a number, rounded up to half a millimetre:
      **fracture 6.5 mm** (6.24, the split's voxels; the fit itself lands
      within 4.62 mm, the iliac wing slid 4 mm from the exact start), up
      from 3.5 mm; **symphysis 6.5 mm**, kept at what an earlier fit
      measured on the half-crushed rim (6.26 mm; this family measures
      3.38 mm); the **SI joint** has never been measured where it is what
      pins a hip (the phantom's SI joint is flat; with a sacral split it
      moves with its unit), so it takes the largest, 6.5 mm.
      **The bound says nothing past the displacements it was measured
      on.** `PHANTOM_TRAVEL_MM` is how far the fit moved a region's two
      sides relative to each other on that family, rounded up: fracture
      8.0 mm (measured 7.99), symphysis 9.5 mm (9.31), the SI joint the
      largest. A region moved further, or any region of a unit moved
      further at another region, is `inf`. Slid 10 mm up from the wrong
      start, the fit stopped short: its symphysis moved only 6.5 mm and
      read the 6.5 mm bound while landing 8.4 mm off; its fracture moved
      10.2 mm, so every region of that hip now reads `inf`. All five 10 mm
      fits read `inf` everywhere. The bounds were measured on the same
      phantoms the round-trip test checks, not on held-out ones, at one
      voxel size, with a hinge of at most 3 degrees.
- [x] **Bilateral recovery** (plan test 2, CLINIC_0060's route), both sacral
      alae fractured, each hemipelvis hinged and slid with its own lateral
      fragment, no mirror: the right hemipelvis goes from 6.29 mm / 3.00
      degrees off to 3.08 mm / 1.40 degrees, the left from 4.04 mm / 2.00
      degrees to 1.98 mm / 0.82 degrees. The fractures land 1.06 and
      1.37 mm, the symphysis 2.78 mm. Each hip is still not pinned down as
      a whole: a free motion moves it 0.63-0.64 mm per mm while moving no
      region's two sides apart by 0.25 mm per mm, so every region reads its
      bound and each hip is a region of its own, `unit_hip_<side>_unpinned`,
      `inf` (since the second review): a screw anywhere in either hip is
      warned.
- [x] **Null** (plan test 3). The undisplaced phantom with its own targets
      moves 0.91 mm / 0.39 degrees (si_joint's width, the 90th percentile
      of the anterior gap over levels, is not a facing pair's gap: the
      phantom's pairs read 4.5 mm against 4.86 mm). Its SI joint and
      symphysis are flat, so with no fracture a hip can slide along them,
      and both read UNCONSTRAINED, as does the hip as a whole (1.04 mm per
      mm). **With 7c's targets it moves 3.09 mm /
      1.30 degrees**: the 4 mm cap and the 4.93 mm target close joints this
      phantom has at 4.9 and 7.5 mm.
- [x] **Comminution** (plan test 4), each from the wrong mirror start:
      - half the face crushed, rim and all (7.6 cm3): the hip ends 2.05 mm
        off and the fracture lands 1.17 mm, but with fewer sliding rows a
        slide along it is no longer resisted (0.53 mm per mm), so it reads
        UNCONSTRAINED, as does the symphysis;
      - the cancellous bone behind the face crushed, rim kept (2.4 cm3):
        the crushed bone adds a second slot and **split_sacrum refuses**
        (one plane no longer separates the faces), so the lateral fragment
        does not move with its hip. Both sacral surfaces are left as
        scanned and read NOT REDUCED (they reported their 10.0 and 9.8 mm
        gap as a finite error before); the SI joint and symphysis read
        UNCONSTRAINED. No region reads a small wrong number.
- [x] **Unconstrained** (plan test 5). The iliac wing fracture with 5 rim
      points per face kept: 2 rim pairs, `inf`, "too little rim", and
      `reduction.Reduction` takes it (the plan records null and lists it as
      unconstrained; Corridor Finder warns at it whatever the screw's
      room). Rims pushed 5 mm apart alternately read "rims disagree" (5.0
      mm). A promoted fragment with no fracture surface gets its own
      region, `inf`, so a moving unit is never missing from the regions.
- [x] **Never a missing key, never a small number** (the review,
      2026-10-03):
      - a fracture left as scanned (both faces on one unit, or on bone that
        does not move: every bilateral case's iliac or pubic fracture, any
        slot on a side that is not moved, a sacral fracture whose split was
        refused) reads `inf`, "NOT REDUCED". Its rims' mismatch did not
        measure it: the iliac wing opened 3 mm and slid 6, 12 and 20 mm,
        fitted as both injured, read 4.3, 4.9 and 5.4 mm (the review's
        measurement, before the faces were grown; 5.0 mm at 6 mm now);
      - a fracture the surgeon marked is a region, `fracture_mark_<k>`,
        `inf`, at every mark point with no surface on its own bone within
        10 mm, moved with the unit it lies on (a mark low on the moving
        right hip moves with it, one on the static left hip stays), and
        Corridor Finder warns there. Matched mark by mark (the second
        review, 2026-10-03): matched as a whole within 20 mm, a sacral
        fracture marked twice on the face found and once on the sacrum
        40 mm from every face read as matched, and so did marks on L5 6-9 mm
        from a hip's
        surface or 15 mm from a surface on their own bone; each now makes
        its region. The region covers the marked plane out to
        `fracture.NEAR_MARKS_MM` (20 mm, as far as Corridor Finder treats
        the plane as the fracture) around each unmatched mark, not only the
        mark: a screw crossing the marked fracture 15 mm from the mark, past
        the 10 mm warning radius of the mark alone, is now warned (the third
        review's finding, fixed by the lead and tested);
      - a unit nothing pins as a whole is a region over all its bone,
        `unit_<name>_unpinned`, `inf` (the second review): the undisplaced
        phantom's hip, held only by its flat SI joint and symphysis, moves
        1.04 mm per mm under the motion they leave free, and hip bone more
        than 15 mm from both joints, which their regions never warned at,
        now warns from it. **Only trustworthy surfaces pin a unit** (the
        third review's finding, fixed by the lead): a region unconstrained
        for its own reasons (too little rim, rims that disagree, not
        reduced, moved beyond the phantoms, no joint found) no longer counts
        toward pinning, which can only add warnings, never remove one. Such a
        region reports its own reason, and a unit displaced beyond the
        phantoms names that root cause on every one of its regions, beside
        any other reason. Tested by making every region untrustworthy: the
        right hip, pinned otherwise, then carries an unpinned region;
      - a region's own notes are in the Reduction's notes under its name;
      - on a left injury the hip's departure from its mirror start is
        measured at the symphysis too (it is the side paired to there):
        5.94 mm, against 5.92 mm on the right.
- [x] **Round trip** (plan test 6) through `reduction.apply_moves`: from the
      wrong mirror start (unilateral) and on the bilateral phantom, the
      reduced right hip overlaps the intact one 0.963 and 0.915 (Dice), the
      left 1.000 and 0.930, the sacrum 0.992 and 0.973; no unit puts more
      than 2% of its voxels on static bone; every region lands within its
      reported residual, here and on the larger slides above.
- [x] **What the Reduction carries.** `accepted_by` None and the first note
      says it is not accepted (7c.8); the unconfirmed split, the mirror
      departures, the unconstrained regions with why, each region's own
      notes, the fracture surfaces' own notes and flags, and how each
      target was set are all in the notes. With `confirm_split`, the split
      is said confirmed and by whom.
- [ ] **What the residual does not contain.** How far this patient's own
      normal symphysis lies from the 4.93 mm median (the normals' 5th-95th
      percentile is 3.32-6.20 mm), and whether the 4 mm SI cap is this
      patient's joint. On the phantom, whose symphysis is wider than almost
      every normal, the 7c.7 target pulled the symphysis 2.7 mm from where
      it belongs; where the rims hold the pose, the mismatch to the target
      shows it, and where nothing holds the pose it does not. Every
      Reduction says so in its notes. Whether the region's error should
      include the normal spread is a ruling for the surgeon and Corridor
      Finder.
- [ ] Engineering choices found by measurement on the phantoms, each with
      its reason in `congruence.py` or `fracture_surface.py`, none
      calibrated on real anatomy: pairs only where the two surfaces face
      each other squarely (within 25 degrees; looser, the pubic bodies'
      curved surround and the rims' corner voxels dragged the fit 8-11 mm);
      a rim's fracture direction taken from the face around it (its own
      normal leans toward the cortex); a sliding row only where both ends
      lie on the cortex; whole faces grown within 3 mm of the found face's
      own plane, facing within 45 degrees, with none of the other body
      within 12 mm along the normal; a split sacral fracture fitted as the
      split's whole boundary (the slot alone has nothing facing down, and
      the bilateral fit pivoted 2 degrees); joints closed along their own
      plane (the edges of flat joints otherwise walked the undisplaced hip
      5 mm and sheared the bilateral symphysis 7 mm); joint pairs kept
      until the fit settles; a motion no surface resists is never taken
      (`PIN_MIN_SLOPE = 0.1`); `RIMS_DISAGREE_MM = 3.0`. Tried and dropped:
      relating the joint's pairs to si_joint's measurement through the
      intact joint (on CLINIC_0012 it asked for a -0.5 mm joint),
      mutual-nearest rim pairs and an empirical rim separation (neither
      helped across the phantoms); a face plane through both faces with a
      6 mm band (it took the crater floor).

- [ ] **On the four CLINIC cases the fit is not usable, and says so:
      every region of every case reads `inf`.** `measure_cases.py`
      (7c's targets; 54-76 s a case with 2 workers). Part A finds no
      sacral fracture surface on 0012, 0023 or 0025, and on 0060 only a
      transverse slot that is not split, so on no case does a sacral
      fracture hold a hip to the sacrum; only the SI and symphysis targets
      do, and those leave the hip free to slide:
      - CLINIC_0012 (right): units the right hip and slice 1's pubic
        fragment. The fragment's boundary with the hip (slice 1's masks,
        flagged as such) read 3.5 mm before; it now reads UNCONSTRAINED:
        the fit moves the hip 13.3 mm at the SI joint and the fragment
        16.3 mm at the symphysis, beyond the 9.5 mm any phantom was
        measured at. The SI joint and symphysis read UNCONSTRAINED (free
        motions). The hip moves up to 21.7 mm (9.6 degrees) from where it
        lies and 36.2 mm from its mirror start, the fragment 23.4 mm (22.6
        degrees); every departure over the mirror's floor is flagged. The
        SI target is the 4 mm cap (the intact left joint reads 7.57 mm);
      - CLINIC_0023 (right): no fracture surface; the hip moves 15.2 mm
        (4.4 degrees), 12.0 mm from its mirror start (flagged at the SI
        joint, 7.6 mm, and the symphysis, 11.6 mm); SI joint and symphysis
        UNCONSTRAINED;
      - CLINIC_0025 (left): the three slots part A found (the right pubic
        body, 135 mm2, and two in the left pubic body and superior ramus,
        101 and 75 mm2) lie each within one unit or on static bone. They
        reported finite 4.3, 5.4 and 3.5 mm before; each now reads NOT
        REDUCED (rims' mismatch 4.5, 6.4 and 6.8 mm). The hip moves
        17.6 mm (5.0 degrees); SI joint (target 2.77 mm, the intact right)
        and symphysis UNCONSTRAINED. The surgeon's marks are not given to
        the tool here; with them, his left superior ramus would be a
        region of its own wherever no surface lies near it;
      - CLINIC_0060 (both): no split (above), so the sacral slot is left as
        scanned and reads NOT REDUCED (mismatch 5.2 mm); both SI joints
        UNCONSTRAINED, the symphysis UNCONSTRAINED with 11 facing pairs
        left after the fit. The hips move 9.0 and 9.2 mm.
      Every moving unit on every case is not pinned down as a whole (a
      free motion moves it 0.90-1.04 mm per mm), so each is also a region
      over all its bone, `unit_<name>_unpinned`, `inf` (rerun after the
      second review, 79-110 s a case with 2 workers): a screw in that bone
      far from the joints and fractures is warned, where before only the
      regions within 10 mm of it could warn. On 0023 that is the whole
      right hip, which the fit put 12.0 mm from its mirror start.
      Every Reduction says it is not accepted. What these cases need first
      is their sacral fractures found (part A's open problem), and a
      measured SI-joint bound.

## Status: slice 1c (finding fractures on real CTs)

DECISIONS 7d. **In one sentence: both parts work on phantoms, and on the
four CLINIC cases none of the lateral sacral fractures the surgeon read is
found, so no real case is reduced by its sacral fracture yet.**

Part A, `fracture_surface.py` (7d.1, 7d.5): the CT route (a lucent line
with a broken cortex, and the dense band of an impacted fracture), the
surgeon's marks as the backup surface, a `source` on every surface (`gap`,
`ct_lucent`, `ct_impacted`, `surgeon_marks`) and the impaction depth on
impacted ones; synthetic CTs in `phantoms.py` (`pelvis_ct`,
`intact_pelvis_with_ct`, `lucent_fractured_pelvis`, `lucent_sacral_pelvis`,
`impacted_sacral_pelvis`). Part B, `congruence.py` (7d.2, 7d.6): the
phantom bound measured per displacement (`phantom_bound_mm`, the family in
`tools/phantom_bound.py`), and impacted fractures reduced by their rims and
the mirror.

### Part A: finding fractures from the CT

- [x] **A gaping fracture the label is painted across is found from the
      CT** (plan test 1). The phantom's iliac wing fracture opened 3 mm and
      its label painted solid across the gap: slice 1b finds nothing; the CT
      route finds one surface, `ct_lucent`, 1228 mm2, faces 97% / 98% on
      their own side, p90 1.57 / 1.65 mm off the true cut, normal 6.1
      degrees off, gap 4.50 mm centre to centre (the gap plus about a
      voxel, as si_joint reads a joint), 118 voxels of broken cortex at 4%
      of the cortex HU. Nothing else is found anywhere in the pelvis.
- [x] **An impacted sacral fracture is found as `ct_impacted`, with its
      depth** (plan test 2). One solid sacrum, the lateral fragment driven
      in 4 and 6 mm, the band 400 HU denser than the bone it lies in (twice
      the margin): depth read 3.83 and 6.18 mm (tolerance one voxel,
      1.5 mm), 100% of the band found and 99-100% of the zone within a
      voxel of it, compared with the mirrored side.
- [ ] **An impaction no denser than its two layers of bone is not found.**
      The phantom's own band (the fragment's bone laid on the central
      sacrum's: about +160 HU here) is under the 200 HU margin and is not
      found; the result says that a band fainter than the margin is not
      seen and never reads as an intact sacrum (pinned in a test). In
      CLINIC_0012's sacrum the interior reads a median 110 HU, so such a
      band would add about 70 HU there. How dense a real impacted band is
      has not been measured.
- [x] **Dense subchondral bone is never read as a fracture** (plan test
      3). The intact phantom with dense subchondral bone under every joint,
      thicker on the right (4 against 3 mm), gives no surface, lucent or
      impacted, against the mirror or against its own nearby bone. Against
      its nearby bone 7 dense bands are examined and every one is removed
      as dense against one side only.
- [x] **The marks are the backup only where nothing is found** (plan test
      4). With the CT blinded (the CT of the same labels, no band), the
      plane through four marks becomes the surface, `surgeon_marks`, a cut
      one voxel thick within 20 mm of the marks, flagged "NOT FOUND", its
      marks still listed as unmatched. With the band in the CT, the band is
      the surface (2 mm from the nearest mark) and no marks surface is
      added. With no CT given the marks stay as slice 1b made them,
      unmatched and flagged: whether the CT shows a fracture there is not
      known (slice 1b's mark tests, unchanged, run without a CT).
- [x] **The sacral split works from every source.** Recall 1.000 and
      purity 1.000 cut along a painted-over lucent line (painted voxels left
      out of purity), along the dense band (recall over the fragment outside
      the band, which is bone of both) and along the marked plane, where the
      split says it rests on his marks and counts none of the cut as found.

How each part works, and what was tried and changed:

- **Lucent line.** Each voxel darker by `LUCENT_MIN_CONTRAST_HU` (100) than
  the bone on both sides along one of 13 directions, within 3 mm, and at
  least half-way down to soft tissue. The CT is smoothed (1 mm) over each
  layer of the bone separately, interior and rind: smoothed across the
  surface, the one-voxel phantom cortex bled into the bone under it and the
  marrow of the whole iliac wing read as one 12000-14000 mm2 lucent line.
  Interior voxels are compared with interior bone, rind voxels with rind
  along the surface (the cortex either side of the break). A patch must be a
  sheet, break the cortex (3 or more rind voxels under 0.6 of the cortex),
  cross the bone beneath it (3 or more interior voxels: a lucency in the
  cortex only is thin cortex), and pass the mirror-twin veto. Its faces are
  the first voxels either side at least half-way back up to the bone, so the
  painted gap's own voxels are never a face.
- **Dense band.** Interior bone (3 mm deep) is compared with the densest
  interior bone within 5 mm of its mirrored place (or, with both sides
  injured or no mirror, the patient's own cancellous bone within 15 mm: the
  mean of the interior there, recomputed without what is denser than it by
  the margin). Over the margin, the largest core first, a band is the bone
  around it down to half its height above the bone's usual excess, so its
  thickness (volume over projected area, the impaction depth) does not
  depend on the margin. It must be a sheet, reach the bone's outer layers,
  and have bone of the usual density on both sides of its middle over at
  least half of it (`IMPACTION_FLANKED_SHARE`): subchondral bone lies
  against its joint surface with bone on one side only. Without that test,
  the displaced phantom's subchondral bone at the SI joint, 4 mm from its
  mirror image and thicker on that side, read as three 200-680 mm2 bands.
- **The margin, `IMPACTION_MARGIN_HU` = 200 HU**, measured on the only
  fully intact side there is, CLINIC_0012's left hip and left sacral half,
  never on the fractures: the 99th percentile of how much denser each
  interior voxel there is than the densest bone within 5 mm of its mirrored
  place, 189 HU (hip) and 171 HU (sacrum), rounded up. With every veto,
  that side shows no band against the mirror at any margin from 0 to
  400 HU, and one against its own nearby bone at 100 and 150 HU, none from
  200 HU. One side of one patient; normal-pelvis CTs are not on the
  workstation (only their labels).

### Part B: the bound per displacement, and impacted fractures

All on phantoms at 1.5 mm voxels (`tests/python/test_congruence.py`;
`tools/phantom_bound.py` for the table). "Lands" is as in slice 1b: the
worst distance, before rounding onto the grid, between where the fit puts a
point of a region and where it belongs once the region's other side is put
where it belongs.

- [x] **The bound is measured per displacement** (7d.2, plan test 5).
      `tools/phantom_bound.py` runs 117 fits: slice 1b's whole family, the
      same fractures displaced 5, 10, 15, 20, 25 and 30 mm with rotation
      (each sacral fracture hinged 3 degrees and slid up or back, right and
      left, from the exact and from the wrong mirror start; both sides at
      once, right up and left back; the iliac wing opened 2 mm, turned
      3 degrees about its fracture's normal and slid laterally or forward,
      both starts), and the impacted sacral fractures. A region's
      displacement is how far the fit moved its units, relative to what they
      are joined to, at it or at any other region: a fit that stops short
      moves a region less than its unit is displaced (the sacral fracture
      slid 10 mm up from the wrong start: the symphysis moved 6.5 mm and
      landed 8.4 mm off, the fracture moved 10.2 mm), so the bound is read
      where the unit was found displaced. At each displacement, the worst
      landing of a region displaced between the displacements either side
      of it, and the bound (rounded up to half a millimetre, never smaller
      than at a smaller displacement, interpolated between):

      | Displacement, mm | 0 | 5 | 10 | 15 | 20 | 25 | 30 |
      | --- | --- | --- | --- | --- | --- | --- | --- |
      | Fracture, worst landing | 1.86 | 6.24 | 10.86 | 15.37 | 25.13 | 25.67 | 25.67 |
      | Fracture, bound | 2.0 | 6.5 | 11.0 | 15.5 | 25.5 | 26.0 | 26.0 |
      | Symphysis, worst landing | 0.95 (6.26 kept) | 4.04 (6.26 kept) | 12.22 | 12.22 | 4.87 | 3.82 | 3.02 |
      | Symphysis, bound | 6.5 | 6.5 | 12.5 | 12.5 | 12.5 | 12.5 | 12.5 |
      | SI joint, bound (the largest) | 6.5 | 6.5 | 12.5 | 15.5 | 25.5 | 26.0 | 26.0 |

      The symphysis keeps, at 0-5 mm, the 6.26 mm an earlier fit measured on
      the half-crushed rim, which slice 1b kept; the present fit reads no
      number there, and the bound is not lowered below it. The SI joint is
      never measured where it pins a hip (its regions here have both sides
      on one unit and land 0), so it takes the largest. Nothing smaller than
      a 3.9 mm displacement was run, so the bound at 0 is the one measured
      between 0 and 5 mm. Measured on the same phantoms the tests check, not
      on held-out ones, at one voxel size.
- [ ] **What the fracture bound is made of: the split, not the fit.** The
      worst fracture landing at every displacement from 5 mm on is the
      sacral split's own error. Where the faces touch, the plane carries the
      cut across bone with no gap in it, and voxels within half a voxel of
      the fracture go to the wrong piece and stay as far from home as the
      slide: 6.24 mm at a 6 mm slide, 10.86 at 10, 15.37 at 15, 25.13-25.67
      at 25 (slid back, and the left side slid up). The fit itself mostly
      lands far closer: the same fractures slid up land 0.9-3.1 mm at
      10-25 mm (the left one slid 25 mm up excepted, the split again), the
      iliac wing 0.8-7.8 mm, except 12.16 mm slid 10 mm laterally from the
      exact start (the fit moved it 19 mm). So **past about 10 mm a fracture region's bound
      is about its own displacement**, too large to tell any screw it is
      safe. What would make large displacements useful is a better split
      where the faces touch, not a different bound.
- [ ] **The symphysis bound jumps to 12.5 mm at 10 mm** because of one
      fit: the bilateral phantom slid 10 mm (right up, left back), with no
      mirror to start from, stops short (its symphysis moved 5.4 mm while its
      units moved 10.5 mm) and the symphysis lands 12.22 mm off. On every
      unilateral fit to 27 mm the symphysis lands within 4.87 mm. The
      bilateral phantom slid 15-30 mm reports no number anywhere (rims
      disagree, too little joint surface).
- [ ] **The phantoms went to 30 mm; the bound stops at 27-28 mm.** At
      30 mm no region of any phantom reported a number: the sacral fracture
      slid 30 mm up is left free to slide along itself (0.28-0.38 mm per mm;
      with the limit below in place, the wrong-start fit moves it past it),
      slid back the fit moves its unit more than 30 mm, the iliac wing slid
      30 mm laterally leaves no fracture surface, and the bilateral rims
      disagree. The furthest that reported one were the iliac wing slid
      25 mm (fracture displaced 27.69 mm) and the sacral fracture slid 25 mm
      back (symphysis 26.76 mm). So `PHANTOM_TRAVEL_MM` is fracture 28.0,
      symphysis 27.0, SI joint 28.0 mm, not the 30 mm the plan asked for: the
      bound says nothing past the displacements it was measured at, as in
      slice 1b. A region the fit moves further, or any region of a unit
      moved further, is `inf`; tested on the sacral fracture slid 35 mm.
      The limits differ by kind, so a unit moved 27-28 mm by a fracture is
      within the fracture's limit and past the symphysis's: the symphysis's
      bound there is `inf`, and the reason ("displaced further than the
      phantoms", naming the unit, how far and at which region) is now set
      where that bound is read (`_bound_by_displacement`). It was not: the
      symphysis read `inf` with no reason. `_check_residual_contract` now
      also checks that every `inf` in the Reduction is named in its notes
      with a reason. On the iliac wing slid 25 mm (hip moved 27.2 mm at the
      fracture) the symphysis now says so beside its unresisted motion.
- [x] **Round trip at every displacement** through `reduction.apply_moves`,
      from the wrong mirror start, the sacral fracture slid up and the iliac
      wing slid laterally, 5-30 mm: every region lands within what it
      reports, and each region's bound is the table's at its displacement.
      At 15 mm, for instance, the sacral fracture is displaced 14.34 mm,
      bound 14.9 mm, lands 2.12 mm; its symphysis bound 12.5 mm, lands
      4.48 mm; the iliac wing's fracture is displaced 19.11 mm, bound
      23.7 mm, lands 5.78 mm. At 30 mm both read `inf` everywhere. The
      reduced right hip overlaps the intact one 0.80-0.95 (Dice; sacral
      0.948, 0.801, 0.862, 0.854, 0.901, 0.940 at 5-30 mm) and 0.885-0.919
      (iliac): lower than the 0.9 slice 1b's round trip holds its two fits
      to, because from the wrong start the moved piece keeps part of the
      mirror's error (the sacral unit slid 10 mm ends 8.63 mm / 3.41 degrees
      off at its worst point). Printed, not asserted; slice 1b's round-trip
      test and its 0.9 are unchanged and pass.
- [x] **An impacted fracture is reduced by its rims and the mirror** (7d.6,
      plan test 6). The lateral fragment driven 4 mm into the sacrum, one
      solid label, the band found from the CT (read 3.83 mm) against the
      confirmed mirror, the split cut along it. Its rims are fitted along the
      fracture (sliding rows), and across it each rim point is held as far
      from its partner face as at the mirror start: the length lost to
      impaction is the mirror's. From the exact start the fit pulls the
      fragment's face 4.02 mm laterally (the true depth 4.0 mm) and the hip
      ends 0.94 mm / 0.39 degrees off at its worst point; the fracture lands
      0.45 mm and reports 11.8 mm. From the wrong start (7.64 mm /
      3.00 degrees) the hip ends 7.05 mm / 2.52 degrees off: what only the
      mirror pins keeps the mirror's error, as 7d.6 says it must; the
      fracture lands 5.57 mm and reports 11.8 mm, the symphysis 1.30 within
      11.9 mm. The fracture's notes and the Reduction's say it rests on the
      mirror, and it carries the mirror's floor, `MIRROR_FLOOR_MM["fracture"]`
      = 11.8 mm (the whole-hemipelvis column of the table under section 1:
      the table has no column for a sacral fracture; whether the SI joint's
      4.7 mm is the right floor there is the surgeon's ruling, not taken
      here).
- [x] **A hip whose pose rests on the mirror is a region over all its
      bone.** On that phantom a tilt of the hip is pinned only by the
      mirror's distance across the band (0.98 mm per mm without it), so
      `unit_hip_right_on_mirror` covers all the hip's bone at the mirror's
      floor for a whole hemipelvis, 11.8 mm: a screw far from the fracture
      and the joints is warned when its room is under 11.8 mm. Without it,
      the mirror's rows would read the hip as pinned and that screw as safe.
      Any other region whose two sides such a motion moves would carry its
      own kind's floor; none did on the phantoms.
- [x] **No mirror, no restored impaction.** Fitted as both sides injured
      (2.4), the impacted fracture reads `inf`, "IMPACTION NOT RESTORED",
      and the fit has no row across it that would hold the impaction as
      scanned.
- [x] **A 6 mm impaction is reduced, by rims and mirror.** It was not: the
      band grew down to half height through touching bone off its plane, and
      its continuation through the rind kept rind voxels level with the
      nearest band voxel however far that voxel was off the plane, so the
      zone ran 7.5 mm from the true band (12 mm against nearby bone, and
      30 mm on the 4 mm phantom against nearby bone), faces with it, and the
      split refused ("the cut plane does not separate the two faces"). Both
      are now held to the band's slab: no further from its fitted plane than
      half its thickness and a voxel (`fracture_surface._in_slab`; the plane
      and thickness refitted to the band grown within it, at most
      `IMPACTION_SLAB_REFITS` = 5 times, starting from the dense core's
      plane). Every impacted phantom's zone now lies within 1.5 mm of its
      band and its faces within 3.0 mm, right and left, against the mirror
      and against nearby bone; depths read 3.83 / 6.16 mm (mirror) and
      3.04 / 6.03 mm (nearby). The 6 mm phantom splits (34.9 cm3) and is
      fitted: from the exact start the fracture lands 3.47 mm within its
      11.8 mm (the mirror's floor), the symphysis 8.07 mm within 12.5 mm;
      from the wrong start 6.31 within 12.7 mm and 5.70 within 12.5 mm. On
      real anatomy a band that curves more than its slab is cut short where
      it leaves the slab: the rest is not part of this surface.
- How the impacted rims were made to work, each found on the phantom: paired
  across the band as they lie, a rim point's nearest partner was the one
  across the least of the face's unevenness (CT faces are two voxel layers
  deep in places), and the medial face, driven toward the sacral canal, has
  the canal's floor in its rim, which the lateral face has not: those paired
  with the partner's outline 6 mm off and the rims disagreed (p90 3.7-4.3 mm)
  from the exact start. Each rim point is now set to its face's local level
  and moved half the faces' distance at the mirror start, so rims pair beside
  each other; a sliding row needs both ends on cortex facing within
  60 degrees of the same way (`IMPACTED_SLIDE_COS`, chosen, not
  calibrated); and one distance across for the whole fracture tilted the
  fit 1.9 degrees (a band read thicker at one end), so each rim point keeps
  its own distance at the mirror start.
- Tests replaced (plan test 7), each because it pinned the single
  `PHANTOM_BOUND_MM` or the 8-9.5 mm travel: `_check_residual_contract`
  (bound == `PHANTOM_BOUND_MM[kind]` became bound == `phantom_bound_mm(kind,
  displacement)`, with the displacement at least the region's own travel
  and within `PHANTOM_TRAVEL_MM`, and a region that rests on the mirror at
  least its floor and saying so); `test_unilateral_recovery` and
  `test_bilateral_recovery` (the hip's worst point within
  `max(PHANTOM_BOUND_MM)` became within the largest bound at the fit's
  displacement: 6.5 mm for the unilateral fits, as before, and 6.72 mm for
  the bilateral one, displaced 5.18 mm); `test_displaced_further_than_the_
  phantoms_is_unconstrained` (10 mm against 8 mm became 35 mm against
  28 mm), and the stop-short case it described is a test of its own. Every
  other slice 1 and 1b test is unchanged and passes.

### On the four CLINIC cases

`measure_cases.py --workers 2` (102-136 s a case), against the surgeon's
reading (DECISIONS 7b). **None of the lateral sacral fractures he read is
found, on any case, by any route.** Each case now prints, per side of the
sacrum, what he read, what was found and whether a split was made:

| Case | Sacrum right | Sacrum left |
| --- | --- | --- |
| CLINIC_0012 | read: fracture; found nothing; no split | read: none; found nothing |
| CLINIC_0023 | read: fracture; found nothing; no split | read: none; found nothing |
| CLINIC_0025 | read: none; found nothing | read: fracture; found `sacrum_1` (`ct_lucent`, 58 mm2), transverse, no split |
| CLINIC_0060 | read: fracture; found `sacrum_2` (`gap`, 44 mm2), transverse, no split | read: fracture; found `sacrum_1` (`ct_impacted`, 104 mm2, 2.2 mm), transverse, no split |

- [ ] CLINIC_0012 (right injured): nothing from the CT in any bone; every
      dense candidate is removed as dense against one side only, the lucent
      ones as lucencies inside intact bone. Found: slice 1's right pubic
      fragment boundary (`gap`, 168 mm2). **That region now reports a
      number, 18.1 mm** (mismatch 1.2 mm; the bound read at 16.3 mm, the
      fragment's displacement at the symphysis, while the fracture itself
      moved 6.8 mm): before slice 1c it read `inf`, displaced beyond the
      9.5 mm the phantoms then reached. It is slice 1's mask boundary, not a
      surface seen in the scan, and both the hip and the fragment are still
      not pinned as wholes (`unit_*_unpinned`, `inf`), so every screw in
      either is still warned as unknown. SI joint and symphysis
      UNCONSTRAINED. The hip moves up to 21.7 mm, 36.2 mm from its mirror
      start.
- [ ] CLINIC_0023 (right): nothing in the sacrum. Three `ct_lucent`
      surfaces in the hips (the right pubic body, 262 mm2, where he read a
      fracture; the low right ilium, 156 mm2; the low left hip, 968 mm2, by
      position the left pubic region he read), each within one unit or on
      static bone: NOT REDUCED. Every region `inf`.
- [ ] CLINIC_0025 (left): the left sacral `ct_lucent` surface (lateral 0.70,
      posterior) is on the side he read, but its faces look front and back
      (80 degrees from left-right), so the split refuses it as not lateral
      and it reads NOT REDUCED. Three slots and two more `ct_lucent` surfaces
      in the pubic regions, NOT REDUCED; nothing at the right acetabulum.
      Every region `inf`.
- [ ] CLINIC_0060 (both): against its own nearby bone (both sides injured,
      and the result says so), the left `ct_impacted` band, on a side he
      read, is transverse (83 degrees from left-right), and so is the right
      44 mm2 slot (86 degrees): no split on either side, both NOT REDUCED.
      The impacted reduction of 7d.6 never runs on a real case: the only
      band found is on the bilateral case (no mirror to restore it) and is
      not split. Every region `inf`. Rerun after the band was held to its
      slab: everything on all four cases reads as before, except this
      band's area, 104 mm2 where it was 106 mm2.

So on real anatomy slice 1c changes one number: CLINIC_0012's pubic
fragment boundary reads 18.1 mm where it read `inf`, because the bound now
reaches the displacement the fit found there. Every SI joint, symphysis and
sacral region of every case, and every `unit_*` region, still reads
UNCONSTRAINED. That these cases come out this way was not used to set any
constant.

Not done in slice 1c:

- the lateral sacral fractures on the four cases are not found (above);
- the impaction no denser than its two layers of bone is not found at the
  200 HU margin (part A), and how dense a real impacted band is has not
  been measured;
- the fracture bound past about 10 mm is the split's error, about the
  displacement itself; nothing reports a number beyond 27-28 mm;
- the mirror floor for an impacted sacral fracture is the whole-hemipelvis
  11.8 mm; the surgeon has not ruled on whether the SI joint's 4.7 mm
  applies there;
- the CT route's other constants (`LUCENT_MIN_CONTRAST_HU`,
  `BREAK_MIN_VOXELS`, `IMPACTION_FLANK_MM`, `IMPACTION_FLANKED_SHARE`,
  `IMPACTION_MIRROR_REACH_MM`) and part B's `IMPACTED_SLIDE_COS` are chosen,
  not calibrated; the normals null test (`--normals`, labels only) was not
  rerun, since it does not exercise the CT route or the fit.

## Running it

From `corridor-finder/`, with the development venv:

    python -m pytest -q                      # the whole engine, including slices 1, 1b and 1c
    python -m pytest -q -s tests/python/test_congruence.py   # the congruence fit, printing its numbers
    python ../displacement-finder/tools/measure_cases.py --workers 2
    python ../displacement-finder/tools/measure_cases.py --normals 5 --workers 4
    python ../displacement-finder/tools/symphysis_gap.py --workers 4

The tools read the CTs and labels under `C:\Users\oom\CorridorFinderData`
read-only and print everything. Allow two to three minutes per CLINIC case
and a few minutes for the symphysis over all normals. The congruence fit
moves each unit's voxels to measure the reduced joints, a few GB per CLINIC
case; the CLINIC run above was made with 2 workers. A CLINIC CT is about
90 million voxels: keep to 4 workers, and do not run the tools alongside
the test suite (an earlier run did, and ran out of memory).
