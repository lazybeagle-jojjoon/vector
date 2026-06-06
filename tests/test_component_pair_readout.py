import csv
import json
import os
import subprocess
import sys
import textwrap

from vector_relations.component_pair_readout import write_component_pair_readout
from vector_relations.component_pair_readout_cli import run


def test_component_pair_readout_keeps_persistent_guarded_same_window_pairs(tmp_path):
    pair_dir = _write_pair_summary(
        tmp_path,
        [
            _row(
                frame_index=0,
                frame_label="2025-01 to 2025-06",
                market_density="0.02",
                a="PIPE1 PIPE2 PIPE3 PIPE4 PIPE5",
                b="MLP1 MLP2 MLP3 MLP4 MLP5",
            ),
            _row(
                frame_index=1,
                frame_label="2025-02 to 2025-07",
                market_density="0.03",
                a="PIPE1 PIPE2 PIPE3 PIPE4 PIPE6",
                b="MLP1 MLP2 MLP3 MLP4 MLP6",
            ),
            _row(
                frame_index=2,
                frame_label="2025-03 to 2025-08",
                market_density="0.25",
                a="REGIME1 REGIME2 REGIME3 REGIME4 REGIME5",
                b="BETA1 BETA2 BETA3 BETA4 BETA5",
            ),
            _row(
                frame_index=3,
                frame_label="2025-04 to 2025-09",
                market_density="0.02",
                a="QUBT IONQ-WT RGTIW ARQQ QBTS",
                b="JOBY JOBY-WT ACHR ACHR-WT KOPN",
            ),
        ],
    )

    outputs = write_component_pair_readout(pair_dir=pair_dir, min_persistence_windows=2)

    metadata = json.loads(outputs.metadata_path.read_text(encoding="utf-8"))
    assert metadata["mode"] == "descriptive_component_pair_readout"
    assert "same-window" in metadata["interpretation_note"]
    assert "not a forecast" in metadata["disclaimer"]

    rows = _read_csv(outputs.summary_path)
    assert len(rows) == 1
    row = rows[0]
    assert row["window_count"] == "2"
    assert row["first_frame_label"] == "2025-01 to 2025-06"
    assert row["last_frame_label"] == "2025-02 to 2025-07"
    assert row["representative_component_a_top_symbols"] == "PIPE1 PIPE2 PIPE3 PIPE4 PIPE5"
    assert row["representative_component_b_top_symbols"] == "MLP1 MLP2 MLP3 MLP4 MLP5"
    assert row["contains_warrant_like_symbol"] == "false"
    assert float(row["avg_mean_cross_correlation"]) >= 0.55

    html = outputs.html_path.read_text(encoding="utf-8")
    assert "Component Pair Readout" in html
    assert "same-window co-movement" in html
    assert "No lead-lag" in html


def test_component_pair_readout_cli_writes_outputs(tmp_path):
    pair_dir = _write_pair_summary(
        tmp_path,
        [
            _row(frame_index=0, frame_label="A", a="A1 A2 A3 A4 A5", b="B1 B2 B3 B4 B5"),
            _row(frame_index=1, frame_label="B", a="A1 A2 A3 A4 A6", b="B1 B2 B3 B4 B6"),
        ],
    )

    outputs = run([str(pair_dir), "--min-persistence-windows", "2"])

    assert outputs.summary_path.exists()
    assert outputs.html_path.exists()


def test_component_pair_readout_cli_import_is_pandas_free():
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
        import vector_relations.component_pair_readout_cli
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


def _write_pair_summary(tmp_path, rows):
    path = tmp_path / "pairs"
    path.mkdir()
    metadata = {
        "artifact_files": {
            "metadata": "component_pair_summary_metadata.json",
            "pair_summary": "component_pair_summary.csv",
            "html": "component_pair_summary.html",
        },
        "mode": "descriptive_component_pair_summary",
        "relationship": "return_correlation",
    }
    (path / "component_pair_summary_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with (path / "component_pair_summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def _row(
    *,
    frame_index,
    frame_label,
    a,
    b,
    market_density="0.02",
    mean_corr="0.60",
    edge_density="0.80",
):
    return {
        "frame_index": str(frame_index),
        "window_frame_index": str(frame_index),
        "window_months": "6",
        "frame_label": frame_label,
        "period_start": "2025-01-01",
        "period_end": "2025-06-30",
        "component_threshold": "0.7",
        "cross_edge_threshold": "0.5",
        "market_pair_count": "1000",
        "market_cross_edge_count": "20",
        "market_cross_edge_density": market_density,
        "market_mean_correlation": "0.10",
        "component_a_id": "C01",
        "component_b_id": "C02",
        "component_a_size": "5",
        "component_b_size": "5",
        "component_a_density": "0.80",
        "component_b_density": "0.80",
        "component_a_mean_internal_correlation": "0.75",
        "component_b_mean_internal_correlation": "0.74",
        "component_a_mean_period_return": "0.10",
        "component_b_mean_period_return": "0.12",
        "cross_pair_count": "25",
        "mean_cross_correlation": mean_corr,
        "median_cross_correlation": mean_corr,
        "mean_cross_correlation_minus_market": "0.50",
        "cross_edge_count": "20",
        "cross_edge_density": edge_density,
        "normalized_cross_edge_density": "40",
        "component_a_top_symbols": a,
        "component_b_top_symbols": b,
    }


def _read_csv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
