import math

import pandas as pd
import pytest

from vector_relations.pipeline import build_relation_snapshot


def test_build_relation_snapshot_ranks_correlated_peers_and_returns_scatter():
    prices = pd.DataFrame(
        [
            ("AAA", "AAA", "2024-01-01", 100.0),
            ("AAA", "AAA", "2024-01-02", 101.0),
            ("AAA", "AAA", "2024-01-03", 102.0),
            ("AAA", "AAA", "2024-01-04", 103.0),
            ("AAA", "AAA", "2024-01-05", 104.0),
            ("BBB", "BBB", "2024-01-01", 200.0),
            ("BBB", "BBB", "2024-01-02", 202.0),
            ("BBB", "BBB", "2024-01-03", 204.0),
            ("BBB", "BBB", "2024-01-04", 206.0),
            ("BBB", "BBB", "2024-01-05", 208.0),
            ("ZZZ", "ZZZ", "2024-01-01", 100.0),
            ("ZZZ", "ZZZ", "2024-01-02", 99.0),
            ("ZZZ", "ZZZ", "2024-01-03", 98.0),
            ("ZZZ", "ZZZ", "2024-01-04", 97.0),
            ("ZZZ", "ZZZ", "2024-01-05", 96.0),
        ],
        columns=["security_id", "symbol", "date", "adjusted_close"],
    )

    snapshot = build_relation_snapshot(
        prices=prices,
        market="US",
        period_start="2024-01-01",
        period_end="2024-01-05",
        price_column="adjusted_close",
        top_k=1,
        projection_seed=42,
        min_observations=3,
        acceptance_examples=["AAA", "BBB"],
    )

    aaa_neighbors = snapshot.neighbors_by_symbol["AAA"]
    assert aaa_neighbors[0]["neighbor_symbol"] == "BBB"
    assert aaa_neighbors[0]["correlation"] > 0.99

    assert len(snapshot.scatter_points) == 3
    assert {point["symbol"] for point in snapshot.scatter_points} == {"AAA", "BBB", "ZZZ"}
    assert all(math.isfinite(point["x"]) and math.isfinite(point["y"]) for point in snapshot.scatter_points)

    assert snapshot.metadata["top_k"] == 1
    assert snapshot.metadata["projection_seed"] == 42
    assert snapshot.metadata["market_cap_overlay"] == "missing"
    assert snapshot.metadata["market_cap_fallback_reason"] == "market_cap_frame_not_provided"
    assert snapshot.metadata["acceptance_examples"]["AAA"]["top_neighbor"] == "BBB"


def test_build_relation_snapshot_uses_market_cap_overlay_when_available():
    prices = pd.DataFrame(
        [
            ("AAA", "AAA", "2024-01-01", 100.0),
            ("AAA", "AAA", "2024-01-02", 102.0),
            ("AAA", "AAA", "2024-01-03", 104.0),
            ("BBB", "BBB", "2024-01-01", 50.0),
            ("BBB", "BBB", "2024-01-02", 51.0),
            ("BBB", "BBB", "2024-01-03", 52.0),
        ],
        columns=["security_id", "symbol", "date", "adjusted_close"],
    )
    market_caps = pd.DataFrame(
        [
            ("AAA", "2024-01-01", 1000.0),
            ("AAA", "2024-01-03", 1100.0),
            ("BBB", "2024-01-01", 500.0),
            ("BBB", "2024-01-03", 550.0),
        ],
        columns=["security_id", "date", "market_cap"],
    )

    snapshot = build_relation_snapshot(
        prices=prices,
        market="US",
        period_start="2024-01-01",
        period_end="2024-01-03",
        price_column="adjusted_close",
        top_k=1,
        projection_seed=42,
        min_observations=2,
        market_caps=market_caps,
    )

    point_by_symbol = {point["symbol"]: point for point in snapshot.scatter_points}
    assert point_by_symbol["AAA"]["market_cap_change"] == pytest.approx(0.1)
    assert point_by_symbol["BBB"]["market_cap_change"] == pytest.approx(0.1)
    assert snapshot.metadata["market_cap_overlay"] == "included"


