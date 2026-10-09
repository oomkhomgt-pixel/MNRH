# Design decisions

Clinical design decisions for Displacement Finder, made by the surgeon who owns
the project on 2026-09-20, in the same form as `corridor-finder/DECISIONS.md`.
Each was chosen from explicit alternatives; the rejected options are kept where
they matter for future changes.

## 0. What this measures and why

In the surgeon's words:

> "Measuring pre/post op CT displacement to be used instead of human-measured.
> We'll use widest gap in each point, posterior ring: sacrum, SI joint,
> Anterior ring: pubic symphysis, ramus, acetabulum. For definition of widest
> gap, it's the largest displacement of fragment measure from CT slices and
> displacement it needs to move back to anatomical position. For both pre &
> post operative of pelvic/acetabulum fracture. All the measure before are
> quite biased due to highly three-dimensional structure of pelvis. This will
> be used to reduced biased to collect radiographic outcome and will also be
> aiding in reduction maneuver from pre-op CT."

Two uses, one measurement: score the radiographic outcome after surgery, and
tell the surgeon which way and how far a fragment has to move before it.

## 1. The number reported at each point

| # | Decision | Rejected |
| --- | --- | --- |
| 1.1 | At each point the tool reports **three things**: the **gap** across the fracture, the **step** along it as a vector, and the **rigid transform** (translation and rotation) that carries the fragment back to anatomical position. The gap/step pair is what is read off a CT slice; the transform is the reduction manoeuvre. They come from one computation. | A single scalar with no direction (no use for the manoeuvre); gap and step with no rotation (under-reports a rotated acetabular fragment). |
| 1.2 | The **headline scalar** — the surgeon's "widest gap" — is the **largest distance any point on that fracture surface has to travel** to reach anatomical position: the maximum over the surface of the distance from a point to where the transform puts it. One number per point per scan, continuous, for the outcome table. | The gap alone (a sheared sacrum reads 2 mm with the hemipelvis 15 mm high); the fragment centroid's travel (hides rotation entirely). |
| 1.3 | A displacement is **three-plane**. Every vector is reported in the patient's own anterior pelvic plane frame (`corridor_engine/app_frame.py`) as well as in scanner axes, never as a single-plane number. | Reporting only the axial-slice component, which is the bias this project exists to remove. |
| 1.4 | A displacement **smaller than this patient's noise floor** (measured 1.3–2.8 mm on the CLINIC cases) is still **reported as a number, and flagged** ("1.1 mm, below this case's floor of 2.2 mm"). Decided 2026-09-27. The variable stays continuous for correlating with function (7.2); the analysis decides what to do with flagged rows. | An "undisplaced" category (a censored variable that complicates regression); zero (0.3 mm and 2.1 mm become the same). |
| 1.5 | **Revised 2026-09-27: the outcome number is the local widest gap and step, not the transform home.** At each named point, the outcome is the **widest gap and the step measured directly across the fracture surface** (fragment against its neighbour), and **across the symphysis** (one pubic body against the other). This is the surgeon's "widest gap in each point", in 3D, with **no reference**. An anatomically reduced fracture reads zero by definition, which is the zero point of 6.3. **The transform home against the mirror (1.1, 1.2) stays as the pre-operative reduction-manoeuvre guide**, always printed with its measured normal-anatomy floor (below). **SI joint:** both are reported, `si_joint.py`'s local gap and step and the mirror transform, each with the range it reads on intact joints, since neither reads zero there (7b). | The mirror transform as the outcome at every point, with its floor printed (displacements under about 5-10 mm could not be told from normal asymmetry); building an atlas first (research-level, not known to beat the floor). |

**1.2 confirmed by the surgeon, 2026-09-27:** the maximum is taken over *the
fracture surface at that named point*, not over the whole fragment. Under a
pure rotation the ischial tuberosity travels further than the fracture line
does, and taking the whole fragment would report that instead of the gap he
asked for. (Rejected: the whole fragment; both reported separately.) Since
1.5, this maximum is the pre-operative manoeuvre guide, not the outcome.

### Why 1.5 was needed: the mirror's floor on normal anatomy (measured 2026-09-27)

Slice 1 measured, and the result was reproduced independently, how far a
hemipelvis "travels home" onto its mirrored twin on **normal, undisplaced
pelvises**, where the right answer is zero. 40 pelvises (CTPelvic1K
ABDOMEN, MSD Task 10, KITS19 and CERVIX, 10 each), 80 hemipelvises. Maximum
travel in mm, median / 90th percentile:

