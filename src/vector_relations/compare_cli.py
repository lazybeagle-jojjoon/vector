from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .compare import ComparisonOutputPaths, compare_snapshot_directories


def run(argv: Sequence[str] | None = None) -> ComparisonOutputPaths:
    args = _parse_args(argv)
    symbols = _split_csv_arg(args.symbols)
    return compare_snapshot_directories(
        [Path(snapshot) for snapshot in args.snapshot],
        output_dir=args.output_dir,
        symbols=symbols or None,
        top_k=args.top_k,
    )


def main(argv: Sequence[str] | None = None) -> int:
    try:
        outputs = run(argv)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Wrote summary: {outputs.summary_path}")
    print(f"Wrote neighbor changes: {outputs.neighbor_changes_path}")
    print(f"Wrote distance changes: {outputs.distance_changes_path}")
    print(f"Wrote insights: {outputs.insights_path}")
    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare saved ticker relation snapshots by top-k neighbor changes."
    )
    parser.add_argument(
        "--snapshot",
        action="append",
        required=True,
        help="Snapshot output directory. Provide at least two, in comparison order.",
    )
    parser.add_argument("--symbols", default="", help="Optional comma-separated target symbols.")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--output-dir", default="outputs/relation_snapshot_comparison")
    return parser.parse_args(argv)


def _split_csv_arg(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


if __name__ == "__main__":
    raise SystemExit(main())
