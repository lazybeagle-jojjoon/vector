from __future__ import annotations

import csv
import html
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .global_map import _write_csv


@dataclass(frozen=True)
class ComponentDashboardPaths:
    metadata_path: Path
    dashboard_path: Path
    html_path: Path


_DASHBOARD_FIELDS = [
    "frame_index",
    "window_frame_index",
    "window_months",
    "frame_label",
    "period_start",
    "period_end",
    "threshold",
    "component_id",
    "size",
    "component_density",
    "mean_internal_correlation",
    "mean_period_return",
    "edge_count",
    "possible_edge_count",
    "giant_component_share",
    "market_strong_edge_ratio",
    "component_count",
    "singleton_count",
    "forward_event_type",
    "forward_overlap_span",
    "forward_jaccard",
    "forward_overlap_count",
    "forward_retention_ratio",
    "forward_to_frame_label",
    "forward_target_component_id",
    "forward_target_size",
    "forward_target_density",
    "forward_source_match_count",
    "forward_target_match_count",
    "top_symbols",
    "forward_target_top_symbols",
]


def write_component_dashboard(
    *,
    component_dir: str | Path,
    output_dir: str | Path | None = None,
    threshold: str = "0.7",
    min_size: int = 5,
    top_n: int = 200,
) -> ComponentDashboardPaths:
    if min_size < 2:
        raise ValueError("min_size must be at least 2.")
    component_path = Path(component_dir)
    output_path = Path(output_dir) if output_dir else component_path
    output_path.mkdir(parents=True, exist_ok=True)

    metadata = _read_json(component_path / "component_structure_metadata.json")
    artifacts = metadata.get("artifact_files", {})
    frame_rows = _read_csv(component_path / artifacts.get("frame_summary", "component_frame_summary.csv"))
    detail_rows = _read_csv(component_path / artifacts.get("component_detail", "component_detail.csv"))
    flow_rows = _read_csv(component_path / artifacts.get("component_flow", "component_flow_summary.csv"))

    threshold_text = str(threshold)
    frame_by_key = {
        (row.get("frame_index", ""), row.get("threshold", "")): row
        for row in frame_rows
        if row.get("threshold") == threshold_text
    }
    flow_by_source = _best_flow_by_source(flow_rows, threshold_text)
    dashboard_rows = []
    for row in detail_rows:
        if row.get("threshold") != threshold_text:
            continue
        if _int(row.get("size")) < min_size:
            continue
        frame = frame_by_key.get((row.get("frame_index", ""), row.get("threshold", "")), {})
        source_key = (row.get("frame_index", ""), row.get("component_id", ""))
        flow = flow_by_source.get(source_key, {})
        dashboard_rows.append(_dashboard_row(row, frame, flow, _forward_overlap_span(source_key, flow_by_source)))

    dashboard_rows = sorted(
        dashboard_rows,
        key=lambda row: (
            -(float(row.get("component_density") or 0)),
            -(int(row.get("size") or 0)),
            row.get("frame_label", ""),
            row.get("component_id", ""),
        ),
    )[:top_n]

    metadata_path = output_path / "component_dashboard_metadata.json"
    dashboard_path = output_path / "component_dashboard.csv"
    html_path = output_path / "component_dashboard.html"
    dashboard_metadata = {
        "artifact_files": {
            "metadata": metadata_path.name,
            "dashboard": dashboard_path.name,
            "html": html_path.name,
        },
        "mode": "descriptive_component_dashboard",
        "source_component_dir": str(component_path),
        "threshold": threshold_text,
        "min_size": min_size,
        "top_n": top_n,
        "relationship": metadata.get("relationship", "return_correlation"),
        "interpretation_note": (
            "Dashboard rows join same-window component structure with adjacent-window membership "
            "overlap. It does not align component structure with future returns."
        ),
        "disclaimer": (
            "Descriptive historical structure only; not investment advice, not a forecast, "
            "and not a recommendation."
        ),
    }
    metadata_path.write_text(
        json.dumps(dashboard_metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_csv(dashboard_path, _DASHBOARD_FIELDS, dashboard_rows)
    html_path.write_text(_render_html(dashboard_metadata, dashboard_rows), encoding="utf-8")
    return ComponentDashboardPaths(
        metadata_path=metadata_path,
        dashboard_path=dashboard_path,
        html_path=html_path,
    )


def _best_flow_by_source(flow_rows: list[dict[str, str]], threshold: str) -> dict[tuple[str, str], dict[str, str]]:
    result: dict[tuple[str, str], dict[str, str]] = {}
    for row in flow_rows:
        if row.get("threshold") != threshold:
            continue
        if not row.get("from_frame_index") or not row.get("source_component_id"):
            continue
        key = (row.get("from_frame_index", ""), row.get("source_component_id", ""))
        current = result.get(key)
        if current is None or _flow_rank(row) > _flow_rank(current):
            result[key] = row
    return result


def _flow_rank(row: dict[str, str]) -> tuple[float, int]:
    return (_float(row.get("jaccard")) or 0.0, _int(row.get("overlap_count")))


def _forward_overlap_span(source_key: tuple[str, str], flow_by_source: dict[tuple[str, str], dict[str, str]]) -> int:
    span = 1
    seen = {source_key}
    current = source_key
    while True:
        flow = flow_by_source.get(current)
        if not flow or not flow.get("to_frame_index") or not flow.get("target_component_id"):
            return span
        if (_float(flow.get("jaccard")) or 0.0) <= 0:
            return span
        current = (flow.get("to_frame_index", ""), flow.get("target_component_id", ""))
        if current in seen:
            return span
        seen.add(current)
        span += 1


def _dashboard_row(
    detail: dict[str, str],
    frame: dict[str, str],
    flow: dict[str, str],
    forward_overlap_span: int,
) -> dict[str, str]:
    return {
        "frame_index": detail.get("frame_index", ""),
        "window_frame_index": detail.get("window_frame_index", ""),
        "window_months": detail.get("window_months", ""),
        "frame_label": detail.get("frame_label", ""),
        "period_start": detail.get("period_start", ""),
        "period_end": detail.get("period_end", ""),
        "threshold": detail.get("threshold", ""),
        "component_id": detail.get("component_id", ""),
        "size": detail.get("size", ""),
        "component_density": detail.get("component_density", ""),
        "mean_internal_correlation": detail.get("mean_internal_correlation", ""),
        "mean_period_return": detail.get("mean_period_return", ""),
        "edge_count": detail.get("edge_count", ""),
        "possible_edge_count": detail.get("possible_edge_count", ""),
        "giant_component_share": frame.get("giant_component_share", ""),
        "market_strong_edge_ratio": frame.get("market_strong_edge_ratio", ""),
        "component_count": frame.get("component_count", ""),
        "singleton_count": frame.get("singleton_count", ""),
        "forward_event_type": flow.get("event_type", ""),
        "forward_overlap_span": str(forward_overlap_span),
        "forward_jaccard": flow.get("jaccard", ""),
        "forward_overlap_count": flow.get("overlap_count", ""),
        "forward_retention_ratio": flow.get("source_retention_ratio", ""),
        "forward_to_frame_label": flow.get("to_frame_label", ""),
        "forward_target_component_id": flow.get("target_component_id", ""),
        "forward_target_size": flow.get("target_size", ""),
        "forward_target_density": flow.get("target_component_density", ""),
        "forward_source_match_count": flow.get("source_match_count", ""),
        "forward_target_match_count": flow.get("target_match_count", ""),
        "top_symbols": detail.get("top_symbols", ""),
        "forward_target_top_symbols": flow.get("target_top_symbols", ""),
    }


def _render_html(metadata: dict[str, Any], rows: list[dict[str, str]]) -> str:
    header = "".join(f"<th>{html.escape(field)}</th>" for field in _DASHBOARD_FIELDS)
    body = "\n".join(
        "<tr>"
        + "".join(f"<td>{html.escape(str(row.get(field, '')))}</td>" for field in _DASHBOARD_FIELDS)
        + "</tr>"
        for row in rows
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Component Dashboard</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 24px; color: #172026; }}
    .note {{ max-width: 980px; color: #44515c; line-height: 1.45; }}
    table {{ border-collapse: collapse; font-size: 12px; min-width: 1400px; }}
    th, td {{ border: 1px solid #d7dde3; padding: 5px 7px; vertical-align: top; }}
    th {{ position: sticky; top: 0; background: #f3f6f8; text-align: left; }}
    .scroll {{ overflow-x: auto; border: 1px solid #d7dde3; }}
  </style>
</head>
<body>
  <h1>Component Dashboard</h1>
  <p class="note">Descriptive historical structure only. No future-return alignment, no lead-lag, no forecast, and no recommendation. Component ids are local to one window and threshold.</p>
  <p class="note">Threshold: {html.escape(str(metadata["threshold"]))}. Relationship: {html.escape(str(metadata["relationship"]))}. Rows join same-window component metrics with adjacent-window membership overlap.</p>
  <div class="scroll"><table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table></div>
</body>
</html>
"""


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _float(value: str | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _int(value: str | None) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(value)
    except ValueError:
        return 0
