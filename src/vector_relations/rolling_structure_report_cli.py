from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .rolling_structure_report import write_rolling_structure_report


def run(argv: Sequence[str] | None = None) -> Path:
    args = _parse_args(argv)
    return write_rolling_structure_report(
        args.scan_dir,
        output_path=args.output,
        max_cross_pairs=args.max_cross_pairs,
    )


def main(argv: Sequence[str] | None = None) -> int:
    try:
        output_path = run(argv)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Wrote rolling structure report: {output_path}")
    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a static descriptive heatmap report from rolling structure summaries."
    )
    parser.add_argument("scan_dir", help="Directory containing rolling_structure_metadata.json and summary CSVs.")
    parser.add_argument("--output", help="HTML output path. Defaults to scan_dir/rolling_structure_report.html.")
    parser.add_argument(
        "--max-cross-pairs",
        type=int,
        default=40,
        help="Maximum cross-sector pairs to render, selected mechanically by largest top-percentile edge count.",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
