"""Hashing per guideline §4: normalized text, frontmatter-free docs, module hash."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

PREFIX = "sha256:"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def short(h: str | None) -> str:
    """Display form: sha256:<12 hex>."""
    if not h:
        return "-"
    h = h.removeprefix(PREFIX)
    return PREFIX + h[:12]


def full(h: str) -> str:
    return h if h.startswith(PREFIX) else PREFIX + h


def normalize_text(data: bytes) -> str | None:
    """UTF-8, CRLF->LF, trailing whitespace stripped per line, exactly one final newline.

    Returns None for binary content (not UTF-8, or contains NUL).
    """
    if b"\x00" in data:
        return None
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    text = text.removeprefix("﻿").replace("\r\n", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    return "\n".join(lines).rstrip("\n") + "\n"


def split_frontmatter(text: str) -> tuple[str | None, str]:
    """Return (frontmatter text or None, body). Text must be normalized."""
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---\n", 3)
    if end == -1:
        return None, text
    return text[4 : end + 1], text[end + 5 :]


def content_hash(data: bytes, name: str) -> str:
    """File hash: binary raw; text normalized; markdown without YAML frontmatter."""
    text = normalize_text(data)
    if text is None:
        return full(sha256(data))
    if name.endswith(".md"):
        _, text = split_frontmatter(text)
    return full(sha256(text.encode("utf-8")))


def text_hash(text: str) -> str:
    norm = normalize_text(text.encode("utf-8")) or ""
    return full(sha256(norm.encode("utf-8")))


def module_hash(file_hashes: dict[str, str], dep_hashes: dict[str, str]) -> str:
    """SHA-256 of sorted `<path>\\t<hash>` lines plus one `dep:<module>\\t<hash>` per dependency."""
    lines = sorted(f"{p}\t{h}" for p, h in file_hashes.items())
    lines += [f"dep:{d}\t{h}" for d, h in sorted(dep_hashes.items())]
    return full(sha256(("\n".join(lines) + "\n").encode("utf-8")))


class HashCache:
    """Incremental cache: path -> (mtime_ns, size, hash), stored in <root>/.modgate/cache.json."""

    def __init__(self, root: Path):
        self.path = root / ".modgate" / "cache.json"
        self.root = root
        self.dirty = False
        try:
            self.data: dict[str, list] = json.loads(self.path.read_text())
        except (OSError, ValueError):
            self.data = {}

    def hash(self, path: Path) -> str:
        st = path.stat()
        key = path.relative_to(self.root).as_posix()
        hit = self.data.get(key)
        if hit and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
            return hit[2]
        h = content_hash(path.read_bytes(), path.name)
        self.data[key] = [st.st_mtime_ns, st.st_size, h]
        self.dirty = True
        return h

    def save(self) -> None:
        if not self.dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, sort_keys=True))
        os.replace(tmp, self.path)
        self.dirty = False
