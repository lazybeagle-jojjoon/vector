# Vector Relations

Build single-period ticker relationship snapshots, then compare saved snapshots through top-k neighbor changes.

The project is intentionally narrow:

- Build one market and one period at a time.
- Define the v1 relationship as return-correlation distance.
- Save source-like artifacts (`universe`, `returns`, `correlations`, `distances`) plus derived artifacts (`neighbors`, `scatter`, `html`).
- Compare periods with numbers first: stayed/entered/exited neighbors, Jaccard similarity, and rank/distance/correlation deltas.

This is a research/inspection tool, not a trading recommendation system.

## How To Read Results

Read "close" as "moved together during this period." It does not mean the
stocks are good, in the same sector, or likely to keep moving together.

Trust the numeric tables first:

- `neighbors.csv` shows each ticker's closest return-correlation neighbors.
- `neighbor_changes.csv` shows which top-k neighbors stayed, entered, or exited
  between saved snapshots.
- `distance_changes.csv` shows rank, distance, and correlation changes for
  those stayed/entered/exited top-k relationships.

Use `scatter.html` as a quick visual aid only. The axes are anchor-distance
axes for one final-period snapshot, not a semantic market map and not a
period-to-period movement chart.

Current US readout highlights:

- Hotel REITs and homebuilders are stable, intuitive control groups.
- Argentina ADRs and uranium names are the cleanest tightening examples.
- Regional banks and energy/oil gas look more like peer-set recomposition.
- Healthcare payers and megacap tech need caution because of membership churn
  and residual CEF/source-classification issues.

## Data Contract

The current pipeline expects a local `stock_data` tree with:

- `meta/derived/backtest_prices_cleaned/{market}.parquet`
- Optional `meta/derived/backtest_universe.parquet`
- Optional `meta/derived/security_classification.parquet`
- Optional `meta/derived/global_market_cap_daily/{market}.parquet`

Set the data root explicitly:

```bash
export STOCK_DATA_ROOT="/path/to/stock_data"
```

The Mac mini workflow is read-oriented for Google Drive data. Do not run EODHD collection, large data mutation, or ad hoc upstream reconstruction from this repo.

## Build A Snapshot

Example final v1 snapshot:

```bash
PYTHONPATH=src uv run --no-project --with pandas --with pyarrow --with duckdb \
  python -m vector_relations.cli \
  --data-root "$STOCK_DATA_ROOT" \
  --market US \
  --period-start 2024-01-01 \
  --period-end 2026-05-22 \
  --universe-scope standard \
  --security-type-scope common-stock \
  --acceptance-examples AAPL,MSFT,JPM,BAC \
  --top-k 10 \
  --projection-seed 42 \
  --min-observations 400 \
  --max-securities 7000 \
  --output-dir outputs/relation_snapshot_us_standard_common_stock_2024-01-01_2026-05-22_minobs400
```

Key outputs:

- `metadata.json`
- `universe.csv`
- `returns.csv`
- `correlations.csv`
- `distances.csv`
- `neighbors.csv`
- `scatter.csv`
- `scatter.html`

`outputs/` is gitignored.

## Compare Snapshots

Selected-symbol comparison:

```bash
PYTHONPATH=src uv run --no-project \
  python -m vector_relations.compare_cli \
  --snapshot outputs/relation_snapshot_us_standard_common_stock_2020-01-01_2021-12-31_minobs350 \
  --snapshot outputs/relation_snapshot_us_standard_common_stock_2022-01-01_2023-12-31_minobs350 \
  --snapshot outputs/relation_snapshot_us_standard_common_stock_2024-01-01_2026-05-22_minobs400 \
  --symbols AAPL,MSFT,JPM,BAC,NVDA,XOM,UNH \
  --top-k 10 \
  --output-dir outputs/relation_snapshot_us_period_comparison_2020_2026_top10
```

Comparison outputs:

- `summary.json`
- `neighbor_changes.csv`
- `distance_changes.csv`
- `insights.md`

The comparison reads top-k `neighbors.csv` rows only. It does not scan every pair in `distances.csv`.

## Render An Ego Network

