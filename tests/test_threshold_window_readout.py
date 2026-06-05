import csv
import json
import os
import subprocess
import sys
import textwrap

from vector_relations.threshold_window_readout import write_window_flow_readout
from vector_relations.threshold_window_readout_cli import run


def test_window_flow_readout_classifies_durable_and_transient_rows(tmp_path):
    sweep_dir = _write_sweep_fixture(tmp_path / "sweep")

    outputs = write_window_flow_readout(
        sweep_dir=sweep_dir,
        min_member_count=5,
        min_pair_count=10,
        min_strong_edges=5,
        min_market_density=0.001,
        top_n=10,
    )

    metadata = json.loads(outputs.metadata_path.read_text(encoding="utf-8"))
    assert metadata["mode"] == "descriptive_window_flow_readout"
    assert metadata["durable_window_months"] == 12
    assert metadata["transient_window_months"] == 6
    assert "not a forecast" in metadata["disclaimer"]
    assert "not independent confirmations" in metadata["interpretation_note"]

    rows = _read_csv(outputs.summary_path)
    durable = _find(rows, classification="durable", scope="internal", label="Utilities")
    assert durable["window_months"] == "12"
    assert durable["strong_edge_count"] == "20"

    transient = _find(rows, classification="transient", scope="internal", label="Energy")
    assert transient["window_months"] == "6"
    assert transient["strong_edge_count"] == "18"

    assert not [row for row in rows if row["label"] == "Tiny"]
    assert not [row for row in rows if row["label"] == "Noisy"]
    assert not [row for row in rows if row["label"] == "missing"]

    markdown = outputs.markdown_path.read_text(encoding="utf-8")
    assert "Durable internal" in markdown
    assert "Durable cross" in markdown
    assert "Transient internal" in markdown
    assert "Transient cross" in markdown
    assert "not investment advice" in markdown
    assert "6-month and 12-month windows are overlapping lenses" in markdown


def test_window_flow_readout_cli_writes_outputs(tmp_path):
    sweep_dir = _write_sweep_fixture(tmp_path / "sweep")

    outputs = run([str(sweep_dir), "--top-n", "5"])

    assert outputs.summary_path.exists()
    assert outputs.markdown_path.exists()


def test_window_flow_readout_cli_import_is_pandas_free():
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
        import vector_relations.threshold_window_readout_cli
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


def _write_sweep_fixture(path):
    path.mkdir()
    metadata = {
        "artifact_files": {
            "group_summary": "threshold_group_summary.csv",
            "cross_group_summary": "threshold_cross_group_summary.csv",
        },
        "window_months_values": [6, 12],
    }
    (path / "threshold_sweep_metadata.json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    _write_csv(
        path / "threshold_group_summary.csv",
        [
            "window_months",
            "window_frame_index",
            "frame_label",
            "threshold",
            "group_name",
            "member_count",
            "internal_pair_count",
            "internal_strong_edge_count",
            "internal_strong_edge_ratio_normalized",
            "market_strong_edge_ratio",
        ],
        [
            ["12", "0", "2020 to 2021", "0.6", "Utilities", "8", "28", "20", "9.5", "0.02"],
            ["6", "1", "2021 H1", "0.6", "Utilities", "8", "28", "16", "8.0", "0.03"],
            ["6", "2", "2021 H2", "0.6", "Energy", "7", "21", "18", "7.5", "0.02"],
            ["12", "0", "2020 to 2021", "0.7", "missing", "8", "28", "20", "99", "0.02"],
            ["12", "1", "2021 to 2022", "0.6", "Tiny", "4", "6", "6", "99", "0.02"],
            ["6", "3", "2022 H1", "0.7", "Noisy", "8", "28", "4", "50", "0.0005"],
        ],
    )
    _write_csv(
        path / "threshold_cross_group_summary.csv",
        [
            "window_months",
            "window_frame_index",
            "frame_label",
            "threshold",
            "group_a",
            "group_b",
            "cross_pair_count",
            "cross_strong_edge_count",
            "cross_strong_edge_ratio_normalized",
            "market_strong_edge_ratio",
        ],
        [
            ["12", "0", "2020 to 2021", "0.5", "Financials", "Real Estate", "100", "30", "6.0", "0.03"],
            ["6", "2", "2021 H2", "0.5", "Energy", "Materials", "80", "20", "7.0", "0.02"],
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
