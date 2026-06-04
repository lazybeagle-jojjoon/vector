from __future__ import annotations

import csv
import html
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .global_map import (
    _EDGE_FIELDS,
    _NODE_FIELDS,
    _filter_value,
    _json_for_script,
    _read_edges,
    _read_period_returns,
    _read_snapshot_metadata,
    _read_universe,
    _safe_float,
    _write_csv,
)


@dataclass(frozen=True)
class GlobalTimelineOutputPaths:
    metadata_path: Path
    nodes_path: Path
    edges_path: Path
    frames_path: Path
    html_path: Path


_TIMELINE_EDGE_FIELDS = [
    "frame_index",
    "frame_label",
    *_EDGE_FIELDS,
]


def write_global_timeline_view(
    reference_map_dir: str | Path,
    snapshot_dirs: list[str | Path] | tuple[str | Path, ...],
    *,
    output_dir: str | Path,
    top_k: int = 10,
) -> GlobalTimelineOutputPaths:
    if top_k < 1:
        raise ValueError("top_k must be at least 1.")
    if not snapshot_dirs:
        raise ValueError("at least one snapshot directory is required.")

    reference_path = Path(reference_map_dir)
    reference_metadata = _read_reference_map_metadata(reference_path)
    reference_layout_path = _reference_layout_path(reference_path, metadata=reference_metadata)
    reference_period_label = _reference_period_label(reference_metadata)
    reference_nodes = _read_reference_nodes(reference_layout_path)
    if not reference_nodes:
        raise ValueError(f"Reference layout has no nodes: {reference_layout_path}")
    reference_symbols = {row["symbol"] for row in reference_nodes}

    frames: list[dict[str, Any]] = []
    edge_rows: list[dict[str, Any]] = []
    for frame_index, snapshot_dir in enumerate(snapshot_dirs):
        frame = _read_timeline_frame(
            frame_index=frame_index,
            snapshot_dir=Path(snapshot_dir),
            reference_symbols=reference_symbols,
            top_k=top_k,
        )
        frames.append(frame)
        for edge in frame["edges"]:
            edge_rows.append(
                {
                    "frame_index": frame_index,
                    "frame_label": frame["frame_label"],
                    **edge,
                }
            )

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    metadata_path = output_path / "global_timeline_metadata.json"
    nodes_path = output_path / "global_timeline_nodes.csv"
    edges_path = output_path / "global_timeline_edges.csv"
    frames_path = output_path / "global_timeline_frames.json"
    html_path = output_path / "global_timeline.html"

    timeline_metadata = {
        "artifact_files": {
            "metadata": metadata_path.name,
            "nodes": nodes_path.name,
            "edges": edges_path.name,
            "frames": frames_path.name,
            "html": html_path.name,
        },
        "reference_map": str(reference_path),
        "reference_layout": str(reference_layout_path),
        "reference_period_start": reference_metadata.get("period_start"),
        "reference_period_end": reference_metadata.get("period_end"),
        "reference_period_label": reference_period_label,
        "projection": "fixed_global_timeline_small_multiples",
        "relationship": "return_correlation_distance",
        "node_set": "reference_layout",
        "top_k": top_k,
        "node_count": len(reference_nodes),
        "frame_count": len(frames),
        "frames": [_frame_summary(frame) for frame in frames],
        "position_note": (
            f"Node positions reuse one fixed reference layout ({reference_period_label}) and "
            "do not mean time movement. Compare frame edges, colors, and tooltips only."
        ),
        "missing_node_policy": (
            "Each frame keeps the reference node set. Nodes missing from a frame remain at "
            "their fixed position with a neutral missing style and no edges."
        ),
        "overlay_note": (
            "Distance means return-correlation distance only. Period return changes node "
            "color per frame; sector, industry, and market cap remain nullable overlays."
        ),
        "filter_controls": _filter_control_metadata(reference_nodes, frames),
    }
    frame_data = {
        "metadata": {
            "projection": timeline_metadata["projection"],
            "node_set": timeline_metadata["node_set"],
            "position_note": timeline_metadata["position_note"],
        },
        "frames": frames,
    }

    metadata_path.write_text(
        json.dumps(timeline_metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    frames_path.write_text(
        json.dumps(frame_data, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    _write_csv(nodes_path, _NODE_FIELDS, reference_nodes)
    _write_csv(edges_path, _TIMELINE_EDGE_FIELDS, edge_rows)
    html_path.write_text(
        _render_html(nodes=reference_nodes, frame_data=frame_data, metadata=timeline_metadata),
        encoding="utf-8",
    )

    return GlobalTimelineOutputPaths(
        metadata_path=metadata_path,
        nodes_path=nodes_path,
        edges_path=edges_path,
        frames_path=frames_path,
        html_path=html_path,
    )


def _read_reference_map_metadata(reference_path: Path) -> dict[str, Any]:
    metadata_path = reference_path / "global_map_metadata.json"
    if metadata_path.exists():
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    return {}


def _reference_layout_path(reference_path: Path, *, metadata: dict[str, Any]) -> Path:
    layout_name = metadata.get("artifact_files", {}).get("layout", "global_layout.csv")
    layout_path = reference_path / layout_name
    if not layout_path.exists():
        raise ValueError(f"Reference global layout CSV does not exist: {layout_path}")
    return layout_path


def _reference_period_label(metadata: dict[str, Any]) -> str:
    start = metadata.get("period_start")
    end = metadata.get("period_end")
    if start and end:
        return f"{start} to {end}"
    return "reference map"


def _read_reference_nodes(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            symbol = str(row.get("symbol") or "").strip().upper()
            if not symbol:
                continue
            if symbol in seen:
                raise ValueError(f"duplicate symbol in reference layout: {symbol}")
            x = str(row.get("x") or "").strip()
            y = str(row.get("y") or "").strip()
            if not x or not y:
                raise ValueError(f"reference layout row is missing x/y for symbol: {symbol}")
            seen.add(symbol)
            normalized = {field: str(row.get(field) or "").strip() for field in _NODE_FIELDS}
            normalized["symbol"] = symbol
            normalized["x"] = x
            normalized["y"] = y
            rows.append(normalized)
    return sorted(rows, key=lambda item: item["symbol"])


def _read_timeline_frame(
    *,
    frame_index: int,
    snapshot_dir: Path,
    reference_symbols: set[str],
    top_k: int,
) -> dict[str, Any]:
    metadata = _read_snapshot_metadata(snapshot_dir)
    artifact_files = metadata.get("artifact_files", {})
    universe_path = snapshot_dir / artifact_files.get("universe", "universe.csv")
    neighbors_path = snapshot_dir / artifact_files.get("neighbors", "neighbors.csv")
    returns_path = snapshot_dir / artifact_files.get("returns", "returns.csv")

    universe = _read_universe(universe_path)
    present_symbols = {row["symbol"] for row in universe} & reference_symbols
    returns = {
        symbol: value
        for symbol, value in _read_period_returns(returns_path).items()
        if symbol in present_symbols and value is not None
    }
    edges = [
        edge
        for edge in _read_edges(neighbors_path, universe=universe, top_k=top_k)
        if edge["source_symbol"] in reference_symbols
        and edge["target_symbol"] in reference_symbols
        and edge["source_symbol"] in present_symbols
        and edge["target_symbol"] in present_symbols
    ]
    label = _frame_label(metadata, fallback=f"frame {frame_index + 1}")
    return {
        "frame_index": frame_index,
        "frame_label": label,
        "period_start": metadata.get("period_start"),
        "period_end": metadata.get("period_end"),
        "source_snapshot": str(snapshot_dir),
        "present_symbols": sorted(present_symbols),
        "returns": {symbol: returns[symbol] for symbol in sorted(returns)},
        "edges": sorted(edges, key=lambda item: (item["source_symbol"], item["rank"], item["target_symbol"])),
        "present_node_count": len(present_symbols),
        "missing_node_count": len(reference_symbols) - len(present_symbols),
        "ignored_snapshot_node_count": len({row["symbol"] for row in universe} - reference_symbols),
    }


def _frame_label(metadata: dict[str, Any], *, fallback: str) -> str:
    start = metadata.get("period_start")
    end = metadata.get("period_end")
    if start and end:
        return f"{start} to {end}"
    return fallback


def _frame_summary(frame: dict[str, Any]) -> dict[str, Any]:
    return {
        "frame_index": frame["frame_index"],
        "frame_label": frame["frame_label"],
        "period_start": frame["period_start"],
        "period_end": frame["period_end"],
        "source_snapshot": frame["source_snapshot"],
        "present_node_count": frame["present_node_count"],
        "missing_node_count": frame["missing_node_count"],
        "ignored_snapshot_node_count": frame["ignored_snapshot_node_count"],
        "edge_count": len(frame["edges"]),
    }


def _filter_control_metadata(nodes: list[dict[str, Any]], frames: list[dict[str, Any]]) -> dict[str, Any]:
    sectors = {_filter_value(node.get("sector") or node.get("primary_sector")) for node in nodes}
    industries = {_filter_value(node.get("industry")) for node in nodes}
    correlations = [
        float(edge["correlation"])
        for frame in frames
        for edge in frame["edges"]
        if _safe_float(edge.get("correlation")) is not None
    ]
    return {
        "sector_count": len(sectors),
        "industry_count": len(industries),
        "edge_threshold_control": "correlation_minimum",
        "edge_correlation_min": min(correlations) if correlations else None,
        "edge_correlation_max": max(correlations) if correlations else None,
        "note": (
            "Sector and industry are filter lenses only; they are not cluster labels "
            "and do not change relationship distance."
        ),
    }


def _render_html(
    *,
    nodes: list[dict[str, Any]],
    frame_data: dict[str, Any],
    metadata: dict[str, Any],
) -> str:
    nodes_json = _json_for_script(nodes)
    frame_data_json = _json_for_script(frame_data)
    metadata_json = _json_for_script(metadata)
    title = f"{len(frame_data['frames'])} frames on one fixed layout"
    reference_period = str(metadata.get("reference_period_label") or "reference map")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Global Relationship Timeline</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #111827; background: #f8fafc; }}
    main {{ max-width: 1440px; margin: 0 auto; padding: 20px; }}
    h1 {{ font-size: 24px; margin: 0 0 6px; }}
    p {{ color: #4b5563; line-height: 1.45; margin: 0 0 10px; }}
    #timelineWrap {{ position: relative; border: 1px solid #cbd5e1; background: #ffffff; }}
    canvas {{ width: 100%; height: min(84vh, 900px); display: block; }}
    #tooltip {{ position: absolute; pointer-events: none; display: none; max-width: 340px; padding: 8px 10px; border: 1px solid #94a3b8; background: rgba(255, 255, 255, 0.96); color: #111827; font-size: 12px; line-height: 1.35; box-shadow: 0 8px 24px rgba(15, 23, 42, 0.16); }}
    .legend {{ display: flex; flex-wrap: wrap; gap: 14px; color: #374151; font-size: 13px; margin: 10px 0 14px; }}
    .controls {{ display: grid; grid-template-columns: repeat(3, minmax(180px, 1fr)); gap: 10px; align-items: end; margin: 12px 0 14px; padding: 10px; border: 1px solid #d1d5db; background: #f9fafb; }}
    .controls label {{ display: grid; gap: 4px; color: #374151; font-size: 12px; font-weight: 600; }}
    .controls select, .controls input {{ min-width: 0; padding: 7px 8px; border: 1px solid #9ca3af; background: #fff; color: #111827; font: inherit; }}
    #filterStats {{ color: #4b5563; font-size: 12px; grid-column: 1 / -1; }}
    .dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 5px; vertical-align: -1px; }}
    @media (max-width: 760px) {{ .controls {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
<main>
  <h1>Global Relationship Timeline</h1>
  <p>{html.escape(title)}</p>
  <p><strong>Each panel uses the same fixed reference layout.</strong> Node positions do not move and do not mean time movement. Compare the edges, return colors, and tooltips inside each frame.</p>
  <p><strong>Reference frame: {html.escape(reference_period)}.</strong> Other periods are overlays on this same frame, so older panels can look messier when their relationships differ from the reference period.</p>
  <p><strong>Missing nodes stay visible.</strong> A node missing in this frame is drawn as a neutral outline at its fixed position with no frame edges.</p>
  <div class="legend">
    <span><span class="dot" style="background:#059669"></span>positive period return</span>
    <span><span class="dot" style="background:#dc2626"></span>negative period return</span>
    <span><span class="dot" style="background:#2563eb"></span>missing return</span>
    <span><span class="dot" style="background:#cbd5e1"></span>missing in this frame</span>
    <span>node size = log current market cap when available</span>
    <span>lines = saved top-k neighbors for that frame</span>
  </div>
  <div class="controls" aria-label="Filter/focus controls">
    <label>Sector filter
      <select id="sectorFilter" aria-label="Sector filter"></select>
    </label>
    <label>Industry filter
      <select id="industryFilter" aria-label="Industry filter"></select>
    </label>
    <label>Minimum edge correlation
      <input id="edgeThreshold" type="range" min="-1" max="1" step="0.01" value="-1" aria-label="Minimum edge correlation">
    </label>
    <div id="filterStats">Filter/focus controls are filter only; not cluster labels.</div>
  </div>
  <div id="timelineWrap">
    <canvas id="timeline" width="1360" height="900" aria-label="Global relationship timeline canvas"></canvas>
    <div id="tooltip"></div>
  </div>
</main>
<script>
const nodes = {nodes_json};
const timelineData = {frame_data_json};
const metadata = {metadata_json};
const frames = timelineData.frames;

const canvas = document.getElementById("timeline");
const tooltip = document.getElementById("tooltip");
const sectorFilter = document.getElementById("sectorFilter");
const industryFilter = document.getElementById("industryFilter");
const edgeThreshold = document.getElementById("edgeThreshold");
const filterStats = document.getElementById("filterStats");
const ctx = canvas.getContext("2d");
const nodeBySymbol = new Map(nodes.map((node) => [node.symbol, node]));
const frameState = frames.map((frame) => ({{
  ...frame,
  present: new Set(frame.present_symbols || []),
  returnsMap: new Map(Object.entries(frame.returns || {{}})),
}}));
const marketCapLogs = nodes
  .map((node) => marketCapNumber(node))
  .filter((value) => Number.isFinite(value) && value > 0)
  .map((value) => Math.log10(value))
  .sort((a, b) => a - b);
const minMarketCapLog = marketCapLogs.length ? marketCapLogs[0] : 0;
const maxMarketCapLog = marketCapLogs.length ? marketCapLogs[marketCapLogs.length - 1] : 0;
const padding = 30;
const titleHeight = 28;
let selectedSector = "all";
let selectedIndustry = "all";
let minEdgeCorrelation = -1;

function filterValue(value) {{
  const text = String(value || "").trim();
  return text || "missing";
}}

function uniqueValues(values) {{
  return Array.from(new Set(values.map(filterValue))).sort((a, b) => a.localeCompare(b));
}}

function populateSelect(select, values, label) {{
  select.innerHTML = "";
  const allOption = document.createElement("option");
  allOption.value = "all";
  allOption.textContent = `All ${{label}}`;
  select.appendChild(allOption);
  for (const value of values) {{
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  }}
}}

populateSelect(sectorFilter, uniqueValues(nodes.map((node) => node.sector || node.primary_sector)), "sectors");
populateSelect(industryFilter, uniqueValues(nodes.map((node) => node.industry)), "industries");

function resizeCanvas() {{
  const ratio = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = Math.max(1, Math.floor(rect.width * ratio));
  canvas.height = Math.max(1, Math.floor(rect.height * ratio));
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  draw();
}}

function panelRect(frameIndex) {{
  const rect = canvas.getBoundingClientRect();
  const frameCount = Math.max(1, frames.length);
  const gap = 12;
  const panelWidth = (rect.width - gap * (frameCount - 1)) / frameCount;
  return {{
    x: frameIndex * (panelWidth + gap),
    y: 0,
    width: panelWidth,
    height: rect.height,
  }};
}}

function project(node, frameIndex) {{
  const panel = panelRect(frameIndex);
  const width = panel.width;
  const height = panel.height - titleHeight;
  return {{
    x: panel.x + padding + ((Number(node.x) + 1) / 2) * (width - padding * 2),
    y: panel.y + titleHeight + padding + ((1 - (Number(node.y) + 1) / 2)) * (height - padding * 2),
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

function marketCapNumber(node) {{
  if (!node || node.market_cap === "" || node.market_cap === null || node.market_cap === undefined) return NaN;
  const value = Number(node.market_cap);
  return Number.isFinite(value) && value > 0 ? value : NaN;
}}

function marketCapRadius(node) {{
  const value = marketCapNumber(node);
  if (!Number.isFinite(value) || maxMarketCapLog <= minMarketCapLog) return 2.8;
  const scaled = (Math.log10(value) - minMarketCapLog) / (maxMarketCapLog - minMarketCapLog);
  return 2.2 + Math.sqrt(Math.max(0, Math.min(1, scaled))) * 5.4;
}}

function hasPositiveMarketCap(node) {{
  return node.market_cap_status === "positive" && Number.isFinite(marketCapNumber(node));
}}

function passesNodeFilters(node) {{
  const sector = filterValue(node.sector || node.primary_sector);
  const industry = filterValue(node.industry);
  return (selectedSector === "all" || sector === selectedSector)
    && (selectedIndustry === "all" || industry === selectedIndustry);
}}

function passesEdgeThreshold(edge) {{
  const corr = Number(edge.correlation);
  return Number.isFinite(corr) && corr >= minEdgeCorrelation;
}}

function visibleNodeSymbols() {{
  return new Set(nodes.filter(passesNodeFilters).map((node) => node.symbol));
}}

function updateFilterStats(visibleSymbols, visibleEdgeCount) {{
  filterStats.textContent = `Filter/focus controls are filter only; not cluster labels. Showing ${{visibleSymbols.size}}/${{nodes.length}} reference nodes per frame and ${{visibleEdgeCount}} frame edges. Minimum edge correlation: ${{minEdgeCorrelation.toFixed(2)}}.`;
}}

function draw() {{
  const rect = canvas.getBoundingClientRect();
  const visibleSymbols = visibleNodeSymbols();
  let visibleEdgeCount = 0;
  ctx.clearRect(0, 0, rect.width, rect.height);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, rect.width, rect.height);

  frameState.forEach((frame, frameIndex) => {{
    const panel = panelRect(frameIndex);
    ctx.fillStyle = "#f8fafc";
    ctx.fillRect(panel.x, 0, panel.width, rect.height);
    ctx.strokeStyle = "#e2e8f0";
    ctx.lineWidth = 1;
    ctx.strokeRect(panel.x + 0.5, 0.5, panel.width - 1, rect.height - 1);
    ctx.fillStyle = "#111827";
    ctx.font = "600 13px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
    ctx.fillText(frame.frame_label, panel.x + 12, 19);

    for (const edge of frame.edges || []) {{
      if (!passesEdgeThreshold(edge)) continue;
      const source = nodeBySymbol.get(edge.source_symbol);
      const target = nodeBySymbol.get(edge.target_symbol);
      if (!source || !target) continue;
      if (!visibleSymbols.has(source.symbol) || !visibleSymbols.has(target.symbol)) continue;
      if (!frame.present.has(source.symbol) || !frame.present.has(target.symbol)) continue;
      visibleEdgeCount += 1;
      const a = project(source, frameIndex);
      const b = project(target, frameIndex);
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x, b.y);
      ctx.strokeStyle = `rgba(71, 85, 105, ${{edgeAlpha(edge)}})`;
      ctx.lineWidth = 0.38;
      ctx.stroke();
    }}

    for (const node of nodes) {{
      if (!visibleSymbols.has(node.symbol)) continue;
      const present = frame.present.has(node.symbol);
      const p = project(node, frameIndex);
      const radius = marketCapRadius(node);
      ctx.beginPath();
      ctx.arc(p.x, p.y, present ? radius : 2.6, 0, Math.PI * 2);
      if (present) {{
        ctx.fillStyle = returnColor(frame.returnsMap.get(node.symbol));
        ctx.globalAlpha = hasPositiveMarketCap(node) ? 0.78 : 0.42;
        ctx.fill();
        if (!hasPositiveMarketCap(node)) {{
          ctx.globalAlpha = 0.74;
          ctx.lineWidth = 0.8;
          ctx.strokeStyle = "#64748b";
          ctx.stroke();
        }}
      }} else {{
        ctx.globalAlpha = 0.22;
        ctx.fillStyle = "#cbd5e1";
        ctx.fill();
        ctx.globalAlpha = 0.48;
        ctx.lineWidth = 0.8;
        ctx.strokeStyle = "#94a3b8";
        ctx.stroke();
      }}
    }}
    ctx.globalAlpha = 1;
  }});
  updateFilterStats(visibleSymbols, visibleEdgeCount);
}}

function formatPercent(value) {{
  if (value === "" || value === null || value === undefined) return "missing";
  const number = Number(value);
  if (!Number.isFinite(number)) return "missing";
  return `${{number >= 0 ? "+" : ""}}${{(number * 100).toFixed(2)}}%`;
}}

function nodeTitle(node, frame) {{
  const present = frame.present.has(node.symbol);
  const frameReturn = present ? frame.returnsMap.get(node.symbol) : "";
  return [
    `<strong>${{escapeHtml(node.symbol)}}</strong>${{node.name ? " | " + escapeHtml(node.name) : ""}}`,
    `frame: ${{escapeHtml(frame.frame_label)}}`,
    `frame_status: ${{present ? "present" : "missing in this frame"}}`,
    `return: ${{present ? formatPercent(frameReturn) : "missing"}}`,
    `sector: ${{escapeHtml(node.sector || node.primary_sector || "missing")}}`,
    `industry: ${{escapeHtml(node.industry || "missing")}}`,
    `market_cap: ${{escapeHtml(node.market_cap || "missing")}}`,
    `market_cap_status: ${{escapeHtml(node.market_cap_status || "missing")}}`,
    `market_cap_label: ${{escapeHtml(node.market_cap_label || "missing")}}`,
  ].join("<br>");
}}

function escapeHtml(value) {{
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}}

function frameIndexAt(x) {{
  for (let index = 0; index < frames.length; index += 1) {{
    const panel = panelRect(index);
    if (x >= panel.x && x <= panel.x + panel.width) return index;
  }}
  return -1;
}}

canvas.addEventListener("mousemove", (event) => {{
  const rect = canvas.getBoundingClientRect();
  const x = event.clientX - rect.left;
  const y = event.clientY - rect.top;
  const frameIndex = frameIndexAt(x);
  if (frameIndex < 0) {{
    tooltip.style.display = "none";
    return;
  }}
  const frame = frameState[frameIndex];
  let best = null;
  let bestDistance = 8;
  for (const node of nodes) {{
    if (!passesNodeFilters(node)) continue;
    const p = project(node, frameIndex);
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
  tooltip.innerHTML = nodeTitle(best, frame);
  tooltip.style.display = "block";
  tooltip.style.left = `${{Math.min(x + 14, rect.width - 360)}}px`;
  tooltip.style.top = `${{Math.min(y + 14, rect.height - 150)}}px`;
}});

canvas.addEventListener("mouseleave", () => {{
  tooltip.style.display = "none";
}});

sectorFilter.addEventListener("change", () => {{
  selectedSector = sectorFilter.value;
  draw();
}});

industryFilter.addEventListener("change", () => {{
  selectedIndustry = industryFilter.value;
  draw();
}});

edgeThreshold.addEventListener("input", () => {{
  minEdgeCorrelation = Number(edgeThreshold.value);
  draw();
}});

window.addEventListener("resize", resizeCanvas);
resizeCanvas();
</script>
</body>
</html>
"""
