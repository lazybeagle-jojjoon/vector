from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .global_map import GlobalMapOutputPaths, write_global_map_view


def run(argv: Sequence[str] | None = None) -> GlobalMapOutputPaths:
    args = _parse_args(argv)
    return write_global_map_view(
        Path(args.snapshot),
        output_dir=args.output_dir,
        node_metadata_path=args.node_metadata,
        top_k=args.top_k,
        seed=args.seed,
        iterations=args.iterations,
    )


def main(argv: Sequence[str] | None = None) -> int:
    try:
        outputs = run(argv)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Wrote global map metadata: {outputs.metadata_path}")
    print(f"Wrote global layout: {outputs.layout_path}")
    print(f"Wrote global edges: {outputs.edges_path}")
    print(f"Wrote global map HTML: {outputs.html_path}")
    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a single-snapshot global relationship map from saved outputs."
    )
    parser.add_argument(
        "--snapshot",
        required=True,
        help="Snapshot output directory containing metadata.json, universe.csv, returns.csv, and neighbors.csv.",
    )
    parser.add_argument(
        "--node-metadata",
        help="Optional CSV keyed by symbol/ticker for tooltip overlays such as name, sector, and industry.",
    )
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--iterations", type=int, default=80)
    parser.add_argument("--output-dir", default="outputs/relation_snapshot_global_map")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
