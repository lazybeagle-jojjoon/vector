from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Sequence



def run(argv: Sequence[str] | None = None):
    args = _parse_args(argv)
    build_relation_snapshot, write_snapshot_outputs = _import_runtime_tools()
    data_root = _resolve_data_root(args.data_root)
    price_path = data_root / "meta" / "derived" / "backtest_prices_cleaned" / f"{args.market.lower()}.parquet"
    if not price_path.exists():
        raise SystemExit(f"Price parquet does not exist: {price_path}")

    symbols = _split_csv_arg(args.symbols)
    acceptance_examples = _split_csv_arg(args.acceptance_examples)
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
        period_start=args.period_start,
        period_end=args.period_end,
        price_column=args.price_column,
        symbols=symbols,
        universe_security_ids=universe_security_ids,
        security_type_symbols=security_type_symbols,
    )
    security_ids = sorted(prices["security_id"].dropna().astype(str).unique())
    _enforce_security_limit(len(security_ids), args.max_securities)
    market_caps = _read_market_caps_if_present(
        data_root=data_root,
        market=args.market,
        period_start=args.period_start,
        period_end=args.period_end,
        security_ids=security_ids,
    )
    snapshot = build_relation_snapshot(
        prices=prices,
        market=args.market,
        period_start=args.period_start,
        period_end=args.period_end,
        price_column=args.price_column,
        top_k=args.top_k,
        projection_seed=args.projection_seed,
        min_observations=args.min_observations,
        acceptance_examples=acceptance_examples,
        market_caps=market_caps,
    )
    residual_classification_meta = _residual_classification_metadata(
        market=args.market,
        security_classification_path=security_classification_path,
        active_symbols=snapshot.universe["symbol"].astype(str).tolist(),
    )
    snapshot.metadata.update(
        {
            "data_root": str(data_root),
            "source_price_path": str(price_path),
            "source_universe_path": str(universe_path) if universe_path else None,
            "source_security_classification_path": str(security_classification_path)
            if security_classification_path
            else None,
            "universe_scope": args.universe_scope,
            "universe_filter_security_count": len(universe_security_ids)
            if universe_security_ids is not None
            else None,
            "security_type_scope": args.security_type_scope,
            "security_type_filter_symbol_count": len(security_type_symbols)
            if security_type_symbols is not None
            else None,
            "symbol_filter": symbols,
            "max_securities": args.max_securities,
            **residual_classification_meta,
        }
    )
    return write_snapshot_outputs(snapshot, args.output_dir)


def main(argv: Sequence[str] | None = None) -> int:
    outputs = run(argv)
    print(f"Wrote metadata: {outputs.metadata_path}")
    print(f"Wrote universe: {outputs.universe_path}")
    print(f"Wrote returns: {outputs.returns_path}")
    print(f"Wrote correlations: {outputs.correlations_path}")
    print(f"Wrote distances: {outputs.distances_path}")
    print(f"Wrote neighbors: {outputs.neighbors_path}")
    print(f"Wrote scatter: {outputs.scatter_path}")
    print(f"Wrote HTML: {outputs.html_path}")
    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a single-period ticker relation snapshot.")
    parser.add_argument("--data-root", help="stock_data root. Defaults to STOCK_DATA_ROOT.")
    parser.add_argument("--market", default="US", help="Single market to analyze, e.g. US or KR.")
    parser.add_argument("--period-start", default="2024-01-01")
    parser.add_argument("--period-end", default="2026-05-22")
    parser.add_argument("--price-column", default="adjusted_close")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--projection-seed", type=int, default=42)
    parser.add_argument("--min-observations", type=int, default=400)
    parser.add_argument(
        "--max-securities",
        type=int,
        default=1000,
        help="Stop before correlation matrix build when selected securities exceed this count.",
    )
    parser.add_argument(
        "--universe-scope",
        choices=["prices", "standard"],
        default="prices",
        help="Use all rows available in the price file, or filter to backtest_universe standard membership.",
    )
    parser.add_argument(
        "--security-type-scope",
        choices=["all", "common-stock"],
        default="all",
        help="Optionally filter with security_classification.type using existing data only.",
    )
    parser.add_argument("--symbols", default="", help="Optional comma-separated symbol allowlist.")
    parser.add_argument(
        "--acceptance-examples",
        default="AAPL,MSFT",
        help="Comma-separated symbols expected to have intuitive peers.",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/relation_snapshot_us_2024-01-01_2026-05-22",
    )
    return parser.parse_args(argv)


