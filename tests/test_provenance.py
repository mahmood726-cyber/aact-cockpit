"""Provenance dataclass basics."""
from __future__ import annotations

from aact_engine.provenance import Provenance


def test_roundtrip_and_extracted_stamp():
    p = Provenance(snapshot_date="2026-04-12", db_path="x.duckdb")
    assert p.snapshot_date == "2026-04-12"
    p2 = p.with_extracted_now()
    assert p2.extracted_at.endswith("Z")
    d = p2.to_dict()
    assert d["snapshot_date"] == "2026-04-12"
    assert d["source"].startswith("ClinicalTrials.gov")
