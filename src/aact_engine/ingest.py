"""Build the AACT DuckDB warehouse from the pipe-delimited snapshot.

One-time (idempotent) ingest of the MVP tables into a single DuckDB file. A
``_meta`` table records, per table, the snapshot date, source bytes/mtime and
row count, so a rerun against the same snapshot is a no-op and a *new* snapshot
date builds a *new* db file.
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

import duckdb

from .paths import discover_snapshot_root, detect_snapshot_date
from .schema import READ_CSV_OPTS, MVP_TABLES
from .provenance import Provenance


def _opts_sql() -> str:
    parts = []
    for k, v in READ_CSV_OPTS.items():
        if isinstance(v, bool):
            parts.append(f"{k}={'true' if v else 'false'}")
        elif isinstance(v, str):
            esc = v.replace("'", "''")
            parts.append(f"{k}='{esc}'")
        else:
            parts.append(f"{k}={v}")
    return ", ".join(parts)


def read_csv_expr(txt_path: Path) -> str:
    """A DuckDB read_csv(...) SQL expression for one snapshot .txt file."""
    p = str(txt_path).replace("\\", "/").replace("'", "''")
    return f"read_csv('{p}', {_opts_sql()})"


def default_db_path(snapshot_date: str) -> Path:
    root = Path(__file__).resolve().parents[2]  # repo root (src/aact_engine/ -> ../..)
    return root / "data" / "warehouse" / f"aact_{snapshot_date}.duckdb"


def _ensure_meta(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS _meta (
            snapshot_date VARCHAR,
            table_name    VARCHAR,
            source_path   VARCHAR,
            source_bytes  BIGINT,
            source_mtime  DOUBLE,
            row_count     BIGINT,
            built_at      VARCHAR
        )
    """)


def _meta_row(con, table: str):
    return con.execute(
        "SELECT snapshot_date, source_bytes, row_count FROM _meta WHERE table_name = ?",
        [table],
    ).fetchone()


def build_warehouse(
    snapshot_root: str | Path | None = None,
    db_path: str | Path | None = None,
    tables: tuple[str, ...] = MVP_TABLES,
    rebuild: bool = False,
    verbose: bool = True,
) -> Provenance:
    """Build (or refresh) the warehouse. Returns Provenance for the built DB."""
    root = Path(snapshot_root) if snapshot_root else discover_snapshot_root()
    snapshot_date = detect_snapshot_date(root)
    db = Path(db_path) if db_path else default_db_path(snapshot_date)
    db.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(db))
    try:
        _ensure_meta(con)
        for table in tables:
            src = root / f"{table}.txt"
            if not src.is_file():
                raise FileNotFoundError(f"AACT table missing from snapshot: {src}")
            st = src.stat()
            existing = _meta_row(con, table)
            table_exists = con.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_name = ?",
                [table],
            ).fetchone()[0] > 0
            if (
                not rebuild
                and table_exists
                and existing is not None
                and existing[0] == snapshot_date
                and existing[1] == st.st_size
            ):
                if verbose:
                    print(f"  = {table:26s} up-to-date ({existing[2]:,} rows)")
                continue

            con.execute(f"DROP TABLE IF EXISTS {table}")
            con.execute(f"CREATE TABLE {table} AS SELECT * FROM {read_csv_expr(src)}")
            n = con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]

            # Row-count integrity check vs raw line count (header excluded).
            # AACT MVP tables have no embedded newlines, so these must match;
            # a mismatch means the quoting/escape dialect is wrong.
            raw_lines = _count_lines(src)
            expected = raw_lines - 1
            if n != expected:
                raise ValueError(
                    f"Row-count mismatch for {table}: duckdb={n} vs file_data_rows={expected}. "
                    "Check the read_csv dialect (schema.READ_CSV_OPTS)."
                )

            con.execute("DELETE FROM _meta WHERE table_name = ?", [table])
            con.execute(
                "INSERT INTO _meta VALUES (?,?,?,?,?,?,?)",
                [snapshot_date, table, str(src), st.st_size, st.st_mtime, n,
                 _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")],
            )
            if verbose:
                print(f"  + {table:26s} {n:,} rows")

        # Stamp an overall snapshot row for quick provenance reads.
        con.execute("DELETE FROM _meta WHERE table_name = '_all'")
        con.execute(
            "INSERT INTO _meta VALUES (?,?,?,?,?,?,?)",
            [snapshot_date, "_all", str(root), 0, 0.0, 0,
             _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")],
        )
    finally:
        con.close()

    return Provenance(snapshot_date=snapshot_date, db_path=str(db)).with_extracted_now()


def _count_lines(path: Path) -> int:
    """Fast line count (bytes-based) for the row-integrity assertion."""
    n = 0
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            n += chunk.count(b"\n")
        # account for a final line without trailing newline
        f.seek(0, 2)
        size = f.tell()
        if size > 0:
            f.seek(size - 1)
            if f.read(1) != b"\n":
                n += 1
    return n


def read_provenance(db_path: str | Path) -> Provenance:
    """Read the snapshot date from a built warehouse's _meta table."""
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        row = con.execute(
            "SELECT snapshot_date FROM _meta WHERE table_name = '_all' LIMIT 1"
        ).fetchone()
        if row is None:
            row = con.execute("SELECT snapshot_date FROM _meta LIMIT 1").fetchone()
        date = row[0] if row else "unknown"
    finally:
        con.close()
    return Provenance(snapshot_date=date, db_path=str(db_path)).with_extracted_now()


__all__ = ["build_warehouse", "read_provenance", "default_db_path", "read_csv_expr"]
