"""Self-contained printable HTML report for a corridor Plan.

No network calls, no external assets -- everything (CSS, DRR images) is
inlined, so the file can be opened offline or handed to a printer.
"""
from __future__ import annotations

import base64
import html
from typing import Dict, Optional

from . import phi
from .validate import UNCHECKED_ENTRY_CODES

_STYLE = """
@page { size: A4; margin: 16mm; }
:root { color-scheme: light; }
* { box-sizing: border-box; }
body {
  font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
  color: #1a1a1a;
  background: #ffffff;
  margin: 0;
  padding: 16px;
}
h1 { font-size: 20px; margin-bottom: 4px; }
h2 { font-size: 16px; margin-top: 28px; border-bottom: 1px solid #ccc; padding-bottom: 4px; }
.disclaimer {
  background: #fff3cd;
  border: 1px solid #d6a828;
  padding: 10px 14px;
  border-radius: 6px;
  font-size: 13px;
  margin-bottom: 20px;
}
table { border-collapse: collapse; width: 100%; margin: 8px 0 16px; font-size: 13px; }
th, td { border: 1px solid #ccc; padding: 4px 8px; text-align: left; }
th { background: #f2f2f2; }
.drr-row { display: flex; flex-wrap: wrap; gap: 10px; margin: 8px 0; }
.drr-row figure { margin: 0; }
.drr-row img { max-width: 220px; border: 1px solid #ccc; }
.drr-row figcaption { font-size: 11px; text-align: center; color: #555; }
.clearance-ok { color: #1a7d34; font-weight: bold; }
.clearance-warn { color: #a06a00; font-weight: bold; }
.clearance-breach { color: #b3261e; font-weight: bold; }
.audit-appendix { margin-top: 32px; }
@media print {
  .screw-section { page-break-inside: avoid; }
}
"""


def _esc(value) -> str:
    return html.escape(str(value))


def _clearance_class(validation: dict, margin_mm) -> str:
    """Classify clearance using the screw's OWN margin_mm, matching
    validate.py's rule exactly: breach if min_clearance_mm < margin_mm.

    We recompute this from min_clearance_mm/margin_mm directly rather than
    trusting a possibly-stale validation["breach"] flag, so the report
    can't drift from validate.py's definition of "safe".

    Escalation used here (a reporting-only refinement on top of
    validate.py's binary breach/no-breach):
      - breach: min_clearance_mm < margin_mm            (matches validate.py)
                or the screw's start on the outer cortex could not be found
                (validate.UNCHECKED_ENTRY_CODES; validate.py calls those a
                breach too, whatever the clearance)
      - warn:   margin_mm <= min_clearance_mm < 2*margin_mm
      - ok:     min_clearance_mm >= 2*margin_mm
    """
    if any(code in UNCHECKED_ENTRY_CODES for code in validation.get("warning_codes") or []):
        return "clearance-breach"
    value = validation.get("min_clearance_mm")
    try:
        value = float(value)
    except (TypeError, ValueError):
        return "clearance-warn"
    try:
        margin_mm = float(margin_mm)
    except (TypeError, ValueError):
        margin_mm = 0.0

    if value < margin_mm:
        return "clearance-breach"
    if value < margin_mm * 2:
        return "clearance-warn"
    return "clearance-ok"


def _render_si_joint(si_joint) -> str:
    """The sacroiliac joints, which decide whether a sacral screw can fit:
    what each measured, which the surgeon declared disrupted, and how much
    of each was counted as bone."""
    if not si_joint or not si_joint.get("sentences"):
        return ""
    disrupted = si_joint.get("disrupted")
    said = f"disrupted: {disrupted}" if disrupted else "which joint is disrupted was not declared"
    items = "".join(f"<li>{_esc(line)}</li>" for line in si_joint["sentences"])
    return f"<h2>Sacroiliac joint</h2><p>{_esc(said)}</p><ul>{items}</ul>"


def _render_drr_images(screw_id: str, drr_images: Optional[Dict[str, Dict[str, bytes]]]) -> str:
    if not drr_images or screw_id not in drr_images:
        return ""
    views = drr_images[screw_id]
    figures = []
    for view_name, png_bytes in views.items():
        b64 = base64.b64encode(png_bytes).decode("ascii")
        figures.append(
            f'<figure><img src="data:image/png;base64,{b64}" alt="{_esc(view_name)}">'
            f'<figcaption>{_esc(view_name)}</figcaption></figure>'
        )
    return f'<div class="drr-row">{"".join(figures)}</div>'


