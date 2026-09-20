"""Plan persistence: the JSON-serializable case plan (screws, corridors,
audit trail) that ties together corridor search, validation, and skin
offsets into one file a surgeon can review and re-load.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import jsonschema
import numpy as np

from . import phi

SCHEMA_ID = "mnrh-corridor-plan/1"
# Every coordinate in a plan (entry/target, skin entry, landmarks, APP frame)
# is in 3D Slicer's RAS world coordinates, mm; recorded in each plan file.
COORDINATE_SYSTEM = "RAS"
DISCLAIMER = "Intended for preoperative planning; verify against intraoperative imaging."

_SCHEMA_PATH = Path(__file__).with_name("plan.schema.json")


def _to_jsonable(obj: Any) -> Any:
    """Recursively convert numpy scalars/arrays and tuples into plain
    python floats/ints/lists so the result is directly json.dumps-able."""
    if isinstance(obj, np.ndarray):
        return [_to_jsonable(x) for x in obj.tolist()]
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    return obj


@dataclass
class ScrewPlan:
    screw_id: str
    corridor_id: str
    side: str
    entry_xyz: tuple
    target_xyz: tuple
    diameter_mm: float
    length_mm: float  # implant length, entry cortex to tip (validation.length_mm)
    margin_mm: float
    skin_entry_xyz: Optional[tuple] = None
    skin_offsets: list = field(default_factory=list)
    angles_app: dict = field(default_factory=dict)
    angles_scanner: dict = field(default_factory=dict)
    validation: dict = field(default_factory=dict)
    # How to aim it: the direction in words, the C-arm view that looks down
    # the screw, and the room around its entry (guidance.py, entry_zone.py).
    guidance: dict = field(default_factory=dict)
    drr_views: list = field(default_factory=list)
    source: str = "auto"  # "auto" or "adjusted"
    # "inside" or "through" (corridors.json "tip", DECISIONS.md 1.5); the
    # exported viewer validates the screw with it.
    tip_rule: str = "inside"


@dataclass
class AuditEntry:
    t: str
    action: str
    screw_id: str = ""
    before: Optional[dict] = None
    after: Optional[dict] = None


@dataclass
class Plan:
    case_alias: str
    case: dict = field(default_factory=dict)
    frame: dict = field(default_factory=dict)
    landmarks: dict = field(default_factory=dict)
    screws: list = field(default_factory=list)  # list[ScrewPlan]
    screw_library: dict = field(default_factory=dict)
    audit: list = field(default_factory=list)  # list[AuditEntry]
    software: dict = field(default_factory=dict)
    disclaimer: str = DISCLAIMER
    schema: str = SCHEMA_ID

    def log(self, action, screw_id: str = "", before: Optional[dict] = None, after: Optional[dict] = None) -> AuditEntry:
        entry = AuditEntry(
            t=datetime.now(timezone.utc).isoformat(),
            action=action,
            screw_id=screw_id,
            before=before,
            after=after,
        )
        self.audit.append(entry)
        return entry

    def to_dict(self) -> dict:
        screws = [
            _to_jsonable(asdict(s)) if not isinstance(s, dict) else _to_jsonable(s)
            for s in self.screws
        ]
        audit = [
            _to_jsonable(asdict(a)) if not isinstance(a, dict) else _to_jsonable(a)
            for a in self.audit
        ]
        return {
            "schema": self.schema,
            "coordinate_system": COORDINATE_SYSTEM,
            "case_alias": self.case_alias,
            "case": _to_jsonable(self.case),
            "frame": _to_jsonable(self.frame),
            "landmarks": _to_jsonable(self.landmarks),
            "screws": screws,
            "screw_library": _to_jsonable(self.screw_library),
            "audit": audit,
            "software": _to_jsonable(self.software),
            "disclaimer": self.disclaimer,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Plan":
        data = dict(data)
        screw_field_names = {f.name for f in fields(ScrewPlan)}
        screws = [
            ScrewPlan(**{k: v for k, v in s.items() if k in screw_field_names})
            for s in data.get("screws", [])
        ]
        audit_field_names = {f.name for f in fields(AuditEntry)}
        audit = [
            AuditEntry(**{k: v for k, v in a.items() if k in audit_field_names})
            for a in data.get("audit", [])
        ]
        return cls(
            case_alias=data.get("case_alias", ""),
            case=data.get("case", {}),
            frame=data.get("frame", {}),
            landmarks=data.get("landmarks", {}),
            screws=screws,
            screw_library=data.get("screw_library", {}),
            audit=audit,
            software=data.get("software", {}),
            disclaimer=data.get("disclaimer", DISCLAIMER),
            schema=data.get("schema", SCHEMA_ID),
        )


def frame_to_dict(frame) -> dict:
    return {
        "origin": _to_jsonable(np.asarray(frame.origin)),
        "x_hat": _to_jsonable(np.asarray(frame.x_hat)),
        "y_hat": _to_jsonable(np.asarray(frame.y_hat)),
        "z_hat": _to_jsonable(np.asarray(frame.z_hat)),
    }


def screw_from_corridor_result(result, corridor_id, side, screw_id, margin_mm, **extras) -> ScrewPlan:
    """Adapter from corridor.CorridorResult -> ScrewPlan.

    Raises ValueError if the corridor result carries no screw that actually
    fits (both a diameter and a catalog length), since a plan entry needs a
    concrete diameter/length to be actionable. The raw corridor length is
    never substituted for a missing catalog length.
    """
    screw = result.screw
    if screw is None or not screw.fits or screw.diameter_mm is None or screw.length_mm is None:
        raise ValueError(f"corridor result for {corridor_id!r} has no fitting screw")

    return ScrewPlan(
        screw_id=screw_id,
        corridor_id=corridor_id,
        side=side,
        entry_xyz=tuple(_to_jsonable(np.asarray(result.entry_xyz))),
        target_xyz=tuple(_to_jsonable(np.asarray(result.target_xyz))),
        diameter_mm=float(screw.diameter_mm),
        length_mm=float(screw.length_mm),
        margin_mm=float(margin_mm),
        tip_rule=getattr(result, "tip_rule", "inside"),
        **extras,
    )


def load_schema() -> dict:
    with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_plan(plan_or_dict) -> None:
    data = plan_or_dict.to_dict() if isinstance(plan_or_dict, Plan) else plan_or_dict
    jsonschema.validate(instance=data, schema=load_schema())


def save_plan(plan: Plan, path, *, check_phi: bool = True) -> None:
    data = plan.to_dict()
    validate_plan(data)
    if check_phi:
        phi.assert_no_phi(data)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def load_plan(path) -> Plan:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return Plan.from_dict(data)
