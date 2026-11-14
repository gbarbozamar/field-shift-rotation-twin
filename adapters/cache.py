"""File cache of the first response of a data source. PROPOSED (see README.md).

One entry per request: the raw response body as received, the query that
produced it and the moment it was retrieved (UTC). The first response stored
for a key is kept for good: the source archive is revised over time and a case
keeps what it first saw.

The cache is a ``Protocol`` so that a host that does not keep files gets
another implementation, not a rewrite of the adapters. ``FileCache`` is the one
implementation today.

No network calls here. Nothing is written outside the folder passed in.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol

_KEY = re.compile(r"[0-9a-f]{64}")
_SUFFIX = ".json"


@dataclass(frozen=True)
class StoredResponse:
    """What the cache keeps for one request."""

    body: str  # the response body as received, decoded as text, never re-encoded
    query: Mapping[str, str]  # the query sent to the source
    retrieved_at: dt.datetime  # when the source answered; timezone-aware, UTC

    def __post_init__(self) -> None:
        if not isinstance(self.body, str):
            raise TypeError("StoredResponse.body is the response text")
        if not isinstance(self.query, Mapping) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in self.query.items()
        ):
            raise TypeError("StoredResponse.query maps text to text")
        if not isinstance(self.retrieved_at, dt.datetime):
            raise TypeError("StoredResponse.retrieved_at is a datetime")
        if self.retrieved_at.utcoffset() != dt.timedelta(0):
            raise ValueError("StoredResponse.retrieved_at is timezone-aware UTC")
        object.__setattr__(self, "query", MappingProxyType(dict(self.query)))
        object.__setattr__(self, "retrieved_at", self.retrieved_at.astimezone(dt.UTC))


class ResponseCache(Protocol):
    """Where an adapter keeps the first response of each request."""

    def get(self, key: str) -> StoredResponse | None:
        """The stored entry, or None when there is none or it cannot be read."""
        ...

    def put(self, key: str, entry: StoredResponse) -> StoredResponse:
        """Store ``entry`` unless a readable entry exists; return the one kept."""
        ...


def cache_key(source_id: str, base_url: str, query: Mapping[str, str]) -> str:
    """SHA-256 hex digest of the canonical JSON of source, endpoint and query.

    Canonical JSON: sorted keys, no whitespace. The order in which the query
    arguments were inserted does not change the key.
    """
    document = {"source_id": source_id, "base_url": base_url, "query": dict(query)}
    canonical = json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _check_key(key: str) -> None:
    # Only a digest made by cache_key reaches a file name.
    if not isinstance(key, str) or not _KEY.fullmatch(key):
        raise ValueError("a cache key is a SHA-256 hex digest made by cache_key")


def _encode(entry: StoredResponse) -> str:
    return json.dumps(
        {
            "body": entry.body,
            "query": dict(entry.query),
            "retrieved_at": entry.retrieved_at.isoformat(),
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _decode(text: str) -> StoredResponse | None:
    try:
        document: Any = json.loads(text)
    except ValueError:
        return None
    if not isinstance(document, dict) or set(document) != {
        "body",
        "query",
        "retrieved_at",
    }:
        return None
    retrieved_at = document["retrieved_at"]
    if not isinstance(retrieved_at, str):
        return None
    try:
        moment = dt.datetime.fromisoformat(retrieved_at)
        return StoredResponse(
            body=document["body"], query=document["query"], retrieved_at=moment
        )
    except (TypeError, ValueError):
        return None


class FileCache:
    """One JSON file per key in one folder. The folder is created on first write."""

    def __init__(self, folder: Path | str) -> None:
        self._folder = Path(folder)

    def _path(self, key: str) -> Path:
        _check_key(key)
        return self._folder / f"{key}{_SUFFIX}"

    def get(self, key: str) -> StoredResponse | None:
        path = self._path(key)
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None
        return _decode(text)

    def put(self, key: str, entry: StoredResponse) -> StoredResponse:
        if not isinstance(entry, StoredResponse):
            raise TypeError("FileCache.put stores a StoredResponse")
        existing = self.get(key)
        if existing is not None:
            return existing  # first response wins
        path = self._path(key)
        self._folder.mkdir(parents=True, exist_ok=True)
        # Atomic: a temporary file in the same folder, then a rename. A crash
        # leaves at most a stray temporary file, never a half-written entry.
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self._folder,
                prefix=f".{key}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temporary = Path(handle.name)
                handle.write(_encode(entry))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        except BaseException:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            raise
        return entry
