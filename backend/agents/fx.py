"""Quarterly FX rate helper (SPEC § 2.2 PxQ consistency).

The Estimator emits revenue in KRW while individual edges may carry P (USD ASP)
× Q (units). Without a quarterly FX figure the Evaluator cannot tell whether
``p_as_usd × q_units`` agrees with ``estimated_revenue_krw``. This module
fetches a quarter-mean FX rate from the no-key Frankfurter API (ECB-backed),
with a legacy ECB XML feed as a backup. It deliberately returns ``None`` when
both fail — callers must skip the check rather than fall back to a guessed
constant.

Env flags:
- ``LIVE_FX`` (default ``true``)  — global kill switch. ``false`` makes every
  call return ``None`` so unit tests stay offline-safe.

Network access:
- Frankfurter:  https://api.frankfurter.dev/v2/rates?from=USD&to=KRW&start_date=...&end_date=...
- ECB legacy:   https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.xml
"""

from __future__ import annotations

import os
import threading
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from functools import lru_cache
from statistics import mean
from typing import Iterable, Optional

import requests


LIVE_FX = os.getenv("LIVE_FX", "true").lower() in {"1", "true", "yes"}

FRANKFURTER_URL = "https://api.frankfurter.dev/v2/rates"
ECB_HIST_URL = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.xml"
HTTP_TIMEOUT_SECONDS = 8

_lock = threading.Lock()


def _quarter_window(target_quarter: str) -> Optional[tuple[date, date]]:
    """Return ``(start, end)`` for "YYYY-Qn", or ``None`` on parse failure."""
    try:
        year_str, q_str = target_quarter.split("-Q")
        year = int(year_str)
        quarter = int(q_str)
        if quarter < 1 or quarter > 4:
            return None
    except (ValueError, AttributeError):
        return None

    start_month = (quarter - 1) * 3 + 1
    end_month = quarter * 3
    start = date(year, start_month, 1)
    if end_month == 12:
        end = date(year, 12, 31)
    else:
        end = date(year, end_month + 1, 1) - timedelta(days=1)
    return start, end


def _safe_mean(values: Iterable[float]) -> Optional[float]:
    materialised = [v for v in values if v and v > 0]
    if not materialised:
        return None
    return mean(materialised)


def _frankfurter_quarter_mean(
    base: str, quote: str, start: date, end: date
) -> Optional[float]:
    try:
        response = requests.get(
            FRANKFURTER_URL,
            params={
                "base": base,
                "symbols": quote,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
            },
            timeout=HTTP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # pragma: no cover - network-dependent
        print(f"[fx] Frankfurter call failed: {exc}")
        return None

    rates_by_date = payload.get("rates") or {}
    daily = (
        float(day_rates.get(quote))
        for day_rates in rates_by_date.values()
        if isinstance(day_rates, dict) and day_rates.get(quote) is not None
    )
    return _safe_mean(daily)


def _ecb_quarter_mean(
    base: str, quote: str, start: date, end: date
) -> Optional[float]:
    """Backup: derive the cross rate from ECB's daily-vs-EUR XML feed."""
    if base == quote:
        return 1.0

    try:
        response = requests.get(ECB_HIST_URL, timeout=HTTP_TIMEOUT_SECONDS)
        response.raise_for_status()
    except Exception as exc:  # pragma: no cover - network-dependent
        print(f"[fx] ECB call failed: {exc}")
        return None

    try:
        root = ET.fromstring(response.text)
    except ET.ParseError as exc:
        print(f"[fx] ECB XML parse failed: {exc}")
        return None

    ns = {"e": "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"}
    cross_rates: list[float] = []
    for day in root.findall(".//e:Cube/e:Cube[@time]", ns):
        try:
            day_date = date.fromisoformat(day.attrib["time"])
        except ValueError:
            continue
        if not (start <= day_date <= end):
            continue
        rates_per_eur: dict[str, float] = {}
        for cube in day.findall("e:Cube", ns):
            ccy = cube.attrib.get("currency")
            rate = cube.attrib.get("rate")
            if ccy and rate:
                try:
                    rates_per_eur[ccy] = float(rate)
                except ValueError:
                    continue
        # ECB feed is "1 EUR -> N <ccy>". Convert to base/quote cross.
        base_per_eur = 1.0 if base == "EUR" else rates_per_eur.get(base)
        quote_per_eur = 1.0 if quote == "EUR" else rates_per_eur.get(quote)
        if base_per_eur and quote_per_eur:
            cross_rates.append(quote_per_eur / base_per_eur)
    return _safe_mean(cross_rates)


@lru_cache(maxsize=128)
def _cached_quarter_average(base: str, quote: str, target_quarter: str) -> Optional[float]:
    if not LIVE_FX:
        return None
    if base == quote:
        return 1.0

    window = _quarter_window(target_quarter)
    if window is None:
        return None
    start, end = window

    rate = _frankfurter_quarter_mean(base, quote, start, end)
    if rate is None:
        rate = _ecb_quarter_mean(base, quote, start, end)
    return rate


def quarter_average(base: str, quote: str, target_quarter: str) -> Optional[float]:
    """Quarter-mean exchange rate (units of ``quote`` per 1 unit of ``base``).

    Returns ``None`` when the rate cannot be sourced — callers MUST treat that
    as "skip the check" rather than substitute a hardcoded constant.
    """
    if not base or not quote or not target_quarter:
        return None
    base = base.upper()
    quote = quote.upper()
    with _lock:
        return _cached_quarter_average(base, quote, target_quarter)


def convert(
    amount: float, from_ccy: str, to_ccy: str, target_quarter: str
) -> Optional[float]:
    """Convert ``amount`` from ``from_ccy`` to ``to_ccy`` at the quarter mean.

    Returns ``None`` if the rate is unavailable.
    """
    if amount is None:
        return None
    rate = quarter_average(from_ccy, to_ccy, target_quarter)
    if rate is None:
        return None
    return amount * rate


def reset_cache() -> None:
    """Test hook — clear the LRU cache between scenarios."""
    _cached_quarter_average.cache_clear()
