import sqlite3

import mysql.connector

from .config import mysql_config, PROJECT_ROOT, sqlite_path, use_sqlite


def _sqlite_columns(conn, table):
    cur = conn.execute("PRAGMA table_info(" + table + ")")
    return {row[1] for row in cur.fetchall()}


def _ensure_sqlite_schema(conn):
    sql = (PROJECT_ROOT / "database" / "schema_sqlite.sql").read_text(encoding="utf-8")
    conn.executescript(sql)
    conn.commit()
    cols = _sqlite_columns(conn, "sections")
    if "section_code" not in cols:
        conn.execute("ALTER TABLE sections ADD COLUMN section_code TEXT")
        conn.commit()
    cols = _sqlite_columns(conn, "sections")
    if "enrolled" not in cols:
        conn.execute("ALTER TABLE sections ADD COLUMN enrolled INTEGER")
        conn.commit()
    if "seat_limit" not in cols:
        conn.execute("ALTER TABLE sections ADD COLUMN seat_limit INTEGER")
        conn.commit()


def connect():
    if use_sqlite():
        path = sqlite_path()
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        _ensure_sqlite_schema(conn)
        return conn, "sqlite"
    conn = mysql.connector.connect(**mysql_config())
    return conn, "mysql"


def sql_placeholder(backend):
    return "?" if backend == "sqlite" else "%s"


def rows_as_dicts(cur, backend):
    if backend == "mysql":
        return cur.fetchall()
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]
