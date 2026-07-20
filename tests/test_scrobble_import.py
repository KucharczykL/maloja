"""Behavioral tests for the fork's add_scrobbles idempotency + orphan tolerance."""
from maloja.database import sqldb
from conftest import scrobble, count, rows, orphan_first_track


# --- idempotency of the same-second collision loop ---

def test_idempotent_reimport_adds_nothing():
    sqldb.add_scrobbles([scrobble(1000, "A"), scrobble(2000, "B")])
    assert count() == 2
    s, e, er = sqldb.add_scrobbles([scrobble(1000, "A"), scrobble(2000, "B")])
    assert (s, e, er) == (0, 2, 0)
    assert count() == 2


def test_same_second_different_tracks_shift_deterministically():
    sqldb.add_scrobbles([scrobble(1000, "A"), scrobble(1000, "B")])
    assert rows() == [(1000, "A"), (1001, "B")]
    sqldb.add_scrobbles([scrobble(1000, "C")])
    assert (1002, "C") in rows()
    assert count() == 3


def test_changed_reimport_adds_only_new():
    # first import: A@1000, B shifts to 1001
    sqldb.add_scrobbles([scrobble(1000, "A"), scrobble(1000, "B")])
    # re-import with a new same-second listen C inserted between A and B
    s, e, er = sqldb.add_scrobbles([scrobble(1000, "A"), scrobble(1000, "C"), scrobble(1000, "B")])
    assert er == 0
    assert s == 1          # only C is genuinely new
    assert e == 2          # A and B reconverge to their slots and dedup
    assert count() == 3    # no duplicates
    assert sorted(t for _, t in rows()) == ["A", "B", "C"]


def test_attempts_bound_drops_without_hanging():
    # a contiguous block of distinct-track seconds longer than the shift bound,
    # so a colliding insert can't reach a free slot within 3600 shifts
    sqldb.add_scrobbles([scrobble(1000 + i, f"T{i}") for i in range(3602)])
    assert count() == 3602
    s, e, er = sqldb.add_scrobbles([scrobble(1000, "OVERFLOW")])
    assert (s, er) == (0, 1)   # dropped as an error, not an infinite loop
    assert count() == 3602


# --- orphan tolerance (a scrobble whose track was deleted) ---

def test_orphan_does_not_crash_track_chart():
    sqldb.add_scrobbles([scrobble(1000, "A"), scrobble(2000, "B")])
    tid = orphan_first_track()
    res = sqldb.count_scrobbles_by_track(since=0, to=9999999999)  # must not KeyError
    assert all(r["track_id"] != tid for r in res)                 # orphan excluded


def test_orphan_does_not_crash_artist_chart():
    sqldb.add_scrobbles([scrobble(1000, "A", artist="X"), scrobble(2000, "B", artist="Y")])
    orphan_first_track()
    sqldb.count_scrobbles_by_artist(since=0, to=9999999999)       # must not KeyError
