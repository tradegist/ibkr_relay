"""Tests for the pure enrich_trades_with_fx function."""

import tempfile
import unittest
from datetime import date
from pathlib import Path
from typing import Any
from unittest import mock

import httpx

from relay_core.fx.client import FxClient, FxLookupError
from relay_core.fx.enrich import enrich_trades_with_fx
from shared import BuySell, Trade


def _trade(
    order_id: str = "o1",
    currency: str | None = "USD",
    timestamp: str = "2026-04-19T12:00:00Z",
) -> Trade:
    return Trade(
        orderId=order_id, symbol="AAPL", assetClass="equity", side=BuySell.BUY,
        orderType="market", price=100.0, volume=1.0, cost=100.0, fee=1.0,
        fillCount=1, execIds=["e1"], timestamp=timestamp, source="flex",
        currency=currency, raw={},
    )


def _ok_response(data: dict[str, Any]) -> httpx.Response:
    return httpx.Response(
        status_code=200, json=data,
        request=httpx.Request("GET", "https://example/"),
    )


class TestEnrichment(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self._tmp.name) / "meta.db")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # ── Same-currency short-circuit ──

    def test_same_currency_sets_rate_one(self) -> None:
        mock_get = mock.Mock(side_effect=AssertionError("should not be called"))
        client = FxClient(api_key="k", db_path=self.db_path, http_get=mock_get)
        errors: list[str] = []
        (out,) = enrich_trades_with_fx(
            [_trade(currency="EUR")],
            base_currency="EUR", client=client, errors=errors,
        )
        assert out.fxRate == 1.0
        assert out.fxRateBase == "EUR"
        assert out.fxRateSource == "historical"
        assert errors == []

    # ── No-currency short-circuit ──

    def test_no_currency_skips_silently(self) -> None:
        mock_get = mock.Mock(side_effect=AssertionError("should not be called"))
        client = FxClient(api_key="k", db_path=self.db_path, http_get=mock_get)
        errors: list[str] = []
        (out,) = enrich_trades_with_fx(
            [_trade(currency=None)],
            base_currency="EUR", client=client, errors=errors,
        )
        assert out.fxRate is None
        assert errors == []

    # ── Historical path (API key) ──

    def test_historical_populates_fields(self) -> None:
        mock_get = mock.Mock(return_value=_ok_response({
            "result": "success",
            "conversion_rates": {"USD": 1.19},
        }))
        client = FxClient(api_key="k", db_path=self.db_path, http_get=mock_get)
        errors: list[str] = []
        (out,) = enrich_trades_with_fx(
            [_trade(currency="USD", timestamp="2026-04-10T00:00:00Z")],
            base_currency="EUR", client=client, errors=errors,
            today_provider=lambda: date(2026, 4, 19),
        )
        assert out.fxRate is not None
        self.assertAlmostEqual(out.fxRate, 1.0 / 1.19, places=6)
        assert out.fxRateBase == "EUR"
        assert out.fxRateSource == "historical"
        assert errors == []

    def test_historical_failure_appends_error(self) -> None:
        mock_get = mock.Mock(side_effect=httpx.ConnectError("down"))
        client = FxClient(api_key="k", db_path=self.db_path, http_get=mock_get)
        errors: list[str] = []
        (out,) = enrich_trades_with_fx(
            [_trade(order_id="xyz", currency="USD")],
            base_currency="EUR", client=client, errors=errors,
            today_provider=lambda: date(2026, 4, 19),
        )
        assert out.fxRate is None
        assert len(errors) == 1
        assert "xyz" in errors[0]

    # ── Keyless path (no API key) ──

    def test_keyless_historical_trade_skipped_with_error(self) -> None:
        mock_get = mock.Mock(side_effect=AssertionError("should not be called"))
        client = FxClient(api_key=None, db_path=self.db_path, http_get=mock_get)
        errors: list[str] = []
        (out,) = enrich_trades_with_fx(
            [_trade(order_id="old", currency="USD", timestamp="2026-04-10T12:00:00Z")],
            base_currency="EUR", client=client, errors=errors,
            today_provider=lambda: date(2026, 4, 19),
        )
        assert out.fxRate is None
        assert len(errors) == 1
        assert "historical FX unavailable" in errors[0]

    def test_keyless_today_uses_latest(self) -> None:
        mock_get = mock.Mock(return_value=_ok_response({
            "result": "success",
            "rates": {"USD": 1.19},
        }))
        client = FxClient(api_key=None, db_path=self.db_path, http_get=mock_get)
        errors: list[str] = []
        (out,) = enrich_trades_with_fx(
            [_trade(currency="USD", timestamp="2026-04-19T12:00:00Z")],
            base_currency="EUR", client=client, errors=errors,
            today_provider=lambda: date(2026, 4, 19),
        )
        assert out.fxRate is not None
        assert out.fxRateSource == "latest"
        assert errors == []

    # ── Failure isolation ──

    def test_one_bad_trade_does_not_affect_others(self) -> None:
        def http_get(url: str, **_: Any) -> httpx.Response:
            # USD succeeds; XYZ triggers missing-currency failure.
            return _ok_response({
                "result": "success",
                "conversion_rates": {"USD": 1.19},
            })
        client = FxClient(api_key="k", db_path=self.db_path, http_get=http_get)
        errors: list[str] = []
        enriched = enrich_trades_with_fx(
            [
                _trade(order_id="good", currency="USD",
                       timestamp="2026-04-19T00:00:00Z"),
                _trade(order_id="bad", currency="XYZ",
                       timestamp="2026-04-19T00:00:00Z"),
            ],
            base_currency="EUR", client=client, errors=errors,
            today_provider=lambda: date(2026, 4, 19),
        )
        assert enriched[0].fxRate is not None
        assert enriched[1].fxRate is None
        assert len(errors) == 1
        assert "bad" in errors[0]

    # ── Unparseable timestamp ──

    def test_unparseable_timestamp_falls_back_to_latest_with_key(self) -> None:
        """Historical path still attempts with a date=None-ish fallback — here it uses latest."""
        mock_get = mock.Mock(return_value=_ok_response({
            "result": "success",
            "rates": {"USD": 1.19},
        }))
        client = FxClient(api_key="k", db_path=self.db_path, http_get=mock_get)
        errors: list[str] = []
        (out,) = enrich_trades_with_fx(
            [_trade(currency="USD", timestamp="!!!garbage!!!")],
            base_currency="EUR", client=client, errors=errors,
            today_provider=lambda: date(2026, 4, 19),
        )
        # No trade date → skips historical path → hits latest.
        assert out.fxRate is not None
        assert out.fxRateSource == "latest"


class TestEnrichmentErrorPropagation(unittest.TestCase):
    def test_fxlookuperror_from_client_is_captured(self) -> None:
        client = mock.create_autospec(FxClient, instance=True)
        client.has_api_key = True
        client.get_historical_rate.side_effect = FxLookupError("boom")
        errors: list[str] = []
        (out,) = enrich_trades_with_fx(
            [_trade(order_id="x", currency="USD",
                    timestamp="2026-04-18T00:00:00Z")],
            base_currency="EUR", client=client, errors=errors,
            today_provider=lambda: date(2026, 4, 19),
        )
        assert out.fxRate is None
        assert len(errors) == 1
        assert "boom" in errors[0]
