import json

import pandas as pd
import pytest

pytest.importorskip("duckdb")
from vector_relations.cli import run


def test_run_reads_standard_price_parquet_and_writes_outputs(tmp_path):
    data_root = tmp_path / "stock_data"
    price_dir = data_root / "meta" / "derived" / "backtest_prices_cleaned"
    market_cap_dir = data_root / "meta" / "derived" / "global_market_cap_daily"
    price_dir.mkdir(parents=True)
    market_cap_dir.mkdir(parents=True)
    prices = pd.DataFrame(
        [
            ("SEC:AAA", "AAA.US", "2024-01-01", 100.0, False),
            ("SEC:AAA", "AAA.US", "2024-01-02", 101.0, False),
            ("SEC:AAA", "AAA.US", "2024-01-03", 102.0, False),
            ("SEC:AAA", "AAA.US", "2024-01-04", 103.0, False),
            ("SEC:BBB", "BBB.US", "2024-01-01", 200.0, False),
            ("SEC:BBB", "BBB.US", "2024-01-02", 202.0, False),
            ("SEC:BBB", "BBB.US", "2024-01-03", 204.0, False),
            ("SEC:BBB", "BBB.US", "2024-01-04", 206.0, False),
            ("SEC:ZZZ", "ZZZ.US", "2024-01-01", 50.0, False),
            ("SEC:ZZZ", "ZZZ.US", "2024-01-02", 49.0, False),
            ("SEC:ZZZ", "ZZZ.US", "2024-01-03", 48.0, False),
            ("SEC:ZZZ", "ZZZ.US", "2024-01-04", 47.0, False),
            ("SEC:DROP", "DROP.US", "2024-01-01", 10.0, True),
            ("SEC:DROP", "DROP.US", "2024-01-02", 11.0, True),
        ],
        columns=["security_id", "symbol", "date", "adjusted_close", "is_sentinel"],
    )
    prices.to_parquet(price_dir / "us.parquet")
    market_caps = pd.DataFrame(
        [
            ("SEC:AAA", "2024-01-01", 1000.0),
            ("SEC:AAA", "2024-01-04", 1100.0),
            ("SEC:BBB", "2024-01-01", 500.0),
            ("SEC:BBB", "2024-01-04", 550.0),
        ],
        columns=["security_id", "date", "market_cap"],
    )
    market_caps.to_parquet(market_cap_dir / "us.parquet")

    output_dir = tmp_path / "out"
    outputs = run(
        [
            "--data-root",
            str(data_root),
            "--market",
            "US",
            "--period-start",
            "2024-01-01",
            "--period-end",
            "2024-01-04",
            "--symbols",
            "AAA,BBB,ZZZ",
            "--acceptance-examples",
            "AAA,BBB",
            "--top-k",
            "1",
            "--projection-seed",
            "42",
            "--min-observations",
            "2",
            "--output-dir",
            str(output_dir),
        ]
    )

    assert outputs.metadata_path == output_dir / "metadata.json"
    metadata = json.loads(outputs.metadata_path.read_text(encoding="utf-8"))
    assert metadata["market"] == "US"
    assert metadata["source_price_path"].endswith("backtest_prices_cleaned/us.parquet")
    assert metadata["symbol_filter"] == ["AAA", "BBB", "ZZZ"]
    assert metadata["market_cap_overlay"] == "included"
    assert metadata["artifact_files"]["returns"] == "returns.csv"

    neighbors = outputs.neighbors_path.read_text(encoding="utf-8")
    assert "AAA,1,BBB" in neighbors
    assert "DROP" not in neighbors

    scatter = outputs.scatter_path.read_text(encoding="utf-8")
    assert "SEC:AAA,AAA" in scatter
    assert ",0.10000000000000009" in scatter

    html = outputs.html_path.read_text(encoding="utf-8")
    assert "Ticker Relationship Scatter" in html


def test_run_stops_when_security_count_exceeds_limit(tmp_path):
    data_root = tmp_path / "stock_data"
    price_dir = data_root / "meta" / "derived" / "backtest_prices_cleaned"
    price_dir.mkdir(parents=True)
    prices = pd.DataFrame(
        [
            ("SEC:AAA", "AAA.US", "2024-01-01", 100.0, False),
            ("SEC:AAA", "AAA.US", "2024-01-02", 101.0, False),
            ("SEC:BBB", "BBB.US", "2024-01-01", 200.0, False),
            ("SEC:BBB", "BBB.US", "2024-01-02", 202.0, False),
            ("SEC:CCC", "CCC.US", "2024-01-01", 300.0, False),
            ("SEC:CCC", "CCC.US", "2024-01-02", 303.0, False),
        ],
        columns=["security_id", "symbol", "date", "adjusted_close", "is_sentinel"],
    )
    prices.to_parquet(price_dir / "us.parquet")

    try:
        run(
            [
                "--data-root",
                str(data_root),
                "--market",
                "US",
                "--period-start",
                "2024-01-01",
                "--period-end",
                "2024-01-02",
                "--max-securities",
                "2",
                "--output-dir",
                str(tmp_path / "out"),
            ]
        )
    except SystemExit as exc:
        assert "security count 3 exceeds --max-securities 2" in str(exc)
    else:
        raise AssertionError("expected SystemExit for oversized run")


