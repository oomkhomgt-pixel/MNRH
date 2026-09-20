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

- **What is measured** (`si_joint.py`), per side: the space the hip and the
  sacrum face each other across, in the band between the S1 and S2 body
  centres. For each empty voxel between them, the distance from one bone to
  the other through it, which is the same quantity the bridging uses. Space
  past the joint's rims does not have the two bones on opposite sides of
  it, and space wider than 8 mm is the interosseous ligament's rather than
  the joint's; neither counts. The reported width is the one covering 90%
  of the rest.
- **What it costs is shown with it.** Next to each width, the panel and the
  report say how much of that joint the bridge actually covers, since the
  rest of the joint stays a gap and a screw crossing there reads as a
  breach. On the sample CT (no injury) the joints measured 7.0 mm on the
  right and 7.1 mm on the left, so both were capped to 4 mm (bridging 4 mm
  covers 46% and 47% of them), which is the case 2.3 was written for.
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

## 3. Post-reduction corridors

Intra-operatively the injury is reduced before fixation, so the corridor that is
drilled is the post-reduction one. Corridor Finder therefore also plans on
virtually reduced anatomy, as an option next to the pre-reduction CT.

| # | Decision | Rejected |
| --- | --- | --- |
| 3.1 | **Virtual reduction, auto-proposed and adjusted by the surgeon.** For a unilateral injury the displaced unit is registered onto the mirror image of the intact side. The surgeon inspects it in 3D and slices, fine-tunes it with a transform handle and accepts it. Corridors are then searched on the reduced bones. Bilateral injuries: manual reduction only. | Manual only; mirroring the intact side's corridor; re-planning on an intra-op scan only. |
| 3.2 | The moving unit is **one hip bone plus fragments marked as travelling with it** (e.g. a lateral sacral fragment split off in Segment Editor). The proposal registers the hip bone onto its mirrored twin and carries attached fragments along. This covers SI dislocations and vertical sacral fractures; acetabular column fragments come later. | Whole hip bone only; any fragment independently. |
| 3.3 | The mirror plane is **fitted automatically to L5 and the central sacrum** (S1 body, canal), which are not displaced by pelvic ring injuries. The surgeon can adjust it with a plane handle before the reduction is proposed. | Whole sacrum; surgeon-placed only. |
| 3.4 | **One plan, each screw tagged with the anatomy it was planned on** (as scanned, or virtually reduced with the saved transform). Report and viewer carry a banner: "planned on virtually reduced anatomy: valid only after this reduction". DRRs are rendered from the reduced CT, skin entry on the moved side is marked approximate, and each screw's pre-reduction status is shown alongside. | Separate plans; storing both frames per screw. |
| 3.5 | Each proposal shows the **mean surface mismatch** between the reduced hip and the mirrored intact hip, and the post-reduction SI width. **Above 2 mm mismatch it warns** "proposal unreliable (fractured or asymmetric hip?)" before it can be accepted. | Blocking above 2 mm; numbers only. |

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
