import csv
import json
import os
import subprocess
import sys
import textwrap

from vector_relations.rolling_structure_report import write_rolling_structure_report
from vector_relations.rolling_structure_report_cli import run


def test_write_rolling_structure_report_renders_baseline_heatmaps(tmp_path):
    scan_dir = tmp_path / "scan"
    scan_dir.mkdir()
    _write_scan(scan_dir)

    output_path = write_rolling_structure_report(scan_dir, output_path=tmp_path / "report.html")

    html = output_path.read_text(encoding="utf-8")
    assert "Rolling Structure Heatmap Report" in html
    assert "Regime baseline" in html
    assert "market-wide correlation regime" in html
    assert "Internal cohesion vs baseline" in html
    assert "Period return vs baseline" in html
    assert "Cross-sector top-percentile links" in html
    assert "Market baseline" in html
    assert "source metadata gap bucket" in html
    assert "not a forecast" in html
    assert "not investment advice" in html
    assert "leads to" not in html


def test_rolling_structure_report_cli_writes_output(tmp_path):
    scan_dir = tmp_path / "scan"
    scan_dir.mkdir()
    _write_scan(scan_dir)

    output_path = run([str(scan_dir), "--output", str(tmp_path / "report.html")])

    assert output_path.exists()
    assert "Rolling Structure Heatmap Report" in output_path.read_text(encoding="utf-8")


def test_rolling_structure_report_cli_import_is_pandas_free():
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
        import vector_relations.rolling_structure_report_cli
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


def _write_scan(path):
    metadata = {
        "artifact_files": {
            "group_summary": "group_summary.csv",
            "cross_group_summary": "cross_group_summary.csv",
            "metadata": "rolling_structure_metadata.json",
        },
        "relationship": "return_correlation_distance",
        "mode": "descriptive_structure_only",
        "group_column": "sector",
        "top_percentile": 0.05,
        "absolute_correlation_threshold": 0.5,
        "frame_count": 2,
        "frames": [
            {
                "frame_index": 0,
                "frame_label": "2020-01-01 to 2020-06-30",
                "period_start": "2020-01-01",
                "period_end": "2020-06-30",
                "security_count": 4,
                "top_percentile_cutoff": 0.7,
            },
            {
                "frame_index": 1,
                "frame_label": "2020-02-01 to 2020-07-31",
                "period_start": "2020-02-01",
                "period_end": "2020-07-31",
                "security_count": 4,
                "top_percentile_cutoff": 0.6,
            },
        ],
        "missing_group_note": "The 'missing' group is a source metadata gap bucket, not a real sector.",
        "disclaimer": "Descriptive historical structure only; not investment advice, not a forecast.",
    }
    (path / "rolling_structure_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    _write_csv(
        path / "group_summary.csv",
        [
            "frame_index",
            "frame_label",
            "period_start",
            "period_end",
            "group_column",
            "group_name",
            "member_count",
            "return_observation_count",
            "mean_period_return",
            "internal_pair_count",
            "internal_mean_correlation",
            "internal_abs_threshold_edge_count",
            "internal_top_percentile_edge_count",
            "top_percentile_cutoff",
        ],
        [
            ["0", "2020-01-01 to 2020-06-30", "2020-01-01", "2020-06-30", "sector", "Growth", "2", "2", "0.10", "1", "0.80", "1", "1", "0.70"],
            ["0", "2020-01-01 to 2020-06-30", "2020-01-01", "2020-06-30", "sector", "Value", "2", "2", "-0.05", "1", "0.20", "0", "0", "0.70"],
            ["1", "2020-02-01 to 2020-07-31", "2020-02-01", "2020-07-31", "sector", "Growth", "2", "2", "0.02", "1", "0.40", "0", "0", "0.60"],
            ["1", "2020-02-01 to 2020-07-31", "2020-02-01", "2020-07-31", "sector", "Value", "2", "2", "0.08", "1", "0.60", "1", "1", "0.60"],
        ],
    )
    _write_csv(
        path / "cross_group_summary.csv",
        [
            "frame_index",
            "frame_label",
            "period_start",
            "period_end",
            "group_column",
            "group_a",
            "group_b",
            "pair_count",
            "mean_correlation",
            "abs_threshold_edge_count",
            "top_percentile_edge_count",
            "top_percentile_cutoff",
        ],
        [
            ["0", "2020-01-01 to 2020-06-30", "2020-01-01", "2020-06-30", "sector", "Growth", "Value", "4", "0.30", "1", "0", "0.70"],
            ["1", "2020-02-01 to 2020-07-31", "2020-02-01", "2020-07-31", "sector", "Growth", "Value", "4", "0.55", "3", "2", "0.60"],
        ],
    )


def _write_csv(path, fieldnames, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(fieldnames)
        writer.writerows(rows)
