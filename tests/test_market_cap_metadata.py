import csv
import json

import vector_relations.market_cap_metadata as market_cap_metadata
from vector_relations.market_cap_metadata import write_market_cap_metadata
from vector_relations.market_cap_metadata_cli import run


def test_write_market_cap_metadata_extracts_current_market_cap_and_status(tmp_path):
    snapshot = tmp_path / "snapshot"
    raw_root = tmp_path / "raw"
    output_csv = tmp_path / "market_cap_metadata.csv"
    _write_snapshot_universe(
        snapshot,
        [
            ("SEC:AAPL", "AAPL"),
            ("SEC:ZERO", "ZERO"),
            ("SEC:MISS", "MISS"),
        ],
    )
    _write_raw(
        raw_root / "us" / "aapl_us.json",
        market_cap=123456789,
        shares_outstanding=10,
        currency="USD",
    )
    _write_raw(
        raw_root / "us" / "zero_us.json",
        market_cap=0,
        shares_outstanding=0,
        currency="USD",
    )

    summary = write_market_cap_metadata(
        snapshot_dir=snapshot,
        raw_root=raw_root,
        market="us",
        output_path=output_csv,
    )

    rows = _read_csv(output_csv)
    row_by_symbol = {row["symbol"]: row for row in rows}
    assert summary["universe_n"] == 3
    assert summary["raw_matched"] == 2
    assert summary["positive_count"] == 1
    assert summary["zero_count"] == 1
    assert summary["missing_count"] == 1
    assert summary["label"] == "raw/current/as-of-fetch"
    assert row_by_symbol["AAPL"]["market_cap"] == "123456789"
    assert row_by_symbol["AAPL"]["market_cap_status"] == "positive"
    assert row_by_symbol["AAPL"]["market_cap_source"] == "raw_highlights_market_capitalization"
    assert row_by_symbol["AAPL"]["market_cap_currency"] == "USD"
    assert row_by_symbol["AAPL"]["market_cap_label"] == "raw/current/as-of-fetch"
    assert row_by_symbol["ZERO"]["market_cap"] == ""
    assert row_by_symbol["ZERO"]["market_cap_status"] == "zero"
    assert row_by_symbol["MISS"]["market_cap"] == ""
    assert row_by_symbol["MISS"]["market_cap_status"] == "missing_raw"


def test_market_cap_metadata_cli_writes_requested_output(tmp_path):
    snapshot = tmp_path / "snapshot"
    raw_root = tmp_path / "raw"
    output_csv = tmp_path / "metadata.csv"
    _write_snapshot_universe(snapshot, [("SEC:005930", "005930.KO")])
    _write_raw(
        raw_root / "kr" / "005930_ko.json",
        market_cap=999,
        shares_outstanding=5,
        currency="KRW",
    )

    result_path = run(
        [
            "--snapshot",
            str(snapshot),
            "--raw-root",
            str(raw_root),
            "--market",
            "kr",
            "--output",
            str(output_csv),
        ]
    )

    assert result_path == output_csv
    rows = _read_csv(output_csv)
    assert rows[0]["symbol"] == "005930.KO"
    assert rows[0]["market_cap"] == "999"
    assert rows[0]["market_cap_currency"] == "KRW"


def test_write_market_cap_metadata_marks_timeout_as_missing(tmp_path, monkeypatch):
    snapshot = tmp_path / "snapshot"
    raw_root = tmp_path / "raw"
    output_csv = tmp_path / "market_cap_metadata.csv"
    _write_snapshot_universe(snapshot, [("SEC:SLOW", "SLOW")])
    _write_raw(
        raw_root / "us" / "slow_us.json",
        market_cap=123,
        shares_outstanding=10,
        currency="USD",
    )

    def raise_timeout(_path, *, timeout_seconds):
        raise TimeoutError

    monkeypatch.setattr(market_cap_metadata, "_read_raw_json", raise_timeout)

    summary = write_market_cap_metadata(
        snapshot_dir=snapshot,
        raw_root=raw_root,
        market="us",
        output_path=output_csv,
        file_timeout_seconds=1,
    )

    rows = _read_csv(output_csv)
    assert summary["timeout_count"] == 1
    assert summary["missing_count"] == 1
    assert rows[0]["market_cap_status"] == "timeout"
    assert rows[0]["market_cap"] == ""


def _write_snapshot_universe(path, rows):
    path.mkdir()
    with (path / "universe.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["security_id", "symbol"])
        writer.writerows(rows)


def _write_raw(path, *, market_cap, shares_outstanding, currency):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "General": {"CurrencyCode": currency},
                "Highlights": {"MarketCapitalization": market_cap},
                "SharesStats": {"SharesOutstanding": shares_outstanding},
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _read_csv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))
