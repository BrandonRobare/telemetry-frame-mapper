from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy.orm import Session as DBSession

from backend.db.models import Annotation, Image, Reconstruction
from backend.db.models import Session as SessionModel
from backend.services.preflight_quality import build_preflight_quality_report


def build_survey_report(session_id: int, db: DBSession) -> dict:
    """Assemble a professional survey report from session metadata, preflight
    quality summaries, coverage data, annotations/measurements, and
    reconstruction metrics.

    Returns a structured JSON report with an ``html`` field containing a
    self-contained HTML document suitable for download or printing.
    """
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session:
        raise ValueError(f"Session {session_id} not found")

    # Gather all source data -------------------------------------------------
    images = db.query(Image).filter(Image.session_id == session_id).all()

    reconstructions = (
        db.query(Reconstruction)
        .filter(Reconstruction.session_id == session_id)
        .order_by(Reconstruction.id.desc())
        .all()
    )

    # Annotations across all reconstructions
    rec_ids = [r.id for r in reconstructions]
    annotations: list[Annotation] = []
    if rec_ids:
        annotations = (
            db.query(Annotation)
            .filter(Annotation.reconstruction_id.in_(rec_ids))
            .all()
        )

    # Preflight / quick-quality
    try:
        preflight = build_preflight_quality_report(session_id, db)
    except ValueError:
        preflight = None

    # Report timestamp
    generated_at = datetime.now(UTC).isoformat()

    # Build structured report -------------------------------------------------
    report: dict = {
        "report_type": "survey-report",
        "version": "1.0",
        "generated_at": generated_at,
        "session": _session_section(session, images),
        "frame_summary": _frame_summary_section(images),
        "quality_assessment": _quality_section(preflight),
        "coverage": _coverage_section(preflight),
        "reconstructions": _reconstructions_section(reconstructions),
        "annotations": _annotations_section(annotations),
        "html": _render_html(
            session, images, preflight, reconstructions, annotations, generated_at
        ),
    }
    return report


# ------------------------------------------------------------------ sections


def _session_section(session: SessionModel, _images: list[Image]) -> dict:
    return {
        "id": session.id,
        "name": session.name,
        "folder_path": session.folder_path,
        "imported_at": session.imported_at.isoformat() if session.imported_at else None,
        "photo_count": session.photo_count,
        "usable_count": session.usable_count,
        "notes": session.notes,
    }


def _frame_summary_section(images: list[Image]) -> dict:
    if not images:
        return {"total": 0, "usable": 0, "quality_breakdown": {}}

    usable = [img for img in images if img.usable]
    flag_counts: dict[str, int] = {}
    for img in images:
        flag_counts[img.flag or "unknown"] = flag_counts.get(img.flag or "unknown", 0) + 1

    # Camera info from first image with data
    camera_info = {}
    for img in images:
        if img.camera_make or img.camera_model:
            camera_info = {
                "make": img.camera_make,
                "model": img.camera_model,
                "width": img.width,
                "height": img.height,
                "focal_length_mm": img.focal_length_mm,
            }
            break

    return {
        "total": len(images),
        "usable": len(usable),
        "quality_breakdown": flag_counts,
        "camera": camera_info if camera_info else None,
        "gps_present": sum(
            1 for img in images
            if img.latitude is not None and img.longitude is not None
        ),
    }


def _quality_section(preflight: dict | None) -> dict:
    if preflight is None:
        return {"available": False, "reason": "preflight check could not run"}

    q = preflight.get("quality", {})
    g = preflight.get("gps", {})
    t = preflight.get("timestamps", {})

    return {
        "available": True,
        "score": preflight.get("score"),
        "safe_to_reconstruct": preflight.get("safe_to_reconstruct"),
        "recommended_action": preflight.get("recommended_action"),
        "warnings": preflight.get("warnings", []),
        "gps": {
            "missing_frames": g.get("missing", 0),
            "completeness_pct": g.get("completeness_pct", 0),
        },
        "timestamps": {
            "missing": t.get("missing", 0),
            "completeness_pct": t.get("completeness_pct", 0),
            "duplicate_groups": t.get("duplicate_groups", 0),
            "gap_count": t.get("gap_count", 0),
        },
        "optical_quality": {
            "blur_pct": q.get("blur_pct", 0),
            "dark_pct": q.get("dark_pct", 0),
            "bright_pct": q.get("bright_pct", 0),
        },
        "match_density": preflight.get("match_density"),
    }


def _coverage_section(preflight: dict | None) -> dict:
    if preflight is None:
        return {"available": False}

    c = preflight.get("coverage", {})
    return {
        "available": True,
        "footprint_count": c.get("footprint_count", 0),
        "coverage_pct": c.get("footprint_coverage_pct", 0),
        "estimated_overlap_pct": c.get("estimated_overlap_pct"),
        "union_area": c.get("union_area", 0),
        "summed_footprint_area": c.get("summed_footprint_area", 0),
        "warnings": c.get("warnings", []),
    }


