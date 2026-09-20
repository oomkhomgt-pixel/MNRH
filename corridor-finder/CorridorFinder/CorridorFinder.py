"""Corridor Finder — a 3D Slicer scripted module for percutaneous screw
corridor planning in the pelvis/acetabulum.

This is the ONLY file in the project that imports slicer/vtk/qt/ctk. All
actual geometry (segmentation, corridor search, validation, landmarks,
DRR, plan/report/mesh/viewer export) lives in the pure-Python
``corridor_engine`` package next to this extension, which is unit tested
headlessly outside Slicer. This file's job is narrow: convert Slicer's
MRML scene (volumes, segmentations, markups) to and from plain numpy
arrays/``corridor_engine.volume.Volume`` objects, and drive the UI.

NOTE ON TESTING: this module runs in 3D Slicer 5.12.4. The self-test
(CorridorFinderTest) checks the volume conversion against Slicer's own
geometry, and ``tests/slicer/workflow_check.py`` drives this panel end to
end inside Slicer (see the README's "Verified inside real 3D Slicer").
Known rough edges are marked "KNOWN LIMITATION" below.

Coordinate conventions
-----------------------
``corridor_engine`` works in the same world coordinates as Slicer's MRML
scene: RAS, x = patient Right+, y = Anterior+, z = Superior+. So points
cross the boundary unchanged (``_ras_to_engine`` / ``_engine_to_ras`` are
kept as the single named crossing point). Volumes are the part that needs
care: an engine Volume maps array index to world as origin + index *
spacing with positive spacing, while a Slicer volume's voxel axes can run
either way along each RAS axis. A typical DICOM CT has i running toward the
patient's left and j toward posterior. ``volume_node_to_engine_volume``
reverses the array along every such axis. The module self-test checks all
8 orientations against Slicer's own IJK-to-RAS mapping.

KNOWN LIMITATION: volumes whose voxel axes are not aligned with R, A and S
(gantry tilt, oblique reformat, sagittal/coronal acquisitions) and volumes
under a transform are rejected with a clear error rather than mis-mapped;
supporting them is future work.
"""

# Keep annotations lazy. The engine import below is guarded so that a
# missing dependency is reported in the module panel, but an eagerly
# evaluated annotation such as ``-> EngineVolume`` runs at class-definition
# time and raises NameError when that import failed, which aborts loading
# the whole file: Slicer then drops the module from its list entirely
# (observed in Slicer 5.12.4 before jsonschema was pip-installed).
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import traceback
from typing import Dict, List, Optional, Tuple

import numpy as np

import vtk

import slicer
from slicer.i18n import tr as _
from slicer.i18n import translate
from slicer.ScriptedLoadableModule import (
    ScriptedLoadableModule,
    ScriptedLoadableModuleLogic,
    ScriptedLoadableModuleTest,
    ScriptedLoadableModuleWidget,
)
from slicer.util import VTKObservationMixin

try:
    import qt
    import ctk
except ImportError:  # pragma: no cover - only missing outside Slicer
    qt = None
    ctk = None

# --------------------------------------------------------------------------
# Make the pure-Python engine importable. This file lives at
# corridor-finder/CorridorFinder/CorridorFinder.py; the engine package and
# its data files live at corridor-finder/corridor_engine, corridors.json,
# screws.json, one directory up.
# --------------------------------------------------------------------------
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_THIS_DIR, ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_ENGINE_IMPORT_ERROR = None
try:
    from corridor_engine import (
        app_frame,
        corridor as corridor_search,
        drr as drr_mod,
        edt as edt_mod,
        si_joint as si_joint_mod,
        entry_zone as entry_zone_mod,
        guidance as guidance_mod,
        landmarks as landmarks_mod,
        mesh as mesh_mod,
        phi as phi_mod,
        plan as plan_mod,
        report as report_mod,
        segmentation as seg_mod,
        skin as skin_mod,
        validate as validate_mod,
        export_viewer as export_viewer_mod,
    )
    from corridor_engine.volume import Volume as EngineVolume
except Exception:  # pragma: no cover
    _ENGINE_IMPORT_ERROR = traceback.format_exc()

# Third-party packages corridor_engine needs that Slicer does not bundle
# (numpy, scipy and Pillow ship with Slicer), keyed by import name, valued by
# pip requirement. jsonschema is imported eagerly by corridor_engine.plan, so
# without it the engine import above fails; scikit-image is imported lazily
# by corridor_engine.mesh, so without it everything appears to work until
# STL/viewer export. Checking both up front turns either case into a single
# "install these packages" prompt in the module panel.
_REQUIRED_PACKAGES = {
    "jsonschema": "jsonschema>=4.20,<5",
    "skimage": "scikit-image>=0.22",
}


def _missing_requirements() -> List[str]:
    """pip requirements for required packages that are not installed in
    Slicer's Python (checked without importing them)."""
    import importlib.util

    return [req for name, req in _REQUIRED_PACKAGES.items() if importlib.util.find_spec(name) is None]


class LeftRightMismatchError(RuntimeError):
    """TotalSegmentator (which labels sides by anatomy) put the right hip on
    the patient's left according to the image's orientation. Planning must
    stop: falling back to the HU segmenter, which trusts that orientation,
    would silently accept a scan whose left and right may be swapped."""


# ==========================================================================
# Coordinate conversion (the one place Slicer geometry meets the engine)
# ==========================================================================

def _ras_to_engine(xyz_ras) -> np.ndarray:
    """Slicer RAS point -> engine world point: the same coordinates (the
    engine works in RAS), as a float array."""
    return np.array([float(v) for v in xyz_ras], dtype=float)


def _engine_to_ras(xyz_engine) -> Tuple[float, float, float]:
    """Engine world point -> Slicer RAS point: the same coordinates."""
    x, y, z = xyz_engine
    return (float(x), float(y), float(z))


# Largest direction-cosine deviation accepted as "axis-aligned": over a
# 500 mm field of view, 1e-4 displaces the far edge by at most 0.05 mm.
_AXIS_ALIGNMENT_TOLERANCE = 1e-4


def _check_axis_aligned(direction: vtk.vtkMatrix4x4) -> None:
    """Raise unless voxel axes i, j, k run along R, A, S respectively (in
    either direction), i.e. the IJK-to-RAS direction matrix is diagonal
    +/-1. Must be given the direction matrix, not the full IJK-to-RAS
    matrix, whose diagonal also carries the voxel spacing."""
    for r in range(3):
        for c in range(3):
            expected = 1.0 if r == c else 0.0
            if abs(abs(direction.GetElement(r, c)) - expected) > _AXIS_ALIGNMENT_TOLERANCE:
                rows = "; ".join(
                    " ".join(f"{direction.GetElement(rr, cc):+.4f}" for cc in range(3)) for rr in range(3)
                )
                raise ValueError(
                    "Corridor Finder needs an axial volume whose voxel axes run "
                    "along the patient's left-right, anterior-posterior and "
                    "superior-inferior axes (no gantry tilt, oblique, sagittal "
                    "or coronal reformat). This volume's IJK-to-RAS direction "
                    f"matrix is [{rows}]. Resample it onto an axis-aligned grid first."
                )


def _engine_grid(volume_node):
    """How volume_node's voxel grid maps onto an engine Volume.

    Returns (flip_axes, spacing, origin): the axes of the node's
    (k, j, i)-ordered array that must be reversed so every array index
    increases along +R, +A and +S, then the (x, y, z) spacing and the RAS
    origin (first voxel) of the reversed array.
    """
    if volume_node.GetParentTransformNode() is not None:
        raise ValueError(
            f"Volume '{volume_node.GetName()}' is under a transform. Harden "
            "the transform first (Data module: right-click the volume > Harden "
            "transform), so screws are planned in the coordinates the CT is "
            "displayed in."
        )
    if volume_node.GetImageData() is None:
        raise ValueError(f"Volume '{volume_node.GetName()}' has no image data.")
    direction = vtk.vtkMatrix4x4()
    volume_node.GetIJKToRASDirectionMatrix(direction)
    _check_axis_aligned(direction)

    spacing = volume_node.GetSpacing()  # (i, j, k), always positive
    origin_ras = volume_node.GetOrigin()  # RAS of voxel (0, 0, 0)
    dims = volume_node.GetImageData().GetDimensions()  # (n_i, n_j, n_k)
    flip_axes = []
    origin = []
    for a in range(3):  # voxel axis a runs along RAS axis a
        o = origin_ras[a]
        if direction.GetElement(a, a) < 0:
            flip_axes.append(2 - a)  # numpy axis holding voxel axis a
            o -= (dims[a] - 1) * spacing[a]  # the last voxel becomes the first
        origin.append(float(o))
    return tuple(flip_axes), tuple(float(s) for s in spacing), tuple(origin)


def node_array_to_engine_array(volume_node, array_kji: np.ndarray) -> np.ndarray:
    """Reorder an array laid out on volume_node's voxel grid (as returned by
    slicer.util.arrayFromVolume or arrayFromSegmentBinaryLabelmap) into the
    engine Volume layout. Always a copy, never a view of VTK memory, so
    later edits to the node cannot change the engine's data."""
    flip_axes, _, _ = _engine_grid(volume_node)
    if not flip_axes:
        return np.array(array_kji, copy=True)
    return np.ascontiguousarray(np.flip(array_kji, axis=flip_axes))


def engine_array_to_node_array(volume_node, array_zyx: np.ndarray) -> np.ndarray:
    """Inverse of node_array_to_engine_array: lay an engine-layout array out
    on volume_node's voxel grid (reversing an axis twice restores it)."""
    return node_array_to_engine_array(volume_node, array_zyx)


def volume_node_to_engine_volume(volume_node) -> EngineVolume:
    """Convert a scalar volume node (HU or label map) to an engine Volume in
    RAS world coordinates."""
    _, spacing, origin = _engine_grid(volume_node)
    array = node_array_to_engine_array(volume_node, slicer.util.arrayFromVolume(volume_node))
    return EngineVolume(array=array, spacing=spacing, origin=origin)


# ==========================================================================
# Module
# ==========================================================================

