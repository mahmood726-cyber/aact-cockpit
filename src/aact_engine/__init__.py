"""aact_engine — one canonical AACT access layer (DuckDB warehouse).

Public API is filled in as modules land:
    from aact_engine import discover_snapshot_root, Provenance
    from aact_engine import cohort_search, effect_extraction   # added in query.py
"""
from __future__ import annotations

from .paths import discover_snapshot_root, detect_snapshot_date
from .provenance import Provenance
from .contracts import PICO, ArmEffect, EffectRecord, EffectsDataset
from .query import cohort_search, get_outcome_analyses, effect_extraction, open_warehouse

__all__ = [
    "discover_snapshot_root", "detect_snapshot_date", "Provenance",
    "PICO", "ArmEffect", "EffectRecord", "EffectsDataset",
    "cohort_search", "get_outcome_analyses", "effect_extraction", "open_warehouse",
]
