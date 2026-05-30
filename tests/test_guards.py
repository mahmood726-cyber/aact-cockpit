"""Data-quality guards."""
from __future__ import annotations

import pytest

from aact_engine.guards import (
    reject_negated_count, normalize_intervention_type,
    enforce_derived_hr_null_ci, assert_nonempty,
)


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