class CorridorFinder(ScriptedLoadableModule):
    def __init__(self, parent):
        ScriptedLoadableModule.__init__(self, parent)
        self.parent.title = _("Corridor Finder")
        self.parent.categories = [translate("qSlicerAbstractCoreModule", "Orthopedics")]
        self.parent.dependencies = []
        self.parent.contributors = ["MNRH Orthopedics"]
        self.parent.helpText = _(
            "Percutaneous screw corridor planning for the pelvis and "
            "acetabulum. Segments the pelvis, auto-suggests safe screw "
            "corridors, and exports a plan report, STL, and a shareable "
            "interactive HTML viewer.\n\n"
            "Intended for preoperative planning; verify against "
            "intraoperative imaging."
        )
        self.parent.acknowledgementText = _(
            "Part of the MNRH orthopedics demo repository. Not a validated "
            "medical device; use as a research/planning aid only."
        )


# ==========================================================================
# Logic
# ==========================================================================

class CorridorFinderLogic(ScriptedLoadableModuleLogic):
    """All non-UI work: segmentation, landmark detection, corridor search,
    validation, and export. Holds the current case's state (labels volume,
    HU volume, landmarks, frame, plan) between UI actions.
    """

    def __init__(self):
        ScriptedLoadableModuleLogic.__init__(self)
        if _ENGINE_IMPORT_ERROR is not None:
            raise ImportError(
                "corridor_engine could not be imported (see traceback below); "
                "Corridor Finder cannot function without it.\n" + _ENGINE_IMPORT_ERROR
            )
        with open(os.path.join(_PROJECT_ROOT, "corridors.json"), "r", encoding="utf-8") as f:
            self.corridor_defs = {c["id"]: c for c in json.load(f)["corridors"]}
        with open(os.path.join(_PROJECT_ROOT, "screws.json"), "r", encoding="utf-8") as f:
            self.screw_library = json.load(f)
        self.view_defs = drr_mod.load_views(os.path.join(_PROJECT_ROOT, "corridors.json"))

        self.volume_node = None
        self.hu_volume: Optional[EngineVolume] = None
        self.labels_volume: Optional[EngineVolume] = None
        self.segmentation_source: str = ""  # "totalsegmentator" | "fallback" | ""
        # Why the fallback was used when TotalSegmentator was preferred.
        self.segmentation_note: str = ""
        # Optional callable(str) for progress text during long steps.
        self.progress_callback = None
        self.landmarks: Dict[str, "landmarks_mod.Landmark"] = {}
        self.frame = None
        self.plan: Optional["plan_mod.Plan"] = None
        self._edt_cache: Dict[tuple, EngineVolume] = {}
        self._body_mask: Optional[EngineVolume] = None  # for skin entries
        # screw id -> (what it was computed from, EntryArea): measuring the
        # room around an entry takes seconds, and four exports in a row ask
        # for the same one.
        self._entry_area_cache: Dict[str, tuple] = {}
        self._labels_version = 0
        # The sacroiliac joints (DECISIONS.md section 2): what they measure,
        # which side the surgeon says is disrupted, and what is therefore
        # counted as bone in each. Sacral corridors wait for that call.
        self.si_widths: Dict[str, "si_joint_mod.JointWidth"] = {}
        self.si_disrupted: Optional[str] = None
        self.si_bridge_mm: Dict[str, float] = {}

    # ---- Segmentation --------------------------------------------------

    def load_volume(self, volume_node) -> None:
        self.hu_volume = volume_node_to_engine_volume(volume_node)
        self.volume_node = volume_node
        self.labels_volume = None
        self.landmarks = {}
        self.frame = None
        self._edt_cache = {}
        self._body_mask = None
        self._labels_version += 1

    def segment(self, prefer_total_segmentator: bool = True) -> str:
        """Populate self.labels_volume. Returns "totalsegmentator" or
        "fallback" to say which path was used, so the UI can warn the user
        when the fallback (unverified) path was taken; segmentation_note
        then says why TotalSegmentator was not used."""
        if self.hu_volume is None:
            raise RuntimeError("load_volume() must be called first")

        self.segmentation_note = ""
        if prefer_total_segmentator:
            try:
                labels_array = self._run_total_segmentator()
                self.labels_volume = EngineVolume(
                    array=labels_array, spacing=self.hu_volume.spacing, origin=self.hu_volume.origin
                )
                self.segmentation_source = "totalsegmentator"
                return self.segmentation_source
            except LeftRightMismatchError:
                raise
            except Exception as exc:
                logging.warning("TotalSegmentator unavailable or failed, falling back to HU threshold:\n%s", traceback.format_exc())
                self.segmentation_note = f"TotalSegmentator was not used: {exc}"

        labels_array = seg_mod.split_pelvis_labels(self.hu_volume.array, self.hu_volume.spacing)
        self.labels_volume = EngineVolume(array=labels_array, spacing=self.hu_volume.spacing, origin=self.hu_volume.origin)
        self.segmentation_source = "fallback"
        return self.segmentation_source

    def _progress(self, text: str) -> None:
        logging.info(text)
        if self.progress_callback is not None:
            self.progress_callback(text)

    def _run_total_segmentator(self) -> np.ndarray:
        """Segment the pelvic bones with the SlicerTotalSegmentator extension
        and return an engine-layout array of corridor_engine label ids.

        Written against the extension as installed from the Slicer 5.12.4
        extension index (revision 270cac2, TotalSegmentator v2.14.0):
        TotalSegmentatorLogic.process(inputVolume, outputSegmentation,
        quality, cpu, task, subset, interactive). Its output segment IDs
        are TotalSegmentator class names, while segment *names* may be
        replaced by standard terminology names, so segments are matched by
        ID. quality="normal" is the 1.5 mm model; "fast" (3 mm) is too coarse
        for screw corridors that are only about 10 mm wide.
        """
        try:
            import TotalSegmentator
        except ImportError as exc:
            raise RuntimeError("the TotalSegmentator extension is not installed (Extensions Manager)") from exc

        ts_logic = TotalSegmentator.TotalSegmentatorLogic()
        ts_logic.logCallback = self._progress
        # Installs PyTorch, nnU-Net and TotalSegmentator on first use, after
        # asking the user (several GB; needs a network connection).
        ts_logic.setupPythonRequirements()

        # TotalSegmentator "total" task class names -> corridor_engine label ids.
        classes = {
            "hip_left": seg_mod.HIP_L,
            "hip_right": seg_mod.HIP_R,
            "sacrum": seg_mod.SACRUM,
            "femur_left": seg_mod.FEMUR_L,
            "femur_right": seg_mod.FEMUR_R,
        }
        seg_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode", "CorridorFinder_TS_temp")
        try:
            ts_logic.process(self.volume_node, seg_node, quality="normal", task="total", subset=list(classes), interactive=False)
            segmentation = seg_node.GetSegmentation()
            labels_array = np.zeros(slicer.util.arrayFromVolume(self.volume_node).shape, dtype=np.uint8)
            found = []
            for class_name, label in classes.items():
                if segmentation.GetSegment(class_name) is None:
                    continue
                mask = slicer.util.arrayFromSegmentBinaryLabelmap(seg_node, class_name, self.volume_node)
                labels_array[mask > 0] = label
                found.append(class_name)
        finally:
            slicer.mrmlScene.RemoveNode(seg_node)
        self._progress(f"TotalSegmentator found: {', '.join(found) or 'nothing'}")
        if not {"hip_left", "hip_right"} <= set(found):
            raise RuntimeError(f"TotalSegmentator did not find both hip bones (found: {', '.join(found) or 'nothing'})")
        # labels_array is on the node's voxel grid; the HU volume was reordered.
        labels = node_array_to_engine_array(self.volume_node, labels_array)
        verdict, reason = seg_mod.check_hip_sides(labels, self.hu_volume.array, self.hu_volume.spacing, self.hu_volume.origin)
        if verdict == "mirrored":
            raise LeftRightMismatchError(
                f"TotalSegmentator found {reason}. The CT's left/right orientation may be wrong "
                "(image header or patient position). Check it before planning; no segmentation was used."
            )
        if verdict != "ok":
            raise RuntimeError(f"TotalSegmentator's result is implausible: {reason}")
        return labels

    def set_labels_from_node_array(self, labels_kji: np.ndarray) -> bool:
        """Replace the labels with an array on the CT node's voxel grid (e.g.
        read back from a segmentation the user corrected). Returns True if
        anything changed; distance fields are then recomputed on next use."""
        new = node_array_to_engine_array(self.volume_node, labels_kji).astype(np.uint8)
        if self.labels_volume is not None and np.array_equal(new, self.labels_volume.array):
            return False
        self.labels_volume = EngineVolume(array=new, spacing=self.hu_volume.spacing, origin=self.hu_volume.origin)
        self._edt_cache = {}
        self._labels_version += 1
        if self.landmarks:
            self.si_widths = si_joint_mod.measure_joint_widths(self.labels_volume, self.landmarks)
            self.set_si_disrupted(self.si_disrupted)  # same declaration, re-measured joints
        return True

    # ---- Landmarks / frame ---------------------------------------------

    def detect_landmarks(self) -> Dict[str, "landmarks_mod.Landmark"]:
        if self.labels_volume is None:
            raise RuntimeError("segment() must be called first")
        self.landmarks = landmarks_mod.detect_landmarks(self.labels_volume)
        self._build_frame()
        self.si_widths = si_joint_mod.measure_joint_widths(self.labels_volume, self.landmarks)
        self.set_si_disrupted(None)  # the surgeon confirms it before any sacral corridor
        return self.landmarks

    # ---- Sacroiliac joint ------------------------------------------------

    def set_si_disrupted(self, disrupted: Optional[str]) -> None:
        """Record which joint(s) the surgeon says are disrupted, and take the
        widths that follow (DECISIONS.md 2.2). None means not yet said, and
        blocks the corridors that cross the joint."""
        self.si_disrupted = disrupted
        self.si_bridge_mm = si_joint_mod.bridging_widths(self.si_widths, disrupted) if disrupted else {}
        self._edt_cache = {}
        self._entry_area_cache = {}

    def set_si_bridge_mm(self, side: str, width_mm: float) -> None:
        """Override what is counted as bone in one joint, after the surgeon
        has measured it on the axial CT."""
        self.si_bridge_mm[side] = float(width_mm)
        self._edt_cache = {}
        self._entry_area_cache = {}

    def si_bridge_by_label(self) -> Dict[int, float]:
        return {seg_mod.HIP_R: self.si_bridge_mm.get("right", 0.0), seg_mod.HIP_L: self.si_bridge_mm.get("left", 0.0)}

    def si_sentences(self) -> List[str]:
        """What to show the surgeon about the two joints."""
        lines = []
        for side in ("right", "left"):
            width = self.si_widths.get(side)
            if width is not None:
                lines.append(width.sentence(self.si_bridge_mm.get(side)))
        return lines

    def landmark_warnings(self) -> List[str]:
        if not self.landmarks:
            return []
        return landmarks_mod.sanity_warnings(self.landmarks)

    def set_landmark_manual(self, name: str, xyz_engine: np.ndarray) -> None:
        """Record a surgeon-dragged landmark position (already converted to
        engine coordinates by the caller) and rebuild the APP frame."""
        self.landmarks[name] = landmarks_mod.Landmark(xyz=np.asarray(xyz_engine, dtype=float), source="manual")
        self._build_frame()

    def _build_frame(self) -> None:
        required = ("asis_right", "asis_left", "pubic_tubercle_right", "pubic_tubercle_left")
        if not all(k in self.landmarks for k in required):
            self.frame = None
            return
        self.frame = app_frame.build_app(
            self.landmarks["asis_right"].xyz,
            self.landmarks["asis_left"].xyz,
            self.landmarks["pubic_tubercle_right"].xyz,
            self.landmarks["pubic_tubercle_left"].xyz,
        )

    # ---- Corridor search -------------------------------------------------

    def _resolve_landmark_xyz(self, name: str, side: str) -> np.ndarray:
        keyed = f"{name}_{side}"
        if keyed in self.landmarks:
            return self.landmarks[keyed].xyz
        if name in self.landmarks:
            return self.landmarks[name].xyz
        raise KeyError(f"landmark {name!r} (side={side!r}) not found; run detect_landmarks() first")

    def _bone_labels_for(self, group: str, side: str) -> tuple:
        if group == "sacrum":
            return (seg_mod.SACRUM,)
        return seg_mod.labels_for_side(group, side)

    def _edt_for_bones(self, label_ids: tuple, si_widths: Optional[Dict[int, float]] = None) -> EngineVolume:
        """Distance field (mm) inside the union of ``label_ids``. With
        ``si_widths`` (mm per hip label), that much of the sacroiliac joint
        between a hip in the union and the sacrum counts as bone (see
        seg_mod.sacroiliac_gap_fill)."""
        ids = tuple(sorted(label_ids))
        widths = {label: mm for label, mm in (si_widths or {}).items() if mm > 0 and label in ids}
        key = (ids, tuple(sorted(widths.items())))
        if key in self._edt_cache:
            return self._edt_cache[key]
        mask = np.isin(self.labels_volume.array, ids)
        hips = tuple(h for h in (seg_mod.HIP_R, seg_mod.HIP_L) if h in ids)
        if widths and seg_mod.SACRUM in ids and hips:
            mask |= seg_mod.sacroiliac_gap_fill(self.labels_volume.array, self.labels_volume.spacing, widths, hips=hips)
        edt = edt_mod.bone_edt_mm(mask, self.labels_volume.spacing)
        vol = EngineVolume(array=edt, spacing=self.labels_volume.spacing, origin=self.labels_volume.origin)
        self._edt_cache[key] = vol
        return vol

    def _traverse_labels(self, corridor_id: str, side: str) -> tuple:
        if side == "midline":
            return (seg_mod.HIP_R, seg_mod.SACRUM, seg_mod.HIP_L)
        ids = set()
        for group in self.corridor_defs[corridor_id]["must_traverse"]:
            ids.update(self._bone_labels_for(group, side))
        return tuple(sorted(ids))

    def clearance_field(self, corridor_id: str, side: str) -> EngineVolume:
        """THE distance field a screw of this corridor and side is checked
        against: by the corridor search, by validate_screw and in the
        exported viewer, so the three can never disagree about the bone."""
        crosses = self.corridor_defs[corridor_id].get("crosses_si_joint")
        return self._edt_for_bones(self._traverse_labels(corridor_id, side), self.si_bridge_by_label() if crosses else None)

    def suggest_corridor(self, corridor_id: str, side: str, margin_mm: Optional[float] = None) -> List["corridor_search.CorridorResult"]:
        """side is 'left' or 'right' for per_side corridors, ignored (pass
        'midline') for the transiliac-transsacral corridor."""
        if self.labels_volume is None or self.frame is None:
            raise RuntimeError("segment() and detect_landmarks() must both succeed first")

        spec = self.corridor_defs[corridor_id]
        if spec.get("crosses_si_joint") and self.si_disrupted is None:
            raise RuntimeError(
                "This corridor crosses the sacroiliac joint, so how much of that joint counts as bone has to be "
                "settled first: say which joint is disrupted (none / right / left / both) in the SI joint row."
            )
        margin_mm = margin_mm if margin_mm is not None else self.screw_library["margin_default_mm"]

        entry_side = spec["entry"].get("reference_side", side)
        exit_side = spec["exit"].get("reference_side", side)
        mirror = -1.0 if (spec["side"] == "per_side" and side == "left") else 1.0

        entry_landmark = self._resolve_landmark_xyz(spec["entry"]["landmark"], entry_side)
        exit_landmark = self._resolve_landmark_xyz(spec["exit"]["landmark"], exit_side)
        entry_offset = np.array(spec["entry"]["offset_mm"], dtype=float) * np.array([mirror, 1.0, 1.0])
        exit_offset = np.array(spec["exit"]["offset_mm"], dtype=float) * np.array([mirror, 1.0, 1.0])
        entry_center = entry_landmark + entry_offset
        exit_center = exit_landmark + exit_offset

        entry_bone_group = spec["entry"]["restrict_to_label"]
        exit_bone_group = spec["exit"]["restrict_to_label"]
        entry_labels = self._bone_labels_for(entry_bone_group, entry_side)
        exit_labels = self._bone_labels_for(exit_bone_group, exit_side)
        entry_mask = np.isin(self.labels_volume.array, entry_labels)
        exit_mask = np.isin(self.labels_volume.array, exit_labels)

        traverse_labels = self._traverse_labels(corridor_id, side)
        edt_vol = self.clearance_field(corridor_id, side)

        valid_vol = None
        gap_mm = max(self.si_bridge_mm.values(), default=0.0) if spec.get("crosses_si_joint") else 0.0
        if gap_mm:
            from scipy.ndimage import binary_dilation

            iterations = max(1, int(round(gap_mm / min(self.labels_volume.spacing))))
            union_mask = np.isin(self.labels_volume.array, traverse_labels)
            dilated = binary_dilation(union_mask, iterations=iterations)
            valid_vol = EngineVolume(array=dilated.astype(np.uint8), spacing=self.labels_volume.spacing, origin=self.labels_volume.origin)

        textbook = spec.get("textbook_direction")
        if side == "left" and spec["side"] == "per_side" and textbook is not None:
            textbook = list(np.array(textbook) * np.array([-1.0, 1.0, 1.0]))

        results = corridor_search.search_corridor(
            entry_mask=entry_mask,
            exit_mask=exit_mask,
            entry_center_xyz=entry_center,
            entry_radius_mm=spec["entry"]["radius_mm"],
            exit_center_xyz=exit_center,
            exit_radius_mm=spec["exit"]["radius_mm"],
            edt_vol=edt_vol,
            valid_vol=valid_vol,
            labels_vol=self.labels_volume,
            margin_mm=margin_mm,
            screw_diameters_mm=[s["diameter_mm"] for s in self.screw_library["screws"]],
            length_range_mm=tuple(spec["length_range_mm"]),
            textbook_direction=textbook,
            tip_rule=self.tip_rule(corridor_id),
            catalog_lengths_mm={s["diameter_mm"]: s["lengths_mm"] for s in self.screw_library["screws"]},
        )
        return results

    # ---- Validation --------------------------------------------------

    def tip_rule(self, corridor_id: str) -> str:
        """The corridor's tip rule, "inside" or "through" (corridors.json
        "tip", DECISIONS.md 1.5)."""
        return self.corridor_defs[corridor_id].get("tip", "inside")

    def catalog_lengths(self, diameter_mm: float) -> Optional[List[float]]:
        """The lengths the screw library has for this diameter (None when the
        diameter is not in it: the screw then runs exactly to its target)."""
        for entry in self.screw_library["screws"]:
            if abs(float(entry["diameter_mm"]) - float(diameter_mm)) < 1e-9:
                return [float(v) for v in entry["lengths_mm"]]
        return None

    def validate_screw(self, corridor_id: str, side: str, entry_xyz, target_xyz, diameter_mm: float, margin_mm: float) -> "validate_mod.Validation":
        """THE check of a screw of this corridor: validate.py's rule with the
        corridor's tip rule and the library's lengths for the diameter,
        against the corridor's own distance field. The exported viewer
        repeats it with the plan's tip_rule and screw_library."""
        return validate_mod.validate_screw(
            entry_xyz, target_xyz, diameter_mm, margin_mm,
            edt_volume=self.clearance_field(corridor_id, side), labels_volume=self.labels_volume,
            tip_rule=self.tip_rule(corridor_id), catalog_lengths_mm=self.catalog_lengths(diameter_mm),
        )

    # ---- Aiming guidance -------------------------------------------------

    def screw_guidance(self, screw, *, with_entry_area: bool = False) -> dict:
        """How to aim a validated screw: its direction in words (in the APP
        frame and in the scan's own axes), the C-arm angles that look
        straight down it, and, when asked for, the room around its entry,
        which costs seconds rather than milliseconds."""
        v = screw.validation or {}
        if v.get("start_xyz") is None or v.get("tip_xyz") is None:
            return {}
        direction = np.asarray(v["tip_xyz"], dtype=float) - np.asarray(v["start_xyz"], dtype=float)
        barrel = guidance_mod.down_the_barrel_view(direction)
        out = {
            "direction_scanner": guidance_mod.describe_direction(direction, app_frame.scanner_frame(), screw.side).sentence,
            "barrel_view": {"rotate_x_deg": barrel.rotate_x_deg, "rotate_z_deg": barrel.rotate_z_deg, "reading": barrel.reading},
        }
        if self.frame is not None:
            out["direction_app"] = guidance_mod.describe_direction(direction, self.frame, screw.side).sentence
        if with_entry_area:
            area = self.entry_area(screw)
            out["entry_area"] = {
                "sentence": area.sentence(),
                "room_mm": area.room_mm,
                "room_is_at_least": area.room_is_at_least,
                "extents_mm": area.extents_mm,
                "step_mm": area.step_mm,
                "half_extent_mm": area.half_extent_mm,
                "n_entries": int(len(area.entry_points_xyz)),
            }
        return out

    def entry_area(self, screw) -> "entry_zone_mod.EntryArea":
        """Where this screw's entry may sit and still pass the same check the
        plan applies. Recomputed whenever the screw or the bones change."""
        key = (tuple(screw.entry_xyz), tuple(screw.target_xyz), screw.diameter_mm, screw.margin_mm, screw.tip_rule, self._labels_version)
        cached = self._entry_area_cache.get(screw.screw_id)
        if cached is None or cached[0] != key:
            self._progress(f"Measuring the room around {screw.screw_id}'s entry...")
            area = entry_zone_mod.safe_entry_area(
                screw.entry_xyz, screw.target_xyz, screw.diameter_mm, screw.margin_mm,
                self.clearance_field(screw.corridor_id, screw.side), self.labels_volume,
                tip_rule=self.tip_rule(screw.corridor_id), catalog_lengths_mm=self.catalog_lengths(screw.diameter_mm),
            )
            self._entry_area_cache[screw.screw_id] = (key, area)
        return self._entry_area_cache[screw.screw_id][1]

    # ---- Skin entry -----------------------------------------------------

    def skin_entry(self, bone_entry_xyz, target_xyz):
        direction_out = np.asarray(bone_entry_xyz, dtype=float) - np.asarray(target_xyz, dtype=float)
        if self._body_mask is None:
            self._body_mask = skin_mod.body_mask_volume(self.hu_volume)
        point, found = skin_mod.skin_entry_auto(self.hu_volume, bone_entry_xyz, direction_out, mask_vol=self._body_mask)
        landmark_xyz = {name: lm.xyz for name, lm in self.landmarks.items()}
        offsets = skin_mod.landmark_offsets(point, landmark_xyz)
        return point, found, offsets

    # ---- DRR -------------------------------------------------------------

    def render_views(self, view_names: List[str]) -> Dict[str, "drr_mod.DrrView"]:
        return drr_mod.render_corridor_views(self.hu_volume, view_names)

    # ---- Plan / export -----------------------------------------------

    def new_plan(self, case_alias: str) -> "plan_mod.Plan":
        frame_dict = plan_mod.frame_to_dict(self.frame) if self.frame else {}
        landmarks_dict = {name: {"xyz": list(lm.xyz), "source": lm.source} for name, lm in self.landmarks.items()}
        self.plan = plan_mod.Plan(
            case_alias=case_alias,
            frame=frame_dict,
            landmarks=landmarks_dict,
            screw_library=self.screw_library,
            si_joint=self.si_joint_record(),
            software={"name": "Corridor Finder", "version": "0.1.0"},
        )
        return self.plan

    def si_joint_record(self) -> dict:
        """What the plan and report say about the joints: what was measured,
        what the surgeon declared, and what was counted as bone."""
        return {
            "disrupted": self.si_disrupted,
            "bridge_mm": dict(self.si_bridge_mm),
            "measured_mm": {side: float(w.measured_mm) for side, w in self.si_widths.items()},
            "covered": {side: round(w.covers(self.si_bridge_mm.get(side, 0.0)), 3) for side, w in self.si_widths.items()},
            "sentences": self.si_sentences(),
        }

    def add_screw_to_plan(self, result, corridor_id: str, side: str, screw_id: str, margin_mm: float, drr_views: Optional[List[str]] = None) -> "plan_mod.ScrewPlan":
        if self.plan is None:
            raise RuntimeError("new_plan() must be called first")
        screw = plan_mod.screw_from_corridor_result(
            result,
            corridor_id=corridor_id,
            side=side,
            screw_id=screw_id,
            margin_mm=margin_mm,
            drr_views=[self._resolve_view(v, side) for v in (drr_views or self.corridor_defs[corridor_id].get("drr_views", []))],
        )
        screw.tip_rule = self.tip_rule(corridor_id)
        self._validate_plan_screw(screw)
        self.plan.screws.append(screw)
        self.plan.log("add_screw", screw_id=screw_id, after=screw.__dict__)
        return screw

    def _resolve_view(self, view: str, side: str) -> str:
        """corridors.json lists side-less view names (e.g. "iliac_oblique")
        for per-side corridors, while the views themselves are defined per
        side; the plan records the concrete one."""
        if view in self.view_defs:
            return view
        if f"{view}_{side}" in self.view_defs:
            return f"{view}_{side}"
        raise KeyError(f"view {view!r} (side {side!r}) is not defined in corridors.json views_deg")

    def _validate_plan_screw(self, screw, derived: bool = True) -> None:
        """Validate a plan screw from its handles and take what validate.py
        decides: its validation and implant length (entry cortex to tip).
        With ``derived``, also the trajectory angles and skin entry, which
        follow the screw as validated (from its cortex crossing toward its
        tip). A check that cannot run marks the screw as a breach, never
        leaves a stale "safe"."""
        try:
            v = self.validate_screw(screw.corridor_id, screw.side, screw.entry_xyz, screw.target_xyz, screw.diameter_mm, screw.margin_mm)
        except ValueError as exc:
            # No bone around the axis at all: reads as a breach everywhere.
            screw.validation = {"breach": True, "min_clearance_mm": -screw.diameter_mm / 2.0, "warnings": [str(exc)], "warning_codes": ["invalid"]}
            return
        screw.validation = v.__dict__
        screw.length_mm = float(v.length_mm)
        # Cheap guidance every time, so a dragged screw never shows the
        # direction it had before; the room around its entry costs seconds,
        # so it is dropped here and measured on request or at export.
        screw.guidance = self.screw_guidance(screw)
        if derived:
            start, tip = np.asarray(v.start_xyz, dtype=float), np.asarray(v.tip_xyz, dtype=float)
            direction = (tip - start) / max(float(np.linalg.norm(tip - start)), 1e-9)
            screw.angles_app = app_frame.screw_angles(direction, self.frame) if self.frame else {}
            screw.angles_scanner = app_frame.screw_angles(direction, app_frame.scanner_frame())
            skin_point, skin_found, offsets = self.skin_entry(start, tip)
            screw.skin_entry_xyz = tuple(float(c) for c in skin_point) if skin_found else None
            # Without a skin entry, skin_point is not on the skin: no offsets.
            screw.skin_offsets = [o.__dict__ for o in offsets] if skin_found else []

    def update_screw_in_plan(self, screw_id: str, entry_xyz=None, target_xyz=None) -> None:
        """Called when a surgeon drags a screw's markups line handle. Angles
        and skin entry are refreshed before export (refresh_derived), not on
        every drag event."""
        for screw in self.plan.screws:
            if screw.screw_id != screw_id:
                continue
            before = dict(entry_xyz=screw.entry_xyz, target_xyz=screw.target_xyz, length_mm=screw.length_mm)
            if entry_xyz is not None:
                screw.entry_xyz = tuple(float(v) for v in entry_xyz)
            if target_xyz is not None:
                screw.target_xyz = tuple(float(v) for v in target_xyz)
            screw.source = "adjusted"
            self._validate_plan_screw(screw, derived=False)
            after = dict(entry_xyz=screw.entry_xyz, target_xyz=screw.target_xyz, length_mm=screw.length_mm)
            self.plan.log("move_handle", screw_id=screw_id, before=before, after=after)
            return
        raise KeyError(f"no screw with id {screw_id!r} in the current plan")

    def revalidate_plan(self) -> None:
        """Re-validate every screw against the current labels (after the
        segmentation was corrected), so the plan never carries a clearance
        computed on bones that no longer apply."""
        for screw in self.plan.screws:
            before = dict(validation=screw.validation, length_mm=screw.length_mm)
            self._validate_plan_screw(screw, derived=False)
            self.plan.log("revalidate", screw_id=screw.screw_id, before=before, after=dict(validation=screw.validation, length_mm=screw.length_mm))

    def refresh_derived(self) -> None:
        """Recompute every screw's validation, angles, skin entry and aiming
        guidance from its current handles; run before anything is exported.
        A validation that changes is logged in the audit trail."""
        for screw in self.plan.screws:
            before = dict(validation=screw.validation, length_mm=screw.length_mm)
            self._validate_plan_screw(screw, derived=True)
            screw.guidance = self.screw_guidance(screw, with_entry_area=True)
            if (screw.length_mm, screw.validation.get("breach"), screw.validation.get("min_clearance_mm")) != (
                before["length_mm"], before["validation"].get("breach"), before["validation"].get("min_clearance_mm")
            ):
                self.plan.log("revalidate", screw_id=screw.screw_id, before=before, after=dict(validation=screw.validation, length_mm=screw.length_mm))

    def export_plan_json(self, path: str) -> None:
        self.plan.si_joint = self.si_joint_record()
        self.refresh_derived()
        plan_mod.save_plan(self.plan, path)

    def export_report(self, path: str, drr_images: Optional[dict] = None) -> None:
        self.plan.si_joint = self.si_joint_record()
        self.refresh_derived()
        report_mod.write_report(self.plan, path, drr_images=drr_images)

    def export_stl(self, path: str) -> None:
        meshes = mesh_mod.extract_label_meshes(self.labels_volume)
        mesh_mod.write_stl_binary_multi(list(meshes.values()), path)

    # Faces per bone mesh in the viewer (display only; the STL keeps full
    # resolution and the viewer's safety check uses the distance fields).
    VIEWER_FACES_PER_MESH = 60000

    def export_viewer_html(self, path: str) -> None:
        meshes = {
            label: mesh_mod.decimate_mesh(m, self.VIEWER_FACES_PER_MESH)
            for label, m in mesh_mod.extract_label_meshes(self.labels_volume).items()
        }
        # Each screw is checked in the viewer against exactly the field
        # validate_screw used for it (with its tip_rule and the plan's
        # screw_library, as validate_screw does).
        self.refresh_derived()
        screw_edts = {s.screw_id: self.clearance_field(s.corridor_id, s.side) for s in self.plan.screws}
        export_viewer_mod.export_viewer(self.plan, meshes, path, screw_edts=screw_edts)


