"""Append a capsule as a new entry in the E156 rewrite-workbook — APPEND ONLY.

Honors the workbook protection rules (CLAUDE.md / e156.md, NON-NEGOTIABLE):
  - never touches any existing block or any YOUR REWRITE content
  - writes the new YOUR REWRITE blank (only the student fills it)
  - never writes 'None' for a missing link (omits the line instead)
  - MA is middle author; never first/last
  - pure append (no denominator sweep) so check_workbook_commit passes; the
    milestone back-rewrite of older denominators is left to reconcile_counts.py

Default is DRY-RUN: it prints the block and the target path. Pass apply=True
(CLI --apply) to actually append. The real workbook is a protected artifact;
callers should review the dry-run first.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SEP = "=" * 70
ENTRY_HEAD_RE = re.compile(r"^\[(\d+)/(\d+)\]", re.MULTILINE)

MA_BLOCK = (
    "SUBMISSION METADATA:\n\n"
    "Middle author: Mahmood Ahmad <mahmood.ahmad2@nhs.net>\n"
    "ORCID: 0000-0001-9107-3704\n"
    "Affiliation: Tahir Heart Institute, Rabwah, Pakistan\n"
)


def _default_workbook() -> Path:
    for c in (r"F:\E156\rewrite-workbook.txt", r"C:\E156\rewrite-workbook.txt"):
        if Path(c).is_file():
            return Path(c)
    raise SystemExit("rewrite-workbook.txt not found (F:/C: E156).")


def next_index_and_total(text: str) -> tuple[int, int]:
    """N = max ordinal + 1; total = the current denominator (kept as-is, no sweep)."""
    pairs = ENTRY_HEAD_RE.findall(text)
    if not pairs:
        return 1, 1
    max_n = max(int(n) for n, _ in pairs)
    total = max(int(t) for _, t in pairs)
    return max_n + 1, total


def build_entry(capsule: dict, n: int, total: int, *, code_url: str | None = None,
                dashboard_url: str | None = None) -> str:
    slug = capsule["slug"]
    title = capsule.get("title", slug)
    estimand = capsule.get("primary_estimand", "effect estimate with 95% CI")
    measure = capsule.get("measure", "")
    pico = capsule.get("pico", {})
    snap = capsule.get("snapshot_date", "")
    body = capsule["e156_body"]
    k = capsule.get("pooled", {}).get("k", "")

    lines = [
        SEP, "",
        f"[{n}/{total}] {slug.upper().replace('-', '_')}",
        f"TITLE: AACTCockpit | {title} — pairwise meta-analysis (ClinicalTrials.gov/AACT)",
        f"TYPE: pairwise  |  ESTIMAND: {estimand}",
        f"DATA: ClinicalTrials.gov via AACT snapshot {snap} · {k} randomized trials · trial-level aggregate",
        "PATH: (browser-native capsule — see Code/Dashboard URL; no local path)",
        "",
        "CURRENT BODY (auto-drafted; <=156 words, 7 sentences):",
        body,
        "",
        "YOUR REWRITE (at most 156 words, 7 sentences):",
        "",
        MA_BLOCK,
    ]
    links = []
    if code_url:
        links.append(f"  Code:      {code_url}")
    if dashboard_url:
        links.append(f"  Dashboard: {dashboard_url}")
    if links:
        lines.append("Links:")
        lines.extend(links)
        lines.append("")
    lines += [
        "Data availability: No patient-level data used. Analysis derived exclusively",
        "  from publicly available trial-level aggregate records in ClinicalTrials.gov/AACT.",
        "Ethics: Not required. Secondary methodological analysis of public aggregate data.",
        "Funding: None.",
        "",
    ]
    return "\n".join(lines)


def append_entry(capsule: dict, workbook: Path | None = None, *, apply: bool = False,
                 code_url: str | None = None, dashboard_url: str | None = None) -> dict:
    wb = Path(workbook) if workbook else _default_workbook()
    text = wb.read_text(encoding="utf-8")
    n, total = next_index_and_total(text)
    block = build_entry(capsule, n, total, code_url=code_url, dashboard_url=dashboard_url)

    # safety: never write a leaked 'None' where a URL/path belongs (the
    # placeholder-leak shape). "Funding: None." prose is legitimate, so the
    # guard is narrow (per the FP-audit lesson: narrow the match, don't weaken).
    if re.search(r"(?:Code|Dashboard|Protocol|PATH|DATA|Links?):\s*None\b", block) \
            or re.search(r"https?://\S*/None\b", block):
        raise ValueError("refusing to append: leaked 'None' in a link/path field")

    if apply:
        # pure append; do not modify any existing byte
        with open(wb, "a", encoding="utf-8") as fh:
            fh.write("\n" + block)
    return {"index": n, "total": total, "workbook": str(wb), "applied": apply,
            "block_preview": block[:400]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--capsule", required=True, help="path to a capsule {slug}.json sidecar")
    ap.add_argument("--workbook", default=None)
    ap.add_argument("--code-url", default=None)
    ap.add_argument("--dashboard-url", default=None)
    ap.add_argument("--apply", action="store_true", help="actually append (default: dry-run)")
    args = ap.parse_args()

    capsule = json.loads(Path(args.capsule).read_text(encoding="utf-8"))
    res = append_entry(capsule, args.workbook, apply=args.apply,
                       code_url=args.code_url, dashboard_url=args.dashboard_url)
    print(f"{'APPENDED' if res['applied'] else 'DRY-RUN'} entry [{res['index']}/{res['total']}] "
          f"-> {res['workbook']}")
    if not res["applied"]:
        print("\n--- block preview ---\n" + res["block_preview"] + "\n...")
        print("\nRe-run with --apply to write (workbook is append-only; existing entries untouched).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
