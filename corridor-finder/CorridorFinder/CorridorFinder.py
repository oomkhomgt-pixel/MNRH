"""Corridor Finder — a 3D Slicer scripted module for percutaneous screw
corridor planning in the pelvis/acetabulum.

This is the ONLY file in the project that imports slicer/vtk/qt/ctk. All
actual geometry (segmentation, corridor search, validation, landmarks,
DRR, plan/report/mesh/viewer export) lives in the pure-Python
``corridor_engine`` package next to this extension, which is unit tested
headlessly outside Slicer. This file's job is narrow: convert Slicer's
MRML scene (volumes, segmentations, markups) to and from plain numpy
arrays/``corridor_engine.volume.Volume`` objects, and drive the UI.

NOTE ON TESTING: this file has been written against the documented Slicer
scripted-module API but has not been run inside Slicer (this development
environment does not have Slicer installed). Expect to debug real
integration issues here — that is expected and is exactly what this
module needs a human at a Slicer workstation for. Known likely rough
edges are called out in comments below (search "KNOWN LIMITATION").

Coordinate conventions
-----------------------
Slicer's MRML scene uses RAS (Right+, Anterior+, Superior+) world
coordinates. ``corridor_engine`` uses a LAS-like convention documented in
its modules: x = patient Left+, y = Anterior+, z = Superior/cephalad+.
The two agree on y and z and are negated on x. All conversion between the
two happens in this file via ``_ras_to_engine`` / ``_engine_to_ras``;
nothing outside this file should ever see a raw RAS coordinate.

KNOWN LIMITATION: volume-to-Volume conversion below assumes the volume's
IJK-to-RAS direction matrix is diagonal (axis-aligned acquisition, i.e.
no gantry tilt / oblique reformat). It raises a clear error if that's not
the case rather than silently producing wrong geometry; supporting
oblique volumes is future work.
"""

import json
import logging
import os
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


# ==========================================================================
# Coordinate conversion helpers (the one place RAS<->engine-LAS happens)
# ==========================================================================

def _ras_to_engine(xyz_ras) -> np.ndarray:
    """RAS (Right+, Anterior+, Superior+) -> engine LAS (Left+, Anterior+,
    Superior+): negate x, keep y and z."""
    x, y, z = xyz_ras
    return np.array([-float(x), float(y), float(z)], dtype=float)


def _engine_to_ras(xyz_engine) -> Tuple[float, float, float]:
    x, y, z = xyz_engine
    return (-float(x), float(y), float(z))


def _check_axis_aligned(direction_matrix: vtk.vtkMatrix4x4) -> None:
    """Raise a clear error if the volume's IJK->RAS direction is not a
    diagonal +/-1 matrix (i.e. the volume is not axis-aligned)."""
    for r in range(3):
        for c in range(3):
            v = direction_matrix.GetElement(r, c)
            if r == c:
                if abs(abs(v) - 1.0) > 1e-3:
                    raise ValueError(
                        "Corridor Finder requires an axis-aligned volume "
                        "(no gantry tilt / oblique reformat). Resample the "
                        "volume to axis-aligned RAS first."
                    )
            else:
                if abs(v) > 1e-3:
                    raise ValueError(
                        "Corridor Finder requires an axis-aligned volume "
                        "(no gantry tilt / oblique reformat). Resample the "
                        "volume to axis-aligned RAS first."
                    )


