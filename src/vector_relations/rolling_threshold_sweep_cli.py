from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .rolling_threshold_sweep import ThresholdSweepOutputPaths, write_threshold_sweep_from_prices


def run(argv: Sequence[str] | None = None) -> ThresholdSweepOutputPaths:
    args = _parse_args(argv)
    prices, source_metadata, metadata_by_symbol = _read_inputs(args)
    return write_threshold_sweep_from_prices(
        prices=prices,
        output_dir=args.output_dir,
        node_metadata_path=args.node_metadata,
        metadata_by_symbol=metadata_by_symbol,
        market=args.market,
        rolling_start=args.rolling_start,
        rolling_end=args.rolling_end,
        window_months=args.window_months,
        window_months_list=_split_ints(args.window_months_list) if args.window_months_list else None,
        stride_months=args.stride_months,
        price_column=args.price_column,
        min_observations=args.min_observations,
        group_column=args.group_column,
        thresholds=_split_thresholds(args.thresholds),
        top_percentile=args.top_percentile,
        source_metadata=source_metadata,
    )


def main(argv: Sequence[str] | None = None) -> int:
    try:
        outputs = run(argv)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Wrote threshold sweep metadata: {outputs.metadata_path}")
    print(f"Wrote threshold market summary: {outputs.market_summary_path}")
    print(f"Wrote threshold group summary: {outputs.group_summary_path}")
    print(f"Wrote threshold cross-group summary: {outputs.cross_group_summary_path}")
    print(f"Wrote threshold HTML report: {outputs.html_path}")
    return 0


def _read_inputs(args: argparse.Namespace):
    if args.prices_csv:
        pd = _import_pandas()
        return pd.read_csv(args.prices_csv), {"input_mode": "prices_csv"}, None
    return _read_prices_from_data_root(args)


def _read_prices_from_data_root(args: argparse.Namespace):
    from .rolling_structure_cli import _read_classification_metadata_by_symbol
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
    classification_path = security_classification_path or data_root / "meta" / "derived" / "security_classification.parquet"
    metadata_by_symbol = None
    if args.node_metadata is None:
        metadata_by_symbol = _read_classification_metadata_by_symbol(classification_path, market=args.market)
    return (
        prices,
        {
            "input_mode": "data_root_price_rolling_windows",
            "data_root": str(data_root),
            "source_price_path": str(price_path),
            "source_universe_path": str(universe_path) if universe_path else None,
            "source_security_classification_path": str(classification_path),
            "universe_scope": args.universe_scope,
            "security_type_scope": args.security_type_scope,
            "max_securities": args.max_securities,
        },
        metadata_by_symbol,
    )


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a descriptive threshold sweep over rolling return-correlation windows."
    )
    parser.add_argument("--prices-csv", help="Testing/local CSV input with security_id,symbol,date,price columns.")
    parser.add_argument("--data-root", help="stock_data root for parquet input. Defaults to STOCK_DATA_ROOT.")
    parser.add_argument("--market", default="US")
    parser.add_argument("--rolling-start", required=True)
    parser.add_argument("--rolling-end", required=True)
    parser.add_argument("--window-months", type=int, default=6)
    parser.add_argument(
        "--window-months-list",
        help="Optional comma-separated window lengths for one-axis smoothing comparison, e.g. 3,6,12.",
    )
    parser.add_argument("--stride-months", type=int, default=1)
    parser.add_argument("--price-column", default="adjusted_close")
    parser.add_argument("--min-observations", type=int, default=60)
    parser.add_argument(
        "--universe-scope",
        choices=["prices", "standard"],
        default="prices",
        help="Parquet mode: all price rows, or standard backtest universe only.",
    )
    parser.add_argument(
        "--security-type-scope",
        choices=["all", "common-stock"],
        default="all",
        help="Parquet mode: optionally filter with security_classification.type.",
    )
    parser.add_argument("--max-securities", type=int, default=1000)
    parser.add_argument(
        "--node-metadata",
        help="CSV keyed by symbol/ticker. Parquet mode can omit this and use security_classification.parquet.",
    )
    parser.add_argument("--group-column", default="sector")
    parser.add_argument("--thresholds", default="0.5,0.6,0.7")
    parser.add_argument("--top-percentile", type=float, default=0.05)
    parser.add_argument("--output-dir", default="outputs/relation_snapshot_threshold_sweep")
    return parser.parse_args(argv)


def _split_thresholds(value: str) -> list[float]:
    return [float(item.strip()) for item in value.split(",") if item.strip()]


def _split_ints(value: str) -> list[int]:
    return [int(item.strip()) for item in value.split(",") if item.strip()]


def _import_pandas():
    try:
        import pandas as pd
    except ModuleNotFoundError as exc:
        raise ValueError(
            "threshold sweep CSV mode requires pandas. Run with: "
            "uv run --no-project --with pandas python -m vector_relations.rolling_threshold_sweep_cli ..."
        ) from exc
    return pd


if __name__ == "__main__":
    raise SystemExit(main())
