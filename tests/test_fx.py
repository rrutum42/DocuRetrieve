"""Currency conversion tests. FrankfurterFx.convert is tested without network by
stubbing the low-level rate fetch; the same-currency and failure paths need no
stub at all.
"""

from __future__ import annotations

from datetime import date

from app.fx import Conversion, FrankfurterFx


def test_same_currency_is_identity_no_network():
    fx = FrankfurterFx()
    c = fx.convert(12.40, "EUR", "EUR", date(2026, 6, 1))
    assert c == Conversion(base_amount=12.40, fx_rate=1.0, fx_date=date(2026, 6, 1))


def test_convert_applies_rate_and_rounds():
    fx = FrankfurterFx()
    fx._fetch_rate = lambda f, t, on: (110.629, date(2026, 6, 1))  # EUR->INR
    c = fx.convert(12.40, "eur", "inr", date(2026, 6, 1))
    assert c is not None
    assert c.fx_rate == 110.629
    assert c.base_amount == round(12.40 * 110.629, 2)
    assert c.fx_date == date(2026, 6, 1)


def test_network_error_returns_none():
    fx = FrankfurterFx()

    def boom(f, t, on):
        raise ConnectionError("frankfurter down")

    fx._fetch_rate = boom
    assert fx.convert(10, "USD", "INR", date(2026, 6, 1)) is None


def test_unsupported_currency_returns_none():
    fx = FrankfurterFx()
    fx._fetch_rate = lambda f, t, on: None  # symbol not in rates
    assert fx.convert(10, "USD", "XYZ", date(2026, 6, 1)) is None


def test_missing_currency_code_returns_none():
    fx = FrankfurterFx()
    assert fx.convert(10, "", "INR", None) is None
