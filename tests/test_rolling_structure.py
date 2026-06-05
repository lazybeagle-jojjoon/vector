import csv
import json
import os
import subprocess
import sys
import textwrap

import pytest

from vector_relations.rolling_structure import (
    write_rolling_structure_scan,
    write_rolling_structure_scan_from_prices,
)
from vector_relations.rolling_structure_cli import run


def test_write_rolling_structure_scan_summarizes_sector_structure_without_prediction(tmp_path):
    pytest.importorskip("pandas")
    first = tmp_path / "snapshot_1"
    second = tmp_path / "snapshot_2"
    metadata_csv = tmp_path / "node_metadata.csv"
    _write_snapshot(
        first,
        period_start="2020-01-01",
        period_end="2020-06-30",
        universe_rows=[
            ("SEC:A1", "A1"),
            ("SEC:A2", "A2"),
            ("SEC:B1", "B1"),
            ("SEC:B2", "B2"),
        ],
        returns_by_security={
            "SEC:A1": [0.10, 0.10],
            "SEC:A2": [0.20, 0.00],
            "SEC:B1": [-0.10, 0.00],
            "SEC:B2": [0.00, -0.10],
        },
        correlations={
            "SEC:A1": {"SEC:A1": 1.0, "SEC:A2": 0.90, "SEC:B1": 0.60, "SEC:B2": 0.20},
            "SEC:A2": {"SEC:A1": 0.90, "SEC:A2": 1.0, "SEC:B1": 0.55, "SEC:B2": 0.10},
            "SEC:B1": {"SEC:A1": 0.60, "SEC:A2": 0.55, "SEC:B1": 1.0, "SEC:B2": 0.70},
            "SEC:B2": {"SEC:A1": 0.20, "SEC:A2": 0.10, "SEC:B1": 0.70, "SEC:B2": 1.0},
        },
    )
    _write_snapshot(
        second,
        period_start="2020-02-01",
        period_end="2020-07-31",
        universe_rows=[
            ("SEC:A1", "A1"),
            ("SEC:A2", "A2"),
            ("SEC:B1", "B1"),
            ("SEC:B2", "B2"),
        ],
        returns_by_security={
            "SEC:A1": [0.00, 0.00],
            "SEC:A2": [0.00, 0.00],
            "SEC:B1": [0.10, 0.00],
            "SEC:B2": [0.10, 0.00],
        },
        correlations={
            "SEC:A1": {"SEC:A1": 1.0, "SEC:A2": 0.40, "SEC:B1": 0.65, "SEC:B2": 0.64},
            "SEC:A2": {"SEC:A1": 0.40, "SEC:A2": 1.0, "SEC:B1": 0.20, "SEC:B2": 0.10},
            "SEC:B1": {"SEC:A1": 0.65, "SEC:A2": 0.20, "SEC:B1": 1.0, "SEC:B2": 0.80},
            "SEC:B2": {"SEC:A1": 0.64, "SEC:A2": 0.10, "SEC:B1": 0.80, "SEC:B2": 1.0},
        },
    )
    _write_metadata(
        metadata_csv,
        [
            ("A1", "Growth"),
            ("A2", "Growth"),
            ("B1", "Value"),
            ("B2", "Value"),
        ],
    )

    outputs = write_rolling_structure_scan(
        [first, second],
        output_dir=tmp_path / "scan",
        node_metadata_path=metadata_csv,
        group_column="sector",
        top_percentile=0.25,
        absolute_correlation_threshold=0.5,
    )

    metadata = json.loads(outputs.metadata_path.read_text(encoding="utf-8"))
    assert metadata["relationship"] == "return_correlation_distance"
    assert metadata["mode"] == "descriptive_structure_only"
    assert metadata["top_percentile"] == 0.25
    assert "not investment advice" in metadata["disclaimer"]
    assert "structure-at-t to return-at-t+1" in metadata["brightline"]
    assert "source metadata gap" in metadata["missing_group_note"]

    sector_rows = _read_csv(outputs.group_summary_path)
    first_growth = _find(sector_rows, frame_index="0", group_name="Growth")
    first_value = _find(sector_rows, frame_index="0", group_name="Value")
    second_growth = _find(sector_rows, frame_index="1", group_name="Growth")
    assert first_growth["member_count"] == "2"
    assert float(first_growth["mean_period_return"]) == pytest.approx(0.205)
    assert float(first_growth["internal_mean_correlation"]) == pytest.approx(0.90)
    assert first_growth["internal_abs_threshold_edge_count"] == "1"
    assert first_growth["internal_top_percentile_edge_count"] == "1"
    assert float(first_value["internal_mean_correlation"]) == pytest.approx(0.70)
    assert float(second_growth["internal_mean_correlation"]) == pytest.approx(0.40)

    cross_rows = _read_csv(outputs.cross_group_summary_path)
    first_cross = _find(cross_rows, frame_index="0", group_a="Growth", group_b="Value")
    second_cross = _find(cross_rows, frame_index="1", group_a="Growth", group_b="Value")
    assert first_cross["abs_threshold_edge_count"] == "2"
    assert first_cross["top_percentile_edge_count"] == "0"
    assert second_cross["abs_threshold_edge_count"] == "2"
    assert second_cross["top_percentile_edge_count"] == "1"

    delta_rows = _read_csv(outputs.group_delta_path)
    growth_delta = _find(delta_rows, frame_index="1", group_name="Growth")
    value_delta = _find(delta_rows, frame_index="1", group_name="Value")
    assert float(growth_delta["delta_internal_mean_correlation"]) == pytest.approx(-0.50)
    assert float(value_delta["delta_internal_mean_correlation"]) == pytest.approx(0.10)

    cross_delta_rows = _read_csv(outputs.cross_group_delta_path)
    cross_delta = _find(cross_delta_rows, frame_index="1", group_a="Growth", group_b="Value")
    assert cross_delta["delta_top_percentile_edge_count"] == "1"

    markdown = outputs.markdown_path.read_text(encoding="utf-8")
    assert "descriptive only" in markdown
    assert "not investment advice" in markdown
    assert "source metadata gap" in markdown
    assert "Top group cohesion increases" in markdown


