from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class RelationSnapshot:
    metadata: dict[str, Any]
    neighbors_by_symbol: dict[str, list[dict[str, Any]]]
    scatter_points: list[dict[str, Any]]
    universe: pd.DataFrame
    returns: pd.DataFrame
    correlations: pd.DataFrame
    distances: pd.DataFrame


def build_relation_snapshot(
    *,
    prices: pd.DataFrame,
    market: str,
    period_start: str,
    period_end: str,
    price_column: str,
    top_k: int,
    projection_seed: int,
    min_observations: int,
    acceptance_examples: list[str] | None = None,
    market_caps: pd.DataFrame | None = None,
) -> RelationSnapshot:
    _require_columns(prices, {"security_id", "symbol", "date", price_column}, "prices")
    if top_k < 1:
        raise ValueError("top_k must be at least 1")
    if min_observations < 2:
        raise ValueError("min_observations must be at least 2")

    filtered = _filter_period(prices, period_start, period_end).copy()
    filtered = filtered.dropna(subset=["security_id", "symbol", "date", price_column])
    filtered = filtered[filtered[price_column] > 0]
    if filtered.empty:
        raise ValueError("no price rows remain after filtering")

    symbol_by_security = (
        filtered.sort_values(["security_id", "date"])
        .groupby("security_id", sort=True)["symbol"]
        .last()
        .to_dict()
    )
    returns = _build_return_matrix(filtered, price_column)
    returns = returns.dropna(axis=1, thresh=min_observations)
    if len(returns.columns) < 2:
        raise ValueError("at least two securities need enough return observations")
    symbol_by_security = _active_symbol_map(returns.columns, symbol_by_security)
    _reject_duplicate_symbols(returns.columns, symbol_by_security)

    correlations = returns.corr(min_periods=min_observations)
    neighbors_by_symbol = _nearest_neighbors(
        correlations=correlations,
        symbol_by_security=symbol_by_security,
        top_k=top_k,
    )
    market_cap_change, market_cap_meta = _market_cap_changes(
        market_caps=market_caps,
        period_start=period_start,
        period_end=period_end,
    )
    scatter_points, scatter_meta = _anchor_distance_scatter(
        correlations=correlations,
        symbol_by_security=symbol_by_security,
        acceptance_examples=acceptance_examples or [],
        market_cap_change=market_cap_change,
    )

    metadata = {
        "market": market.upper(),
        "period_start": period_start,
        "period_end": period_end,
        "price_column": price_column,
        "id_column": "security_id",
        "ticker_display_column": "symbol",
        "relationship": "return_correlation_distance",
        "projection": "anchor_distance_scatter",
        "top_k": top_k,
        "projection_seed": projection_seed,
        "min_observations": min_observations,
        "security_count": len(returns.columns),
        "return_date_count": len(returns.index),
        "matrix_cell_count": len(returns.columns) * len(returns.columns),
        "empty_neighbor_count": sum(
            1 for neighbors in neighbors_by_symbol.values() if not neighbors
        ),
        "acceptance_examples": _acceptance_summary(
            acceptance_examples or [], neighbors_by_symbol
        ),
        **scatter_meta,
        **market_cap_meta,
    }
    if metadata["matrix_cell_count"] > 25_000_000:
        metadata["large_matrix_warning"] = "correlation matrix exceeds 25M cells"

    universe = _universe_frame(returns.columns, symbol_by_security)
    distances = 1.0 - correlations

    return RelationSnapshot(
        metadata=metadata,
        neighbors_by_symbol=neighbors_by_symbol,
        scatter_points=scatter_points,
        universe=universe,
        returns=_storage_matrix(returns, "date"),
        correlations=_storage_matrix(correlations, "security_id"),
        distances=_storage_matrix(distances, "security_id"),
    )


def _require_columns(frame: pd.DataFrame, columns: set[str], name: str) -> None:
    missing = sorted(columns - set(frame.columns))
    if missing:
        raise ValueError(f"{name} missing required columns: {', '.join(missing)}")


