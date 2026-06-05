from __future__ import annotations

import html
import json
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Any

from .component_structure import _component_detail_row, _components_for_threshold
from .global_map import _write_csv
from .rolling_structure import (
    _build_return_matrix,
    _format_float,
    _period_returns_from_matrix,
    _reject_duplicate_symbols,
    _require_columns,
    _rolling_windows,
)
from .rolling_threshold_sweep import (
    _count_at_least,
    _format_threshold,
    _import_numpy,
    _import_pandas,
    _mean,
    _ratio,
    _upper_triangle_values,
    _validate_thresholds,
    _window_months_values,
)


@dataclass(frozen=True)
class ComponentPairSummaryOutputPaths:
    metadata_path: Path
    pair_summary_path: Path
    html_path: Path


_PAIR_FIELDS = [
    "frame_index",
    "window_frame_index",
    "window_months",
    "frame_label",
    "period_start",
    "period_end",
    "component_threshold",
    "cross_edge_threshold",
    "market_pair_count",
    "market_cross_edge_count",
    "market_cross_edge_density",
    "market_mean_correlation",
    "component_a_id",
    "component_b_id",
    "component_a_size",
    "component_b_size",
    "component_a_density",
    "component_b_density",
    "component_a_mean_internal_correlation",
    "component_b_mean_internal_correlation",
    "component_a_mean_period_return",
    "component_b_mean_period_return",
    "cross_pair_count",
    "mean_cross_correlation",
    "median_cross_correlation",
    "mean_cross_correlation_minus_market",
    "cross_edge_count",
    "cross_edge_density",
    "normalized_cross_edge_density",
    "component_a_top_symbols",
    "component_b_top_symbols",
]