Render a static one-symbol relationship view from existing snapshot and comparison outputs:

```bash
PYTHONPATH=src uv run --no-project \
  python -m vector_relations.ego_cli \
  --snapshot outputs/relation_snapshot_us_standard_common_stock_2020-01-01_2021-12-31_minobs350 \
  --snapshot outputs/relation_snapshot_us_standard_common_stock_2024-01-01_2026-05-22_minobs400 \
  --comparison-dir outputs/relation_snapshot_us_period_comparison_2020_2026_direct_all_symbols_top10 \
  --symbol HUT \
  --top-k 10 \
  --output-dir outputs/relation_snapshot_us_ego_hut_2020_2026
```

The center symbol is generic; use any symbol present in the saved snapshots.
The view does not recompute relationships and does not use the center symbol as
a projection anchor. It redraws existing top-k neighbors as a local network:

- edge color shows baseline/current/stayed/entered/exited status when a
  comparison directory is provided,
- edge strength still comes from return-correlation distance,
- node color is a period-return overlay from existing `returns.csv`,
- each panel is its own static view, not an animation of coordinates moving
  through time.

Use the same `--top-k` for the comparison output and ego view when possible.
If the ego view asks for more neighbors than the comparison classified, those
extra current-panel edges stay gray as `current`.

## Render A Global Map

Render a single-snapshot full-market map from existing snapshot outputs:

```bash
PYTHONPATH=src uv run --no-project --with numpy \
  python -m vector_relations.global_map_cli \
  --snapshot outputs/relation_snapshot_us_standard_common_stock_2024-01-01_2026-05-22_minobs400 \
  --top-k 10 \
  --seed 42 \
  --iterations 80 \
  --output-dir outputs/relation_snapshot_us_global_map_2024-01-01_2026-05-22_top10
```

To size nodes by raw current market cap, first generate a node metadata CSV from
existing raw fundamentals:

```bash
PYTHONPATH=src uv run --no-project \
  python -m vector_relations.market_cap_metadata_cli \
  --snapshot outputs/relation_snapshot_us_standard_common_stock_2024-01-01_2026-05-22_minobs400 \
  --raw-root "$STOCK_DATA_ROOT/paid_db/eodhd_fundamentals_raw" \
  --market us \
  --output outputs/relation_snapshot_us_market_cap_metadata_2024_2026.csv \
  --file-timeout-seconds 2
```

Then pass it to the global map:

```bash
PYTHONPATH=src uv run --no-project --with numpy \
  python -m vector_relations.global_map_cli \
  --snapshot outputs/relation_snapshot_us_standard_common_stock_2024-01-01_2026-05-22_minobs400 \
  --node-metadata outputs/relation_snapshot_us_market_cap_metadata_2024_2026.csv \
  --top-k 10 \
  --seed 42 \
  --iterations 80 \
  --output-dir outputs/relation_snapshot_us_global_map_2024-01-01_2026-05-22_top10_mcap
```

If you already have a sector/industry metadata CSV, merge it with the market-cap
metadata before rendering so the HTML filters are useful. The current US
artifact uses:

```bash
PYTHONPATH=src uv run --no-project --with numpy \
  python -m vector_relations.global_map_cli \
  --snapshot outputs/relation_snapshot_us_standard_common_stock_2024-01-01_2026-05-22_minobs400 \
  --node-metadata outputs/relation_snapshot_us_node_metadata_sector_mcap_2024_2026.csv \
  --top-k 10 \
  --seed 42 \
  --iterations 80 \
  --output-dir outputs/relation_snapshot_us_global_map_2024-01-01_2026-05-22_top10_sector_mcap
```

Optional `--node-metadata path/to/node_metadata.csv` enriches tooltips when a
CSV keyed by `symbol` or `ticker` is available. Supported nullable overlay
columns include `name`, `type`, `sector`, `industry`, `primary_sector`,
`avg_volume`, `avg_turnover`, `volatility`, `market_cap`,
`market_cap_status`, `market_cap_source`, `market_cap_currency`,
`market_cap_label`, and `market_cap_change`.

Global map outputs:

- `global_map_metadata.json`
- `global_layout.csv`
- `global_edges.csv`
- `global_map.html`

