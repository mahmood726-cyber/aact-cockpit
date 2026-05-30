"""Shared pytest fixtures: a tiny in-memory DuckDB AACT fixture (no F: drive
needed) so engine tests run anywhere and fast.

The fixture mirrors the real schema for the MVP tables and includes deliberate
edge cases:
  - one clean cardiology all-cause-mortality trial with a real-shaped HR row
  - one p-value-only analysis row (no estimate) that MUST be skipped
  - one crafted "Not Randomized 1,807" disposition string for the negated-count guard
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make src/ importable without an editable install.
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

SNAPSHOT_DATE = "2026-04-12"


@pytest.fixture
def aact_con():
    """In-memory DuckDB with minimal MVP tables + a _meta provenance row."""
    import duckdb

    con = duckdb.connect(":memory:")

    con.execute(
        "CREATE TABLE _meta (snapshot_date VARCHAR, table_name VARCHAR, row_count BIGINT)"
    )
    con.execute(
        "INSERT INTO _meta VALUES (?, '_all', 0)", [SNAPSHOT_DATE]
    )

    # studies: two HF mortality RCTs with results posted, one non-RCT to exclude
    con.execute("""
        CREATE TABLE studies (
            nct_id VARCHAR, study_type VARCHAR, overall_status VARCHAR, phase VARCHAR,
            enrollment VARCHAR, brief_title VARCHAR, official_title VARCHAR,
            start_date VARCHAR, results_first_posted_date VARCHAR, number_of_arms VARCHAR
        )
    """)
    con.executemany(
        "INSERT INTO studies VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            ("NCT01000001", "Interventional", "Completed", "Phase 3", "2400",
             "Drug A in heart failure", "Drug A vs placebo in HFrEF",
             "2017-01-01", "2020-06-01", "2"),
            ("NCT01000002", "Interventional", "Completed", "Phase 3", "2100",
             "Drug A in heart failure 2", "Drug A vs placebo in HFrEF II",
             "2018-01-01", "2021-06-01", "2"),
            ("NCT09999999", "Observational", "Completed", "N/A", "500",
             "Registry of HF", "Observational HF registry",
             "2015-01-01", None, "1"),
        ],
    )

    con.execute("""
        CREATE TABLE designs (
            id VARCHAR, nct_id VARCHAR, allocation VARCHAR,
            intervention_model VARCHAR, primary_purpose VARCHAR
        )
    """)
    con.executemany(
        "INSERT INTO designs VALUES (?,?,?,?,?)",
        [
            ("1", "NCT01000001", "Randomized", "Parallel Assignment", "Treatment"),
            ("2", "NCT01000002", "Randomized", "Parallel Assignment", "Treatment"),
            ("3", "NCT09999999", "N/A", "N/A", "N/A"),
        ],
    )

    con.execute("CREATE TABLE conditions (id VARCHAR, nct_id VARCHAR, name VARCHAR, downcase_name VARCHAR)")
    con.executemany(
        "INSERT INTO conditions VALUES (?,?,?,?)",
        [
            ("1", "NCT01000001", "Heart Failure", "heart failure"),
            ("2", "NCT01000002", "Heart Failure", "heart failure"),
            ("3", "NCT09999999", "Heart Failure", "heart failure"),
        ],
    )

    con.execute("CREATE TABLE interventions (id VARCHAR, nct_id VARCHAR, intervention_type VARCHAR, name VARCHAR)")
    con.executemany(
        "INSERT INTO interventions VALUES (?,?,?,?)",
        [
            ("1", "NCT01000001", "drug", "Dapagliflozin 10 mg"),
            ("2", "NCT01000001", "drug", "Placebo"),
            ("3", "NCT01000002", "drug", "Dapagliflozin 10 mg"),
            ("4", "NCT01000002", "drug", "Placebo"),
        ],
    )

    con.execute("CREATE TABLE outcomes (id VARCHAR, nct_id VARCHAR, outcome_type VARCHAR, title VARCHAR, param_type VARCHAR)")
    con.executemany(
        "INSERT INTO outcomes VALUES (?,?,?,?,?)",
        [
            ("10", "NCT01000001", "Primary", "All-cause mortality", "Number"),
            ("20", "NCT01000002", "Primary", "Death from any cause", "Number"),
        ],
    )

    con.execute("""
        CREATE TABLE outcome_analyses (
            id VARCHAR, nct_id VARCHAR, outcome_id VARCHAR, param_type VARCHAR,
            param_value VARCHAR, p_value VARCHAR, ci_n_sides VARCHAR, ci_percent VARCHAR,
            ci_lower_limit VARCHAR, ci_upper_limit VARCHAR, method VARCHAR
        )
    """)
    con.executemany(
        "INSERT INTO outcome_analyses VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [
            # clean HR row with CI
            ("100", "NCT01000001", "10", "Hazard Ratio (HR)", "0.83", "0.015",
             "TWO_SIDED", "95.0", "0.71", "0.97", "Cox Proportional Hazards"),
            ("200", "NCT01000002", "20", "Hazard Ratio (HR)", "0.74", "0.008",
             "TWO_SIDED", "95.0", "0.60", "0.92", "Cox Proportional Hazards"),
            # p-value-only row (no estimate) — must be skipped
            ("300", "NCT01000001", "10", None, None, "0.42",
             "TWO_SIDED", "95.0", None, None, "Log Rank"),
        ],
    )

    con.execute("""
        CREATE TABLE outcome_analysis_groups (
            id VARCHAR, nct_id VARCHAR, outcome_analysis_id VARCHAR, result_group_id VARCHAR
        )
    """)
    con.executemany(
        "INSERT INTO outcome_analysis_groups VALUES (?,?,?,?)",
        [
            ("1", "NCT01000001", "100", "501"),
            ("2", "NCT01000001", "100", "502"),
            ("3", "NCT01000002", "200", "601"),
            ("4", "NCT01000002", "200", "602"),
        ],
    )

    con.execute("""
        CREATE TABLE result_groups (
            id VARCHAR, nct_id VARCHAR, ctgov_group_code VARCHAR, result_type VARCHAR,
            title VARCHAR, outcome_id VARCHAR
        )
    """)
    con.executemany(
        "INSERT INTO result_groups VALUES (?,?,?,?,?,?)",
        [
            ("501", "NCT01000001", "OG000", "Outcome", "Dapagliflozin", "10"),
            ("502", "NCT01000001", "OG001", "Outcome", "Placebo", "10"),
            ("601", "NCT01000002", "OG000", "Outcome", "Dapagliflozin", "20"),
            ("602", "NCT01000002", "OG001", "Outcome", "Placebo", "20"),
        ],
    )

    yield con
    con.close()
