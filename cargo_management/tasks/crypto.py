# cargo_management/tasks/crypto.py

import sys
import math
from contextlib import closing
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
import frappe

# Keep the existing module-level adapter seam for callers/tests, without making
# a disabled optional integration a mandatory installation dependency.
try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None

CMC_URL       = "https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest"
FIAT          = "USD"

UPSERT = """
INSERT INTO crypto_snapshots (
  cmc_id, symbol, name, slug,
  fiat, ts,
  price, market_cap, fully_diluted_mcap, market_cap_dominance_pct, volume_24h, volume_change_24h_pct,
  pct_change_1h, pct_change_24h, pct_change_7d, pct_change_30d, pct_change_60d, pct_change_90d,
  cmc_rank, num_market_pairs, circulating_supply, total_supply, max_supply, infinite_supply,
  date_added, tags, status_timestamp, payload_last_updated, ingested_at
) VALUES (
  %(cmc_id)s, %(symbol)s, %(name)s, %(slug)s,
  %(fiat)s, %(ts)s,
  %(price)s, %(market_cap)s, %(fully_diluted_mcap)s, %(market_cap_dominance_pct)s, %(volume_24h)s, %(volume_change_24h_pct)s,
  %(pct_change_1h)s, %(pct_change_24h)s, %(pct_change_7d)s, %(pct_change_30d)s, %(pct_change_60d)s, %(pct_change_90d)s,
  %(cmc_rank)s, %(num_market_pairs)s, %(circulating_supply)s, %(total_supply)s, %(max_supply)s, %(infinite_supply)s,
  %(date_added)s, %(tags)s, %(status_timestamp)s, %(payload_last_updated)s, now()
)
ON CONFLICT (cmc_id, fiat, ts) DO NOTHING;
"""

# --- logging helpers ---
def _log(msg: str, title: str = "crypto"):
    try:
        frappe.log_error(message=msg, title=title)
    except Exception:
        print(f"[{title}] {msg}", file=sys.stdout)

def _log_exc(err_title: str, err: Exception):
    # Connection/HTTP exceptions and traceback locals may contain credentials.
    _log("Crypto integration failed; inspect private service diagnostics.", title="crypto:ERROR")

# --- utils ---
def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        try:
            return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
        except Exception:
            return None

