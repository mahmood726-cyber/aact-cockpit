"""Scan a directory of generated capsules and write an offline index.html that
lists every capsule (pairwise or TSA) with its assurance tier and headline.

Usage:
    python scripts/build_index.py --dir docs
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

CSS = (
    "body{font:15px/1.55 -apple-system,Segoe UI,Roboto,Arial,sans-serif;max-width:940px;"
    "margin:36px auto;padding:0 18px;color:#1a1a1f;background:#fbfbfd}"
    "@media(prefers-color-scheme:dark){body{background:#15161a;color:#ececf1}"
    "table{background:#1d1f25}th,td{border-color:#2b2d34}}"
    "h1{font-size:24px;margin:0 0 2px}.sub{color:#5a5a66;font-size:13.5px;margin-bottom:18px}"
    "table{width:100%;border-collapse:collapse;font-size:14px}"
    "th,td{padding:8px 10px;border-bottom:1px solid #e3e3ea;text-align:left}"
    "td.r,th.r{text-align:right}a{color:#2456c6;text-decoration:none;font-weight:600}a:hover{text-decoration:underline}"
    ".t{font-weight:800;padding:2px 8px;border-radius:5px;color:#fff;font-size:11.5px;text-transform:uppercase}"
    ".gold{background:#b8860b}.silver{background:#8a8f99}.bronze{background:#a9712e}.none{background:#b33}"
    ".kind{font-size:11px;color:#5a5a66;border:1px solid #e3e3ea;border-radius:4px;padding:1px 6px}"
    ".foot{color:#5a5a66;font-size:12.5px;margin-top:22px}"
)


def collect(d: Path) -> list[dict]:
    rows = []
    for sidecar in sorted(d.glob("*/*.json")):
        if sidecar.name == "assurance.json":
            continue
        try:
            c = json.loads(sidecar.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            continue
        if "pico" not in c or "tier" not in c:
            continue
        slug = c["slug"]
        html = f"{slug}/{slug}-capsule.html"
        if not (d / html).is_file():
            continue
        pico = c["pico"]
        kind = c.get("kind", "pairwise")
        if kind == "tsa":
            t = c.get("tsa", {})
            fin = (t.get("steps") or [{}])[-1]
            headline = (f"cum. {c.get('measure','')} {fin.get('est',0):.2f} · "
                        f"{t.get('conclusion','')}" if fin else c.get("measure", ""))
        else:
            p = c.get("pooled", {})
            headline = (f"{c.get('measure','')} {p.get('est',0):.2f} "
                        f"({p.get('ci_lower',0):.2f}–{p.get('ci_upper',0):.2f}) · I²{p.get('i2',0):.0f}%")
        rows.append({
            "title": f"{pico.get('outcome','')} in {pico.get('population','')}",
            "kind": kind, "k": c.get("pooled", {}).get("k") or c.get("tsa", {}).get("k", ""),
            "tier": c["tier"], "html": html, "headline": headline,
            "snapshot": c.get("snapshot_date", "?"),
        })
    return rows


def build(d: Path) -> Path:
    rows = collect(d)
    snap = rows[0]["snapshot"] if rows else "?"
    body = ""
    for r in rows:
        body += (f"<tr><td><a href='{r['html']}'>{r['title']}</a> "
                 f"<span class='kind'>{r['kind']}</span></td>"
                 f"<td>{r['headline']}</td><td class='r'>{r['k']}</td>"
                 f"<td><span class='t {r['tier']}'>{r['tier']}</span></td></tr>")
    html = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>AACTCockpit — living evidence capsules</title>"
        "<meta property='og:title' content='AACTCockpit — living evidence capsules'>"
        f"<style>{CSS}</style></head><body>"
        "<h1>AACTCockpit — living evidence capsules</h1>"
        f"<div class='sub'>{len(rows)} self-auditing meta-analyses produced from one "
        f"ClinicalTrials.gov/AACT warehouse (snapshot {snap}), one engine. "
        "Each capsule is offline, recomputes live on edit, and cross-validates against R.</div>"
        "<table><tr><th>Analysis</th><th>Result</th><th class='r'>k</th><th>Assurance</th></tr>"
        f"{body}</table>"
        "<div class='foot'>Bronze = parses · Silver = statistical invariants pass + dashboard agrees · "
        "Gold = independent R reproduction + human sign-off. "
        "Source: <a href='https://github.com/mahmood726-cyber/aact-cockpit'>github.com/mahmood726-cyber/aact-cockpit</a></div>"
        "</body></html>"
    )
    idx = d / "index.html"
    idx.write_text(html, encoding="utf-8")
    return idx


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="docs")
    args = ap.parse_args()
    idx = build(Path(args.dir))
    print(f"wrote {idx} ({len(collect(Path(args.dir)))} capsules)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
