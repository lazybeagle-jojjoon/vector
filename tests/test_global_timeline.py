import csv
import json
import os
import subprocess
import sys
import textwrap

from vector_relations.global_timeline import write_global_timeline_view
from vector_relations.global_timeline_cli import run


def test_write_global_timeline_view_reuses_reference_layout_and_marks_missing_nodes(tmp_path):
    reference_map = tmp_path / "reference_map"
    reference_map.mkdir()
    _write_reference_map(
        reference_map,
        [
            {
                "security_id": "SEC:AAA",
                "symbol": "AAA",
                "x": "-0.50000000",
                "y": "0.25000000",
                "period_return": "0.1",
                "name": "Alpha Corp",
                "sector": "Technology",
                "industry": "Software",
                "market_cap": "1000000000",
                "market_cap_status": "positive",
                "market_cap_currency": "USD",
                "market_cap_label": "raw/current/as-of-fetch",
            },
            {
                "security_id": "SEC:BBB",
                "symbol": "BBB",
                "x": "0.10000000",
                "y": "-0.15000000",
                "period_return": "-0.2",
                "name": "Beta Bank",
                "sector": "Financials",
                "industry": "Banks",
                "market_cap": "",
                "market_cap_status": "missing",
                "market_cap_currency": "USD",
                "market_cap_label": "raw/current/as-of-fetch",
            },
            {
                "security_id": "SEC:CCC",
                "symbol": "CCC",
                "x": "0.75000000",
                "y": "0.50000000",
                "period_return": "",
                "name": "Gamma Energy",
                "sector": "Energy",
                "industry": "Oil & Gas",
                "market_cap": "500000000",
                "market_cap_status": "positive",
                "market_cap_currency": "USD",
                "market_cap_label": "raw/current/as-of-fetch",
            },
        ],
    )
    snapshot_early = tmp_path / "snapshot_2020"
    snapshot_late = tmp_path / "snapshot_2024"
    _write_snapshot(
        snapshot_early,
        period_start="2020-01-01",
        period_end="2020-12-31",
        universe_rows=[("SEC:AAA", "AAA"), ("SEC:BBB", "BBB")],
        neighbor_rows=[
            ("SEC:AAA", "AAA", 1, "BBB", "SEC:BBB", 0.80, 0.20),
            ("SEC:BBB", "BBB", 1, "AAA", "SEC:AAA", 0.80, 0.20),
        ],
        return_rows=[
            ("2020-01-02", {"AAA": 0.01, "BBB": -0.01}),
            ("2020-01-03", {"AAA": 0.02, "BBB": -0.02}),
        ],
    )
    _write_snapshot(
        snapshot_late,
        period_start="2024-01-01",
        period_end="2024-12-31",
        universe_rows=[("SEC:AAA", "AAA"), ("SEC:CCC", "CCC")],
        neighbor_rows=[
            ("SEC:AAA", "AAA", 1, "CCC", "SEC:CCC", 0.70, 0.30),
            ("SEC:CCC", "CCC", 1, "AAA", "SEC:AAA", 0.70, 0.30),
            ("SEC:BBB", "BBB", 1, "AAA", "SEC:AAA", 0.90, 0.10),
        ],
        return_rows=[
            ("2024-01-02", {"AAA": -0.02, "CCC": 0.03}),
            ("2024-01-03", {"AAA": -0.01, "CCC": 0.04}),
        ],
    )

    outputs = write_global_timeline_view(
        reference_map,
        [snapshot_early, snapshot_late],
        output_dir=tmp_path / "timeline",
        top_k=1,
    )

    metadata = json.loads(outputs.metadata_path.read_text(encoding="utf-8"))
    assert metadata["projection"] == "fixed_global_timeline_small_multiples"
    assert metadata["reference_layout"] == str(reference_map / "global_layout.csv")
    assert metadata["reference_period_label"] == "2024-01-01 to 2026-05-22"
    assert metadata["node_set"] == "reference_layout"
    assert metadata["frame_count"] == 2
    assert metadata["frames"][0]["present_node_count"] == 2
    assert metadata["frames"][0]["missing_node_count"] == 1
    assert metadata["frames"][1]["present_node_count"] == 2
    assert metadata["frames"][1]["missing_node_count"] == 1
    assert "do not mean time movement" in metadata["position_note"]

    nodes = _read_csv(outputs.nodes_path)
    assert [row["symbol"] for row in nodes] == ["AAA", "BBB", "CCC"]
    assert nodes[0]["x"] == "-0.50000000"
    assert nodes[1]["y"] == "-0.15000000"

    edges = _read_csv(outputs.edges_path)
    assert [(row["frame_label"], row["source_symbol"], row["target_symbol"]) for row in edges] == [
        ("2020-01-01 to 2020-12-31", "AAA", "BBB"),
        ("2020-01-01 to 2020-12-31", "BBB", "AAA"),
        ("2024-01-01 to 2024-12-31", "AAA", "CCC"),
        ("2024-01-01 to 2024-12-31", "CCC", "AAA"),
    ]

    frame_data = json.loads(outputs.frames_path.read_text(encoding="utf-8"))
    assert frame_data["frames"][0]["returns"]["AAA"] > 0
    assert "CCC" not in frame_data["frames"][0]["returns"]
    assert "BBB" not in frame_data["frames"][1]["present_symbols"]

    html = outputs.html_path.read_text(encoding="utf-8")
    assert "Global Relationship Timeline" in html
    assert "same fixed reference layout" in html
    assert "Reference frame: 2024-01-01 to 2026-05-22" in html
    assert "missing in this frame" in html
    assert "const timelineData =" in html


