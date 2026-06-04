from __future__ import annotations

import csv
import html
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class EgoNetworkOutputPaths:
    html_path: Path


@dataclass(frozen=True)
class _SnapshotView:
    label: str
    path: Path
    metadata: dict[str, Any]
    neighbors: dict[str, dict[str, Any]]
    returns: dict[str, float | None]


def write_ego_network_view(
    snapshot_dirs: Iterable[str | Path],
    *,
    symbol: str,
    output_dir: str | Path,
    comparison_dir: str | Path | None = None,
    top_k: int = 10,
) -> EgoNetworkOutputPaths:
    paths = [Path(path) for path in snapshot_dirs]
    if not paths:
        raise ValueError("At least one snapshot directory is required.")
    if top_k < 1:
        raise ValueError("top_k must be at least 1.")
    target_symbol = symbol.strip().upper()
    if not target_symbol:
        raise ValueError("symbol is required.")

    snapshots = [_load_snapshot(path, symbol=target_symbol, top_k=top_k) for path in paths]
    if not any(snapshot.neighbors for snapshot in snapshots):
        raise ValueError(f"No top-k neighbors found for symbol: {target_symbol}")

    transitions = _load_neighbor_transitions(comparison_dir, symbol=target_symbol)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    html_path = output_path / "ego_network.html"
    html_path.write_text(
        _render_ego_html(
            symbol=target_symbol,
            snapshots=snapshots,
            transitions=transitions,
            top_k=top_k,
        ),
        encoding="utf-8",
    )
    return EgoNetworkOutputPaths(html_path=html_path)


