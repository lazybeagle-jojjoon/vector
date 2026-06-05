import csv
import json
import os
import subprocess
import sys
import textwrap

from vector_relations.component_pair_summary import write_component_pair_summary_from_prices
from vector_relations.component_pair_summary_cli import run


def test_component_pair_summary_measures_same_window_cross_relationships(tmp_path):
    pd = pytest_importorskip_pandas()
    prices = _price_frame_from_returns(
        pd,
        {
            "SEC:A1": ("A1", [0.10, 0.20, 0.10, 0.20]),
            "SEC:A2": ("A2", [0.10, 0.20, 0.10, 0.20]),
            "SEC:B1": ("B1", [0.08, 0.18, 0.12, 0.16]),
            "SEC:B2": ("B2", [0.08, 0.18, 0.12, 0.16]),
            "SEC:C1": ("C1", [-0.10, -0.20, -0.10, -0.20]),
            "SEC:C2": ("C2", [-0.10, -0.20, -0.10, -0.20]),
        },
    )

    outputs = write_component_pair_summary_from_prices(
        prices=prices,
        output_dir=tmp_path / "pairs",
        market="US",
        rolling_start="2020-01-01",
        rolling_end="2020-02-29",
        window_months=2,
        stride_months=1,
        price_column="adjusted_close",
        min_observations=2,
        component_threshold=0.99,
        cross_edge_threshold=0.5,
        min_component_size=2,
        min_cross_pair_count=4,
        top_n_pairs=10,
    )

    metadata = json.loads(outputs.metadata_path.read_text(encoding="utf-8"))
    assert metadata["mode"] == "descriptive_component_pair_summary"
    assert metadata["relationship"] == "return_correlation"
    assert metadata["component_threshold"] == 0.99
    assert metadata["cross_edge_threshold"] == 0.5
    assert metadata["min_component_density"] == 0.5
    assert "same-window" in metadata["interpretation_note"]
    assert "not a forecast" in metadata["disclaimer"]

    rows = _read_csv(outputs.pair_summary_path)
    pair = _find(rows, component_a_id="C01", component_b_id="C02")
    assert pair["component_a_size"] == "2"
    assert pair["component_b_size"] == "2"
    assert pair["cross_pair_count"] == "4"
    assert pair["cross_edge_count"] == "4"
    assert pair["cross_edge_density"] == "1"
    assert 0.5 < float(pair["mean_cross_correlation"]) < 0.99
    assert pair["median_cross_correlation"] == pair["mean_cross_correlation"]
    assert round(float(pair["normalized_cross_edge_density"]), 6) == 2.142857
    assert pair["component_a_top_symbols"] == "A1 A2"
    assert pair["component_b_top_symbols"] == "B1 B2"

    html = outputs.html_path.read_text(encoding="utf-8")
    assert "Component Pair Summary" in html
    assert "same-window component-to-component relationships" in html
    assert "No lead-lag" in html


def test_component_pair_summary_cli_writes_outputs(tmp_path):
    pd = pytest_importorskip_pandas()
    prices = _price_frame_from_returns(
        pd,
        {
            "SEC:A1": ("A1", [0.10, 0.20, 0.10, 0.20]),
            "SEC:A2": ("A2", [0.10, 0.20, 0.10, 0.20]),
            "SEC:B1": ("B1", [0.08, 0.18, 0.12, 0.16]),
            "SEC:B2": ("B2", [0.08, 0.18, 0.12, 0.16]),
        },
    )
    price_csv = tmp_path / "prices.csv"
    prices.to_csv(price_csv, index=False)

    outputs = run(
        [
            "--prices-csv",
            str(price_csv),
            "--market",
            "US",
            "--rolling-start",
            "2020-01-01",
            "--rolling-end",
            "2020-02-29",
            "--window-months",
            "2",
            "--stride-months",
            "1",
            "--min-observations",
            "2",
            "--component-threshold",
            "0.99",
            "--cross-edge-threshold",
            "0.5",
            "--min-component-size",
            "2",
            "--output-dir",
            str(tmp_path / "pairs"),
        ]
    )

    assert outputs.pair_summary_path.exists()
    assert outputs.html_path.exists()


def test_component_pair_summary_cli_import_is_pandas_free():
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
        import vector_relations.component_pair_summary_cli
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


def pytest_importorskip_pandas():
    import pytest

    return pytest.importorskip("pandas")


def _price_frame_from_returns(pd, returns_by_security):
    rows = []
    dates = pd.date_range("2020-01-01", periods=5, freq="14D")
    for security_id, (symbol, returns) in returns_by_security.items():
        price = 100.0
        rows.append(
            {
                "security_id": security_id,
                "symbol": symbol,
                "date": dates[0].strftime("%Y-%m-%d"),
                "adjusted_close": price,
            }
        )
        for date, value in zip(dates[1:], returns, strict=True):
            price *= 1.0 + value
            rows.append(
                {
                    "security_id": security_id,
                    "symbol": symbol,
                    "date": date.strftime("%Y-%m-%d"),
                    "adjusted_close": price,
                }
            )
    return pd.DataFrame(rows)


def _read_csv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _find(rows, **matches):
    for row in rows:
        if all(row.get(key) == value for key, value in matches.items()):
            return row
    raise AssertionError(f"row not found: {matches}")
