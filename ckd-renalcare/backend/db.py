"""Postgres access. One small connection pool; every call gets a dict cursor."""
import os
from contextlib import contextmanager
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool

DSN = os.getenv("DATABASE_URL", "postgresql://ckd_user:ckd_user123@localhost:5432/ckd")
_pool = None


def pool():
    global _pool
    if _pool is None:
        _pool = ThreadedConnectionPool(1, 8, DSN, client_encoding="utf8")
    return _pool


@contextmanager
def cursor():
    """with cursor() as cur: ...   commits on success, rolls back on error."""
    conn = pool().getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool().putconn(conn)


def one(sql, args=()):
    with cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchone()


def all(sql, args=()):
    with cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchall()


def run(sql, args=()):
    with cursor() as cur:
        cur.execute(sql, args)
        return cur.rowcount
