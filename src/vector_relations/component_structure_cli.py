from __future__ import annotations

import argparse
from typing import Sequence

from .component_structure import ComponentStructureOutputPaths, write_component_structure_from_prices


def run(argv: Sequence[str] | None = None) -> ComponentStructureOutputPaths:
    args = _parse_args(argv)
    prices, source_metadata = _read_inputs(args)
    return write_component_structure_from_prices(
        prices=prices,
        output_dir=args.output_dir,
        market=args.market,
        rolling_start=args.rolling_start,
        rolling_end=args.rolling_end,
        window_months=args.window_months,
        window_months_list=_split_ints(args.window_months_list) if args.window_months_list else None,
        stride_months=args.stride_months,
        price_column=args.price_column,
        min_observations=args.min_observations,
        thresholds=_split_thresholds(args.thresholds),
        max_components_per_frame=args.max_components_per_frame,
        max_top_symbols=args.max_top_symbols,
        source_metadata=source_metadata,
    )


def main(argv: Sequence[str] | None = None) -> int:
    try:
        outputs = run(argv)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Wrote component metadata: {outputs.metadata_path}")
    print(f"Wrote component frame summary: {outputs.frame_summary_path}")
    print(f"Wrote component detail: {outputs.component_detail_path}")
    print(f"Wrote component flow: {outputs.component_flow_path}")
    print(f"Wrote component markdown: {outputs.markdown_path}")
    return 0


def _read_inputs(args: argparse.Namespace):
    if args.prices_csv:
        pd = _import_pandas()
        return pd.read_csv(args.prices_csv), {"input_mode": "prices_csv"}
    prices, source_metadata, _metadata_by_symbol = _read_prices_from_data_root(args)
    source_metadata = {**source_metadata, "input_mode": "data_root_price_component_windows"}
    return prices, source_metadata


def _read_prices_from_data_root(args: argparse.Namespace):
    from .rolling_threshold_sweep_cli import _read_prices_from_data_root

    return _read_prices_from_data_root(args)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build descriptive connected components from rolling return-correlation windows."
    )
    parser.add_argument("--prices-csv", help="Testing/local CSV input with security_id,symbol,date,price columns.")
    parser.add_argument("--data-root", help="stock_data root for parquet input. Defaults to STOCK_DATA_ROOT.")
    parser.add_argument("--market", default="US")
    parser.add_argument("--rolling-start", required=True)
    parser.add_argument("--rolling-end", required=True)
    parser.add_argument("--window-months", type=int, default=6)
    parser.add_argument("--window-months-list", help="Optional comma-separated window lengths, e.g. 6,12.")
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
    parser.add_argument("--node-metadata", help="Accepted for compatibility; ignored by component scanner.")
    parser.add_argument("--group-column", default="sector", help="Accepted for input compatibility; ignored.")
    parser.add_argument("--thresholds", default="0.5,0.6,0.7")
    parser.add_argument("--top-percentile", type=float, default=0.05, help="Accepted for input compatibility; ignored.")
    parser.add_argument("--max-components-per-frame", type=int, default=25)
    parser.add_argument("--max-top-symbols", type=int, default=12)
    parser.add_argument("--output-dir", default="outputs/relation_snapshot_component_structure")
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
            "component structure CSV mode requires pandas. Run with: "
            "uv run --no-project --with pandas python -m vector_relations.component_structure_cli ..."
        ) from exc
    return pd


if __name__ == "__main__":
    raise SystemExit(main())
