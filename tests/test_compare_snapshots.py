import csv
import json
import os
import subprocess
import sys
import textwrap

import pytest

from vector_relations.compare import compare_snapshot_directories
from vector_relations.compare_cli import run


def test_compare_snapshot_directories_reports_neighbor_and_distance_changes(tmp_path):
    old_snapshot = tmp_path / "snapshot_2024"
    new_snapshot = tmp_path / "snapshot_2025"
    _write_snapshot(
        old_snapshot,
        period_start="2024-01-01",
        period_end="2024-12-31",
        rows=[
            ("SEC:AAA", "AAA", 1, "BBB", "SEC:BBB", 0.90, 0.10),
            ("SEC:AAA", "AAA", 2, "CCC", "SEC:CCC", 0.80, 0.20),
            ("SEC:ZZZ", "ZZZ", 1, "AAA", "SEC:AAA", 0.70, 0.30),
        ],
    )
    _write_snapshot(
        new_snapshot,
        period_start="2025-01-01",
        period_end="2025-12-31",
        rows=[
            ("SEC:AAA", "AAA", 1, "BBB", "SEC:BBB", 0.85, 0.15),
            ("SEC:AAA", "AAA", 2, "DDD", "SEC:DDD", 0.75, 0.25),
            ("SEC:ZZZ", "ZZZ", 1, "AAA", "SEC:AAA", 0.65, 0.35),
        ],
    )

    outputs = compare_snapshot_directories(
        [old_snapshot, new_snapshot],
        output_dir=tmp_path / "comparison",
        symbols=["AAA"],
        top_k=2,
    )

    neighbor_rows = _read_csv(outputs.neighbor_changes_path)
    assert neighbor_rows == [
        {
            "from_snapshot": "2024-01-01_to_2024-12-31",
            "to_snapshot": "2025-01-01_to_2025-12-31",
            "symbol": "AAA",
            "old_symbol_in_universe": "true",
            "new_symbol_in_universe": "true",
            "old_neighbor_count": "2",
            "new_neighbor_count": "2",
            "stayed_neighbors": "BBB",
            "entered_neighbors": "DDD",
            "exited_neighbors": "CCC",
            "jaccard_similarity": "0.3333333333333333",
        }
    ]

    distance_rows = _read_csv(outputs.distance_changes_path)
    assert distance_rows == [
        {
            "from_snapshot": "2024-01-01_to_2024-12-31",
            "to_snapshot": "2025-01-01_to_2025-12-31",
            "symbol": "AAA",
            "neighbor_symbol": "BBB",
            "old_neighbor_in_universe": "true",
            "new_neighbor_in_universe": "true",
            "old_rank": "1",
            "new_rank": "1",
            "old_distance": "0.1",
            "new_distance": "0.15",
            "distance_delta": "0.04999999999999999",
            "old_correlation": "0.9",
            "new_correlation": "0.85",
            "correlation_delta": "-0.050000000000000044",
            "status": "stayed",
        },
        {
            "from_snapshot": "2024-01-01_to_2024-12-31",
            "to_snapshot": "2025-01-01_to_2025-12-31",
            "symbol": "AAA",
            "neighbor_symbol": "CCC",
            "old_neighbor_in_universe": "true",
            "new_neighbor_in_universe": "false",
            "old_rank": "2",
            "new_rank": "",
            "old_distance": "0.2",
            "new_distance": "",
            "distance_delta": "",
            "old_correlation": "0.8",
            "new_correlation": "",
            "correlation_delta": "",
            "status": "exited",
        },
        {
            "from_snapshot": "2024-01-01_to_2024-12-31",
            "to_snapshot": "2025-01-01_to_2025-12-31",
            "symbol": "AAA",
            "neighbor_symbol": "DDD",
            "old_neighbor_in_universe": "false",
            "new_neighbor_in_universe": "true",
            "old_rank": "",
            "new_rank": "2",
            "old_distance": "",
            "new_distance": "0.25",
            "distance_delta": "",
            "old_correlation": "",
            "new_correlation": "0.75",
            "correlation_delta": "",
            "status": "entered",
        },
    ]

    summary = json.loads(outputs.summary_path.read_text(encoding="utf-8"))
    assert summary["snapshot_count"] == 2
    assert summary["symbols"] == ["AAA"]
    assert summary["top_k"] == 2
    assert summary["neighbor_change_rows"] == 1
    assert summary["distance_change_rows"] == 3
    assert summary["artifact_files"]["insights"] == "insights.md"
    insights = outputs.insights_path.read_text(encoding="utf-8")
    assert "Most Stable Neighbor Sets" in insights
    assert "AAA: jaccard 0.3333" in insights
    assert "Largest Stayed Distance Changes" in insights
    assert "AAA-BBB: farther by 0.0500" in insights
    assert "Top-k neighbor rows only" in insights
    assert "Entered/exited can reflect relationship changes, universe membership changes, or both" in insights
    assert "Residual source-data classification issues can remain" in insights
    assert "universe membership changes" in summary["universe_presence_note"]