def volume_node_to_engine_volume(volume_node) -> "EngineVolume":
    """Convert a vtkMRMLScalarVolumeNode (HU or label map) to an
    ``corridor_engine.volume.Volume`` in engine (LAS) world coordinates.
    """
    ijk_to_ras = vtk.vtkMatrix4x4()
    volume_node.GetIJKToRASMatrix(ijk_to_ras)
    _check_axis_aligned(ijk_to_ras)

    array_kji = slicer.util.arrayFromVolume(volume_node)  # shape (nk, nj, ni) = (z, y, x) in IJK order
    spacing_ijk = volume_node.GetSpacing()  # (sp_i, sp_j, sp_k)
    origin_ras = [ijk_to_ras.GetElement(r, 3) for r in range(3)]

    # Diagonal signs tell us whether increasing I/J/K increases or decreases
    # each RAS axis; combined with the known spacing this gives the engine
    # (x=Left+, y=Anterior+, z=Superior+) spacing directly, since engine x
    # is simply -RAS_x.
    sign_i = 1.0 if ijk_to_ras.GetElement(0, 0) >= 0 else -1.0
    sign_j = 1.0 if ijk_to_ras.GetElement(1, 1) >= 0 else -1.0
    sign_k = 1.0 if ijk_to_ras.GetElement(2, 2) >= 0 else -1.0

    # engine spacing must be positive; if increasing IJK decreases RAS along
    # that axis we'd need to flip the array too. For v1 (axis-aligned,
    # typically identity-sign volumes from a standard CT import) we assume
    # sign_i/j/k are all +1 and raise otherwise rather than silently
    # mis-orienting the volume.
    if sign_i < 0 or sign_j < 0 or sign_k < 0:
        raise ValueError(
            "Volume has a flipped IJK->RAS direction (sign_i=%.0f sign_j=%.0f "
            "sign_k=%.0f). Corridor Finder v1 only supports the standard "
            "orientation; use Volumes > Convert to reorient the volume first."
            % (sign_i, sign_j, sign_k)
        )

    engine_origin = _ras_to_engine(origin_ras)
    # spacing along engine x is the same magnitude as RAS x spacing (only the
    # sign of the axis, not its scale, differs between RAS and engine LAS).
    engine_spacing = (float(spacing_ijk[0]), float(spacing_ijk[1]), float(spacing_ijk[2]))

    return EngineVolume(array=np.asarray(array_kji), spacing=engine_spacing, origin=tuple(engine_origin))


