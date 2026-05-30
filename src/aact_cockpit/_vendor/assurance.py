"""Vendored compute_tier from F:\\E156\\scripts\\build_assurance_jsons.py.
Keep in sync. Bronze/Silver/Gold rule per the e156 Assurance Standard.
"""
from __future__ import annotations

PASS_OR_NOT_RUN = frozenset({"pass", "not-run"})


def compute_tier(checks: dict) -> str:
    """Any single 'fail' -> none (honest under-claiming).
    Bronze = citation_cascade != fail AND data_file_present == pass AND code_runs in {pass,not-run}
    Silver = Bronze + dashboard_match == pass AND claim_language == pass
    Gold   = Silver + analysis_rerun == pass AND external_review == pass
    """
    if "fail" in checks.values():
        return "none"
    bronze_ok = (
        checks.get("citation_cascade") != "fail"
        and checks.get("data_file_present") == "pass"
        and checks.get("code_runs") in PASS_OR_NOT_RUN
    )
    if not bronze_ok:
        return "none"
    silver_ok = checks.get("dashboard_match") == "pass" and checks.get("claim_language") == "pass"
    if not silver_ok:
        return "bronze"
    gold_ok = checks.get("analysis_rerun") == "pass" and checks.get("external_review") == "pass"
    return "gold" if gold_ok else "silver"
