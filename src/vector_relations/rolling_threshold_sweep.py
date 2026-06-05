from __future__ import annotations

import csv
import html
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .global_map import _filter_value, _read_node_metadata, _write_csv
from .rolling_structure import (
    _build_return_matrix,
    _format_float,
    _groups_by_security,
    _period_returns_from_matrix,
    _reject_duplicate_symbols,
    _require_columns,
    _rolling_windows,
    _top_percentile_cutoff,
)


@dataclass(frozen=True)
class ThresholdSweepOutputPaths:
    metadata_path: Path
    market_summary_path: Path
    group_summary_path: Path
    cross_group_summary_path: Path
    html_path: Path


_MARKET_FIELDS = [
    "frame_index",
    "frame_label",
    "period_start",
    "period_end",
    "threshold",
    "market_pair_count",
    "market_strong_edge_count",
    "market_strong_edge_ratio",
    "top_percentile_cutoff",
]

_GROUP_FIELDS = [
    "frame_index",
    "frame_label",
    "period_start",
    "period_end",
    "threshold",
    "group_column",
    "group_name",
    "member_count",
    "mean_period_return",
    "internal_pair_count",
    "internal_strong_edge_count",
    "internal_strong_edge_ratio",
    "market_strong_edge_ratio",
    "internal_strong_edge_ratio_normalized",
]

_CROSS_FIELDS = [
    "frame_index",
    "frame_label",
    "period_start",
    "period_end",
    "threshold",
    "group_column",
    "group_a",
    "group_b",
    "cross_pair_count",
    "cross_strong_edge_count",
    "cross_strong_edge_ratio",
    "market_strong_edge_ratio",
    "cross_strong_edge_ratio_normalized",
]