def labelmap_node_to_engine_volume(labelmap_node) -> "EngineVolume":
    return volume_node_to_engine_volume(labelmap_node)


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
        with open(os.path.join(_PROJECT_ROOT, "corridors.json"), "r") as f:
            self.corridor_defs = {c["id"]: c for c in json.load(f)["corridors"]}
        with open(os.path.join(_PROJECT_ROOT, "screws.json"), "r") as f:
            self.screw_library = json.load(f)

        self.hu_volume: Optional[EngineVolume] = None
        self.labels_volume: Optional[EngineVolume] = None
        self.segmentation_source: str = ""  # "totalsegmentator" | "fallback" | ""
        self.landmarks: Dict[str, "landmarks_mod.Landmark"] = {}
        self.frame = None
        self.plan: Optional["plan_mod.Plan"] = None
        self._edt_cache: Dict[tuple, EngineVolume] = {}

    # ---- Segmentation --------------------------------------------------

    def load_volume(self, volume_node) -> None:
        self.hu_volume = volume_node_to_engine_volume(volume_node)
        self.labels_volume = None
        self.landmarks = {}
        self.frame = None
        self._edt_cache = {}

    def segment(self, prefer_total_segmentator: bool = True) -> str:
        """Populate self.labels_volume. Returns "totalsegmentator" or
        "fallback" to say which path was used, so the UI can warn the user
        when the fallback (unverified) path was taken."""
        if self.hu_volume is None:
            raise RuntimeError("load_volume() must be called first")

        if prefer_total_segmentator:
            try:
                labels_array = self._run_total_segmentator()
                self.labels_volume = EngineVolume(
                    array=labels_array, spacing=self.hu_volume.spacing, origin=self.hu_volume.origin
                )
                self.segmentation_source = "totalsegmentator"
                return self.segmentation_source
            except Exception:
                logging.warning("TotalSegmentator unavailable or failed, falling back to HU threshold:\n%s", traceback.format_exc())

        labels_array = seg_mod.split_pelvis_labels(self.hu_volume.array, self.hu_volume.spacing)
        self.labels_volume = EngineVolume(array=labels_array, spacing=self.hu_volume.spacing, origin=self.hu_volume.origin)
        self.segmentation_source = "fallback"
        return self.segmentation_source

    def _run_total_segmentator(self) -> np.ndarray:
        """Run the SlicerTotalSegmentator extension (if installed) and remap
        its label names to corridor_engine.segmentation's label ids.

        KNOWN LIMITATION: this assumes the SlicerTotalSegmentator extension
        is installed and its Python logic class is importable as below;
        the exact class name/entry point should be double-checked against
        the installed extension version and adjusted here if it differs.
        """
        try:
            import TotalSegmentator  # noqa: F401  (provided by the extension, if installed)
        except ImportError as exc:
            raise RuntimeError("SlicerTotalSegmentator extension is not installed") from exc

        ts_logic = slicer.modules.totalsegmentator.widgetRepresentation().self().logic
        # NOTE: the exact call signature of TotalSegmentator's logic varies by
        # version; this targets the "total" task producing per-structure
        # segments on the currently loaded volume. Adjust the call below to
        # match the installed version if this raises.
        temp_seg_node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLSegmentationNode", "CorridorFinder_TS_temp")
        ts_logic.process(
            inputVolume=self._current_volume_node,
            outputSegmentation=temp_seg_node,
            fast=True,
            task="total",
        )

        name_map = {
            "hip_left": seg_mod.HIP_L,
            "hip_right": seg_mod.HIP_R,
            "sacrum": seg_mod.SACRUM,
            "femur_left": seg_mod.FEMUR_L,
            "femur_right": seg_mod.FEMUR_R,
        }
        labels_array = np.zeros(self.hu_volume.array.shape, dtype=np.uint8)
        seg = temp_seg_node.GetSegmentation()
        for seg_id_index in range(seg.GetNumberOfSegments()):
            segment_id = seg.GetNthSegmentID(seg_id_index)
            segment_name = seg.GetSegment(segment_id).GetName().lower()
            target_label = name_map.get(segment_name)
            if target_label is None:
                continue
            seg_array = slicer.util.arrayFromSegmentBinaryLabelmap(temp_seg_node, segment_id, self._current_volume_node)
            labels_array[seg_array > 0] = target_label

        slicer.mrmlScene.RemoveNode(temp_seg_node)
        return labels_array

    # ---- Landmarks / frame ---------------------------------------------

    def detect_landmarks(self) -> Dict[str, "landmarks_mod.Landmark"]:
        if self.labels_volume is None:
            raise RuntimeError("segment() must be called first")
        self.landmarks = landmarks_mod.detect_landmarks(self.labels_volume)
        self._build_frame()
        return self.landmarks

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

    def _edt_for_bones(self, label_ids: tuple) -> EngineVolume:
        key = tuple(sorted(label_ids))
        if key in self._edt_cache:
            return self._edt_cache[key]
        mask = np.isin(self.labels_volume.array, key)
        edt = edt_mod.bone_edt_mm(mask, self.labels_volume.spacing)
        vol = EngineVolume(array=edt, spacing=self.labels_volume.spacing, origin=self.labels_volume.origin)
        self._edt_cache[key] = vol
        return vol

    def suggest_corridor(self, corridor_id: str, side: str, margin_mm: Optional[float] = None) -> List["corridor_search.CorridorResult"]:
        """side is 'left' or 'right' for per_side corridors, ignored (pass
        'midline') for the transiliac-transsacral corridor."""
        if self.labels_volume is None or self.frame is None:
            raise RuntimeError("segment() and detect_landmarks() must both succeed first")

        spec = self.corridor_defs[corridor_id]
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

        must_traverse_groups = spec["must_traverse"]
        if side == "midline":
            traverse_labels = (seg_mod.HIP_R, seg_mod.SACRUM, seg_mod.HIP_L)
        else:
            traverse_ids = set()
            for group in must_traverse_groups:
                traverse_ids.update(self._bone_labels_for(group, side))
            traverse_labels = tuple(sorted(traverse_ids))
        edt_vol = self._edt_for_bones(traverse_labels)

        valid_vol = None
        gap_mm = spec.get("sacral_gap_allowance_mm")
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
        )
        return results

    # ---- Validation --------------------------------------------------

    def validate_screw(self, corridor_id: str, side: str, entry_xyz, target_xyz, diameter_mm: float, margin_mm: float) -> "validate_mod.Validation":
        spec = self.corridor_defs[corridor_id]
        if side == "midline":
            traverse_labels = (seg_mod.HIP_R, seg_mod.SACRUM, seg_mod.HIP_L)
        else:
            traverse_ids = set()
            for group in spec["must_traverse"]:
                traverse_ids.update(self._bone_labels_for(group, side))
            traverse_labels = tuple(sorted(traverse_ids))
        edt_vol = self._edt_for_bones(traverse_labels)
        return validate_mod.validate_screw(
            entry_xyz, target_xyz, diameter_mm, margin_mm, edt_volume=edt_vol, labels_volume=self.labels_volume
        )

    # ---- Skin entry -----------------------------------------------------

    def skin_entry(self, bone_entry_xyz, target_xyz):
        direction_out = np.asarray(bone_entry_xyz, dtype=float) - np.asarray(target_xyz, dtype=float)
        point, found = skin_mod.skin_entry_auto(self.hu_volume, bone_entry_xyz, direction_out)
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
            software={"name": "Corridor Finder", "version": "0.1.0"},
        )
        return self.plan

    def add_screw_to_plan(self, result, corridor_id: str, side: str, screw_id: str, margin_mm: float, drr_views: Optional[List[str]] = None) -> "plan_mod.ScrewPlan":
        if self.plan is None:
            raise RuntimeError("new_plan() must be called first")
        validation = self.validate_screw(corridor_id, side, result.entry_xyz, result.target_xyz, result.screw.diameter_mm, margin_mm)
        skin_point, skin_found, offsets = self.skin_entry(result.entry_xyz, result.target_xyz)
        angles_app = app_frame.screw_angles(np.asarray(result.direction), self.frame) if self.frame else {}
        angles_scanner = app_frame.screw_angles(np.asarray(result.direction), app_frame.scanner_frame())

        screw = plan_mod.screw_from_corridor_result(
            result,
            corridor_id=corridor_id,
            side=side,
            screw_id=screw_id,
            margin_mm=margin_mm,
            skin_entry_xyz=tuple(skin_point) if skin_found else None,
            skin_offsets=[o.__dict__ for o in offsets],
            angles_app=angles_app,
            angles_scanner=angles_scanner,
            validation=validation.__dict__,
            drr_views=drr_views or self.corridor_defs[corridor_id].get("drr_views", []),
        )
        self.plan.screws.append(screw)
        self.plan.log("add_screw", screw_id=screw_id, after=screw.__dict__)
        return screw

    def update_screw_in_plan(self, screw_id: str, entry_xyz=None, target_xyz=None) -> None:
        """Called when a surgeon drags a screw's markups line handle."""
        for screw in self.plan.screws:
            if screw.screw_id != screw_id:
                continue
            before = dict(entry_xyz=screw.entry_xyz, target_xyz=screw.target_xyz)
            if entry_xyz is not None:
                screw.entry_xyz = tuple(float(v) for v in entry_xyz)
            if target_xyz is not None:
                screw.target_xyz = tuple(float(v) for v in target_xyz)
            screw.source = "adjusted"
            validation = self.validate_screw(screw.corridor_id, screw.side, screw.entry_xyz, screw.target_xyz, screw.diameter_mm, screw.margin_mm)
            screw.validation = validation.__dict__
            after = dict(entry_xyz=screw.entry_xyz, target_xyz=screw.target_xyz)
            self.plan.log("move_handle", screw_id=screw_id, before=before, after=after)
            return
        raise KeyError(f"no screw with id {screw_id!r} in the current plan")

    def export_plan_json(self, path: str) -> None:
        plan_mod.save_plan(self.plan, path)

    def export_report(self, path: str, drr_images: Optional[dict] = None) -> None:
        report_mod.write_report(self.plan, path, drr_images=drr_images)

    def export_stl(self, path: str) -> None:
        meshes = mesh_mod.extract_label_meshes(self.labels_volume)
        mesh_mod.write_stl_binary_multi(list(meshes.values()), path)

    def export_viewer_html(self, path: str) -> None:
        meshes = mesh_mod.extract_label_meshes(self.labels_volume)
        coarse = edt_mod.coarse_edt_uint8(self._edt_for_bones(tuple(seg_mod.LABEL_NAMES.keys())).array)
        export_viewer_mod.export_viewer(
            self.plan,
            meshes,
            path,
            edt_uint8=coarse,
            edt_spacing=self.labels_volume.spacing,
            edt_origin=self.labels_volume.origin,
        )


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
        self._screw_line_nodes: Dict[str, "vtkMRMLMarkupsLineNode"] = {}
        self._landmark_fiducial_node = None

    def setup(self):
        ScriptedLoadableModuleWidget.setup(self)
        try:
            self.logic = CorridorFinderLogic()
        except ImportError as exc:
            self._showEngineImportError(str(exc))
            return

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
        planForm.addRow(_("Live clearance:"), self.clearanceLabel)

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
        self.screwsList.currentRowChanged.connect(self.onScrewSelected)
        self.exportPlanButton.clicked.connect(self.onExportPlan)
        self.exportReportButton.clicked.connect(self.onExportReport)
        self.exportStlButton.clicked.connect(self.onExportStl)
        self.exportViewerButton.clicked.connect(self.onExportViewer)

        self._onCorridorChanged()

    def _showEngineImportError(self, message: str) -> None:
        label = qt.QLabel(
            _("Corridor Finder's engine package (corridor_engine) could not be "
              "imported. Check that numpy/scipy/scikit-image/jsonschema are "
              "installed for Slicer's Python (Edit > Application Settings > "
              "Python, or use slicer.util.pip_install). Details:\n\n") + message
        )
        label.setWordWrap(True)
        self.layout.addWidget(label)

    # ---- UI callbacks ---------------------------------------------------

    def _currentCorridorId(self) -> str:
        """The selected corridor's id.

        NOTE: QComboBox::currentData() is a plain method with a default
        argument, not a Qt property, so PythonQt does NOT expose it as an
        attribute — reading ``combo.currentData`` yields a bound method
        object rather than the data. Go through itemData(currentIndex).
        """
        return self.corridorCombo.itemData(self.corridorCombo.currentIndex)

    def _onCorridorChanged(self):
        cid = self._currentCorridorId()
        spec = self.logic.corridor_defs[cid]
        self.sideCombo.clear()
        for side in CORRIDOR_SIDE_OPTIONS[spec["side"]]:
            self.sideCombo.addItem(side)

    def onSegment(self):
        volume_node = self.volumeSelector.currentNode()
        if volume_node is None:
            qt.QMessageBox.warning(self.parent, _("Corridor Finder"), _("Select a volume first."))
            return
        self.logic._current_volume_node = volume_node
        try:
            self.logic.load_volume(volume_node)
            source = self.logic.segment(prefer_total_segmentator=self.segmentTsCheckbox.checked)
        except Exception as exc:
            logging.error(traceback.format_exc())
            qt.QMessageBox.critical(self.parent, _("Corridor Finder"), str(exc))
            return

        if source == "fallback":
            self.segmentStatusLabel.setText(_("HU-threshold fallback — UNVERIFIED, please review/correct in Segment Editor"))
            self.segmentStatusLabel.setStyleSheet("color: #b45309; font-weight: bold;")
        else:
            self.segmentStatusLabel.setText(_("TotalSegmentator"))
            self.segmentStatusLabel.setStyleSheet("color: #15803d;")
        self.detectLandmarksButton.enabled = True

    def onDetectLandmarks(self):
        try:
            self.logic.detect_landmarks()
        except Exception as exc:
            logging.error(traceback.format_exc())
            qt.QMessageBox.critical(self.parent, _("Corridor Finder"), str(exc))
            return

        self._placeLandmarkFiducials()
        warnings = self.logic.landmark_warnings()
        self.landmarkWarningsLabel.setText("\n".join(warnings) if warnings else _("none"))
        self.suggestButton.enabled = self.logic.frame is not None
        if self.logic.frame is None:
            qt.QMessageBox.warning(
                self.parent, _("Corridor Finder"),
                _("Could not build the anterior pelvic plane frame — ASIS/pubic "
                  "tubercle landmarks were not all detected. Check the "
                  "segmentation and add missing landmarks manually."),
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

    def onSuggest(self):
        cid = self._currentCorridorId()
        side = self.sideCombo.currentText
        margin = self.marginSpin.value
        try:
            self._current_results = self.logic.suggest_corridor(cid, side, margin_mm=margin)
        except Exception as exc:
            logging.error(traceback.format_exc())
            qt.QMessageBox.critical(self.parent, _("Corridor Finder"), str(exc))
            return

        self.resultsList.clear()
        for i, r in enumerate(self._current_results):
            if r.screw.fits:
                text = f"#{i+1}: {r.screw.diameter_mm} mm x {r.screw.length_mm} mm, clearance {r.r_safe_mm:.1f} mm"
            else:
                text = f"#{i+1}: NO SCREW FITS (best clearance {r.r_safe_mm:.1f} mm)"
            self.resultsList.addItem(text)
        self.addScrewButton.enabled = len(self._current_results) > 0

    def onAddScrew(self):
        row = self.resultsList.currentRow
        if row < 0 or row >= len(self._current_results):
            row = 0
        result = self._current_results[row]
        if not result.screw.fits:
            qt.QMessageBox.warning(self.parent, _("Corridor Finder"), _("No screw fits this corridor at the current margin; not adding."))
            return
        if self.logic.plan is None:
            self.onNewPlan()

        cid = self._currentCorridorId()
        side = self.sideCombo.currentText
        margin = self.marginSpin.value
        screw_id = f"{cid}_{side}_{len(self.logic.plan.screws) + 1}"
        try:
            screw = self.logic.add_screw_to_plan(result, cid, side, screw_id, margin)
        except Exception as exc:
            logging.error(traceback.format_exc())
            qt.QMessageBox.critical(self.parent, _("Corridor Finder"), str(exc))
            return

        self._createScrewLineNode(screw)
        self.screwsList.addItem(f"{screw.screw_id}: {screw.corridor_id} ({screw.side}) {screw.diameter_mm}x{screw.length_mm}mm")

    def _createScrewLineNode(self, screw) -> None:
        node = slicer.mrmlScene.AddNewNodeByClass("vtkMRMLMarkupsLineNode", f"CF_{screw.screw_id}")
        node.AddControlPoint(vtk.vtkVector3d(*_engine_to_ras(screw.entry_xyz)), "entry")
        node.AddControlPoint(vtk.vtkVector3d(*_engine_to_ras(screw.target_xyz)), "target")
        self._screw_line_nodes[screw.screw_id] = node
        self.addObserver(node, slicer.vtkMRMLMarkupsNode.PointModifiedEvent, lambda c, e, sid=screw.screw_id: self.onScrewHandleMoved(sid))

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
        self._refreshClearanceLabel(screw_id)

    def onScrewSelected(self, row: int) -> None:
        if self.logic.plan is None or row < 0 or row >= len(self.logic.plan.screws):
            self.clearanceLabel.setText("")
            return
        self._refreshClearanceLabel(self.logic.plan.screws[row].screw_id)

    def _refreshClearanceLabel(self, screw_id: str) -> None:
        screw = next((s for s in self.logic.plan.screws if s.screw_id == screw_id), None)
        if screw is None:
            return
        v = screw.validation
        breach = v.get("breach")
        text = f"{v.get('min_clearance_mm', float('nan')):.1f} mm clearance"
        self.clearanceLabel.setText(text)
        self.clearanceLabel.setStyleSheet("color: #b91c1c; font-weight: bold;" if breach else "color: #15803d;")

    def onNewPlan(self):
        alias = self.caseAliasEdit.text or "case"
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
            self.logic.export_plan_json(path)
        except Exception as exc:
            logging.error(traceback.format_exc())
            qt.QMessageBox.critical(self.parent, _("Corridor Finder"), str(exc))

    def onExportReport(self):
        if self.logic.plan is None:
            return
        path = self._promptSavePath(_("Export report"), "HTML (*.html)")
        if not path:
            return
        try:
            drr_images = self._renderDrrImagesForPlan()
            self.logic.export_report(path, drr_images=drr_images)
        except Exception as exc:
            logging.error(traceback.format_exc())
            qt.QMessageBox.critical(self.parent, _("Corridor Finder"), str(exc))

    def _renderDrrImagesForPlan(self) -> dict:
        all_views = sorted({v for s in self.logic.plan.screws for v in s.drr_views})
        if not all_views:
            return {}
        rendered = self.logic.render_views(all_views)
        images = {}
        for screw in self.logic.plan.screws:
            per_screw = {}
            for view_name in screw.drr_views:
                view = rendered.get(view_name)
                if view is None:
                    continue
                overlay = drr_mod.draw_screw(view, screw.entry_xyz, screw.target_xyz)
                import io

                from PIL import Image

                buf = io.BytesIO()
                Image.fromarray(overlay).save(buf, format="PNG")
                per_screw[view_name] = buf.getvalue()
            images[screw.screw_id] = per_screw
        return images

    def onExportStl(self):
        if self.logic.labels_volume is None:
            return
        path = self._promptSavePath(_("Export STL"), "STL (*.stl)")
        if not path:
            return
        try:
            self.logic.export_stl(path)
        except Exception as exc:
            logging.error(traceback.format_exc())
            qt.QMessageBox.critical(self.parent, _("Corridor Finder"), str(exc))

    def onExportViewer(self):
        if self.logic.plan is None:
            return
        path = self._promptSavePath(_("Export interactive viewer"), "HTML (*.html)")
        if not path:
            return
        try:
            self.logic.export_viewer_html(path)
        except Exception as exc:
            logging.error(traceback.format_exc())
            qt.QMessageBox.critical(self.parent, _("Corridor Finder"), str(exc))

    def cleanup(self):
        self.removeObservers()


# ==========================================================================
# Test
# ==========================================================================

class CorridorFinderTest(ScriptedLoadableModuleTest):
    """Minimal self-test. Full coverage of the geometry lives in
    corridor-finder/tests/python (run outside Slicer with pytest); this
    test only exercises the Slicer-specific conversion boundary, which
    cannot be tested outside Slicer.
    """

    def setUp(self):
        slicer.mrmlScene.Clear()

    def runTest(self):
        self.setUp()
        self.test_ras_engine_roundtrip()

    def test_ras_engine_roundtrip(self):
        ras = (10.0, -20.0, 30.0)
        engine = _ras_to_engine(ras)
        back = _engine_to_ras(engine)
        for a, b in zip(ras, back):
            if abs(a - b) > 1e-9:
                raise AssertionError(f"RAS<->engine roundtrip failed: {ras} -> {engine} -> {back}")
        self.delayDisplay("RAS<->engine coordinate roundtrip: PASS")