| Fit | Whole hemipelvis | At the SI joint | At the symphysis |
| --- | --- | --- | --- |
| Whole hemipelvis onto its mirror (slice 1's main body) | 13.5 / 31.2 | 6.3 / 14.6 | 11.5 / 30.1 |
| The same, relative to the sacrum (cancels any rigid plane error exactly) | 11.8 / 19.5 | 4.7 / 9.3 | 9.6 / 20.2 |
| Only the bone within 30 mm of the joint, relative to the sacrum | | 4.4 / 8.5 | 6.7 / 19.3 |

Measuring relative to the sacrum removes any error of the plane, so most of
what remains is **genuine side-to-side asymmetry of normal hemipelves**. A
better plane cannot remove it. It is the floor of 6.3, measured rather than
claimed, and it is the same size as the displacements that matter. Hence
1.5: the outcome is measured locally, across each break, where anatomical
reduction reads zero by definition, and the transform home is a manoeuvre
guide printed with this floor. (Slice 1 first attributed all of it to the
mirror plane. Its evidence, that the right and left numbers are
near-identical, does not show that: fitting the right onto the mirrored left
and the left onto the mirrored right are mirror images of one problem, so
they always agree.)

This is also why Corridor Finder's virtual reduction cannot yet apply the
transform home to a real CT (`fragments.reduce_labels` refuses): on a
typical patient it would land the hemipelvis about 5 mm off at the SI joint
and 7-10 mm off at the symphysis, and 10-20 mm off on the worst tenth.

## 2. "Anatomical position" — the reference

| # | Decision | Rejected |
| --- | --- | --- |
| 2.1 | **The mirrored intact hemipelvis**, mirrored across a plane fitted to what the injury has not displaced: **L5 and the central sacrum** (S1 body, canal) when the sacrum is intact, and **L5 alone when the sacrum is fractured**. Revised 2026-09-27, see below. With an intact sacrum this is the plane already specified for Corridor Finder's virtual reduction (corridor-finder DECISIONS 3.3), so the two projects agree on what "reduced" means. | A surgeon-placed target, which re-introduces the human bias the project removes. L5 alone for every case (one vertebra is a small base for a whole-pelvis plane, and an L5 transverse process fracture would corrupt it). L5 and central sacrum for every case (see below). |
| 2.1a | **Whether the sacrum is fractured is measured, pre-selected and confirmed**, the same pattern as the SI joint (corridor-finder DECISIONS 2.4): the tool fits the plane both ways, pre-selects "sacrum fractured" when adding the central sacrum makes the fit markedly worse than L5 alone, and **the surgeon confirms** before any displacement is reported. Which reference was used is recorded on every row (2.3). | Deciding automatically with no confirmation; asking the surgeon with no measurement to go on. |
| 2.2 | **With both sides injured, a statistical pelvis atlas** fitted to whatever is not displaced (L5, central sacrum, any intact ring segment). Every case then has a reference, bilateral included. | An atlas for every case: a normal pelvis varies enough that the atlas adds its own error to cases where a perfectly good mirror exists. |
| 2.3 | Which reference was used, and how well it fits, is **reported with every number**. A mirror fit and an atlas fit do not have the same error, and a paper has to say which produced each row. | Reporting the displacement alone. |
| 2.4 | **Until the atlas exists, a bilateral case reports gap and step only** — the fragment-relative numbers, which need no reference — and refuses the transform home with the reason. The case stays in the study. Decided 2026-09-27. | Excluding bilateral cases (usually the worst injuries, so a biased study); building the atlas before the per-point measurements. |
| 2.5 | Bilateral cases still get a **reduction function**, automatic or manual. **Automatic = fit the fractures back together**: each fragment is moved until its fracture surface meets its parent's, closing the gap and step with no outside reference (the "jigsaw" repositioning of Zeng et al., Med Image Anal 2024). At a pure SI dislocation, where there is no fracture surface, the two joint surfaces are matched instead. **Manual** = the surgeon places it, in Slicer (3.3). Decided 2026-09-27. This changes corridor-finder DECISIONS 3.1, which says bilateral injuries get manual reduction only. | The atlas as the automatic route (not built); manual only. |

### Why 2.1 changed (measured 2026-09-27)

Fitting the mirror plane on the four CLINIC cases, L5 alone was a better
symmetry reference than L5 plus the central sacrum **on every case**
(self-symmetry residual, median / 90th percentile, mm):

| Case | L5 alone | L5 + central sacrum |
| --- | --- | --- |
| CLINIC_0012 | 1.24 / 2.02 | 1.90 / 3.33 |
| CLINIC_0023 | 1.49 / 2.55 | 2.22 / 4.56 |
| CLINIC_0025 | 1.37 / 2.15 | 1.97 / 3.76 |
| CLINIC_0060 | 1.27 / 2.17 | 1.81 / 3.73 |

These are pelvic fracture cases, and the likely reason is that where the
sacrum is fractured it is part of the injury, so it cannot be asked to say
what "unfractured" is. Every plane fitted, both ways, came out square to the
patient: 1.9-7.4 degrees off the line joining the two hip centroids.

Not yet known: whether the four CLINIC cases actually have sacral fractures.
The measured difference is present on all four, so either they all do, or
adding the sacrum costs some fit on any pelvis and the pre-selection
threshold in 2.1a has to allow for that. The surgeon's reading of the four
cases settles which. He then read them from case-reading sheets: all four
have a sacral fracture (7b).

### Calibrating 2.1a on normal pelvises (2026-09-27)

With his approval (8.1), the label files of CTPelvic1K's four normal-anatomy
subsets were downloaded (ABDOMEN, MSD Task 10, KITS19, CERVIX: 275 labels,
19.2 MB; labels only) and the plane fitted both ways on each. The **penalty**
is how much adding the central sacrum worsens the fit's mean closest-point
cost, in mm:

| Group | n | Penalty, 5th / median / 95th percentile |
| --- | --- | --- |
| Normal: ABDOMEN | 35 | 0.44 / 0.62 / 0.87 |
| Normal: MSD Task 10 | 155 | 0.35 / 0.59 / 0.79 |
| Normal: KITS19 | 43 | 0.42 / 0.52 / 0.70 |
| Normal: CERVIX | 41 | 0.49 / 0.63 / 0.79 |
| Sacral fracture: the four CLINIC cases | 4 | 0.73, 0.82, 0.87, 0.99 |

- **Adding the sacrum costs fit on a normal pelvis too** (about 0.6 mm), so
  the penalty only partly signals a fracture. The fractures sit above most
  normals but not all: **a threshold of 0.70 mm pre-selects all four
  fractures and 39 of 274 normal pelvises (14%)**. That threshold is
  proposed, not settled. With only four fractures behind it, it is a starting
  point, and it works as a pre-selection only because the surgeon confirms
  every case (2.1a). The normals come from other scanners and populations
  than the fractures, which may account for some of the separation.
- **The plane can fail badly with L5 alone.** 3 of 278 L5-alone fits came out
  71-77 degrees off the patient's inter-hip axis. **L5 plus central sacrum:
  0 of 278.** The failed fits do not look healthy: their self-symmetry (90th
  percentile 4.8-6.4 mm) is far outside that of good L5 fits (1.6-3.0 mm,
  5th-95th percentile). The **15-degree tilt gate** refuses all three. When
  it refuses the pre-selected reference, the tool pre-selects the other one
  with a warning, and the surgeon confirms as usual.
- **Hip ids are not consistent across CTPelvic1K's subsets.** In ABDOMEN
  (35 of 35) and most of CERVIX (36 of 41), id 2 is on the patient's right
  according to the file's own affine, the opposite of CLINIC. Either those
  labels are swapped or the mapped-back images are mirrored, and labels
  alone cannot tell which. Sides are therefore always taken from geometry,
  file by file, never from the id.

## 3. Fragments

| # | Decision | Rejected |
| --- | --- | --- |
| 3.1 | Fragments are found **automatically and corrected by the surgeon**: shown in 3D, colour-coded, and he may merge, split or reassign any of them before anything is measured. | Marking every fragment by hand (minutes per case, which caps the size of the study); never identifying fragments (then no manoeuvre can be reported). |
| 3.2 | **Smallest fragment:** **0.5 cm³ at the acetabular articular surface**, where a small step matters, and **2 cm³ elsewhere in the ring**, where a small piece does not change the reduction. A smaller piece is carried with its neighbour and not reported on its own. Named constants, to be revised once seen on real cases. Decided 2026-09-27. | 1 cm³, 0.5 cm³ or 2 cm³ everywhere. |
| 3.3 | **Review happens on a batch sheet now, in Slicer later.** Each case runs headless and produces one sheet: the bones in 3D with fragments colour-coded, the mirrored side overlaid, the pre-selections (2.1a) and the numbers. The surgeon marks accept or correct in a table; corrections re-run. The Slicer step (editing a fragment boundary by hand, manual reduction) comes with Corridor Finder's virtual reduction. Decided 2026-09-27. | Slicer only (about a minute per case to start and load, over a whole study); the sheet only (a fragment boundary could never be corrected by hand). |

### What 3.1 cannot be built on (measured 2026-09-20)

**Connected components does not separate fragments.** On all four CTPelvic1K
CLINIC fracture cases, each expert bone label comes out as one body plus dust:
the sacrum 164–275 cm³ in a single component, each hip 241–416 cm³ in a single
component, and every remaining component 0.0–0.4 cm³. Only CLINIC_0023's left
hip has a genuine second body (19.3 cm³). A fracture whose fragments still
touch, or whose line is thinner than a voxel, stays one component — and the
CTPelvic1K annotators labelled *bones*, not fragments.

So fragment identification has to come from somewhere else. The reference in
section 2 is the natural source: register the mirrored intact hemipelvis onto
the injured one, and the parts that will not fit under one rigid transform
are, by definition, separate fragments. That yields the fragments and their
transforms (1.1) from one computation. How it is implemented is an engineering
decision and belongs in the project plan, not here.

## 4. The five points

| # | Point | What is measured |
| --- | --- | --- |
| 4.1 | **Sacrum** | The fracture through the ala or body: gap and step across the fracture plane, plus the transform of the lateral fragment. |
| 4.2 | **Sacroiliac joint** | **Revised 2026-09-27** (see 7b: intact joints read a 2.9-9.7 mm step). The **outcome number** is measured **against the mirrored side**: how far the hemipelvis sits from its mirrored twin at the joint, the same transform home as the other four points (1.1, 1.2), so an intact joint reads about zero by construction. `corridor_engine/si_joint.py`'s anterior gap and step are **still reported, unchanged**, as the numbers read off a slice; the engine is not modified and Corridor Finder's use of it is untouched (7a.1). Bilateral: gap and step only, with the intact-joint range from 7b given for context (2.4). Rejected: injured minus intact side (assumes symmetric joints; CLINIC_0012's two intact sides differ by 4.7 mm); redefining the step in the shared engine. |
| 4.3 | **Pubic symphysis** | Gap and step across the symphyseal surfaces, plus the transform. Diastasis is the gap; the step is the anteroposterior and vertical offset that a plain film under-reads. |
| 4.4 | **Pubic rami** | Superior and inferior ramus fractures: gap and step across the fracture, plus the transform of the ramus fragment. |
| 4.5 | **Acetabulum** | **Both, reported separately.** (a) Gap and step **at the articular surface** — the joint line — which is what an outcome score grades. (b) The **rigid displacement of the column or wall fragment** as a body, which is what the reduction manoeuvre needs. They answer different questions. Also, **Trouwborst et al.'s published 3D gap area** (mm²; Bone Joint J 2025, doi 10.1302/0301-620X.107B2.BJJ-2024-0390.R1) is emitted **here only, alongside** the surgeon's own number, so reviewers can compare it with the one published 3D metric. Decided 2026-09-27. |
| 4.6 | **Order** | **SI joint first, then symphysis.** The SI joint is already built and tested, so it proves the whole pipeline (fragments, per-point number, study row, review sheet) on a measurement the surgeon has already approved; the symphysis is the first new one. Decided 2026-09-27. |

## 5. Pre-operative and post-operative

| # | Decision | Rejected |
| --- | --- | --- |
| 5.1 | **Each scan is measured on its own**, against its own reference from section 2; the outcome is the pre-operative number minus the post-operative one. This survives metal artifact, and it still gives a valid number when only one scan exists. | Registering the post-operative scan onto the pre-operative one: a registration that fails on metal streak corrupts every number silently. Doing both and cross-checking is deferred, not rejected — it can be added as a check later. |
| 5.2 | The two scans' references may differ slightly. That difference is **measured and reported** as part of the tool's own error, not assumed away. | Assuming one reference serves both scans. |

| # | Decision (2026-09-27) |
| --- | --- |
| 5.3 | **Post-operative cases are not planned yet.** No hospital pre/post pairs are coming for now. Any scan with metal is **refused**, with the metal's volume and its distance to the fracture in the reason, and the first version of the paper is **pre-operative displacement and the reduction plan**. |

**Known problem, not yet solved.** A post-operative CT contains screws and
plates, whose streak artifact corrupts HU exactly along the fracture line being
measured, and TotalSegmentator was not trained on it. There is no
post-operative CT in any data on this workstation. This has to be tested on
real post-operative cases from the hospital before the post-operative half can
be trusted.

## 6. Validation

The surgeon, asked what accuracy would beat hand measurement and what to
validate against:

> "Hand measurement are usually inaccurate before. This will make the hand
> measurement obsolete. There's no 100% accurate technique for measurement in
> pelvic and acetabulum measurement except if it's nondisplace fracture or
> anatomically reduced. It's a 3-plane deformity and displacement."

| # | Decision |
| --- | --- |
| 6.1 | **A surgeon's measurement is not ground truth, and the tool is not validated against agreeing with one.** Agreement with hand measurement would only prove the tool reproduces the bias it exists to remove. |
| 6.2 | **Ground truth comes from a computational phantom**: an intact pelvis CT, cut along a chosen fracture plane, with a fragment moved by a transform we choose. The tool must recover that transform. This is the only exact ground truth available. |
| 6.3 | **Two real-patient zero points**, from the surgeon's own statement that these are the only cases where measurement is certain: an **undisplaced fracture** must read about zero, and an **anatomically reduced** post-operative case must read about zero. What the tool reads on those cases is its accuracy floor — measured, not claimed. |
| 6.4 | **No accuracy target is claimed in advance.** The figure that goes in the paper is whatever 6.2 and 6.3 measure. |

## 7. What the output is for

| # | Decision | Rejected |
| --- | --- | --- |
| 7.1 | The tool reports **its own number**, not a published grade. It is **not** mapped onto Matta, Matta–Tornetta or Lefaivre. | Emitting a Matta or Tornetta grade alongside: it would bin a continuous three-plane measurement into a one-plane threshold and inherit exactly the bias being removed. |
| 7.2 | The intended use is to **correlate that number with a functional score later**. So the output is study-ready from the start: continuous, one row per patient per point per timepoint, carrying the reference used and its fit quality, ready to join to a functional outcome table. | A per-case report only, with no machine-readable table. |

## 7a. One engine with Corridor Finder

The surgeon's decision, recorded as corridor-finder DECISIONS 8.4 (2026-09-27):
this project **shares Corridor Finder's engine** (`corridor-finder/corridor_engine`),
and neither project keeps its own copy of a measurement the other makes.

| # | Consequence |
| --- | --- |
| 7a.1 | The sacroiliac gap and step (4.2) is `corridor_engine/si_joint.py`, called, never re-implemented. A different definition is a change to the engine, with a test, and Corridor Finder's harness is re-run. |
| 7a.2 | The fragment finder, the mirror reference (section 2) and the per-fragment transform home (1.1) are **new modules in `corridor_engine`**, not a separate package. The transform home is exactly what Corridor Finder's virtual reduction (its section 3, now first in its order of work, its 8.1) applies to the bones before searching for a corridor, so both projects stand on one implementation. |
| 7a.3 | Therefore the mirror reference of 2.1/2.1a is the reference for both projects; corridor-finder DECISIONS 3.3 has to say the same. |
| 7a.5 | **How the injured side is put back, for both projects** (the surgeon's ruling in the Corridor Finder session, recorded there as its 3.6, 2026-09-27, after this project's floor finding under 1.5): the mirror gives only the **starting position**, and every reduction, unilateral as well as bilateral, is then fitted by **congruence of the fracture surfaces and the SI joint surfaces** (the "jigsaw" of 2.5), reporting its **remaining error per region** (SI joint, symphysis, each fracture). So the fracture-surface route and congruence fitting (slice 1b) are what Corridor Finder's virtual reduction is built on, not `to_reference` from the mirror alone. |
| 7a.4 | This directory keeps what is this project's alone: these decisions, the per-point measurement and reporting layer, the study table (7.2), and its tools and README. |

## 7b. The four CLINIC cases, as read by the surgeon (2026-09-27)

Read from case-reading sheets (3D bones, axial CT at S1, S2, acetabular roof,
mid-acetabulum and symphysis, simulated AP). This is the ground truth the
tool is tested against on real anatomy.

| Case | Sacral fracture | SI disruption | Acetabulum | Anterior ring | Intact hemipelvis |
| --- | --- | --- | --- | --- | --- |
| CLINIC_0012 | right | none | no | right pubic body and rami (the fragment slice 1 found; confirmed) | left |
| CLINIC_0023 | right | none | no | **both** pubic bodies | none fully: the left has a pubic body fracture |
| CLINIC_0025 | left | none | **right** | left superior ramus | none: right acetabulum, left sacrum and ramus |
| CLINIC_0060 | **both (bilateral)** | none | no | yes | none: gap/step and fitting fractures together (2.4, 2.5) |

**Correction, 2026-09-27.** This table first recorded CLINIC_0025's
acetabular fracture as left and its right side as intact. When asked, the
surgeon had given only the sacral side, and it was wrongly assumed that the
acetabulum was on the same side. His reading from the fragment sheets:
0025's acetabular fracture is **right**, its anterior ring injury is the left
superior ramus, and 0023's anterior ring injury is **bilateral** (both pubic
bodies). So only CLINIC_0012 has a whole intact hemipelvis to mirror. On
0023 and 0025 the mirrored "intact" side carries a fracture of its own.

**What slice 1 found, against his reading** (fragment sheets, 2026-09-27):

- CLINIC_0012: the one promoted fragment, 18.8 cm³ of the right pubic body
  and rami, 12.2 mm off the rest of the hip, **is the fracture** he read.
- CLINIC_0023: bone no body carries home at the right pubic body (a
  fracture he read) and at the lateral rim of the right iliac wing (not a
  fracture: asymmetry, a false signal).
- CLINIC_0025: bone no body carries home at the left pubic body and superior
  ramus (a fracture he read) and at the posterior ilium beside the left
  sacrum (he read the sacrum as fractured, not that ilium). The right
  acetabular fracture cannot show: it lies in the mirrored reference side.

What follows from it:

- **The sacrum pre-selection of 2.1a is right on all four, but still cannot
  be calibrated.** All four have a sacral fracture, so there is no case with
  an intact sacrum to show how much adding the sacrum costs a normal fit.
- **The eight SI joints are zero points** (6.3). What `si_joint.py` reads on
  them, all read by the surgeon as undisplaced (gap p90 / step / ilium in
  front + / ilium above +, mm). *Before* is the engine at 712f8cc; *after*
  is d25d003, where the Corridor Finder session fixed a bias in the up/down
  estimate (it clamped at the ends of the trace and broke ties toward the
  most negative shift). The after numbers were re-measured here and match
  theirs exactly.

  | Case | Side | Before | After |
  | --- | --- | --- | --- |
  | CLINIC_0012 | right | 3.7 / 5.0 / +4.2 / -0.8 | 3.6 / 4.0 / +2.8 / -1.4 |
  | CLINIC_0012 | left | 7.2 / 9.7 / +7.8 / -1.6 | 7.6 / 7.8 / +6.8 / -1.6 |
  | CLINIC_0023 | right | 5.6 / 4.4 / +2.1 / -2.4 | 5.4 / 2.4 / +2.3 / -0.6 |
  | CLINIC_0023 | left | 4.8 / 2.9 / +0.8 / -0.8 | 4.7 / 3.0 / +0.5 / -1.4 |
  | CLINIC_0025 | right | 4.0 / 3.8 / +3.5 / -0.8 | 2.8 / 2.2 / +1.9 / -0.8 |
  | CLINIC_0025 | left | 2.9 / 3.8 / +0.8 / -2.4 | 2.9 / 3.0 / +0.6 / -2.0 |
  | CLINIC_0060 | right | 3.6 / 6.9 / +6.0 / -1.6 | 3.5 / 6.3 / +5.3 / -1.4 |
  | CLINIC_0060 | left | 3.0 / 6.5 / +3.0 / -0.8 | 2.9 / 6.6 / +2.9 / -0.6 |

  (Some of the change in gap and step comes from a landmark fix in 966e35c:
  the S1/S2 body centres now sit in the vertebral body, which moves the S1-S2
  band slightly.) After the fix, the step on an intact joint is still
  **2.2-7.8 mm** (median 3.5), the ilium always in front, and the largest is
  on CLINIC_0012's uninjured side. `si_joint.looks_disrupted` still
  pre-selects that side as disrupted, now from the gap (7.6 against 3.6 mm,
  under the 2 mm rule of corridor-finder 2.4): a 4 mm gap asymmetry between
  two joints the surgeon reads as intact. So the absolute step is largely
  anatomy. It stays right for Corridor Finder's purpose (how much of the
  joint to bridge as bone), but it **cannot be the outcome number**, because
  6.3 requires an undisplaced joint to read about zero; hence 4.2 as revised.
  The up/down component is no longer in whole slices but is **still below on
  all eight, 0.6-2.0 mm**. Whether that is anatomy or method is not known.
  On phantoms the fixed estimate reads no shift as 0 and gets the sign right,
  but it **under-reads the size by about a quarter** (3 / 5 / 8 mm read as
  2.0 / 3.8 / 6.8 mm). That is pinned in its tests, not corrected.