def _reconstructions_section(reconstructions: list[Reconstruction]) -> list[dict]:
    result: list[dict] = []
    for rec in reconstructions:
        metrics = {}
        if rec.training_metrics:
            try:
                metrics = {"iterations": json.loads(rec.training_metrics)}
            except (json.JSONDecodeError, TypeError):
                metrics = {}

        artifacts = {}
        for field in (
            "splat_path", "splat_preview_path", "splat_medium_path",
            "pointcloud_path", "mesh_glb_path", "mesh_obj_path",
            "flythrough_path", "coverage_gaps_path",
        ):
            val = getattr(rec, field, None)
            if val:
                artifacts[field] = val

        result.append({
            "id": rec.id,
            "status": rec.status,
            "preset": rec.preset,
            "frames_used": rec.frames_used,
            "frames_registered": rec.frames_registered,
            "gaussian_count": rec.gaussian_count,
            "psnr": rec.psnr,
            "ssim": rec.ssim,
            "mesh_status": rec.mesh_status,
            "flythrough_status": rec.flythrough_status,
            "started_at": rec.started_at.isoformat() if rec.started_at else None,
            "completed_at": rec.completed_at.isoformat() if rec.completed_at else None,
            "duration_s": rec.duration_s,
            "artifacts": artifacts,
            "training_metrics": metrics,
        })
    return result


