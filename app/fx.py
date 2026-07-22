"""Currency conversion via Frankfurter (ECB daily reference rates).

Free, no API key, historical dates supported. We snapshot the conversion at save
time — the rate for the receipt's own date — so a receipt's home-currency value
is locked in, reproducible, and survives the FX service being unavailable later.

Conversion never raises to the caller: on any failure (unsupported currency,
network error, unknown date) it returns None, and the receipt is stored with its
native amount only, flagged "not converted".
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from datetime import date
from typing import Protocol

BASE_URL = "https://api.frankfurter.dev/v1"
HTTP_TIMEOUT = 12
# Frankfurter's edge (Cloudflare) 403s the default urllib User-Agent, so set one.
USER_AGENT = "DocuRetrieve/0.1 (receipt ledger)"


@dataclass
class Conversion:
    base_amount: float
    fx_rate: float
    fx_date: date | None  # the date whose rate was actually used


class FxService(Protocol):
    def convert(
        self, amount: float, from_currency: str, to_currency: str, on: date | None
    ) -> Conversion | None: ...


def _round2(x: float) -> float:
    return round(x + 0.0, 2)


class FrankfurterFx:
    """Live conversion against api.frankfurter.dev."""

    def _fetch_rate(
        self, from_cur: str, to_cur: str, on: date | None
    ) -> tuple[float, date] | None:
        when = on.isoformat() if on else "latest"
        url = f"{BASE_URL}/{when}?base={from_cur}&symbols={to_cur}"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            payload = json.loads(resp.read())
        rate = (payload.get("rates") or {}).get(to_cur)
        if rate is None:
            return None
        eff_raw = payload.get("date")
        eff = date.fromisoformat(eff_raw) if eff_raw else None
        return float(rate), eff

    def convert(
        self, amount: float, from_currency: str, to_currency: str, on: date | None
    ) -> Conversion | None:
        from_cur = (from_currency or "").upper()
        to_cur = (to_currency or "").upper()
        if not from_cur or not to_cur:
            return None
        if from_cur == to_cur:
            return Conversion(base_amount=_round2(amount), fx_rate=1.0, fx_date=on)
        try:
            result = self._fetch_rate(from_cur, to_cur, on)
        except Exception:
            return None
        if result is None:
            return None
        rate, eff = result
        return Conversion(base_amount=_round2(amount * rate), fx_rate=rate, fx_date=eff)


class NoopFx:
    """Never converts (used when we deliberately want native-only storage)."""

    def convert(self, amount, from_currency, to_currency, on):  # noqa: D401
        return None
