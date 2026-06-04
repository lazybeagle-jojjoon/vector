from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


FIELDNAMES = [
    "security_id",
    "symbol",
    "market_cap",
    "market_cap_status",
    "market_cap_source",
    "market_cap_currency",
    "market_cap_label",
    "shares_outstanding",
    "shares_outstanding_status",
]

MARKET_CAP_LABEL = "raw/current/as-of-fetch"
MARKET_CAP_SOURCE = "raw_highlights_market_capitalization"
_RAW_READER_CODE = """
import json
import sys
from pathlib import Path

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(json.dumps({
    "General": data.get("General") or {},
    "Highlights": data.get("Highlights") or {},
    "SharesStats": data.get("SharesStats") or {},
}))
"""


def write_market_cap_metadata(
    *,
    snapshot_dir: str | Path,
    raw_root: str | Path,
    market: str,
    output_path: str | Path,
    file_timeout_seconds: int = 0,
) -> dict[str, Any]:
    universe = _read_universe(Path(snapshot_dir) / "universe.csv")
    raw_dir = Path(raw_root) / market.lower()
    if not raw_dir.exists():
        raise ValueError(f"Raw fundamentals market directory does not exist: {raw_dir}")

    rows: list[dict[str, str]] = []
    summary = {
        "market": market.upper(),
        "universe_n": len(universe),
        "raw_matched": 0,
        "positive_count": 0,
        "zero_count": 0,
        "missing_count": 0,
        "parse_error_count": 0,
        "timeout_count": 0,
        "label": MARKET_CAP_LABEL,
    }

    for item in universe:
        raw_path = _raw_path_for_symbol(raw_dir, market, item["symbol"])
        row = {
            "security_id": item["security_id"],
            "symbol": item["symbol"],
            "market_cap": "",
            "market_cap_status": "missing_raw",
            "market_cap_source": MARKET_CAP_SOURCE,
            "market_cap_currency": "",
            "market_cap_label": MARKET_CAP_LABEL,
            "shares_outstanding": "",
            "shares_outstanding_status": "missing_raw",
        }
        if not raw_path.exists():
            summary["missing_count"] += 1
            rows.append(row)
            continue

        summary["raw_matched"] += 1
        try:
            data = _read_raw_json(raw_path, timeout_seconds=file_timeout_seconds)
        except TimeoutError:
            row["market_cap_status"] = "timeout"
            row["shares_outstanding_status"] = "timeout"
            summary["timeout_count"] += 1
            summary["missing_count"] += 1
            rows.append(row)
            continue
        except (OSError, json.JSONDecodeError):
            row["market_cap_status"] = "parse_error"
            row["shares_outstanding_status"] = "parse_error"
            summary["parse_error_count"] += 1
            summary["missing_count"] += 1
            rows.append(row)
            continue

        currency = str((data.get("General") or {}).get("CurrencyCode") or "").strip()
        market_cap = _to_float((data.get("Highlights") or {}).get("MarketCapitalization"))
        shares = _to_float((data.get("SharesStats") or {}).get("SharesOutstanding"))
        row["market_cap_currency"] = currency
        row["shares_outstanding"] = _format_number(shares)
        row["shares_outstanding_status"] = _numeric_status(shares)

        status = _numeric_status(market_cap)
        row["market_cap_status"] = status
        if status == "positive":
            row["market_cap"] = _format_number(market_cap)
            summary["positive_count"] += 1
        elif status == "zero":
            summary["zero_count"] += 1
        else:
            summary["missing_count"] += 1
        rows.append(row)

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    summary["coverage_rate"] = (
        summary["positive_count"] / summary["universe_n"]
        if summary["universe_n"]
        else 0.0
    )
    return summary


def _read_universe(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise ValueError(f"Snapshot universe CSV does not exist: {path}")
    rows: list[dict[str, str]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            symbol = row.get("symbol", "").strip().upper()
            if symbol:
                rows.append(
                    {
                        "security_id": row.get("security_id", "").strip(),
                        "symbol": symbol,
                    }
                )
    return rows


def _raw_path_for_symbol(raw_dir: Path, market: str, symbol: str) -> Path:
    if market.lower() == "us" and "." not in symbol:
        symbol = f"{symbol}.US"
    return raw_dir / f"{_symbol_stem(symbol)}.json"


def _read_raw_json(path: Path, *, timeout_seconds: int) -> dict[str, Any]:
    if timeout_seconds <= 0:
        return json.loads(path.read_text(encoding="utf-8"))
    try:
        result = subprocess.run(
            [sys.executable, "-c", _RAW_READER_CODE, str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError from exc
    if result.returncode != 0:
        raise json.JSONDecodeError(result.stderr or "raw reader failed", "", 0)
    return json.loads(result.stdout)


def _symbol_stem(symbol: str) -> str:
    return (
        symbol.strip()
        .lower()
        .replace(".", "_")
        .replace("-", "_")
        .replace("/", "_")
    )


def _to_float(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _numeric_status(value: float | None) -> str:
    if value is None:
        return "missing"
    if value > 0:
        return "positive"
    if value == 0:
        return "zero"
    return "invalid"


def _format_number(value: float | None) -> str:
    if value is None:
        return ""
    if value.is_integer():
        return str(int(value))
    return f"{value:.8g}"
