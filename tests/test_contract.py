"""Freeze the engine->capsule integration contract field names."""
from __future__ import annotations

from aact_engine.contracts import (
    EFFECT_RECORD_FIELDS, EFFECTS_DATASET_FIELDS, PICO, EffectsDataset,
)
from aact_engine.provenance import Provenance


def test_effect_record_fields_frozen():
    assert EFFECT_RECORD_FIELDS == {
        "nct_id", "study_label", "year", "endpoint", "measure_type",
        "point_estimate", "ci_lower", "ci_upper", "ci_percent", "yi", "sei",
        "derived", "source_nct_id", "source_outcome_id",
        "source_outcome_analysis_id", "source_method",
        "arm_experimental", "arm_comparator",
    }
    # explicitly forbid drifted names
    assert "ci_lo" not in EFFECT_RECORD_FIELDS
    assert "nct" not in EFFECT_RECORD_FIELDS


def test_effects_dataset_fields_frozen():
    assert EFFECTS_DATASET_FIELDS == {
        "records", "provenance", "pico", "primary_estimand",
        "measure", "n_studies", "notes",
    }


def test_dataset_to_dict_shape():
    ds = EffectsDataset(
        records=[], provenance=Provenance(snapshot_date="2026-04-12"),
        pico=PICO(population="heart failure", outcome="all-cause mortality"),
        primary_estimand="hazard ratio for all-cause mortality",
        measure="HR", n_studies=0,
    )
    d = ds.to_dict()
    assert d["snapshot_date"] == "2026-04-12"
    assert set(d) >= {"pico", "primary_estimand", "measure", "snapshot_date",
                      "provenance", "n_studies", "studies", "notes"}
