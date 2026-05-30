"""Query API against the in-memory AACT fixture (conftest.aact_con)."""
from __future__ import annotations

from aact_engine.contracts import PICO
from aact_engine.query import cohort_search, get_outcome_analyses, effect_extraction


def test_cohort_excludes_observational(aact_con):
    res = cohort_search(PICO(population="heart failure", outcome="all-cause mortality"),
                        con=aact_con)
    ncts = {t["nct_id"] for t in res["trials"]}
    assert "NCT01000001" in ncts and "NCT01000002" in ncts
    assert "NCT09999999" not in ncts  # observational, no results posted
    assert res["provenance"]["snapshot_date"] == "2026-04-12"


def test_outcome_analyses_drops_pvalue_only(aact_con):
    rows = get_outcome_analyses(["NCT01000001", "NCT01000002"], con=aact_con)
    ids = {r["outcome_analysis_id"] for r in rows}
    assert "100" in ids and "200" in ids
    assert "300" not in ids  # p-value-only row dropped at SQL level
    # arm titles present
    r100 = next(r for r in rows if r["outcome_analysis_id"] == "100")
    assert "Dapagliflozin" in r100["arm_titles"] and "Placebo" in r100["arm_titles"]


def test_effect_extraction_nonempty_with_provenance(aact_con):
    ds = effect_extraction(
        ["NCT01000001", "NCT01000002"],
        pico=PICO(population="heart failure", outcome="all-cause mortality"),
        primary_estimand="hazard ratio for all-cause mortality",
        endpoint="acm", con=aact_con,
    )
    assert ds.n_studies == 2
    assert ds.measure == "HR"
    assert ds.provenance.snapshot_date == "2026-04-12"
    # arm split: comparator should be Placebo
    rec = next(r for r in ds.records if r.nct_id == "NCT01000001")
    assert rec.arm_comparator.label == "Placebo"
    assert rec.arm_experimental.label == "Dapagliflozin"
    # dataset serializes cleanly
    d = ds.to_dict()
    assert d["n_studies"] == 2 and len(d["studies"]) == 2
