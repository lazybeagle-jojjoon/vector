from __future__ import annotations

import csv
import html
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class GlobalMapOutputPaths:
    metadata_path: Path
    layout_path: Path
    edges_path: Path
    html_path: Path


_NODE_FIELDS = [
    "security_id",
    "symbol",
    "x",
    "y",
    "period_return",
    "name",
    "type",
    "sector",
    "industry",
    "primary_sector",
    "volatility",
    "avg_volume",
    "avg_turnover",
    "market_cap",
    "market_cap_change",
    "community_id",
]

_EDGE_FIELDS = [
    "source_symbol",
    "target_symbol",
    "source_security_id",
    "target_security_id",
    "rank",
    "correlation",
    "distance",
]


def write_global_map_view(
    snapshot_dir: str | Path,
    *,
    output_dir: str | Path,
    node_metadata_path: str | Path | None = None,
    top_k: int = 10,
    seed: int = 42,
    iterations: int = 80,
) -> GlobalMapOutputPaths:
    if top_k < 1:
        raise ValueError("top_k must be at least 1.")
    if iterations < 0:
        raise ValueError("iterations must be non-negative.")

    snapshot_path = Path(snapshot_dir)
    metadata = _read_snapshot_metadata(snapshot_path)
    artifact_files = metadata.get("artifact_files", {})
    universe_path = snapshot_path / artifact_files.get("universe", "universe.csv")
    neighbors_path = snapshot_path / artifact_files.get("neighbors", "neighbors.csv")
    returns_path = snapshot_path / artifact_files.get("returns", "returns.csv")

    universe = _read_universe(universe_path)
    if not universe:
        raise ValueError(f"Snapshot universe CSV has no rows: {universe_path}")
    returns = _read_period_returns(returns_path)
    metadata_by_symbol = _read_node_metadata(Path(node_metadata_path)) if node_metadata_path else {}
    edges = _read_edges(neighbors_path, universe=universe, top_k=top_k)
    positions = _deterministic_layout(
        symbols=[row["symbol"] for row in universe],
        edges=edges,
        seed=seed,
        iterations=iterations,
    )
    nodes = _build_nodes(
        universe=universe,
        positions=positions,
        returns=returns,
        metadata_by_symbol=metadata_by_symbol,
    )

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    metadata_path = output_path / "global_map_metadata.json"
    layout_path = output_path / "global_layout.csv"
    edges_path = output_path / "global_edges.csv"
    html_path = output_path / "global_map.html"

    global_metadata = {
        "artifact_files": {
            "metadata": metadata_path.name,
            "layout": layout_path.name,
            "edges": edges_path.name,
            "html": html_path.name,
        },
        "source_snapshot": str(snapshot_path),
        "period_start": metadata.get("period_start"),
        "period_end": metadata.get("period_end"),
        "relationship": "return_correlation_distance",
        "projection": "fixed_global_relationship_layout",
        "layout_algorithm": "seeded_force_layout_v2",
        "layout_seed": seed,
        "layout_iterations": iterations,
        "layout_quality": _layout_quality(positions),
        "top_k": top_k,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "position_note": (
            "Node positions are a fixed reference frame. They do not mean time movement; "
            "compare edges, colors, and tooltips only."
        ),
        "overlay_note": (
            "Distance means return-correlation distance only. Returns, sector, volume, "
            "volatility, and market cap are nullable overlays."
        ),
    }
    metadata_path.write_text(
        json.dumps(global_metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_csv(layout_path, _NODE_FIELDS, nodes)
    _write_csv(edges_path, _EDGE_FIELDS, edges)
    html_path.write_text(
        _render_html(nodes=nodes, edges=edges, metadata=global_metadata),
        encoding="utf-8",
    )

    return GlobalMapOutputPaths(
        metadata_path=metadata_path,
        layout_path=layout_path,
        edges_path=edges_path,
        html_path=html_path,
    )


def _read_snapshot_metadata(snapshot_path: Path) -> dict[str, Any]:
    metadata_path = snapshot_path / "metadata.json"
    if not metadata_path.exists():
        raise ValueError(f"Snapshot metadata does not exist: {metadata_path}")
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def _read_universe(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise ValueError(f"Snapshot universe CSV does not exist: {path}")
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            symbol = row.get("symbol", "").strip().upper()
            security_id = row.get("security_id", "").strip()
            if not symbol:
                continue
            if symbol in seen:
                raise ValueError(f"duplicate symbol in snapshot universe: {symbol}")
            seen.add(symbol)
            rows.append({"security_id": security_id, "symbol": symbol})
    return sorted(rows, key=lambda item: item["symbol"])


def _read_edges(
    path: Path,
    *,
    universe: list[dict[str, str]],
    top_k: int,
) -> list[dict[str, Any]]:
    if not path.exists():
        raise ValueError(f"Snapshot neighbors CSV does not exist: {path}")
    valid_symbols = {row["symbol"] for row in universe}
    edges: list[dict[str, Any]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rank = int(row["rank"])
            if rank > top_k:
                continue
            source = row["symbol"].strip().upper()
            target = row["neighbor_symbol"].strip().upper()
            if source not in valid_symbols or target not in valid_symbols:
                continue
            edges.append(
                {
                    "source_symbol": source,
                    "target_symbol": target,
                    "source_security_id": row.get("security_id", ""),
                    "target_security_id": row.get("neighbor_security_id", ""),
                    "rank": rank,
                    "correlation": float(row["correlation"]),
                    "distance": float(row["distance"]),
                }
            )
    return sorted(edges, key=lambda item: (item["source_symbol"], item["rank"], item["target_symbol"]))


def _read_node_metadata(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        raise ValueError(f"Node metadata CSV does not exist: {path}")
    metadata: dict[str, dict[str, str]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            symbol = row.get("symbol", row.get("ticker", "")).strip().upper()
            if symbol:
                metadata[symbol] = row
    return metadata


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


def _build_nodes(
    *,
    universe: list[dict[str, str]],
    positions: dict[str, tuple[float, float]],
    returns: dict[str, float | None],
    metadata_by_symbol: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for row in universe:
        symbol = row["symbol"]
        security_id = row["security_id"]
        node_metadata = metadata_by_symbol.get(symbol, {})
        x, y = positions[symbol]
        period_return = returns.get(symbol)
        if period_return is None:
            period_return = returns.get(security_id.upper())
        nodes.append(
            {
                "security_id": security_id,
                "symbol": symbol,
                "x": f"{x:.8f}",
                "y": f"{y:.8f}",
                "period_return": _optional_float(period_return),
                "name": _metadata_value(node_metadata, "name"),
                "type": _metadata_value(node_metadata, "type"),
                "sector": _metadata_value(node_metadata, "sector", "eodhd_sector"),
                "industry": _metadata_value(node_metadata, "industry", "eodhd_industry"),
                "primary_sector": _metadata_value(node_metadata, "primary_sector"),
                "volatility": _metadata_value(node_metadata, "volatility"),
                "avg_volume": _metadata_value(node_metadata, "avg_volume", "volume"),
                "avg_turnover": _metadata_value(node_metadata, "avg_turnover", "avg_turnover_1y"),
                "market_cap": _metadata_value(node_metadata, "market_cap"),
                "market_cap_change": _metadata_value(node_metadata, "market_cap_change"),
                "community_id": _metadata_value(node_metadata, "community_id"),
            }
        )
    return nodes


def _deterministic_layout(
    *,
    symbols: list[str],
    edges: list[dict[str, Any]],
    seed: int,
    iterations: int,
) -> dict[str, tuple[float, float]]:
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        raise ValueError(
            "global map layout requires numpy. Run with: "
            "uv run --no-project --with numpy python -m vector_relations.global_map_cli ..."
        ) from exc

    if not symbols:
        return {}
    if len(symbols) == 1:
        return {symbols[0]: (0.0, 0.0)}

    index_by_symbol = {symbol: index for index, symbol in enumerate(symbols)}
    rng = np.random.default_rng(seed)
    node_count = len(symbols)
    anchors = rng.normal(0.0, 1.0, size=(node_count, 2))
    anchors = _normalize_positions(np, anchors)
    positions = anchors.copy()

    weighted_edges: list[tuple[int, int, float, float]] = []
    for edge in edges:
        source = index_by_symbol.get(str(edge["source_symbol"]))
        target = index_by_symbol.get(str(edge["target_symbol"]))
        if source is None or target is None or source == target:
            continue
        correlation = float(edge["correlation"])
        weight = max(0.01, min(1.0, correlation))
        desired_distance = 0.10 + (1.0 - weight) * 0.45
        weighted_edges.append((source, target, weight, desired_distance))

    if weighted_edges:
        sources = np.array([edge[0] for edge in weighted_edges], dtype=int)
        targets = np.array([edge[1] for edge in weighted_edges], dtype=int)
        weights = np.array([edge[2] for edge in weighted_edges], dtype=float)
        desired = np.array([edge[3] for edge in weighted_edges], dtype=float)
    else:
        sources = np.array([], dtype=int)
        targets = np.array([], dtype=int)
        weights = np.array([], dtype=float)
        desired = np.array([], dtype=float)

    for _ in range(iterations):
        accum = np.zeros_like(positions)
        if len(sources):
            deltas = positions[targets] - positions[sources]
            distances = np.linalg.norm(deltas, axis=1) + 1e-6
            units = deltas / distances[:, None]
            spring = ((distances - desired) * weights * 0.028)[:, None] * units
            np.add.at(accum, sources, spring)
            np.add.at(accum, targets, -spring)

        sample_count = min(8, max(1, node_count - 1))
        base = np.repeat(np.arange(node_count), sample_count)
        sampled = rng.integers(0, node_count, size=node_count * sample_count)
        mask = base != sampled
        base = base[mask]
        sampled = sampled[mask]
        repulsion_delta = positions[base] - positions[sampled]
        repulsion_distance_sq = np.sum(repulsion_delta * repulsion_delta, axis=1) + 0.015
        repulsion = (repulsion_delta / repulsion_distance_sq[:, None]) * 0.0018
        np.add.at(accum, base, repulsion)

        accum += (anchors - positions) * 0.020
        accum += -positions * 0.004
        positions = positions + accum
        positions = _normalize_positions(np, positions)

    return {
        symbol: (float(positions[index, 0]), float(positions[index, 1]))
        for symbol, index in index_by_symbol.items()
    }


def _normalize_positions(np: Any, positions: Any) -> Any:
    centered = positions - positions.mean(axis=0, keepdims=True)
    radii = np.linalg.norm(centered, axis=1)
    scale = float(np.quantile(radii, 0.99))
    if scale == 0:
        scale = float(np.max(radii))
    if scale == 0:
        return centered
    return np.tanh((centered / scale) * 1.15)


def _layout_quality(positions: dict[str, tuple[float, float]]) -> dict[str, float | int]:
    if not positions:
        return {
            "radius_p90": 0.0,
            "radius_p95": 0.0,
            "occupied20x20_cells": 0,
        }
    radii = sorted((x * x + y * y) ** 0.5 for x, y in positions.values())
    occupied: set[tuple[int, int]] = set()
    for x, y in positions.values():
        gx = max(0, min(19, int(((x + 1.0) / 2.0) * 20)))
        gy = max(0, min(19, int(((y + 1.0) / 2.0) * 20)))
        occupied.add((gx, gy))

    def quantile(value: float) -> float:
        index = min(len(radii) - 1, int(value * (len(radii) - 1)))
        return radii[index]

    return {
        "radius_p90": quantile(0.90),
        "radius_p95": quantile(0.95),
        "occupied20x20_cells": len(occupied),
    }


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _render_html(
    *,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> str:
    nodes_json = _json_for_script(nodes)
    edges_json = _json_for_script(edges)
    metadata_json = _json_for_script(metadata)
    title = _period_title(metadata)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Global Relationship Map</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #111827; background: #f8fafc; }}
    main {{ max-width: 1240px; margin: 0 auto; padding: 20px; }}
    h1 {{ font-size: 24px; margin: 0 0 6px; }}
    p {{ color: #4b5563; line-height: 1.45; margin: 0 0 10px; }}
    #mapWrap {{ position: relative; border: 1px solid #cbd5e1; background: #ffffff; }}
    canvas {{ width: 100%; height: min(78vh, 760px); display: block; }}
    #tooltip {{ position: absolute; pointer-events: none; display: none; max-width: 320px; padding: 8px 10px; border: 1px solid #94a3b8; background: rgba(255, 255, 255, 0.96); color: #111827; font-size: 12px; line-height: 1.35; box-shadow: 0 8px 24px rgba(15, 23, 42, 0.16); }}
    .legend {{ display: flex; flex-wrap: wrap; gap: 14px; color: #374151; font-size: 13px; margin: 10px 0 14px; }}
    .dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 5px; vertical-align: -1px; }}
    code {{ background: #e5e7eb; padding: 1px 4px; }}
  </style>
</head>
<body>
<main>
  <h1>Global Relationship Map</h1>
  <p>{html.escape(title)}</p>
  <p><strong>Node positions are a fixed reference frame.</strong> They do not mean time movement. Distance means return-correlation distance only; return, sector, industry, volume, volatility, and market cap are overlays.</p>
  <div class="legend">
    <span><span class="dot" style="background:#059669"></span>positive period return</span>
    <span><span class="dot" style="background:#dc2626"></span>negative period return</span>
    <span><span class="dot" style="background:#2563eb"></span>missing return</span>
    <span>lines = saved top-k neighbors</span>
  </div>
  <div id="mapWrap">
    <canvas id="map" width="1180" height="760" aria-label="Global relationship map canvas"></canvas>
    <div id="tooltip"></div>
  </div>
</main>
<script>
const nodes = {nodes_json};
const edges = {edges_json};
const metadata = {metadata_json};

const canvas = document.getElementById("map");
const tooltip = document.getElementById("tooltip");
const ctx = canvas.getContext("2d");
const nodeBySymbol = new Map(nodes.map((node) => [node.symbol, node]));
const padding = 36;

function resizeCanvas() {{
  const ratio = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = Math.max(1, Math.floor(rect.width * ratio));
  canvas.height = Math.max(1, Math.floor(rect.height * ratio));
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  draw();
}}

function project(node) {{
  const rect = canvas.getBoundingClientRect();
  const width = rect.width;
  const height = rect.height;
  return {{
    x: padding + ((Number(node.x) + 1) / 2) * (width - padding * 2),
    y: padding + ((1 - (Number(node.y) + 1) / 2)) * (height - padding * 2),
  }};
}}

function returnColor(value) {{
  if (value === "" || value === null || value === undefined) return "#2563eb";
  const number = Number(value);
  if (!Number.isFinite(number)) return "#2563eb";
  if (number > 0) return "#059669";
  if (number < 0) return "#dc2626";
  return "#6b7280";
}}

function edgeAlpha(edge) {{
  const corr = Number(edge.correlation);
  if (!Number.isFinite(corr)) return 0.015;
  return Math.max(0.012, Math.min(0.085, 0.012 + corr * 0.052));
}}

function draw() {{
  const rect = canvas.getBoundingClientRect();
  ctx.clearRect(0, 0, rect.width, rect.height);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, rect.width, rect.height);

  for (const edge of edges) {{
    const source = nodeBySymbol.get(edge.source_symbol);
    const target = nodeBySymbol.get(edge.target_symbol);
    if (!source || !target) continue;
    const a = project(source);
    const b = project(target);
    ctx.beginPath();
    ctx.moveTo(a.x, a.y);
    ctx.lineTo(b.x, b.y);
    ctx.strokeStyle = `rgba(71, 85, 105, ${{edgeAlpha(edge)}})`;
    ctx.lineWidth = 0.45;
    ctx.stroke();
  }}

  for (const node of nodes) {{
    const p = project(node);
    ctx.beginPath();
    ctx.arc(p.x, p.y, 2.9, 0, Math.PI * 2);
    ctx.fillStyle = returnColor(node.period_return);
    ctx.globalAlpha = 0.86;
    ctx.fill();
  }}
  ctx.globalAlpha = 1;
}}

function formatPercent(value) {{
  if (value === "" || value === null || value === undefined) return "missing";
  const number = Number(value);
  if (!Number.isFinite(number)) return "missing";
  return `${{number >= 0 ? "+" : ""}}${{(number * 100).toFixed(2)}}%`;
}}

function nodeTitle(node) {{
  return [
    `<strong>${{escapeHtml(node.symbol)}}</strong>${{node.name ? " | " + escapeHtml(node.name) : ""}}`,
    `return: ${{formatPercent(node.period_return)}}`,
    `sector: ${{escapeHtml(node.sector || node.primary_sector || "missing")}}`,
    `industry: ${{escapeHtml(node.industry || "missing")}}`,
    `avg_turnover: ${{escapeHtml(node.avg_turnover || "missing")}}`,
    `market_cap: ${{escapeHtml(node.market_cap || "missing")}}`,
  ].join("<br>");
}}

function escapeHtml(value) {{
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}}

canvas.addEventListener("mousemove", (event) => {{
  const rect = canvas.getBoundingClientRect();
  const x = event.clientX - rect.left;
  const y = event.clientY - rect.top;
  let best = null;
  let bestDistance = 9;
  for (const node of nodes) {{
    const p = project(node);
    const distance = Math.hypot(p.x - x, p.y - y);
    if (distance < bestDistance) {{
      best = node;
      bestDistance = distance;
    }}
  }}
  if (!best) {{
    tooltip.style.display = "none";
    return;
  }}
  tooltip.innerHTML = nodeTitle(best);
  tooltip.style.display = "block";
  tooltip.style.left = `${{Math.min(x + 14, rect.width - 340)}}px`;
  tooltip.style.top = `${{Math.min(y + 14, rect.height - 130)}}px`;
}});

canvas.addEventListener("mouseleave", () => {{
  tooltip.style.display = "none";
}});

window.addEventListener("resize", resizeCanvas);
resizeCanvas();
</script>
</body>
</html>
"""


def _metadata_value(row: dict[str, str], *names: str) -> str:
    for name in names:
        value = row.get(name, "")
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _optional_float(value: float | None) -> str:
    if value is None:
        return ""
    return str(value)


def _json_for_script(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def _period_title(metadata: dict[str, Any]) -> str:
    start = metadata.get("period_start")
    end = metadata.get("period_end")
    if start and end:
        return f"{start} to {end}"
    return "single snapshot"