def test_run_filters_to_standard_universe_when_requested(tmp_path):
    data_root = tmp_path / "stock_data"
    price_dir = data_root / "meta" / "derived" / "backtest_prices_cleaned"
    universe_dir = data_root / "meta" / "derived"
    price_dir.mkdir(parents=True)
    prices = pd.DataFrame(
        [
            ("SEC:AAA", "AAA.US", "2024-01-01", 100.0, False),
            ("SEC:AAA", "AAA.US", "2024-01-02", 101.0, False),
            ("SEC:AAA", "AAA.US", "2024-01-03", 102.0, False),
            ("SEC:BBB", "BBB.US", "2024-01-01", 200.0, False),
            ("SEC:BBB", "BBB.US", "2024-01-02", 202.0, False),
            ("SEC:BBB", "BBB.US", "2024-01-03", 204.0, False),
            ("SEC:FUND", "FUND.US", "2024-01-01", 300.0, False),
            ("SEC:FUND", "FUND.US", "2024-01-02", 303.0, False),
            ("SEC:FUND", "FUND.US", "2024-01-03", 306.0, False),
        ],
        columns=["security_id", "symbol", "date", "adjusted_close", "is_sentinel"],
    )
    prices.to_parquet(price_dir / "us.parquet")
    universe = pd.DataFrame(
        [
            ("US", "SEC:AAA", True, False),
            ("US", "SEC:BBB", True, False),
            ("US", "SEC:FUND", False, True),
        ],
        columns=["market", "security_id", "is_in_standard_universe", "is_etf"],
    )
    universe.to_parquet(universe_dir / "backtest_universe.parquet")

    output_dir = tmp_path / "out"
    outputs = run(
        [
            "--data-root",
            str(data_root),
            "--market",
            "US",
            "--period-start",
            "2024-01-01",
            "--period-end",
            "2024-01-03",
            "--universe-scope",
            "standard",
            "--top-k",
            "1",
            "--min-observations",
            "2",
            "--output-dir",
            str(output_dir),
        ]
    )

    metadata = json.loads(outputs.metadata_path.read_text(encoding="utf-8"))
    assert metadata["universe_scope"] == "standard"
    assert metadata["universe_filter_security_count"] == 2
    assert metadata["source_universe_path"].endswith("backtest_universe.parquet")

    universe_csv = outputs.universe_path.read_text(encoding="utf-8")
    assert "SEC:AAA,AAA" in universe_csv
    assert "SEC:BBB,BBB" in universe_csv
    assert "FUND" not in universe_csv

    neighbors = outputs.neighbors_path.read_text(encoding="utf-8")
    assert "FUND" not in neighbors


def test_run_filters_to_common_stock_classification_when_requested(tmp_path):
    data_root = tmp_path / "stock_data"
    price_dir = data_root / "meta" / "derived" / "backtest_prices_cleaned"
    derived_dir = data_root / "meta" / "derived"
    price_dir.mkdir(parents=True)
    prices = pd.DataFrame(
        [
            ("SEC:AAA", "AAA.US", "2024-01-01", 100.0, False),
            ("SEC:AAA", "AAA.US", "2024-01-02", 101.0, False),
            ("SEC:AAA", "AAA.US", "2024-01-03", 102.0, False),
            ("SEC:BBB", "BBB.US", "2024-01-01", 200.0, False),
            ("SEC:BBB", "BBB.US", "2024-01-02", 202.0, False),
            ("SEC:BBB", "BBB.US", "2024-01-03", 204.0, False),
            ("SEC:FUND", "FUND.US", "2024-01-01", 300.0, False),
            ("SEC:FUND", "FUND.US", "2024-01-02", 303.0, False),
            ("SEC:FUND", "FUND.US", "2024-01-03", 306.0, False),
        ],
        columns=["security_id", "symbol", "date", "adjusted_close", "is_sentinel"],
    )
    prices.to_parquet(price_dir / "us.parquet")
    classification = pd.DataFrame(
        [
            ("US", "AAA", "Common Stock", "Asset Management"),
            ("US", "BBB", "Common Stock", "Software - Application"),
            ("US", "FUND", "FUND", None),
        ],
        columns=["market", "ticker", "type", "eodhd_industry"],
    )
    classification.to_parquet(derived_dir / "security_classification.parquet")

    output_dir = tmp_path / "out"
    outputs = run(
        [
            "--data-root",
            str(data_root),
            "--market",
            "US",
            "--period-start",
            "2024-01-01",
            "--period-end",
            "2024-01-03",
            "--security-type-scope",
            "common-stock",
            "--top-k",
            "1",
            "--min-observations",
            "2",
            "--output-dir",
            str(output_dir),
        ]
    )

    metadata = json.loads(outputs.metadata_path.read_text(encoding="utf-8"))
    assert metadata["security_type_scope"] == "common-stock"
    assert metadata["security_type_filter_symbol_count"] == 2
    assert metadata["source_security_classification_path"].endswith("security_classification.parquet")
    assert metadata["residual_common_stock_asset_management_count"] == 1
    assert metadata["residual_common_stock_asset_management_symbols_sample"] == ["AAA"]

    universe_csv = outputs.universe_path.read_text(encoding="utf-8")
    assert "SEC:AAA,AAA" in universe_csv
    assert "SEC:BBB,BBB" in universe_csv
    assert "FUND" not in universe_csv
