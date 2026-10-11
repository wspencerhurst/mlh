"""Thin client for Tiger Data (TimescaleDB on Postgres) that stores CME settlements.

The connection string is read from the TIGER_DATABASE_URL env var or a local .env file;
it is never written into code or outputs. Everything is optional: with no URL set,
enabled() is False and callers skip the database.
"""
from __future__ import annotations

import os

import pandas as pd

SCHEMA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db", "settlements.sql")


def url() -> str | None:
    k = os.environ.get("TIGER_DATABASE_URL")
    d = os.path.abspath(os.getcwd())
    while not k:  # nearest .env in this or a parent directory (keeps secrets out of the repo)
        p = os.path.join(d, ".env")
        if os.path.exists(p):
            for line in open(p):
                if line.startswith("TIGER_DATABASE_URL="):
                    k = line.split("=", 1)[1].strip()
        if os.path.dirname(d) == d:
            break
        d = os.path.dirname(d)
    return k or None


def enabled() -> bool:
    return url() is not None


def connect(**kw):
    import psycopg
    return psycopg.connect(url(), **kw)


def ensure_schema() -> None:
    """Apply db/settlements.sql statement by statement (continuous aggregates cannot run in a transaction)."""
    text = "\n".join(l for l in open(SCHEMA).read().splitlines() if not l.lstrip().startswith("--"))
    with connect(autocommit=True) as con:
        for stmt in filter(None, (s.strip() for s in text.split(";"))):
            con.execute(stmt)


def upsert_settlements(product_id: str, trade_date, df: pd.DataFrame) -> int:
    """Insert or update one day's curve (columns ym, settle, volume, oi); returns rows written."""
    if df is None or not len(df):
        return 0
    d = pd.Timestamp(trade_date).date()
    rows = [(d, str(product_id), int(r.ym), float(r.settle), float(r.volume), float(r.oi))
            for r in df.itertuples()]
    with connect() as con, con.cursor() as cur:
        cur.executemany(
            "INSERT INTO cme_settlements (trade_date, product_id, ym, settle, volume, oi) "
            "VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (product_id, ym, trade_date) DO UPDATE "
            "SET settle = EXCLUDED.settle, volume = EXCLUDED.volume, oi = EXCLUDED.oi", rows)
    return len(rows)