- CLINIC_0025 is the only acetabular case (right), so the acetabular point
  (4.5) and the 0.5 cm³ rule (3.2) can be tested on one case only.
- CLINIC_0023's left femoral head sits 18 mm lower than its right (5-11 mm on
  the other three); injury or positioning is not yet known.

## 7c. Reduction by congruence (slice 1b), decided 2026-09-27

How a displaced hemipelvis is put back, for both projects (7a.5,
corridor-finder 3.6): the mirror gives the starting pose, and the pose is
then fitted by congruence of the fracture surfaces and the SI joint
surfaces.

| # | Decision | Rejected |
| --- | --- | --- |
| 7c.1 | **Order:** fracture surfaces first (both the reduction and the outcome number of 1.5 are measured across them), then the **reduction fit**, which Corridor Finder's virtual reduction is waiting on and which is the only route for bilateral cases. Then the local gap and step outcome. | The outcome number first; both at once. |
| 7c.2 | **SI joint target width:** the reduced joint is closed to the **intact side's measured anterior gap, capped at 4 mm**; with both sides injured, **4 mm** (the definition of corridor-finder 2.2, shared). | Fitting the step only, leaving the width free (a joint left open would read as reduced); a fixed 3 mm. |
| 7c.3 | **The surgeon's fracture marks** (corridor-finder 7.1) **seed** the fracture-surface search when present; fracture surfaces are still found automatically without them, and one found far from every mark is flagged. | Automatic only; marks required. |
| 7c.4 | **Mirror and congruence disagreeing:** the congruence result is used, and flagged for the surgeon's review when it departs from the mirror start by more than the mirror's measured normal floor for that region (the table under section 1: about 5 mm at the SI joint, 10 mm at the symphysis). | Congruence always wins with no flag; limiting the move to the floor (it could then never correct the mirror beyond its own floor). |
| 7c.5 | **The moving unit** is the hip bone plus the lateral sacral fragment when the sacrum is fractured: the sacral fracture surface is found and the **fragment split off automatically**, and the surgeon **confirms the split** on the review sheet (3.1, 3.3). This changes corridor-finder 3.2, where the fragment is split by hand. | Splitting by hand in Segment Editor; keeping the sacrum whole (wrong for every sacral fracture). |
| 7c.6 | **Comminution:** the fit uses the **cortical rims** of each fracture, which survive comminution better than the cancellous face; a region whose rims do not agree is reported **unconstrained**, with an infinite error and the reason, never a small number. | Fitting the whole face with trimming (crushed bone pulls the fit); refusing every region with missing bone. |
| 7c.7 | **Symphysis target gap:** the **median symphyseal gap measured on the 274 normal CTPelvic1K pelvises**, reported with its range. | A textbook 4 mm; fitting the step only. |
| 7c.8 | **Acceptance:** nothing is planned on a reduction of a real CT until the surgeon **accepts that case** on a before/after sheet (bones as scanned, as reduced, the error per region), as corridor-finder 3.1 already requires. | Automatic acceptance under an error threshold (the errors are fit quality, not a proven bound); blocking real CTs until a bulk validation. |

