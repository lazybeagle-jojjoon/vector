import csv
import json
import os
import subprocess
import sys
import textwrap

from vector_relations.compare import compare_snapshot_directories
from vector_relations.ego import write_ego_network_view
from vector_relations.ego_cli import run


def test_write_ego_network_view_renders_generic_symbol_status_and_returns(tmp_path):
    old_snapshot = tmp_path / "snapshot_2024"
    new_snapshot = tmp_path / "snapshot_2025"
    _write_snapshot(
        old_snapshot,
        period_start="2024-01-01",
        period_end="2024-12-31",
        neighbor_rows=[
            ("SEC:AAA", "AAA", 1, "BBB", "SEC:BBB", 0.90, 0.10),
            ("SEC:AAA", "AAA", 2, "CCC", "SEC:CCC", 0.80, 0.20),
        ],
        return_rows=[
            ("2024-01-02", {"AAA": 0.01, "BBB": 0.02, "CCC": -0.01}),
            ("2024-01-03", {"AAA": 0.02, "BBB": 0.01, "CCC": -0.02}),
        ],
    )
    _write_snapshot(
        new_snapshot,
        period_start="2025-01-01",
        period_end="2025-12-31",
        neighbor_rows=[
            ("SEC:AAA", "AAA", 1, "BBB", "SEC:BBB", 0.85, 0.15),
            ("SEC:AAA", "AAA", 2, "DDD", "SEC:DDD", 0.75, 0.25),
        ],
        return_rows=[
            ("2025-01-02", {"AAA": -0.01, "BBB": 0.03, "DDD": 0.04}),
            ("2025-01-03", {"AAA": 0.01, "BBB": 0.02, "DDD": 0.03}),
        ],
    )
    comparison = compare_snapshot_directories(
        [old_snapshot, new_snapshot],
        output_dir=tmp_path / "comparison",
        symbols=["AAA"],
        top_k=2,
    )

    outputs = write_ego_network_view(
        [old_snapshot, new_snapshot],
        symbol="AAA",
        output_dir=tmp_path / "ego",
        comparison_dir=comparison.summary_path.parent,
        top_k=2,
    )

    html = outputs.html_path.read_text(encoding="utf-8")
    assert "AAA Ego Network" in html
    assert "2024-01-01_to_2024-12-31" in html
    assert "2025-01-01_to_2025-12-31" in html
    assert "status-stayed" in html
    assert "status-entered" in html
    assert "status-exited" in html
    assert "BBB" in html
    assert "CCC" in html
    assert "DDD" in html
    assert "period return" in html
    assert "HUT" not in html


def test_ego_cli_writes_html_for_requested_symbol(tmp_path):
    snapshot = tmp_path / "snapshot_2025"
    _write_snapshot(
        snapshot,
        period_start="2025-01-01",
        period_end="2025-12-31",
        neighbor_rows=[("SEC:AAA", "AAA", 1, "BBB", "SEC:BBB", 0.85, 0.15)],
        return_rows=[("2025-01-02", {"AAA": 0.01, "BBB": 0.02})],
    )

    outputs = run(
        [
            "--snapshot",
            str(snapshot),
            "--symbol",
            "AAA",
            "--top-k",
            "1",
            "--output-dir",
            str(tmp_path / "ego"),
        ]
    )

    assert outputs.html_path.exists()
    assert "AAA Ego Network" in outputs.html_path.read_text(encoding="utf-8")


def test_ego_cli_import_does_not_require_dataframe_dependencies(tmp_path):
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
        import vector_relations.ego_cli
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


