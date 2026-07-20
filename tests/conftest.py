"""Test fixtures for maloja.

maloja builds its SQLite engine at import time, bound to MALOJA_DATA_DIRECTORY,
so point it at a throwaway dir *before* anything imports maloja.database.
"""
import os
import sqlite3
import tempfile

_TMP = tempfile.mkdtemp(prefix="maloja-test-")
os.environ["MALOJA_DATA_DIRECTORY"] = _TMP
os.environ.setdefault("MALOJA_SKIP_SETUP", "yes")
os.environ.setdefault("MALOJA_FORCE_PASSWORD", "test")

import pytest  # noqa: E402

DB = os.path.join(_TMP, "malojadb.sqlite")

# importing this creates the engine + tables at DB
from maloja.database import sqldb, dbcache  # noqa: E402,F401


@pytest.fixture(autouse=True)
def clean_db():
    """Empty scrobble-related tables before each test for isolation.

    Uses sqldb's own engine so the deletes share the pool/WAL context that
    add_scrobbles reads through (a separate sqlite3 connection doesn't).
    """
    with sqldb.engine.begin() as conn:
        for tbl in ("scrobbles", "trackartists", "albumartists",
                    "associated_artists", "tracks", "albums", "artists"):
            conn.exec_driver_sql(f"DELETE FROM {tbl}")
    # the row DELETEs orphan maloja's cached id lookups; clear the LRUs directly
    # (invalidate_caches() doesn't reliably empty them)
    if getattr(dbcache, "cache", None) is not None:
        dbcache.cache.clear()
    if getattr(dbcache, "entitycache", None) is not None:
        dbcache.entitycache.clear()
    yield


def scrobble(t, title, artist="A"):
    """Build a scrobble dict in the shape add_scrobbles expects."""
    return {
        "time": t,
        "track": {"artists": [artist], "title": title, "length": None, "album": None},
        "duration": None,
        "origin": "import:test",
        "extra": {},
    }


def count():
    conn = sqlite3.connect(DB)
    n = conn.execute("SELECT count(*) FROM scrobbles").fetchone()[0]
    conn.close()
    return n


def rows():
    conn = sqlite3.connect(DB)
    r = conn.execute(
        "SELECT s.timestamp, t.title FROM scrobbles s "
        "JOIN tracks t ON t.id = s.track_id ORDER BY s.timestamp"
    ).fetchall()
    conn.close()
    return r


def orphan_first_track():
    """Delete the track of the earliest scrobble, leaving it orphaned."""
    conn = sqlite3.connect(DB)
    tid = conn.execute("SELECT track_id FROM scrobbles ORDER BY timestamp LIMIT 1").fetchone()[0]
    conn.execute("DELETE FROM trackartists WHERE track_id = ?", (tid,))
    conn.execute("DELETE FROM tracks WHERE id = ?", (tid,))
    conn.commit()
    conn.close()
    return tid
