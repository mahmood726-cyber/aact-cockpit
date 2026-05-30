"""Ingest: builds tables, records _meta, idempotent rerun, row-count guard."""
from __future__ import annotations

import pytest

from aact_engine.ingest import build_warehouse, read_provenance


def _write_snapshot(base, date="2026-04-12"):
    snap = base / "AACT" / date
    snap.mkdir(parents=True)
    # quoted-CSV dialect: embedded | inside quotes must survive
    (snap / "studies.txt").write_text(
        'nct_id|brief_title\n'
        'NCT1|"Drug A | vs placebo"\n'
        'NCT2|Plain title\n',
        encoding="utf-8",
    )
    (snap / "conditions.txt").write_text(
        "id|nct_id|name|downcase_name\n1|NCT1|Heart Failure|heart failure\n",
        encoding="utf-8",
    )
    return snap


def test_build_and_meta(tmp_path):
    snap = _write_snapshot(tmp_path)
    db = tmp_path / "wh.duckdb"
    prov = build_warehouse(snapshot_root=snap, db_path=db,
                           tables=("studies", "conditions"), verbose=False)
    assert prov.snapshot_date == "2026-04-12"
    assert prov.db_path == str(db)

    import duckdb
    con = duckdb.connect(str(db), read_only=True)
    # embedded pipe survived quoting => 2 study rows, not 3
    assert con.execute("SELECT count(*) FROM studies").fetchone()[0] == 2
    assert con.execute("SELECT brief_title FROM studies WHERE nct_id='NCT1'").fetchone()[0] == "Drug A | vs placebo"
    meta = con.execute("SELECT row_count FROM _meta WHERE table_name='studies'").fetchone()[0]
    assert meta == 2
    con.close()


def test_idempotent_rerun(tmp_path):
    snap = _write_snapshot(tmp_path)
    db = tmp_path / "wh.duckdb"
    build_warehouse(snapshot_root=snap, db_path=db, tables=("studies",), verbose=False)
    import duckdb
    con = duckdb.connect(str(db), read_only=True)
    built_at_1 = con.execute("SELECT built_at FROM _meta WHERE table_name='studies'").fetchone()[0]
    con.close()
    # rerun: same bytes => no rebuild => built_at unchanged
    build_warehouse(snapshot_root=snap, db_path=db, tables=("studies",), verbose=False)
    con = duckdb.connect(str(db), read_only=True)
    built_at_2 = con.execute("SELECT built_at FROM _meta WHERE table_name='studies'").fetchone()[0]
    con.close()
    assert built_at_1 == built_at_2


def test_provenance_read(tmp_path):
    snap = _write_snapshot(tmp_path)
    db = tmp_path / "wh.duckdb"
    build_warehouse(snapshot_root=snap, db_path=db, tables=("studies",), verbose=False)
    prov = read_provenance(db)
    assert prov.snapshot_date == "2026-04-12"
