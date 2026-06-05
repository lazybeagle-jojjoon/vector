from __future__ import annotations

import csv
import html
import json
from pathlib import Path
from typing import Any


def write_rolling_structure_report(
    scan_dir: str | Path,
    *,
    output_path: str | Path | None = None,
    max_cross_pairs: int = 40,
) -> Path:
    scan_path = Path(scan_dir)
    metadata = _read_json(scan_path / "rolling_structure_metadata.json")
    artifacts = metadata.get("artifact_files", {})
    group_rows = _read_csv(scan_path / artifacts.get("group_summary", "group_summary.csv"))
    cross_rows = _read_csv(scan_path / artifacts.get("cross_group_summary", "cross_group_summary.csv"))
    if not group_rows:
        raise ValueError(f"No group summary rows found in {scan_path}")

    frames = _frames(metadata, group_rows)
    group_baselines = _group_baselines(group_rows)
    group_names = _ordered_groups(group_rows)
    pair_names = _ordered_cross_pairs(cross_rows, max_cross_pairs=max_cross_pairs)

    output = Path(output_path) if output_path else scan_path / "rolling_structure_report.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        _render_html(
            metadata=metadata,
            frames=frames,
            group_rows=group_rows,
            cross_rows=cross_rows,
            group_baselines=group_baselines,
            group_names=group_names,
            pair_names=pair_names,
        ),
        encoding="utf-8",
    )
    return output


def _frames(metadata: dict[str, Any], group_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    if metadata.get("frames"):
        return [
            {
                "frame_index": str(frame.get("frame_index", index)),
                "frame_label": str(frame.get("frame_label") or f"frame {index + 1}"),
            }
            for index, frame in enumerate(metadata["frames"])
        ]
    seen: dict[str, str] = {}
    for row in group_rows:
        seen.setdefault(row["frame_index"], row.get("frame_label") or row["frame_index"])
    return [
        {"frame_index": frame_index, "frame_label": seen[frame_index]}
        for frame_index in sorted(seen, key=lambda value: int(value))
    ]


def _group_baselines(rows: list[dict[str, str]]) -> dict[str, dict[str, float | None]]:
    by_frame: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_frame.setdefault(row["frame_index"], []).append(row)
    baselines: dict[str, dict[str, float | None]] = {}
    for frame_index, frame_rows in by_frame.items():
        baselines[frame_index] = {
            "internal_mean_correlation": _weighted_mean(
                frame_rows,
                value_field="internal_mean_correlation",
                weight_field="internal_pair_count",
            ),
            "mean_period_return": _weighted_mean(
                frame_rows,
                value_field="mean_period_return",
                weight_field="return_observation_count",
            ),
            "top_percentile_cutoff": _first_number(frame_rows, "top_percentile_cutoff"),
        }
    return baselines


def _ordered_groups(rows: list[dict[str, str]]) -> list[str]:
    max_members: dict[str, int] = {}
    for row in rows:
        group = row.get("group_name", "")
        max_members[group] = max(max_members.get(group, 0), _int(row.get("member_count")))
    return sorted(max_members, key=lambda group: (-max_members[group], group == "missing", group))


def _ordered_cross_pairs(rows: list[dict[str, str]], *, max_cross_pairs: int) -> list[str]:
    scores: dict[str, float] = {}
    for row in rows:
        pair = _pair_name(row)
        scores[pair] = max(scores.get(pair, 0.0), abs(_number(row.get("top_percentile_edge_count")) or 0.0))
    return sorted(scores, key=lambda pair: (-scores[pair], pair))[:max_cross_pairs]


def _render_html(
    *,
    metadata: dict[str, Any],
    frames: list[dict[str, str]],
    group_rows: list[dict[str, str]],
    cross_rows: list[dict[str, str]],
    group_baselines: dict[str, dict[str, float | None]],
    group_names: list[str],
    pair_names: list[str],
) -> str:
    group_lookup = {
        (row["frame_index"], row["group_name"]): row
        for row in group_rows
    }
    cross_lookup = {
        (row["frame_index"], _pair_name(row)): row
        for row in cross_rows
    }
    disclaimer = metadata.get(
        "disclaimer",
        "Descriptive historical structure only; not investment advice, not a forecast, and not a recommendation.",
    )
    missing_note = metadata.get(
        "missing_group_note",
        "The 'missing' group is a source metadata gap bucket, not a real sector or industry label.",
    )
    return "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '<meta charset="utf-8">',
            "<title>Rolling Structure Heatmap Report</title>",
            "<style>",
            _CSS,
            "</style>",
            "</head>",
            "<body>",
            "<main>",
            "<h1>Rolling Structure Heatmap Report</h1>",
            "<p class=\"note\">This is a mechanical visualization of descriptive rolling structure tables. "
            "It is not investment advice, not a forecast, and not a recommendation.</p>",
            f"<p class=\"note\">{html.escape(str(disclaimer))}</p>",
            "<section>",
            "<h2>Regime baseline</h2>",
            "<p>Several sectors tightening at the same time can reflect a market-wide correlation regime, "
            "not sector-specific structure. Compare each row against the baseline before reading a sector move.</p>",
            f"<p>{html.escape(str(missing_note))}</p>",
            _baseline_table(frames, group_baselines),
            "</section>",
            "<section>",
            "<h2>Internal cohesion vs baseline</h2>",
            "<p>Cell value is sector internal mean correlation minus the same-window market baseline.</p>",
            _group_heatmap(
                frames=frames,
                group_names=group_names,
                group_lookup=group_lookup,
                group_baselines=group_baselines,
                value_field="internal_mean_correlation",
                baseline_field="internal_mean_correlation",
                formatter=_format_number,
            ),
            "</section>",
            "<section>",
            "<h2>Period return vs baseline</h2>",
            "<p>Cell value is sector period return minus the same-window market baseline return.</p>",
            _group_heatmap(
                frames=frames,
                group_names=group_names,
                group_lookup=group_lookup,
                group_baselines=group_baselines,
                value_field="mean_period_return",
                baseline_field="mean_period_return",
                formatter=_format_percent,
            ),
            "</section>",
            "<section>",
            "<h2>Cross-sector top-percentile links</h2>",
            "<p>Rows are mechanically selected by largest observed top-percentile edge count. "
            "This is a connection-density view, not a prediction and not a sector taxonomy.</p>",
            _cross_heatmap(
                frames=frames,
                pair_names=pair_names,
                cross_lookup=cross_lookup,
            ),
            "</section>",
            "</main>",
            "</body>",
            "</html>",
        ]
    )


