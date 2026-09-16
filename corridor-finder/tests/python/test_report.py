from corridor_engine.plan import Plan, ScrewPlan
from corridor_engine.report import render_report_html

# Smallest possible valid PNG (1x1 transparent pixel)
_TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _plan_with_screws(clearances):
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
                margin_mm=2.0,
                validation={"min_clearance_mm": clearance, "breach": clearance < 0},
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
    plan = _plan_with_screws([5.0, 1.0, -1.0])
    html_str = render_report_html(plan)

    assert "clearance-ok" in html_str
    assert "clearance-warn" in html_str
    assert "clearance-breach" in html_str