def _safe_num(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        value = float(v)
        return value if math.isfinite(value) else None
    except Exception:
        return None

def _row_from_item(item: Dict[str, Any], status_ts: Optional[datetime], fiat: str) -> Optional[Dict[str, Any]]:
    q = (item.get("quote") or {}).get(fiat) or {}
    payload_last_updated = _parse_iso(q.get("last_updated")) or status_ts
    if payload_last_updated is None:
        # Wall-clock fallback creates a new key on every retry of an identical
        # invalid payload. Do not invent an ingestion timestamp as market time.
        raise ValueError("Crypto snapshot requires a source timestamp.")
    ts = payload_last_updated
    return {
        "cmc_id": item.get("id"),
        "symbol": item.get("symbol"),
        "name": item.get("name"),
        "slug": item.get("slug"),
        "fiat": fiat,
        "ts": ts,
        "price": _safe_num(q.get("price")),
        "market_cap": _safe_num(q.get("market_cap")),
        "fully_diluted_mcap": _safe_num(q.get("fully_diluted_market_cap")),
        "market_cap_dominance_pct": _safe_num(q.get("market_cap_dominance")),
        "volume_24h": _safe_num(q.get("volume_24h")),
        "volume_change_24h_pct": _safe_num(q.get("volume_change_24h")),
        "pct_change_1h": _safe_num(q.get("percent_change_1h")),
        "pct_change_24h": _safe_num(q.get("percent_change_24h")),
        "pct_change_7d": _safe_num(q.get("percent_change_7d")),
        "pct_change_30d": _safe_num(q.get("percent_change_30d")),
        "pct_change_60d": _safe_num(q.get("percent_change_60d")),
        "pct_change_90d": _safe_num(q.get("percent_change_90d")),
        "cmc_rank": item.get("cmc_rank"),
        "num_market_pairs": item.get("num_market_pairs"),
        "circulating_supply": _safe_num(item.get("circulating_supply")),
        "total_supply": _safe_num(item.get("total_supply")),
        "max_supply": _safe_num(item.get("max_supply")),
        "infinite_supply": bool(item.get("infinite_supply")) if item.get("infinite_supply") is not None else None,
        "date_added": _parse_iso(item.get("date_added")),
        "tags": item.get("tags") or [],
        "status_timestamp": status_ts,
        "payload_last_updated": payload_last_updated,
    }

def pull_and_store():
    """Fetch latest listings from CMC (defaults) and upsert into Postgres (USD only)."""
    # Safety exception to v15: no scheduler or manual network activity without opt-in.
    if not frappe.utils.cint(frappe.conf.get("cargo_crypto_enabled", 0)):
        return {"status": "disabled"}
    database_secret_url = frappe.conf.get("cargo_crypto_database_url")
    api_key = frappe.conf.get("cargo_crypto_api_key")
    if not database_secret_url or not api_key:
        frappe.throw("Crypto integration requires private database and API configuration.")
    try:
        # Optional driver must not prevent app/scheduler metadata import when
        # this integration is disabled on an ordinary Cargo installation.
        import psycopg2
        import psycopg2.extras

        headers = {"Accept": "application/json", "X-CMC_PRO_API_KEY": api_key}

        _log(f"Calling CoinMarketCap API (no params) at {CMC_URL} | fiat={FIAT}")

        # no params – rely on CMC defaults
        # A custom API-key header must never follow an unverified redirect.
        resp = requests.get(CMC_URL, headers=headers, timeout=60, allow_redirects=False)
        if resp.status_code != 200:
            # _log(f"CMC non-200 response: {resp.status_code} {resp.text[:500]}")
            resp.raise_for_status()
            raise ValueError("Unexpected crypto provider response status.")

        try:
            payload = resp.json()
        except Exception:
            _log("Crypto response was not valid JSON; response body omitted.")
            raise

        if not isinstance(payload, dict):
            raise ValueError("Invalid crypto response envelope.")

        status = payload.get("status")
        status = {} if status is None else status
        if not isinstance(status, dict):
            raise ValueError("Invalid crypto response status.")
        status_ts = _parse_iso(status.get("timestamp"))
        data = payload.get("data")
        data = [] if data is None else data
        if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
            raise ValueError("Invalid crypto response item collection.")
        if not data:
            _log("CMC returned no data")
            return

        rows: List[Dict[str, Any]] = []
        for item in data:
            row = _row_from_item(item, status_ts, FIAT)
            if row and row.get("cmc_id") and row.get("symbol") and row.get("name"):
                rows.append(row)

        if not rows:
            _log("No parsable rows")
            return

        # _log(f"Parsed {len(rows)} rows; connecting to Postgres…")

        # psycopg2's transaction context does not close its connection.
        with closing(psycopg2.connect(database_secret_url, connect_timeout=10)) as conn:
            with conn:
                with conn.cursor() as cur:
                    psycopg2.extras.execute_batch(cur, UPSERT, rows, page_size=1000)
                conn.commit()

        # _log(f"Upserted {len(rows)} snapshot rows into crypto_snapshots.")
    except Exception:
        # Native developer tracebacks include frame locals. Remove objects
        # whose repr/payload could carry credentials before surfacing failure.
        database_secret_url = api_key = headers = resp = payload = status = data = rows = item = row = conn = cur = None
        # Connection exceptions can contain credentials: never log their values.
        _log("Crypto fetch/store failed; check private configuration and service availability.", title="crypto:ERROR")
        # Suppress the original exception's message/context in RQ Error Logs.
        # No HTTP body, connection URL or adapter traceback locals are emitted.
        raise RuntimeError("Crypto fetch/store failed; check private configuration and service availability.") from None
