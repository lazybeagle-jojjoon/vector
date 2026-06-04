from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .market_cap_metadata import write_market_cap_metadata


def run(argv: Sequence[str] | None = None) -> Path:
    args = _parse_args(argv)
    write_market_cap_metadata(
        snapshot_dir=args.snapshot,
        raw_root=args.raw_root,
        market=args.market,
        output_path=args.output,
        file_timeout_seconds=args.file_timeout_seconds,
    )
    return Path(args.output)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        output_path = run(argv)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print(f"Wrote market-cap node metadata: {output_path}")
    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Write raw/current/as-of-fetch market-cap node metadata from "
            "saved snapshot universe and raw EODHD fundamentals."
        )
    )
    parser.add_argument(
        "--snapshot",
        required=True,
        help="Snapshot output directory containing universe.csv.",
    )
    parser.add_argument(
        "--raw-root",
        required=True,
        help="Directory containing per-market raw fundamentals folders such as us/ and kr/.",
    )
    parser.add_argument(
        "--market",
        required=True,
        help="Market code matching the raw fundamentals subdirectory, for example us or kr.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output CSV path for node metadata.",
    )
    parser.add_argument(
        "--file-timeout-seconds",
        type=int,
        default=0,
        help=(
            "Optional per-file read timeout for cloud-synced raw JSON. "
            "0 means no timeout."
        ),
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
