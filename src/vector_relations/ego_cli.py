from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .ego import EgoNetworkOutputPaths, write_ego_network_view


def run(argv: Sequence[str] | None = None) -> EgoNetworkOutputPaths:
    args = _parse_args(argv)
    return write_ego_network_view(
        [Path(snapshot) for snapshot in args.snapshot],
        symbol=args.symbol,
        output_dir=args.output_dir,
        comparison_dir=args.comparison_dir,
        top_k=args.top_k,
    )


def main(argv: Sequence[str] | None = None) -> int:
    try:
        outputs = run(argv)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Wrote ego network HTML: {outputs.html_path}")
    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a generic single-symbol ego network from saved relation snapshots."
    )
    parser.add_argument(
        "--snapshot",
        action="append",
        required=True,
        help="Snapshot output directory. Provide one or more, in display order.",
    )
    parser.add_argument(
        "--symbol",
        required=True,
        help="Center symbol to render. This is generic and is not tied to any fixed ticker.",
    )
    parser.add_argument(
        "--comparison-dir",
        help="Optional comparison output directory with neighbor_changes.csv for status colors.",
    )
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--output-dir", default="outputs/relation_snapshot_ego_network")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
