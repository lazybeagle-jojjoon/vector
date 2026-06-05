from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .global_map import _write_csv


@dataclass(frozen=True)
class WindowFlowReadoutPaths:
    metadata_path: Path
    summary_path: Path
    markdown_path: Path


_SUMMARY_FIELDS = [
    "classification",
    "scope",
    "window_months",
    "window_frame_index",
    "frame_label",
    "threshold",
    "label",
    "normalized_ratio",
    "market_strong_edge_ratio",
    "member_count",
    "pair_count",
    "strong_edge_count",
    "readout_note",
]


def write_window_flow_readout(
    *,
    sweep_dir: str | Path,
    output_dir: str | Path | None = None,
    durable_window_months: int = 12,
    transient_window_months: int = 6,
    min_member_count: int = 5,
    min_pair_count: int = 10,
    min_strong_edges: int = 5,
    min_market_density: float = 0.001,
    exclude_groups: list[str] | tuple[str, ...] = ("missing",),
    top_n: int = 40,
) -> WindowFlowReadoutPaths:
    sweep_path = Path(sweep_dir)
    output_path = Path(output_dir) if output_dir else sweep_path
    output_path.mkdir(parents=True, exist_ok=True)

    metadata = _read_json(sweep_path / "threshold_sweep_metadata.json")
    artifacts = metadata.get("artifact_files", {})
    group_rows = _read_csv(sweep_path / artifacts.get("group_summary", "threshold_group_summary.csv"))
    cross_rows = _read_csv(
        sweep_path / artifacts.get("cross_group_summary", "threshold_cross_group_summary.csv")
    )

    candidates = _candidate_rows(
        group_rows=group_rows,
        cross_rows=cross_rows,
        min_member_count=min_member_count,
        min_pair_count=min_pair_count,
        min_strong_edges=min_strong_edges,
        min_market_density=min_market_density,
        exclude_groups={value.lower() for value in exclude_groups},
    )
    durable = _top_rows(
        [row for row in candidates if row["window_months"] == str(durable_window_months)],
        top_n=top_n,
        classification="durable",
        note=f"High normalized ratio in {durable_window_months}-month windows; read as slower structure.",
    )
    durable_keys = {(row["scope"], row["threshold"], row["label"]) for row in durable}
    transient = _top_rows(
        [
            row
            for row in candidates
            if row["window_months"] == str(transient_window_months)
            and (row["scope"], row["threshold"], row["label"]) not in durable_keys
        ],
        top_n=top_n,
        classification="transient",
        note=(
            f"High normalized ratio in {transient_window_months}-month windows but not in the "
            f"top {durable_window_months}-month durable set; read as resolution-specific movement."
        ),
    )
    summary_rows = durable + transient

    metadata_path = output_path / "window_flow_readout_metadata.json"
    summary_path = output_path / "window_flow_summary.csv"
    markdown_path = output_path / "window_flow_summary.md"
    readout_metadata = {
        "artifact_files": {
            "metadata": metadata_path.name,
            "summary": summary_path.name,
            "markdown": markdown_path.name,
        },
        "mode": "descriptive_window_flow_readout",
        "source_sweep_dir": str(sweep_path),
        "durable_window_months": durable_window_months,
        "transient_window_months": transient_window_months,
        "min_member_count": min_member_count,
        "min_pair_count": min_pair_count,
        "min_strong_edges": min_strong_edges,
        "min_market_density": min_market_density,
        "exclude_groups": list(exclude_groups),
        "top_n": top_n,
        "interpretation_note": (
            "6-month and 12-month windows are overlapping lenses, not independent confirmations. "
            "This readout classifies same-window structure only."
        ),
        "disclaimer": (
            "Descriptive historical structure only; not investment advice, not a forecast, "
            "and not a recommendation."
        ),
    }
    metadata_path.write_text(
        json.dumps(readout_metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_csv(summary_path, _SUMMARY_FIELDS, summary_rows)
    markdown_path.write_text(_render_markdown(readout_metadata, summary_rows), encoding="utf-8")
    return WindowFlowReadoutPaths(
        metadata_path=metadata_path,
        summary_path=summary_path,
        markdown_path=markdown_path,
    )


def _candidate_rows(
    *,
    group_rows: list[dict[str, str]],
    cross_rows: list[dict[str, str]],
    min_member_count: int,
    min_pair_count: int,
    min_strong_edges: int,
    min_market_density: float,
    exclude_groups: set[str],
) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    for row in group_rows:
        group_name = row.get("group_name", "")
        if group_name.lower() in exclude_groups:
            continue
        member_count = _int(row.get("member_count"))
        pair_count = _int(row.get("internal_pair_count"))
        strong_edges = _int(row.get("internal_strong_edge_count"))
        if member_count < min_member_count:
            continue
        if not _passes_common_guards(row, pair_count, strong_edges, min_pair_count, min_strong_edges, min_market_density):
            continue
        candidates.append(
            _candidate(
                row=row,
                scope="internal",
                label=group_name,
                member_count=str(member_count),
                pair_count=str(pair_count),
                strong_edges=str(strong_edges),
                normalized=row.get("internal_strong_edge_ratio_normalized", ""),
            )
        )

    for row in cross_rows:
        group_a = row.get("group_a", "")
        group_b = row.get("group_b", "")
        if group_a.lower() in exclude_groups or group_b.lower() in exclude_groups:
            continue
        pair_count = _int(row.get("cross_pair_count"))
        strong_edges = _int(row.get("cross_strong_edge_count"))
        if not _passes_common_guards(row, pair_count, strong_edges, min_pair_count, min_strong_edges, min_market_density):
            continue
        label = f"{group_a} / {group_b}"
        candidates.append(
            _candidate(
                row=row,
                scope="cross",
                label=label,
                member_count="",
                pair_count=str(pair_count),
                strong_edges=str(strong_edges),
                normalized=row.get("cross_strong_edge_ratio_normalized", ""),
            )
        )
    return [row for row in candidates if _float(row.get("normalized_ratio")) is not None]


def _passes_common_guards(
    row: dict[str, str],
    pair_count: int,
    strong_edges: int,
    min_pair_count: int,
    min_strong_edges: int,
    min_market_density: float,
) -> bool:
    market_density = _float(row.get("market_strong_edge_ratio"))
    if pair_count < min_pair_count or strong_edges < min_strong_edges:
        return False
    return market_density is not None and market_density >= min_market_density


def _candidate(
    *,
    row: dict[str, str],
    scope: str,
    label: str,
    member_count: str,
    pair_count: str,
    strong_edges: str,
    normalized: str,
) -> dict[str, str]:
    return {
        "classification": "",
        "scope": scope,
        "window_months": row.get("window_months", ""),
        "window_frame_index": row.get("window_frame_index", ""),
        "frame_label": row.get("frame_label", ""),
        "threshold": row.get("threshold", ""),
        "label": label,
        "normalized_ratio": normalized,
        "market_strong_edge_ratio": row.get("market_strong_edge_ratio", ""),
        "member_count": member_count,
        "pair_count": pair_count,
        "strong_edge_count": strong_edges,
        "readout_note": "",
    }


def _top_rows(
    rows: list[dict[str, str]], *, top_n: int, classification: str, note: str
) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    for scope in sorted({row["scope"] for row in rows}):
        sorted_rows = sorted(
            [row for row in rows if row["scope"] == scope],
            key=lambda row: _float(row.get("normalized_ratio")) or float("-inf"),
            reverse=True,
        )[:top_n]
        selected.extend(
            {**row, "classification": classification, "readout_note": note}
            for row in sorted_rows
        )
    return sorted(
        selected,
        key=lambda row: (row["classification"], row["scope"], -(_float(row["normalized_ratio"]) or 0)),
    )


def _render_markdown(metadata: dict[str, Any], rows: list[dict[str, str]]) -> str:
    lines = [
        "# Window Flow Summary",
        "",
        "This is descriptive historical structure only, not investment advice, not a forecast, and not a recommendation.",
        "",
        "6-month and 12-month windows are overlapping lenses, not independent confirmations.",
        "",
        "## Durable internal",
        *_markdown_rows(_section_rows(rows, "durable", "internal")),
        "",
        "## Durable cross",
        *_markdown_rows(_section_rows(rows, "durable", "cross")),
        "",
        "## Transient internal",
        *_markdown_rows(_section_rows(rows, "transient", "internal")),
        "",
        "## Transient cross",
        *_markdown_rows(_section_rows(rows, "transient", "cross")),
        "",
        "## Guards",
        "",
        f"- min_member_count: {metadata['min_member_count']}",
        f"- min_pair_count: {metadata['min_pair_count']}",
        f"- min_strong_edges: {metadata['min_strong_edges']}",
        f"- min_market_density: {metadata['min_market_density']}",
        f"- exclude_groups: {', '.join(metadata['exclude_groups'])}",
        "",
    ]
    return "\n".join(lines)


def _section_rows(rows: list[dict[str, str]], classification: str, scope: str) -> list[dict[str, str]]:
    return [
        row for row in rows if row["classification"] == classification and row["scope"] == scope
    ][:12]


def _markdown_rows(rows: list[dict[str, str]]) -> list[str]:
    if not rows:
        return ["- None after guards."]
    return [
        (
            f"- {row['window_months']}m {row['threshold']} {row['scope']} "
            f"{row['label']}: ratio {row['normalized_ratio']}, edges {row['strong_edge_count']}, "
            f"pairs {row['pair_count']}"
        )
        for row in rows
    ]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _int(value: Any) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(str(value))
    except (TypeError, ValueError):
        return None