def test_ego_network_surfaces_current_edges_when_comparison_top_k_is_smaller(tmp_path):
    old_snapshot = tmp_path / "snapshot_2024"
    new_snapshot = tmp_path / "snapshot_2025"
    _write_snapshot(
        old_snapshot,
        period_start="2024-01-01",
        period_end="2024-12-31",
        neighbor_rows=[
            ("SEC:AAA", "AAA", 1, "BBB", "SEC:BBB", 0.90, 0.10),
            ("SEC:AAA", "AAA", 2, "CCC", "SEC:CCC", 0.80, 0.20),
        ],
        return_rows=[("2024-01-02", {"AAA": 0.01, "BBB": 0.02, "CCC": 0.03})],
    )
    _write_snapshot(
        new_snapshot,
        period_start="2025-01-01",
        period_end="2025-12-31",
        neighbor_rows=[
            ("SEC:AAA", "AAA", 1, "BBB", "SEC:BBB", 0.85, 0.15),
            ("SEC:AAA", "AAA", 2, "CCC", "SEC:CCC", 0.75, 0.25),
            ("SEC:AAA", "AAA", 3, "DDD", "SEC:DDD", 0.65, 0.35),
        ],
        return_rows=[("2025-01-02", {"AAA": 0.01, "BBB": 0.02, "CCC": 0.03, "DDD": 0.04})],
    )
    comparison = compare_snapshot_directories(
        [old_snapshot, new_snapshot],
        output_dir=tmp_path / "comparison",
        symbols=["AAA"],
        top_k=1,
    )

    outputs = write_ego_network_view(
        [old_snapshot, new_snapshot],
        symbol="AAA",
        output_dir=tmp_path / "ego",
        comparison_dir=comparison.summary_path.parent,
        top_k=3,
    )

    html = outputs.html_path.read_text(encoding="utf-8")
    assert "status-current" in html
    assert "current = present in this panel but not classified by the comparison file" in html
    assert "Use the same top-k for ego and comparison outputs when possible." in html


def test_ego_network_renders_missing_returns_as_missing_overlay(tmp_path):
    snapshot = tmp_path / "snapshot_2025"
    _write_snapshot(
        snapshot,
        period_start="2025-01-01",
        period_end="2025-12-31",
        neighbor_rows=[("SEC:AAA", "AAA", 1, "BBB", "SEC:BBB", 0.85, 0.15)],
        return_rows=None,
    )

    outputs = write_ego_network_view(
        [snapshot],
        symbol="AAA",
        output_dir=tmp_path / "ego",
        top_k=1,
    )

    html = outputs.html_path.read_text(encoding="utf-8")
    assert "period return: missing" in html


def test_ego_network_labels_periods_with_no_top_k_neighbors(tmp_path):
    old_snapshot = tmp_path / "snapshot_2024"
    new_snapshot = tmp_path / "snapshot_2025"
    _write_snapshot(
        old_snapshot,
        period_start="2024-01-01",
        period_end="2024-12-31",
        neighbor_rows=[],
        return_rows=[("2024-01-02", {"AAA": 0.01})],
        universe_rows=[("SEC:AAA", "AAA")],
    )
    _write_snapshot(
        new_snapshot,
        period_start="2025-01-01",
        period_end="2025-12-31",
        neighbor_rows=[("SEC:AAA", "AAA", 1, "BBB", "SEC:BBB", 0.85, 0.15)],
        return_rows=[("2025-01-02", {"AAA": 0.01, "BBB": 0.02})],
    )

    outputs = write_ego_network_view(
        [old_snapshot, new_snapshot],
        symbol="AAA",
        output_dir=tmp_path / "ego",
        top_k=1,
    )

    html = outputs.html_path.read_text(encoding="utf-8")
    assert "No top-k neighbors for AAA in this snapshot." in html


def _write_snapshot(
    path,
    *,
    period_start,
    period_end,
    neighbor_rows,
    return_rows,
    universe_rows=None,
):
    path.mkdir()
    if universe_rows is None:
        universe_rows = sorted(
            {
                (row[0], row[1])
                for row in neighbor_rows
            }
            | {
                (row[4], row[3])
                for row in neighbor_rows
            }
        )
    (path / "metadata.json").write_text(
        json.dumps(
            {
                "period_start": period_start,
                "period_end": period_end,
                "security_count": len(universe_rows),
                "artifact_files": {
                    "neighbors": "neighbors.csv",
                    "returns": "returns.csv",
                    "universe": "universe.csv",
                },
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
        writer.writerows(neighbor_rows)
    with (path / "universe.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["security_id", "symbol"])
        writer.writerows(universe_rows)
    if return_rows is not None:
        symbols = sorted({symbol for _, values in return_rows for symbol in values})
        with (path / "returns.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=["date", *symbols])
            writer.writeheader()
            for date, values in return_rows:
                writer.writerow({"date": date, **values})
