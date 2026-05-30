"""Cockpit smoke test: app imports, index serves, health responds.

Warehouse-dependent endpoints (effects/build) are exercised in the E2E recipe
and the Overmind nightly; here we keep it environment-independent."""
from __future__ import annotations

import pytest

pytest.importorskip("httpx")  # FastAPI TestClient dependency
from fastapi.testclient import TestClient

from aact_cockpit.cockpit.app import app

client = TestClient(app, raise_server_exceptions=False)


def test_index_serves():
    r = client.get("/")
    assert r.status_code == 200
    assert "AACT Cockpit" in r.text


def test_health_responds():
    r = client.get("/api/health")
    # 200 if the warehouse is built, 503 (fail-closed) if not — both are valid.
    assert r.status_code in (200, 503)
    if r.status_code == 200:
        assert "snapshot_date" in r.json()


def test_build_rejects_garbage():
    r = client.post("/api/build", json={"effects": {"studies": []}, "method": "PM"})
    assert r.status_code == 422  # CapsuleInputError -> missing pico/snapshot_date