def _filter_period(frame: pd.DataFrame, period_start: str, period_end: str) -> pd.DataFrame:
    dates = frame["date"].astype(str)
    return frame[(dates >= period_start) & (dates <= period_end)]


def _build_return_matrix(prices: pd.DataFrame, price_column: str) -> pd.DataFrame:
    ordered = prices.sort_values(["security_id", "date"]).copy()
    ordered["return"] = ordered.groupby("security_id", sort=True)[price_column].pct_change()
    return ordered.pivot_table(
        index="date",
        columns="security_id",
        values="return",
        aggfunc="last",
    ).sort_index()


def _nearest_neighbors(
    *,
    correlations: pd.DataFrame,
    symbol_by_security: dict[str, str],
    top_k: int,
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for security_id in correlations.columns:
        symbol = symbol_by_security.get(security_id, security_id)
        candidates: list[dict[str, Any]] = []
        for neighbor_id, correlation in correlations[security_id].items():
            if neighbor_id == security_id or pd.isna(correlation):
                continue
            neighbor_symbol = symbol_by_security.get(neighbor_id, neighbor_id)
            candidates.append(
                {
                    "security_id": security_id,
                    "symbol": symbol,
                    "neighbor_security_id": neighbor_id,
                    "neighbor_symbol": neighbor_symbol,
                    "correlation": float(correlation),
                    "distance": float(1.0 - correlation),
                }
            )
        candidates.sort(key=lambda item: (item["distance"], item["neighbor_symbol"]))
        result[symbol] = candidates[:top_k]
    return result


def _anchor_distance_scatter(
    *,
    correlations: pd.DataFrame,
    symbol_by_security: dict[str, str],
    acceptance_examples: list[str],
    market_cap_change: dict[str, float | None],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    security_by_symbol = {symbol: sid for sid, symbol in symbol_by_security.items()}
    anchor_a, anchor_b, anchor_note = _choose_scatter_anchors(
        correlations=correlations,
        security_by_symbol=security_by_symbol,
        acceptance_examples=acceptance_examples,
    )

    points: list[dict[str, Any]] = []
    for security_id in sorted(correlations.columns, key=lambda sid: symbol_by_security.get(sid, sid)):
        symbol = symbol_by_security.get(security_id, security_id)
        points.append(
            {
                "security_id": security_id,
                "symbol": symbol,
                "x": _distance(correlations, security_id, anchor_a),
                "y": _distance(correlations, security_id, anchor_b),
                "market_cap_change": market_cap_change.get(security_id),
            }
        )
    anchor_symbols = [
        symbol_by_security[anchor_id]
        for anchor_id in [anchor_a, anchor_b]
        if anchor_id is not None
    ]
    return points, {
        "scatter_anchor_symbols": anchor_symbols,
        "scatter_anchor_note": anchor_note,
    }


def _choose_scatter_anchors(
    *,
    correlations: pd.DataFrame,
    security_by_symbol: dict[str, str],
    acceptance_examples: list[str],
) -> tuple[str | None, str | None, str]:
    if not security_by_symbol:
        return None, None, "no_anchors_available"

    valid_examples = [symbol for symbol in acceptance_examples if symbol in security_by_symbol]
    first_symbol = valid_examples[0] if valid_examples else sorted(security_by_symbol)[0]
    anchor_a = security_by_symbol[first_symbol]
    candidates: list[tuple[float, str, str]] = []
    for symbol, security_id in security_by_symbol.items():
        if security_id == anchor_a:
            continue
        correlation = correlations.loc[anchor_a, security_id]
        if pd.isna(correlation):
            continue
        candidates.append((float(correlation), symbol, security_id))

    if candidates:
        _, _, anchor_b = min(candidates, key=lambda item: (item[0], item[1]))
        return anchor_a, anchor_b, "second_anchor_lowest_correlation_to_first"

    fallback_symbols = [
        symbol for symbol in sorted(security_by_symbol)
        if security_by_symbol[symbol] != anchor_a
    ]
    if fallback_symbols:
        return anchor_a, security_by_symbol[fallback_symbols[0]], "second_anchor_sorted_fallback"
    return anchor_a, anchor_a, "single_anchor_only"


def _distance(
    correlations: pd.DataFrame,
    security_id: str,
    anchor_id: str | None,
) -> float:
    if anchor_id is None or security_id == anchor_id:
        return 0.0
    correlation = correlations.loc[security_id, anchor_id]
    if pd.isna(correlation):
        return 1.0
    return float(1.0 - correlation)


def _market_cap_changes(
    *,
    market_caps: pd.DataFrame | None,
    period_start: str,
    period_end: str,
) -> tuple[dict[str, float | None], dict[str, Any]]:
    if market_caps is None:
        return {}, {
            "market_cap_overlay": "missing",
            "market_cap_fallback_reason": "market_cap_frame_not_provided",
        }

    _require_columns(market_caps, {"security_id", "date", "market_cap"}, "market_caps")
    filtered = _filter_period(market_caps, period_start, period_end).copy()
    filtered = filtered.dropna(subset=["security_id", "date", "market_cap"])
    filtered = filtered[filtered["market_cap"] > 0]
    if filtered.empty:
        return {}, {
            "market_cap_overlay": "missing",
            "market_cap_fallback_reason": "no_market_cap_rows_in_period",
        }

    changes: dict[str, float | None] = {}
    for security_id, group in filtered.sort_values(["security_id", "date"]).groupby("security_id"):
        first = float(group.iloc[0]["market_cap"])
        last = float(group.iloc[-1]["market_cap"])
        changes[security_id] = (last / first) - 1.0 if first else None
    return changes, {"market_cap_overlay": "included"}


def _acceptance_summary(
    acceptance_examples: list[str],
    neighbors_by_symbol: dict[str, list[dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for symbol in acceptance_examples:
        neighbors = neighbors_by_symbol.get(symbol, [])
        summary[symbol] = {
            "top_neighbor": neighbors[0]["neighbor_symbol"] if neighbors else None,
            "top_correlation": neighbors[0]["correlation"] if neighbors else None,
        }
    return summary


def _active_symbol_map(
    security_ids: pd.Index,
    symbol_by_security: dict[str, str],
) -> dict[str, str]:
    return {
        security_id: symbol_by_security.get(security_id, security_id)
        for security_id in security_ids
    }


def _reject_duplicate_symbols(
    security_ids: pd.Index,
    symbol_by_security: dict[str, str],
) -> None:
    security_by_symbol: dict[str, list[str]] = {}
    for security_id in security_ids:
        symbol = symbol_by_security.get(security_id, security_id)
        security_by_symbol.setdefault(symbol, []).append(security_id)

    duplicates = {
        symbol: ids
        for symbol, ids in security_by_symbol.items()
        if len(ids) > 1
    }
    if not duplicates:
        return

    details = "; ".join(
        f"{symbol} -> {', '.join(sorted(ids))}"
        for symbol, ids in sorted(duplicates.items())
    )
    raise ValueError(
        "duplicate display symbols in selected universe; "
        f"use a narrower symbol filter or preserve unique symbols before snapshot: {details}"
    )


def _universe_frame(
    security_ids: pd.Index,
    symbol_by_security: dict[str, str],
) -> pd.DataFrame:
    rows = [
        {"security_id": security_id, "symbol": symbol_by_security.get(security_id, security_id)}
        for security_id in security_ids
    ]
    return pd.DataFrame(rows).sort_values(["symbol", "security_id"]).reset_index(drop=True)


def _storage_matrix(frame: pd.DataFrame, index_name: str) -> pd.DataFrame:
    stored = frame.copy()
    stored.index.name = index_name
    stored.columns.name = None
    return stored
