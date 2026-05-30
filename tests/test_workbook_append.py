"""Workbook append is append-only and never touches existing YOUR REWRITE."""
from __future__ import annotations

from aact_cockpit.discipline.append_workbook_entry import (
    append_entry, next_index_and_total, build_entry,
)

FIXTURE = """E156 REWRITE WORKBOOK
sentinel:skip-file

======================================================================

[1/2] EXISTING_ONE
TITLE: existing one
CURRENT BODY (156 words):
Old body one.

YOUR REWRITE (at most 156 words, 7 sentences):
A STUDENT WROTE THIS ONE — must be preserved verbatim.

======================================================================

[2/2] EXISTING_TWO
CURRENT BODY (156 words):
Old body two.

YOUR REWRITE (at most 156 words, 7 sentences):
SECOND student rewrite — also preserved.
"""

CAPSULE = {
    "slug": "hr-acm-hf", "title": "HR for all-cause mortality in heart failure",
    "measure": "HR", "primary_estimand": "hazard ratio for all-cause mortality",
    "snapshot_date": "2026-04-12", "pico": {"population": "heart failure"},
    "pooled": {"k": 25},
    "e156_body": ("In heart failure, does treatment change mortality? Twenty-five trials "
                  "were aggregated. Effects were pooled. The HR was 0.94 (95% CI 0.91 to 0.97). "
                  "Heterogeneity was modest. Findings are consistent with a small effect. "
                  "Interpretation is limited by the snapshot."),
}


def test_next_index_and_total():
    assert next_index_and_total(FIXTURE) == (3, 2)


def test_dry_run_does_not_write(tmp_path):
    wb = tmp_path / "wb.txt"
    wb.write_text(FIXTURE, encoding="utf-8")
    before = wb.read_text(encoding="utf-8")
    res = append_entry(CAPSULE, wb, apply=False, code_url="https://example/repo")
    assert res["applied"] is False
    assert wb.read_text(encoding="utf-8") == before  # untouched on dry-run


def test_apply_is_pure_append(tmp_path):
    wb = tmp_path / "wb.txt"
    wb.write_text(FIXTURE, encoding="utf-8")
    append_entry(CAPSULE, wb, apply=True,
                 code_url="https://example/repo",
                 dashboard_url="https://example/dash.html")
    after = wb.read_text(encoding="utf-8")
    # original content is a byte-prefix of the new file (pure append)
    assert after.startswith(FIXTURE)
    # both existing student rewrites preserved verbatim
    assert "A STUDENT WROTE THIS ONE — must be preserved verbatim." in after
    assert "SECOND student rewrite — also preserved." in after
    # new entry added with correct header, blank YOUR REWRITE, MA middle author
    assert "[3/2] HR-ACM-HF".replace("-", "_") in after
    assert "Middle author: Mahmood Ahmad" in after
    # exactly one new YOUR REWRITE added (3 total), and it is blank
    assert after.count("YOUR REWRITE") == 3
    new_block = after[len(FIXTURE):]
    rewrite_section = new_block.split("YOUR REWRITE (at most 156 words, 7 sentences):")[1]
    assert rewrite_section.split("SUBMISSION METADATA")[0].strip() == ""


def test_no_none_literal_when_links_missing():
    block = build_entry(CAPSULE, 5, 9, code_url=None, dashboard_url=None)
    # no leaked None in a link/path field (Funding: None. prose is fine)
    import re
    assert not re.search(r"(?:Code|Dashboard|Protocol|PATH|DATA):\s*None\b", block)
    assert "Links:" not in block  # omitted entirely when no URLs
