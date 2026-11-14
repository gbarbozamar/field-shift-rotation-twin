"""Acceptance tests of the file cache (PROPOSED cases 1 to 6 of the plan).

Run with ``uv run pytest adapters/`` from the repository root.
"""

from __future__ import annotations

import datetime as dt
import re

import pytest

from adapters.cache import FileCache, StoredResponse, cache_key

MOMENT = dt.datetime(1900, 1, 4, 12, 0, tzinfo=dt.UTC)
QUERY = {
    "parameters": "PLACEHOLDER_PARAMETER_A",
    "latitude": "1.5",
    "longitude": "-2.5",
    "start": "19000101",
    "end": "19000103",
}
BASE = "https://power.invalid/daily/point"


def entry(body: str = '{"placeholder": 1.0}', moment=MOMENT) -> StoredResponse:
    return StoredResponse(body=body, query=QUERY, retrieved_at=moment)


def key(**query_overrides) -> str:
    return cache_key("placeholder_source", BASE, {**QUERY, **query_overrides})


def test_miss_then_put_then_get(tmp_path):
    cache = FileCache(tmp_path / "cache")
    assert cache.get(key()) is None
    kept = cache.put(key(), entry())
    got = cache.get(key())
    assert got == kept
    assert got.body == '{"placeholder": 1.0}'
    assert dict(got.query) == QUERY
    assert got.retrieved_at == MOMENT


def test_first_response_wins(tmp_path):
    cache = FileCache(tmp_path)
    cache.put(key(), entry(body='"first"'))
    later = entry(body='"second"', moment=MOMENT + dt.timedelta(days=1))
    kept = cache.put(key(), later)
    assert kept.body == '"first"'
    assert kept.retrieved_at == MOMENT
    assert cache.get(key()).body == '"first"'


def test_key_is_stable_across_argument_order():
    reordered = dict(reversed(list(QUERY.items())))
    assert cache_key("placeholder_source", BASE, reordered) == key()
    assert cache_key("placeholder_source", BASE, dict(QUERY)) == key()


@pytest.mark.parametrize(
    "changed",
    [
        {"latitude": "1.6"},
        {"longitude": "-2.6"},
        {"start": "19000102"},
        {"end": "19000104"},
        {"parameters": "PLACEHOLDER_PARAMETER_A,PLACEHOLDER_PARAMETER_B"},
    ],
)
def test_key_differs_with_the_query(changed):
    assert key(**changed) != key()


def test_key_differs_with_base_url_and_source_id():
    assert cache_key("placeholder_source", BASE + "/other", QUERY) != key()
    assert cache_key("placeholder_other_source", BASE, QUERY) != key()


@pytest.mark.parametrize(
    "content",
    [b'{"body": "x", "query": {}, "retr', b"not json at all", b"\xff\xfe\x00", b""],
)
def test_corrupt_entry_is_absent_and_replaced(tmp_path, content):
    cache = FileCache(tmp_path)
    (tmp_path / f"{key()}.json").write_bytes(content)
    assert cache.get(key()) is None
    kept = cache.put(key(), entry())
    assert kept == entry()
    assert cache.get(key()) == entry()


def test_entry_with_wrong_shape_is_absent(tmp_path):
    cache = FileCache(tmp_path)
    (tmp_path / f"{key()}.json").write_text(
        '{"body": "x", "query": {"a": 1}, "retrieved_at": "1900-01-01T00:00:00+00:00"}'
    )
    assert cache.get(key()) is None
    (tmp_path / f"{key()}.json").write_text(
        '{"body": "x", "query": {}, "retrieved_at": "1900-01-01T00:00:00"}'
    )
    assert cache.get(key()) is None


def test_nothing_left_behind_and_nothing_outside(tmp_path):
    folder = tmp_path / "cache"
    cache = FileCache(folder)
    cache.put(key(), entry())
    cache.put(key(), entry(body='"second"'))
    cache.put(key(latitude="1.6"), entry())
    assert sorted(p.name for p in tmp_path.iterdir()) == ["cache"]
    names = sorted(p.name for p in folder.iterdir())
    assert names == sorted([f"{key()}.json", f"{key(latitude='1.6')}.json"])


def test_folder_is_created_on_first_write_only(tmp_path):
    folder = tmp_path / "not" / "yet"
    cache = FileCache(folder)
    assert cache.get(key()) is None
    assert not folder.exists()
    cache.put(key(), entry())
    assert folder.is_dir()


def test_file_name_is_hex_and_extension(tmp_path):
    cache = FileCache(tmp_path)
    cache.put(key(), entry())
    (path,) = tmp_path.iterdir()
    assert re.fullmatch(r"[0-9a-f]{64}\.json", path.name)


@pytest.mark.parametrize(
    "bad_key", ["../escape", "A" * 64, "0" * 63, "placeholder", "0" * 64 + "/x"]
)
def test_only_a_digest_reaches_a_file_name(tmp_path, bad_key):
    cache = FileCache(tmp_path)
    with pytest.raises(ValueError):
        cache.get(bad_key)
    with pytest.raises(ValueError):
        cache.put(bad_key, entry())
    assert list(tmp_path.iterdir()) == []


def test_retrieved_at_must_be_utc():
    with pytest.raises(ValueError):
        StoredResponse(body="x", query={}, retrieved_at=dt.datetime(1900, 1, 1))


def test_failed_write_leaves_no_temporary_file(tmp_path, monkeypatch):
    cache = FileCache(tmp_path)

    def broken_replace(*_args, **_kwargs):
        raise OSError("placeholder failure")

    monkeypatch.setattr("adapters.cache.os.replace", broken_replace)
    with pytest.raises(OSError):
        cache.put(key(), entry())
    assert list(tmp_path.iterdir()) == []