def write_threshold_sweep_from_prices(
    *,
    prices: Any,
    output_dir: str | Path,
    node_metadata_path: str | Path | None = None,
    metadata_by_symbol: dict[str, dict[str, str]] | None = None,
    market: str,
    rolling_start: str,
    rolling_end: str,
    window_months: int = 6,
    stride_months: int = 1,
    price_column: str = "adjusted_close",
    min_observations: int = 60,
    group_column: str = "sector",
    thresholds: list[float] | tuple[float, ...] = (0.5, 0.6, 0.7),
    top_percentile: float = 0.05,
    source_metadata: dict[str, Any] | None = None,
) -> ThresholdSweepOutputPaths:
    pd = _import_pandas()
    np = _import_numpy()
    thresholds = _validate_thresholds(thresholds)
    if not 0 < top_percentile < 1:
        raise ValueError("top_percentile must be between 0 and 1.")
    if min_observations < 2:
        raise ValueError("min_observations must be at least 2.")
    _require_columns(prices, {"security_id", "symbol", "date", price_column}, "prices")
    if metadata_by_symbol is None:
        if node_metadata_path is None:
            raise ValueError("Provide node_metadata_path or metadata_by_symbol.")
        metadata_by_symbol = _read_node_metadata(Path(node_metadata_path))

    windows = _rolling_windows(
        pd,
        rolling_start=rolling_start,
        rolling_end=rolling_end,
        window_months=window_months,
        stride_months=stride_months,
    )
    if not windows:
        raise ValueError("no complete rolling windows fit inside the requested date range.")

    prepared = prices.copy()
    prepared["_rolling_date"] = pd.to_datetime(prepared["date"], errors="coerce")
    prepared = prepared.dropna(subset=["security_id", "symbol", "_rolling_date", price_column])
    prepared = prepared[prepared[price_column] > 0]
    if prepared.empty:
        raise ValueError("no price rows remain after filtering.")

    frames: list[dict[str, Any]] = []
    market_rows: list[dict[str, Any]] = []
    group_rows: list[dict[str, Any]] = []
    cross_rows: list[dict[str, Any]] = []
    for frame_index, (period_start, period_end) in enumerate(windows):
        frame = _summarize_window(
            pd=pd,
            np=np,
            prices=prepared,
            frame_index=frame_index,
            period_start=period_start,
            period_end=period_end,
            price_column=price_column,
            min_observations=min_observations,
            metadata_by_symbol=metadata_by_symbol,
            group_column=group_column,
            thresholds=thresholds,
            top_percentile=top_percentile,
        )
        frames.append(frame["metadata"])
        market_rows.extend(frame["market_rows"])
        group_rows.extend(frame["group_rows"])
        cross_rows.extend(frame["cross_rows"])

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    metadata_path = output_path / "threshold_sweep_metadata.json"
    market_summary_path = output_path / "threshold_market_summary.csv"
    group_summary_path = output_path / "threshold_group_summary.csv"
    cross_group_summary_path = output_path / "threshold_cross_group_summary.csv"
    html_path = output_path / "threshold_sweep_report.html"
    metadata = {
        "artifact_files": {
            "metadata": metadata_path.name,
            "market_summary": market_summary_path.name,
            "group_summary": group_summary_path.name,
            "cross_group_summary": cross_group_summary_path.name,
            "html": html_path.name,
        },
        "mode": "descriptive_threshold_sweep",
        "relationship": "return_correlation_distance",
        "market": market.upper(),
        "rolling_start": rolling_start,
        "rolling_end": rolling_end,
        "window_months": window_months,
        "stride_months": stride_months,
        "price_column": price_column,
        "min_observations": min_observations,
        "group_column": group_column,
        "thresholds": thresholds,
        "top_percentile": top_percentile,
        "frame_count": len(frames),
        "frames": frames,
        "interpretation_note": (
            "Fixed thresholds are zoom levels. Cross-window interpretation should use "
            "baseline-normalized ratios, because raw strong-edge counts move with the "
            "market-wide correlation regime."
        ),
        "brightline": (
            "This sweep describes structure-at-t only. Aligning structure-at-t to "
            "return-at-t+1 is predictive lead-lag research and is out of scope."
        ),
        "disclaimer": (
            "Descriptive historical structure only; not investment advice, not a forecast, "
            "and not a recommendation."
        ),
        **(source_metadata or {}),
    }
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_csv(market_summary_path, _MARKET_FIELDS, market_rows)
    _write_csv(group_summary_path, _GROUP_FIELDS, group_rows)
    _write_csv(cross_group_summary_path, _CROSS_FIELDS, cross_rows)
    html_path.write_text(
        _render_html(
            metadata=metadata,
            market_rows=market_rows,
            group_rows=group_rows,
            cross_rows=cross_rows,
        ),
        encoding="utf-8",
    )
    return ThresholdSweepOutputPaths(
        metadata_path=metadata_path,
        market_summary_path=market_summary_path,
        group_summary_path=group_summary_path,
        cross_group_summary_path=cross_group_summary_path,
        html_path=html_path,
    )


