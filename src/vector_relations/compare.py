from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class ComparisonOutputPaths:
    summary_path: Path
    neighbor_changes_path: Path
    distance_changes_path: Path
    insights_path: Path


@dataclass(frozen=True)
class _SnapshotNeighbors:
    label: str
    path: Path
    metadata: dict[str, Any]
    neighbors_by_symbol: dict[str, dict[str, dict[str, Any]]]
    symbols_in_universe: set[str] | None


def compare_snapshot_directories(
    snapshot_dirs: Iterable[str | Path],
    *,
    output_dir: str | Path,
    symbols: list[str] | None = None,
    top_k: int = 10,
) -> ComparisonOutputPaths:
    paths = [Path(path) for path in snapshot_dirs]
    if len(paths) < 2:
        raise ValueError("At least two snapshot directories are required.")
    if top_k < 1:
        raise ValueError("top_k must be at least 1.")

    snapshots = [_load_snapshot(path, top_k=top_k) for path in paths]
    requested_symbols = _resolve_symbols(snapshots, symbols)
    neighbor_change_rows: list[dict[str, Any]] = []
    distance_change_rows: list[dict[str, Any]] = []

    for old_snapshot, new_snapshot in zip(snapshots, snapshots[1:]):
        for symbol in requested_symbols:
            old_neighbors = old_snapshot.neighbors_by_symbol.get(symbol, {})
            new_neighbors = new_snapshot.neighbors_by_symbol.get(symbol, {})
            old_set = set(old_neighbors)
            new_set = set(new_neighbors)
            stayed = sorted(old_set & new_set)
            entered = sorted(new_set - old_set)
            exited = sorted(old_set - new_set)
            union = old_set | new_set

            neighbor_change_rows.append(
                {
                    "from_snapshot": old_snapshot.label,
                    "to_snapshot": new_snapshot.label,
                    "symbol": symbol,
                    "old_symbol_in_universe": _presence(old_snapshot, symbol),
                    "new_symbol_in_universe": _presence(new_snapshot, symbol),
                    "old_neighbor_count": len(old_set),
                    "new_neighbor_count": len(new_set),
                    "stayed_neighbors": ";".join(stayed),
                    "entered_neighbors": ";".join(entered),
                    "exited_neighbors": ";".join(exited),
                    "jaccard_similarity": _jaccard(old_set, new_set),
                }
            )
            for neighbor_symbol in sorted(union):
                old_entry = old_neighbors.get(neighbor_symbol)
                new_entry = new_neighbors.get(neighbor_symbol)
                distance_change_rows.append(
                    _distance_change_row(
                        from_snapshot=old_snapshot.label,
                        to_snapshot=new_snapshot.label,
                        symbol=symbol,
                        neighbor_symbol=neighbor_symbol,
                        old_neighbor_in_universe=_presence(old_snapshot, neighbor_symbol),
                        new_neighbor_in_universe=_presence(new_snapshot, neighbor_symbol),
                        old_entry=old_entry,
                        new_entry=new_entry,
                    )
                )

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    summary_path = output_path / "summary.json"
    neighbor_changes_path = output_path / "neighbor_changes.csv"
    distance_changes_path = output_path / "distance_changes.csv"
    insights_path = output_path / "insights.md"

    summary = {
        "artifact_files": {
            "neighbor_changes": neighbor_changes_path.name,
            "distance_changes": distance_changes_path.name,
            "insights": insights_path.name,
        },
        "snapshot_count": len(snapshots),
        "snapshots": [
            {
                "label": snapshot.label,
                "path": str(snapshot.path),
                "period_start": snapshot.metadata.get("period_start"),
                "period_end": snapshot.metadata.get("period_end"),
                "security_count": snapshot.metadata.get("security_count"),
            }
            for snapshot in snapshots
        ],
        "symbols": requested_symbols,
        "top_k": top_k,
        "pair_count": len(snapshots) - 1,
        "neighbor_change_rows": len(neighbor_change_rows),
        "distance_change_rows": len(distance_change_rows),
        "comparison_note": (
            "Compares top-k neighbor tables only; full N x N distance matrices are not re-read."
        ),
        "universe_presence_note": (
            "Entered/exited neighbors can reflect relationship changes, universe membership changes, "
            "or both. Use *_in_universe columns to separate those cases when universe.csv is available."
        ),
    }
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_csv(neighbor_changes_path, _NEIGHBOR_CHANGE_FIELDS, neighbor_change_rows)
    _write_csv(distance_changes_path, _DISTANCE_CHANGE_FIELDS, distance_change_rows)
    insights_path.write_text(
        _render_insights_markdown(
            neighbor_change_rows=neighbor_change_rows,
            distance_change_rows=distance_change_rows,
        ),
        encoding="utf-8",
    )
    return ComparisonOutputPaths(
        summary_path=summary_path,
        neighbor_changes_path=neighbor_changes_path,
        distance_changes_path=distance_changes_path,
        insights_path=insights_path,
    )


