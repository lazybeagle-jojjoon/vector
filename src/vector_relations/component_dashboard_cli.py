from __future__ import annotations

import argparse
from typing import Sequence

from .component_dashboard import ComponentDashboardPaths, write_component_dashboard


def run(argv: Sequence[str] | None = None) -> ComponentDashboardPaths:
    args = _parse_args(argv)
    return write_component_dashboard(
        component_dir=args.component_dir,
        output_dir=args.output_dir,
        threshold=args.threshold,
        min_size=args.min_size,
        top_n=args.top_n,
    )


def main(argv: Sequence[str] | None = None) -> int:
    outputs = run(argv)
    print(f"Wrote component dashboard metadata: {outputs.metadata_path}")
    print(f"Wrote component dashboard CSV: {outputs.dashboard_path}")
    print(f"Wrote component dashboard HTML: {outputs.html_path}")
    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a descriptive component dashboard from component structure summaries."
    )
    parser.add_argument("component_dir", help="Directory containing component structure summary CSVs.")
    parser.add_argument("--output-dir", help="Optional output directory. Defaults to component_dir.")
    parser.add_argument("--threshold", default="0.7")
    parser.add_argument("--min-size", type=int, default=5)
    parser.add_argument("--top-n", type=int, default=200)
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
