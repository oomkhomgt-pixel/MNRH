"""End-to-end check of the Corridor Finder panel inside real 3D Slicer.

Drives the module's own widget the way a user does (select the CT, click
Segment, Detect landmarks, pick corridor and side, Suggest, Add, drag a screw
handle through the markups API, click each Export button) and checks every
step's result and the exported files. Two CTs are used:

  phantom  a synthetic pelvis (corridor_engine.phantoms.pelvis_like as bone
           HU inside a soft-tissue body), stored in the standard DICOM
           layout (i toward patient left, j toward posterior), so the
           left/right answer is known exactly;
  sample   a real CT from Slicer's Sample Data (default CTAAbdomenPanoramix,
           lower chest to upper pelvis) to prove the mechanics on real HU
           values and scan geometry. Its anatomy is incomplete (no pubis or
           acetabulum), so only mechanics are checked on it, not anatomy.

Run with Slicer's normal settings, so that installed extensions (such as
TotalSegmentator) and the module path to this checkout are loaded:

  Slicer --no-splash --no-main-window
    --python-script <repo>/corridor-finder/tests/slicer/workflow_check.py

Message boxes are intercepted: error/warning displays are recorded and
fail the step; confirmation prompts are recorded and declined.

Not named test_*.py so pytest never collects it (it needs Slicer).
Environment: CF_OUT_DIR (exports and the report; default a new temp dir),
CF_SAMPLE (Sample Data name; empty to skip). Exit code 0 only if every
check passed.
"""
import base64
import copy
import gzip
import importlib.util
import json
import os
import struct
import sys
import tempfile
import time
import traceback

import numpy as np
import slicer
import vtk

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from corridor_engine import plan as plan_mod  # noqa: E402
from corridor_engine import segmentation as seg  # noqa: E402
from corridor_engine.phantoms import pelvis_like  # noqa: E402

OUT_DIR = os.environ.get("CF_OUT_DIR") or tempfile.mkdtemp(prefix="cf_workflow_")
os.makedirs(OUT_DIR, exist_ok=True)
SAMPLE = os.environ.get("CF_SAMPLE", "CTAAbdomenPanoramix")

_report = open(os.path.join(OUT_DIR, "workflow_check_report.txt"), "w", encoding="utf-8")
_failures = []
_dialogs = []


def log(msg=""):
    print(msg)
    _report.write(msg + "\n")
    _report.flush()


def check(condition, what):
    log(f"    [{'ok' if condition else 'FAIL'}] {what}")
    if not condition:
        _failures.append(what)
    return condition


def _record_dialog(kind):
    def record(text, *args, **kwargs):
        _dialogs.append((kind, str(text)))
        log(f"    [{kind}] {text}")
    return record


slicer.util.errorDisplay = _record_dialog("errorDisplay")
slicer.util.warningDisplay = _record_dialog("warningDisplay")
slicer.util.confirmOkCancelDisplay = lambda text, *a, **k: log(f"    [declined confirmation] {text}") and False
slicer.util.confirmYesNoDisplay = lambda text, *a, **k: log(f"    [declined confirmation] {text}") and False


def step(name):
    """Decorator: run a workflow step, time it, and fail the dataset on an
    exception or on any error/warning dialog raised during the step."""
    def wrap(fn):
        def run(*args, **kwargs):
            log(f"  - {name}")
            n_dialogs = len(_dialogs)
            t0 = time.time()
            try:
                result = fn(*args, **kwargs)
            except Exception:
                log(traceback.format_exc())
                _failures.append(f"{name}: exception")
                raise
            finally:
                log(f"    ({time.time() - t0:.1f} s)")
            new = _dialogs[n_dialogs:]
            if not check(not new, f"{name}: no error/warning dialogs"):
                raise RuntimeError(f"{name}: dialog(s) {new}")
            return result
        return run
    return wrap


def make_phantom_ct():
    """Synthetic pelvis CT in the standard DICOM voxel layout. Returns the
    node; the engine should see patient right at +x."""
    labels, spacing = pelvis_like()  # engine layout (z, y, x), RAS, +x = patient right
    sx, sy, sz = spacing
    nz, ny, nx = labels.shape
    zz, yy, xx = np.mgrid[0:nz, 0:ny, 0:nx]
    body = ((xx - nx / 2.0) / (nx * 0.49)) ** 2 + ((yy - ny * 0.55) / (ny * 0.47)) ** 2 <= 1.0
    hu = np.full(labels.shape, -1000, dtype=np.int16)
    hu[body] = 40
    hu[labels > 0] = 700
    origin = (-(nx - 1) / 2.0 * sx, -(ny - 1) / 2.0 * sy, 0.0)  # engine RAS of voxel (0, 0, 0)
    # DICOM layout: i runs toward patient LEFT (-R), j toward POSTERIOR (-A).
    ijk_to_ras = np.diag([-sx, -sy, sz, 1.0])
    ijk_to_ras[:3, 3] = (origin[0] + (nx - 1) * sx, origin[1] + (ny - 1) * sy, origin[2])
    return slicer.util.addVolumeFromArray(hu[:, ::-1, ::-1].copy(), ijkToRAS=ijk_to_ras, name="CF phantom CT")