**What each region reports** (agreed with Corridor Finder): the larger of
the 90th-percentile surface mismatch after the fit and the error measured
on phantoms for that kind of region; `inf` when unconstrained. Corridor
Finder shows a screw with an amber warning wherever that error exceeds the
screw's spare clearance within 10 mm of the region, and never reads a
missing region as safe.

## 7d. Finding fractures on real CTs (decided 2026-10-03)

After slice 1b, on the four CLINIC cases the sacral fractures were not
found, so every reduction region was unconstrained. The surgeon read
close-ups of each sacrum with the expert label outlined over the CT:

> "It doesn't detect an impact fracture which bone will be dense instead of
> creating a radiolucent area" — and on CLINIC_0060 the label runs solid
> across a fracture line visible on the CT.

So slice 1b failed for two reasons. An **impacted fracture** (bone driven
into itself, the usual lateral-compression sacral fracture) shows as a
**dense band**, not a lucent line: there is no gap to find, in the label or
in the CT. And where there is a visible line, the expert label may paint
over it.

| # | Decision | Rejected |
| --- | --- | --- |
| 7d.1 | **Fractures are found from the CT first**, inside the bone label: both the **lucent line and broken cortex** of a fracture that gapes, and the **dense band** of an impacted one. **The surgeon's marks are the backup**: where the CT finds nothing, the plane through his marks (corridor-finder fracture.py) is used as the fracture surface. | CT only (a faint line stays unfound); marks as the only source (every case needs marking); re-segmenting the bones and hoping the new labels leave a gap. |
| 7d.2 | **The phantoms behind each region's error bound go to 30 mm** of displacement, and the bound is **measured per displacement**, so a 15 mm case is given the bound measured at 15 mm. Previously they reached only 8-9.5 mm, and every real region (11-17 mm) read "displaced further than the phantoms". | 20 mm; 50 mm. |
| 7d.3 | **Next: fracture finding**, together with the wider phantom range. It unblocks Corridor Finder's reduction and three of the five outcome points (sacrum, rami, acetabulum). The outcome number at the SI joint and symphysis, which needs no fracture finding, follows. | The SI and symphysis outcome first; both together. |
| 7d.4 | **Impaction in the outcome number (1.5)** is a **negative gap**, in mm: -4 mm means 4 mm of bone driven into itself. One continuous variable runs from impacted through anatomical (0) to gaping, for regression against function (7.2); the step is reported as usual. | A separate impaction depth (two variables where one does); flagging impaction and reporting only the step. |
| 7d.5 | **A band is dense (impacted)** when it is denser than **the same place on the mirrored intact side of the same patient** by a measured margin: self-calibrating to each patient's bone and scanner. With both sides injured, against the patient's own cancellous bone nearby, and it says so. | The patient's own nearby cancellous bone always (normal sclerosis, as at the SI joint, could read as impaction); a fixed HU threshold (slice 1 found 44-65% of cancellous bone under 150 HU). |
| 7d.6 | **Reducing an impacted fracture**: the cortical rims beyond the impacted zone are fitted together, and the length lost to impaction comes from the mirrored side. Where the reduction rests on the mirror, it says so and carries the mirror's floor (the table under section 1); where the rims cannot pin it, the region is unconstrained (inf). | The mirror alone there; leaving it unreduced. |

