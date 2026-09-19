import pytest

from corridor_engine.plan import Plan, ScrewPlan
from corridor_engine.report import render_report_html, write_report

# Smallest possible valid PNG (1x1 transparent pixel)
_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _plan_with_screws(clearances, margin_mm=2.0):
    """Build a plan whose screws carry the given min_clearance_mm values,
    each screw with the given margin_mm.

    NOTE: breach is NOT "clearance < 0". It is the validate.py rule
    (min_clearance_mm < margin_mm). The "breach" flag stored on each
    screw's validation dict is deliberately set to a WRONG/stale value
    here (the opposite of what validate.py's rule would say) so that
    tests confirm the report recomputes from min_clearance_mm/margin_mm
    directly instead of trusting a possibly-stale breach flag.
    """
    plan = Plan(case_alias="case-report")
    for i, clearance in enumerate(clearances):
        plan.screws.append(
            ScrewPlan(
                screw_id=f"S{i}",
                corridor_id=f"C{i}",
                side="right" if i % 2 == 0 else "left",
                entry_xyz=(0.0, 0.0, 0.0),
                target_xyz=(1.0, 1.0, 1.0),
                diameter_mm=6.5,
                length_mm=80.0,
                margin_mm=margin_mm,
                validation={
                    "min_clearance_mm": clearance,
                    # Deliberately wrong/stale, per the docstring above.
                    "breach": not (clearance < margin_mm),
                },
            )
        )
    plan.log("created")
    return plan


def test_report_is_self_contained():
    plan = _plan_with_screws([3.0])
    html_str = render_report_html(
        plan, drr_images={"S0": {"AP": _TINY_PNG}}, title="Test report"
    )

    assert "http://" not in html_str
    assert "https://" not in html_str
    assert "data:image/png;base64," in html_str
    assert "<img" in html_str
    assert 'name="robots" content="noindex, nofollow"' in html_str


def test_report_contains_disclaimer_and_every_screw():
    plan = _plan_with_screws([3.0, 1.0, -1.0])
    html_str = render_report_html(plan)

    assert plan.disclaimer in html_str
    for screw in plan.screws:
        assert screw.screw_id in html_str


def test_clearance_colour_classes():
    # margin_mm=2.0 for every screw here (see _plan_with_screws default).
    # ok:     min_clearance_mm >= 2*margin_mm (>= 4.0)      -> 5.0
    # warn:   margin_mm <= min_clearance_mm < 2*margin_mm   -> 2.5
    # breach: min_clearance_mm < margin_mm (< 2.0)          -> -1.0
    plan = _plan_with_screws([5.0, 2.5, -1.0])
    html_str = render_report_html(plan)

    assert "clearance-ok" in html_str
    assert "clearance-warn" in html_str
    assert "clearance-breach" in html_str


def test_clearance_class_uses_screw_margin_not_absolute_clearance():
    """A positive clearance can still be a breach if it's below THAT
    screw's margin_mm, and a screw's own breach flag being (wrongly) set
    or unset must not matter -- report.py recomputes from
    min_clearance_mm/margin_mm directly."""
    # margin_mm=4.0, clearance=2.5 -> breach even though clearance > 0.
    plan = _plan_with_screws([2.5], margin_mm=4.0)
    html_str = render_report_html(plan)
    assert 'class="clearance-breach"' in html_str
    assert 'class="clearance-ok"' not in html_str

    # margin_mm=2.0, clearance=2.5 -> ok is NOT reached (2.5 < 2*2.0=4.0),
    # this lands in warn.
    plan2 = _plan_with_screws([2.5], margin_mm=2.0)
    html_str2 = render_report_html(plan2)
    assert 'class="clearance-warn"' in html_str2
    assert 'class="clearance-breach"' not in html_str2

    # margin_mm=2.0, clearance=0.5 -> breach (0.5 < 2.0).
    plan3 = _plan_with_screws([0.5], margin_mm=2.0)
    html_str3 = render_report_html(plan3)
    assert 'class="clearance-breach"' in html_str3


def test_write_report_rejects_phi(tmp_path):
    plan = {
        "disclaimer": "for testing only",
        "case_alias": "case-report",
        "case": {"PatientName": "Jane Doe"},
        "screws": [],
        "audit": [],
    }
    out_path = tmp_path / "report.html"

    with pytest.raises(ValueError):
        write_report(plan, out_path)

    assert not out_path.exists()


def test_write_report_allows_check_phi_disabled(tmp_path):
    plan = {
        "disclaimer": "for testing only",
        "case_alias": "case-report",
        "case": {"PatientName": "Jane Doe"},
        "screws": [],
        "audit": [],
    }
    out_path = tmp_path / "report.html"

    write_report(plan, out_path, check_phi=False)

    assert out_path.exists()


def test_skin_offsets_name_their_anatomical_directions():
    plan = _plan_with_screws([3.0])
    plan.screws[0].skin_entry_xyz = (60.0, 20.0, 100.0)
    plan.screws[0].skin_offsets = [{"landmark": "asis_right", "dx_cm": 1.0, "dy_cm": -2.0, "dz_cm": 3.0, "distance_cm": 3.7}]
    html_str = render_report_html(plan)
    # dx/dy/dz alone do not say which way is positive; RAS: +x is the
    # patient's right, +y anterior, +z superior.
    for header in ("right (+) / left (-)", "anterior (+) / posterior (-)", "superior (+) / inferior (-)"):
        assert header in html_str


def test_report_says_where_the_screw_is_and_warns():
    plan = _plan_with_screws([3.0])
    screw = plan.screws[0]
    screw.tip_rule = "through"
    screw.validation.update(
        {
            "start_xyz": [10.0, -20.25, 30.0],
            "entry_handle_offset_mm": -3.0,
            "entry_angle_deg": 64.4,
            "protrusion_mm": 2.37,
            "warnings": ["entry too oblique: 64 degrees to the cortex normal"],
        }
    )
    html_str = render_report_html(plan)
    assert "Length (cortex to tip)" in html_str
    assert "Entry on the cortex at (10.0, -20.2, 30.0) mm; the entry handle was 3.0 mm inside it" in html_str
    assert "Entry angle: 64 degrees" in html_str
    assert "protruding 2.4 mm" in html_str
    assert "entry too oblique" in html_str


def test_report_inside_tip():
    plan = _plan_with_screws([3.0])
    assert "Tip: inside bone, with the full margin" in render_report_html(plan)


def test_report_calls_an_unplaceable_entry_a_breach_whatever_the_clearance():
    # validate.py never reports safe a screw whose start on the outer cortex
    # could not be found; the report must not either.
    plan = _plan_with_screws([5.0])
    plan.screws[0].validation["warning_codes"] = ["entry_not_outer"]
    assert "BREACH" in render_report_html(plan)


def test_offsets_without_a_skin_entry_are_not_shown_as_skin_offsets():
    # Plans made before this fix stored offsets measured from the bone
    # entry when the skin entry was not found.
    plan = _plan_with_screws([3.0])
    plan.screws[0].skin_entry_xyz = None
    plan.screws[0].skin_offsets = [{"landmark": "ischial_tuberosity_right", "dx_cm": 0.66, "dy_cm": 0.6, "dz_cm": -0.07, "distance_cm": 0.89}]
    html_str = render_report_html(plan)
    assert "Skin entry not found" in html_str
    assert "ischial_tuberosity_right" not in html_str