def label_centroid_x(logic, label):
    pts = logic.labels_volume.mask_voxel_centers_world(logic.labels_volume.array == label)
    return float(pts[:, 0].mean()) if len(pts) else float("nan")


def segment_centroid_ras(seg_node, segment_id, ct):
    """RAS centroid of a segment, computed with Slicer's own IJK-to-RAS."""
    arr = slicer.util.arrayFromSegmentBinaryLabelmap(seg_node, segment_id, ct)
    k, j, i = np.argwhere(arr > 0).mean(axis=0)
    m = vtk.vtkMatrix4x4()
    ct.GetIJKToRASMatrix(m)
    return np.array(m.MultiplyPoint([i, j, k, 1.0])[:3])


def run_workflow(w, ct, name, *, expect_source, check_anatomy):
    log(f"\n=== {name}: {ct.GetName()} ===")
    logic = w.logic
    logic.corridor_defs = copy.deepcopy(_PRISTINE_CORRIDOR_DEFS)  # undo any mechanics-only relaxation
    w.marginSpin.value = logic.screw_library["margin_default_mm"]

    @step("Segment")
    def segment():
        w.volumeSelector.setCurrentNode(ct)
        w.segmentTsCheckbox.checked = True  # TotalSegmentator preferred, as by default
        w.segmentButton.click()
        check(logic.labels_volume is not None, "labels volume created")
        present = sorted(int(v) for v in np.unique(logic.labels_volume.array) if v)
        log(f"    labels present: {[seg.LABEL_NAMES.get(v, v) for v in present]}")
        log(f"    status: {w.segmentStatusLabel.text!r}")
        check(logic.segmentation_source == expect_source, f"segmentation source is {expect_source}: {logic.segmentation_source!r}")
        if logic.segmentation_source == "fallback":
            check("UNVERIFIED" in w.segmentStatusLabel.text, "panel flags the fallback segmentation as UNVERIFIED")
            check(bool(logic.segmentation_note), "panel says why TotalSegmentator was not used")
        check(w.detectLandmarksButton.enabled, "Detect landmarks enabled")
        check(seg.HIP_L in present and seg.HIP_R in present, "both hips labelled")
        xr, xl = label_centroid_x(logic, seg.HIP_R), label_centroid_x(logic, seg.HIP_L)
        log(f"    hip_right centroid x = {xr:.1f} mm, hip_left centroid x = {xl:.1f} mm (RAS)")
        if check_anatomy:
            check(xr > 0 > xl, "patient's right hip is labelled hip_right (+x in RAS)")
        seg_node = w._bonesSegmentationNode
        segmentation = seg_node.GetSegmentation() if seg_node else None
        ids = {segmentation.GetNthSegmentID(i) for i in range(segmentation.GetNumberOfSegments())} if segmentation else set()
        check(ids == {seg.LABEL_NAMES[v] for v in present}, "'CF bones' segmentation shows exactly the engine's labels")
        if "hip_right" in ids:
            shown_x = segment_centroid_ras(seg_node, "hip_right", ct)[0]
            check(abs(shown_x - xr) < 0.5, f"hip_right is displayed where the engine has it (x {shown_x:.1f} vs {xr:.1f} mm)")

    @step("Detect landmarks")
    def landmarks():
        w.detectLandmarksButton.click()
        lms = logic.landmarks
        log(f"    {len(lms)} landmarks; warnings: {w.landmarkWarningsLabel.text!r}")
        node = w._landmark_fiducial_node
        check(node is not None and node.GetNumberOfControlPoints() == len(lms), "one fiducial per landmark shown")
        check(logic.frame is not None, "APP frame built")
        check(w.suggestButton.enabled, "Suggest enabled")
        if logic.frame is not None:
            f = logic.frame
            log(f"    APP x_hat {np.round(f.x_hat, 3)}, y_hat {np.round(f.y_hat, 3)}, z_hat {np.round(f.z_hat, 3)}")
            check(f.x_hat[0] < 0 and f.y_hat[1] > 0 and f.z_hat[2] > 0, "APP axes: x toward patient left, y anterior, z cephalad")
        if check_anatomy:
            check(lms["asis_right"].xyz[0] > lms["asis_left"].xyz[0], "right ASIS lies to the patient's right of the left ASIS")
        # Drag a landmark: the frame must be rebuilt from the moved point.
        before = logic.frame.origin.copy()
        idx = w._landmark_index_to_name.index("asis_left")
        p = [0.0, 0.0, 0.0]
        node.GetNthControlPointPosition(idx, p)
        node.SetNthControlPointPosition(idx, p[0] - 10.0, p[1], p[2])
        check(logic.landmarks["asis_left"].source == "manual", "dragged landmark recorded as manual")
        check(np.allclose(logic.frame.origin, before + np.array([-5.0, 0.0, 0.0]), atol=1e-6), "APP origin moved by half the ASIS drag")
        node.SetNthControlPointPosition(idx, *p)  # put it back

    @step("Suggest every corridor and side")
    def suggest_all():
        found = {}
        for ci in range(w.corridorCombo.count):
            w.corridorCombo.setCurrentIndex(ci)
            for si in range(w.sideCombo.count):
                w.sideCombo.setCurrentIndex(si)
                cid, side = w._currentCorridorId(), w.sideCombo.currentText
                t0 = time.time()
                w.suggestButton.click()
                res = w._current_results
                desc = w.resultsList.item(0).text() if w.resultsList.count else "no candidates"
                log(f"    {cid:28s} {side:8s} {desc}  [{w.resultsList.count} listed, {time.time() - t0:.1f} s]")
                check(w.resultsList.count == len(res), f"{cid}/{side}: panel lists every suggestion")
                found[(cid, side)] = res
        # Suggestions belong to the corridor they were computed for: changing
        # the selection must drop them, so Add cannot file them elsewhere.
        w.corridorCombo.setCurrentIndex(0)
        check(w.resultsList.count == 0 and not w.addScrewButton.enabled, "changing the corridor clears the old suggestions")
        return found

    found = {}
    try:
        segment()
        landmarks()
        found = suggest_all()
    except Exception:
        return

    fitting = [(k, r) for k, r in found.items() if r and r[0].screw.fits]
    if name == "phantom":
        check(("iliosacral_s1", "right") in dict(fitting), "a screw fits the right iliosacral S1 corridor on the phantom")
    check(bool(fitting), f"at least one corridor yields a screw that fits at the default {w.marginSpin.value} mm margin")
    if not fitting:
        # MECHANICS ONLY: to exercise add/drag/export when nothing fits,
        # retry with the panel's margin at 0 mm and, in this test's memory
        # only, no minimum corridor length. Neither changes the breach rule
        # or corridors.json; a screw added this way says nothing about anatomy.
        log("  - MECHANICS ONLY: nothing fits; retrying with margin 0 mm and no minimum length (in memory)")
        w.marginSpin.value = 0.0
        for spec in logic.corridor_defs.values():
            spec["length_range_mm"] = [0.0, spec["length_range_mm"][1]]
        for (c, s) in found:
            w.corridorCombo.setCurrentIndex(w.corridorCombo.findData(c))
            w.sideCombo.setCurrentIndex(w.sideCombo.findText(s))
            w.suggestButton.click()
            if w._current_results and w._current_results[0].screw.fits:
                fitting.append(((c, s), w._current_results))
                log(f"    {c}/{s} fits at margin 0: {w._current_results[0].screw.diameter_mm} mm")
        if not check(bool(fitting), "some corridor fits at margin 0 (needed to test add/drag/export)"):
            return
    (cid, side), _ = next(((k, r) for k, r in fitting if k == ("iliosacral_s1", "right")), fitting[0])

    @step(f"Add {cid}/{side} to the plan")
    def add():
        w.corridorCombo.setCurrentIndex(w.corridorCombo.findData(cid))
        w.sideCombo.setCurrentIndex(w.sideCombo.findText(side))
        w.suggestButton.click()
        w.caseAliasEdit.text = f"workflow-{name}"
        w.newPlanButton.click()
        w.resultsList.setCurrentRow(0)
        w.addScrewButton.click()
        check(len(logic.plan.screws) == 1, "plan has one screw")
        screw = logic.plan.screws[0]
        node = w._screw_line_nodes.get(screw.screw_id)
        check(node is not None and node.GetNumberOfControlPoints() == 2, "screw shown as a 2-point markups line")
        e, t = [0.0] * 3, [0.0] * 3
        node.GetNthControlPointPosition(0, e)
        node.GetNthControlPointPosition(1, t)
        check(np.allclose(e, screw.entry_xyz) and np.allclose(t, screw.target_xyz), "line endpoints are the planned entry/target (RAS)")
        v = screw.validation
        log(f"    {screw.screw_id}: {screw.diameter_mm} x {screw.length_mm} mm, clearance {v['min_clearance_mm']:.2f} mm, margin {screw.margin_mm} mm, breach {v['breach']}")
        check(v["breach"] is False, "suggested screw validates without breach")
        log(f"    skin entry found: {screw.skin_entry_xyz is not None}; APP angles {screw.angles_app}")
        return screw, node

    try:
        screw, line = add()
    except Exception:
        return

    @step("Drag the target handle")
    def drag(delta_mm, expect_breach):
        t = [0.0] * 3
        line.GetNthControlPointPosition(1, t)
        new_t = np.array(t) + np.array(delta_mm)
        n_audit = len(logic.plan.audit)
        line.SetNthControlPointPosition(1, *new_t)
        check(np.allclose(screw.target_xyz, new_t), "plan target follows the handle")
        check(screw.source == "adjusted", "screw marked adjusted")
        check(len(logic.plan.audit) > n_audit and logic.plan.audit[-1].action == "move_handle", "move logged in the audit trail")
        v = screw.validation
        breach = v["breach"]
        log(f"    clearance now {v['min_clearance_mm']:.2f} mm, breach {breach}; label {w.clearanceLabel.text!r}")
        check(breach == expect_breach, f"breach is {expect_breach} after moving the target by {delta_mm} mm")
        check(("b91c1c" in w.clearanceLabel.styleSheet) == breach, "clearance label is red exactly when breached")

    @step("Export plan JSON, report, STL and viewer")
    def export(tag):
        paths = {
            "JSON": os.path.join(OUT_DIR, f"{name}_{tag}_plan.json"),
            "HTML report": os.path.join(OUT_DIR, f"{name}_{tag}_report.html"),
            "STL": os.path.join(OUT_DIR, f"{name}_{tag}.stl"),
            "HTML viewer": os.path.join(OUT_DIR, f"{name}_{tag}_viewer.html"),
        }

        def fake_prompt(title, filter_str):
            return paths["HTML viewer" if "viewer" in title.lower() else "HTML report" if filter_str.startswith("HTML") else filter_str.split(" ")[0]]

        w._promptSavePath = fake_prompt
        for button, key in ((w.exportPlanButton, "JSON"), (w.exportReportButton, "HTML report"),
                            (w.exportStlButton, "STL"), (w.exportViewerButton, "HTML viewer")):
            if os.path.exists(paths[key]):
                os.remove(paths[key])
            t0 = time.time()
            button.click()
            ok = os.path.exists(paths[key])
            size = os.path.getsize(paths[key]) if ok else 0
            check(ok, f"{key} written ({size / 1e6:.2f} MB, {time.time() - t0:.1f} s)")
        if os.path.exists(paths["JSON"]):
            loaded = plan_mod.load_plan(paths["JSON"])
            plan_mod.validate_plan(loaded)
            check(len(loaded.screws) == 1 and np.allclose(loaded.screws[0].target_xyz, screw.target_xyz), "plan JSON reloads, validates and matches the plan")
        if os.path.exists(paths["HTML report"]):
            html = open(paths["HTML report"], encoding="utf-8").read()
            check(screw.screw_id in html, "report names the screw")
            check(("BREACH" in html) == screw.validation["breach"], "report shows BREACH exactly when breached")
        if os.path.exists(paths["STL"]):
            with open(paths["STL"], "rb") as f:
                f.seek(80)
                n_tri = struct.unpack("<I", f.read(4))[0]
            check(os.path.getsize(paths["STL"]) == 84 + 50 * n_tri and n_tri > 0, f"STL is a well-formed binary STL ({n_tri} triangles)")
        if os.path.exists(paths["HTML viewer"]):
            html = open(paths["HTML viewer"], encoding="utf-8").read()
            check(screw.screw_id in html, "viewer embeds the plan")
            b64 = html.split('id="payload">', 1)[1].split("</script>", 1)[0]
            raw = gzip.decompress(base64.b64decode(b64))
            header = json.loads(raw[4:4 + struct.unpack("<I", raw[:4])[0]])
            check([e["screw_id"] for e in header.get("edts", [])] == [s.screw_id for s in logic.plan.screws],
                  "viewer carries each screw's own distance field")

    @step("Correct the segmentation: erase bone around the screw, then restore it")
    def edit_segmentation():
        # Erase a 12 mm ball of bone around the screw's midpoint in every
        # segment, as a user would in Segment Editor. The next action (here:
        # Export plan JSON) must read the edit back and re-validate the
        # screw as breached; restoring the bone must restore its clearance.
        seg_node = w._bonesSegmentationNode
        segmentation = seg_node.GetSegmentation()
        m = vtk.vtkMatrix4x4()
        ct.GetRASToIJKMatrix(m)
        mid = (np.asarray(screw.entry_xyz) + np.asarray(screw.target_xyz)) / 2.0
        ci, cj, ck = m.MultiplyPoint([*mid, 1.0])[:3]
        si, sj, sk = ct.GetSpacing()
        nk, nj, ni = slicer.util.arrayFromVolume(ct).shape
        kk, jj, ii = np.ogrid[:nk, :nj, :ni]
        ball = ((ii - ci) * si) ** 2 + ((jj - cj) * sj) ** 2 + ((kk - ck) * sk) ** 2 <= 12.0 ** 2
        saved = {}
        for n in range(segmentation.GetNumberOfSegments()):
            sid = segmentation.GetNthSegmentID(n)
            arr = slicer.util.arrayFromSegmentBinaryLabelmap(seg_node, sid, ct)
            saved[sid] = arr.copy()
            arr[ball] = 0
            slicer.util.updateSegmentBinaryLabelmapFromArray(arr, seg_node, sid, ct)
        json_path = os.path.join(OUT_DIR, f"{name}_edited_plan.json")
        w._promptSavePath = lambda title, filter_str: json_path
        w.exportPlanButton.click()
        check(logic.plan.audit[-1].action == "revalidate", "edit read back and the screw re-validated")
        check(screw.validation["breach"] is True, "screw is a breach once the bone around it is erased")
        check("b91c1c" in w.clearanceLabel.styleSheet, "clearance label turned red")
        for sid, arr in saved.items():
            slicer.util.updateSegmentBinaryLabelmapFromArray(arr, seg_node, sid, ct)
        w.exportPlanButton.click()
        check(screw.validation["breach"] is False, "restoring the bone restores the screw's clearance")

    # Pulling the target 1 mm back along the axis keeps the screw on a subset
    # of its validated path, so it cannot breach; moving it 80 mm anterior
    # takes it out of bone, so it must.
    axis = np.asarray(screw.target_xyz) - np.asarray(screw.entry_xyz)
    shorten = tuple(-1.0 * axis / np.linalg.norm(axis))
    for fn, args in ((drag, (shorten, False)), (export, ("ok",)), (edit_segmentation, ()),
                     (drag, ((0.0, 80.0, 0.0), True)), (export, ("breach",))):
        try:
            fn(*args)
        except Exception:
            return


