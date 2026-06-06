from __future__ import annotations

import csv
import html
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .global_map import _write_csv


@dataclass(frozen=True)
class ComponentPairReadoutPaths:
    metadata_path: Path
    summary_path: Path
    html_path: Path


_SUMMARY_FIELDS = [
    "sequence_id",
    "window_count",
    "first_frame_index",
    "last_frame_index",
    "first_frame_label",
    "last_frame_label",
    "avg_mean_cross_correlation",
    "max_mean_cross_correlation",
    "avg_cross_edge_density",
    "avg_market_cross_edge_density",
    "max_market_cross_edge_density",
    "avg_normalized_cross_edge_density",
    "min_cross_pair_count",
    "avg_cross_pair_count",
    "min_component_density",
    "contains_warrant_like_symbol",
    "representative_component_a_top_symbols",
    "representative_component_b_top_symbols",
    "frame_labels",
    "readout_note",
]


def write_component_pair_readout(
    *,
    pair_dir: str | Path,
    output_dir: str | Path | None = None,
    min_mean_cross_correlation: float = 0.55,
    min_cross_edge_density: float = 0.7,
    min_cross_pair_count: int = 25,
    min_component_density: float = 0.5,
    max_market_density: float = 0.1,
    min_pair_jaccard: float = 0.5,
    min_persistence_windows: int = 2,
    exclude_warrant_like: bool = True,
    top_n: int = 80,
) -> ComponentPairReadoutPaths:
    _validate_args(
        min_mean_cross_correlation=min_mean_cross_correlation,
        min_cross_edge_density=min_cross_edge_density,
        min_cross_pair_count=min_cross_pair_count,
        min_component_density=min_component_density,
        max_market_density=max_market_density,
        min_pair_jaccard=min_pair_jaccard,
        min_persistence_windows=min_persistence_windows,
        top_n=top_n,
    )
    pair_path = Path(pair_dir)
    output_path = Path(output_dir) if output_dir else pair_path
    output_path.mkdir(parents=True, exist_ok=True)

    metadata = _read_json(pair_path / "component_pair_summary_metadata.json")
    artifacts = metadata.get("artifact_files", {})
    rows = _read_csv(pair_path / artifacts.get("pair_summary", "component_pair_summary.csv"))
    candidates = [
        row
        for row in rows
        if _passes_candidate_guards(
            row,
            min_mean_cross_correlation=min_mean_cross_correlation,
            min_cross_edge_density=min_cross_edge_density,
            min_cross_pair_count=min_cross_pair_count,
            min_component_density=min_component_density,
            max_market_density=max_market_density,
            exclude_warrant_like=exclude_warrant_like,
        )
    ]
    sequences = _build_sequences(candidates, min_pair_jaccard=min_pair_jaccard)
    summary_rows = [
        _sequence_row(index, sequence)
        for index, sequence in enumerate(sequences, start=1)
        if len(sequence) >= min_persistence_windows
    ]
    summary_rows.sort(
        key=lambda row: (
            -int(row["window_count"]),
            -_float(row["avg_mean_cross_correlation"]),
            -_float(row["avg_cross_edge_density"]),
            row["first_frame_label"],
        )
    )
    summary_rows = summary_rows[:top_n]

    metadata_path = output_path / "component_pair_readout_metadata.json"
    summary_path = output_path / "component_pair_readout.csv"
    html_path = output_path / "component_pair_readout.html"
    readout_metadata = {
        "artifact_files": {
            "metadata": metadata_path.name,
            "summary": summary_path.name,
            "html": html_path.name,
        },
        "mode": "descriptive_component_pair_readout",
        "source_pair_dir": str(pair_path),
        "min_mean_cross_correlation": min_mean_cross_correlation,
        "min_cross_edge_density": min_cross_edge_density,
        "min_cross_pair_count": min_cross_pair_count,
        "min_component_density": min_component_density,
        "max_market_density": max_market_density,
        "min_pair_jaccard": min_pair_jaccard,
        "min_persistence_windows": min_persistence_windows,
        "exclude_warrant_like": exclude_warrant_like,
        "top_n": top_n,
        "candidate_count": len(candidates),
        "sequence_count_before_persistence_filter": len(sequences),
        "sequence_count_written": len(summary_rows),
        "interpretation_note": (
            "This readout filters same-window component-pair summaries and groups adjacent "
            "windows by top-symbol overlap only. It is a descriptive co-movement readout, "
            "not stable component identity tracking and not lead-lag."
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
    html_path.write_text(_render_html(readout_metadata, summary_rows), encoding="utf-8")
    return ComponentPairReadoutPaths(metadata_path=metadata_path, summary_path=summary_path, html_path=html_path)


def _validate_args(
    *,
    min_mean_cross_correlation: float,
    min_cross_edge_density: float,
    min_cross_pair_count: int,
    min_component_density: float,
    max_market_density: float,
    min_pair_jaccard: float,
    min_persistence_windows: int,
    top_n: int,
) -> None:
    for name, value in {
        "min_cross_edge_density": min_cross_edge_density,
        "min_component_density": min_component_density,
        "max_market_density": max_market_density,
        "min_pair_jaccard": min_pair_jaccard,
    }.items():
        if value < 0 or value > 1:
            raise ValueError(f"{name} must be between 0 and 1.")
    if min_mean_cross_correlation < -1 or min_mean_cross_correlation > 1:
        raise ValueError("min_mean_cross_correlation must be between -1 and 1.")
    if min_cross_pair_count < 1:
        raise ValueError("min_cross_pair_count must be positive.")
    if min_persistence_windows < 1:
        raise ValueError("min_persistence_windows must be positive.")
    if top_n < 1:
        raise ValueError("top_n must be positive.")


def _passes_candidate_guards(
    row: dict[str, str],
    *,
    min_mean_cross_correlation: float,
    min_cross_edge_density: float,
    min_cross_pair_count: int,
    min_component_density: float,
    max_market_density: float,
    exclude_warrant_like: bool,
) -> bool:
    if _float(row.get("mean_cross_correlation")) < min_mean_cross_correlation:
        return False
    if _float(row.get("cross_edge_density")) < min_cross_edge_density:
        return False
    if _int(row.get("cross_pair_count")) < min_cross_pair_count:
        return False
    if _float(row.get("component_a_density")) < min_component_density:
        return False
    if _float(row.get("component_b_density")) < min_component_density:
        return False
    if _float(row.get("market_cross_edge_density")) > max_market_density:
        return False
    if exclude_warrant_like and _contains_warrant_like(row):
        return False
    return True


def _build_sequences(rows: list[dict[str, str]], *, min_pair_jaccard: float) -> list[list[dict[str, str]]]:
    sequences: list[list[dict[str, str]]] = []
    sorted_rows = sorted(
        rows,
        key=lambda row: (
            _int(row.get("frame_index")),
            -_float(row.get("mean_cross_correlation")),
            row.get("component_a_top_symbols", ""),
            row.get("component_b_top_symbols", ""),
        ),
    )
    for row in sorted_rows:
        best_index = None
        best_score = 0.0
        frame_index = _int(row.get("frame_index"))
        for index, sequence in enumerate(sequences):
            last = sequence[-1]
            if _int(last.get("frame_index")) != frame_index - 1:
                continue
            score = _pair_jaccard(last, row)
            if score >= min_pair_jaccard and score > best_score:
                best_score = score
                best_index = index
        if best_index is None:
            sequences.append([row])
        else:
            sequences[best_index].append(row)
    return sequences


def _sequence_row(index: int, sequence: list[dict[str, str]]) -> dict[str, str]:
    first = sequence[0]
    last = sequence[-1]
    all_symbols = " ".join(
        row.get("component_a_top_symbols", "") + " " + row.get("component_b_top_symbols", "")
        for row in sequence
    )
    return {
        "sequence_id": f"P{index:03d}",
        "window_count": str(len(sequence)),
        "first_frame_index": first.get("frame_index", ""),
        "last_frame_index": last.get("frame_index", ""),
        "first_frame_label": first.get("frame_label", ""),
        "last_frame_label": last.get("frame_label", ""),
        "avg_mean_cross_correlation": _format_float(_average(sequence, "mean_cross_correlation")),
        "max_mean_cross_correlation": _format_float(max(_float(row.get("mean_cross_correlation")) for row in sequence)),
        "avg_cross_edge_density": _format_float(_average(sequence, "cross_edge_density")),
        "avg_market_cross_edge_density": _format_float(_average(sequence, "market_cross_edge_density")),
        "max_market_cross_edge_density": _format_float(max(_float(row.get("market_cross_edge_density")) for row in sequence)),
        "avg_normalized_cross_edge_density": _format_float(_average(sequence, "normalized_cross_edge_density")),
        "min_cross_pair_count": str(min(_int(row.get("cross_pair_count")) for row in sequence)),
        "avg_cross_pair_count": _format_float(_average(sequence, "cross_pair_count")),
        "min_component_density": _format_float(
            min(
                min(_float(row.get("component_a_density")), _float(row.get("component_b_density")))
                for row in sequence
            )
        ),
        "contains_warrant_like_symbol": str(_contains_warrant_text(all_symbols)).lower(),
        "representative_component_a_top_symbols": first.get("component_a_top_symbols", ""),
        "representative_component_b_top_symbols": first.get("component_b_top_symbols", ""),
        "frame_labels": " | ".join(row.get("frame_label", "") for row in sequence),
        "readout_note": (
            "Same-window co-movement sequence grouped by top-symbol overlap; not a direction, "
            "not propagation, not a forecast."
        ),
    }


def _average(rows: list[dict[str, str]], field: str) -> float:
    if not rows:
        return 0.0
    return sum(_float(row.get(field)) for row in rows) / len(rows)


def _pair_jaccard(left: dict[str, str], right: dict[str, str]) -> float:
    left_a = _symbol_set(left.get("component_a_top_symbols", ""))
    left_b = _symbol_set(left.get("component_b_top_symbols", ""))
    right_a = _symbol_set(right.get("component_a_top_symbols", ""))
    right_b = _symbol_set(right.get("component_b_top_symbols", ""))
    direct = min(_jaccard(left_a, right_a), _jaccard(left_b, right_b))
    swapped = min(_jaccard(left_a, right_b), _jaccard(left_b, right_a))
    return max(direct, swapped)


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def _symbol_set(value: str) -> set[str]:
    return {item.strip().upper() for item in value.split() if item.strip()}


def _contains_warrant_like(row: dict[str, str]) -> bool:
    text = f"{row.get('component_a_top_symbols', '')} {row.get('component_b_top_symbols', '')}"
    return _contains_warrant_text(text)


def _contains_warrant_text(text: str) -> bool:
    for symbol in _symbol_set(text):
        if "-WT" in symbol or symbol.endswith("WT") or symbol.endswith("W") or "-W" in symbol:
            return True
    return False


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _int(value: Any) -> int:
    try:
        if value in ("", None):
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        if value in ("", None):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _format_float(value: float) -> str:
    return f"{value:.12g}"


def _render_html(metadata: dict[str, Any], rows: list[dict[str, str]]) -> str:
    header = "".join(f"<th>{html.escape(field)}</th>" for field in _SUMMARY_FIELDS)
    body = "\n".join(
        "<tr>"
        + "".join(f"<td>{html.escape(str(row.get(field, '')))}</td>" for field in _SUMMARY_FIELDS)
        + "</tr>"
        for row in rows
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Component Pair Readout</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 24px; color: #172026; }}
    .note {{ max-width: 1080px; color: #44515c; line-height: 1.45; }}
    table {{ border-collapse: collapse; font-size: 12px; min-width: 1500px; }}
    th, td {{ border: 1px solid #d7dde3; padding: 5px 7px; vertical-align: top; }}
    th {{ position: sticky; top: 0; background: #f3f6f8; text-align: left; }}
    .scroll {{ overflow-x: auto; border: 1px solid #d7dde3; }}
  </style>
</head>
<body>
  <h1>Component Pair Readout</h1>
  <p class="note">Filtered same-window co-movement sequences from component pair summaries. No lead-lag, no direction, no propagation, no forecast, and no recommendation.</p>
  <p class="note">Rows are grouped by adjacent-window top-symbol overlap only. This is not stable identity tracking. Normalized density is context; mean cross-correlation is the main co-movement magnitude.</p>
  <p class="note">Minimum windows: {metadata.get("min_persistence_windows")}; min mean correlation: {metadata.get("min_mean_cross_correlation")}; max market density: {metadata.get("max_market_density")}.</p>
  <div class="scroll"><table><thead><tr>{header}</tr></thead><tbody>{body}</tbody></table></div>
</body>
</html>
"""