# ==========================================================================
# Widget
# ==========================================================================

CORRIDOR_SIDE_OPTIONS = {
    "per_side": ["right", "left"],
    "midline": ["midline"],
}


class CorridorFinderWidget(ScriptedLoadableModuleWidget, VTKObservationMixin):
    def __init__(self, parent=None):
        ScriptedLoadableModuleWidget.__init__(self, parent)
        VTKObservationMixin.__init__(self)
        self.logic: Optional[CorridorFinderLogic] = None
        self._current_results = []
        self._results_for = None  # (corridor id, side, margin) the suggestions were computed for
        self._screw_line_nodes: Dict[str, "vtkMRMLMarkupsLineNode"] = {}
        self._screw_line_handlers: Dict[str, object] = {}  # to detach observers
        self._screw_model_nodes: Dict[str, "vtkMRMLModelNode"] = {}  # the screws as validated
        self._entry_area_nodes: Dict[str, "vtkMRMLModelNode"] = {}  # where each entry may sit
        self._landmark_fiducial_node = None
        self._bonesSegmentationNode = None
        self._shownScrewId = None  # screw whose clearance the label shows
        self._updating_si = False  # while the panel writes the SI widths itself

    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)
        missing = _missing_requirements()
        if missing or _ENGINE_IMPORT_ERROR is not None:
            self._showDependencyProblem(missing)
            return
        self.logic = CorridorFinderLogic()

        # ScriptedLoadableModuleWidget.setup() has already installed a layout
        # on self.parent and exposed it as self.layout. Creating another
        # QVBoxLayout on the same widget makes Qt warn and silently drop every
        # widget we add, so always append to the existing self.layout.
        layout = self.layout

        # --- Input volume ---
        inputBox = ctk.ctkCollapsibleButton()
        inputBox.text = _("1. Input")
        layout.addWidget(inputBox)
        inputForm = qt.QFormLayout(inputBox)

        self.volumeSelector = slicer.qMRMLNodeComboBox()
        self.volumeSelector.nodeTypes = ["vtkMRMLScalarVolumeNode"]
        self.volumeSelector.selectNodeUponCreation = False
        self.volumeSelector.addEnabled = False
        self.volumeSelector.removeEnabled = False
        self.volumeSelector.noneEnabled = True
        self.volumeSelector.setMRMLScene(slicer.mrmlScene)
        inputForm.addRow(_("Pelvis CT volume:"), self.volumeSelector)

        self.segmentTsCheckbox = qt.QCheckBox(_("Prefer TotalSegmentator (falls back to HU threshold if unavailable)"))
        self.segmentTsCheckbox.checked = True
        inputForm.addRow(self.segmentTsCheckbox)

        self.segmentButton = qt.QPushButton(_("Segment"))
        inputForm.addRow(self.segmentButton)
        self.segmentStatusLabel = qt.QLabel("")
        inputForm.addRow(_("Segmentation:"), self.segmentStatusLabel)

        self.detectLandmarksButton = qt.QPushButton(_("Detect landmarks"))
        self.detectLandmarksButton.enabled = False
        inputForm.addRow(self.detectLandmarksButton)
        self.landmarkWarningsLabel = qt.QLabel("")
        self.landmarkWarningsLabel.setWordWrap(True)
        inputForm.addRow(_("Warnings:"), self.landmarkWarningsLabel)

        # --- Corridors ---
        corridorBox = ctk.ctkCollapsibleButton()
        corridorBox.text = _("2. Corridors")
        layout.addWidget(corridorBox)
        corridorForm = qt.QFormLayout(corridorBox)

        self.siLabel = qt.QLabel(_("measured after Detect landmarks"))
        self.siLabel.setWordWrap(True)
        corridorForm.addRow(_("SI joint:"), self.siLabel)

        self.siDisruptedCombo = qt.QComboBox()
        self.siDisruptedCombo.addItems([_("not set"), "none", "right", "left", "both"])
        self.siDisruptedCombo.setToolTip(
            _("Which sacroiliac joint the injury has opened. A disrupted joint is not a measurement of anything, "
              "so it takes the intact side's width; with both disrupted a fixed 4 mm is used. Corridors that cross "
              "the joint are not suggested until this is set."))
        corridorForm.addRow(_("Disrupted joint:"), self.siDisruptedCombo)

        widthsRow = qt.QWidget()
        widthsLayout = qt.QHBoxLayout(widthsRow)
        widthsLayout.setContentsMargins(0, 0, 0, 0)
        self.siRightSpin = qt.QDoubleSpinBox()
        self.siLeftSpin = qt.QDoubleSpinBox()
        for label, spin in ((_("right"), self.siRightSpin), (_("left"), self.siLeftSpin)):
            spin.setRange(0.0, 10.0)
            spin.setSingleStep(0.1)
            spin.setSuffix(" mm")
            spin.enabled = False
            spin.setToolTip(_("How much of this joint counts as bone. Check it against the axial CT and correct it."))
            widthsLayout.addWidget(qt.QLabel(label))
            widthsLayout.addWidget(spin)
        corridorForm.addRow(_("Counted as bone:"), widthsRow)

        self.corridorCombo = qt.QComboBox()
        for cid, spec in self.logic.corridor_defs.items():
            self.corridorCombo.addItem(spec["label"], cid)
        corridorForm.addRow(_("Corridor:"), self.corridorCombo)

        self.sideCombo = qt.QComboBox()
        corridorForm.addRow(_("Side:"), self.sideCombo)
        self.corridorCombo.currentIndexChanged.connect(self._onCorridorChanged)

        self.marginSpin = qt.QDoubleSpinBox()
        self.marginSpin.setRange(0.0, 10.0)
        self.marginSpin.setSingleStep(0.5)
        self.marginSpin.setValue(self.logic.screw_library["margin_default_mm"])
        corridorForm.addRow(_("Safety margin (mm):"), self.marginSpin)

        self.suggestButton = qt.QPushButton(_("Suggest corridor"))
        self.suggestButton.enabled = False
        corridorForm.addRow(self.suggestButton)

        self.resultsList = qt.QListWidget()
        self.resultsList.setMaximumHeight(100)
        corridorForm.addRow(_("Suggestions:"), self.resultsList)

        self.addScrewButton = qt.QPushButton(_("Add selected suggestion as a screw"))
        self.addScrewButton.enabled = False
        corridorForm.addRow(self.addScrewButton)

        # --- Plan ---
        planBox = ctk.ctkCollapsibleButton()
        planBox.text = _("3. Plan")
        layout.addWidget(planBox)
        planForm = qt.QFormLayout(planBox)

        self.caseAliasEdit = qt.QLineEdit()
        self.caseAliasEdit.setPlaceholderText(_("case alias (no patient identifiers)"))
        planForm.addRow(_("Case alias:"), self.caseAliasEdit)

        self.newPlanButton = qt.QPushButton(_("New plan"))
        planForm.addRow(self.newPlanButton)

        self.screwsList = qt.QListWidget()
        planForm.addRow(_("Screws in plan:"), self.screwsList)

        self.clearanceLabel = qt.QLabel("")
        self.clearanceLabel.setWordWrap(True)
        planForm.addRow(_("Live clearance:"), self.clearanceLabel)

        self.entryAreaButton = qt.QPushButton(_("Show where this entry may sit"))
        self.entryAreaButton.setToolTip(_("Slide this screw sideways and mark every entry that still passes the same check (takes a few seconds)."))
        self.entryAreaButton.enabled = False
        planForm.addRow(self.entryAreaButton)

        # --- Export ---
        exportBox = ctk.ctkCollapsibleButton()
        exportBox.text = _("4. Export")
        layout.addWidget(exportBox)
        exportForm = qt.QFormLayout(exportBox)

        self.exportPlanButton = qt.QPushButton(_("Export plan JSON..."))
        self.exportReportButton = qt.QPushButton(_("Export report HTML..."))
        self.exportStlButton = qt.QPushButton(_("Export STL..."))
        self.exportViewerButton = qt.QPushButton(_("Export interactive viewer HTML..."))
        for b in (self.exportPlanButton, self.exportReportButton, self.exportStlButton, self.exportViewerButton):
            exportForm.addRow(b)

        layout.addStretch(1)

        # --- Signals ---
        self.segmentButton.clicked.connect(self.onSegment)
        self.detectLandmarksButton.clicked.connect(self.onDetectLandmarks)
        self.suggestButton.clicked.connect(self.onSuggest)
        self.addScrewButton.clicked.connect(self.onAddScrew)
        self.newPlanButton.clicked.connect(self.onNewPlan)
        self.entryAreaButton.clicked.connect(self.onShowEntryArea)
        self.screwsList.currentRowChanged.connect(self.onScrewSelected)
        self.sideCombo.currentIndexChanged.connect(self._clearSuggestions)
        self.marginSpin.valueChanged.connect(self._clearSuggestions)
        self.siDisruptedCombo.currentIndexChanged.connect(self.onSiDisruptedChanged)
        self.siRightSpin.valueChanged.connect(lambda value: self.onSiWidthChanged("right", value))
        self.siLeftSpin.valueChanged.connect(lambda value: self.onSiWidthChanged("left", value))
        self.exportPlanButton.clicked.connect(self.onExportPlan)
        self.exportReportButton.clicked.connect(self.onExportReport)
        self.exportStlButton.clicked.connect(self.onExportStl)
        self.exportViewerButton.clicked.connect(self.onExportViewer)

        self._onCorridorChanged()

    def _showDependencyProblem(self, missing: List[str]) -> None:
        """Show why the engine is unusable instead of the normal UI: either
        the packages to install (with a button that installs them) or, for
        any other engine import failure, the full traceback."""
        if missing:
            text = _(
                "Corridor Finder needs Python packages that are not installed "
                "in Slicer's Python:\n\n{packages}\n\n"
                "Install them with the button below, then restart Slicer."
            ).format(packages="\n".join(missing))
        else:
            text = _(
                "Corridor Finder's engine package (corridor_engine) could not "
                "be imported. Details:\n\n"
            ) + _ENGINE_IMPORT_ERROR
        label = qt.QLabel(text)
        label.setWordWrap(True)
        label.setTextInteractionFlags(qt.Qt.TextSelectableByMouse)
        self.layout.addWidget(label)
        if missing:
            self.installDependenciesButton = qt.QPushButton(_("Install required Python packages"))
            self.installDependenciesButton.clicked.connect(lambda: self.onInstallDependencies(missing))
            self.layout.addWidget(self.installDependenciesButton)
        self.layout.addStretch(1)

    def onInstallDependencies(self, requirements: List[str]) -> None:
        if not slicer.util.confirmOkCancelDisplay(
            _("Install these packages into Slicer's Python environment?\n\n{packages}").format(
                packages="\n".join(requirements)),
            _("Corridor Finder"),
        ):
            return
        try:
            slicer.util.pip_install(requirements)
        except subprocess.CalledProcessError:
            # pip_install has already shown pip's log in an error dialog.
            logging.error(traceback.format_exc())
            return
        except Exception as exc:
            logging.error(traceback.format_exc())
            slicer.util.errorDisplay(_("Installing the packages failed:\n\n{error}").format(error=exc))
            return
        if slicer.util.confirmYesNoDisplay(
            _("Packages installed. Slicer must restart to finish loading Corridor Finder. Restart now?"),
            _("Corridor Finder"),
        ):
            slicer.util.restart()

    # ---- UI callbacks ---------------------------------------------------

    def _currentCorridorId(self) -> str:
        """The selected corridor's id.

        NOTE: QComboBox::currentData() is a plain method with a default
        argument, not a Qt property, so PythonQt does NOT expose it as an
        attribute — reading ``combo.currentData`` yields a bound method
        object rather than the data. Go through itemData(currentIndex).
        """
        return self.corridorCombo.itemData(self.corridorCombo.currentIndex)

    def _clearSuggestions(self, *args) -> None:
        """Suggestions belong to the corridor, side and margin they were
        computed for; once any of those changes (or Suggest fails) they are
        dropped, so Add can never file one under a different corridor."""
        self._current_results = []
        self._results_for = None
        self.resultsList.clear()
        self.addScrewButton.enabled = False

    def _onCorridorChanged(self):
        self._clearSuggestions()
        cid = self._currentCorridorId()
        spec = self.logic.corridor_defs[cid]
        self.sideCombo.clear()
        for side in CORRIDOR_SIDE_OPTIONS[spec["side"]]:
            self.sideCombo.addItem(side)

    def onSegment(self):
        volume_node = self.volumeSelector.currentNode()
        if volume_node is None:
            slicer.util.warningDisplay(_("Select a volume first."), windowTitle=_("Corridor Finder"))
            return
        self.logic.progress_callback = self._showProgress
        qt.QApplication.setOverrideCursor(qt.Qt.WaitCursor)
        try:
            self.logic.load_volume(volume_node)
            source = self.logic.segment(prefer_total_segmentator=self.segmentTsCheckbox.checked)
            self._showBonesSegmentation()
        except Exception as exc:
            logging.error(traceback.format_exc())
            slicer.util.errorDisplay(str(exc), windowTitle=_("Corridor Finder"))
            return
        finally:
            qt.QApplication.restoreOverrideCursor()
            self.logic.progress_callback = None

        if source == "fallback":
            text = _("HU-threshold fallback — UNVERIFIED. Review the 'CF bones' "
                     "segmentation and correct it in Segment Editor before continuing.")
            if self.logic.segmentation_note:
                text += "\n" + self.logic.segmentation_note
            self.segmentStatusLabel.setText(text)
            self.segmentStatusLabel.setStyleSheet("color: #b45309; font-weight: bold;")
        else:
            self.segmentStatusLabel.setText(_("TotalSegmentator. Review the 'CF bones' segmentation before continuing."))
            self.segmentStatusLabel.setStyleSheet("color: #15803d;")
        self.detectLandmarksButton.enabled = True

    def _showProgress(self, text: str) -> None:
        self.segmentStatusLabel.setText(text[:200])
        slicer.app.processEvents()

    # Left and right in clearly different colours, so a side mix-up is
    # visible at a glance when reviewing the segmentation.
    _BONE_COLORS = {
        "hip_left": (0.26, 0.52, 0.96),
        "hip_right": (0.95, 0.55, 0.15),
        "sacrum": (0.95, 0.85, 0.35),
        "femur_left": (0.60, 0.78, 1.00),
        "femur_right": (1.00, 0.78, 0.55),
    }

    def _showBonesSegmentation(self) -> None:
        """Show the bone labels the engine plans on as the "CF bones"
        segmentation, so the surgeon can check them and correct them in
        Segment Editor. _syncLabelsFromSegmentation() reads edits back."""
        node = self._bonesSegmentationNode
        if node is None or node.GetScene() is None:
            node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode", "CF bones")
            node.CreateDefaultDisplayNodes()
            self._bonesSegmentationNode = node
        volume_node = self.logic.volume_node
        node.SetReferenceImageGeometryParameterFromVolumeNode(volume_node)
        segmentation = node.GetSegmentation()
        segmentation.RemoveAllSegments()
        labels = engine_array_to_node_array(volume_node, self.logic.labels_volume.array)
        for label, name in seg_mod.LABEL_NAMES.items():
            mask = labels == label
            if not mask.any():
                continue
            segmentation.AddEmptySegment(name, name, self._BONE_COLORS.get(name, (0.8, 0.8, 0.8)))
            slicer.util.updateSegmentBinaryLabelmapFromArray(mask.astype(np.uint8), node, name, volume_node)
        node.CreateClosedSurfaceRepresentation()

    def _syncLabelsFromSegmentation(self) -> bool:
        """Read the "CF bones" segmentation (possibly corrected by the user)
        back into the engine. Segments are matched by ID, so renaming one is
        harmless; a deleted segment clears that bone. When anything changed,
        every screw in the plan is re-validated against the new bones.
        Returns True if the labels changed."""
        node = self._bonesSegmentationNode
        if node is None or node.GetScene() is None or self.logic.labels_volume is None:
            return False
        volume_node = self.logic.volume_node
        labels = np.zeros(slicer.util.arrayFromVolume(volume_node).shape, dtype=np.uint8)
        segmentation = node.GetSegmentation()
        for label, name in seg_mod.LABEL_NAMES.items():
            if segmentation.GetSegment(name) is None:
                continue
            mask = slicer.util.arrayFromSegmentBinaryLabelmap(node, name, volume_node)
            labels[mask > 0] = label
        if not self.logic.set_labels_from_node_array(labels):
            return False
        logging.info("Corridor Finder: bone segmentation was edited; using the edited labels")
        if self.logic.plan is not None and self.logic.plan.screws:
            self.logic.revalidate_plan()
            for screw in self.logic.plan.screws:
                self._updateScrewModel(screw)
            if self._shownScrewId is not None:
                self._refreshClearanceLabel(self._shownScrewId)
        return True

    def onDetectLandmarks(self):
        try:
            self._syncLabelsFromSegmentation()
            self.logic.detect_landmarks()
        except Exception as exc:
            logging.error(traceback.format_exc())
            slicer.util.errorDisplay(str(exc), windowTitle=_("Corridor Finder"))
            return

        self._placeLandmarkFiducials()
        self._updating_si = True
        try:
            self.siDisruptedCombo.setCurrentIndex(0)
        finally:
            self._updating_si = False
        self._syncSiWidths()
        warnings = self.logic.landmark_warnings()
        self.landmarkWarningsLabel.setText("\n".join(warnings) if warnings else _("none"))
        self.suggestButton.enabled = self.logic.frame is not None
        if self.logic.frame is None:
            slicer.util.warningDisplay(
                _("Could not build the anterior pelvic plane frame — ASIS/pubic "
                  "tubercle landmarks were not all detected. Check the "
                  "segmentation and add missing landmarks manually."),
                windowTitle=_("Corridor Finder"),
            )

    def _placeLandmarkFiducials(self):
        """Show detected landmarks as a markups fiducial node so the surgeon
        can see and drag them; dragging updates logic.landmarks (see the
        point-modified observer wired below)."""
        if self._landmark_fiducial_node is None:
            self._landmark_fiducial_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsFiducialNode", "CF_Landmarks")
            self.addObserver(self._landmark_fiducial_node, slicer.vtkMRMLMarkupsNode.PointModifiedEvent, self.onLandmarkMoved)
        node = self._landmark_fiducial_node
        node.RemoveAllControlPoints()
        self._landmark_index_to_name = []
        for name, lm in self.logic.landmarks.items():
            ras = _engine_to_ras(lm.xyz)
            node.AddControlPoint(vtk.vtkVector3d(*ras), name)
            self._landmark_index_to_name.append(name)

    def onLandmarkMoved(self, caller, event):
        node = caller
        for i in range(node.GetNumberOfControlPoints()):
            name = node.GetNthControlPointLabel(i)
            ras = [0.0, 0.0, 0.0]
            node.GetNthControlPointPosition(i, ras)
            engine_xyz = _ras_to_engine(ras)
            if name in self.logic.landmarks and np.allclose(self.logic.landmarks[name].xyz, engine_xyz, atol=1e-6):
                continue
            self.logic.set_landmark_manual(name, engine_xyz)

    def onSiDisruptedChanged(self, index: int) -> None:
        self.logic.set_si_disrupted(None if index == 0 else self.siDisruptedCombo.currentText)
        self._syncSiWidths()
        self._clearSuggestions()

    def onSiWidthChanged(self, side: str, value: float) -> None:
        if self._updating_si or self.logic.si_disrupted is None:
            return
        self.logic.set_si_bridge_mm(side, value)
        self._refreshSiLabel()
        self._clearSuggestions()

    def _syncSiWidths(self) -> None:
        """Show the widths that follow from the declaration, without taking
        that for the surgeon editing them."""
        self._updating_si = True
        try:
            declared = self.logic.si_disrupted is not None
            for side, spin in (("right", self.siRightSpin), ("left", self.siLeftSpin)):
                spin.value = self.logic.si_bridge_mm.get(side, 0.0)
                spin.enabled = declared
        finally:
            self._updating_si = False
        self._refreshSiLabel()

    def _refreshSiLabel(self) -> None:
        lines = self.logic.si_sentences()
        if not lines:
            self.siLabel.setText(_("measured after Detect landmarks"))
            return
        if self.logic.si_disrupted is None:
            suggestion = si_joint_mod.looks_disrupted(self.logic.si_widths)
            prompt = _("say which joint is disrupted before suggesting a sacral corridor")
            lines.append(prompt + (_(" — the {0} one looks disrupted").format(suggestion) if suggestion else ""))
        self.siLabel.setText("\n".join(lines))

    def onSuggest(self):
        cid = self._currentCorridorId()
        side = self.sideCombo.currentText
        margin = self.marginSpin.value
        self._clearSuggestions()
        try:
            if self._syncLabelsFromSegmentation():
                self.landmarkWarningsLabel.setText(
                    _("The segmentation was edited after landmarks were detected; "
                      "run Detect landmarks again if bones near a landmark changed."))
            results = self.logic.suggest_corridor(cid, side, margin_mm=margin)
        except Exception as exc:
            logging.error(traceback.format_exc())
            slicer.util.errorDisplay(str(exc), windowTitle=_("Corridor Finder"))
            return

        self._current_results = results
        self._results_for = (cid, side, margin)
        lo, hi = self.logic.corridor_defs[cid]["length_range_mm"]
        for i, r in enumerate(self._current_results):
            v = r.validation
            if r.screw.fits:
                text = f"#{i+1}: {r.screw.diameter_mm} mm x {r.screw.length_mm:.0f} mm, clearance {v.min_clearance_mm:.1f} mm"
                if v.protrusion_mm is not None:
                    text += f", tip {v.protrusion_mm:.1f} mm past the far cortex"
            elif r.reason == "too_short":
                text = f"#{i+1}: NO SCREW FITS: no axis of {lo:.0f}-{hi:.0f} mm from the cortex joins the entry and target regions"
            elif r.reason == "length":
                text = f"#{i+1}: NO SCREW FITS: {r.length_mm:.0f} mm from the cortex; no catalogue length within {lo:.0f}-{hi:.0f} mm"
            elif v.breach:
                text = f"#{i+1}: NO SCREW FITS: too narrow ({r.checked_diameter_mm} mm screw: clearance {v.min_clearance_mm:.1f} mm, margin {margin:.1f} mm)"
            else:
                text = f"#{i+1}: NO SCREW FITS"
            if v is not None and v.warnings:
                text += " [" + "; ".join(v.warnings) + "]"
            self.resultsList.addItem(text)
        self.addScrewButton.enabled = len(self._current_results) > 0

    def onAddScrew(self):
        if self._results_for is None or not self._current_results:
            slicer.util.warningDisplay(_("Run Suggest corridor first."), windowTitle=_("Corridor Finder"))
            return
        row = self.resultsList.currentRow
        if row < 0 or row >= len(self._current_results):
            row = 0
        result = self._current_results[row]
        if not result.screw.fits:
            slicer.util.warningDisplay(
                _("No screw fits this suggestion (too narrow at the current margin, or too short for the corridor's length range); not adding."),
                windowTitle=_("Corridor Finder"),
            )
            return
        if self.logic.plan is None:
            self.onNewPlan()

        cid, side, margin = self._results_for
        screw_id = f"{cid}_{side}_{len(self.logic.plan.screws) + 1}"
        try:
            self._syncLabelsFromSegmentation()
            screw = self.logic.add_screw_to_plan(result, cid, side, screw_id, margin)
        except Exception as exc:
            logging.error(traceback.format_exc())
            slicer.util.errorDisplay(str(exc), windowTitle=_("Corridor Finder"))
            return

        self._createScrewLineNode(screw)
        self._updateScrewModel(screw)
        self.screwsList.addItem(self._screwListText(screw))
        self.screwsList.setCurrentRow(self.screwsList.count - 1)  # shows its clearance

    def _createScrewLineNode(self, screw) -> None:
        node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsLineNode", f"CF_{screw.screw_id}")
        node.AddControlPoint(vtk.vtkVector3d(*_engine_to_ras(screw.entry_xyz)), "entry")
        node.AddControlPoint(vtk.vtkVector3d(*_engine_to_ras(screw.target_xyz)), "target")
        handler = lambda caller, event, sid=screw.screw_id: self.onScrewHandleMoved(sid)  # noqa: E731
        self._screw_line_nodes[screw.screw_id] = node
        self._screw_line_handlers[screw.screw_id] = handler
        self.addObserver(node, slicer.vtkMRMLMarkupsNode.PointModifiedEvent, handler)

    def onScrewHandleMoved(self, screw_id: str) -> None:
        node = self._screw_line_nodes.get(screw_id)
        if node is None or node.GetNumberOfControlPoints() < 2:
            return
        entry_ras = [0.0, 0.0, 0.0]
        target_ras = [0.0, 0.0, 0.0]
        node.GetNthControlPointPosition(0, entry_ras)
        node.GetNthControlPointPosition(1, target_ras)
        try:
            self.logic.update_screw_in_plan(
                screw_id, entry_xyz=_ras_to_engine(entry_ras), target_xyz=_ras_to_engine(target_ras)
            )
        except Exception:
            logging.error(traceback.format_exc())
            return
        screw = next((s for s in self.logic.plan.screws if s.screw_id == screw_id), None)
        if screw is not None:
            self._updateScrewModel(screw)
        self._refreshClearanceLabel(screw_id)

    def onScrewSelected(self, row: int) -> None:
        if self.logic.plan is None or row < 0 or row >= len(self.logic.plan.screws):
            self.clearanceLabel.setText("")
            self._shownScrewId = None
            self.entryAreaButton.enabled = False
            return
        self._refreshClearanceLabel(self.logic.plan.screws[row].screw_id)

    @staticmethod
    def _screwListText(screw) -> str:
        return f"{screw.screw_id}: {screw.corridor_id} ({screw.side}) {screw.diameter_mm}x{screw.length_mm:.0f}mm"

    def _refreshClearanceLabel(self, screw_id: str) -> None:
        screw = next((s for s in self.logic.plan.screws if s.screw_id == screw_id), None)
        if screw is None:
            return
        self._shownScrewId = screw_id
        self.entryAreaButton.enabled = True
        row = next((i for i, s in enumerate(self.logic.plan.screws) if s.screw_id == screw_id), None)
        if row is not None and row < self.screwsList.count:
            self.screwsList.item(row).setText(self._screwListText(screw))  # the length follows the handles
        v = screw.validation
        breach = v.get("breach")
        warnings = v.get("warnings") or []
        # Shows validate.py's verdict; the rule itself lives only there.
        text = f"{screw.screw_id}: clearance {v.get('min_clearance_mm', float('nan')):.1f} mm, margin {screw.margin_mm:.1f} mm"
        if breach:
            text += " — BREACH"
        text += f"\n{screw.diameter_mm} x {screw.length_mm:.0f} mm from the entry cortex"
        if v.get("protrusion_mm") is not None:
            text += f", tip {v['protrusion_mm']:.1f} mm past the far cortex"
        guidance = screw.guidance or {}
        if guidance.get("direction_app") or guidance.get("direction_scanner"):
            text += f"\nAim: {guidance.get('direction_app') or guidance['direction_scanner']}"
        if (guidance.get("barrel_view") or {}).get("reading"):
            text += f"\nC-arm down the screw: {guidance['barrel_view']['reading']}"
        if (guidance.get("entry_area") or {}).get("sentence"):
            text += f"\nEntry room: {guidance['entry_area']['sentence']}"
        for warning in warnings:
            text += f"\nWarning: {warning}"
        self.clearanceLabel.setText(text)
        if breach:
            style = "color: #b91c1c; font-weight: bold;"
        elif warnings:
            style = "color: #b45309; font-weight: bold;"
        else:
            style = "color: #15803d;"
        self.clearanceLabel.setStyleSheet(style)

    def onShowEntryArea(self) -> None:
        """Measure the room around the selected screw's entry and mark every
        entry that still passes, on the bone."""
        screw = next((s for s in self.logic.plan.screws if s.screw_id == self._shownScrewId), None)
        if screw is None:
            return
        qt.QApplication.setOverrideCursor(qt.Qt.WaitCursor)
        try:
            area = self.logic.entry_area(screw)
            screw.guidance = self.logic.screw_guidance(screw, with_entry_area=True)
        except Exception as exc:
            logging.error(traceback.format_exc())
            slicer.util.errorDisplay(str(exc), windowTitle=_("Corridor Finder"))
            return
        finally:
            qt.QApplication.restoreOverrideCursor()
        self._showEntryAreaPoints(screw.screw_id, area.entry_points_xyz)
        self._refreshClearanceLabel(screw.screw_id)

    def _showEntryAreaPoints(self, screw_id: str, points) -> None:
        """Show the safe entries as a patch of points on the bone surface."""
        node = self._entry_area_nodes.get(screw_id)
        vtk_points = vtk.vtkPoints()
        for p in points:
            vtk_points.InsertNextPoint(*_engine_to_ras(p))
        poly = vtk.vtkPolyData()
        poly.SetPoints(vtk_points)
        vertices = vtk.vtkVertexGlyphFilter()
        vertices.SetInputData(poly)
        vertices.Update()
        if node is None or node.GetScene() is None:
            node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", f"CF_{screw_id}_entry_area")
            node.CreateDefaultDisplayNodes()
            node.GetDisplayNode().SetColor(0.13, 0.77, 0.37)
            node.GetDisplayNode().SetPointSize(6)
            node.GetDisplayNode().SetRepresentation(1)  # points, not a surface
            node.GetDisplayNode().SetVisibility2D(True)
            self._entry_area_nodes[screw_id] = node
        node.SetAndObservePolyData(vertices.GetOutput())
        node.SetDisplayVisibility(vtk_points.GetNumberOfPoints() > 0)

    def _updateScrewModel(self, screw) -> None:
        """Show the screw as validate.py checked it: from its entry-cortex
        crossing to its tip, at its diameter; red in breach, amber with a
        warning, green otherwise. The line's handles only steer it."""
        v = screw.validation or {}
        start, tip = v.get("start_xyz"), v.get("tip_xyz")
        node = self._screw_model_nodes.get(screw.screw_id)
        if start is None or tip is None:
            if node is not None and node.GetScene() is not None:
                node.SetDisplayVisibility(False)
            return
        line = vtk.vtkLineSource()
        line.SetPoint1(*_engine_to_ras(start))
        line.SetPoint2(*_engine_to_ras(tip))
        tube = vtk.vtkTubeFilter()
        tube.SetInputConnection(line.GetOutputPort())
        tube.SetRadius(screw.diameter_mm / 2.0)
        tube.SetNumberOfSides(24)
        tube.CappingOn()
        tube.Update()
        if node is None or node.GetScene() is None:
            node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLModelNode", f"CF_{screw.screw_id}_screw")
            node.CreateDefaultDisplayNodes()
            self._screw_model_nodes[screw.screw_id] = node
        node.SetAndObservePolyData(tube.GetOutput())
        display = node.GetDisplayNode()
        if v.get("breach"):
            display.SetColor(0.85, 0.15, 0.15)
        elif v.get("warnings"):
            display.SetColor(0.96, 0.62, 0.04)
        else:
            display.SetColor(0.13, 0.77, 0.37)
        display.SetVisibility2D(True)
        node.SetDisplayVisibility(True)

    def onNewPlan(self):
        alias = self.caseAliasEdit.text or "case"
        # Remove the previous plan's screw lines. Screw ids restart in a new
        # plan, so a leftover line (still observed) could otherwise move the
        # new plan's screw of the same id when dragged.
        for screw_id, node in self._screw_line_nodes.items():
            self.removeObserver(node, slicer.vtkMRMLMarkupsNode.PointModifiedEvent, self._screw_line_handlers[screw_id])
            if node.GetScene() is not None:
                slicer.mrmlScene.RemoveNode(node)
        self._screw_line_nodes = {}
        self._screw_line_handlers = {}
        for node in list(self._screw_model_nodes.values()) + list(self._entry_area_nodes.values()):
            if node.GetScene() is not None:
                slicer.mrmlScene.RemoveNode(node)
        self._screw_model_nodes = {}
        self._entry_area_nodes = {}
        self.logic.new_plan(alias)
        self.screwsList.clear()

    def _promptSavePath(self, title: str, filter_str: str) -> Optional[str]:
        path = qt.QFileDialog.getSaveFileName(self.parent, title, "", filter_str)
        return path if path else None

    def onExportPlan(self):
        if self.logic.plan is None:
            return
        path = self._promptSavePath(_("Export plan JSON"), "JSON (*.json)")
        if not path:
            return
        try:
            self._syncLabelsFromSegmentation()
            self.logic.export_plan_json(path)
        except Exception as exc:
            logging.error(traceback.format_exc())
            slicer.util.errorDisplay(str(exc), windowTitle=_("Corridor Finder"))

    def onExportReport(self):
        if self.logic.plan is None:
            return
        path = self._promptSavePath(_("Export report"), "HTML (*.html)")
        if not path:
            return
        try:
            self._syncLabelsFromSegmentation()
            drr_images = self._renderDrrImagesForPlan()
            self.logic.export_report(path, drr_images=drr_images)
        except Exception as exc:
            logging.error(traceback.format_exc())
            slicer.util.errorDisplay(str(exc), windowTitle=_("Corridor Finder"))

    def _renderDrrImagesForPlan(self) -> dict:
        import io

        from PIL import Image

        def png(overlay) -> bytes:
            buf = io.BytesIO()
            Image.fromarray(overlay).save(buf, format="PNG")
            return buf.getvalue()

        all_views = sorted({v for s in self.logic.plan.screws for v in s.drr_views})
        rendered = self.logic.render_views(all_views) if all_views else {}
        images = {}
        for screw in self.logic.plan.screws:
            per_screw = {}
            # The screw as validated: entry cortex to tip.
            v = screw.validation or {}
            start = v.get("start_xyz") or screw.entry_xyz
            tip = v.get("tip_xyz") or screw.target_xyz
            for view_name in screw.drr_views:
                view = rendered.get(view_name)
                if view is not None:
                    per_screw[view_name] = png(drr_mod.draw_screw(view, start, tip))
            # One more view per screw: straight down it, where the screw is a
            # dot inside the area its entry may move in.
            barrel = (screw.guidance or {}).get("barrel_view")
            if barrel is not None:
                view = drr_mod.render_view(self.logic.hu_volume, barrel["rotate_x_deg"], barrel["rotate_z_deg"], name="down the screw")
                overlay = drr_mod.draw_points(view, self.logic.entry_area(screw).entry_points_xyz)
                overlay = drr_mod.draw_screw(view, start, tip, rgb=overlay)
                per_screw["down the screw"] = png(drr_mod.crop_around(view, overlay, start))
            images[screw.screw_id] = per_screw
        return images

    def onExportStl(self):
        if self.logic.labels_volume is None:
            return
        path = self._promptSavePath(_("Export STL"), "STL (*.stl)")
        if not path:
            return
        try:
            self._syncLabelsFromSegmentation()
            self.logic.export_stl(path)
        except Exception as exc:
            logging.error(traceback.format_exc())
            slicer.util.errorDisplay(str(exc), windowTitle=_("Corridor Finder"))

    def onExportViewer(self):
        if self.logic.plan is None:
            return
        path = self._promptSavePath(_("Export interactive viewer"), "HTML (*.html)")
        if not path:
            return
        try:
            self._syncLabelsFromSegmentation()
            self.logic.export_viewer_html(path)
        except Exception as exc:
            logging.error(traceback.format_exc())
            slicer.util.errorDisplay(str(exc), windowTitle=_("Corridor Finder"))

    def cleanup(self):
        self.removeObservers()


