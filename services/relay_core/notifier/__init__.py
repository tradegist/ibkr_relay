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


def _get_notifiers_config(prefix: str, suffix: str) -> str:
    """Read ``{prefix}NOTIFIERS{suffix}``, falling back to ``NOTIFIERS{suffix}``."""
    val = os.environ.get(f"{prefix}NOTIFIERS{suffix}", "").strip()
    if val:
        return val
    return os.environ.get(f"NOTIFIERS{suffix}", "").strip()


def load_notifiers(prefix: str = "", suffix: str = "") -> list[BaseNotifier]:
    """Read NOTIFIERS env var, instantiate backends, return ready list.

    Each backend validates its own configuration in ``__init__``.

    Args:
        prefix: Relay-specific prefix (e.g. ``"IBKR_"``).  Each var is
                tried as ``{prefix}{var}{suffix}`` first, falling back
                to ``{var}{suffix}`` when the prefixed version is unset.
        suffix: Env var suffix for multi-instance support (e.g. "_2").

    Returns:
        List of ready-to-use notifier instances. Empty list = dry-run mode.

    Raises:
        SystemExit: If a notifier name is unknown or a backend rejects its config.
    """
    label = f"{prefix}NOTIFIERS{suffix}" if prefix else f"NOTIFIERS{suffix}"
    raw = _get_notifiers_config(prefix, suffix)
    if not raw:
        log.info("No notifiers configured (%s is empty) — dry-run mode", label)
        _warn_orphaned_notifier_vars(prefix, suffix)
        return []

    names = [n.strip() for n in raw.split(",") if n.strip()]
    notifiers: list[BaseNotifier] = []

    for name in names:
        cls = REGISTRY.get(name)
        if cls is None:
            msg = (
                f"Unknown notifier {name!r} in {label}. "
                f"Available: {', '.join(REGISTRY)}"
            )
            log.error("%s", msg)
            raise SystemExit(msg)

        notifiers.append(cls(prefix=prefix, suffix=suffix))
        log.info("Loaded notifier: %s (prefix=%s, suffix=%s)", name, prefix or "-", suffix or "-")

    return notifiers


def _warn_orphaned_notifier_vars(prefix: str = "", suffix: str = "") -> None:
    """Warn if any registered notifier's env vars are set but NOTIFIERS is empty."""
    label = f"{prefix}NOTIFIERS{suffix}" if prefix else f"NOTIFIERS{suffix}"
    for name, cls in REGISTRY.items():
        orphaned: list[str] = []
        for var in cls.required_env_vars():
            prefixed = f"{prefix}{var}{suffix}"
            generic = f"{var}{suffix}"
            if (os.environ.get(prefixed, "").strip()
                    or os.environ.get(generic, "").strip()):
                orphaned.append(prefixed if prefix else generic)
        if orphaned:
            log.warning(
                "%s is empty but %s env vars are set: %s. "
                "Add %s=%s to enable delivery, "
                "or remove them to silence this warning.",
                label, name, ", ".join(orphaned), label, name,
            )


def validate_notifier_env(prefix: str = "", suffix: str = "") -> bool:
    """Check whether NOTIFIERS env vars are valid by instantiating backends.

    Returns True if NOTIFIERS is set and all backends accept their config.
    Returns False if NOTIFIERS is empty (no notifiers configured).
    Calls die() if a backend rejects its config (missing env vars).

    Designed for CLI pre-deploy validation (cli/_pre_sync_hook).
    """
    raw = _get_notifiers_config(prefix, suffix)
    if not raw:
        # Warn if notifier env vars are set but NOTIFIERS is empty —
        # likely a misconfiguration after the notifier migration.
        _warn_orphaned_notifier_vars(prefix, suffix)
        return False

    names = [n.strip() for n in raw.split(",") if n.strip()]

    for name in names:
        cls = REGISTRY.get(name)
        if cls is None:
            return False  # unknown notifier — let runtime error handle it

        try:
            cls(prefix=prefix, suffix=suffix)
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