def _annotations_section(annotations: list[Annotation]) -> list[dict]:
    return [
        {
            "id": a.id,
            "reconstruction_id": a.reconstruction_id,
            "label": a.label,
            "lat": a.lat,
            "lon": a.lon,
            "alt_m": a.alt_m,
            "color": a.color,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in annotations
    ]


# ------------------------------------------------------------------- HTML


def _render_html(
    session: SessionModel,
    images: list[Image],
    preflight: dict | None,
    reconstructions: list[Reconstruction],
    annotations: list[Annotation],
    generated_at: str,
) -> str:
    """Render a self-contained HTML report suitable for download or print."""
    session_s = _session_section(session, images)
    frame_s = _frame_summary_section(images)
    quality_s = _quality_section(preflight)
    coverage_s = _coverage_section(preflight)
    recs_s = _reconstructions_section(reconstructions)
    anns_s = _annotations_section(annotations)

    # Quality score badge colour
    score = quality_s.get("score") if quality_s.get("available") else None
    if score is not None:
        if score >= 80:
            score_color = "#2ea043"
        elif score >= 60:
            score_color = "#d29922"
        else:
            score_color = "#f85149"
    else:
        score_color = "#8b949e"

    safe = quality_s.get("safe_to_reconstruct", "N/A")

    def esc(s: str) -> str:
        return (
            s.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )

    rec_rows = ""
    for rec in recs_s:
        status_label = rec["status"]
        psnr_str = f'{rec["psnr"]:.2f}' if rec["psnr"] is not None else "—"
        ssim_str = f'{rec["ssim"]:.4f}' if rec["ssim"] is not None else "—"
        dur = rec.get("duration_s")
        dur_str = f"{dur:.0f}s" if dur is not None else "—"
        rec_rows += f"""
        <tr>
          <td>{rec["id"]}</td>
          <td>{esc(rec.get("preset", ""))}</td>
          <td>{esc(status_label or "")}</td>
          <td>{rec.get("frames_used", 0)}</td>
          <td>{rec.get("frames_registered") or "—"}</td>
          <td>{rec.get("gaussian_count") or "—"}</td>
          <td>{psnr_str}</td>
          <td>{ssim_str}</td>
          <td>{dur_str}</td>
        </tr>"""

    warnings_html = ""
    for w in quality_s.get("warnings", []):
        warnings_html += f'<li style="color:#f85149;font-size:13px;">{esc(w)}</li>'

    annotations_html = ""
    for a in anns_s:
        annotations_html += f"""
        <tr>
          <td>{esc(a["label"])}</td>
          <td>{a["lat"]:.6f}</td>
          <td>{a["lon"]:.6f}</td>
          <td>{a["alt_m"]:.2f}</td>
          <td>{esc(a.get("color", ""))}</td>
        </tr>"""

    report_title = f"Survey Report — {esc(session.name or f'Session {session.id}')}"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{report_title}</title>
<style>
  body {{ font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
         max-width:820px; margin:0 auto; padding:24px; color:#c9d1d9; background:#0d1117; }}
  h1 {{ font-size:22px; margin:0 0 4px; color:#e6edf3; }}
  h2 {{ font-size:16px; margin:28px 0 12px; border-bottom:1px solid #30363d; padding-bottom:6px; color:#e6edf3; }}
  .meta {{ color:#8b949e; font-size:13px; margin-bottom:20px; }}
  .score-badge {{ display:inline-block; padding:2px 10px; border-radius:12px; font-weight:600; font-size:14px; margin-left:8px; }}
  table {{ border-collapse:collapse; width:100%; font-size:13px; }}
  th, td {{ padding:6px 10px; text-align:left; border-bottom:1px solid #21262d; }}
  th {{ color:#8b949e; font-weight:500; }}
  .section {{ margin-bottom:8px; }}
  .kv {{ display:grid; grid-template-columns:180px 1fr; gap:4px 8px; font-size:13px; }}
  .kv dt {{ color:#8b949e; }}
  .kv dd {{ color:#c9d1d9; margin:0; }}
  ul {{ padding-left:20px; }}
  .footer {{ margin-top:36px; font-size:11px; color:#484f58; border-top:1px solid #21262d; padding-top:12px; }}
  @media print {{ body {{ background:#fff; color:#000; }} }}
</style>
</head>
<body>
<h1>{report_title}</h1>
<p class="meta">Generated {generated_at} &mdash; TFM Operator</p>

<h2>Quality Assessment</h2>
<div class="section">
  <div style="margin-bottom:12px;">
    Score: <span class="score-badge" style="background:{score_color};color:#fff;">{score or "N/A"}</span>
    Verdict: <strong>{esc(str(safe))}</strong>
  </div>
  <div class="kv">
    <dt>Recommended action</dt>
    <dd>{esc(quality_s.get("recommended_action", "N/A") or "N/A")}</dd>
  </div>
</div>

{"<h3>Warnings</h3><ul>" + warnings_html + "</ul>" if warnings_html else ""}

<h2>Session Metadata</h2>
<div class="kv">
  <dt>Session ID</dt><dd>{session_s["id"]}</dd>
  <dt>Name</dt><dd>{esc(session_s["name"] or "")}</dd>
  <dt>Imported</dt><dd>{session_s["imported_at"] or "—"}</dd>
  <dt>Total frames</dt><dd>{frame_s["total"]}</dd>
  <dt>Usable frames</dt><dd>{frame_s["usable"]}</dd>
  <dt>GPS frames</dt><dd>{frame_s["gps_present"]}</dd>
</div>

<h2>Frame Quality Breakdown</h2>
<table>
  <tr><th>Flag</th><th>Count</th></tr>
  {"".join(f'<tr><td>{esc(k)}</td><td>{v}</td></tr>' for k,v in sorted(frame_s.get("quality_breakdown", {}).items()))}
</table>

<h2>GPS</h2>
<div class="kv">
  <dt>Missing</dt><dd>{quality_s["gps"]["missing_frames"]}</dd>
  <dt>Completeness</dt><dd>{quality_s["gps"]["completeness_pct"]}%</dd>
</div>

<h2>Timestamps</h2>
<div class="kv">
  <dt>Missing</dt><dd>{quality_s["timestamps"]["missing"]}</dd>
  <dt>Completeness</dt><dd>{quality_s["timestamps"]["completeness_pct"]}%</dd>
  <dt>Duplicate groups</dt><dd>{quality_s["timestamps"]["duplicate_groups"]}</dd>
  <dt>Gap count</dt><dd>{quality_s["timestamps"]["gap_count"]}</dd>
</div>

<h2>Optical Quality</h2>
<div class="kv">
  <dt>Blur</dt><dd>{quality_s["optical_quality"]["blur_pct"]}%</dd>
  <dt>Dark</dt><dd>{quality_s["optical_quality"]["dark_pct"]}%</dd>
  <dt>Bright</dt><dd>{quality_s["optical_quality"]["bright_pct"]}%</dd>
</div>

<h2>Coverage</h2>
<div class="kv">
  <dt>Footprint count</dt><dd>{coverage_s["footprint_count"]}</dd>
  <dt>Coverage %</dt><dd>{coverage_s["coverage_pct"]}%</dd>
  <dt>Estimated overlap</dt><dd>{coverage_s.get("estimated_overlap_pct") or "—"}%</dd>
</div>

<h2>Reconstructions ({len(recs_s)})</h2>
{"<table><tr><th>ID</th><th>Preset</th><th>Status</th><th>Frames Used</th><th>Registered</th><th>Gaussians</th><th>PSNR</th><th>SSIM</th><th>Duration</th></tr>" + rec_rows + "</table>" if recs_s else "<p>No reconstructions found.</p>"}

<h2>Annotations ({len(anns_s)})</h2>
{"<table><tr><th>Label</th><th>Lat</th><th>Lon</th><th>Alt (m)</th><th>Color</th></tr>" + annotations_html + "</table>" if anns_s else "<p>No annotations recorded.</p>"}

<div class="footer">
  <p>TFM Operator Survey Report &mdash; generated {generated_at}</p>
  <p>PDF output: generation was not requested or a PDF backend (e.g. WeasyPrint) is not installed.
  This HTML report can be printed-to-PDF from any modern browser (Ctrl/Cmd+P &rarr; Save as PDF).</p>
</div>
</body>
</html>"""