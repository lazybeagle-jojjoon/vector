# Analysis Index

This project builds single-period ticker relationship snapshots, then compares saved snapshots through top-k neighbor changes.

This index describes local generated artifacts under `outputs/`. Those artifacts are gitignored and are not part of the repository; use the regeneration commands below before opening these paths in a fresh clone.

## Start Here

Read these first:

- `outputs/relation_snapshot_us_reading_guide_2020_2026.md`
  Best entry point for the current artifact set: reading order, trusted reads, caveated reads, and stop line.
- `outputs/relation_snapshot_us_period_group_review_2020_2026_top10.md`  
  Manual analyst note for curated groups: hotel REITs, homebuilders, Argentina ADRs, regional banks, gold/silver miners, uranium names. This is not a generated taxonomy or classifier.
- `outputs/relation_snapshot_us_period_global_highlights_2020_2026_top10.md`  
  Broad all-symbol highlights, distribution counts, stable clusters, and universe cautions.
- `outputs/relation_snapshot_us_period_ticker_timeline_2020_2026_top10.md`  
  Per-ticker timeline for `AAPL`, `BAC`, `JPM`, `MSFT`, `NVDA`, `UNH`, `XOM`.

## Core Snapshot Artifacts

Final v1 acceptance snapshot:

- `outputs/relation_snapshot_us_standard_common_stock_2024-01-01_2026-05-22_minobs400/`
- Market: `US`
- Universe: `standard + common-stock`
- Period: `2024-01-01` to `2026-05-22`
- Approx size: `1.0GB`
- Key files:
  - `metadata.json`
  - `universe.csv`
  - `returns.csv`
  - `correlations.csv`
  - `distances.csv`
  - `neighbors.csv`
  - `scatter.csv`
  - `scatter.html`

Period snapshots used for comparisons:

- `outputs/relation_snapshot_us_standard_common_stock_2020-01-01_2021-12-31_minobs350/` approx `588MB`
- `outputs/relation_snapshot_us_standard_common_stock_2022-01-01_2023-12-31_minobs350/` approx `853MB`
- `outputs/relation_snapshot_us_standard_common_stock_2024-01-01_2026-05-22_minobs400/` approx `1.0GB`

Exploratory artifact, not acceptance:

- `outputs/relation_snapshot_us_full_1972-01-03_2026-05-22/` approx `2.1GB`
- This uses the broad price file and a long window. It is useful for curiosity, but not the clean v1 acceptance run.

## Comparison Artifacts

Selected-symbol adjacent comparison:

- `outputs/relation_snapshot_us_period_comparison_2020_2026_top10/`
- Symbols: `AAPL`, `BAC`, `JPM`, `MSFT`, `NVDA`, `UNH`, `XOM`
- Compares:
  - `2020-2021 -> 2022-2023`
  - `2022-2023 -> 2024-2026`

Selected-symbol direct comparison:

- `outputs/relation_snapshot_us_period_comparison_2020_2026_direct_top10/`
- Compares:
  - `2020-2021 -> 2024-2026`

All-symbol adjacent comparison:

- `outputs/relation_snapshot_us_period_comparison_2020_2026_all_symbols_top10/`
- `symbols_count=5085`
- `neighbor_change_rows=10170`
- `distance_change_rows=160897`
- Approx size: `22MB`

All-symbol direct comparison:

- `outputs/relation_snapshot_us_period_comparison_2020_2026_direct_all_symbols_top10/`
- `symbols_count=5079`
- `neighbor_change_rows=5079`
- `distance_change_rows=81308`
- Approx size: `11MB`

Each comparison directory contains:

- `summary.json`
- `neighbor_changes.csv`
- `distance_changes.csv`
- `insights.md`

## What The Comparison Means

The comparison is intentionally numeric-first:

- `neighbor_changes.csv` compares top-k neighbor sets.
- `distance_changes.csv` records rank, distance, and correlation deltas for stayed/entered/exited top-k neighbors.
- `insights.md` summarizes stable sets, changed sets, large stayed-distance moves, and universe cautions.

Important limits:

- It compares top-k neighbor tables only. It does not scan every pair in `distances.csv`.
- `entered` and `exited` can mean relationship change, universe membership change, or both.
- Use `old_symbol_in_universe`, `new_symbol_in_universe`, `old_neighbor_in_universe`, and `new_neighbor_in_universe` before interpreting a change.
- AAPL still has residual CEF contamination because some source classifications mark CEF-like names as `Common Stock`.
- Manual group-review files are analyst notes over fixed artifacts, not truth data. Do not promote those labels into code, metadata, or CLI behavior without a separate Later-scope decision.
- These outputs are research artifacts, not trading recommendations.

## Strongest Current Observations

- Reading guide: use the current artifact set for manual reading, and do not add more automation without a new data-contract item or explicit new question.
- Hotel REITs and homebuilders are very stable, economically coherent clusters.
- Argentina ADRs and uranium are the cleanest tightening reads in the current manual notes.
- Regional banks and energy/oil gas look more like recomposition reads than simple tightening reads.
- Healthcare payers and megacap tech remain caveated by weakening peers, membership churn, and residual CEF/source-classification issues.
- Regional banks are coherent but show more turnover than hotel REITs/homebuilders.
- `BAC` is stable among the hand-picked ticker examples.
- `AAPL`, `MSFT`, and `NVDA` show high top-k turnover over the long direct comparison.
- `UNH` retains several healthcare peers, but stayed distances moved materially farther.

## Regeneration Commands

Set the data root first:

```bash
export STOCK_DATA_ROOT="/Users/joonyoungjo/Library/CloudStorage/GoogleDrive-jojjoon@gmail.com/내 드라이브/stock_data"
```

Rebuild the final v1 snapshot:

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

Rebuild selected-symbol adjacent comparison:

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

Rebuild all-symbol adjacent comparison:

```bash
PYTHONPATH=src uv run --no-project \
  python -m vector_relations.compare_cli \
  --snapshot outputs/relation_snapshot_us_standard_common_stock_2020-01-01_2021-12-31_minobs350 \
  --snapshot outputs/relation_snapshot_us_standard_common_stock_2022-01-01_2023-12-31_minobs350 \
  --snapshot outputs/relation_snapshot_us_standard_common_stock_2024-01-01_2026-05-22_minobs400 \
  --top-k 10 \
  --output-dir outputs/relation_snapshot_us_period_comparison_2020_2026_all_symbols_top10
```

## Next Aligned Moves

Most aligned:

- Stop here and treat v1/v1.5 as closed unless a new data-contract item is explicitly chosen.
- If continuing within the original intent, the most aligned data-contract item is adding market-cap change numbers to period comparison, if market-cap history becomes available.
- Current data audit: US/KR market-cap history is not available in `meta/derived/global_market_cap_daily/` or `meta/derived/global_shares_outstanding_events/` as of the checked 2026-06-03 reports. Do not add ad hoc collection or fundamentals reconstruction inside v1/v1.5.

Keep in Later Ideas:

- PCA or coordinate alignment.
- Clustering.
- Sector labeling or a maintained taxonomy.
- Fund/CEF classifier.
- Interactive period-comparison UI.
- Group-review automation or CLI promotion.