def test_build_relation_snapshot_chooses_second_anchor_with_lower_correlation():
    prices = pd.DataFrame(
        [
            ("AAA", "AAA", "2024-01-01", 100.0),
            ("AAA", "AAA", "2024-01-02", 101.0),
            ("AAA", "AAA", "2024-01-03", 102.0),
            ("AAA", "AAA", "2024-01-04", 103.0),
            ("AAA", "AAA", "2024-01-05", 104.0),
            ("BBB", "BBB", "2024-01-01", 200.0),
            ("BBB", "BBB", "2024-01-02", 202.0),
            ("BBB", "BBB", "2024-01-03", 204.0),
            ("BBB", "BBB", "2024-01-04", 206.0),
            ("BBB", "BBB", "2024-01-05", 208.0),
            ("CCC", "CCC", "2024-01-01", 100.0),
            ("CCC", "CCC", "2024-01-02", 99.0),
            ("CCC", "CCC", "2024-01-03", 98.0),
            ("CCC", "CCC", "2024-01-04", 97.0),
            ("CCC", "CCC", "2024-01-05", 96.0),
        ],
        columns=["security_id", "symbol", "date", "adjusted_close"],
    )

    snapshot = build_relation_snapshot(
        prices=prices,
        market="US",
        period_start="2024-01-01",
        period_end="2024-01-05",
        price_column="adjusted_close",
        top_k=1,
        projection_seed=42,
        min_observations=3,
        acceptance_examples=["AAA", "BBB"],
    )

    assert snapshot.metadata["scatter_anchor_symbols"] == ["AAA", "CCC"]
    assert snapshot.metadata["scatter_anchor_note"] == "second_anchor_lowest_correlation_to_first"


def test_build_relation_snapshot_rejects_duplicate_display_symbols():
    prices = pd.DataFrame(
        [
            ("SEC:AAA1", "AAA", "2024-01-01", 100.0),
            ("SEC:AAA1", "AAA", "2024-01-02", 101.0),
            ("SEC:AAA1", "AAA", "2024-01-03", 102.0),
            ("SEC:AAA2", "AAA", "2024-01-01", 200.0),
            ("SEC:AAA2", "AAA", "2024-01-02", 198.0),
            ("SEC:AAA2", "AAA", "2024-01-03", 196.0),
            ("SEC:BBB", "BBB", "2024-01-01", 50.0),
            ("SEC:BBB", "BBB", "2024-01-02", 51.0),
            ("SEC:BBB", "BBB", "2024-01-03", 52.0),
        ],
        columns=["security_id", "symbol", "date", "adjusted_close"],
    )

    with pytest.raises(ValueError, match="duplicate display symbols"):
        build_relation_snapshot(
            prices=prices,
            market="US",
            period_start="2024-01-01",
            period_end="2024-01-03",
            price_column="adjusted_close",
            top_k=1,
            projection_seed=42,
            min_observations=2,
        )


def test_build_relation_snapshot_drops_short_history_symbols_before_scatter():
    prices = pd.DataFrame(
        [
            ("AAA", "AAA", "2024-01-01", 100.0),
            ("AAA", "AAA", "2024-01-02", 101.0),
            ("AAA", "AAA", "2024-01-03", 102.0),
            ("AAA", "AAA", "2024-01-04", 103.0),
            ("BBB", "BBB", "2024-01-01", 200.0),
            ("BBB", "BBB", "2024-01-02", 202.0),
            ("BBB", "BBB", "2024-01-03", 204.0),
            ("BBB", "BBB", "2024-01-04", 206.0),
            ("SHORT", "SHORT", "2024-01-01", 50.0),
            ("SHORT", "SHORT", "2024-01-02", 51.0),
        ],
        columns=["security_id", "symbol", "date", "adjusted_close"],
    )

    snapshot = build_relation_snapshot(
        prices=prices,
        market="US",
        period_start="2024-01-01",
        period_end="2024-01-04",
        price_column="adjusted_close",
        top_k=1,
        projection_seed=42,
        min_observations=3,
        acceptance_examples=["AAA", "BBB"],
    )

    assert set(snapshot.universe["symbol"]) == {"AAA", "BBB"}
    assert {point["symbol"] for point in snapshot.scatter_points} == {"AAA", "BBB"}