## 7e. After slice 1c on the real cases (decided 2026-10-04)

Slice 1c finds fractures from the CT on phantoms (a lucent line painted
over by the label; impacted bands, with depth to within 0.2-1.0 mm). On
the four CLINIC cases it found **no** lateral sacral fracture the surgeon
read, and he read **every** sacral surface it did find as **not a
fracture**: CLINIC_0025 sacrum_1 (lucent, transverse), CLINIC_0060
sacrum_1 (impacted band along the junction of two sacral segments) and
sacrum_2 (gap near the top of the right ala). On real sacra the CT detector
is so far 0 of 3 right where it fires, and it has missed every lateral
sacral fracture read.

| # | Decision | Rejected |
| --- | --- | --- |
| 7e.1 | **For now, a sacral fracture is found from the surgeon's marks** (3 or more clicks in Corridor Finder, its fracture.py), which become the fracture surface. They are labelled as marks, never as found. This unblocks the reduction and the outcome number on real cases. **The CT detector keeps improving behind it**, and is reported beside the marks wherever both exist. | Improving the detector with no marks (nothing works on real cases until it does); trying a learned fracture-segmentation model first. |
| 7e.2 | **Surfaces lying along the junctions between fused sacral segments** (S1-S2, S2-S3 and so on: remnant disc spaces, present in every adult sacrum) are **flagged as a probable disc remnant** on the review sheet, **not dropped**: a true transverse sacral fracture can run there too, and the surgeon decides. | Dropping them (a transverse fracture at that level would vanish); reporting them as found (every adult sacrum would show fractures). |
| 7e.3 | **The phantom bounds stop at 27-28 mm**, not the 30 mm of 7d.2: at 30 mm the phantom fits gave no usable number. Beyond the limit a region is unconstrained, with the reason. | Reworking the phantoms or the fit until 30 mm gives a number. |

