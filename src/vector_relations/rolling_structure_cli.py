from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .rolling_structure import (
    RollingStructureOutputPaths,
    write_rolling_structure_scan,
    write_rolling_structure_scan_from_prices,
)


def run(argv: Sequence[str] | None = None) -> RollingStructureOutputPaths:
    args = _parse_args(argv)
    if not args.snapshot:
        return _run_from_prices(args)
    if not args.node_metadata:
        raise ValueError("Provide --node-metadata when summarizing saved --snapshot directories.")
    return write_rolling_structure_scan(
        [Path(snapshot) for snapshot in args.snapshot],
        output_dir=args.output_dir,
        node_metadata_path=args.node_metadata,
        group_column=args.group_column,
        top_percentile=args.top_percentile,
        absolute_correlation_threshold=args.absolute_correlation_threshold,
    )


def _run_from_prices(args: argparse.Namespace) -> RollingStructureOutputPaths:
    if not args.rolling_start or not args.rolling_end:
        raise ValueError("Provide --rolling-start and --rolling-end when --snapshot is not used.")
    (
        prices,
        data_root,
        price_path,
        universe_path,
        security_classification_path,
        universe_filter_count,
        security_type_filter_count,
    ) = _read_prices_for_rolling(args)
    metadata_by_symbol = None
    node_metadata_path = args.node_metadata
    if node_metadata_path is None:
        if security_classification_path is None:
            security_classification_path = data_root / "meta" / "derived" / "security_classification.parquet"
        metadata_by_symbol = _read_classification_metadata_by_symbol(
            security_classification_path,
            market=args.market,
        )
    return write_rolling_structure_scan_from_prices(
        prices=prices,
        output_dir=args.output_dir,
        node_metadata_path=node_metadata_path,
        metadata_by_symbol=metadata_by_symbol,
        market=args.market,
        rolling_start=args.rolling_start,
        rolling_end=args.rolling_end,
        window_months=args.window_months,
        stride_months=args.stride_months,
        price_column=args.price_column,
        min_observations=args.min_observations,
        group_column=args.group_column,
        top_percentile=args.top_percentile,
        absolute_correlation_threshold=args.absolute_correlation_threshold,
        source_metadata={
            "data_root": str(data_root),
            "source_price_path": str(price_path),
            "source_universe_path": str(universe_path) if universe_path else None,
            "source_security_classification_path": str(security_classification_path)
            if security_classification_path
            else None,
            "node_metadata_source": str(node_metadata_path)
            if node_metadata_path
            else "security_classification.parquet",
            "universe_scope": args.universe_scope,
            "universe_filter_security_count": universe_filter_count,
            "security_type_scope": args.security_type_scope,
            "security_type_filter_symbol_count": security_type_filter_count,
            "max_securities": args.max_securities,
        },
    )


def _read_classification_metadata_by_symbol(path: Path, *, market: str) -> dict[str, dict[str, str]]:
    if not path.exists():
        raise ValueError(f"Security classification parquet does not exist: {path}")
    from .cli import _import_duckdb, _sql_literal, _sql_path

    duckdb = _import_duckdb()
    sql = f"""
        select
          regexp_replace(coalesce(ticker, symbol), '\\.[^.]+$', '') as symbol,
          coalesce(nullif(name, ''), '') as name,
          coalesce(nullif(type, ''), '') as type,
          coalesce(nullif(primary_sector, ''), nullif(eodhd_sector, ''), nullif(gic_sector, ''), '') as sector,
          coalesce(nullif(gic_industry, ''), nullif(eodhd_industry, ''), '') as industry,
          coalesce(nullif(primary_sector, ''), '') as primary_sector,
          coalesce(nullif(eodhd_sector, ''), '') as eodhd_sector,
          coalesce(nullif(eodhd_industry, ''), '') as eodhd_industry,
          coalesce(nullif(gic_sector, ''), '') as gic_sector,
          coalesce(nullif(gic_industry, ''), '') as gic_industry
        from read_parquet('{_sql_path(path)}')
        where market = '{_sql_literal(market.upper())}'
          and coalesce(ticker, symbol) is not null
    """
    metadata: dict[str, dict[str, str]] = {}
    columns = [
        "symbol",
        "name",
        "type",
        "sector",
        "industry",
        "primary_sector",
        "eodhd_sector",
        "eodhd_industry",
        "gic_sector",
        "gic_industry",
    ]
    for values in duckdb.sql(sql).fetchall():
        row = {column: str(value or "") for column, value in zip(columns, values, strict=True)}
        symbol = row["symbol"].strip().upper()
        if symbol:
            row["symbol"] = symbol
            metadata[symbol] = row
    if not metadata:
        raise ValueError(f"No classification metadata found for market {market.upper()} in {path}.")
    return metadata


