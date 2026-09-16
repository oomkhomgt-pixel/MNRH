import dataclasses
import json
from datetime import datetime

import numpy as np
import pytest
import jsonschema

from corridor_engine.corridor import search_corridor
from corridor_engine.edt import bone_edt_mm
from corridor_engine.phantoms import solid_rod
from corridor_engine.volume import Volume
from corridor_engine.plan import (
    Plan,
    ScrewPlan,
    save_plan,
    load_plan,
    validate_plan,
    screw_from_corridor_result,
)

SPACING = (1.0, 1.0, 1.0)
SHAPE = (60, 60, 120)


def _build_plan():
    plan = Plan(case_alias="case-001")
    plan.screws.append(
        ScrewPlan(
            screw_id="S1",
            corridor_id="C1",
            side="right",
            entry_xyz=(1.0, 2.0, 3.0),
            target_xyz=(4.0, 5.0, 6.0),
            diameter_mm=6.5,
            length_mm=80.0,
            margin_mm=2.0,
        )
    )
    plan.screws.append(
        ScrewPlan(
            screw_id="S2",
            corridor_id="C2",
            side="left",
            entry_xyz=(7.0, 8.0, 9.0),
            target_xyz=(10.0, 11.0, 12.0),
            diameter_mm=4.5,
            length_mm=60.0,
            margin_mm=1.5,
        )
    )
    plan.log("created", screw_id="S1", before=None, after={"diameter_mm": 6.5})
    return plan


def test_roundtrip_preserves_screws_and_audit(tmp_path):
    plan = _build_plan()
    path = tmp_path / "plan.json"
    save_plan(plan, path)
    loaded = load_plan(path)

    assert loaded.to_dict() == plan.to_dict()
    assert len(loaded.audit) == 1
    # timestamp is parseable ISO8601
    datetime.fromisoformat(loaded.audit[0].t)


def test_valid_plan_passes_schema_and_bad_plan_fails():
    plan = _build_plan()
    validate_plan(plan)  # should not raise

    data = plan.to_dict()

    missing_required = dict(data)
    del missing_required["screws"]
    with pytest.raises(jsonschema.ValidationError):
        validate_plan(missing_required)

    unknown_top_level = dict(data)
    unknown_top_level["unexpected_field"] = "oops"
    with pytest.raises(jsonschema.ValidationError):
        validate_plan(unknown_top_level)


def _rod_setup(radius_mm: float):
    mask = solid_rod(shape=SHAPE, radius_mm=radius_mm)
    edt = bone_edt_mm(mask, SPACING)
    edt_vol = Volume(edt, SPACING)
    nz, ny, nx = SHAPE
    xx = np.arange(nx).reshape(1, 1, nx)
    xx = np.broadcast_to(xx, SHAPE)
    entry_mask = mask & (xx < 12)
    exit_mask = mask & (xx > nx - 12)
    entry_center = edt_vol.ijk_to_world((5, ny / 2.0, nz / 2.0))
    exit_center = edt_vol.ijk_to_world((nx - 5, ny / 2.0, nz / 2.0))
    return mask, edt_vol, entry_mask, exit_mask, entry_center, exit_center


def test_screw_from_corridor_result_is_json_clean():
    mask, edt_vol, entry_mask, exit_mask, entry_c, exit_c = _rod_setup(radius_mm=8.0)
    results = search_corridor(
        entry_mask=entry_mask,
        exit_mask=exit_mask,
        entry_center_xyz=entry_c,
        entry_radius_mm=15.0,
        exit_center_xyz=exit_c,
        exit_radius_mm=15.0,
        edt_vol=edt_vol,
        margin_mm=2.0,
        screw_diameters_mm=[3.5, 4.5, 6.5, 7.0, 7.3],
        length_range_mm=(60.0, 130.0),
        textbook_direction=(1, 0, 0),
        top_k=1,
    )
    assert results

    screw = screw_from_corridor_result(
        results[0], corridor_id="C1", side="right", screw_id="S1", margin_mm=2.0
    )

    # No numpy TypeError from json.dumps
    dumped = json.dumps(dataclasses.asdict(screw))
    assert dumped