def _resolve_data_root(data_root: str | None) -> Path:
    value = data_root or os.environ.get("STOCK_DATA_ROOT")
    if not value:
        raise SystemExit("Provide --data-root or set STOCK_DATA_ROOT.")
    path = Path(value).expanduser()
    if not path.exists():
        raise SystemExit(f"Data root does not exist: {path}")
    return path


def _split_csv_arg(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _read_prices(
    *,
    price_path: Path,
    period_start: str,
    period_end: str,
    price_column: str,
    symbols: list[str],
    universe_security_ids: list[str] | None,
    security_type_symbols: list[str] | None,
) -> pd.DataFrame:
    duckdb = _import_duckdb()
    symbol_filter = _symbol_filter_sql(symbols)
    universe_filter = _security_filter_sql(universe_security_ids) if universe_security_ids is not None else ""
    security_type_filter = _normalized_symbol_filter_sql(security_type_symbols) if security_type_symbols is not None else ""
    sentinel_filter = "and coalesce(is_sentinel, false) = false"
    sql = f"""
        select security_id, regexp_replace(symbol, '\\.[^.]+$', '') as symbol, date, {price_column}
        from read_parquet('{_sql_path(price_path)}')
        where date >= '{_sql_literal(period_start)}'
          and date <= '{_sql_literal(period_end)}'
          and {price_column} is not null
          and {price_column} > 0
          {sentinel_filter}
          {symbol_filter}
          {universe_filter}
          {security_type_filter}
    """
    return duckdb.sql(sql).df()


def _read_universe_security_ids_if_requested(
    *,
    data_root: Path,
    market: str,
    universe_scope: str,
) -> tuple[list[str] | None, Path | None]:
    if universe_scope == "prices":
        return None, None
    if universe_scope != "standard":
        raise SystemExit(f"Unsupported universe scope: {universe_scope}")

    path = data_root / "meta" / "derived" / "backtest_universe.parquet"
    if not path.exists():
        raise SystemExit(f"Universe parquet does not exist: {path}")
    duckdb = _import_duckdb()
    sql = f"""
        select distinct security_id
        from read_parquet('{_sql_path(path)}')
        where market = '{_sql_literal(market.upper())}'
          and coalesce(is_in_standard_universe, false) = true
          and coalesce(is_etf, false) = false
          and security_id is not null
    """
    security_ids = [row[0] for row in duckdb.sql(sql).fetchall()]
    if not security_ids:
        raise SystemExit(f"No securities found for universe scope '{universe_scope}' and market {market.upper()}.")
    return sorted(str(security_id) for security_id in security_ids), path


def _read_security_type_symbols_if_requested(
    *,
    data_root: Path,
    market: str,
    security_type_scope: str,
) -> tuple[list[str] | None, Path | None]:
    if security_type_scope == "all":
        return None, None
    if security_type_scope != "common-stock":
        raise SystemExit(f"Unsupported security type scope: {security_type_scope}")

    path = data_root / "meta" / "derived" / "security_classification.parquet"
    if not path.exists():
        raise SystemExit(f"Security classification parquet does not exist: {path}")
    duckdb = _import_duckdb()
    sql = f"""
        select distinct ticker
        from read_parquet('{_sql_path(path)}')
        where market = '{_sql_literal(market.upper())}'
          and type = 'Common Stock'
          and ticker is not null
    """
    symbols = [row[0] for row in duckdb.sql(sql).fetchall()]
    if not symbols:
        raise SystemExit(
            f"No symbols found for security type scope '{security_type_scope}' and market {market.upper()}."
        )
    return sorted(str(symbol) for symbol in symbols), path


def _residual_classification_metadata(
    *,
    market: str,
    security_classification_path: Path | None,
    active_symbols: list[str],
) -> dict[str, object]:
    if security_classification_path is None:
        return {}
    if not active_symbols:
        return {
            "residual_common_stock_asset_management_count": 0,
            "residual_common_stock_asset_management_symbols_sample": [],
            "residual_common_stock_asset_management_note": (
                "Existing classification signal only; not excluded in v1."
            ),
        }

    duckdb = _import_duckdb()
    symbol_filter = _normalized_ticker_filter_sql(active_symbols)
    sql = f"""
        select distinct ticker
        from read_parquet('{_sql_path(security_classification_path)}')
        where market = '{_sql_literal(market.upper())}'
          and type = 'Common Stock'
          and eodhd_industry = 'Asset Management'
          {symbol_filter}
        order by ticker
    """
    symbols = [str(row[0]) for row in duckdb.sql(sql).fetchall()]
    return {
        "residual_common_stock_asset_management_count": len(symbols),
        "residual_common_stock_asset_management_symbols_sample": symbols[:20],
        "residual_common_stock_asset_management_note": (
            "Existing classification signal only; not excluded in v1."
        ),
    }


def _read_market_caps_if_present(
    *,
    data_root: Path,
    market: str,
    period_start: str,
    period_end: str,
    security_ids: list[str],
) -> pd.DataFrame | None:
    path = data_root / "meta" / "derived" / "global_market_cap_daily" / f"{market.lower()}.parquet"
    if not path.exists():
        return None
    duckdb = _import_duckdb()
    security_filter = _security_filter_sql(security_ids)
    sql = f"""
        select security_id, date, market_cap
        from read_parquet('{_sql_path(path)}')
        where date >= '{_sql_literal(period_start)}'
          and date <= '{_sql_literal(period_end)}'
          and market_cap is not null
          and market_cap > 0
          {security_filter}
    """
    return duckdb.sql(sql).df()


def _symbol_filter_sql(symbols: list[str]) -> str:
    if not symbols:
        return ""
    quoted = ", ".join(f"'{_sql_literal(symbol)}'" for symbol in symbols)
    return f"and (symbol in ({quoted}) or regexp_replace(symbol, '\\.[^.]+$', '') in ({quoted}) or security_id in ({quoted}))"


def _security_filter_sql(security_ids: list[str]) -> str:
    if not security_ids:
        return "and false"
    quoted = ", ".join(f"'{_sql_literal(security_id)}'" for security_id in security_ids)
    return f"and security_id in ({quoted})"


def _normalized_symbol_filter_sql(symbols: list[str]) -> str:
    if not symbols:
        return "and false"
    quoted = ", ".join(f"'{_sql_literal(symbol)}'" for symbol in symbols)
    return f"and regexp_replace(symbol, '\\.[^.]+$', '') in ({quoted})"


def _normalized_ticker_filter_sql(symbols: list[str]) -> str:
    if not symbols:
        return "and false"
    quoted = ", ".join(f"'{_sql_literal(symbol)}'" for symbol in symbols)
    return f"and regexp_replace(ticker, '\\.[^.]+$', '') in ({quoted})"


def _enforce_security_limit(security_count: int, max_securities: int) -> None:
    if max_securities < 1:
        raise SystemExit("--max-securities must be at least 1")
    if security_count > max_securities:
        raise SystemExit(
            f"security count {security_count} exceeds --max-securities {max_securities}; "
            "use --symbols for a smaller run or raise --max-securities intentionally"
        )


def _sql_path(path: Path) -> str:
    return str(path).replace("'", "''")


def _sql_literal(value: str) -> str:
    return value.replace("'", "''")


def _import_runtime_tools():
    try:
        from .output import write_snapshot_outputs
        from .pipeline import build_relation_snapshot
    except ModuleNotFoundError as exc:
        if exc.name == "pandas":
            raise SystemExit(
                "pandas is required for snapshot builds. Run with: "
                "uv run --with duckdb --with pandas --with pyarrow python -m vector_relations.cli ..."
            ) from exc
        raise
    return build_relation_snapshot, write_snapshot_outputs


def _import_duckdb():
    try:
        import duckdb
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "duckdb is required for Parquet input. Run with: "
            "uv run --with duckdb --with pandas --with pyarrow python -m vector_relations.cli ..."
        ) from exc
    return duckdb


if __name__ == "__main__":
    raise SystemExit(main())
