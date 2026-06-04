import os
import subprocess
import sys
from pathlib import Path


def test_snapshot_cli_help_does_not_import_dataframe_dependencies():
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")

    result = subprocess.run(
        [sys.executable, "-S", "-m", "vector_relations.cli", "--help"],
        capture_output=True,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Build a single-period ticker relation snapshot" in result.stdout
