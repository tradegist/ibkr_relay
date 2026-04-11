"""IBKR Webhook Relay CLI — project-specific configuration.

Sets up CoreConfig and exposes IBKR-specific helpers used by
project-specific commands (poll, test_webhook).
"""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from cli.core import CoreConfig, die, env, set_config

PROJECT_DIR = Path(__file__).resolve().parent.parent
PROJECT_NAME = "ibkr-relay"
REMOTE_DIR = f"/opt/{PROJECT_NAME}"


# ── IBKR-specific helpers ───────────────────────────────────────────

def validate_poller_env(suffix=""):
    """Check that poller env vars are set for the given suffix.

    For the primary poller (suffix=""), both IBKR_FLEX_TOKEN and
    IBKR_FLEX_QUERY_ID are required.

    For poller-2 (suffix="_2"), only IBKR_FLEX_QUERY_ID_2 is required.
    IBKR_FLEX_TOKEN_2 is optional — when absent, the primary
    IBKR_FLEX_TOKEN is used (allows two queries under one token).
    """
    if suffix:
        # Poller-2: only the query ID is required
        query_id = os.environ.get(f"IBKR_FLEX_QUERY_ID{suffix}", "").strip()
        if not query_id:
            return False
        # If a dedicated token isn't set, the primary token must exist
        token_2 = os.environ.get(f"IBKR_FLEX_TOKEN{suffix}", "").strip()
        token_1 = os.environ.get("IBKR_FLEX_TOKEN", "").strip()
        if not token_2 and not token_1:
            die(f"Poller{suffix} has IBKR_FLEX_QUERY_ID{suffix} but "
                f"neither IBKR_FLEX_TOKEN{suffix} nor IBKR_FLEX_TOKEN is set")
        return True

    required = ["IBKR_FLEX_TOKEN", "IBKR_FLEX_QUERY_ID"]
    missing = []
    set_count = 0
    for var in required:
        if os.environ.get(var, "").strip():
            set_count += 1
        else:
            missing.append(var)
    if set_count == 0:
        return False
    if missing:
        die(f"Poller partially configured. Missing: {', '.join(missing)}")
    return True


def _compose_profiles():
    profiles = []
    if validate_poller_env("_2"):
        profiles.append("poller2")
    return ",".join(profiles)


def _compose_env():
    """Compute derived env vars for docker compose commands."""
    env_vars: dict[str, str] = {}
    # POLLER_REPLICAS from Makefile (make sync POLLER=0) takes precedence
    replicas = os.environ.get("POLLER_REPLICAS")
    if replicas is not None:
        if replicas not in ("0", "1"):
            die(f"POLLER_REPLICAS must be 0 or 1 (got: {replicas})")
        env_vars["POLLER_REPLICAS"] = replicas
    else:
        poller_enabled = os.environ.get("POLLER_ENABLED", "true")
        if poller_enabled.lower() in ("false", "0", "no", ""):
            env_vars["POLLER_REPLICAS"] = "0"

    # DEBUG_REPLICAS: auto-enable debug service when DEBUG_WEBHOOK_PATH is set
    if os.environ.get("DEBUG_WEBHOOK_PATH", "").strip():
        env_vars["DEBUG_REPLICAS"] = "1"

    return env_vars


def _droplet_size():
    override = os.environ.get("DROPLET_SIZE", "")
    if override:
        return override
    # Poller-only needs minimal resources
    return "s-1vcpu-512mb"


def _pre_sync_hook():
    validate_poller_env("_2")
    from notifier import validate_notifier_env
    validate_notifier_env()
    validate_notifier_env("_2")


_RELAY_URLS: dict[str, str] = {
    "local": "http://localhost:15001",
}

# Local-mode routing: Caddy is disabled, so we replicate its path-based
# routing (poller-2 on a separate port with path rewrite).
_LOCAL_ROUTE_OVERRIDES: list[tuple[str, str, str]] = [
    # (path_prefix, base_url, rewrite_from → rewrite_to)
    ("/ibkr/poller/2/", "http://localhost:15002", "/ibkr/poller/2"),
]


def relay_api(path, method="POST", data=None):
    relay_env = os.environ.get("RELAY_ENV") or os.environ.get("DEFAULT_CLI_RELAY_ENV") or "prod"
    base_url = _RELAY_URLS.get(relay_env)
    if base_url:
        if relay_env == "local":
            # Caddy is disabled locally, so replicate its path-based routing
            for prefix, override_url, rewrite_prefix in _LOCAL_ROUTE_OVERRIDES:
                if path.startswith(prefix):
                    path = path.replace(rewrite_prefix, "/ibkr/poller", 1)
                    base_url = override_url
                    break
        url = f"{base_url}{path}"
    else:
        domain = env("SITE_DOMAIN")
        url = f"https://{domain}{path}"
    token = env("API_TOKEN")
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    if body:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        content = e.read().decode()
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            die(f"Request failed ({e.code}): {content}")


# ── CoreConfig for IBKR project ────────────────────────────────────

_CONFIG = CoreConfig(
    project_name=PROJECT_NAME,
    project_dir=PROJECT_DIR,
    terraform_vars={
        "do_token": "DO_API_TOKEN",
        "droplet_size": "DROPLET_SIZE",
        "site_domain": "SITE_DOMAIN",
    },
    required_env=[
        "DO_API_TOKEN",
        "IBKR_FLEX_TOKEN", "IBKR_FLEX_QUERY_ID",
        "API_TOKEN",
    ],
    service_map={
        "caddy": "caddy",
        "poller": "poller",
        "poller2": "poller-2",
        "poller-2": "poller-2",
        "debug": "ibkr-debug",
        "ibkr-debug": "ibkr-debug",
    },
    compose_profiles_fn=_compose_profiles,
    compose_env_fn=_compose_env,
    size_selector_fn=_droplet_size,
    route_prefix="/ibkr",
    pre_sync_hook=_pre_sync_hook,
)

set_config(_CONFIG)

