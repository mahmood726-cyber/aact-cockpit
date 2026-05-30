"""Effect extraction must be reproducible: a trial with multiple usable
mortality analyses always yields the same (lowest-id) one, every run."""
from __future__ import annotations

import duckdb
import pytest

from aact_engine.contracts import PICO
from aact_engine.query import get_outcome_analyses, effect_extraction


@pytest.fixture
def multi_analysis_con():
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE _meta(snapshot_date VARCHAR, table_name VARCHAR, row_count BIGINT)")
    con.execute("INSERT INTO _meta VALUES ('2026-04-12','_all',0)")
    con.execute("CREATE TABLE studies(nct_id VARCHAR, study_type VARCHAR, overall_status VARCHAR, "
                "phase VARCHAR, enrollment VARCHAR, brief_title VARCHAR, official_title VARCHAR, "
                "start_date VARCHAR, results_first_posted_date VARCHAR, number_of_arms VARCHAR)")
    con.execute("INSERT INTO studies VALUES ('NCTX','Interventional','Completed','Phase 3','2000',"
                "'t','Trial X','2018-01-01','2021-01-01','2')")
    con.execute("CREATE TABLE outcomes(id VARCHAR, nct_id VARCHAR, outcome_type VARCHAR, title VARCHAR, param_type VARCHAR)")
    con.execute("INSERT INTO outcomes VALUES ('1','NCTX','Primary','All-cause mortality','Number'),"
                "('2','NCTX','Secondary','All-cause mortality subgroup','Number')")
    # two usable HR analyses for the same trial, different ids + different HRs
    con.execute("CREATE TABLE outcome_analyses(id VARCHAR, nct_id VARCHAR, outcome_id VARCHAR, "
                "param_type VARCHAR, param_value VARCHAR, p_value VARCHAR, ci_n_sides VARCHAR, "
                "ci_percent VARCHAR, ci_lower_limit VARCHAR, ci_upper_limit VARCHAR, method VARCHAR)")
    con.execute("INSERT INTO outcome_analyses VALUES "
                "('900','NCTX','2','Hazard Ratio (HR)','1.05','0.5','TWO_SIDED','95.0','0.83','1.32','Cox Proportional Hazards'),"
                "('100','NCTX','1','Hazard Ratio (HR)','0.84','0.02','TWO_SIDED','95.0','0.73','0.97','Cox Proportional Hazards')")
    con.execute("CREATE TABLE outcome_analysis_groups(id VARCHAR, nct_id VARCHAR, outcome_analysis_id VARCHAR, result_group_id VARCHAR)")
    con.execute("INSERT INTO outcome_analysis_groups VALUES ('1','NCTX','100','501'),('2','NCTX','100','502'),"
                "('3','NCTX','900','501'),('4','NCTX','900','502')")
    con.execute("CREATE TABLE result_groups(id VARCHAR, nct_id VARCHAR, ctgov_group_code VARCHAR, "
                "result_type VARCHAR, title VARCHAR, outcome_id VARCHAR)")
    con.execute("INSERT INTO result_groups VALUES ('501','NCTX','OG000','Outcome','Drug','1'),"
                "('502','NCTX','OG001','Outcome','Placebo','1')")
    yield con
    con.close()


def test_lowest_id_analysis_selected(multi_analysis_con):
    pico = PICO(population="x", outcome="all-cause mortality")
    ds = effect_extraction(["NCTX"], pico=pico,
                           primary_estimand="HR for all-cause mortality",
                           endpoint="acm", con=multi_analysis_con)
    assert ds.n_studies == 1
    rec = ds.records[0]
    # lowest id (100, HR 0.84) wins, not 900 (HR 1.05)
    assert rec.source_outcome_analysis_id == "100"
    assert rec.point_estimate == 0.84


def test_repeated_runs_identical(multi_analysis_con):
    rows1 = get_outcome_analyses(["NCTX"], con=multi_analysis_con)
    rows2 = get_outcome_analyses(["NCTX"], con=multi_analysis_con)
    order1 = [r["outcome_analysis_id"] for r in rows1]
    order2 = [r["outcome_analysis_id"] for r in rows2]
    assert order1 == order2 == ["100", "900"]  # deterministic ascending id