def _baseline_table(frames: list[dict[str, str]], baselines: dict[str, dict[str, float | None]]) -> str:
    header = "".join(f"<th>{html.escape(frame['frame_label'])}</th>" for frame in frames)
    cohesion = "".join(
        f"<td>{_format_number(baselines.get(frame['frame_index'], {}).get('internal_mean_correlation'))}</td>"
        for frame in frames
    )
    returns = "".join(
        f"<td>{_format_percent(baselines.get(frame['frame_index'], {}).get('mean_period_return'))}</td>"
        for frame in frames
    )
    cutoff = "".join(
        f"<td>{_format_number(baselines.get(frame['frame_index'], {}).get('top_percentile_cutoff'))}</td>"
        for frame in frames
    )
    return (
        '<div class="table-wrap"><table class="baseline"><thead><tr><th>Market baseline</th>'
        f"{header}</tr></thead><tbody>"
        f"<tr><th>Internal cohesion</th>{cohesion}</tr>"
        f"<tr><th>Period return</th>{returns}</tr>"
        f"<tr><th>Top-percentile cutoff</th>{cutoff}</tr>"
        "</tbody></table></div>"
    )


def _group_heatmap(
    *,
    frames: list[dict[str, str]],
    group_names: list[str],
    group_lookup: dict[tuple[str, str], dict[str, str]],
    group_baselines: dict[str, dict[str, float | None]],
    value_field: str,
    baseline_field: str,
    formatter,
) -> str:
    rows = []
    header = "".join(f"<th>{html.escape(frame['frame_label'])}</th>" for frame in frames)
    for group in group_names:
        cells = []
        for frame in frames:
            row = group_lookup.get((frame["frame_index"], group), {})
            value = _number(row.get(value_field))
            baseline = group_baselines.get(frame["frame_index"], {}).get(baseline_field)
            delta = value - baseline if value is not None and baseline is not None else None
            title = (
                f"{group} | {frame['frame_label']} | value={formatter(value)} | "
                f"baseline={formatter(baseline)} | delta={formatter(delta)}"
            )
            cells.append(_cell(delta, title=title, formatter=formatter))
        rows.append(f"<tr><th>{html.escape(group)}</th>{''.join(cells)}</tr>")
    return (
        '<div class="table-wrap"><table class="heatmap"><thead><tr><th>Group</th>'
        f"{header}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def _cross_heatmap(
    *,
    frames: list[dict[str, str]],
    pair_names: list[str],
    cross_lookup: dict[tuple[str, str], dict[str, str]],
) -> str:
    rows = []
    header = "".join(f"<th>{html.escape(frame['frame_label'])}</th>" for frame in frames)
    for pair in pair_names:
        cells = []
        for frame in frames:
            row = cross_lookup.get((frame["frame_index"], pair), {})
            value = _number(row.get("top_percentile_edge_count"))
            title = f"{pair} | {frame['frame_label']} | top-percentile edges={_format_number(value)}"
            cells.append(_cell(value, title=title, formatter=_format_number, scale=1000.0))
        rows.append(f"<tr><th>{html.escape(pair)}</th>{''.join(cells)}</tr>")
    return (
        '<div class="table-wrap"><table class="heatmap"><thead><tr><th>Pair</th>'
        f"{header}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>"
    )