def _render_offsets_table(skin_offsets, skin_entry_xyz) -> str:
    if skin_entry_xyz is None:
        # Offsets without a skin entry would not be skin offsets (older plans
        # stored them measured from the bone entry): never show them as such.
        return ("<p><em>Skin entry not found along the screw's axis within the scan "
                "(for example, the axis leaves the scan first); no incision offsets.</em></p>")
    if not skin_offsets:
        return "<p><em>No skin offsets recorded.</em></p>"
    rows = []
    for off in skin_offsets:
        if not isinstance(off, dict):
            off = off.__dict__
        rows.append(
            "<tr>"
            f"<td>{_esc(off.get('landmark', ''))}</td>"
            f"<td>{_esc(off.get('dx_cm', ''))}</td>"
            f"<td>{_esc(off.get('dy_cm', ''))}</td>"
            f"<td>{_esc(off.get('dz_cm', ''))}</td>"
            f"<td>{_esc(off.get('distance_cm', ''))}</td>"
            "</tr>"
        )
    return (
        "<p>Skin entry point relative to each landmark, in cm.</p>"
        "<table><thead><tr><th>Landmark</th><th>right (+) / left (-)</th>"
        "<th>anterior (+) / posterior (-)</th><th>superior (+) / inferior (-)</th>"
        "<th>distance</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _render_guidance(guidance: dict) -> str:
    """How to aim the screw: its direction in words, the C-arm position that
    looks straight down it, and how far its entry may move."""
    if not guidance:
        return "<p><em>No aiming guidance recorded.</em></p>"
    lines = []
    for key, label in (("direction_app", "Direction, anterior pelvic plane"), ("direction_scanner", "Direction, scan axes")):
        if guidance.get(key):
            lines.append(f"{label}: {guidance[key]}")
    barrel = guidance.get("barrel_view") or {}
    if barrel.get("reading"):
        lines.append(
            f"C-arm looking down the screw: {barrel['reading']} "
            f"(tilt {_fmt_mm(barrel.get('rotate_x_deg'), 0)} degrees, roll {_fmt_mm(barrel.get('rotate_z_deg'), 0)} degrees)"
        )
    area = guidance.get("entry_area") or {}
    if area.get("sentence"):
        lines.append(f"Room at the entry: {area['sentence']}")
    return "<ul>" + "".join(f"<li>{_esc(line)}</li>" for line in lines) + "</ul>"


def _render_angles_table(angles_app: dict, angles_scanner: dict) -> str:
    keys = sorted(set(angles_app or {}) | set(angles_scanner or {}))
    if not keys:
        return "<p><em>No angle data recorded.</em></p>"
    rows = []
    for k in keys:
        rows.append(
            "<tr>"
            f"<td>{_esc(k)}</td>"
            f"<td>{_esc((angles_app or {}).get(k, ''))}</td>"
            f"<td>{_esc((angles_scanner or {}).get(k, ''))}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>Angle</th><th>APP frame</th><th>Scanner frame</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _fmt_mm(value, digits=1) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "n/a"


def _render_geometry(screw: dict, validation: dict) -> str:
    """Where validate.py placed the screw: entry on the cortex, length from
    there, the tip rule and protrusion, the entry angle, and its warnings."""
    lines = []
    start = validation.get("start_xyz")
    if start is not None:
        text = "Entry on the cortex at (" + ", ".join(_fmt_mm(v) for v in start) + ") mm"
        offset = validation.get("entry_handle_offset_mm") or 0.0
        if abs(float(offset)) >= 0.05:
            text += f"; the entry handle was {_fmt_mm(abs(float(offset)))} mm {'outside' if float(offset) > 0 else 'inside'} it"
        lines.append(text)
    angle = validation.get("entry_angle_deg")
    if angle is not None:
        lines.append(f"Entry angle: {_fmt_mm(angle, 0)} degrees to the cortex normal")
    if screw.get("tip_rule", validation.get("tip_rule")) == "through":
        protrusion = validation.get("protrusion_mm")
        if protrusion is None:
            lines.append("Tip: meant to pass the far cortex, but the far cortex was not found; kept inside bone")
        else:
            lines.append(f"Tip: through the far cortex, protruding {_fmt_mm(protrusion)} mm")
    else:
        lines.append("Tip: inside bone, with the full margin")
    items = "".join(f"<li>{_esc(line)}</li>" for line in lines)
    warnings = validation.get("warnings") or []
    warn_html = ""
    if warnings:
        warn_html = '<p class="clearance-warn">Warnings:</p><ul>' + "".join(f"<li>{_esc(w)}</li>" for w in warnings) + "</ul>"
    return f"<ul>{items}</ul>{warn_html}"


def _render_screw_section(screw, drr_images=None) -> str:
    if not isinstance(screw, dict):
        screw = screw.__dict__
    validation = screw.get("validation") or {}
    margin_mm = screw.get("margin_mm", 0)
    clearance_class = _clearance_class(validation, margin_mm)
    clearance_val = validation.get("min_clearance_mm", "n/a")
    breach = clearance_class == "clearance-breach"

    return f"""
<section class="screw-section">
  <h2>Screw {_esc(screw.get('screw_id', ''))} &mdash; {_esc(screw.get('side', ''))} ({_esc(screw.get('corridor_id', ''))})</h2>
  <p>Diameter: {_esc(screw.get('diameter_mm', ''))} mm &nbsp;|&nbsp;
     Length (cortex to tip): {_esc(screw.get('length_mm', ''))} mm &nbsp;|&nbsp;
     Margin: {_esc(screw.get('margin_mm', ''))} mm &nbsp;|&nbsp;
     Source: {_esc(screw.get('source', ''))}</p>
  <p>Clearance: <span class="{clearance_class}">{_esc(clearance_val)} mm{' (BREACH)' if breach else ''}</span></p>
  {_render_geometry(screw, validation)}
  <h3>How to aim it</h3>
  {_render_guidance(screw.get('guidance'))}
  {_render_drr_images(screw.get('screw_id', ''), drr_images)}
  <h3>Skin landmark offsets</h3>
  {_render_offsets_table(screw.get('skin_offsets'), screw.get('skin_entry_xyz'))}
  <h3>Trajectory angles</h3>
  {_render_angles_table(screw.get('angles_app'), screw.get('angles_scanner'))}
</section>
"""


def _render_audit_appendix(audit) -> str:
    if not audit:
        return "<p><em>No audit entries.</em></p>"
    rows = []
    for entry in audit:
        if not isinstance(entry, dict):
            entry = entry.__dict__
        rows.append(
            "<tr>"
            f"<td>{_esc(entry.get('t', ''))}</td>"
            f"<td>{_esc(entry.get('action', ''))}</td>"
            f"<td>{_esc(entry.get('screw_id', ''))}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>Timestamp</th><th>Action</th><th>Screw</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def render_report_html(plan, *, drr_images: dict = None, title: str = "Corridor plan") -> str:
    if hasattr(plan, "to_dict"):
        data = plan.to_dict()
    else:
        data = plan

    disclaimer = data.get("disclaimer", "")
    case_alias = data.get("case_alias", "")
    screws = data.get("screws", [])
    audit = data.get("audit", [])

    sections = []
    for screw in screws:
        if not isinstance(screw, dict):
            screw = screw.__dict__
        sections.append(_render_screw_section(screw, drr_images))

    body_sections = "\n".join(sections) if sections else "<p><em>No screws in this plan.</em></p>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="robots" content="noindex, nofollow">
<title>{_esc(title)}</title>
<style>{_STYLE}</style>
</head>
<body>
<h1>{_esc(title)}</h1>
<p>Case: {_esc(case_alias)}</p>
{_render_si_joint(data.get("si_joint"))}
<div class="disclaimer">{_esc(disclaimer)}</div>
{body_sections}
<div class="audit-appendix">
  <h2>Audit log</h2>
  {_render_audit_appendix(audit)}
</div>
</body>
</html>
"""


def write_report(plan, path, *, check_phi: bool = True, **kwargs) -> None:
    if check_phi:
        data = plan.to_dict() if hasattr(plan, "to_dict") else plan
        phi.assert_no_phi(data)
    html_str = render_report_html(plan, **kwargs)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_str)
