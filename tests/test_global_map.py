import csv
import json
import os
import subprocess
import sys
import textwrap

import pytest

from vector_relations.global_map import write_global_map_view
from vector_relations.global_map_cli import run


def test_write_global_map_view_creates_deterministic_layout_edges_and_html(tmp_path):
    pytest.importorskip("numpy")
    snapshot = tmp_path / "snapshot_2025"
    metadata_csv = tmp_path / "node_metadata.csv"
    _write_snapshot(
        snapshot,
        period_start="2025-01-01",
        period_end="2025-12-31",
        universe_rows=[
            ("SEC:AAA", "AAA"),
            ("SEC:BBB", "BBB"),
            ("SEC:CCC", "CCC"),
        ],
        neighbor_rows=[
            ("SEC:AAA", "AAA", 1, "BBB", "SEC:BBB", 0.90, 0.10),
            ("SEC:AAA", "AAA", 2, "CCC", "SEC:CCC", 0.60, 0.40),
            ("SEC:BBB", "BBB", 1, "AAA", "SEC:AAA", 0.90, 0.10),
            ("SEC:CCC", "CCC", 1, "AAA", "SEC:AAA", 0.60, 0.40),
        ],
        return_rows=[
            ("2025-01-02", {"AAA": 0.01, "BBB": 0.02, "CCC": -0.01}),
            ("2025-01-03", {"AAA": 0.02, "BBB": 0.01, "CCC": -0.02}),
        ],
    )
    _write_metadata_csv(
        metadata_csv,
        [
            {
                "symbol": "AAA",
                "name": "Alpha Corp",
                "sector": "Technology",
                "industry": "Software",
                "avg_turnover": "12345",
            },
            {
                "symbol": "BBB",
                "name": "Beta Bank",
                "sector": "Financials",
                "industry": "Banks",
                "avg_turnover": "23456",
            },
        ],
    )

    first = write_global_map_view(
        snapshot,
        output_dir=tmp_path / "global_a",
        node_metadata_path=metadata_csv,
        top_k=2,
        seed=7,
        iterations=8,
    )
    second = write_global_map_view(
        snapshot,
        output_dir=tmp_path / "global_b",
        node_metadata_path=metadata_csv,
        top_k=2,
        seed=7,
        iterations=8,
    )

    assert first.html_path.exists()
    assert first.layout_path.exists()
    assert first.edges_path.exists()
    assert first.metadata_path.exists()

    metadata = json.loads(first.metadata_path.read_text(encoding="utf-8"))
    assert metadata["projection"] == "fixed_global_relationship_layout"
    assert metadata["relationship"] == "return_correlation_distance"
    assert metadata["layout_algorithm"] == "seeded_force_layout_v2"
    assert metadata["layout_seed"] == 7
    assert metadata["layout_iterations"] == 8
    assert metadata["top_k"] == 2
    assert metadata["layout_quality"]["radius_p90"] > 0
    assert metadata["layout_quality"]["occupied20x20_cells"] > 0
    assert "Node positions are a fixed reference frame" in metadata["position_note"]

    first_layout = first.layout_path.read_text(encoding="utf-8")
    second_layout = second.layout_path.read_text(encoding="utf-8")
    assert first_layout == second_layout
    layout_rows = _read_csv(first.layout_path)
    assert [row["symbol"] for row in layout_rows] == ["AAA", "BBB", "CCC"]
    assert layout_rows[0]["name"] == "Alpha Corp"
    assert layout_rows[0]["sector"] == "Technology"
    assert layout_rows[0]["industry"] == "Software"
    assert layout_rows[0]["period_return"].startswith("0.03")
    assert all(row["x"] and row["y"] for row in layout_rows)

    edge_rows = _read_csv(first.edges_path)
    assert len(edge_rows) == 4
    assert edge_rows[0]["source_symbol"] == "AAA"
    assert edge_rows[0]["target_symbol"] == "BBB"
    assert edge_rows[0]["rank"] == "1"
    assert edge_rows[0]["correlation"] == "0.9"
    assert edge_rows[0]["distance"] == "0.1"

    html = first.html_path.read_text(encoding="utf-8")
    assert "Global Relationship Map" in html
    assert "Node positions are a fixed reference frame" in html
    assert "Distance means return-correlation distance only" in html
    assert "Alpha Corp" in html
    assert "Technology" in html
    assert "const nodes =" in html
    assert "const edges =" in html