def main():
    log(f"Corridor Finder workflow check, Slicer {slicer.app.applicationVersion}; output in {OUT_DIR}")
    module_path = slicer.modules.corridorfinder.path
    check(os.path.normcase(os.path.abspath(module_path)).startswith(os.path.normcase(REPO_ROOT)),
          f"Slicer loaded the module from this checkout ({module_path})")
    w = slicer.util.getModuleWidget("CorridorFinder")
    check(w.logic is not None, "panel built with a logic (dependencies present)")
    global _PRISTINE_CORRIDOR_DEFS
    _PRISTINE_CORRIDOR_DEFS = copy.deepcopy(w.logic.corridor_defs)

    ts_installed = importlib.util.find_spec("TotalSegmentator") is not None
    log(f"TotalSegmentator extension installed: {ts_installed}")
    # TotalSegmentator finds no pelvis in the synthetic phantom, so the
    # fallback must take over (with the reason shown) either way.
    run_workflow(w, make_phantom_ct(), "phantom", expect_source="fallback", check_anatomy=True)
    if SAMPLE:
        import SampleData

        ct = SampleData.SampleDataLogic().downloadSample(SAMPLE)
        # TotalSegmentator labels sides by anatomy, independently of this
        # module's orientation handling, so on a real CT hip_right must come
        # out at +x (patient right): an end-to-end left/right check.
        run_workflow(w, ct, "sample", expect_source="totalsegmentator" if ts_installed else "fallback",
                     check_anatomy=ts_installed)

    log(f"\n{len(_failures)} failed check(s)" + ("" if not _failures else ":"))
    for f in _failures:
        log(f"  - {f}")


try:
    main()
except Exception:
    log(traceback.format_exc())
    _failures.append("harness crashed")
finally:
    _report.close()
    slicer.util.exit(0 if not _failures else 1)
