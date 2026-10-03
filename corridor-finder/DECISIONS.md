# Design decisions

Clinical design decisions for Corridor Finder, made by the surgeon who owns the
project in a structured interview on 2026-09-19. They settle the open questions
found while getting the Slicer module to run on real CTs (see README "What still
blocks real planning"). Each was chosen from explicit alternatives; the
rejected options are noted where they matter for future changes.

Terms: r = screw radius; m = the screw's safety margin; clearance = distance from
the screw's surface to the outer surface of the segmented bone; **breach =
clearance < m** (unchanged, and still identical in `validate.py`,
`viewer/clearance.js` and `report.py`).

## 1. Screw geometry and the breach rule

| # | Decision | Rejected |
| --- | --- | --- |
| 1.1 | A screw's **entry is the point where its axis crosses the outer cortex**, where the guidewire starts. **Length is measured cortex to tip**, like a depth gauge. Previously the search moved the entry several mm into the bone (at least 6.9 mm in a test case), so lengths were short and that stretch was never checked. | Entry at the first fully safe point inside the bone. |
| 1.2 | The unavoidable crossing of the entry cortex is exempted **only for the entry cortex itself**. Near the entry, parts of the screw's (r + m) envelope that lie outside the entry cortex's tangent plane are ignored. Everything else must still be bone, so a side-wall breach next to the entry is still caught. | Leaving the whole first stretch unchecked; a fixed 5 mm stretch. |
| 1.3 | The exempt stretch is (r + m) / cos(angle between the screw axis and the cortex normal at entry), **capped at its 60 degree value, 2 x (r + m)**. | Letting it grow with the angle. |
| 1.4 | An entry steeper than **60 degrees** gets an amber **warning** ("entry too oblique") but can still be added. With the cap in 1.3, a screw that really skims the cortex also shows red for clearance. | Treating > 60 degrees as a breach; 45 or 70 degree limits. |
| 1.5 | **Transiliac-transsacral S1 and LC-2** may pass through the far cortex, exempted by the same plane rule, with its own obliquity check. **All other corridors keep the whole tip inside bone** with the full margin, and their targets are sampled in bone interior rather than on the surface. Stored per corridor in corridors.json. | Only transiliac exits; nothing exits. |
| 1.6 | Lengths come from the 5 mm catalogue. **Far-cortex corridors round up**, and the plan and report state the protrusion past the far cortex (0-5 mm); the far crossing is exempted only up to that protrusion. **Inside corridors round down.** | Rounding far-cortex screws down, or up only when protrusion <= 2 mm. |
| 1.7 | Default margin **2 mm for every corridor** (about the cortex plus TotalSegmentator's ~1 mm boundary error), adjustable per screw. | 3 mm for sacral corridors; 3 mm for all. |

### 1.2a Tolerance for the crossed cortex's shape (decided 2026-09-20)

Implementing 1.2 on real segmentations showed that the tangent plane alone
cannot work. A segmented cortex is neither flat nor smooth: TotalSegmentator
works at 1.5 mm and the pelvis curves. Within the screw's envelope, the
cortex being crossed dips below its own tangent plane at almost every entry.
On the sample CT, the plane alone flagged 91-100% of entries as a breach at
the entry itself, counting only entries into bone that is clear for 15 mm
beyond the entry zone.

**Decided: 1.5 mm**, after seeing what each value costs (the table below)
and a cut through a typical entry checked both ways. It matches the
resolution TotalSegmentator works at, so it covers the segmentation's own
roughness without excusing anything deeper
(`cortex.CORTEX_DEPTH_TOLERANCE_MM`, mirrored in `viewer/clearance.js`):

- Non-bone less than **1.5 mm** inside the tangent plane counts as part of
  the crossed cortex.
- Deeper non-bone within the envelope still counts, so a side wall next to
  the entry is still caught. For example, a 2 mm slot 3.5 mm from a 4.5 mm
  screw's axis is a breach in the tests.
- The exempt stretch grows to match: (r + m + 1.5 mm) / cos θ, capped at the
  60 degree value.
- The far cortex of "through" corridors uses the same rule.

Share of those entries still flagged at the entry, by tolerance (sample CT,
TotalSegmentator bones, 2 mm margin, axes 0, 30 and 50 degrees off the
surface normal; range over the three angles):

| Bone, screw | 0 mm | 0.9 mm | 1.5 mm | 2.0 mm | 2.5 mm |
| --- | --- | --- | --- | --- | --- |
| Hip bone, 7.3 mm | 96-98% | 38-51% | 15-22% | 6-9% | 4-6% |
| Hip bone, 6.5 mm | 91-99% | 37-62% | 18-25% | 6-19% | 4-7% |
| Sacrum, 7.3 mm | 96-100% | 54-73% | 27-35% | 18-23% | 12-18% |

The remaining flags at 1.5 mm have not been reviewed one by one. Some will
be real (an entry next to an edge or notch), some the segmentation's
roughness. That review belongs to step 3, on the full-pelvis CTs.

### How step 1 is implemented

- **Entry.** The axis from the entry handle toward the target handle is
  followed in 0.1 mm steps (nearest voxel), and the screw starts at the
  first bone voxel. If the entry handle is inside bone, the cortex is looked
  for up to 20 mm behind it. If none is found there, the screw's start is
  unchecked, so it is reported as a breach whatever its clearance, with a
  warning to move the handle. The cortex normal points toward the centroid
  of the bone within 4 mm of the crossing.
- **Gaps inside the bone are not a cortex.** A crossing counts as the
  outer (or far) cortex only if the axis meets no more of the corridor's
  bone within 20 mm beyond it. Otherwise it is a gap inside the bone: a
  joint wider than it is bridged, the sacral canal, a foramen. Such a gap
  is never exempted:
  - an entry there is reported as a breach whatever the clearance, since
    the screw's real path from the outer cortex is unchecked;
  - a far crossing there keeps the tip inside bone.
- **Length** comes from `screws.json` for the screw's diameter:
  - "inside" corridors: the longest length ending before the target handle.
    A suggested screw's target handle sits at its tip.
  - "through" corridors: the shortest length reaching past the far cortex.
    The far cortex is looked for near the target handle: up to 20 mm beyond
    it, or back from it. The tip is exempted at most 5 mm past the far
    cortex; anything beyond that is a breach.
- **Tip rule per corridor** (corridors.json `tip`): "through" for
  transiliac_transsacral_s1 and supra_acetabular (LC-2); "inside" for all
  others.
- **Warnings** show in amber:
  - entry handle more than 2 mm off the cortex;
  - entry or far-cortex crossing steeper than 60 degrees;
  - no catalogue length fits (the exact length is then used);
  - far cortex not found, or a gap (the tip is kept inside);
  - the axis does not enter bone;
  - entry cortex not found, or a gap. These two also make the screw a
    breach.

  Any of these except the first two keeps a screw from being suggested.
- **Suggestions.** The search offers only screws that validate exactly as
  the plan will validate them. Their lengths must also lie in the
  corridor's `length_range_mm`.
- **Viewer.** It repeats all of this in `viewer/clearance.js`, golden-tested
  against `validate.py` under Node, including the exemption's distance
  transform. A screw dragged beyond the region exported with it (at least
  about 15 mm) is shown as not checked, never as safe.

## 2. The sacroiliac joint

| # | Decision |
| --- | --- |
| 2.1 | A pre-reduction CT is **measured as it is**. A corridor that is not available before reduction (sacral or otherwise) is reported as not available, with the measured SI gap shown when that is the reason. |
| 2.2 | How wide an SI joint gap is bridged as bone is **patient-specific**. With one intact joint, the reference is **the intact joint's width**: the width covering 90% of its synovial (auricular) part at S1-S2. It is measured automatically, shown ("left SI joint 3.2 mm") and editable after checking with a ruler on the axial CT. With **both joints disrupted, 4 mm**. With no joint disrupted, each joint uses its own measured width. |
| 2.3 | Automatic references are **capped at 4 mm**. A wider measurement is shown with a warning ("measured 5.1 mm, capped at 4.0 mm") and can be raised deliberately. |
| 2.4 | The surgeon **declares the disrupted side(s)** (none / right / left / both). The tool measures both joints and pre-selects the wider as disrupted when they differ by more than 2 mm, and **no iliosacral or transiliac corridor is suggested until the choice is confirmed**. |

### How step 2 is implemented

- **Where it is measured** (`si_joint.py`), per side: at the **anterior
  bony margin** of the joint, the way it is read off a CT, at every level
  through the S1-S2 band. The surgeon asked for this after the first
  version measured the joint as a whole: that takes in the interosseous
  ligament's space behind the joint, which is naturally wide and irregular,
  and on four full-pelvis CTs it read 6.9 to 10.5 mm -- the ligament, not
  the joint. Measured at the anterior margin the same joints read 2.9 to
  7.2 mm, with medians of 2.4 to 3.8 mm.
- **What is measured**, at each level: the **gap** across the joint (the
  width of the joint space at its front end) and the **step** along it (how
  far the ilium's anterior cortex beside the joint sits in front of or
  behind the sacrum's, and how far above or below). A hemipelvis does not
  displace in one plane only, so the step is kept as a vector and reported
  in both directions. The up-or-down part cannot be read off a single level
  -- both points are taken at the same level -- so it comes from sliding
  one margin's profile along the other; where the joint margin runs too
  straight for that to mean anything, the tool says so instead of reporting
  zero.
- **What it costs is shown with it.** Next to each width, the panel and the
  report say how much of that joint the bridge actually covers, since the
  rest of the joint stays a gap and a screw crossing there reads as a
  breach.
- **The declaration gates the corridors.** Until the surgeon picks none,
  right, left or both, nothing is bridged and any corridor marked
  `crosses_si_joint` in corridors.json refuses to be suggested, saying why.
  When the two joints differ by more than 2 mm, the panel names the wider
  one as the one that looks disrupted; the surgeon still has to choose it.
- **Both widths are editable** afterwards, per side, and an edit rebuilds
  every distance field, so the suggestions and the live check follow it. A
  deliberately raised width is accepted (2.3); only the automatic reference
  is capped.
- **An edited segmentation re-measures** the joints and keeps the
  declaration.
- **corridors.json** no longer carries a fixed `sacral_gap_allowance_mm`;
  it says only which corridors cross the joint.
- **The plan and report record** what each joint measured, which side was
  declared disrupted, what was counted as bone and how much of the joint
  that covered.

## 8. Order of work, as it now stands

| # | Decision |
| --- | --- |
| 8.1 | **Reduce first, then find the corridor.** On a pre-reduction CT the fracture itself reads as a gap and narrows every corridor through it -- on the four public fracture CTs, 31 of 60 corridor/side/case combinations give a screw, and on the most displaced only 2 of 18. Virtual reduction (section 3) therefore comes **before** the pilot, not after it. |
| 8.2 | The pilot runs on **public CTs** for now; hospital cases are not available yet. |
| 8.3 | The surgeon will check the computed C-arm angles against a **real C-arm on his own cases**, and may use **Brainlab navigation**, which the plan will eventually have to export to. **Format (surgeon, 2026-10-03: Brainlab Elements and Spine & Trauma; screws as DICOM objects):** Brainlab's Surgery DICOM conformance statement (Rev 8.0, 2026) lists Segmentation Storage (DICOM SEG) for Elements and Spine & Trauma 3D navigation and does not list RT Structure Set, which only its RT Elements import performer reads; and SlicerRT's RTSTRUCT export references a duplicated CT with new UIDs, which Brainlab would not tie to the original images. So each passing screw is a segment (SNOMED "Screw", entry cortex to tip, its diameter) in one DICOM SEG referencing every slice of the original CT series, same patient, study and frame of reference (corridor_engine/dicom_seg.py). Screws that breach, are flagged, or were planned on a virtual reduction are left out and named. A CT not loaded from DICOM, or moved by a transform, is refused. Brainlab reads a binary SEG only when the CT's columns are a multiple of 8, so other CTs are refused. Trajectories as such cannot be imported (Brainlab's own are an undocumented private format): the surgeon re-creates the trajectory along the screw object. **Not yet confirmed on his Brainlab system:** a test import (through the Brainlab rep or biomed) must show the screws where they belong before any clinical use. |
| 8.4 | The displacement-measurement project (pre/post-operative CT, the widest gap at the sacrum, sacroiliac joint, symphysis, rami and acetabulum) **shares this engine**. Neither project keeps its own copy of a measurement the other already makes -- the sacroiliac gap and step above all -- and the two are kept in step. |

## 3. Post-reduction corridors

Intra-operatively the injury is reduced before fixation, so the corridor that is
drilled is the post-reduction one. Corridor Finder therefore also plans on
virtually reduced anatomy, as an option next to the pre-reduction CT.

| # | Decision | Rejected |
| --- | --- | --- |
| 3.1 | **Virtual reduction, auto-proposed and adjusted by the surgeon.** For a unilateral injury the displaced unit is registered onto the mirror image of the intact side. The surgeon inspects it in 3D and slices, fine-tunes it with a transform handle and accepts it. Corridors are then searched on the reduced bones. **Bilateral injuries: automatic or manual** (revised 2026-09-27, the surgeon's ruling in the displacement project, displacement-finder/DECISIONS.md 2.5, kept in step under 8.4): automatic fits the fractures back together with no outside reference -- each fragment moved until its fracture surface meets its parent's, or, at a pure SI dislocation, the two joint surfaces matched; manual is the transform handle above. | Manual only; mirroring the intact side's corridor; re-planning on an intra-op scan only. |
| 3.2 | The moving unit is **one hip bone plus the fragments travelling with it**. When the sacrum is fractured, the lateral sacral fragment is **split off automatically at the sacral fracture surface** and carried with the hip bone, and the surgeon **confirms the split** on the review sheet (revised 2026-09-27 to match displacement-finder/DECISIONS.md 7c.5, kept in step under 8.4; it was split by hand in Segment Editor). The proposal starts from the hip bone registered onto its mirrored twin and carries attached fragments along (3.6 then refines it). This covers SI dislocations and vertical sacral fractures; acetabular column fragments come later. | Whole hip bone only; any fragment independently. |
| 3.3 | The mirror plane is **fitted automatically to L5 and the central sacrum** (S1 body, canal) **when the sacrum is intact, and to L5 alone when it is fractured** (revised 2026-09-27 to match displacement-finder/DECISIONS.md 2.1-2.1a, the same reference, under 8.4). The tool fits both ways, pre-selects "sacrum fractured" when adding the sacrum makes the fit markedly worse, and the surgeon confirms before anything is used; unconfirmed, it refuses and says why. On the four CLINIC cases L5 alone fits better (self-symmetry median 1.2-1.5 mm vs 1.8-2.2 mm). The surgeon can adjust it with a plane handle before the reduction is proposed. | Whole sacrum; surgeon-placed only. |
| 3.4 | **One plan, each screw tagged with the anatomy it was planned on** (as scanned, or virtually reduced with the saved transform). Report and viewer carry a banner: "planned on virtually reduced anatomy: valid only after this reduction". DRRs are rendered from the reduced CT, skin entry on the moved side is marked approximate, and each screw's pre-reduction status is shown alongside. | Separate plans; storing both frames per screw. |
| 3.5 | Each proposal shows the **mean surface mismatch** between the reduced hip and the mirrored intact hip, and the post-reduction SI width. **Above 2 mm mismatch it warns** "proposal unreliable (fractured or asymmetric hip?)" before it can be accepted. | Blocking above 2 mm; numbers only. |
| 3.6 | **How the injured side is put back (surgeon, 2026-09-27).** A mirror alone is not accurate enough: on 40 normal CTPelvic1K pelves, a hemipelvis fitted onto its mirrored twin is off by a median ~5 mm at the SI joint and ~10 mm at the symphysis (worst 10%: ~9 and ~20 mm), and measuring the hip relative to the sacrum shows this is real left-right asymmetry, not the plane (displacement session's finding). So the mirror gives only the **starting position**; the reduction is then fitted by **congruence of the fracture surfaces and the SI joint surfaces** (the "jigsaw" of 3.1), and reports its **remaining error per region** (SI joint, symphysis, each fracture). Where that error is larger than a screw's spare clearance (clearance minus margin) in the same region, the screw is **still shown, with an amber warning** that its fit depends on the reduction's accuracy; the surgeon decides. This replaces 3.5's single mean-mismatch figure as the reliability measure. *Corridor side implemented* (corridor_engine/reduction.py, 2026-09-27): given each moving unit's rigid transform, the tool moves the bones and the CT, re-measures landmarks, joints and views, plans on the reduced anatomy, tags each screw with its anatomy, checks it there (and, for 3.4, on the bones as scanned), and warns where the reduction's error in a region is larger than the screw's spare clearance within 10 mm of that region's surface. The reduction itself (mirror start, congruence fit, per-region error and surface) comes from the displacement engine and is not built yet, and there is no panel control to apply one. **A reduction is used only once the surgeon has accepted that case** on the before/after sheet (3.1; displacement-finder 7c.8): the tool refuses one without a recorded acceptance, and the plan and report say who accepted it. | Mirror with the floor stated; atlas from the intact side; no reduction. Refusing the screw; numbers without a warning. |

## 4. Validation on real anatomy

| # | Decision |
| --- | --- |
| 4.1 | **Public full-pelvis CTs first** (an openly licensed dataset; exact files, source and size to be approved before any download), **then de-identified cases from the surgeon's hospital**. CTs stay on the workstation; nothing patient-derived is committed. |
| 4.2 | **Pilot on 5 cases, then 20 blinded cases** (10 without and 10 with a unilateral posterior ring injury), which the surgeon plans the usual way before seeing the tool's suggestions. **Pass:** left/right correct 20/20; no suggested screw the surgeon calls a breach; fits / does-not-fit agrees in at least 90% of corridors; suggested diameter within one catalogue size. |

## 5. Order of work

Each step is committed separately, verified inside Slicer and reflected in the
README:

1. Screw rules (section 1) in `validate.py`, `viewer/clearance.js` and
   `report.py` together, golden-tested against each other, and in the search.
2. Per-case SI reference width (section 2).
3. Review of the corridor anchors, textbook directions and DRR view angles in
   corridors.json with the surgeon, on public full-pelvis CTs.
4. 5-case pilot.
5. Virtual reduction (section 3).
6. 20-case blinded validation.

## 6. Aiming guidance (added on the surgeon's request, 2026-09-20)

Asked for after step 1: the tool should say where the entry is and how to
aim, not only that a screw fits. The conventions below were chosen while
implementing it and are open to correction.

| # | Choice | Note |
| --- | --- | --- |
| 6.1 | A direction is given as **how far it runs cephalad or caudad, then how far it swings anterior or posterior of straight medial** (or of straight lateral, whichever it is nearer), measured for the screw's own side. Both frames are reported: the anterior pelvic plane, and the scan's own axes as the patient lay on the table. | Midline screws read "toward the patient's left/right" instead of medial. |
| 6.2 | The **C-arm view looking straight down the screw** is given as the tilt and roll of the existing DRR views (so inlet/outlet and obliquity read the same way), with a sentence, and rendered as a simulated image in which the screw is a dot. | It is a starting position: the DRR is a parallel projection, with no magnification or source distance. |
| 6.3 | The **safe entry area** is the set of entries the screw can be **slid sideways to, keeping its direction**, and still pass the same check the plan applies. The tip moves with it and must stay safe too. Reported as the radius of the safe circle around the planned entry, the room in each of four named directions, a patch of points on the bone in Slicer, and a green area on the view down the screw. | Measured on a 1 mm grid out to 10 mm, so the numbers are conservative by about 1 mm. It does not cover pivoting the screw about its tip, which is a different question. |

## 7. The corridors themselves

From the surgeon, on seeing the first anchors drawn on full-pelvis CTs
(step 3). These are what corridors.json is set from.

| # | Decision |
| --- | --- |
| 7.1 | An **anterior column screw** (either direction) has its pubic end at least **10 mm on the symphysis side of the fracture**: a screw put in to hold a fracture starts before it, not past it. The surgeon marks the fracture; with nothing marked the rule does not apply. |
| 7.2 | Its tip **does not have to reach the lateral cortex of the ilium**: stopping above the acetabular roof is a screw. The longest trajectory is still reported when one exists, and so are the alternatives. |
| 7.3a | The **antegrade** route starts **about 15 mm lateral to the pelvic brim**, in the proximal part of the posterior column triangle, and its tip stops in the ischium or anywhere up to the ischial spine, as the surgeon chooses: the target region covers that whole run and the length is offered as options. The triangle is bounded medially by the quadrilateral surface, laterally by the retro-acetabular surface and below by the supero-posterior acetabular surface (Sikarinkul E, Puangnam P, Mayurasakaorn C, Phiphobmongkol V, Bavonratanavech S. *Posterior column triangle fluoroscopic view for posterior column screw placement in acetabular surgery.* Bangkok Med J 2025;21(2):116-122, the surgeon's reference). Entering beside the iliopectineal eminence instead runs along the quadrilateral surface, which takes only a 3.5-4.5 mm screw and only at a margin of 0.5-1.5 mm (measured on four hemipelves). |
| 7.3d | The antegrade screw is aimed **mostly square to the fracture** (the surgeon, 2026-09-27: "mostly aim for perpendicularity with the fracture site"). *Implemented* (corridors.json `square_to_fracture`, 2026-10-03): with 3 or more fracture marks within 40 mm of the corridor, a plane is fitted to them (marks elsewhere, such as on the ramus, are ignored), a second search aims within 20 degrees of its normal, and among the safe screws of the widest diameter that cross the fracture the one most nearly square to it comes first; every suggestion, the panel and the report say how many degrees off square it is and whether it crosses the fracture. Squareness only orders screws that already pass the breach rule. On CLINIC_0025 with a synthetic fracture 35 degrees off the widest screw, it found one 30 degrees off on the left and nothing squarer on the right: the column's shape limits it. |
| 7.3b | The **butt screw** enters **directly at the ischial tuberosity, a little medial**, to keep away from the sciatic nerve. |
| 7.3c | A screw may **touch the acetabular articular surface but never penetrate it**. The tool's own margin (2 mm from any cortex, the joint surface included) is stricter than this, so a corridor it refuses only for the acetabular margin may still be one the surgeon would use. |
| 7.7 | **No fixed fluoroscopic angles.** Every view is computed from the patient's own bones (corridor_engine/views.py): the AP square to his anterior pelvic plane, the inlet perpendicular to his pelvic brim, the outlet square to the front of his sacrum, the iliac oblique square to his own iliac wing, the lateral sacral along the line between his sacroiliac joints, and the combined views built from those. The **obturator oblique** is the roll about the patient's own upright axis, within 30 degrees of the classic 45, at which most of that side's obturator foramen shows: the foramen is the hole in that hip bone's own projection, less whatever other bone in the CT lies across it (2026-10-03; on the four CLINIC pelves it came out 1-11 degrees from the classic view on six sides. Projecting the hip bone alone put the femoral shaft across the foramen on CLINIC_0023, and letting the tilt vary drifted to about 26 degrees of outlet, an outlet-obturator rather than a Judet view, so neither is used). Where no foramen-sized opening shows, or the best roll is at the edge of the search (both sides of CLINIC_0025), the classic 45 degrees about his own axis is used and the view says so. Only Sikarinkul's 10/25 degrees are still numbers rather than definitions. Each view is reported with how far it is from the textbook angle. The **anterior column** is read on the **outlet-obturator oblique and the inlet** only. |
| 7.6 | **Fluoroscopic views per route**, from the literature, to be set on each patient's own anatomy rather than by fixed angles: posterior column, **the posterior column triangle view** (obturator oblique 10 degrees with inlet 25 degrees, Sikarinkul et al.) with iliac oblique and AP or cross-table lateral to confirm; anterior column, obturator oblique first (most accurate for the joint), then iliac oblique/outlet and inlet; iliosacral and transsacral, the **true lateral of the sacrum first** for the iliac cortical density, then inlet (S1 anterior cortex over S2) and outlet (symphysis at the S2 foramen, both foramina clear). |
| 7.3 | There are **two posterior column routes**, not one: **antegrade** from the pelvic brim or iliac crest down the posterior column and across the fracture, and **retrograde** from the ischial tuberosity back up to the brim (the "butt screw"). The old single corridor aimed at the PSIS, which puts the greater sciatic notch in the way of every axis. |
| 7.4 | A **transiliac-transsacral screw** is planned from the side the surgeon chooses, entering the **lateral ilium** and leaving the opposite one. Its safety is read first from the **lateral view (the iliac cortical density) to find the corridor**, then from **inlet and outlet** views; it must not breach the anterior sacral cortex, the sacral canal or a nerve foramen, and it takes **all six cortices** (ipsilateral ilium, sacrum, contralateral ilium). |
| 7.5 | The screws available are **130-150 mm in normal use and none longer than 180 mm**; most Thai patients do not need more. A corridor that needs a longer screw is reported as not available, with its measured length. The diameters the surgeon uses in practice are **6.5 and 7.3 mm**; those are what is suggested, and the thinner ones are only used to say how narrow a corridor is. |
| 7.10 | **Screw length is chosen, not only found.** Screws over **130 mm cost significantly more**, so when the widest corridor needs a longer one, the best corridor within 130 mm is offered beside it; and the surgeon can ask for a trajectory that takes a particular length. |
| 7.8 | A **dysmorphic sacrum has no S1 transsacral corridor**, and the answer there is **S2, or S3**, not a narrower S1 screw. The tool has to recognise dysmorphism and say which level to use. Its reading of the corridor is to be taken from the **iliac cortical density** (the alar slope) on the lateral, as in theatre. |
| 7.9 | A screw may **touch the acetabular articular surface but not penetrate it**, so the margin there is **0 mm**, while the **sacral canal and the nerve foramina keep the full 2 mm**, as does every other cortex. The margin is therefore per structure, not one number for the whole screw. *Implemented* (corridor_engine/structures.py): the breach rule stays the one rule -- clearance below the margin -- in validate.py, the viewer and the report; what changes is the field it reads, E = min(distance to any surface but the hip joint, distance to the joint surface + margin), inside bone only. The joint surface is where the hip bone and its femoral head face each other across the joint space, so it needs a femur label: TotalSegmentator gives one, the public CTPelvic1K labels do not, and without it the full margin applies everywhere. |
| 7.11 | Beside a screw that runs under the acetabulum, the tool states its **distance to the articular surface** (0 = touching; below 0 is never allowed), not the bone left under it. (Surgeon, 2026-09-27.) |
| 7.12 | An **LC-2 / supra-acetabular screw reaches the far cortex if possible**. When it cannot within the chosen length, it must at least **pass through the fracture**: a **partially threaded screw with its whole thread (16 or 32 mm) beyond the fracture line**, a **fully threaded screw with at least 32 mm beyond it** (surgeon's choice after the literature: no study sets a minimum purchase past a pelvic fracture; pullout rises with the length of thread engaged -- Chapman 1996, Thompson 1997, Kraemer/Tile 1994, Zheng 2009 -- so 32 mm matches the long-thread rule; extrapolated, not validated). **With no fracture marked, the far cortex is required**, and the tool says that marking the fracture would allow a shorter screw. (Surgeon, 2026-09-27.) *Implemented* (corridor_engine/fracture.py; corridors.json `short_tip`): the surgeon marks 3 or more points along the fracture and a plane is fitted through them (it must span at least 3 mm RMS across, and a screw crosses the fracture only within 20 mm of a mark). When no LC-2 reaching the far cortex fits within 130 mm or the length asked for, the longest screw on the corridors found that stops in bone with 32 mm past the plane is offered, checked with the inside-bone tip rule; the plan records that tip rule, so Slicer, the viewer and the report check it the same way, and the screw is flagged if the fracture mark later moves or is cleared. The tool does not know the thread type, so it asks 32 mm for every screw, which also covers the 16 mm-thread one. Only a corridor with `short_tip` can take the inside-bone rule. |
| 7.13 | The narrow corridor **just posterolateral to the iliopectineal eminence** (3.5-4.5 mm at 0.5-1.5 mm margin, 7.3a) is **not offered**: only stocked screws at the full margin are suggested. (Surgeon, 2026-09-27.) |

Still to settle with the surgeon (step 3 continues): exactly where each
posterior column route starts and ends, how close either may come to the
acetabular articular surface, which fluoroscopic views belong to each, and
whether the fracture level decides between the two routes.
