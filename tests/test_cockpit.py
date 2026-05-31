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


def test_build_tsa_rejects_garbage():
    r = client.post("/api/build", json={"effects": {"studies": []}, "kind": "tsa"})
    assert r.status_code == 422


def test_nma_presets_lists_configs():
    r = client.get("/api/nma_presets")
    assert r.status_code == 200
    presets = r.json()["presets"]
    ids = {p["id"] for p in presets}
    # the two shipped NMA configs should be discoverable
    assert "af_anticoag_nma" in ids and "melanoma_os_nma" in ids


def test_build_nma_unknown_preset_404():
    r = client.post("/api/build_nma", json={"preset": "does_not_exist"})
    assert r.status_code == 404