def _load_snapshot(path: Path, *, symbol: str, top_k: int) -> _SnapshotView:
    metadata_path = path / "metadata.json"
    if not metadata_path.exists():
        raise ValueError(f"Snapshot metadata does not exist: {metadata_path}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    artifact_files = metadata.get("artifact_files", {})
    neighbors_path = path / artifact_files.get("neighbors", "neighbors.csv")
    if not neighbors_path.exists():
        raise ValueError(f"Snapshot neighbors CSV does not exist: {neighbors_path}")

    neighbors: dict[str, dict[str, Any]] = {}
    with neighbors_path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["symbol"].upper() != symbol:
                continue
            rank = int(row["rank"])
            if rank > top_k:
                continue
            neighbor_symbol = row["neighbor_symbol"].upper()
            neighbors[neighbor_symbol] = {
                "symbol": neighbor_symbol,
                "rank": rank,
                "correlation": float(row["correlation"]),
                "distance": float(row["distance"]),
            }

    returns_path = path / artifact_files.get("returns", "returns.csv")
    return _SnapshotView(
        label=_snapshot_label(metadata, path),
        path=path,
        metadata=metadata,
        neighbors=neighbors,
        returns=_read_period_returns(returns_path),
    )


def _load_neighbor_transitions(
    comparison_dir: str | Path | None,
    *,
    symbol: str,
) -> dict[tuple[str, str], dict[str, set[str]]]:
    if comparison_dir is None:
        return {}
    path = Path(comparison_dir) / "neighbor_changes.csv"
    if not path.exists():
        raise ValueError(f"Comparison neighbor_changes.csv does not exist: {path}")

    transitions: dict[tuple[str, str], dict[str, set[str]]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["symbol"].upper() != symbol:
                continue
            transitions[(row["from_snapshot"], row["to_snapshot"])] = {
                "stayed": _split_semicolon(row["stayed_neighbors"]),
                "entered": _split_semicolon(row["entered_neighbors"]),
                "exited": _split_semicolon(row["exited_neighbors"]),
            }
    return transitions


def _read_period_returns(path: Path) -> dict[str, float | None]:
    if not path.exists():
        return {}
    products: dict[str, float] = {}
    seen: set[str] = set()
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        symbols = [field for field in (reader.fieldnames or []) if field != "date"]
        for symbol in symbols:
            products[symbol.upper()] = 1.0
        for row in reader:
            for symbol in symbols:
                value = row.get(symbol, "")
                if value == "":
                    continue
                try:
                    products[symbol.upper()] *= 1.0 + float(value)
                except ValueError:
                    continue
                seen.add(symbol.upper())
    return {
        symbol: (products[symbol] - 1.0 if symbol in seen else None)
        for symbol in products
    }


def _render_ego_html(
    *,
    symbol: str,
    snapshots: list[_SnapshotView],
    transitions: dict[tuple[str, str], dict[str, set[str]]],
    top_k: int,
) -> str:
    panels = []
    for index, snapshot in enumerate(snapshots):
        previous = snapshots[index - 1] if index > 0 else None
        transition = (
            transitions.get((previous.label, snapshot.label))
            if previous is not None
            else None
        )
        panels.append(_render_panel(symbol=symbol, snapshot=snapshot, previous=previous, transition=transition))

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{html.escape(symbol)} Ego Network</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #111827; background: #f8fafc; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 24px; }}
    h1 {{ font-size: 24px; margin: 0 0 8px; }}
    p {{ color: #4b5563; line-height: 1.45; margin: 0 0 16px; }}
    .panel {{ margin: 18px 0; background: #ffffff; border: 1px solid #d1d5db; }}
    svg {{ width: 100%; height: auto; display: block; }}
    .status-baseline {{ stroke: #64748b; }}
    .status-current {{ stroke: #64748b; }}
    .status-stayed {{ stroke: #2563eb; }}
    .status-entered {{ stroke: #059669; }}
    .status-exited {{ stroke: #dc2626; stroke-dasharray: 7 5; }}
    .edge {{ stroke-width: 2.4; opacity: 0.72; }}
    .node {{ stroke: #111827; stroke-width: 1; opacity: 0.92; }}
    .center {{ fill: #111827; }}
    .label {{ font-size: 12px; fill: #111827; }}
    .muted {{ font-size: 11px; fill: #6b7280; }}
    .legend {{ display: flex; flex-wrap: wrap; gap: 12px; font-size: 13px; margin: 8px 0 18px; color: #374151; }}
    .swatch {{ display: inline-block; width: 22px; height: 3px; margin-right: 5px; vertical-align: middle; }}
  </style>
</head>
<body>
<main>
  <h1>{html.escape(symbol)} Ego Network</h1>
  <p>Static top-{top_k} ego network built from existing neighbors.csv outputs. Distance still means return-correlation distance only; period return is an overlay color.</p>
  <div class="legend">
    <span><span class="swatch" style="background:#2563eb"></span>stayed</span>
    <span><span class="swatch" style="background:#059669"></span>entered</span>
    <span><span class="swatch" style="background:#dc2626"></span>exited</span>
    <span><span class="swatch" style="background:#64748b"></span>baseline/current</span>
  </div>
  <p>current = present in this panel but not classified by the comparison file. Use the same top-k for ego and comparison outputs when possible.</p>
  {"".join(panels)}
</main>
</body>
</html>
"""


def _render_panel(
    *,
    symbol: str,
    snapshot: _SnapshotView,
    previous: _SnapshotView | None,
    transition: dict[str, set[str]] | None,
) -> str:
    width = 960
    height = 440
    center_x = width / 2
    center_y = height / 2
    radius = 150
    nodes = _panel_nodes(snapshot=snapshot, previous=previous, transition=transition)
    positioned = []
    count = max(len(nodes), 1)
    for index, node in enumerate(nodes):
        angle = -math.pi / 2 + (2 * math.pi * index / count)
        positioned.append(
            {
                **node,
                "x": center_x + radius * math.cos(angle),
                "y": center_y + radius * math.sin(angle),
            }
        )

    edges = []
    labels = []
    for node in positioned:
        status = html.escape(node["status"])
        edge_class = f"edge status-{status}"
        edges.append(
            f'<line class="{edge_class}" x1="{center_x:.2f}" y1="{center_y:.2f}" '
            f'x2="{node["x"]:.2f}" y2="{node["y"]:.2f}"><title>{_node_title(node)}</title></line>'
        )
        labels.append(_render_node(node))

    center_return = snapshot.returns.get(symbol.upper())
    title = html.escape(snapshot.label if previous is None else f"{previous.label} -> {snapshot.label}")
    center_title = html.escape(f"{symbol} | period return: {_format_return(center_return)}")
    empty_note = ""
    if not snapshot.neighbors:
        empty_note = (
            f'<text x="{center_x:.2f}" y="{center_y + 48:.2f}" '
            f'text-anchor="middle" class="muted">No top-k neighbors for '
            f"{html.escape(symbol)} in this snapshot.</text>"
        )
    return f"""<section class="panel">
  <svg viewBox="0 0 {width} {height}" role="img" aria-label="{html.escape(symbol)} ego network for {title}">
    <rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"></rect>
    <text x="24" y="34" font-size="18" font-weight="700" fill="#111827">{title}</text>
    <text x="24" y="54" class="muted">Node color = period return overlay. Edge color = top-k neighbor status.</text>
    {"".join(edges)}
    <circle class="node center" cx="{center_x:.2f}" cy="{center_y:.2f}" r="18"><title>{center_title}</title></circle>
    <text x="{center_x + 24:.2f}" y="{center_y + 4:.2f}" class="label">{html.escape(symbol)}</text>
    {empty_note}
    {"".join(labels)}
  </svg>
</section>
"""


def _panel_nodes(
    *,
    snapshot: _SnapshotView,
    previous: _SnapshotView | None,
    transition: dict[str, set[str]] | None,
) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    if transition is None:
        for neighbor in sorted(snapshot.neighbors.values(), key=lambda item: item["rank"]):
            nodes.append(_node_from_entry(neighbor, snapshot=snapshot, status="baseline"))
        return nodes

    for neighbor in sorted(snapshot.neighbors.values(), key=lambda item: item["rank"]):
        neighbor_symbol = neighbor["symbol"]
        status = "current"
        if neighbor_symbol in transition["stayed"]:
            status = "stayed"
        elif neighbor_symbol in transition["entered"]:
            status = "entered"
        nodes.append(_node_from_entry(neighbor, snapshot=snapshot, status=status))

    if previous is not None:
        for neighbor_symbol in sorted(transition["exited"]):
            previous_entry = previous.neighbors.get(neighbor_symbol)
            if previous_entry is None:
                nodes.append(
                    {
                        "symbol": neighbor_symbol,
                        "rank": "",
                        "correlation": "",
                        "distance": "",
                        "period_return": previous.returns.get(neighbor_symbol),
                        "status": "exited",
                    }
                )
            else:
                nodes.append(_node_from_entry(previous_entry, snapshot=previous, status="exited"))
    return nodes


def _node_from_entry(
    entry: dict[str, Any],
    *,
    snapshot: _SnapshotView,
    status: str,
) -> dict[str, Any]:
    return {
        "symbol": entry["symbol"],
        "rank": entry["rank"],
        "correlation": entry["correlation"],
        "distance": entry["distance"],
        "period_return": snapshot.returns.get(entry["symbol"]),
        "status": status,
    }


def _render_node(node: dict[str, Any]) -> str:
    symbol = html.escape(str(node["symbol"]))
    x = float(node["x"])
    y = float(node["y"])
    fill = _return_color(node["period_return"])
    title = _node_title(node)
    return (
        f'<g><circle class="node status-{html.escape(str(node["status"]))}" '
        f'cx="{x:.2f}" cy="{y:.2f}" r="12" fill="{fill}"><title>{title}</title></circle>'
        f'<text x="{x + 16:.2f}" y="{y + 4:.2f}" class="label">{symbol}</text></g>'
    )


def _node_title(node: dict[str, Any]) -> str:
    details = [
        str(node["symbol"]),
        f"status: {node['status']}",
        f"rank: {node['rank']}",
        f"correlation: {_format_number(node['correlation'])}",
        f"distance: {_format_number(node['distance'])}",
        f"period return: {_format_return(node['period_return'])}",
    ]
    return html.escape(" | ".join(details))


def _return_color(value: float | None) -> str:
    if value is None:
        return "#93c5fd"
    if value > 0:
        return "#34d399"
    if value < 0:
        return "#f87171"
    return "#d1d5db"


def _format_number(value: Any) -> str:
    if value == "":
        return "missing"
    try:
        return f"{float(value):.4f}"
    except (TypeError, ValueError):
        return str(value)


def _format_return(value: float | None) -> str:
    if value is None:
        return "missing"
    return f"{value:+.2%}"


def _snapshot_label(metadata: dict[str, Any], path: Path) -> str:
    period_start = metadata.get("period_start")
    period_end = metadata.get("period_end")
    if period_start and period_end:
        return f"{period_start}_to_{period_end}"
    return path.name


def _split_semicolon(value: str) -> set[str]:
    return {item.strip().upper() for item in value.split(";") if item.strip()}
