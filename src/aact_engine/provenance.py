"""Snapshot provenance — threaded through every query result.

A capsule must be able to cite the exact AACT data vintage it was built from,
even if the engine is pointed at an older snapshot. The ``Provenance`` is read
from the warehouse ``_meta`` table (not a module constant), so it reflects the
DB actually queried.
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class Provenance:
    snapshot_date: str            # e.g. "2026-04-12" — read from _meta, never guessed
    source: str = "ClinicalTrials.gov via AACT"
    db_path: str | None = None
    extracted_at: str = ""        # ISO timestamp of this extraction

    @staticmethod
    def now_iso() -> str:
        return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def with_extracted_now(self) -> "Provenance":
        return Provenance(
            snapshot_date=self.snapshot_date,
            source=self.source,
            db_path=self.db_path,
            extracted_at=self.now_iso(),
        )

    def to_dict(self) -> dict:
        return asdict(self)


__all__ = ["Provenance"]
