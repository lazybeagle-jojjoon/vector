from __future__ import annotations

import csv
import html
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
class ComponentStructureOutputPaths:
    metadata_path: Path
    frame_summary_path: Path
    component_detail_path: Path
    component_flow_path: Path
    markdown_path: Path


_FRAME_FIELDS = [
    "frame_index",
    "window_frame_index",
    "window_months",
    "frame_label",
    "period_start",
    "period_end",
    "threshold",
    "security_count",
    "component_count",
    "non_singleton_component_count",
    "singleton_count",
    "giant_component_size",
    "giant_component_share",
    "market_pair_count",
    "market_strong_edge_count",
    "market_strong_edge_ratio",
]

_DETAIL_FIELDS = [
    "frame_index",
    "window_frame_index",
    "window_months",
    "frame_label",
    "period_start",
    "period_end",
    "threshold",
    "component_id",
    "size",
    "edge_count",
    "possible_edge_count",
    "component_density",
    "mean_internal_correlation",
    "mean_period_return",
    "top_symbols",
]

_FLOW_FIELDS = [
    "window_months",
    "threshold",
    "from_frame_index",
    "to_frame_index",
    "from_frame_label",
    "to_frame_label",
    "event_type",
    "source_component_id",
    "target_component_id",
    "source_size",
    "target_size",
    "overlap_count",
    "jaccard",
    "source_retention_ratio",
    "target_capture_ratio",
    "source_match_count",
    "target_match_count",
    "source_component_density",
    "target_component_density",
    "source_top_symbols",
    "target_top_symbols",
]


