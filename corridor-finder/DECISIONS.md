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

## 2. The sacroiliac joint

| # | Decision |
| --- | --- |
| 2.1 | A pre-reduction CT is **measured as it is**. A corridor that is not available before reduction (sacral or otherwise) is reported as not available, with the measured SI gap shown when that is the reason. |
| 2.2 | How wide an SI joint gap is bridged as bone is **patient-specific**. With one intact joint, the reference is **the intact joint's width**: the width covering 90% of its synovial (auricular) part at S1-S2. It is measured automatically, shown ("left SI joint 3.2 mm") and editable after checking with a ruler on the axial CT. With **both joints disrupted, 4 mm**. With no joint disrupted, each joint uses its own measured width. |
| 2.3 | Automatic references are **capped at 4 mm**. A wider measurement is shown with a warning ("measured 5.1 mm, capped at 4.0 mm") and can be raised deliberately. |
| 2.4 | The surgeon **declares the disrupted side(s)** (none / right / left / both). The tool measures both joints and pre-selects the wider as disrupted when they differ by more than 2 mm, and **no iliosacral or transiliac corridor is suggested until the choice is confirmed**. |

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
