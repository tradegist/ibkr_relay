"""Notifier registry — load, validate, and dispatch to configured backends."""

import logging
import os

from pydantic import BaseModel

from .base import BaseNotifier
from .webhook import WebhookNotifier

log = logging.getLogger("notifier")

REGISTRY: dict[str, type[BaseNotifier]] = {
    "webhook": WebhookNotifier,
}


def _get_notifiers_config(suffix: str) -> str:
    return os.environ.get(f"NOTIFIERS{suffix}", "").strip()


def load_notifiers(suffix: str = "") -> list[BaseNotifier]:
    """Read NOTIFIERS env var, instantiate backends, return ready list.

    Each backend validates its own configuration in ``__init__``.

    Args:
        suffix: Env var suffix for multi-instance support (e.g. "_2").
                Applied to both NOTIFIERS and each backend's required vars.

    Returns:
        List of ready-to-use notifier instances. Empty list = dry-run mode.

    Raises:
        SystemExit: If a notifier name is unknown or a backend rejects its config.
    """
    raw = _get_notifiers_config(suffix)
    if not raw:
        log.info("No notifiers configured (NOTIFIERS%s is empty) — dry-run mode", suffix)
        _warn_orphaned_notifier_vars(suffix)
        return []

    names = [n.strip() for n in raw.split(",") if n.strip()]
    notifiers: list[BaseNotifier] = []

    for name in names:
        cls = REGISTRY.get(name)
        if cls is None:
            msg = (
                f"Unknown notifier {name!r} in NOTIFIERS{suffix}. "
                f"Available: {', '.join(REGISTRY)}"
            )
            log.error("%s", msg)
            raise SystemExit(msg)

        notifiers.append(cls(suffix=suffix))
        log.info("Loaded notifier: %s%s", name, suffix or "")

    return notifiers


def _warn_orphaned_notifier_vars(suffix: str = "") -> None:
    """Warn if any registered notifier's env vars are set but NOTIFIERS is empty."""
    for name, cls in REGISTRY.items():
        orphaned = [
            f"{var}{suffix}"
            for var in cls.required_env_vars()
            if os.environ.get(f"{var}{suffix}", "").strip()
        ]
        if orphaned:
            log.warning(
                "NOTIFIERS%s is empty but %s env vars are set: %s. "
                "Add NOTIFIERS%s=%s to enable delivery, "
                "or remove them to silence this warning.",
                suffix, name, ", ".join(orphaned), suffix, name,
            )


def validate_notifier_env(suffix: str = "") -> bool:
    """Check whether NOTIFIERS env vars are valid by instantiating backends.

    Returns True if NOTIFIERS is set and all backends accept their config.
    Returns False if NOTIFIERS is empty (no notifiers configured).
    Calls die() if a backend rejects its config (missing env vars).

    Designed for CLI pre-deploy validation (cli/_pre_sync_hook).
    """
    raw = _get_notifiers_config(suffix)
    if not raw:
        # Warn if notifier env vars are set but NOTIFIERS is empty —
        # likely a misconfiguration after the notifier migration.
        _warn_orphaned_notifier_vars(suffix)
        return False

    names = [n.strip() for n in raw.split(",") if n.strip()]

    for name in names:
        cls = REGISTRY.get(name)
        if cls is None:
            return False  # unknown notifier — let runtime error handle it

        try:
            cls(suffix=suffix)
        except SystemExit as exc:
            from cli.core import die  # lazy: cli/ not available in Docker containers
            detail = str(exc) if str(exc) else f"Notifier {name!r} partially configured"
            die(f"{detail} — check env vars")

    return True


def notify(notifiers: list[BaseNotifier], payload: BaseModel) -> None:
    """Dispatch payload to all configured notifiers."""
    if not notifiers:
        log.info("No notifiers configured — skipping notification")
        return

    for notifier in notifiers:
        try:
            notifier.send(payload)
        except Exception:
            log.exception(
                "Notifier %s failed while dispatching payload",
                type(notifier).__name__,
            )