def write_component_structure_from_prices(
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
    thresholds: list[float] | tuple[float, ...] = (0.5, 0.6, 0.7),
    max_components_per_frame: int = 25,
    max_top_symbols: int = 12,
    source_metadata: dict[str, Any] | None = None,
) -> ComponentStructureOutputPaths:
    pd = _import_pandas()
    np = _import_numpy()
    thresholds = _validate_thresholds(thresholds)
    if min_observations < 2:
        raise ValueError("min_observations must be at least 2.")
    if max_components_per_frame < 1:
        raise ValueError("max_components_per_frame must be positive.")
    if max_top_symbols < 1:
        raise ValueError("max_top_symbols must be positive.")
    window_months_values = _window_months_values(window_months, window_months_list)
    _require_columns(prices, {"security_id", "symbol", "date", price_column}, "prices")

    prepared = prices.copy()
    prepared["_rolling_date"] = pd.to_datetime(prepared["date"], errors="coerce")
    prepared = prepared.dropna(subset=["security_id", "symbol", "_rolling_date", price_column])
    prepared = prepared[prepared[price_column] > 0]
    if prepared.empty:
        raise ValueError("no price rows remain after filtering.")

    frames: list[dict[str, Any]] = []
    frame_rows: list[dict[str, Any]] = []
    detail_rows: list[dict[str, Any]] = []
    flow_rows: list[dict[str, Any]] = []
    previous_components_by_key: dict[tuple[int, str], list[dict[str, Any]]] = {}
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
            frame = _summarize_component_window(
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
                thresholds=thresholds,
                max_components_per_frame=max_components_per_frame,
                max_top_symbols=max_top_symbols,
            )
            frame_index += 1
            frames.append(frame["metadata"])
            frame_rows.extend(frame["frame_rows"])
            detail_rows.extend(frame["detail_rows"])
            for threshold_text, components in frame["component_records_by_threshold"].items():
                key = (window_months_value, threshold_text)
                previous_components = previous_components_by_key.get(key)
                if previous_components is not None:
                    flow_rows.extend(_component_flow_rows(previous_components, components))
                previous_components_by_key[key] = components

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    metadata_path = output_path / "component_structure_metadata.json"
    frame_summary_path = output_path / "component_frame_summary.csv"
    component_detail_path = output_path / "component_detail.csv"
    component_flow_path = output_path / "component_flow_summary.csv"
    markdown_path = output_path / "component_structure_summary.md"
    metadata = {
        "artifact_files": {
            "metadata": metadata_path.name,
            "frame_summary": frame_summary_path.name,
            "component_detail": component_detail_path.name,
            "component_flow": component_flow_path.name,
            "markdown": markdown_path.name,
        },
        "mode": "descriptive_connected_components",
        "relationship": "return_correlation",
        "market": market.upper(),
        "rolling_start": rolling_start,
        "rolling_end": rolling_end,
        "window_months": window_months,
        "window_months_values": window_months_values,
        "stride_months": stride_months,
        "price_column": price_column,
        "min_observations": min_observations,
        "thresholds": thresholds,
        "frame_count": len(frames),
        "frames": frames,
        "interpretation_note": (
            "Connected components are unnamed threshold-defined relationship sets. "
            "C01/C02 ids are local to one window and threshold; do not treat them as "
            "stable taxonomy labels. Components use single-linkage connectivity: a large "
            "component can be a chained set, so read size with component_density. "
            "Component detail rows are capped; frame_summary contains the full counts."
        ),
        "flow_interpretation_note": (
            "Component flow rows use adjacent-window membership overlap only. They are not stable "
            "component identities, lead-lag signals, forecasts, or recommendations."
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
    _write_csv(frame_summary_path, _FRAME_FIELDS, frame_rows)
    _write_csv(component_detail_path, _DETAIL_FIELDS, detail_rows)
    _write_csv(component_flow_path, _FLOW_FIELDS, flow_rows)
    markdown_path.write_text(_render_markdown(metadata, frame_rows, detail_rows, flow_rows), encoding="utf-8")
    return ComponentStructureOutputPaths(
        metadata_path=metadata_path,
        frame_summary_path=frame_summary_path,
        component_detail_path=component_detail_path,
        component_flow_path=component_flow_path,
        markdown_path=markdown_path,
    )


def _summarize_component_window(
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
    thresholds: list[float],
    max_components_per_frame: int,
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
    returns_by_security = _period_returns_from_matrix(returns)
    frame_label = f"{period_start} to {period_end}"
    common = {
        "frame_index": str(frame_index),
        "window_frame_index": str(window_frame_index),
        "window_months": str(window_months),
        "frame_label": frame_label,
        "period_start": period_start,
        "period_end": period_end,
    }
    frame_rows: list[dict[str, Any]] = []
    detail_rows: list[dict[str, Any]] = []
    component_records_by_threshold: dict[str, list[dict[str, Any]]] = {}
    for threshold in thresholds:
        components = _components_for_threshold(np, matrix, threshold, security_ids)
        non_singletons = [component for component in components if len(component) > 1]
        singletons = len(components) - len(non_singletons)
        giant_size = len(components[0]) if components else 0
        market_count = _count_at_least(market_values, threshold)
        market_ratio = _ratio(market_count, len(market_values))
        threshold_text = _format_threshold(threshold)
        frame_rows.append(
            {
                **common,
                "threshold": threshold_text,
                "security_count": len(security_ids),
                "component_count": len(components),
                "non_singleton_component_count": len(non_singletons),
                "singleton_count": singletons,
                "giant_component_size": giant_size,
                "giant_component_share": _format_float(_ratio(giant_size, len(security_ids))),
                "market_pair_count": len(market_values),
                "market_strong_edge_count": market_count,
                "market_strong_edge_ratio": _format_float(market_ratio),
            }
        )
        threshold_records: list[dict[str, Any]] = []
        for component_index, component in enumerate(non_singletons, start=1):
            component_id = f"C{component_index:02d}"
            detail_row = _component_detail_row(
                np=np,
                matrix=matrix,
                security_ids=security_ids,
                symbols=symbols,
                returns_by_security=returns_by_security,
                component=component,
                common=common,
                threshold=threshold,
                component_id=component_id,
                max_top_symbols=max_top_symbols,
            )
            threshold_records.append(
                {
                    **detail_row,
                    "members": frozenset(security_ids[index] for index in component),
                }
            )
            if component_index <= max_components_per_frame:
                detail_rows.append(detail_row)
        component_records_by_threshold[threshold_text] = threshold_records
    return {
        "metadata": {
            "frame_index": frame_index,
            "window_frame_index": window_frame_index,
            "window_months": window_months,
            "frame_label": frame_label,
            "period_start": period_start,
            "period_end": period_end,
            "security_count": len(security_ids),
        },
        "frame_rows": frame_rows,
        "detail_rows": detail_rows,
        "component_records_by_threshold": component_records_by_threshold,
    }


def _component_flow_rows(
    previous_components: list[dict[str, Any]],
    current_components: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    min_jaccard = 0.1
    source_matches: dict[str, list[dict[str, Any]]] = {}
    target_matches: dict[str, list[dict[str, Any]]] = {}
    for source in previous_components:
        source_id = str(source["component_id"])
        source_matches[source_id] = []
        source_members = source["members"]
        for target in current_components:
            target_members = target["members"]
            overlap = len(source_members & target_members)
            union = len(source_members | target_members)
            jaccard = _ratio(overlap, union)
            if jaccard < min_jaccard:
                continue
            match = {
                "source": source,
                "target": target,
                "overlap": overlap,
                "jaccard": jaccard,
            }
            source_matches[source_id].append(match)
            target_matches.setdefault(str(target["component_id"]), []).append(match)
        source_matches[source_id].sort(
            key=lambda match: (-match["jaccard"], -match["overlap"], str(match["target"]["component_id"]))
        )

    rows: list[dict[str, Any]] = []
    for source in previous_components:
        matches = source_matches.get(str(source["component_id"]), [])
        if not matches:
            rows.append(_flow_row(source=source, target=None, event_type="ended", source_match_count=0, target_match_count=0))
            continue
        best = matches[0]
        target = best["target"]
        source_match_count = len(matches)
        target_match_count = len(target_matches.get(str(target["component_id"]), []))
        if source_match_count > 1 and target_match_count > 1:
            event_type = "reconfigured"
        elif source_match_count > 1:
            event_type = "split"
        elif target_match_count > 1:
            event_type = "merged"
        else:
            event_type = "continued"
        rows.append(
            _flow_row(
                source=source,
                target=target,
                event_type=event_type,
                overlap=best["overlap"],
                jaccard=best["jaccard"],
                source_match_count=source_match_count,
                target_match_count=target_match_count,
            )
        )

    matched_targets = {str(match["target"]["component_id"]) for matches in source_matches.values() for match in matches}
    for target in current_components:
        if str(target["component_id"]) in matched_targets:
            continue
        rows.append(_flow_row(source=None, target=target, event_type="new", source_match_count=0, target_match_count=0))
    return rows


def _flow_row(
    *,
    source: dict[str, Any] | None,
    target: dict[str, Any] | None,
    event_type: str,
    overlap: int = 0,
    jaccard: float = 0.0,
    source_match_count: int,
    target_match_count: int,
) -> dict[str, Any]:
    anchor = source if source is not None else target
    if anchor is None:
        raise ValueError("flow row needs a source or target component.")
    source_size = int(source["size"]) if source is not None else 0
    target_size = int(target["size"]) if target is not None else 0
    return {
        "window_months": anchor["window_months"],
        "threshold": anchor["threshold"],
        "from_frame_index": source["frame_index"] if source is not None else "",
        "to_frame_index": target["frame_index"] if target is not None else "",
        "from_frame_label": source["frame_label"] if source is not None else "",
        "to_frame_label": target["frame_label"] if target is not None else "",
        "event_type": event_type,
        "source_component_id": source["component_id"] if source is not None else "",
        "target_component_id": target["component_id"] if target is not None else "",
        "source_size": source_size,
        "target_size": target_size,
        "overlap_count": overlap,
        "jaccard": _format_float(jaccard),
        "source_retention_ratio": _format_float(_ratio(overlap, source_size)),
        "target_capture_ratio": _format_float(_ratio(overlap, target_size)),
        "source_match_count": source_match_count,
        "target_match_count": target_match_count,
        "source_component_density": source["component_density"] if source is not None else "",
        "target_component_density": target["component_density"] if target is not None else "",
        "source_top_symbols": source["top_symbols"] if source is not None else "",
        "target_top_symbols": target["top_symbols"] if target is not None else "",
    }


def _components_for_threshold(np: Any, matrix: Any, threshold: float, security_ids: list[str]) -> list[list[int]]:
    parent = list(range(len(security_ids)))
    rank = [0] * len(security_ids)
    rows, cols = np.triu_indices(len(security_ids), k=1)
    values = matrix[rows, cols]
    mask = np.isfinite(values) & (values >= threshold)
    for left, right in zip(rows[mask], cols[mask], strict=False):
        _union(parent, rank, int(left), int(right))
    grouped: dict[int, list[int]] = {}
    for index in range(len(security_ids)):
        grouped.setdefault(_find(parent, index), []).append(index)
    return sorted(grouped.values(), key=lambda component: (-len(component), [security_ids[i] for i in component]))


def _component_detail_row(
    *,
    np: Any,
    matrix: Any,
    security_ids: list[str],
    symbols: list[str],
    returns_by_security: dict[str, float | None],
    component: list[int],
    common: dict[str, str],
    threshold: float,
    component_id: str,
    max_top_symbols: int,
) -> dict[str, Any]:
    submatrix = matrix[np.ix_(component, component)]
    values = submatrix[np.triu_indices(len(component), k=1)]
    finite_values = [float(value) for value in values[np.isfinite(values)]]
    edge_count = _count_at_least(finite_values, threshold)
    possible_edges = len(component) * (len(component) - 1) // 2
    return_values = [returns_by_security.get(security_ids[index]) for index in component]
    return_values = [value for value in return_values if value is not None]
    top_symbols = [symbols[index] for index in component[:max_top_symbols]]
    return {
        **common,
        "threshold": _format_threshold(threshold),
        "component_id": component_id,
        "size": len(component),
        "edge_count": edge_count,
        "possible_edge_count": possible_edges,
        "component_density": _format_float(_ratio(edge_count, possible_edges)),
        "mean_internal_correlation": _format_float(_mean(finite_values)),
        "mean_period_return": _format_float(_mean(return_values)),
        "top_symbols": " ".join(top_symbols),
    }


def _find(parent: list[int], value: int) -> int:
    while parent[value] != value:
        parent[value] = parent[parent[value]]
        value = parent[value]
    return value


def _union(parent: list[int], rank: list[int], left: int, right: int) -> None:
    left_root = _find(parent, left)
    right_root = _find(parent, right)
    if left_root == right_root:
        return
    if rank[left_root] < rank[right_root]:
        parent[left_root] = right_root
    elif rank[left_root] > rank[right_root]:
        parent[right_root] = left_root
    else:
        parent[right_root] = left_root
        rank[left_root] += 1


def _render_markdown(
    metadata: dict[str, Any],
    frame_rows: list[dict[str, Any]],
    detail_rows: list[dict[str, Any]],
    flow_rows: list[dict[str, Any]],
) -> str:
    lines = [
        "# Connected Component Structure",
        "",
        "This is descriptive historical structure only, not investment advice, not a forecast, and not a recommendation.",
        "",
        "Components are unnamed local threshold sets. C01 in one window is not the same identity as C01 in another window.",
        "",
        "Components use single-linkage connectivity: a large component can be a chained set, not a fully similar blob.",
        "Read component size together with component_density. Component detail rows are capped; frame-level counts are complete.",
        "",
        "Component flow rows use adjacent-window membership overlap only; they are not stable component identities.",
        "",
        "## Largest frame-level component shares",
    ]
    ranked_frames = sorted(
        frame_rows,
        key=lambda row: float(row.get("giant_component_share") or 0),
        reverse=True,
    )[:12]
    for row in ranked_frames:
        lines.append(
            f"- {row['window_months']}m {row['frame_label']} corr>={row['threshold']}: "
            f"giant share {row['giant_component_share']}, components {row['component_count']}, "
            f"singletons {row['singleton_count']}"
        )
    lines.extend(["", "## Largest unnamed components"])
    ranked_details = sorted(
        detail_rows,
        key=lambda row: (int(row.get("size") or 0), int(row.get("edge_count") or 0)),
        reverse=True,
    )[:12]
    for row in ranked_details:
        lines.append(
            f"- {row['window_months']}m {row['frame_label']} corr>={row['threshold']} "
            f"{row['component_id']}: size {row['size']}, density {row['component_density']}, "
            f"top symbols {row['top_symbols']}"
        )
    lines.extend(["", "## Strong adjacent-window component flows"])
    ranked_flows = sorted(
        [
            row
            for row in flow_rows
            if row.get("event_type") in {"continued", "split", "merged", "reconfigured"}
        ],
        key=lambda row: (
            float(row.get("jaccard") or 0),
            int(row.get("overlap_count") or 0),
        ),
        reverse=True,
    )[:12]
    for row in ranked_flows:
        lines.append(
            f"- {row['window_months']}m corr>={row['threshold']} {row['event_type']}: "
            f"{row['from_frame_label']} {row['source_component_id']} -> "
            f"{row['to_frame_label']} {row['target_component_id']}; "
            f"jaccard {row['jaccard']}, overlap {row['overlap_count']}; "
            f"source top {row['source_top_symbols']}"
        )
    lines.extend(
        [
            "",
            "## Stop line",
            "",
            "- No community naming, taxonomy, lead-lag, recommendation, or forecast is included.",
            f"- Relationship: {metadata['relationship']}",
            "",
        ]
    )
    return "\n".join(lines)