def _summarize_window(
    *,
    pd: Any,
    np: Any,
    prices: Any,
    frame_index: int,
    period_start: str,
    period_end: str,
    price_column: str,
    min_observations: int,
    metadata_by_symbol: dict[str, dict[str, str]],
    group_column: str,
    thresholds: list[float],
    top_percentile: float,
) -> dict[str, Any]:
    frame_prices = prices[
        (prices["_rolling_date"] >= pd.Timestamp(period_start))
        & (prices["_rolling_date"] <= pd.Timestamp(period_end))
    ].copy()
    if frame_prices.empty:
        raise ValueError(f"no price rows remain for rolling window {period_start} to {period_end}.")
    symbol_by_security = (
        frame_prices.sort_values(["security_id", "_rolling_date"])
        .groupby("security_id", sort=True)["symbol"]
        .last()
        .astype(str)
        .to_dict()
    )
    returns = _build_return_matrix(frame_prices, price_column)
    returns = returns.dropna(axis=1, thresh=min_observations)
    if len(returns.columns) < 2:
        raise ValueError(
            f"at least two securities need {min_observations} return observations "
            f"for rolling window {period_start} to {period_end}."
        )
    symbol_by_security = {
        security_id: symbol_by_security.get(security_id, security_id)
        for security_id in returns.columns
    }
    _reject_duplicate_symbols(returns.columns, symbol_by_security)
    corr = returns.corr(min_periods=min_observations)
    corr.index = corr.index.astype(str)
    corr.columns = corr.columns.astype(str)
    universe = [
        {"security_id": str(security_id), "symbol": str(symbol_by_security[security_id])}
        for security_id in returns.columns
    ]
    groups_by_security = _groups_by_security(
        universe=universe,
        metadata_by_symbol=metadata_by_symbol,
        group_column=group_column,
    )
    group_to_ids: dict[str, list[str]] = {}
    for security_id in corr.columns:
        group = groups_by_security.get(str(security_id), "missing")
        group_to_ids.setdefault(group, []).append(str(security_id))

    market_values = _upper_triangle_values(np, corr)
    top_cutoff = _top_percentile_cutoff(np, corr, top_percentile)
    returns_by_security = _period_returns_from_matrix(returns)
    frame_label = f"{period_start} to {period_end}"
    common = {
        "frame_index": str(frame_index),
        "frame_label": frame_label,
        "period_start": period_start,
        "period_end": period_end,
    }
    market_rows = []
    group_rows = []
    cross_rows = []
    for threshold in thresholds:
        market_count = _count_at_least(market_values, threshold)
        market_ratio = _ratio(market_count, len(market_values))
        market_rows.append(
            {
                **common,
                "threshold": _format_threshold(threshold),
                "market_pair_count": len(market_values),
                "market_strong_edge_count": market_count,
                "market_strong_edge_ratio": _format_float(market_ratio),
                "top_percentile_cutoff": _format_float(top_cutoff),
            }
        )
        for group in sorted(group_to_ids):
            ids = group_to_ids[group]
            values = _internal_values(np, corr, ids)
            count = _count_at_least(values, threshold)
            strong_ratio = _ratio(count, len(values))
            return_values = [returns_by_security.get(security_id) for security_id in ids]
            return_values = [value for value in return_values if value is not None]
            group_rows.append(
                {
                    **common,
                    "threshold": _format_threshold(threshold),
                    "group_column": group_column,
                    "group_name": group,
                    "member_count": len(ids),
                    "mean_period_return": _format_float(_mean(return_values)),
                    "internal_pair_count": len(values),
                    "internal_strong_edge_count": count,
                    "internal_strong_edge_ratio": _format_float(strong_ratio),
                    "market_strong_edge_ratio": _format_float(market_ratio),
                    "internal_strong_edge_ratio_normalized": _format_float(
                        _normalized(strong_ratio, market_ratio)
                    ),
                }
            )
        groups = sorted(group_to_ids)
        for left_index, group_a in enumerate(groups):
            for group_b in groups[left_index + 1 :]:
                values = _cross_values(np, corr, group_to_ids[group_a], group_to_ids[group_b])
                count = _count_at_least(values, threshold)
                strong_ratio = _ratio(count, len(values))
                cross_rows.append(
                    {
                        **common,
                        "threshold": _format_threshold(threshold),
                        "group_column": group_column,
                        "group_a": group_a,
                        "group_b": group_b,
                        "cross_pair_count": len(values),
                        "cross_strong_edge_count": count,
                        "cross_strong_edge_ratio": _format_float(strong_ratio),
                        "market_strong_edge_ratio": _format_float(market_ratio),
                        "cross_strong_edge_ratio_normalized": _format_float(
                            _normalized(strong_ratio, market_ratio)
                        ),
                    }
                )
    return {
        "metadata": {
            "frame_index": frame_index,
            "frame_label": frame_label,
            "period_start": period_start,
            "period_end": period_end,
            "security_count": len(corr.columns),
            "top_percentile_cutoff": top_cutoff,
        },
        "market_rows": market_rows,
        "group_rows": group_rows,
        "cross_rows": cross_rows,
    }


