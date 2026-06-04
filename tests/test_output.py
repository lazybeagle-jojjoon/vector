import json

import pandas as pd

from vector_relations.output import write_snapshot_outputs
from vector_relations.pipeline import RelationSnapshot


def test_write_snapshot_outputs_creates_metadata_tables_and_html(tmp_path):
    snapshot = RelationSnapshot(
        metadata={
            "market": "US",
            "period_start": "2024-01-01",
            "period_end": "2024-01-05",
            "market_cap_overlay": "missing",
            "market_cap_fallback_reason": "market_cap_frame_not_provided",
        },
        neighbors_by_symbol={
            "AAA": [
                {
                    "security_id": "AAA",
                    "symbol": "AAA",
                    "neighbor_symbol": "BBB",
                    "neighbor_security_id": "BBB",
                    "correlation": 0.99,
                    "distance": 0.01,
                }
            ]
        },
        scatter_points=[
            {
                "security_id": "AAA",
                "symbol": "AAA",
                "x": 0.0,
                "y": 0.01,
                "market_cap_change": None,
            },
            {
                "security_id": "BBB",
                "symbol": "BBB",
                "x": 0.01,
                "y": 0.0,
                "market_cap_change": None,
            },
        ],
        universe=pd.DataFrame(
            [{"security_id": "AAA", "symbol": "AAA"}, {"security_id": "BBB", "symbol": "BBB"}]
        ),
        returns=pd.DataFrame(
            {"AAA": [0.01, 0.02], "BBB": [0.01, 0.02]},
            index=pd.Index(["2024-01-02", "2024-01-03"], name="date"),
        ),
        correlations=pd.DataFrame(
            {"AAA": [1.0, 0.99], "BBB": [0.99, 1.0]},
            index=pd.Index(["AAA", "BBB"], name="security_id"),
        ),
        distances=pd.DataFrame(
            {"AAA": [0.0, 0.01], "BBB": [0.01, 0.0]},
            index=pd.Index(["AAA", "BBB"], name="security_id"),
        ),
    )

    outputs = write_snapshot_outputs(snapshot, tmp_path)

    assert outputs.metadata_path.exists()
    assert outputs.universe_path.exists()
    assert outputs.returns_path.exists()
    assert outputs.correlations_path.exists()
    assert outputs.distances_path.exists()
    assert outputs.neighbors_path.exists()
    assert outputs.scatter_path.exists()
    assert outputs.html_path.exists()

    metadata = json.loads(outputs.metadata_path.read_text(encoding="utf-8"))
    assert metadata["market"] == "US"
    assert metadata["market_cap_overlay"] == "missing"
    assert metadata["artifact_files"]["universe"] == "universe.csv"
    assert metadata["artifact_files"]["returns"] == "returns.csv"
    assert metadata["artifact_files"]["correlations"] == "correlations.csv"
    assert metadata["artifact_files"]["distances"] == "distances.csv"

    returns = outputs.returns_path.read_text(encoding="utf-8")
    assert "date,AAA,BBB" in returns

    universe = outputs.universe_path.read_text(encoding="utf-8")
    assert "security_id,symbol" in universe
    assert "AAA,AAA" in universe

    correlations = outputs.correlations_path.read_text(encoding="utf-8")
    assert "security_id,AAA,BBB" in correlations

    distances = outputs.distances_path.read_text(encoding="utf-8")
    assert "security_id,AAA,BBB" in distances

    neighbors = outputs.neighbors_path.read_text(encoding="utf-8")
    assert "security_id,symbol,rank,neighbor_symbol,neighbor_security_id,correlation,distance" in neighbors
    assert "AAA,AAA,1,BBB,BBB,0.99,0.01" in neighbors

    scatter = outputs.scatter_path.read_text(encoding="utf-8")
    assert "security_id,symbol,x,y,market_cap_change" in scatter
    assert "AAA,AAA,0.0,0.01," in scatter

    html = outputs.html_path.read_text(encoding="utf-8")
    assert "Ticker Relationship Scatter" in html
    assert "<title>AAA | market_cap_change: missing</title>" in html
