"""Unit tests for notifier registry, loader, and dispatcher."""

from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from relay_core.notifier import REGISTRY, load_notifiers, notify
from relay_core.notifier.webhook import WebhookNotifier


class _SamplePayload(BaseModel):
    symbol: str


class TestRegistry:
    def test_webhook_registered(self) -> None:
        assert "webhook" in REGISTRY

    def test_registry_values_are_classes(self) -> None:
        from relay_core.notifier.base import BaseNotifier

        for cls in REGISTRY.values():
            assert issubclass(cls, BaseNotifier)


class TestLoadNotifiers:
    def test_empty_env_returns_empty(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            result = load_notifiers()
        assert result == []

    def test_blank_env_returns_empty(self) -> None:
        with patch.dict("os.environ", {"NOTIFIERS": "  "}, clear=True):
            result = load_notifiers()
        assert result == []

    def test_unknown_name_exits(self) -> None:
        with patch.dict("os.environ", {"NOTIFIERS": "bogus"}, clear=True), \
             pytest.raises(SystemExit):
            load_notifiers()

    def test_missing_required_vars_exits(self) -> None:
        with patch.dict("os.environ", {"NOTIFIERS": "webhook"}, clear=True), \
             pytest.raises(SystemExit):
            load_notifiers()

    def test_valid_config_returns_instances(self) -> None:
        env = {
            "NOTIFIERS": "webhook",
            "TARGET_WEBHOOK_URL": "https://example.com/hook",
            "WEBHOOK_SECRET": "s",
        }
        with patch.dict("os.environ", env, clear=True):
            result = load_notifiers()
        assert len(result) == 1
        assert result[0].name == "webhook"

    def test_suffix_reads_suffixed_vars(self) -> None:
        env = {
            "NOTIFIERS_2": "webhook",
            "TARGET_WEBHOOK_URL_2": "https://example.com/hook2",
            "WEBHOOK_SECRET_2": "secret2",
        }
        with patch.dict("os.environ", env, clear=True):
            result = load_notifiers(suffix="_2")
        assert len(result) == 1

    def test_prefix_reads_prefixed_vars(self) -> None:
        env = {
            "IBKR_NOTIFIERS": "webhook",
            "IBKR_TARGET_WEBHOOK_URL": "https://example.com/ibkr",
            "IBKR_WEBHOOK_SECRET": "ibkr-secret",
        }
        with patch.dict("os.environ", env, clear=True):
            result = load_notifiers(prefix="IBKR_")
        assert len(result) == 1
        assert result[0].name == "webhook"

    def test_prefix_falls_back_to_generic(self) -> None:
        """IBKR_NOTIFIERS unset → falls back to NOTIFIERS."""
        env = {
            "NOTIFIERS": "webhook",
            "TARGET_WEBHOOK_URL": "https://example.com/hook",
            "WEBHOOK_SECRET": "s",
        }
        with patch.dict("os.environ", env, clear=True):
            result = load_notifiers(prefix="IBKR_")
        assert len(result) == 1

    def test_prefix_overrides_generic(self) -> None:
        """IBKR_NOTIFIERS is set → generic NOTIFIERS is ignored."""
        env = {
            "NOTIFIERS": "webhook",
            "TARGET_WEBHOOK_URL": "https://generic.com",
            "WEBHOOK_SECRET": "generic-s",
            "IBKR_NOTIFIERS": "webhook",
            "IBKR_TARGET_WEBHOOK_URL": "https://ibkr.com",
            "IBKR_WEBHOOK_SECRET": "ibkr-s",
        }
        with patch.dict("os.environ", env, clear=True):
            result = load_notifiers(prefix="IBKR_")
        assert len(result) == 1
        # The notifier should have used the IBKR-prefixed URL
        assert cast(WebhookNotifier, result[0])._url == "https://ibkr.com"

    def test_prefix_plus_suffix(self) -> None:
        """Prefix and suffix compose: IBKR_TARGET_WEBHOOK_URL_2."""
        env = {
            "IBKR_NOTIFIERS_2": "webhook",
            "IBKR_TARGET_WEBHOOK_URL_2": "https://ibkr-2.com",
            "IBKR_WEBHOOK_SECRET_2": "ibkr-s-2",
        }
        with patch.dict("os.environ", env, clear=True):
            result = load_notifiers(prefix="IBKR_", suffix="_2")
        assert len(result) == 1

    def test_prefix_empty_falls_back_to_generic_dry_run(self) -> None:
        """Prefix set but no IBKR_NOTIFIERS and no NOTIFIERS → dry-run."""
        with patch.dict("os.environ", {}, clear=True):
            result = load_notifiers(prefix="IBKR_")
        assert result == []


class TestNotify:
    def test_dispatches_to_all(self) -> None:
        n1 = MagicMock()
        n2 = MagicMock()
        payload = _SamplePayload(symbol="AAPL")

        notify([n1, n2], payload)

        n1.send.assert_called_once_with(payload)
        n2.send.assert_called_once_with(payload)

    def test_empty_list_is_noop(self) -> None:
        notify([], _SamplePayload(symbol="AAPL"))  # should not raise