def _render_html(
    *,
    metadata: dict[str, Any],
    market_rows: list[dict[str, Any]],
    group_rows: list[dict[str, Any]],
    cross_rows: list[dict[str, Any]],
) -> str:
    thresholds = [str(value) for value in metadata["thresholds"]]
    frames = [str(frame["frame_label"]) for frame in metadata["frames"]]
    lines = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        "<title>Threshold Sweep Report</title>",
        "<style>",
        _CSS,
        "</style>",
        "</head>",
        "<body><main>",
        "<h1>Threshold Sweep Report</h1>",
        "<p class=\"note\">This report is descriptive only, not investment advice, not a forecast, and not a recommendation.</p>",
        "<p class=\"note\">fixed thresholds are zoom levels. Raw counts are market-regime sensitive; use baseline-normalized ratio for cross-window reading.</p>",
        "<h2>Market regime density line chart</h2>",
        "<p>Read this first: shaded windows are the highest market-density decile; spikes mean many pairs crossed the fixed threshold in the same window.</p>",
        _market_regime_chart(market_rows),
        "<h2>Market strong-edge baseline</h2>",
        "<p>Market baseline is the share of all finite pairs with correlation at or above each threshold.</p>",
        _market_table(market_rows),
        "<h2>Sector internal normalized ratios</h2>",
        "<p>Read ratios with member and edge counts. A high ratio from very few pairs can be unstable.</p>",
        _summary_table(
            group_rows,
            key_fields=["threshold", "group_name"],
            support_fields=["member_count", "internal_pair_count", "internal_strong_edge_count"],
            value_field="internal_strong_edge_ratio_normalized",
            max_rows=80,
        ),
        "<h2>Cross-sector normalized ratios</h2>",
        "<p>Read cross ratios with pair and edge counts. They describe same-window structure only.</p>",
        _summary_table(
            cross_rows,
            key_fields=["threshold", "group_a", "group_b"],
            support_fields=["cross_pair_count", "cross_strong_edge_count"],
            value_field="cross_strong_edge_ratio_normalized",
            max_rows=120,
        ),
        "<h2>Notes</h2>",
        "<ul>",
        f"<li>Relationship: {html.escape(metadata['relationship'])}</li>",
        f"<li>Thresholds: {html.escape(', '.join(thresholds))}</li>",
        f"<li>Frames: {html.escape(str(len(frames)))}</li>",
        "<li>baseline-normalized ratio = group/cross strong-edge density divided by same-window market strong-edge density.</li>",
        "<li>When same-window market density is small, normalized ratios can be noisy; check raw edge counts and member/pair counts before interpreting.</li>",
        "<li>Do not align this structure-at-t output with future returns in this report.</li>",
        "</ul>",
        "</main></body></html>",
    ]
    return "\n".join(lines)


