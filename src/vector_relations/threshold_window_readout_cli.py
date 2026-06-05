from __future__ import annotations

import argparse
from typing import Sequence

from .threshold_window_readout import WindowFlowReadoutPaths, write_window_flow_readout


def run(argv: Sequence[str] | None = None) -> WindowFlowReadoutPaths:
    args = _parse_args(argv)
    return write_window_flow_readout(
        sweep_dir=args.sweep_dir,
        output_dir=args.output_dir,
        durable_window_months=args.durable_window_months,
        transient_window_months=args.transient_window_months,
        min_member_count=args.min_member_count,
        min_pair_count=args.min_pair_count,
        min_strong_edges=args.min_strong_edges,
        min_market_density=args.min_market_density,
        top_n=args.top_n,
    )


def main(argv: Sequence[str] | None = None) -> int:
    outputs = run(argv)
    print(f"Wrote window flow readout metadata: {outputs.metadata_path}")
    print(f"Wrote window flow summary: {outputs.summary_path}")
    print(f"Wrote window flow markdown: {outputs.markdown_path}")
    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a descriptive durable/transient readout from threshold window sweep CSVs."
    )
    parser.add_argument("sweep_dir", help="Directory containing threshold_sweep_metadata.json and summary CSVs.")
    parser.add_argument("--output-dir", help="Optional output directory. Defaults to sweep_dir.")
    parser.add_argument("--durable-window-months", type=int, default=12)
    parser.add_argument("--transient-window-months", type=int, default=6)
    parser.add_argument("--min-member-count", type=int, default=5)
    parser.add_argument("--min-pair-count", type=int, default=10)
    parser.add_argument("--min-strong-edges", type=int, default=5)
    parser.add_argument("--min-market-density", type=float, default=0.001)
    parser.add_argument("--top-n", type=int, default=40)
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
