from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .global_timeline import GlobalTimelineOutputPaths, write_global_timeline_view


def run(argv: Sequence[str] | None = None) -> GlobalTimelineOutputPaths:
    args = _parse_args(argv)
    return write_global_timeline_view(
        Path(args.reference_map),
        [Path(snapshot) for snapshot in args.snapshot],
        output_dir=args.output_dir,
        top_k=args.top_k,
    )


def main(argv: Sequence[str] | None = None) -> int:
    try:
        outputs = run(argv)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Wrote global timeline metadata: {outputs.metadata_path}")
    print(f"Wrote global timeline nodes: {outputs.nodes_path}")
    print(f"Wrote global timeline edges: {outputs.edges_path}")
    print(f"Wrote global timeline frames: {outputs.frames_path}")
    print(f"Wrote global timeline HTML: {outputs.html_path}")
    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render fixed-layout small multiples from saved relationship snapshots."
    )
    parser.add_argument(
        "--reference-map",
        required=True,
        help="Global map output directory containing global_layout.csv to reuse as the fixed frame.",
    )
    parser.add_argument(
        "--snapshot",
        action="append",
        required=True,
        help=(
            "Snapshot output directory containing metadata.json, universe.csv, returns.csv, "
            "and neighbors.csv. Pass once per timeline frame in display order."
        ),
    )
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--output-dir", default="outputs/relation_snapshot_global_timeline")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
