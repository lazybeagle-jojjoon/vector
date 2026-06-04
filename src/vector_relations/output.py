from __future__ import annotations

import csv
import html
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .pipeline import RelationSnapshot


@dataclass(frozen=True)
class SnapshotOutputPaths:
    metadata_path: Path
    universe_path: Path
    returns_path: Path
    correlations_path: Path
    distances_path: Path
    neighbors_path: Path
    scatter_path: Path
    html_path: Path


def write_snapshot_outputs(
    snapshot: RelationSnapshot,
    output_dir: str | Path,
) -> SnapshotOutputPaths:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)

    metadata_path = path / "metadata.json"
    universe_path = path / "universe.csv"
    returns_path = path / "returns.csv"
    correlations_path = path / "correlations.csv"
    distances_path = path / "distances.csv"
    neighbors_path = path / "neighbors.csv"
    scatter_path = path / "scatter.csv"
    html_path = path / "scatter.html"

    metadata = {
        **snapshot.metadata,
        "artifact_files": {
            "universe": universe_path.name,
            "returns": returns_path.name,
            "correlations": correlations_path.name,
            "distances": distances_path.name,
            "neighbors": neighbors_path.name,
            "scatter": scatter_path.name,
            "html": html_path.name,
        },
    }
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    snapshot.universe.to_csv(universe_path, index=False)
    snapshot.returns.to_csv(returns_path)
    snapshot.correlations.to_csv(correlations_path)
    snapshot.distances.to_csv(distances_path)
    _write_neighbors_csv(neighbors_path, snapshot.neighbors_by_symbol)
    _write_scatter_csv(scatter_path, snapshot.scatter_points)
    html_path.write_text(_render_scatter_html(snapshot, metadata), encoding="utf-8")

    return SnapshotOutputPaths(
        metadata_path=metadata_path,
        universe_path=universe_path,
        returns_path=returns_path,
        correlations_path=correlations_path,
        distances_path=distances_path,
        neighbors_path=neighbors_path,
        scatter_path=scatter_path,
        html_path=html_path,
    )


def _write_neighbors_csv(
    path: Path,
    neighbors_by_symbol: dict[str, list[dict[str, Any]]],
) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "security_id",
                "symbol",
                "rank",
                "neighbor_symbol",
                "neighbor_security_id",
                "correlation",
                "distance",
            ],
        )
        writer.writeheader()
        for symbol in sorted(neighbors_by_symbol):
            for rank, item in enumerate(neighbors_by_symbol[symbol], start=1):
                writer.writerow(
                    {
                        "security_id": item["security_id"],
                        "symbol": item["symbol"],
                        "rank": rank,
                        "neighbor_symbol": item["neighbor_symbol"],
                        "neighbor_security_id": item["neighbor_security_id"],
                        "correlation": item["correlation"],
                        "distance": item["distance"],
                    }
                )


def _write_scatter_csv(path: Path, scatter_points: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["security_id", "symbol", "x", "y", "market_cap_change"],
        )
        writer.writeheader()
        for point in scatter_points:
            writer.writerow(
                {
                    "security_id": point["security_id"],
                    "symbol": point["symbol"],
                    "x": point["x"],
                    "y": point["y"],
                    "market_cap_change": point.get("market_cap_change"),
                }
            )


def _render_scatter_html(snapshot: RelationSnapshot, metadata: dict[str, Any]) -> str:
    points = snapshot.scatter_points
    width = 960
    height = 640
    padding = 48
    xs = [float(point["x"]) for point in points] or [0.0]
    ys = [float(point["y"]) for point in points] or [0.0]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    def scale(value: float, low: float, high: float, out_low: float, out_high: float) -> float:
        if high == low:
            return (out_low + out_high) / 2
        return out_low + ((value - low) / (high - low)) * (out_high - out_low)

    circles = []
    for point in points:
        x = scale(float(point["x"]), min_x, max_x, padding, width - padding)
        y = scale(float(point["y"]), min_y, max_y, height - padding, padding)
        symbol = html.escape(str(point["symbol"]))
        market_cap_change = point.get("market_cap_change")
        color = _market_cap_color(market_cap_change)
        title = _point_title(symbol, market_cap_change)
        circles.append(
            f'<g><circle cx="{x:.2f}" cy="{y:.2f}" r="5" fill="{color}" opacity="0.82">'
            f"<title>{title}</title></circle>"
            f'<text x="{x + 7:.2f}" y="{y + 4:.2f}" font-size="11" fill="#1f2937">{symbol}</text></g>'
        )

    metadata_json = html.escape(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True)
    )
    points_json = html.escape(json.dumps(points, ensure_ascii=False, indent=2))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Ticker Relationship Scatter</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; color: #111827; background: #f8fafc; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 24px; }}
    h1 {{ font-size: 24px; margin: 0 0 8px; }}
    p {{ margin: 0 0 16px; color: #4b5563; }}
    svg {{ width: 100%; height: auto; background: white; border: 1px solid #d1d5db; }}
    pre {{ overflow: auto; padding: 16px; background: #111827; color: #e5e7eb; }}
  </style>
</head>
<body>
<main>
  <h1>Ticker Relationship Scatter</h1>
  <p>Deterministic anchor-distance scatter generated from return-correlation distances.</p>
  <svg viewBox="0 0 {width} {height}" role="img" aria-label="Ticker relationship scatter">
    <rect x="0" y="0" width="{width}" height="{height}" fill="#ffffff"></rect>
    {"".join(circles)}
  </svg>
  <h2>Metadata</h2>
  <pre>{metadata_json}</pre>
  <h2>Points</h2>
  <pre>{points_json}</pre>
</main>
</body>
</html>
"""


def _market_cap_color(market_cap_change: Any) -> str:
    if market_cap_change is None:
        return "#2563eb"
    try:
        value = float(market_cap_change)
    except (TypeError, ValueError):
        return "#2563eb"
    if value > 0:
        return "#059669"
    if value < 0:
        return "#dc2626"
    return "#6b7280"


def _point_title(symbol: str, market_cap_change: Any) -> str:
    if market_cap_change is None:
        return html.escape(f"{symbol} | market_cap_change: missing")
    try:
        value = float(market_cap_change)
    except (TypeError, ValueError):
        return html.escape(f"{symbol} | market_cap_change: {market_cap_change}")
    return html.escape(f"{symbol} | market_cap_change: {value:.4f}")