def _read_prices_for_rolling(args: argparse.Namespace):
    from .cli import (
        _enforce_security_limit,
        _read_prices,
        _read_security_type_symbols_if_requested,
        _read_universe_security_ids_if_requested,
        _resolve_data_root,
    )

    data_root = _resolve_data_root(args.data_root)
    price_path = data_root / "meta" / "derived" / "backtest_prices_cleaned" / f"{args.market.lower()}.parquet"
    if not price_path.exists():
        raise ValueError(f"Price parquet does not exist: {price_path}")
    universe_security_ids, universe_path = _read_universe_security_ids_if_requested(
        data_root=data_root,
        market=args.market,
        universe_scope=args.universe_scope,
    )
    security_type_symbols, security_classification_path = _read_security_type_symbols_if_requested(
        data_root=data_root,
        market=args.market,
        security_type_scope=args.security_type_scope,
    )
    prices = _read_prices(
        price_path=price_path,
        period_start=args.rolling_start,
        period_end=args.rolling_end,
        price_column=args.price_column,
        symbols=[],
        universe_security_ids=universe_security_ids,
        security_type_symbols=security_type_symbols,
    )
    security_ids = sorted(prices["security_id"].dropna().astype(str).unique())
    _enforce_security_limit(len(security_ids), args.max_securities)
    return (
        prices,
        data_root,
        price_path,
        universe_path,
        security_classification_path,
        len(universe_security_ids) if universe_security_ids is not None else None,
        len(security_type_symbols) if security_type_symbols is not None else None,
    )


def main(argv: Sequence[str] | None = None) -> int:
    try:
        outputs = run(argv)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Wrote rolling structure metadata: {outputs.metadata_path}")
    print(f"Wrote group summary: {outputs.group_summary_path}")
    print(f"Wrote cross-group summary: {outputs.cross_group_summary_path}")
    print(f"Wrote group deltas: {outputs.group_delta_path}")
    print(f"Wrote cross-group deltas: {outputs.cross_group_delta_path}")
    print(f"Wrote markdown summary: {outputs.markdown_path}")
    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Summarize descriptive group-level structure from saved relationship snapshots "
            "or from in-memory rolling price windows."
        )
    )
    parser.add_argument(
        "--snapshot",
        action="append",
        help=(
            "Snapshot output directory containing metadata.json, universe.csv, returns.csv, "
            "and correlations.csv. Pass once per window in display order."
        ),
    )
    parser.add_argument("--data-root", help="stock_data root for direct rolling price-window mode.")
    parser.add_argument("--market", default="US", help="Single market to analyze in direct rolling mode.")
    parser.add_argument("--rolling-start", help="First rolling-window start date, e.g. 2020-01-01.")
    parser.add_argument("--rolling-end", help="Last date allowed for complete rolling windows.")
    parser.add_argument("--window-months", type=int, default=6)
    parser.add_argument("--stride-months", type=int, default=1)
    parser.add_argument("--price-column", default="adjusted_close")
    parser.add_argument("--min-observations", type=int, default=60)
    parser.add_argument(
        "--max-securities",
        type=int,
        default=1000,
        help="Stop before rolling correlation builds when selected securities exceed this count.",
    )
    parser.add_argument(
        "--universe-scope",
        choices=["prices", "standard"],
        default="prices",
        help="Direct rolling mode: all price rows, or standard backtest universe only.",
    )
    parser.add_argument(
        "--security-type-scope",
        choices=["all", "common-stock"],
        default="all",
        help="Direct rolling mode: optionally filter with security_classification.type.",
    )
    parser.add_argument(
        "--node-metadata",
        help=(
            "CSV keyed by symbol/ticker containing existing group labels such as sector or industry. "
            "Direct rolling mode can omit this and use security_classification.parquet."
        ),
    )
    parser.add_argument(
        "--group-column",
        default="sector",
        help="Existing metadata column to group by. This is a group-by key, not a classifier.",
    )
    parser.add_argument(
        "--top-percentile",
        type=float,
        default=0.05,
        help="Regime-relative strong-edge fraction, e.g. 0.05 means top 5%% correlations per window.",
    )
    parser.add_argument(
        "--absolute-correlation-threshold",
        type=float,
        default=0.5,
        help="Secondary absolute strong-edge count threshold.",
    )
    parser.add_argument("--output-dir", default="outputs/relation_snapshot_rolling_structure")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