def test_global_map_cli_writes_outputs(tmp_path):
    pytest.importorskip("numpy")
    snapshot = tmp_path / "snapshot_2025"
    _write_snapshot(
        snapshot,
        period_start="2025-01-01",
        period_end="2025-12-31",
        universe_rows=[("SEC:AAA", "AAA"), ("SEC:BBB", "BBB")],
        neighbor_rows=[("SEC:AAA", "AAA", 1, "BBB", "SEC:BBB", 0.90, 0.10)],
        return_rows=[("2025-01-02", {"AAA": 0.01, "BBB": 0.02})],
    )

    outputs = run(
        [
            "--snapshot",
            str(snapshot),
            "--top-k",
            "1",
            "--seed",
            "11",
            "--iterations",
            "4",
            "--output-dir",
            str(tmp_path / "global"),
        ]
    )

    assert outputs.html_path.exists()
    assert outputs.layout_path.exists()
    assert outputs.edges_path.exists()
    assert outputs.metadata_path.exists()


def test_global_map_reads_period_returns_keyed_by_security_id(tmp_path):
    pytest.importorskip("numpy")
    snapshot = tmp_path / "snapshot_2025"
    _write_snapshot(
        snapshot,
        period_start="2025-01-01",
        period_end="2025-12-31",
        universe_rows=[("SEC:AAA", "AAA"), ("SEC:BBB", "BBB")],
        neighbor_rows=[("SEC:AAA", "AAA", 1, "BBB", "SEC:BBB", 0.90, 0.10)],
        return_rows=[
            ("2025-01-02", {"SEC:AAA": 0.01, "SEC:BBB": 0.02}),
            ("2025-01-03", {"SEC:AAA": 0.02, "SEC:BBB": 0.01}),
        ],
    )

    outputs = write_global_map_view(
        snapshot,
        output_dir=tmp_path / "global",
        top_k=1,
        seed=11,
        iterations=4,
    )

    rows = _read_csv(outputs.layout_path)
    row_by_symbol = {row["symbol"]: row for row in rows}
    assert row_by_symbol["AAA"]["period_return"].startswith("0.03")
    assert row_by_symbol["BBB"]["period_return"].startswith("0.03")


def test_global_map_market_cap_overlay_records_coverage_and_preserves_edges(tmp_path):
    pytest.importorskip("numpy")
    snapshot = tmp_path / "snapshot_2025"
    metadata_csv = tmp_path / "node_metadata.csv"
    _write_snapshot(
        snapshot,
        period_start="2025-01-01",
        period_end="2025-12-31",
        universe_rows=[
            ("SEC:AAA", "AAA"),
            ("SEC:BBB", "BBB"),
            ("SEC:CCC", "CCC"),
        ],
        neighbor_rows=[
            ("SEC:AAA", "AAA", 1, "BBB", "SEC:BBB", 0.90, 0.10),
            ("SEC:BBB", "BBB", 1, "AAA", "SEC:AAA", 0.90, 0.10),
        ],
        return_rows=[("2025-01-02", {"AAA": 0.01, "BBB": 0.02, "CCC": -0.01})],
    )
    _write_metadata_csv(
        metadata_csv,
        [
            {
                "symbol": "AAA",
                "market_cap": "1000000000",
                "market_cap_status": "positive",
                "market_cap_source": "raw_highlights_market_capitalization",
                "market_cap_currency": "USD",
                "market_cap_label": "raw/current/as-of-fetch",
            },
            {
                "symbol": "BBB",
                "market_cap": "",
                "market_cap_status": "zero",
                "market_cap_source": "raw_highlights_market_capitalization",
                "market_cap_currency": "USD",
                "market_cap_label": "raw/current/as-of-fetch",
            },
        ],
    )

    with_overlay = write_global_map_view(
        snapshot,
        output_dir=tmp_path / "global_with_overlay",
        node_metadata_path=metadata_csv,
        top_k=1,
        seed=11,
        iterations=4,
    )
    without_overlay = write_global_map_view(
        snapshot,
        output_dir=tmp_path / "global_without_overlay",
        top_k=1,
        seed=11,
        iterations=4,
    )

    metadata = json.loads(with_overlay.metadata_path.read_text(encoding="utf-8"))
    assert metadata["market_cap_overlay"]["label"] == "raw/current/as-of-fetch"
    assert metadata["market_cap_overlay"]["positive_count"] == 1
    assert metadata["market_cap_overlay"]["zero_count"] == 1
    assert metadata["market_cap_overlay"]["missing_count"] == 1
    assert metadata["market_cap_overlay"]["coverage_rate"] == pytest.approx(1 / 3)
    assert metadata["market_cap_overlay"]["size_scale"] == "log_current_market_cap"

    layout_rows = _read_csv(with_overlay.layout_path)
    row_by_symbol = {row["symbol"]: row for row in layout_rows}
    assert row_by_symbol["AAA"]["market_cap"] == "1000000000"
    assert row_by_symbol["AAA"]["market_cap_status"] == "positive"
    assert row_by_symbol["BBB"]["market_cap"] == ""
    assert row_by_symbol["BBB"]["market_cap_status"] == "zero"
    assert row_by_symbol["CCC"]["market_cap_status"] == "missing"

    assert _read_csv(with_overlay.edges_path) == _read_csv(without_overlay.edges_path)
    html = with_overlay.html_path.read_text(encoding="utf-8")
    assert "raw/current/as-of-fetch" in html
    assert "missing or zero market cap" in html
    assert "marketCapRadius" in html


