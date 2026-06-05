import csv
import json
import os
import subprocess
import sys
import textwrap

import pytest

from vector_relations.component_structure import write_component_structure_from_prices
from vector_relations.component_structure_cli import run


def test_component_structure_writes_threshold_components_without_labels(tmp_path):
    pd = pytest.importorskip("pandas")
    prices = _price_frame(
        pd,
        {
            "SEC:A1": ("A1", [100, 101, 102, 103, 104, 105, 106, 107]),
            "SEC:A2": ("A2", [50, 50.5, 51, 51.5, 52, 52.5, 53, 53.5]),
            "SEC:B1": ("B1", [100, 99, 98, 97, 96, 95, 94, 93]),
            "SEC:B2": ("B2", [30, 29.7, 29.4, 29.1, 28.8, 28.5, 28.2, 27.9]),
            "SEC:X": ("X", [10, 10.8, 9.7, 10.5, 9.6, 10.4, 9.5, 10.3]),
        },
    )

    outputs = write_component_structure_from_prices(
        prices=prices,
        output_dir=tmp_path / "components",
        market="US",
        rolling_start="2020-01-01",
        rolling_end="2020-04-30",
        window_months=2,
        stride_months=1,
        price_column="adjusted_close",
        min_observations=2,
        thresholds=[0.99999],
        max_components_per_frame=10,
    )

    metadata = json.loads(outputs.metadata_path.read_text(encoding="utf-8"))
    assert metadata["mode"] == "descriptive_connected_components"
    assert metadata["relationship"] == "return_correlation"
    assert "not a forecast" in metadata["disclaimer"]
    assert "Connected components are unnamed" in metadata["interpretation_note"]

    frame_rows = _read_csv(outputs.frame_summary_path)
    first_frame = _find(frame_rows, frame_index="0", threshold="0.99999")
    assert first_frame["component_count"] == "3"
    assert first_frame["non_singleton_component_count"] == "2"
    assert first_frame["singleton_count"] == "1"
    assert first_frame["giant_component_size"] == "2"

    detail_rows = _read_csv(outputs.component_detail_path)
    c01 = _find(detail_rows, frame_index="0", threshold="0.99999", component_id="C01")
    assert c01["size"] == "2"
    assert c01["top_symbols"] == "A1 A2"
    assert c01["edge_count"] == "1"
    assert c01["component_density"] == "1"
    assert "Technology" not in c01

    markdown = outputs.markdown_path.read_text(encoding="utf-8")
    assert "Connected Component Structure" in markdown
    assert "C01" in markdown
    assert "unnamed" in markdown
    assert "not investment advice" in markdown


def test_component_structure_cli_writes_outputs(tmp_path):
    pd = pytest.importorskip("pandas")
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
            "0.99999",
            "--output-dir",
            str(tmp_path / "components"),
        ]
    )

    assert outputs.metadata_path.exists()
    assert outputs.frame_summary_path.exists()
    assert outputs.component_detail_path.exists()


def test_component_structure_cli_import_is_pandas_free():
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
        import vector_relations.component_structure_cli
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


def _read_csv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _find(rows, **matches):
    for row in rows:
        if all(row.get(key) == value for key, value in matches.items()):
            return row
    raise AssertionError(f"row not found: {matches}")
