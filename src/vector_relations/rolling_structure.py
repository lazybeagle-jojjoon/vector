from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .global_map import (
    _filter_value,
    _read_node_metadata,
    _read_period_returns,
    _read_snapshot_metadata,
    _read_universe,
    _write_csv,
)


@dataclass(frozen=True)
class RollingStructureOutputPaths:
    metadata_path: Path
    group_summary_path: Path
    cross_group_summary_path: Path
    group_delta_path: Path
    cross_group_delta_path: Path
    markdown_path: Path


_GROUP_FIELDS = [
    "frame_index",
    "frame_label",
    "period_start",
    "period_end",
    "group_column",
    "group_name",
    "member_count",
    "return_observation_count",
    "mean_period_return",
    "internal_pair_count",
    "internal_mean_correlation",
    "internal_abs_threshold_edge_count",
    "internal_top_percentile_edge_count",
    "top_percentile_cutoff",
]

_CROSS_FIELDS = [
    "frame_index",
    "frame_label",
    "period_start",
    "period_end",
    "group_column",
    "group_a",
    "group_b",
    "pair_count",
    "mean_correlation",
    "abs_threshold_edge_count",
    "top_percentile_edge_count",
    "top_percentile_cutoff",
]

_GROUP_DELTA_FIELDS = [
    "frame_index",
    "previous_frame_label",
    "frame_label",
    "group_column",
    "group_name",
    "delta_member_count",
    "delta_mean_period_return",
    "delta_internal_mean_correlation",
    "delta_internal_abs_threshold_edge_count",
    "delta_internal_top_percentile_edge_count",
]

_CROSS_DELTA_FIELDS = [
    "frame_index",
    "previous_frame_label",
    "frame_label",
    "group_column",
    "group_a",
    "group_b",
    "delta_mean_correlation",
    "delta_abs_threshold_edge_count",
    "delta_top_percentile_edge_count",
]


def write_rolling_structure_scan(
    snapshot_dirs: list[str | Path] | tuple[str | Path, ...],
    *,
    output_dir: str | Path,
    node_metadata_path: str | Path,
    group_column: str = "sector",
    top_percentile: float = 0.05,
    absolute_correlation_threshold: float = 0.5,
) -> RollingStructureOutputPaths:
    if not snapshot_dirs:
        raise ValueError("at least one snapshot directory is required.")
    if not 0 < top_percentile < 1:
        raise ValueError("top_percentile must be between 0 and 1.")

    metadata_by_symbol = _read_node_metadata(Path(node_metadata_path))
    frames: list[dict[str, Any]] = []
    for frame_index, snapshot_dir in enumerate(snapshot_dirs):
        frame = _read_frame(
            frame_index=frame_index,
            snapshot_dir=Path(snapshot_dir),
            metadata_by_symbol=metadata_by_symbol,
            group_column=group_column,
            top_percentile=top_percentile,
            absolute_correlation_threshold=absolute_correlation_threshold,
        )
        frames.append(frame)

    return _write_scan_outputs(
        frames=frames,
        output_dir=output_dir,
        group_column=group_column,
        top_percentile=top_percentile,
        absolute_correlation_threshold=absolute_correlation_threshold,
        extra_metadata={
            "input_mode": "saved_snapshots",
            "storage_note": (
                "Saved snapshot mode reads existing correlations.csv files and writes "
                "descriptive summary tables only."
            ),
        },
    )