_NEIGHBOR_CHANGE_FIELDS = [
    "from_snapshot",
    "to_snapshot",
    "symbol",
    "old_symbol_in_universe",
    "new_symbol_in_universe",
    "old_neighbor_count",
    "new_neighbor_count",
    "stayed_neighbors",
    "entered_neighbors",
    "exited_neighbors",
    "jaccard_similarity",
]

_DISTANCE_CHANGE_FIELDS = [
    "from_snapshot",
    "to_snapshot",
    "symbol",
    "neighbor_symbol",
    "old_neighbor_in_universe",
    "new_neighbor_in_universe",
    "old_rank",
    "new_rank",
    "old_distance",
    "new_distance",
    "distance_delta",
    "old_correlation",
    "new_correlation",
    "correlation_delta",
    "status",
]


def _load_snapshot(path: Path, *, top_k: int) -> _SnapshotNeighbors:
    metadata_path = path / "metadata.json"
    if not metadata_path.exists():
        raise ValueError(f"Snapshot metadata does not exist: {metadata_path}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    neighbors_path = path / metadata.get("artifact_files", {}).get("neighbors", "neighbors.csv")
    if not neighbors_path.exists():
        raise ValueError(f"Snapshot neighbors CSV does not exist: {neighbors_path}")
    universe_path = path / metadata.get("artifact_files", {}).get("universe", "universe.csv")

    neighbors_by_symbol: dict[str, dict[str, dict[str, Any]]] = {}
    with neighbors_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rank = int(row["rank"])
            if rank > top_k:
                continue
            symbol = row["symbol"]
            neighbor_symbol = row["neighbor_symbol"]
            neighbors_by_symbol.setdefault(symbol, {})[neighbor_symbol] = {
                "rank": rank,
                "distance": float(row["distance"]),
                "correlation": float(row["correlation"]),
            }
    return _SnapshotNeighbors(
        label=_snapshot_label(metadata, path),
        path=path,
        metadata=metadata,
        neighbors_by_symbol=neighbors_by_symbol,
        symbols_in_universe=_read_universe_symbols(universe_path),
    )


def _snapshot_label(metadata: dict[str, Any], path: Path) -> str:
    period_start = metadata.get("period_start")
    period_end = metadata.get("period_end")
    if period_start and period_end:
        return f"{period_start}_to_{period_end}"
    return path.name


def _resolve_symbols(
    snapshots: list[_SnapshotNeighbors],
    symbols: list[str] | None,
) -> list[str]:
    if symbols:
        return sorted(dict.fromkeys(symbols))
    all_symbols: set[str] = set()
    for snapshot in snapshots:
        all_symbols.update(snapshot.neighbors_by_symbol)
    return sorted(all_symbols)


def _jaccard(old_set: set[str], new_set: set[str]) -> float | str:
    union = old_set | new_set
    if not union:
        return ""
    return len(old_set & new_set) / len(union)


def _distance_change_row(
    *,
    from_snapshot: str,
    to_snapshot: str,
    symbol: str,
    neighbor_symbol: str,
    old_neighbor_in_universe: str,
    new_neighbor_in_universe: str,
    old_entry: dict[str, Any] | None,
    new_entry: dict[str, Any] | None,
) -> dict[str, Any]:
    old_distance = _entry_value(old_entry, "distance")
    new_distance = _entry_value(new_entry, "distance")
    old_correlation = _entry_value(old_entry, "correlation")
    new_correlation = _entry_value(new_entry, "correlation")
    return {
        "from_snapshot": from_snapshot,
        "to_snapshot": to_snapshot,
        "symbol": symbol,
        "neighbor_symbol": neighbor_symbol,
        "old_neighbor_in_universe": old_neighbor_in_universe,
        "new_neighbor_in_universe": new_neighbor_in_universe,
        "old_rank": _entry_value(old_entry, "rank"),
        "new_rank": _entry_value(new_entry, "rank"),
        "old_distance": old_distance,
        "new_distance": new_distance,
        "distance_delta": _delta(old_distance, new_distance),
        "old_correlation": old_correlation,
        "new_correlation": new_correlation,
        "correlation_delta": _delta(old_correlation, new_correlation),
        "status": _status(old_entry, new_entry),
    }


def _entry_value(entry: dict[str, Any] | None, key: str) -> Any:
    if entry is None:
        return ""
    return entry[key]


def _delta(old_value: Any, new_value: Any) -> float | str:
    if old_value == "" or new_value == "":
        return ""
    return float(new_value) - float(old_value)


def _status(old_entry: dict[str, Any] | None, new_entry: dict[str, Any] | None) -> str:
    if old_entry is not None and new_entry is not None:
        return "stayed"
    if old_entry is None:
        return "entered"
    return "exited"


def _read_universe_symbols(path: Path) -> set[str] | None:
    if not path.exists():
        return None
    with path.open(newline="", encoding="utf-8") as handle:
        return {row["symbol"] for row in csv.DictReader(handle)}


def _presence(snapshot: _SnapshotNeighbors, symbol: str) -> str:
    if snapshot.symbols_in_universe is None:
        return ""
    return "true" if symbol in snapshot.symbols_in_universe else "false"


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _render_insights_markdown(
    *,
    neighbor_change_rows: list[dict[str, Any]],
    distance_change_rows: list[dict[str, Any]],
) -> str:
    lines = [
        "# Snapshot Comparison Insights",
        "",
        "This is a lightweight text summary of top-k neighbor changes.",
        "",
        "## Limits",
        "",
        "- Top-k neighbor rows only; full pairwise distance matrices are not scanned here.",
        "- Entered/exited can reflect relationship changes, universe membership changes, or both.",
        "- Residual source-data classification issues can remain, including CEF-like names marked as Common Stock.",
        "",
        "## Most Stable Neighbor Sets",
        "",
    ]
    stable_rows = sorted(
        (row for row in neighbor_change_rows if row["jaccard_similarity"] != ""),
        key=lambda row: float(row["jaccard_similarity"]),
        reverse=True,
    )
    lines.extend(_neighbor_change_lines(stable_rows[:10]))
    lines.extend(["", "## Most Changed Neighbor Sets", ""])
    changed_rows = sorted(
        (row for row in neighbor_change_rows if row["jaccard_similarity"] != ""),
        key=lambda row: float(row["jaccard_similarity"]),
    )
    lines.extend(_neighbor_change_lines(changed_rows[:10]))
    lines.extend(["", "## Largest Stayed Distance Changes", ""])
    stayed_rows = sorted(
        (
            row
            for row in distance_change_rows
            if row["status"] == "stayed" and row["distance_delta"] != ""
        ),
        key=lambda row: abs(float(row["distance_delta"])),
        reverse=True,
    )
    lines.extend(_distance_change_lines(stayed_rows[:10]))
    lines.extend(["", "## Universe Cautions", ""])
    lines.extend(_universe_caution_lines(neighbor_change_rows, distance_change_rows))
    return "\n".join(lines).rstrip() + "\n"


def _neighbor_change_lines(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["- No comparable neighbor sets."]
    lines = []
    for row in rows:
        lines.append(
            "- "
            f"{row['from_snapshot']} -> {row['to_snapshot']} | "
            f"{row['symbol']}: jaccard {float(row['jaccard_similarity']):.4f}, "
            f"stayed [{row['stayed_neighbors']}], "
            f"entered [{row['entered_neighbors']}], "
            f"exited [{row['exited_neighbors']}]"
        )
    return lines


def _distance_change_lines(rows: list[dict[str, Any]]) -> list[str]:
    if not rows:
        return ["- No stayed neighbor distance changes."]
    lines = []
    for row in rows:
        delta = float(row["distance_delta"])
        direction = "farther" if delta > 0 else "closer"
        lines.append(
            "- "
            f"{row['from_snapshot']} -> {row['to_snapshot']} | "
            f"{row['symbol']}-{row['neighbor_symbol']}: {direction} by {abs(delta):.4f} "
            f"({float(row['old_distance']):.4f} -> {float(row['new_distance']):.4f})"
        )
    return lines


def _universe_caution_lines(
    neighbor_change_rows: list[dict[str, Any]],
    distance_change_rows: list[dict[str, Any]],
) -> list[str]:
    lines = []
    for row in neighbor_change_rows:
        old_presence = row["old_symbol_in_universe"]
        new_presence = row["new_symbol_in_universe"]
        if old_presence != new_presence:
            lines.append(
                "- "
                f"{row['from_snapshot']} -> {row['to_snapshot']} | "
                f"{row['symbol']}: target universe {old_presence} -> {new_presence}"
            )
        elif old_presence == "false" and new_presence == "false" and row["jaccard_similarity"] == "":
            lines.append(
                "- "
                f"{row['from_snapshot']} -> {row['to_snapshot']} | "
                f"{row['symbol']}: absent from both universes"
            )

    for row in distance_change_rows:
        old_presence = row["old_neighbor_in_universe"]
        new_presence = row["new_neighbor_in_universe"]
        if old_presence == new_presence:
            continue
        lines.append(
            "- "
            f"{row['from_snapshot']} -> {row['to_snapshot']} | "
            f"{row['symbol']}-{row['neighbor_symbol']}: neighbor universe "
            f"{old_presence} -> {new_presence} ({row['status']})"
        )
    if not lines:
        return ["- No target or neighbor universe membership changes detected for these rows."]
    return lines[:25]
