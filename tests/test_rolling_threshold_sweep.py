import csv
import json
import os
import subprocess
import sys
import textwrap

import pytest

from vector_relations.rolling_threshold_sweep import write_threshold_sweep_from_prices
from vector_relations.rolling_threshold_sweep_cli import run


def test_threshold_sweep_writes_market_normalized_ratios_and_report(tmp_path):
    pd = pytest.importorskip("pandas")
    metadata_csv = tmp_path / "node_metadata.csv"
    _write_metadata(
        metadata_csv,
        [
            ("A1", "Alpha"),
            ("A2", "Alpha"),
            ("B1", "Beta"),
            ("B2", "Beta"),
        ],
    )
    prices = _price_frame(
        pd,
        {
            "SEC:A1": ("A1", [100, 101, 103, 106, 108, 111, 114, 116]),
            "SEC:A2": ("A2", [50, 50.5, 51.5, 53, 54, 55.5, 57, 58]),
            "SEC:B1": ("B1", [80, 79, 78, 78.5, 79, 80, 80.5, 81]),
            "SEC:B2": ("B2", [30, 29.5, 29, 29.2, 29.4, 29.8, 30.0, 30.2]),
        },
    )

    outputs = write_threshold_sweep_from_prices(
        prices=prices,
        output_dir=tmp_path / "sweep",
        node_metadata_path=metadata_csv,
        market="US",
        rolling_start="2020-01-01",
        rolling_end="2020-04-30",
        window_months=2,
        stride_months=1,
        price_column="adjusted_close",
        min_observations=2,
        group_column="sector",
        thresholds=[0.5, 0.7],
        top_percentile=0.25,
    )

    metadata = json.loads(outputs.metadata_path.read_text(encoding="utf-8"))
    assert metadata["mode"] == "descriptive_threshold_sweep"
    assert metadata["thresholds"] == [0.5, 0.7]
    assert "baseline-normalized" in metadata["interpretation_note"]
    assert "structure-at-t to return-at-t+1" in metadata["brightline"]

    market_rows = _read_csv(outputs.market_summary_path)
    first_market = _find(market_rows, frame_index="0", threshold="0.5")
    assert first_market["market_pair_count"] == "6"
    assert 0.0 <= float(first_market["market_strong_edge_ratio"]) <= 1.0

    group_rows = _read_csv(outputs.group_summary_path)
    alpha = _find(group_rows, frame_index="0", threshold="0.5", group_name="Alpha")
    assert alpha["internal_pair_count"] == "1"
    assert alpha["market_strong_edge_ratio"] == first_market["market_strong_edge_ratio"]
    assert alpha["internal_strong_edge_ratio_normalized"] != ""

    cross_rows = _read_csv(outputs.cross_group_summary_path)
    cross = _find(cross_rows, frame_index="0", threshold="0.5", group_a="Alpha", group_b="Beta")
    assert cross["cross_pair_count"] == "4"
    assert cross["cross_strong_edge_ratio_normalized"] != ""

    html = outputs.html_path.read_text(encoding="utf-8")
    assert "Threshold Sweep Report" in html
    assert "Market strong-edge baseline" in html
    assert "baseline-normalized ratio" in html
    assert "fixed thresholds are zoom levels" in html
    assert "not a forecast" in html
    assert "leads to" not in html


def test_threshold_sweep_cli_writes_outputs(tmp_path):
    pd = pytest.importorskip("pandas")
    metadata_csv = tmp_path / "node_metadata.csv"
    _write_metadata(metadata_csv, [("A1", "Alpha"), ("A2", "Alpha")])
    prices = _price_frame(
        pd,
        {
            "SEC:A1": ("A1", [100, 101, 102, 103, 104, 105, 106, 107]),
            "SEC:A2": ("A2", [50, 50.5, 51, 51.5, 52, 52.5, 53, 53.5]),
        },
    )
    price_csv = tmp_path / "prices.csv"
    prices.to_csv(price_csv, index=False)

    outputs = run(
        [
            "--prices-csv",
            str(price_csv),
            "--node-metadata",
            str(metadata_csv),
            "--market",
            "US",
            "--rolling-start",
            "2020-01-01",
            "--rolling-end",
            "2020-04-30",
            "--window-months",
            "2",
            "--stride-months",
            "1",
            "--min-observations",
            "2",
            "--thresholds",
            "0.5,0.7",
            "--top-percentile",
            "0.25",
            "--output-dir",
            str(tmp_path / "sweep"),
        ]
    )

    assert outputs.metadata_path.exists()
    assert outputs.html_path.exists()


def test_threshold_sweep_cli_import_is_pandas_free():
    code = textwrap.dedent(
        """
        import importlib.abc
        import sys

        class BlockPandasFinder(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname == "pandas" or fullname.startswith("pandas."):
                    raise ModuleNotFoundError(f"blocked import: {fullname}")
                return None

        sys.meta_path.insert(0, BlockPandasFinder())
        import vector_relations.rolling_threshold_sweep_cli
        print("ok")
        """
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.join(os.getcwd(), "src")

    result = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def _price_frame(pd, prices_by_security):
    rows = []
    dates = pd.date_range("2020-01-01", periods=8, freq="15D")
    for security_id, (symbol, prices) in prices_by_security.items():
        for date, price in zip(dates, prices, strict=True):
            rows.append(
                {
                    "security_id": security_id,
                    "symbol": symbol,
                    "date": date.strftime("%Y-%m-%d"),
                    "adjusted_close": price,
                }
            )
    return pd.DataFrame(rows)


def _write_metadata(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["symbol", "sector"])
        writer.writerows(rows)


def _read_csv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _find(rows, **matches):
    for row in rows:
        if all(row.get(key) == value for key, value in matches.items()):
            return row
    raise AssertionError(f"row not found: {matches}")