def _market_regime_chart(rows: list[dict[str, Any]]) -> str:
    by_threshold: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_threshold.setdefault(str(row["threshold"]), []).append(row)
    thresholds = sorted(by_threshold, key=float)
    all_values = [
        _number(row.get("market_strong_edge_ratio")) or 0.0
        for threshold in thresholds
        for row in by_threshold[threshold]
    ]
    max_value = max(all_values) if all_values else 0.0
    if max_value <= 0:
        max_value = 1.0

    width = 980
    height = 260
    padding_left = 56
    padding_right = 24
    padding_top = 24
    padding_bottom = 46
    plot_width = width - padding_left - padding_right
    plot_height = height - padding_top - padding_bottom
    colors = ["#0f766e", "#2563eb", "#b45309", "#9333ea", "#be123c"]
    stress_indices = _stress_frame_indices(by_threshold)
    frame_count = max((len(rows) for rows in by_threshold.values()), default=0)
    denominator = max(frame_count - 1, 1)
    band_width = plot_width / max(frame_count, 1)
    chart_parts = [
        '<div class="chart-wrap">',
        f'<svg class="regime-chart" viewBox="0 0 {width} {height}" role="img" aria-label="Market strong-edge density by threshold">',
    ]
    for frame_index in stress_indices:
        x = padding_left + (frame_index / denominator) * plot_width - band_width / 2
        x = max(padding_left, min(x, width - padding_right - band_width))
        chart_parts.append(
            f'<rect class="stress-window" x="{x:.2f}" y="{padding_top}" '
            f'width="{band_width:.2f}" height="{plot_height}"/>'
        )
    chart_parts.extend(
        [
        f'<line x1="{padding_left}" y1="{padding_top}" x2="{padding_left}" y2="{height - padding_bottom}" class="axis"/>',
        f'<line x1="{padding_left}" y1="{height - padding_bottom}" x2="{width - padding_right}" y2="{height - padding_bottom}" class="axis"/>',
        f'<text x="8" y="{padding_top + 4}" class="axis-label">{html.escape(_format_percent(max_value))}</text>',
        f'<text x="8" y="{height - padding_bottom}" class="axis-label">0.0%</text>',
        ]
    )
    for index, threshold in enumerate(thresholds):
        series = sorted(by_threshold[threshold], key=lambda row: int(row["frame_index"]))
        points = []
        denominator = max(len(series) - 1, 1)
        for point_index, row in enumerate(series):
            value = _number(row.get("market_strong_edge_ratio")) or 0.0
            x = padding_left + (point_index / denominator) * plot_width
            y = padding_top + (1.0 - (value / max_value)) * plot_height
            points.append(f"{x:.2f},{y:.2f}")
        color = colors[index % len(colors)]
        chart_parts.append(
            f'<polyline points="{" ".join(points)}" fill="none" stroke="{color}" '
            'stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>'
        )
        legend_x = padding_left + index * 120
        legend_y = height - 14
        chart_parts.append(f'<circle cx="{legend_x}" cy="{legend_y - 4}" r="4" fill="{color}"/>')
        chart_parts.append(
            f'<text x="{legend_x + 8}" y="{legend_y}" class="legend">corr&gt;={html.escape(threshold)}</text>'
        )
    chart_parts.extend(["</svg>", "</div>"])
    return "".join(chart_parts)


def _stress_frame_indices(by_threshold: dict[str, list[dict[str, Any]]]) -> set[int]:
    max_by_frame: dict[int, float] = {}
    for rows in by_threshold.values():
        for row in rows:
            frame_index = int(row["frame_index"])
            value = _number(row.get("market_strong_edge_ratio")) or 0.0
            max_by_frame[frame_index] = max(max_by_frame.get(frame_index, 0.0), value)
    if not max_by_frame:
        return set()
    values = sorted(max_by_frame.values())
    cutoff_index = max(0, int(len(values) * 0.9) - 1)
    cutoff = values[cutoff_index]
    return {frame_index for frame_index, value in max_by_frame.items() if value >= cutoff and value > 0}


def _market_table(rows: list[dict[str, Any]]) -> str:
    return _plain_table(
        rows,
        fields=[
            "frame_label",
            "threshold",
            "market_pair_count",
            "market_strong_edge_count",
            "market_strong_edge_ratio",
            "top_percentile_cutoff",
        ],
        max_rows=500,
    )


def _summary_table(
    rows: list[dict[str, Any]],
    *,
    key_fields: list[str],
    support_fields: list[str],
    value_field: str,
    max_rows: int,
) -> str:
    ranked = sorted(
        [row for row in rows if row.get(value_field) not in {"", None}],
        key=lambda row: float(row[value_field]),
        reverse=True,
    )[:max_rows]
    fields = ["frame_label", *key_fields, *support_fields, value_field, "market_strong_edge_ratio"]
    return _plain_table(ranked, fields=fields, max_rows=max_rows)