## 7f. True anatomical planes (the surgeon's rulings, given in the Corridor Finder session, 2026-10-09)

Relayed by the Corridor Finder session under one engine (7a, corridor-finder
8.4), in the surgeon's words:

> "When you measured gap/stepping, make sure the cut was really
> symmetrical, or it will be biased."
>
> "Always generate true axial, coronal, sagittal views using anatomical
> landmarks (intact ones first), then create the correct cut from the first
> generated plane."

| # | Decision |
| --- | --- |
| 7f.1 | The **first plane is the mid-sagittal plane of the sacrum**. As first ruled, it went through the S1 and S2 vertebral body centres and the centre of the sacral canal at those levels. **Amended with the surgeon's agreement, 2026-10-09:** it is the **central sacrum's own symmetry plane** (`mirror.fit_plane(labels, "central_sacrum")`, placed from L5 but fitted to sacrum voxels only), with the S1/S2/canal points kept as the fallback. Fitted to those points, the plane came out 13 and 31 degrees off the pelvis on 2 of the 4 CLINIC cases (on 0023 a canal "centre" was an S1 foramen 23 mm lateral), while the symmetry plane was 2.6-6.5 degrees from the line between the ASISs on all four (Corridor Finder session's measurement, corridor-finder DECISIONS 8.5). |
| 7f.2 | The **true coronal** is then tilted parallel to the anterior pelvic plane of the **intact** hemipelvis (its ASIS and pubic tubercle; both sides when both are intact). The surgeon can shift the axes himself. |
| 7f.3 | The **true axial** is perpendicular to both. |
| 7f.4 | Scope: Corridor Finder's SI gap and step, its C-arm views and screw angles, and **this project's displacement measurement**. The frame is built once, in the shared engine (`corridor_engine/anatomical_frame.py`, being built by the Corridor Finder session), and every slice-based measurement and every reported direction (1.3) uses it. |
| 7f.5 | **The outcome gap and step (1.5) is reported both ways, side by side** (this project's ruling, 2026-10-09): measured in 3D across each fracture surface, where no cut can tilt it, and measured slice by slice on the CT resliced into the true planes, as it is read on a film. The paper can then show how much slicing alone changes the number. Every direction is given in the true frame either way. Rejected: the frame for direction only; true-plane slices only. |
| 7f.7 | **Slice-by-slice numbers are taken from the original voxels**, placed in the true frame and binned by their true-axial coordinate, **never from resampled voxels**: reslicing the labels onto the true planes moved SI gaps by 1-2 mm even with no turn at all (Corridor Finder session's measurement). A resliced CT is for display only. |
| 7f.6 | **Two midlines are kept, each for its own question**, and the engine reports how far apart they are on every case: the **mirror plane** (2.1, 2.1a: L5, plus the central sacrum when it is intact) decides the symmetry of the bones, and the **frame's mid-sagittal plane** (7f.1: the S1 and S2 bodies and the canal) decides the orientation of the cuts. Rejected: one plane under the frame's rule; one plane under the mirror's rule. |

## 7g. Which bone labels the study measures on (decided 2026-10-09)

The same CT gives different SI figures on the CTPelvic1K expert labels and
on TotalSegmentator's: CLINIC_0012's left gap 8.4 against 4.5 mm,
CLINIC_0023's right step 2.3 against 6.1 mm (Corridor Finder session's
measurement). Hospital cases will only have TotalSegmentator labels.

| # | Decision | Rejected |
| --- | --- | --- |
| 7g.1 | The study measures on **TotalSegmentator's labels, corrected by the surgeon** in Segment Editor at each measured joint and fracture before anything is measured. The correction is part of the measurement and is saved with the case, so every number can be traced to the labels it was taken on. | TotalSegmentator uncorrected, with its difference from the expert labels reported as method error; the expert labels only (the hospital cases will not have them). |
| 7g.2 | How far the numbers move between the expert labels, uncorrected TotalSegmentator labels and corrected ones is still **measured** on the CTPelvic1K cases and reported, so the paper says what the segmentation, and the correction, contribute. | Not measuring it. |

## 8. Data

| # | Decision |
| --- | --- |
| 8.1 | Unchanged from corridor-finder DECISIONS 4.1: before any public dataset is downloaded, the exact files, source and size are put to the surgeon and his go-ahead waited for. CTs stay on the workstation. Nothing patient-derived is ever committed to git. |
| 8.2 | The four CTPelvic1K CLINIC cases already on the workstation are **pre-operative fracture CTs only**. Pre/post pairs, and any post-operative case at all, have to come from the hospital, de-identified, under 8.1. |