def _cell(value: float | None, *, title: str, formatter, scale: float = 0.2) -> str:
    if value is None:
        return '<td class="cell missing" title="missing">NA</td>'
    magnitude = min(abs(value) / scale, 1.0)
    if value > 0:
        color = f"rgba(17, 122, 101, {0.18 + magnitude * 0.72:.3f})"
    elif value < 0:
        color = f"rgba(178, 34, 34, {0.18 + magnitude * 0.72:.3f})"
    else:
        color = "rgba(229, 231, 235, 0.75)"
    return (
        f'<td class="cell" style="background:{color}" title="{html.escape(title)}">'
        f"{html.escape(formatter(value))}</td>"
    )


def _weighted_mean(rows: list[dict[str, str]], *, value_field: str, weight_field: str) -> float | None:
    numerator = 0.0
    denominator = 0.0
    for row in rows:
        value = _number(row.get(value_field))
        weight = _number(row.get(weight_field))
        if value is None or weight is None or weight <= 0:
            continue
        numerator += value * weight
        denominator += weight
    if denominator == 0:
        return None
    return numerator / denominator


def _first_number(rows: list[dict[str, str]], field: str) -> float | None:
    for row in rows:
        value = _number(row.get(field))
        if value is not None:
            return value
    return None


def _pair_name(row: dict[str, str]) -> str:
    return f"{row.get('group_a', '')} / {row.get('group_b', '')}"


def _number(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    number = _number(value)
    return int(number or 0)


def _format_number(value: float | None) -> str:
    if value is None:
        return "NA"
    return f"{value:.3f}"


def _format_percent(value: float | None) -> str:
    if value is None:
        return "NA"
    return f"{value * 100:.1f}%"


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"Rolling structure metadata does not exist: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise ValueError(f"Rolling structure CSV does not exist: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


_CSS = """
:root {
  color-scheme: light;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: #f6f7f9;
  color: #172026;
}
body {
  margin: 0;
}
main {
  max-width: 1180px;
  margin: 0 auto;
  padding: 28px;
}
h1, h2 {
  letter-spacing: 0;
}
.note {
  color: #46515c;
}
section {
  margin-top: 28px;
}
.table-wrap {
  overflow: auto;
  border: 1px solid #d7dde3;
  background: #ffffff;
}
table {
  border-collapse: collapse;
  font-size: 12px;
  width: max-content;
  min-width: 100%;
}
th, td {
  border: 1px solid #e5e9ee;
  padding: 6px 8px;
  white-space: nowrap;
}
th {
  background: #f0f3f6;
  text-align: left;
  position: sticky;
  left: 0;
  z-index: 1;
}
thead th {
  position: sticky;
  top: 0;
  z-index: 2;
}
thead th:first-child {
  z-index: 3;
}
.cell {
  text-align: right;
  min-width: 70px;
}
.missing {
  color: #7b8794;
  background: #f4f5f6;
}
"""
