from __future__ import annotations

import argparse
from typing import Sequence

from .component_pair_readout import ComponentPairReadoutPaths, write_component_pair_readout


def run(argv: Sequence[str] | None = None) -> ComponentPairReadoutPaths:
    args = _parse_args(argv)
    return write_component_pair_readout(
        pair_dir=args.pair_dir,
        output_dir=args.output_dir,
        min_mean_cross_correlation=args.min_mean_cross_correlation,
        min_cross_edge_density=args.min_cross_edge_density,
        min_cross_pair_count=args.min_cross_pair_count,
        min_component_density=args.min_component_density,
        max_market_density=args.max_market_density,
        min_pair_jaccard=args.min_pair_jaccard,
        min_persistence_windows=args.min_persistence_windows,
        exclude_warrant_like=not args.include_warrant_like,
        top_n=args.top_n,
    )


def main(argv: Sequence[str] | None = None) -> int:
    outputs = run(argv)
    print(f"Wrote component pair readout metadata: {outputs.metadata_path}")
    print(f"Wrote component pair readout summary: {outputs.summary_path}")
    print(f"Wrote component pair readout HTML: {outputs.html_path}")
    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a guarded descriptive readout from component pair summary CSVs."
    )
    parser.add_argument("pair_dir", help="Directory containing component_pair_summary_metadata.json and CSV.")
    parser.add_argument("--output-dir", help="Optional output directory. Defaults to pair_dir.")
    parser.add_argument("--min-mean-cross-correlation", type=float, default=0.55)
    parser.add_argument("--min-cross-edge-density", type=float, default=0.7)
    parser.add_argument("--min-cross-pair-count", type=int, default=25)
    parser.add_argument("--min-component-density", type=float, default=0.5)
    parser.add_argument("--max-market-density", type=float, default=0.1)
    parser.add_argument("--min-pair-jaccard", type=float, default=0.5)
    parser.add_argument("--min-persistence-windows", type=int, default=2)
    parser.add_argument("--include-warrant-like", action="store_true")
    parser.add_argument("--top-n", type=int, default=80)
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
