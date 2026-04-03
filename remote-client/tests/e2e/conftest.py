"""E2E test fixtures — httpx client pointed at the local test stack."""

from __future__ import annotations

import httpx
import pytest

BASE_URL = "http://localhost:15000"
API_TOKEN = "test-token"


@pytest.fixture(scope="session")
def api() -> httpx.Client:
    """Shared httpx client with auth header, scoped to the entire test session."""
    with httpx.Client(
        base_url=BASE_URL,
        headers={"Authorization": f"Bearer {API_TOKEN}"},
        timeout=15.0,
    ) as client:
        yield client


@pytest.fixture(scope="session")
def anon_api() -> httpx.Client:
    """Httpx client without auth — for testing 401 responses."""
    with httpx.Client(base_url=BASE_URL, timeout=15.0) as client:
        yield client