def test_rolling_structure_cli_writes_outputs(tmp_path):
    pytest.importorskip("pandas")
    snapshot = tmp_path / "snapshot"
    metadata_csv = tmp_path / "node_metadata.csv"
    _write_snapshot(
        snapshot,
        period_start="2020-01-01",
        period_end="2020-06-30",
        universe_rows=[("SEC:A1", "A1"), ("SEC:A2", "A2")],
        returns_by_security={"SEC:A1": [0.01], "SEC:A2": [0.02]},
        correlations={
            "SEC:A1": {"SEC:A1": 1.0, "SEC:A2": 0.8},
            "SEC:A2": {"SEC:A1": 0.8, "SEC:A2": 1.0},
        },
    )
    _write_metadata(metadata_csv, [("A1", "Growth"), ("A2", "Growth")])

    outputs = run(
        [
            "--snapshot",
            str(snapshot),
            "--node-metadata",
            str(metadata_csv),
            "--group-column",
            "sector",
            "--top-percentile",
            "0.25",
            "--absolute-correlation-threshold",
            "0.5",
            "--output-dir",
            str(tmp_path / "scan"),
        ]
    )

    assert outputs.metadata_path.exists()
    assert outputs.group_summary_path.exists()
    assert outputs.cross_group_summary_path.exists()
    assert outputs.markdown_path.exists()


def test_write_rolling_structure_scan_from_prices_writes_summary_only_rolling_windows(tmp_path):
    pd = pytest.importorskip("pandas")
    metadata_csv = tmp_path / "node_metadata.csv"
    _write_metadata(
        metadata_csv,
        [
            ("A1", "Growth"),
            ("A2", "Growth"),
            ("B1", "Value"),
            ("B2", "Value"),
        ],
    )
    prices = _price_frame(
        pd,
        {
            "SEC:A1": ("A1", [100, 101, 102, 104, 106, 109, 111, 114, 117, 119, 121, 123]),
            "SEC:A2": ("A2", [50, 50.5, 51, 52, 53, 54.5, 56, 58, 60, 61, 62, 63]),
            "SEC:B1": ("B1", [80, 79, 78, 78, 79, 80, 81, 82, 83, 84, 85, 86]),
            "SEC:B2": ("B2", [30, 29.5, 29, 29, 29.2, 29.5, 30, 30.4, 30.8, 31, 31.2, 31.4]),
        },
    )

    outputs = write_rolling_structure_scan_from_prices(
        prices=prices,
        output_dir=tmp_path / "rolling",
        node_metadata_path=metadata_csv,
        market="US",
        rolling_start="2020-01-01",
        rolling_end="2020-05-31",
        window_months=2,
        stride_months=1,
        price_column="adjusted_close",
        min_observations=2,
        group_column="sector",
        top_percentile=0.25,
        absolute_correlation_threshold=0.5,
    )

    metadata = json.loads(outputs.metadata_path.read_text(encoding="utf-8"))
    assert metadata["input_mode"] == "price_rolling_windows_summary_only"
    assert metadata["storage_note"].startswith("Rolling windows are computed in memory")
    assert metadata["window_months"] == 2
    assert metadata["stride_months"] == 1
    assert len(metadata["frames"]) == 4
    assert metadata["frames"][0]["period_start"] == "2020-01-01"
    assert metadata["frames"][0]["period_end"] == "2020-02-29"
    assert metadata["frames"][-1]["period_start"] == "2020-04-01"
    assert metadata["frames"][-1]["period_end"] == "2020-05-31"

    assert outputs.group_summary_path.exists()
    assert outputs.cross_group_summary_path.exists()
    assert not (tmp_path / "rolling" / "correlations.csv").exists()
    assert not (tmp_path / "rolling" / "distances.csv").exists()
    assert _find(_read_csv(outputs.group_summary_path), frame_index="0", group_name="Growth")


def test_rolling_structure_cli_import_does_not_require_pandas():
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
        import vector_relations.rolling_structure_cli
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


def _write_snapshot(path, *, period_start, period_end, universe_rows, returns_by_security, correlations):
    path.mkdir()
    (path / "metadata.json").write_text(
        json.dumps(
            {
                "period_start": period_start,
                "period_end": period_end,
                "artifact_files": {
                    "universe": "universe.csv",
                    "returns": "returns.csv",
                    "correlations": "correlations.csv",
                },
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    with (path / "universe.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["security_id", "symbol"])
        writer.writerows(universe_rows)
    securities = [security_id for security_id, _ in universe_rows]
    with (path / "returns.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["date", *securities])
        writer.writeheader()
        row_count = max(len(values) for values in returns_by_security.values())
        for index in range(row_count):
            row = {"date": f"2020-01-{index + 2:02d}"}
            for security_id in securities:
                values = returns_by_security.get(security_id, [])
                row[security_id] = values[index] if index < len(values) else ""
            writer.writerow(row)
    with (path / "correlations.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["security_id", *securities])
        writer.writeheader()
        for security_id in securities:
            writer.writerow({"security_id": security_id, **correlations[security_id]})


def _write_metadata(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["symbol", "sector"])
        writer.writerows(rows)


def _price_frame(pd, prices_by_security):
    rows = []
    dates = pd.date_range("2020-01-01", periods=12, freq="15D")
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