The layout is a seeded, deterministic reference frame. It is not a semantic
axis system and not a period-to-period movement model. Relationship distance
still means return-correlation distance only; return, sector, volume,
volatility, and market cap are overlays.

Market-cap node size is raw/current/as-of-fetch from fundamentals
`Highlights.MarketCapitalization`. It is not period-aligned market-cap change.
Missing or zero market cap is rendered as a neutral outline and counted in
`global_map_metadata.json`. The timeout option is useful when Google Drive raw
JSON hydration is slow; timed-out rows are treated as missing overlay data.

The HTML includes filter/focus controls for sector, industry, and minimum edge
correlation. These controls hide visual clutter only; they do not recompute the
layout, recompute neighbors, rename clusters, or change the return-correlation
relationship.

## Global Timeline

Render several saved snapshots on the same frozen global-map layout:

```bash
PYTHONPATH=src uv run --no-project \
  python -m vector_relations.global_timeline_cli \
  --reference-map outputs/relation_snapshot_us_global_map_2024-01-01_2026-05-22_top10_sector_mcap \
  --snapshot outputs/relation_snapshot_us_standard_common_stock_2020-01-01_2021-12-31_minobs350 \
  --snapshot outputs/relation_snapshot_us_standard_common_stock_2022-01-01_2023-12-31_minobs350 \
  --snapshot outputs/relation_snapshot_us_standard_common_stock_2024-01-01_2026-05-22_minobs400 \
  --top-k 10 \
  --output-dir outputs/relation_snapshot_us_global_timeline_2020_2026_top10_fixed_2024_layout
```

Timeline outputs:

- `global_timeline_metadata.json`
- `global_timeline_nodes.csv`
- `global_timeline_edges.csv`
- `global_timeline_frames.json`
- `global_timeline.html`

The timeline reuses `global_layout.csv` from the reference map. In the example
above, that means the 2024-2026 layout is the reference frame and the earlier
periods are overlaid onto it. Nodes keep the same coordinates in every panel;
only each frame's saved top-k edges, period return colors, and tooltips change.
If a reference-layout node is missing from a frame's universe, it stays visible
as a neutral missing marker with no frame edges. Do not read timeline panels as
node movement.

## Interpretation Limits

- `entered` and `exited` can reflect relationship changes, universe membership changes, or both.
- Residual source-data classification issues can remain. In the current US v1 artifact, some CEF-like names are marked as `Common Stock` upstream.
- The scatter plot is a single-period visual aid, not a period-to-period coordinate movement model.
- Ego network panels are local top-k redraws, not full-market maps, clustering, or 3D views.
- The global map uses one fixed layout for a single snapshot. Do not read node
  position as time movement, sector identity, or investment meaning.
- Market-cap node size is meaningful only within one market/currency map. Do
  not compare raw USD and KRW node sizes in one combined map.
- Sector and industry controls are filters, not taxonomy or cluster labels.
- The global timeline is a fixed-frame small multiple. Position is reused from
  the reference map; compare edges, colors, and tooltip values, not coordinate
  movement. If the reference map is 2024-2026, earlier periods are overlays on
  that frame rather than independently laid-out maps.
- PCA, coordinate alignment, clustering, sector taxonomy, fund/CEF classification, and interactive comparison UI are Later Ideas.
- US/KR market-cap history is not currently available in `global_market_cap_daily` or `global_shares_outstanding_events`; market-cap period comparison is deferred until that data contract exists. Current/as-of-fetch size overlays can be generated from raw fundamentals, but they are not period-change data.

See `ANALYSIS_INDEX.md` for the generated artifact map and current observations.

## Verify

The default system Python may not have DuckDB or NumPy. Plain `pytest -v` skips the Parquet CLI tests and global-map layout tests when those runtimes are unavailable.

The authoritative pre-commit gate is the full CLI test suite with the same ephemeral runtime used by the data CLIs:

```bash
uv run --no-project --with duckdb --with pandas --with pyarrow --with numpy --with pytest \
  python -m pytest -v
```

Also check diff hygiene before finishing:

```bash
git diff --check
```