def test_global_timeline_cli_writes_outputs(tmp_path):
    reference_map = tmp_path / "reference_map"
    reference_map.mkdir()
    _write_reference_map(
        reference_map,
        [{"security_id": "SEC:AAA", "symbol": "AAA", "x": "0", "y": "0"}],
    )
    snapshot = tmp_path / "snapshot"
    _write_snapshot(
        snapshot,
        period_start="2025-01-01",
        period_end="2025-12-31",
        universe_rows=[("SEC:AAA", "AAA")],
        neighbor_rows=[],
        return_rows=[("2025-01-02", {"AAA": 0.01})],
    )

    outputs = run(
        [
            "--reference-map",
            str(reference_map),
            "--snapshot",
            str(snapshot),
            "--top-k",
            "1",
            "--output-dir",
            str(tmp_path / "timeline"),
        ]
    )

    assert outputs.metadata_path.exists()
    assert outputs.nodes_path.exists()
    assert outputs.edges_path.exists()
    assert outputs.frames_path.exists()
    assert outputs.html_path.exists()


def test_global_timeline_cli_import_does_not_require_numpy_or_pandas():
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
        import vector_relations.global_timeline_cli
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


def _write_reference_map(path, rows):
    fieldnames = [
        "security_id",
        "symbol",
        "x",
        "y",
        "period_return",
        "name",
        "type",
        "sector",
        "industry",
        "primary_sector",
        "volatility",
        "avg_volume",
        "avg_turnover",
        "market_cap",
        "market_cap_status",
        "market_cap_source",
        "market_cap_currency",
        "market_cap_label",
        "market_cap_change",
        "community_id",
    ]
    with (path / "global_layout.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    (path / "global_map_metadata.json").write_text(
        json.dumps(
            {
                "artifact_files": {
                    "layout": "global_layout.csv",
                    "edges": "global_edges.csv",
                    "html": "global_map.html",
                },
                "period_start": "2024-01-01",
                "period_end": "2026-05-22",
                "projection": "fixed_global_relationship_layout",
                "relationship": "return_correlation_distance",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


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


def _read_csv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