def test_compare_cli_writes_outputs_for_requested_symbols(tmp_path):
    old_snapshot = tmp_path / "snapshot_2024"
    new_snapshot = tmp_path / "snapshot_2025"
    _write_snapshot(
        old_snapshot,
        period_start="2024-01-01",
        period_end="2024-12-31",
        rows=[("SEC:AAA", "AAA", 1, "BBB", "SEC:BBB", 0.90, 0.10)],
    )
    _write_snapshot(
        new_snapshot,
        period_start="2025-01-01",
        period_end="2025-12-31",
        rows=[("SEC:AAA", "AAA", 1, "CCC", "SEC:CCC", 0.80, 0.20)],
    )

    outputs = run(
        [
            "--snapshot",
            str(old_snapshot),
            "--snapshot",
            str(new_snapshot),
            "--symbols",
            "AAA",
            "--top-k",
            "1",
            "--output-dir",
            str(tmp_path / "comparison"),
        ]
    )

    assert outputs.summary_path.exists()
    assert outputs.neighbor_changes_path.exists()
    assert outputs.distance_changes_path.exists()
    assert outputs.insights_path.exists()


def test_compare_cli_import_does_not_require_pandas(tmp_path):
    code = textwrap.dedent(
        """
        import importlib.abc
        import sys

        class BlockPandasFinder(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname == "pandas" or fullname.startswith("pandas."):
                    raise ModuleNotFoundError("blocked pandas import")
                return None

        sys.meta_path.insert(0, BlockPandasFinder())
        import vector_relations.compare_cli
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


def test_compare_cli_main_reports_validation_errors_without_traceback(tmp_path):
    from vector_relations.compare_cli import main

    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "--snapshot",
                str(tmp_path / "only_snapshot"),
                "--output-dir",
                str(tmp_path / "comparison"),
            ]
        )

    assert str(excinfo.value) == "At least two snapshot directories are required."


def test_compare_marks_symbol_absence_without_treating_empty_neighbors_as_stable(tmp_path):
    old_snapshot = tmp_path / "snapshot_2024"
    new_snapshot = tmp_path / "snapshot_2025"
    _write_snapshot(
        old_snapshot,
        period_start="2024-01-01",
        period_end="2024-12-31",
        rows=[("SEC:AAA", "AAA", 1, "BBB", "SEC:BBB", 0.90, 0.10)],
        universe_rows=[("SEC:AAA", "AAA"), ("SEC:BBB", "BBB")],
    )
    _write_snapshot(
        new_snapshot,
        period_start="2025-01-01",
        period_end="2025-12-31",
        rows=[],
        universe_rows=[("SEC:BBB", "BBB")],
    )

    outputs = compare_snapshot_directories(
        [old_snapshot, new_snapshot],
        output_dir=tmp_path / "comparison",
        symbols=["AAA", "MISSING"],
        top_k=10,
    )

    rows = _read_csv(outputs.neighbor_changes_path)
    assert rows == [
        {
            "from_snapshot": "2024-01-01_to_2024-12-31",
            "to_snapshot": "2025-01-01_to_2025-12-31",
            "symbol": "AAA",
            "old_symbol_in_universe": "true",
            "new_symbol_in_universe": "false",
            "old_neighbor_count": "1",
            "new_neighbor_count": "0",
            "stayed_neighbors": "",
            "entered_neighbors": "",
            "exited_neighbors": "BBB",
            "jaccard_similarity": "0.0",
        },
        {
            "from_snapshot": "2024-01-01_to_2024-12-31",
            "to_snapshot": "2025-01-01_to_2025-12-31",
            "symbol": "MISSING",
            "old_symbol_in_universe": "false",
            "new_symbol_in_universe": "false",
            "old_neighbor_count": "0",
            "new_neighbor_count": "0",
            "stayed_neighbors": "",
            "entered_neighbors": "",
            "exited_neighbors": "",
            "jaccard_similarity": "",
        },
    ]

    distance_rows = _read_csv(outputs.distance_changes_path)
    assert distance_rows[0]["neighbor_symbol"] == "BBB"
    assert distance_rows[0]["old_neighbor_in_universe"] == "true"
    assert distance_rows[0]["new_neighbor_in_universe"] == "true"
    assert distance_rows[0]["status"] == "exited"

    insights = outputs.insights_path.read_text(encoding="utf-8")
    assert "Universe Cautions" in insights
    assert "AAA: target universe true -> false" in insights
    assert "MISSING: absent from both universes" in insights


def _write_snapshot(path, *, period_start, period_end, rows, universe_rows=None):
    path.mkdir()
    artifact_files = {"neighbors": "neighbors.csv", "universe": "universe.csv"}
    (path / "metadata.json").write_text(
        json.dumps(
            {
                "period_start": period_start,
                "period_end": period_end,
                "security_count": 4,
                "artifact_files": artifact_files,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
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
        writer.writerows(rows)
    if universe_rows is None:
        universe_rows = sorted(
            {(row[0], row[1]) for row in rows} | {(row[4], row[3]) for row in rows}
        )
    with (path / "universe.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["security_id", "symbol"])
        writer.writerows(universe_rows)


def _read_csv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
