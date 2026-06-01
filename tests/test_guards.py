"""Data-quality guards."""
from __future__ import annotations

import duckdb
import pytest

from aact_engine.guards import (
    reject_negated_count, normalize_intervention_type,
    enforce_derived_hr_null_ci, assert_nonempty,
    assert_value_present, cohort_field_notes, COHORT_FIELDS, EFFECT_SELECTION_NOTES,
)


def test_assert_value_present_drift_guard():
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE studies(study_type VARCHAR)")
    con.execute("INSERT INTO studies VALUES ('Interventional'), ('Observational')")
    assert assert_value_present(con, "studies", "study_type", "interventional") == 1
    # a renamed/recased value the snapshot no longer has -> fail closed
    with pytest.raises(ValueError):
        assert_value_present(con, "studies", "study_type", "experimental")


def test_cohort_field_notes_document_filters():
    notes = cohort_field_notes()
    assert len(notes) == len(COHORT_FIELDS)
    assert any("interventional" in n and "EXCLUDES observational" in n for n in notes)
    assert any("non-randomized" in n.lower() for n in notes)


def test_effect_selection_notes_documented():
    assert "one record per trial" in EFFECT_SELECTION_NOTES
    assert "p-value-only" in EFFECT_SELECTION_NOTES


def test_negated_count_rejects():
    text = "Not Randomized 1,807"
    idx = text.index("1,807")
    assert reject_negated_count(text, idx) is True


def test_negated_count_glued_non():
    text = "Non-randomized cohort 1807"
    idx = text.index("1807")
    assert reject_negated_count(text, idx) is True


def test_plain_count_accepted():
    text = "Deaths 1,807"
    idx = text.index("1,807")
    assert reject_negated_count(text, idx) is False


def test_normalize_intervention_type():
    assert normalize_intervention_type("Drug") == "drug"
    assert normalize_intervention_type(None) == ""


def test_derived_hr_nulls_ci():
    lo, hi = enforce_derived_hr_null_ci(-0.18, 0.07, 0.71, 0.97, derived=True)
    assert lo is None and hi is None
    # not derived: CI preserved
    lo2, hi2 = enforce_derived_hr_null_ci(-0.18, 0.07, 0.71, 0.97, derived=False)
    assert lo2 == 0.71 and hi2 == 0.97


def test_assert_nonempty():
    assert assert_nonempty([1], "ctx") == [1]
    with pytest.raises(ValueError):
        assert_nonempty([], "empty cohort")
