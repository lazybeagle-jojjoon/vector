# Vector Relations

Build single-period ticker relationship snapshots, then compare saved snapshots through top-k neighbor changes.

The project is intentionally narrow:

- Build one market and one period at a time.
- Define the v1 relationship as return-correlation distance.
- Save source-like artifacts (`universe`, `returns`, `correlations`, `distances`) plus derived artifacts (`neighbors`, `scatter`, `html`).
- Compare periods with numbers first: stayed/entered/exited neighbors, Jaccard similarity, and rank/distance/correlation deltas.

This is a research/inspection tool, not a trading recommendation system.

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

## Interpretation Limits

- `entered` and `exited` can reflect relationship changes, universe membership changes, or both.
- Residual source-data classification issues can remain. In the current US v1 artifact, some CEF-like names are marked as `Common Stock` upstream.
- The scatter plot is a single-period visual aid, not a period-to-period coordinate movement model.
- PCA, coordinate alignment, clustering, sector taxonomy, fund/CEF classification, and interactive comparison UI are Later Ideas.
- US/KR market-cap history is not currently available in `global_market_cap_daily` or `global_shares_outstanding_events`; market-cap period comparison is deferred until that data contract exists.

See `ANALYSIS_INDEX.md` for the generated artifact map and current observations.

## Verify

The default system Python may not have DuckDB. Plain `pytest -v` skips the Parquet CLI tests when DuckDB is unavailable.

The authoritative pre-commit gate is the full CLI test suite with the same ephemeral runtime used by the data CLIs:

```bash
uv run --no-project --with duckdb --with pandas --with pyarrow --with pytest \
  python -m pytest -v
```

Also check diff hygiene before finishing:

```bash
git diff --check
```
