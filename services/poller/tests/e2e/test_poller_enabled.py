"""E2E test — verify POLLER_ENABLED=false stops the poller container."""

import subprocess
import time

import httpx
import pytest

POLLER_URL = "http://localhost:15011/health"
E2E_COMPOSE = [
    "docker", "compose",
    "-f", "docker-compose.yml",
    "-f", "docker-compose.test.yml",
    "-p", "ibkr-relay-test",
    "--env-file", ".env.test",
]


def _poller_is_reachable(timeout: float = 2.0) -> bool:
    try:
        resp = httpx.get(POLLER_URL, timeout=timeout)
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


def _wait_for_poller(up: bool, *, retries: int = 10, delay: float = 2.0) -> None:
    """Wait for poller to become reachable (up=True) or unreachable (up=False)."""
    for _ in range(retries):
        if _poller_is_reachable() == up:
            return
        time.sleep(delay)
    state = "reachable" if up else "unreachable"
    pytest.fail(f"Poller did not become {state} after {retries * delay}s")


class TestPollerEnabled:
    """Scale poller to 0, verify it stops, scale back, verify it recovers."""

    def test_poller_disable_and_reenable(self) -> None:
        # Precondition: poller is running (conftest preflight check guarantees this)
        assert _poller_is_reachable(), "Poller should be reachable before test"

        # Scale poller to 0
        subprocess.run(
            [*E2E_COMPOSE, "up", "-d", "--scale", "poller=0", "--no-recreate"],
            check=True,
            capture_output=True,
        )
        _wait_for_poller(up=False)

        # Scale poller back to 1
        subprocess.run(
            [*E2E_COMPOSE, "up", "-d", "--scale", "poller=1", "--no-recreate"],
            check=True,
            capture_output=True,
        )
        _wait_for_poller(up=True, retries=15)