def _plain_table(rows: list[dict[str, Any]], *, fields: list[str], max_rows: int) -> str:
    header = "".join(f"<th>{html.escape(field)}</th>" for field in fields)
    body = []
    for row in rows[:max_rows]:
        body.append(
            "<tr>"
            + "".join(f"<td>{html.escape(str(row.get(field, '')))}</td>" for field in fields)
            + "</tr>"
        )
    return (
        '<div class="table-wrap"><table><thead><tr>'
        f"{header}</tr></thead><tbody>{''.join(body)}</tbody></table></div>"
    )


def _validate_thresholds(thresholds: list[float] | tuple[float, ...]) -> list[float]:
    values = sorted({float(value) for value in thresholds})
    if not values:
        raise ValueError("at least one threshold is required.")
    invalid = [value for value in values if value < -1 or value > 1]
    if invalid:
        raise ValueError("thresholds must be between -1 and 1.")
    return values


def _number(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _format_percent(value: float | None) -> str:
    if value is None:
        return "NA"
    return f"{value * 100:.1f}%"


def _upper_triangle_values(np: Any, corr: Any) -> list[float]:
    matrix = corr.to_numpy(dtype=float)
    if matrix.shape[0] < 2:
        return []
    values = matrix[np.triu_indices(matrix.shape[0], k=1)]
    return _finite_values(np, values)


def _internal_values(np: Any, corr: Any, ids: list[str]) -> list[float]:
    if len(ids) < 2:
        return []
    matrix = corr.loc[ids, ids].to_numpy(dtype=float)
    values = matrix[np.triu_indices(matrix.shape[0], k=1)]
    return _finite_values(np, values)


def _cross_values(np: Any, corr: Any, left_ids: list[str], right_ids: list[str]) -> list[float]:
    if not left_ids or not right_ids:
        return []
    values = corr.loc[left_ids, right_ids].to_numpy(dtype=float).reshape(-1)
    return _finite_values(np, values)


def _finite_values(np: Any, values: Any) -> list[float]:
    return [float(value) for value in values[np.isfinite(values)]]


def _count_at_least(values: list[float], threshold: float) -> int:
    return sum(1 for value in values if value >= threshold)


def _ratio(count: int, total: int) -> float | None:
    if total <= 0:
        return None
    return count / total


def _normalized(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None or baseline == 0:
        return None
    return value / baseline


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _format_threshold(value: float) -> str:
    return f"{value:.12g}"


def _import_pandas():
    try:
        import pandas as pd
    except ModuleNotFoundError as exc:
        raise ValueError(
            "threshold sweep requires pandas. Run with: "
            "uv run --no-project --with pandas python -m vector_relations.rolling_threshold_sweep_cli ..."
        ) from exc
    return pd


def _import_numpy():
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        raise ValueError(
            "threshold sweep requires numpy. Run with: "
            "uv run --no-project --with pandas --with numpy python -m vector_relations.rolling_threshold_sweep_cli ..."
        ) from exc
    return np


_CSS = """
:root {
  color-scheme: light;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  background: #f6f7f9;
  color: #172026;
}
body { margin: 0; }
main { max-width: 1180px; margin: 0 auto; padding: 28px; }
h1, h2 { letter-spacing: 0; }
.note { color: #46515c; }
.table-wrap { overflow: auto; border: 1px solid #d7dde3; background: #fff; margin-bottom: 24px; }
table { border-collapse: collapse; font-size: 12px; min-width: 100%; }
th, td { border: 1px solid #e5e9ee; padding: 6px 8px; white-space: nowrap; }
th { background: #f0f3f6; text-align: left; }
.chart-wrap { border: 1px solid #d7dde3; background: #fff; margin-bottom: 24px; overflow: auto; }
.regime-chart { display: block; min-width: 860px; width: 100%; height: auto; }
.axis { stroke: #9aa4af; stroke-width: 1; }
.stress-window { fill: #f97316; opacity: 0.12; }
.axis-label, .legend { fill: #46515c; font-size: 12px; }
"""