# ==========================================================================
# Test
# ==========================================================================

class CorridorFinderTest(ScriptedLoadableModuleTest):
    """Self-test of the Slicer-specific conversion boundary, which cannot be
    tested outside Slicer. The geometry itself is covered by
    corridor-finder/tests/python (run outside Slicer with pytest).
    """

    def setUp(self):
        slicer.mrmlScene.Clear()

    def runTest(self):
        self.setUp()
        self.test_volume_conversion_matches_slicer_geometry()
        self.test_unsupported_volume_geometry_is_rejected()

    def test_volume_conversion_matches_slicer_geometry(self):
        """For all 8 axis-aligned orientations, with anisotropic non-unit
        spacing, a marked voxel must come out of the engine Volume at exactly
        the RAS point where Slicer itself places it, with positive spacing.
        The expected position comes from Slicer's IJK-to-RAS matrix, not
        from the conversion code, so a mirrored or shifted conversion fails.
        (Before this test existed, every realistic CT was rejected and the
        one orientation accepted was mirrored left-right.)"""
        import itertools

        spacing = (0.7, 0.8, 1.25)
        origin = (12.5, -30.0, 101.0)
        marked_ijk = (5, 1, 3)
        for signs in itertools.product((1.0, -1.0), repeat=3):
            ijk_to_ras = np.eye(4)
            for a in range(3):
                ijk_to_ras[a, a] = signs[a] * spacing[a]
                ijk_to_ras[a, 3] = origin[a]
            array = np.zeros((5, 6, 7), dtype=np.int16)  # (k, j, i)
            array[marked_ijk[2], marked_ijk[1], marked_ijk[0]] = 1000
            node = slicer.util.addVolumeFromArray(array, ijkToRAS=ijk_to_ras)
            expected_ras = (ijk_to_ras @ np.array([*marked_ijk, 1.0]))[:3]
            try:
                vol = volume_node_to_engine_volume(node)
                points = vol.mask_voxel_centers_world(vol.array > 0)
                if points.shape[0] != 1 or not np.allclose(_engine_to_ras(points[0]), expected_ras, atol=1e-6):
                    raise AssertionError(
                        f"direction signs {signs}: marked voxel at engine {points.tolist()}, "
                        f"but Slicer places it at RAS {expected_ras.tolist()}"
                    )
                if not np.allclose(vol.spacing, spacing):
                    raise AssertionError(f"direction signs {signs}: engine spacing {vol.spacing}, expected {spacing}")
                # A second array on the node's voxel grid (as TotalSegmentator's
                # labelmap arrives) must be reordered exactly like the volume.
                labels = node_array_to_engine_array(node, (array > 0).astype(np.uint8))
                if not np.array_equal(labels > 0, vol.array > 0):
                    raise AssertionError(f"direction signs {signs}: label array reordered differently from the volume")
            finally:
                slicer.mrmlScene.RemoveNode(node)
        self.delayDisplay("Volume conversion matches Slicer's geometry for all 8 orientations: PASS")

    def test_unsupported_volume_geometry_is_rejected(self):
        """Oblique (gantry tilt), axis-permuted (sagittal) and transformed
        volumes must raise rather than be silently mis-mapped."""
        array = np.zeros((5, 6, 7), dtype=np.int16)
        c, s = np.cos(np.radians(5.0)), np.sin(np.radians(5.0))
        cases = {
            "oblique (5 degree tilt)": np.array([[1, 0, 0, 0], [0, c, -s, 0], [0, s, c, 0], [0, 0, 0, 1]], dtype=float),
            "axis-permuted (sagittal)": np.array([[0, 0, 1, 0], [1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 0, 1]], dtype=float),
        }
        for name, ijk_to_ras in cases.items():
            node = slicer.util.addVolumeFromArray(array, ijkToRAS=ijk_to_ras)
            try:
                volume_node_to_engine_volume(node)
            except ValueError:
                pass
            else:
                raise AssertionError(f"{name} volume was accepted; it must be rejected")
            finally:
                slicer.mrmlScene.RemoveNode(node)

        node = slicer.util.addVolumeFromArray(array)
        transform = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLLinearTransformNode")
        node.SetAndObserveTransformNodeID(transform.GetID())
        try:
            volume_node_to_engine_volume(node)
        except ValueError:
            pass
        else:
            raise AssertionError("volume under a transform was accepted; it must be rejected")
        finally:
            slicer.mrmlScene.RemoveNode(node)
            slicer.mrmlScene.RemoveNode(transform)
        self.delayDisplay("Oblique, axis-permuted and transformed volumes are rejected: PASS")
