"""Tests run on a throw-away database (ckd_test) built from schema.sql, so your real data is never touched.
Needs a Postgres user that can CREATE DATABASE. Set DATABASE_URL like the app does."""
import os, sys, re
from pathlib import Path
import psycopg2, pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
BASE = os.getenv("DATABASE_URL", "postgresql://ckd:ckd123@localhost:5432/ckd")
ADMIN = re.sub(r"/[^/]*$", "/postgres", BASE)
TEST = re.sub(r"/[^/]*$", "/ckd_test", BASE)
os.environ["DATABASE_URL"] = TEST


@pytest.fixture(scope="session", autouse=True)
def test_db():
    try:
        c = psycopg2.connect(ADMIN); c.autocommit = True
    except Exception as e:
        pytest.skip(f"no Postgres available: {e}", allow_module_level=True)
    cur = c.cursor()
    cur.execute("DROP DATABASE IF EXISTS ckd_test WITH (FORCE)"); cur.execute("CREATE DATABASE ckd_test")
    c.close()
    t = psycopg2.connect(TEST); t.autocommit = True
    t.cursor().execute((BACKEND / "schema.sql").read_text()); t.close()
    import seed
    seed.main()
    yield
    import db
    db.pool().closeall()
    c = psycopg2.connect(ADMIN); c.autocommit = True
    c.cursor().execute("DROP DATABASE IF EXISTS ckd_test WITH (FORCE)")
