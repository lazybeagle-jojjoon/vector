import csv
import json
import os
import subprocess
import sys
import textwrap

from vector_relations.component_dashboard import write_component_dashboard
from vector_relations.component_dashboard_cli import run


def test_component_dashboard_joins_detail_flow_and_regime_context(tmp_path):
    component_dir = _write_component_fixture(tmp_path / "components")

    outputs = write_component_dashboard(component_dir=component_dir, threshold="0.7", min_size=2, top_n=10)

    metadata = json.loads(outputs.metadata_path.read_text(encoding="utf-8"))
    assert metadata["mode"] == "descriptive_component_dashboard"
    assert metadata["threshold"] == "0.7"
    assert metadata["min_size"] == 2
    assert "not a forecast" in metadata["disclaimer"]
    assert "future returns" in metadata["interpretation_note"]

    rows = _read_csv(outputs.dashboard_path)
    a = _find(rows, frame_label="2020 H1", component_id="C01")
    assert a["size"] == "4"
    assert a["component_density"] == "0.8"
    assert a["mean_period_return"] == "0.12"
    assert a["market_strong_edge_ratio"] == "0.02"
    assert a["giant_component_share"] == "0.4"
    assert a["forward_event_type"] == "continued"
    assert a["forward_overlap_span"] == "2"
    assert a["forward_jaccard"] == "0.75"
    assert a["forward_overlap_count"] == "3"
    assert a["forward_to_frame_label"] == "2020 H2"
    assert a["forward_target_component_id"] == "C02"

    b = _find(rows, frame_label="2020 H1", component_id="C02")
    assert b["forward_event_type"] == "merged"
    assert b["forward_target_component_id"] == "C02"
    assert b["forward_target_match_count"] == "2"

    html = outputs.html_path.read_text(encoding="utf-8")
    assert "Component Dashboard" in html
    assert "Descriptive historical structure only" in html
    assert "No future-return alignment" in html
    assert "AEM RGLD CDE" in html


def test_component_dashboard_cli_writes_outputs(tmp_path):
    component_dir = _write_component_fixture(tmp_path / "components")

    outputs = run([str(component_dir), "--threshold", "0.7", "--min-size", "2", "--top-n", "5"])

    assert outputs.dashboard_path.exists()
    assert outputs.html_path.exists()


def test_component_dashboard_cli_import_is_pandas_free():
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
        import vector_relations.component_dashboard_cli
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


def _write_component_fixture(path):
    path.mkdir()
    metadata = {
        "artifact_files": {
            "metadata": "component_structure_metadata.json",
            "frame_summary": "component_frame_summary.csv",
            "component_detail": "component_detail.csv",
            "component_flow": "component_flow_summary.csv",
            "markdown": "component_structure_summary.md",
        },
        "mode": "descriptive_connected_components",
        "relationship": "return_correlation",
    }
    (path / "component_structure_metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    _write_csv(
        path / "component_frame_summary.csv",
        [
            "frame_index",
            "window_frame_index",
            "window_months",
            "frame_label",
            "period_start",
            "period_end",
            "threshold",
            "security_count",
            "component_count",
            "non_singleton_component_count",
            "singleton_count",
            "giant_component_size",
            "giant_component_share",
            "market_pair_count",
            "market_strong_edge_count",
            "market_strong_edge_ratio",
        ],
        [
            ["0", "0", "6", "2020 H1", "2020-01-01", "2020-06-30", "0.7", "10", "3", "2", "1", "4", "0.4", "45", "1", "0.02"],
            ["1", "1", "6", "2020 H2", "2020-07-01", "2020-12-31", "0.7", "11", "4", "3", "1", "5", "0.45", "55", "2", "0.04"],
            ["0", "0", "6", "2020 H1", "2020-01-01", "2020-06-30", "0.6", "10", "2", "1", "1", "7", "0.7", "45", "4", "0.08"],
        ],
    )
    _write_csv(
        path / "component_detail.csv",
        [
            "frame_index",
            "window_frame_index",
            "window_months",
            "frame_label",
            "period_start",
            "period_end",
            "threshold",
            "component_id",
            "size",
            "edge_count",
            "possible_edge_count",
            "component_density",
            "mean_internal_correlation",
            "mean_period_return",
            "top_symbols",
        ],
        [
            ["0", "0", "6", "2020 H1", "2020-01-01", "2020-06-30", "0.7", "C01", "4", "5", "6", "0.8", "0.76", "0.12", "AEM RGLD CDE"],
            ["0", "0", "6", "2020 H1", "2020-01-01", "2020-06-30", "0.7", "C02", "3", "3", "3", "1", "0.81", "-0.05", "YPF BBAR TGS"],
            ["1", "1", "6", "2020 H2", "2020-07-01", "2020-12-31", "0.7", "C02", "5", "8", "10", "0.8", "0.78", "0.2", "AEM RGLD CDE HL"],
            ["0", "0", "6", "2020 H1", "2020-01-01", "2020-06-30", "0.6", "C01", "7", "10", "21", "0.48", "0.61", "0.03", "AEM RGLD CDE YPF"],
        ],
    )
    _write_csv(
        path / "component_flow_summary.csv",
        [
            "window_months",
            "threshold",
            "from_frame_index",
            "to_frame_index",
            "from_frame_label",
            "to_frame_label",
            "event_type",
            "source_component_id",
            "target_component_id",
            "source_size",
            "target_size",
            "overlap_count",
            "jaccard",
            "source_retention_ratio",
            "target_capture_ratio",
            "source_match_count",
            "target_match_count",
            "source_component_density",
            "target_component_density",
            "source_top_symbols",
            "target_top_symbols",
        ],
        [
            ["6", "0.7", "0", "1", "2020 H1", "2020 H2", "continued", "C01", "C02", "4", "5", "3", "0.75", "0.75", "0.6", "1", "2", "0.8", "0.8", "AEM RGLD CDE", "AEM RGLD CDE HL"],
            ["6", "0.7", "0", "1", "2020 H1", "2020 H2", "merged", "C02", "C02", "3", "5", "2", "0.4", "0.667", "0.4", "1", "2", "1", "0.8", "YPF BBAR TGS", "AEM RGLD CDE HL"],
        ],
    )
    return path


def _write_csv(path, fields, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(fields)
        writer.writerows(rows)


def _read_csv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _find(rows, **matches):
    for row in rows:
        if all(row.get(key) == value for key, value in matches.items()):
            return row
    raise AssertionError(f"row not found: {matches}")
