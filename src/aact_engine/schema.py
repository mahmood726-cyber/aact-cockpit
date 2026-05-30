"""Single source of truth for AACT table structure and the DuckDB read dialect.

Verified against the F:\\AACT-storage\\AACT\\2026-04-12 snapshot (2026-05-29):
the flat files are *quoted CSV* with a ``|`` delimiter (text fields contain
embedded ``|`` and newlines inside ``"`` quotes), NOT raw pipe-delimited text.
Reading them with ``quote='', escape=''`` fails; the dialect below reads all 12
MVP tables with row counts matching ``wc -l - 1`` exactly.
"""
from __future__ import annotations

# DuckDB read_csv options shared by ingest + any ad-hoc read.
# all_varchar: keep everything as text and cast deliberately downstream
#   (mirrors the proven pandas dtype=str discipline; avoids 3.x type inference drift).
READ_CSV_OPTS: dict[str, object] = {
    "delim": "|",
    "header": True,
    "quote": '"',
    "escape": '"',
    "all_varchar": True,
    "sample_size": -1,
}

# Tables required for the MVP (cardiology mortality pairwise MA). The three
# ~2.9 GB tables (reported_events, outcome_measurements, design_outcomes) are
# deferred and ingested lazily only when a vertical needs them.
MVP_TABLES: tuple[str, ...] = (
    "studies",
    "conditions",
    "interventions",
    "designs",
    "design_groups",
    "sponsors",
    "eligibilities",
    "outcomes",
    "outcome_analyses",
    "outcome_analysis_groups",
    "result_groups",
    "calculated_values",
)

# Large tables ingested only on demand.
BIG_TABLES: frozenset[str] = frozenset(
    {"reported_events", "outcome_measurements", "design_outcomes", "baseline_measurements"}
)

# Columns the engine actually relies on, per table. Used by assert_columns_exist
# as a header-drift guard before any SELECT (AACT column names shift between
# snapshots). Not exhaustive of the file — only the columns we query.
REQUIRED_COLUMNS: dict[str, tuple[str, ...]] = {
    "studies": (
        "nct_id", "study_type", "overall_status", "phase", "enrollment",
        "brief_title", "official_title", "start_date", "results_first_posted_date",
        "number_of_arms",
    ),
    "conditions": ("id", "nct_id", "name", "downcase_name"),
    "interventions": ("id", "nct_id", "intervention_type", "name"),
    "designs": ("id", "nct_id", "allocation", "intervention_model", "primary_purpose"),
    "design_groups": ("id", "nct_id", "group_type", "title"),
    "sponsors": ("id", "nct_id", "agency_class", "lead_or_collaborator", "name"),
    "eligibilities": ("id", "nct_id", "gender", "minimum_age", "maximum_age", "criteria"),
    "outcomes": ("id", "nct_id", "outcome_type", "title", "param_type"),
    "outcome_analyses": (
        "id", "nct_id", "outcome_id", "param_type", "param_value",
        "p_value", "ci_n_sides", "ci_percent", "ci_lower_limit", "ci_upper_limit",
        "method",
    ),
    "outcome_analysis_groups": ("id", "nct_id", "outcome_analysis_id", "result_group_id"),
    "result_groups": ("id", "nct_id", "ctgov_group_code", "result_type", "title", "outcome_id"),
    "calculated_values": ("nct_id",),
}

__all__ = ["READ_CSV_OPTS", "MVP_TABLES", "BIG_TABLES", "REQUIRED_COLUMNS"]