def write_rolling_structure_scan_from_prices(
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
    top_percentile: float = 0.05,
    absolute_correlation_threshold: float = 0.5,
    source_metadata: dict[str, Any] | None = None,
) -> RollingStructureOutputPaths:
    pd = _import_pandas()
    if not 0 < top_percentile < 1:
        raise ValueError("top_percentile must be between 0 and 1.")
    if window_months < 1:
        raise ValueError("window_months must be at least 1.")
    if stride_months < 1:
        raise ValueError("stride_months must be at least 1.")
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
    for frame_index, (period_start, period_end) in enumerate(windows):
        frame_prices = prepared[
            (prepared["_rolling_date"] >= pd.Timestamp(period_start))
            & (prepared["_rolling_date"] <= pd.Timestamp(period_end))
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
        correlations = returns.corr(min_periods=min_observations)
        universe = [
            {"security_id": str(security_id), "symbol": str(symbol_by_security[security_id])}
            for security_id in returns.columns
        ]
        frames.append(
            _summarize_frame(
                frame_index=frame_index,
                frame_label=f"{period_start} to {period_end}",
                period_start=period_start,
                period_end=period_end,
                source_snapshot="",
                universe=universe,
                returns_by_security=_period_returns_from_matrix(returns),
                correlations=correlations,
                metadata_by_symbol=metadata_by_symbol,
                group_column=group_column,
                top_percentile=top_percentile,
                absolute_correlation_threshold=absolute_correlation_threshold,
            )
        )

    return _write_scan_outputs(
        frames=frames,
        output_dir=output_dir,
        group_column=group_column,
        top_percentile=top_percentile,
        absolute_correlation_threshold=absolute_correlation_threshold,
        extra_metadata={
            "input_mode": "price_rolling_windows_summary_only",
            "market": market.upper(),
            "rolling_start": rolling_start,
            "rolling_end": rolling_end,
            "window_months": window_months,
            "stride_months": stride_months,
            "price_column": price_column,
            "min_observations": min_observations,
            "storage_note": (
                "Rolling windows are computed in memory from prices; full returns, "
                "correlations, and distances matrices are not written for each window."
            ),
            **(source_metadata or {}),
        },
    )


def _write_scan_outputs(
    *,
    frames: list[dict[str, Any]],
    output_dir: str | Path,
    group_column: str,
    top_percentile: float,
    absolute_correlation_threshold: float,
    extra_metadata: dict[str, Any],
) -> RollingStructureOutputPaths:
    group_rows: list[dict[str, Any]] = []
    cross_rows: list[dict[str, Any]] = []
    for frame in frames:
        group_rows.extend(frame["group_rows"])
        cross_rows.extend(frame["cross_rows"])

    group_delta_rows = _delta_rows(
        rows=group_rows,
        key_fields=["group_name"],
        value_fields=[
            "member_count",
            "mean_period_return",
            "internal_mean_correlation",
            "internal_abs_threshold_edge_count",
            "internal_top_percentile_edge_count",
        ],
        output_fields=_GROUP_DELTA_FIELDS,
        label_fields={"group_column": group_column},
    )
    cross_delta_rows = _delta_rows(
        rows=cross_rows,
        key_fields=["group_a", "group_b"],
        value_fields=[
            "mean_correlation",
            "abs_threshold_edge_count",
            "top_percentile_edge_count",
        ],
        output_fields=_CROSS_DELTA_FIELDS,
        label_fields={"group_column": group_column},
    )

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    metadata_path = output_path / "rolling_structure_metadata.json"
    group_summary_path = output_path / "group_summary.csv"
    cross_group_summary_path = output_path / "cross_group_summary.csv"
    group_delta_path = output_path / "group_deltas.csv"
    cross_group_delta_path = output_path / "cross_group_deltas.csv"
    markdown_path = output_path / "rolling_structure_summary.md"

    metadata = {
        "artifact_files": {
            "metadata": metadata_path.name,
            "group_summary": group_summary_path.name,
            "cross_group_summary": cross_group_summary_path.name,
            "group_deltas": group_delta_path.name,
            "cross_group_deltas": cross_group_delta_path.name,
            "markdown": markdown_path.name,
        },
        "relationship": "return_correlation_distance",
        "mode": "descriptive_structure_only",
        "group_column": group_column,
        "top_percentile": top_percentile,
        "absolute_correlation_threshold": absolute_correlation_threshold,
        "frame_count": len(frames),
        "frames": [
            {
                "frame_index": frame["frame_index"],
                "frame_label": frame["frame_label"],
                "period_start": frame["period_start"],
                "period_end": frame["period_end"],
                "source_snapshot": frame["source_snapshot"],
                "security_count": frame["security_count"],
                "top_percentile_cutoff": frame["top_percentile_cutoff"],
            }
            for frame in frames
        ],
        "brightline": (
            "This scan describes structure-at-t only. Aligning structure-at-t to return-at-t+1 "
            "is predictive lead-lag research and is out of scope."
        ),
        "window_caveat": (
            "Overlapping rolling windows are useful for viewing smooth structure changes, "
            "but adjacent windows are not independent samples."
        ),
        "threshold_note": (
            "top_percentile is regime-relative and is the primary strong-edge lens; "
            "absolute_correlation_threshold is a secondary regime-level count."
        ),
        "sector_note": (
            "Groups use existing metadata labels only. They are group-by keys, not detected "
            "clusters, taxonomy assignments, or investment themes."
        ),
        "missing_group_note": (
            "The 'missing' group is a source metadata gap bucket, not a real sector or "
            "industry label."
        ),
        "disclaimer": (
            "Descriptive historical structure only; not investment advice, not a forecast, "
            "and not a recommendation."
        ),
        **extra_metadata,
    }
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_csv(group_summary_path, _GROUP_FIELDS, group_rows)
    _write_csv(cross_group_summary_path, _CROSS_FIELDS, cross_rows)
    _write_csv(group_delta_path, _GROUP_DELTA_FIELDS, group_delta_rows)
    _write_csv(cross_group_delta_path, _CROSS_DELTA_FIELDS, cross_delta_rows)
    markdown_path.write_text(
        _render_markdown(metadata=metadata, group_delta_rows=group_delta_rows, cross_delta_rows=cross_delta_rows),
        encoding="utf-8",
    )

    return RollingStructureOutputPaths(
        metadata_path=metadata_path,
        group_summary_path=group_summary_path,
        cross_group_summary_path=cross_group_summary_path,
        group_delta_path=group_delta_path,
        cross_group_delta_path=cross_group_delta_path,
        markdown_path=markdown_path,
    )


def _read_frame(
    *,
    frame_index: int,
    snapshot_dir: Path,
    metadata_by_symbol: dict[str, dict[str, str]],
    group_column: str,
    top_percentile: float,
    absolute_correlation_threshold: float,
) -> dict[str, Any]:
    pd = _import_pandas()
    np = _import_numpy()
    metadata = _read_snapshot_metadata(snapshot_dir)
    artifacts = metadata.get("artifact_files", {})
    universe = _read_universe(snapshot_dir / artifacts.get("universe", "universe.csv"))
    returns = _read_period_returns(snapshot_dir / artifacts.get("returns", "returns.csv"))
    correlations_path = snapshot_dir / artifacts.get("correlations", "correlations.csv")
    if not correlations_path.exists():
        raise ValueError(f"Snapshot correlations CSV does not exist: {correlations_path}")
    correlations = pd.read_csv(correlations_path, index_col=0)
    correlations.index = correlations.index.astype(str)
    correlations.columns = correlations.columns.astype(str)
    return _summarize_frame(
        frame_index=frame_index,
        frame_label=_frame_label(metadata, fallback=f"frame {frame_index + 1}"),
        period_start=metadata.get("period_start") or "",
        period_end=metadata.get("period_end") or "",
        source_snapshot=str(snapshot_dir),
        universe=universe,
        returns_by_security=returns,
        correlations=correlations,
        metadata_by_symbol=metadata_by_symbol,
        group_column=group_column,
        top_percentile=top_percentile,
        absolute_correlation_threshold=absolute_correlation_threshold,
    )


def _summarize_frame(
    *,
    frame_index: int,
    frame_label: str,
    period_start: str,
    period_end: str,
    source_snapshot: str,
    universe: list[dict[str, str]],
    returns_by_security: dict[str, float | None],
    correlations: Any,
    metadata_by_symbol: dict[str, dict[str, str]],
    group_column: str,
    top_percentile: float,
    absolute_correlation_threshold: float,
) -> dict[str, Any]:
    pd = _import_pandas()
    np = _import_numpy()
    symbol_by_security = {row["security_id"]: row["symbol"] for row in universe}
    groups_by_security = _groups_by_security(
        universe=universe,
        metadata_by_symbol=metadata_by_symbol,
        group_column=group_column,
    )
    correlations.index = correlations.index.astype(str)
    correlations.columns = correlations.columns.astype(str)
    active_ids = [
        security_id
        for security_id in symbol_by_security
        if security_id in correlations.index and security_id in correlations.columns
    ]
    corr = correlations.loc[active_ids, active_ids].apply(pd.to_numeric, errors="coerce")
    cutoff = _top_percentile_cutoff(np, corr, top_percentile)
    common = {
        "frame_index": str(frame_index),
        "frame_label": frame_label,
        "period_start": period_start,
        "period_end": period_end,
        "group_column": group_column,
        "top_percentile_cutoff": _format_float(cutoff),
    }
    group_to_ids: dict[str, list[str]] = {}
    for security_id in active_ids:
        group = groups_by_security.get(security_id, "missing")
        group_to_ids.setdefault(group, []).append(security_id)

    group_rows = []
    for group in sorted(group_to_ids):
        ids = group_to_ids[group]
        values = _internal_values(np, corr, ids)
        return_values = [
            returns_by_security.get(security_id, returns_by_security.get(symbol_by_security[security_id]))
            for security_id in ids
        ]
        return_values = [float(value) for value in return_values if value is not None]
        group_rows.append(
            {
                **common,
                "group_name": group,
                "member_count": len(ids),
                "return_observation_count": len(return_values),
                "mean_period_return": _format_float(_mean(return_values)),
                "internal_pair_count": len(values),
                "internal_mean_correlation": _format_float(_mean(values)),
                "internal_abs_threshold_edge_count": _count_at_least(values, absolute_correlation_threshold),
                "internal_top_percentile_edge_count": _count_at_least(values, cutoff),
            }
        )

    cross_rows = []
    groups = sorted(group_to_ids)
    for left_index, group_a in enumerate(groups):
        for group_b in groups[left_index + 1 :]:
            values = _cross_values(np, corr, group_to_ids[group_a], group_to_ids[group_b])
            cross_rows.append(
                {
                    **common,
                    "group_a": group_a,
                    "group_b": group_b,
                    "pair_count": len(values),
                    "mean_correlation": _format_float(_mean(values)),
                    "abs_threshold_edge_count": _count_at_least(values, absolute_correlation_threshold),
                    "top_percentile_edge_count": _count_at_least(values, cutoff),
                }
            )

    return {
        "frame_index": frame_index,
        "frame_label": frame_label,
        "period_start": period_start,
        "period_end": period_end,
        "source_snapshot": source_snapshot,
        "security_count": len(active_ids),
        "top_percentile_cutoff": cutoff,
        "group_rows": group_rows,
        "cross_rows": cross_rows,
    }


def _groups_by_security(
    *,
    universe: list[dict[str, str]],
    metadata_by_symbol: dict[str, dict[str, str]],
    group_column: str,
) -> dict[str, str]:
    groups = {}
    for row in universe:
        symbol = row["symbol"]
        metadata = metadata_by_symbol.get(symbol, {})
        groups[row["security_id"]] = _filter_value(metadata.get(group_column))
    return groups


def _rolling_windows(
    pd: Any,
    *,
    rolling_start: str,
    rolling_end: str,
    window_months: int,
    stride_months: int,
) -> list[tuple[str, str]]:
    current = pd.Timestamp(rolling_start).normalize()
    final = pd.Timestamp(rolling_end).normalize()
    windows: list[tuple[str, str]] = []
    while True:
        window_end = current + pd.DateOffset(months=window_months) - pd.Timedelta(days=1)
        if window_end > final:
            break
        windows.append((current.strftime("%Y-%m-%d"), window_end.strftime("%Y-%m-%d")))
        current = current + pd.DateOffset(months=stride_months)
    return windows


def _build_return_matrix(prices: Any, price_column: str) -> Any:
    ordered = prices.sort_values(["security_id", "_rolling_date"]).copy()
    ordered["return"] = ordered.groupby("security_id", sort=True)[price_column].pct_change()
    return ordered.pivot_table(
        index="_rolling_date",
        columns="security_id",
        values="return",
        aggfunc="last",
    ).sort_index()


def _period_returns_from_matrix(returns: Any) -> dict[str, float | None]:
    results: dict[str, float | None] = {}
    for security_id in returns.columns:
        values = returns[security_id].dropna()
        if values.empty:
            results[str(security_id)] = None
        else:
            results[str(security_id)] = float((1.0 + values).prod() - 1.0)
    return results


def _reject_duplicate_symbols(security_ids: Any, symbol_by_security: dict[str, str]) -> None:
    security_by_symbol: dict[str, list[str]] = {}
    for security_id in security_ids:
        symbol = symbol_by_security.get(security_id, security_id)
        security_by_symbol.setdefault(str(symbol), []).append(str(security_id))
    duplicates = {
        symbol: ids
        for symbol, ids in security_by_symbol.items()
        if len(ids) > 1
    }
    if not duplicates:
        return
    detail = "; ".join(
        f"{symbol}: {', '.join(ids)}"
        for symbol, ids in sorted(duplicates.items())
    )
    raise ValueError(
        "Duplicate display symbols would make rolling group summaries ambiguous. "
        f"Use a stricter universe or disambiguate symbols first. Duplicates: {detail}"
    )


def _require_columns(frame: Any, columns: set[str], name: str) -> None:
    missing = sorted(columns - set(frame.columns))
    if missing:
        raise ValueError(f"{name} missing required columns: {', '.join(missing)}")


def _top_percentile_cutoff(np: Any, corr: Any, top_percentile: float) -> float:
    matrix = corr.to_numpy(dtype=float)
    if matrix.shape[0] < 2:
        return 1.0
    values = matrix[np.triu_indices(matrix.shape[0], k=1)]
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return 1.0
    return float(np.quantile(values, 1.0 - top_percentile))


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


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _count_at_least(values: list[float], threshold: float) -> int:
    return sum(1 for value in values if value >= threshold)


def _delta_rows(
    *,
    rows: list[dict[str, Any]],
    key_fields: list[str],
    value_fields: list[str],
    output_fields: list[str],
    label_fields: dict[str, str],
) -> list[dict[str, Any]]:
    by_frame: dict[int, dict[tuple[str, ...], dict[str, Any]]] = {}
    labels_by_frame: dict[int, str] = {}
    for row in rows:
        frame_index = int(row["frame_index"])
        key = tuple(str(row[field]) for field in key_fields)
        by_frame.setdefault(frame_index, {})[key] = row
        labels_by_frame[frame_index] = str(row["frame_label"])

    results: list[dict[str, Any]] = []
    for frame_index in sorted(by_frame):
        if frame_index == 0 or frame_index - 1 not in by_frame:
            continue
        current = by_frame[frame_index]
        previous = by_frame[frame_index - 1]
        for key in sorted(set(current) | set(previous)):
            current_row = current.get(key, {})
            previous_row = previous.get(key, {})
            row = {
                "frame_index": str(frame_index),
                "previous_frame_label": labels_by_frame.get(frame_index - 1, ""),
                "frame_label": labels_by_frame.get(frame_index, ""),
                **label_fields,
            }
            for field, value in zip(key_fields, key, strict=True):
                row[field] = value
            for field in value_fields:
                row[f"delta_{field}"] = _format_float(
                    _optional_number(current_row.get(field)) - _optional_number(previous_row.get(field))
                    if current_row.get(field, "") != "" and previous_row.get(field, "") != ""
                    else None
                )
            results.append({field: row.get(field, "") for field in output_fields})
    return results


def _optional_number(value: Any) -> float:
    return float(value)


def _frame_label(metadata: dict[str, Any], *, fallback: str) -> str:
    start = metadata.get("period_start")
    end = metadata.get("period_end")
    if start and end:
        return f"{start} to {end}"
    return fallback


def _format_float(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.12g}"


def _render_markdown(
    *,
    metadata: dict[str, Any],
    group_delta_rows: list[dict[str, Any]],
    cross_delta_rows: list[dict[str, Any]],
) -> str:
    top_group_increases = sorted(
        [
            row
            for row in group_delta_rows
            if row.get("delta_internal_mean_correlation") not in {"", None}
        ],
        key=lambda row: float(row["delta_internal_mean_correlation"]),
        reverse=True,
    )[:10]
    top_cross_increases = sorted(
        [
            row
            for row in cross_delta_rows
            if row.get("delta_top_percentile_edge_count") not in {"", None}
        ],
        key=lambda row: float(row["delta_top_percentile_edge_count"]),
        reverse=True,
    )[:10]
    lines = [
        "# Rolling Structure Summary",
        "",
        "This output is descriptive only and is not investment advice, not a forecast, and not a recommendation.",
        "",
        f"- Relationship: `{metadata['relationship']}`",
        f"- Group column: `{metadata['group_column']}`",
        f"- Top-percentile strong-edge lens: `{metadata['top_percentile']}`",
        f"- Absolute correlation count lens: `{metadata['absolute_correlation_threshold']}`",
        "",
        "## Brightline",
        "",
        metadata["brightline"],
        "",
        "## Missing group note",
        "",
        metadata["missing_group_note"],
        "",
        "## Top group cohesion increases",
        "",
    ]
    if top_group_increases:
        for row in top_group_increases:
            lines.append(
                f"- {row['frame_label']} | {row['group_name']}: "
                f"delta internal mean correlation {row['delta_internal_mean_correlation']}"
            )
    else:
        lines.append("- No comparable group deltas.")
    lines.extend(["", "## Top cross-group top-percentile edge increases", ""])
    if top_cross_increases:
        for row in top_cross_increases:
            lines.append(
                f"- {row['frame_label']} | {row['group_a']} / {row['group_b']}: "
                f"delta top-percentile edge count {row['delta_top_percentile_edge_count']}"
            )
    else:
        lines.append("- No comparable cross-group deltas.")
    lines.append("")
    return "\n".join(lines)


def _import_pandas():
    try:
        import pandas as pd
    except ModuleNotFoundError as exc:
        raise ValueError(
            "rolling structure scan requires pandas. Run with: "
            "uv run --no-project --with pandas python -m vector_relations.rolling_structure_cli ..."
        ) from exc
    return pd


def _import_numpy():
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        raise ValueError(
            "rolling structure scan requires numpy. Run with: "
            "uv run --no-project --with pandas --with numpy python -m vector_relations.rolling_structure_cli ..."
        ) from exc
    return np