def test_global_map_html_includes_filter_controls_without_changing_edges(tmp_path):
    pytest.importorskip("numpy")
    snapshot = tmp_path / "snapshot_2025"
    metadata_csv = tmp_path / "node_metadata.csv"
    _write_snapshot(
        snapshot,
        period_start="2025-01-01",
        period_end="2025-12-31",
        universe_rows=[
            ("SEC:AAA", "AAA"),
            ("SEC:BBB", "BBB"),
            ("SEC:CCC", "CCC"),
        ],
        neighbor_rows=[
            ("SEC:AAA", "AAA", 1, "BBB", "SEC:BBB", 0.90, 0.10),
            ("SEC:AAA", "AAA", 2, "CCC", "SEC:CCC", 0.40, 0.60),
            ("SEC:BBB", "BBB", 1, "AAA", "SEC:AAA", 0.90, 0.10),
        ],
        return_rows=[("2025-01-02", {"AAA": 0.01, "BBB": 0.02, "CCC": -0.01})],
    )
    _write_metadata_csv(
        metadata_csv,
        [
            {"symbol": "AAA", "sector": "Technology", "industry": "Software"},
            {"symbol": "BBB", "sector": "Financials", "industry": "Banks"},
            {"symbol": "CCC", "sector": "", "industry": ""},
        ],
    )

    with_controls = write_global_map_view(
        snapshot,
        output_dir=tmp_path / "global_with_controls",
        node_metadata_path=metadata_csv,
        top_k=2,
        seed=11,
        iterations=4,
    )
    without_metadata = write_global_map_view(
        snapshot,
        output_dir=tmp_path / "global_without_metadata",
        top_k=2,
        seed=11,
        iterations=4,
    )

    metadata = json.loads(with_controls.metadata_path.read_text(encoding="utf-8"))
    assert metadata["filter_controls"]["sector_count"] == 3
    assert metadata["filter_controls"]["industry_count"] == 3
    assert metadata["filter_controls"]["edge_threshold_control"] == "correlation_minimum"
    assert _read_csv(with_controls.edges_path) == _read_csv(without_metadata.edges_path)

    html = with_controls.html_path.read_text(encoding="utf-8")
    assert 'id="sectorFilter"' in html
    assert 'id="industryFilter"' in html
    assert 'id="edgeThreshold"' in html
    assert "passesNodeFilters" in html
    assert "passesEdgeThreshold" in html
    assert "Filter/focus controls" in html
    assert "filter only; not cluster labels" in html


def test_global_map_cli_import_does_not_require_numpy_or_pandas():
    code = textwrap.dedent(
        """
        import importlib.abc
        import sys

        class BlockDataframeFinder(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname in {"numpy", "pandas"} or fullname.startswith(("numpy.", "pandas.")):
                    raise ModuleNotFoundError(f"blocked import: {fullname}")
                return None

        sys.meta_path.insert(0, BlockDataframeFinder())
        import vector_relations.global_map_cli
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


def _write_snapshot(
    path,
    *,
    period_start,
    period_end,
    universe_rows,
    neighbor_rows,
    return_rows,
):
    path.mkdir()
    (path / "metadata.json").write_text(
        json.dumps(
            {
                "period_start": period_start,
                "period_end": period_end,
                "security_count": len(universe_rows),
                "relationship": "return_correlation_distance",
                "artifact_files": {
                    "universe": "universe.csv",
                    "neighbors": "neighbors.csv",
                    "returns": "returns.csv",
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
    with (path / "neighbors.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "security_id",
                "symbol",
                "rank",
                "neighbor_symbol",
                "neighbor_security_id",
                "correlation",
                "distance",
            ]
        )
        writer.writerows(neighbor_rows)
    symbols = sorted({symbol for _, values in return_rows for symbol in values})
    with (path / "returns.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["date", *symbols])
        writer.writeheader()
        for date, values in return_rows:
            writer.writerow({"date": date, **values})


def _write_metadata_csv(path, rows):
    fieldnames = [
        "symbol",
        "name",
        "sector",
        "industry",
        "avg_turnover",
        "market_cap",
        "market_cap_status",
        "market_cap_source",
        "market_cap_currency",
        "market_cap_label",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _read_csv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