def write_component_pair_summary_from_prices(
    *,
    prices: Any,
    output_dir: str | Path,
    market: str,
    rolling_start: str,
    rolling_end: str,
    window_months: int = 6,
    window_months_list: list[int] | tuple[int, ...] | None = None,
    stride_months: int = 1,
    price_column: str = "adjusted_close",
    min_observations: int = 60,
    component_threshold: float = 0.7,
    cross_edge_threshold: float = 0.5,
    min_component_size: int = 5,
    min_component_density: float = 0.0,
    min_cross_pair_count: int = 10,
    top_n_pairs: int = 200,
    max_top_symbols: int = 12,
    source_metadata: dict[str, Any] | None = None,
) -> ComponentPairSummaryOutputPaths:
    pd = _import_pandas()
    np = _import_numpy()
    _validate_component_pair_args(
        component_threshold=component_threshold,
        cross_edge_threshold=cross_edge_threshold,
        min_component_size=min_component_size,
        min_component_density=min_component_density,
        min_cross_pair_count=min_cross_pair_count,
        top_n_pairs=top_n_pairs,
        max_top_symbols=max_top_symbols,
    )
    window_months_values = _window_months_values(window_months, window_months_list)
    _require_columns(prices, {"security_id", "symbol", "date", price_column}, "prices")

    prepared = prices.copy()
    prepared["_rolling_date"] = pd.to_datetime(prepared["date"], errors="coerce")
    prepared = prepared.dropna(subset=["security_id", "symbol", "_rolling_date", price_column])
    prepared = prepared[prepared[price_column] > 0]
    if prepared.empty:
        raise ValueError("no price rows remain after filtering.")

    pair_rows: list[dict[str, Any]] = []
    frame_metadata: list[dict[str, Any]] = []
    frame_index = 0
    for window_months_value in window_months_values:
        windows = _rolling_windows(
            pd,
            rolling_start=rolling_start,
            rolling_end=rolling_end,
            window_months=window_months_value,
            stride_months=stride_months,
        )
        if not windows:
            raise ValueError("no complete rolling windows fit inside the requested date range.")
        for window_frame_index, (period_start, period_end) in enumerate(windows):
            frame = _summarize_pair_window(
                pd=pd,
                np=np,
                prices=prepared,
                frame_index=frame_index,
                window_frame_index=window_frame_index,
                window_months=window_months_value,
                period_start=period_start,
                period_end=period_end,
                price_column=price_column,
                min_observations=min_observations,
                component_threshold=component_threshold,
                cross_edge_threshold=cross_edge_threshold,
                min_component_size=min_component_size,
                min_component_density=min_component_density,
                min_cross_pair_count=min_cross_pair_count,
                top_n_pairs=top_n_pairs,
                max_top_symbols=max_top_symbols,
            )
            frame_metadata.append(frame["metadata"])
            pair_rows.extend(frame["pair_rows"])
            frame_index += 1

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    metadata_path = output_path / "component_pair_summary_metadata.json"
    pair_summary_path = output_path / "component_pair_summary.csv"
    html_path = output_path / "component_pair_summary.html"
    metadata = {
        "artifact_files": {
            "metadata": metadata_path.name,
            "pair_summary": pair_summary_path.name,
            "html": html_path.name,
        },
        "mode": "descriptive_component_pair_summary",
        "relationship": "return_correlation",
        "market": market.upper(),
        "rolling_start": rolling_start,
        "rolling_end": rolling_end,
        "window_months": window_months,
        "window_months_values": window_months_values,
        "stride_months": stride_months,
        "price_column": price_column,
        "min_observations": min_observations,
        "component_threshold": component_threshold,
        "cross_edge_threshold": cross_edge_threshold,
        "min_component_size": min_component_size,
        "min_component_density": min_component_density,
        "min_cross_pair_count": min_cross_pair_count,
        "top_n_pairs": top_n_pairs,
        "frame_count": len(frame_metadata),
        "frames": frame_metadata,
        "interpretation_note": (
            "This table describes same-window component-to-component relationships only. "
            "Components are defined with the component threshold, while cross edges are "
            "measured with a lower threshold because same-threshold edges between distinct "
            "connected components are structurally absent. Rows are undirected and are not "
            "lead-lag paths."
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
    _write_csv(pair_summary_path, _PAIR_FIELDS, pair_rows)
    html_path.write_text(_render_html(metadata, pair_rows), encoding="utf-8")
    return ComponentPairSummaryOutputPaths(
        metadata_path=metadata_path,
        pair_summary_path=pair_summary_path,
        html_path=html_path,
    )


def _validate_component_pair_args(
    *,
    component_threshold: float,
    cross_edge_threshold: float,
    min_component_size: int,
    min_component_density: float,
    min_cross_pair_count: int,
    top_n_pairs: int,
    max_top_symbols: int,
) -> None:
    _validate_thresholds([component_threshold, cross_edge_threshold])
    if cross_edge_threshold >= component_threshold:
        raise ValueError("cross_edge_threshold must be lower than component_threshold.")
    if min_component_size < 2:
        raise ValueError("min_component_size must be at least 2.")
    if min_component_density < 0 or min_component_density > 1:
        raise ValueError("min_component_density must be between 0 and 1.")
    if min_cross_pair_count < 1:
        raise ValueError("min_cross_pair_count must be positive.")
    if top_n_pairs < 1:
        raise ValueError("top_n_pairs must be positive.")
    if max_top_symbols < 1:
        raise ValueError("max_top_symbols must be positive.")


def _summarize_pair_window(
    *,
    pd: Any,
    np: Any,
    prices: Any,
    frame_index: int,
    window_frame_index: int,
    window_months: int,
    period_start: str,
    period_end: str,
    price_column: str,
    min_observations: int,
    component_threshold: float,
    cross_edge_threshold: float,
    min_component_size: int,
    min_component_density: float,
    min_cross_pair_count: int,
    top_n_pairs: int,
    max_top_symbols: int,
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
        str(security_id): symbol_by_security.get(security_id, security_id)
        for security_id in returns.columns
    }
    _reject_duplicate_symbols(returns.columns, symbol_by_security)

    corr = returns.corr(min_periods=min_observations)
    corr.index = corr.index.astype(str)
    corr.columns = corr.columns.astype(str)
    security_ids = [str(value) for value in corr.columns]
    symbols = [str(symbol_by_security[security_id]) for security_id in security_ids]
    matrix = corr.to_numpy(dtype=float)
    market_values = _upper_triangle_values(np, corr)
    market_cross_edge_count = _count_at_least(market_values, cross_edge_threshold)
    market_cross_edge_density = _ratio(market_cross_edge_count, len(market_values))
    market_mean = _mean(market_values)
    returns_by_security = _period_returns_from_matrix(returns)
    frame_label = f"{period_start} to {period_end}"
    common = {
        "frame_index": str(frame_index),
        "window_frame_index": str(window_frame_index),
        "window_months": str(window_months),
        "frame_label": frame_label,
        "period_start": period_start,
        "period_end": period_end,
        "component_threshold": _format_threshold(component_threshold),
        "cross_edge_threshold": _format_threshold(cross_edge_threshold),
        "market_pair_count": len(market_values),
        "market_cross_edge_count": market_cross_edge_count,
        "market_cross_edge_density": _format_float(market_cross_edge_density),
        "market_mean_correlation": _format_float(market_mean),
    }

    components = _components_for_threshold(np, matrix, component_threshold, security_ids)
    non_singletons = [component for component in components if len(component) > 1]
    component_records = []
    for component_index, component in enumerate(non_singletons, start=1):
        component_id = f"C{component_index:02d}"
        detail = _component_detail_row(
            np=np,
            matrix=matrix,
            security_ids=security_ids,
            symbols=symbols,
            returns_by_security=returns_by_security,
            component=component,
            common={
                "frame_index": str(frame_index),
                "window_frame_index": str(window_frame_index),
                "window_months": str(window_months),
                "frame_label": frame_label,
                "period_start": period_start,
                "period_end": period_end,
            },
            threshold=component_threshold,
            component_id=component_id,
            max_top_symbols=max_top_symbols,
        )
        if int(detail["size"]) < min_component_size:
            continue
        if _to_float(detail["component_density"]) < min_component_density:
            continue
        component_records.append({**detail, "members": tuple(component)})

    pair_rows = [
        _pair_row(
            np=np,
            matrix=matrix,
            common=common,
            left=left,
            right=right,
            cross_edge_threshold=cross_edge_threshold,
            market_cross_edge_density=market_cross_edge_density,
            market_mean=market_mean,
        )
        for left, right in combinations(component_records, 2)
        if len(left["members"]) * len(right["members"]) >= min_cross_pair_count
    ]
    pair_rows.sort(
        key=lambda row: (
            -_to_float(row["normalized_cross_edge_density"]),
            -_to_float(row["mean_cross_correlation"]),
            -int(row["cross_edge_count"] or 0),
            -(int(row["component_a_size"]) + int(row["component_b_size"])),
            row["component_a_id"],
            row["component_b_id"],
        )
    )
    capped_rows = pair_rows[:top_n_pairs]
    return {
        "metadata": {
            "frame_index": frame_index,
            "window_frame_index": window_frame_index,
            "window_months": window_months,
            "frame_label": frame_label,
            "period_start": period_start,
            "period_end": period_end,
            "security_count": len(security_ids),
            "eligible_component_count": len(component_records),
            "component_pair_count_before_cap": len(pair_rows),
            "component_pair_count_written": len(capped_rows),
            "market_cross_edge_density": _format_float(market_cross_edge_density),
        },
        "pair_rows": capped_rows,
    }


def _pair_row(
    *,
    np: Any,
    matrix: Any,
    common: dict[str, Any],
    left: dict[str, Any],
    right: dict[str, Any],
    cross_edge_threshold: float,
    market_cross_edge_density: float | None,
    market_mean: float | None,
) -> dict[str, Any]:
    values = matrix[np.ix_(left["members"], right["members"])].reshape(-1)
    finite_values = [float(value) for value in values[np.isfinite(values)]]
    mean_cross = _mean(finite_values)
    median_cross = _median(finite_values)
    cross_edge_count = _count_at_least(finite_values, cross_edge_threshold)
    cross_density = _ratio(cross_edge_count, len(finite_values))
    normalized_cross_density = _normalized(cross_density, market_cross_edge_density)
    mean_minus_market = None if mean_cross is None or market_mean is None else mean_cross - market_mean
    return {
        **common,
        "component_a_id": left["component_id"],
        "component_b_id": right["component_id"],
        "component_a_size": left["size"],
        "component_b_size": right["size"],
        "component_a_density": left["component_density"],
        "component_b_density": right["component_density"],
        "component_a_mean_internal_correlation": left["mean_internal_correlation"],
        "component_b_mean_internal_correlation": right["mean_internal_correlation"],
        "component_a_mean_period_return": left["mean_period_return"],
        "component_b_mean_period_return": right["mean_period_return"],
        "cross_pair_count": len(finite_values),
        "mean_cross_correlation": _format_float(mean_cross),
        "median_cross_correlation": _format_float(median_cross),
        "mean_cross_correlation_minus_market": _format_float(mean_minus_market),
        "cross_edge_count": cross_edge_count,
        "cross_edge_density": _format_float(cross_density),
        "normalized_cross_edge_density": _format_float(normalized_cross_density),
        "component_a_top_symbols": left["top_symbols"],
        "component_b_top_symbols": right["top_symbols"],
    }


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    sorted_values = sorted(values)
    middle = len(sorted_values) // 2
    if len(sorted_values) % 2:
        return sorted_values[middle]
    return (sorted_values[middle - 1] + sorted_values[middle]) / 2.0


def _normalized(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None or baseline == 0:
        return None
    return value / baseline


def _to_float(value: Any) -> float:
    if value in ("", None):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _render_html(metadata: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    header = "".join(f"<th>{html.escape(field)}</th>" for field in _PAIR_FIELDS)
    body = "\n".join(
        "<tr>"
        + "".join(f"<td>{html.escape(str(row.get(field, '')))}</td>" for field in _PAIR_FIELDS)
        + "</tr>"
        for row in rows
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Component Pair Summary</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 24px; color: #172026; }}
    .note {{ max-width: 1080px; color: #44515c; line-height: 1.45; }}
    table {{ border-collapse: collapse; font-size: 12px; min-width: 1600px; }}
    th, td {{ border: 1px solid #d7dde3; padding: 5px 7px; vertical-align: top; }}
    th {{ position: sticky; top: 0; background: #f3f6f8; text-align: left; }}
    .scroll {{ overflow-x: auto; border: 1px solid #d7dde3; }}
  </style>
</head>
<body>
  <h1>Component Pair Summary</h1>
  <p class="note">Mechanical table of same-window component-to-component relationships. No lead-lag, no direction, no forecast, and no recommendation. Cross-edge counts use a lower threshold than the component definition because same-threshold edges between distinct connected components are structurally absent.</p>
  <p class="note">Component ids are local to one window and threshold. Mean period returns are separate same-window overlays, not signals.</p>
  <p class="note">Relationship: {html.escape(str(metadata.get("relationship", "")))}. Component threshold: {metadata.get("component_threshold")}. Cross-edge threshold: {metadata.get("cross_edge_threshold")}.</p>
  <div class="scroll"><table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table></div>
</body>
</html>
"""
