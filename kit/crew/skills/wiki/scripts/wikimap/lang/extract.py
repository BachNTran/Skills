"""Per-file extraction entry point (spec §3.1). `extract()` never raises.

Adapters (lang_py, lang_c, lang_js, lang_misc) return a partial result; this module adds
the language-independent parts: skip detection, REQ ids, mentions, SQL/route strings,
doc refs, `wiki: ignore` / `wiki: skip` comments and test flags.
"""
from __future__ import annotations

import re

ADAPTER_VERSION = "2"

LANG_BY_EXT: dict[str, str] = {
    ".py": "python", ".pyi": "python",
    ".c": "c", ".h": "c",
    ".cc": "cpp", ".cpp": "cpp", ".cxx": "cpp", ".hpp": "cpp", ".hh": "cpp", ".hxx": "cpp", ".ino": "cpp",
    ".js": "js", ".mjs": "js", ".cjs": "js", ".jsx": "js",
    ".ts": "ts", ".tsx": "ts", ".mts": "ts",
    ".go": "go", ".rs": "rust",
    ".java": "clike", ".kt": "clike", ".cs": "clike", ".swift": "clike",
    ".proto": "proto", ".sql": "sql", ".sh": "shell", ".bash": "shell",
}
HEADER_EXT = (".h", ".hh", ".hpp", ".hxx")
MAX_BYTES = 1 << 20

_REQ = re.compile(r"\b(?:REQ|FEAT)-[A-Z0-9]+(?:-[A-Z0-9]+)*-\d+\b")
_MENTION = re.compile(r"\b[a-z_][a-z0-9_]*(?:\.[a-z_][a-z0-9_]*)*\.[A-Z][A-Za-z0-9_]*\b")
_SQL = re.compile(r"\b(INSERT(?: OR \w+)? INTO|FROM|UPDATE|JOIN)\s+[`\"\[]?(\w+)")
_IGNORE = re.compile(r"wiki:\s*ignore\s+([A-Z][A-Z0-9_]*(?:\s*,\s*[A-Z][A-Z0-9_]*)*)")
_SKIP = re.compile(r"wiki:\s*skip\b")
_TEST_DIRS = ("test", "tests", "__tests__")


def lang_of(rel: str) -> str | None:
    """Language of a repo-relative path by extension (`.h` reports `c`; content may upgrade it)."""
    m = re.search(r"(\.[^./\\]+)$", rel)
    return LANG_BY_EXT.get(m.group(1).lower()) if m else None


def is_test_path(rel: str) -> bool:
    parts = rel.replace("\\", "/").split("/")
    if any(p in _TEST_DIRS for p in parts[:-1]):
        return True
    base = parts[-1]
    return bool(re.match(r"^test_", base) or re.search(r"_test\.[^.]+$", base)
                or re.search(r"\.(test|spec)\.[^.]+$", base))


def empty(lang: str | None) -> dict:
    return {"lang": lang, "ok": True, "conf": "high", "skip": None, "file_doc": None, "symbols": [],
            "calls": [], "imports": [], "refs": [], "strings": [], "reqs": [], "mentions": [], "errors": []}


_CPP_HINT = re.compile(r"\bnamespace\b|\bclass\s+\w|\btemplate\s*<|::|#\s*include\s*<(?:iostream|string|vector|memory|cstdint|cstddef|cstring|cstdio|map|array|algorithm|utility|functional|optional)>"
                       r"|\b(?:public|private|protected)\s*:")


def _decode(data: bytes):
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    if b"\x00" in data[:8192]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def extract(rel: str, data: bytes, cfg: dict | None = None) -> dict:
    """Extract symbols, calls, imports, docs from one file. Never raises."""
    lang = lang_of(rel)
    try:
        return _extract(rel, data, cfg or {}, lang)
    except RecursionError:
        r = empty(lang)
        r.update(ok=False, conf="low", errors=["recursion limit"])
        return r
    except Exception as e:  # never raise on repo content
        r = empty(lang)
        r.update(ok=False, conf="low", errors=[f"{type(e).__name__}: {e}"[:300]])
        return r


def _extract(rel: str, data: bytes, cfg: dict, lang: str | None) -> dict:
    r = empty(lang)
    if lang is None:
        return r
    if len(data) > MAX_BYTES:
        r["skip"] = "size"
        return r
    text = _decode(data)
    if text is None:
        r["skip"] = "binary"
        return r
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    head = text.split("\n", 20)[:20]
    if any(len(ln) > 500 for ln in head):
        r["skip"] = "minified"
        return r
    if lang == "c" and rel.lower().endswith(".h") and _CPP_HINT.search(text):
        lang = "cpp"
    r["lang"] = lang
    test_file = is_test_path(rel)
    ctx = {"rel": rel, "test_file": test_file, "header": rel.lower().endswith(HEADER_EXT), "cfg": cfg}
    if lang == "python":
        from . import lang_py as ad
        part = ad.extract_py(text, ctx)
    elif lang in ("c", "cpp"):
        from . import lang_c as ad
        part = ad.extract_c(text, ctx, lang)
    elif lang in ("js", "ts"):
        from . import lang_js as ad
        part = ad.extract_js(text, ctx, lang)
    else:
        from . import lang_misc as ad
        part = ad.extract_misc(text, ctx, lang)
    r.update({k: v for k, v in part.items() if not k.startswith("_")})
    _common(r, text, part, ctx)
    return r


def _owner(spans, line):
    best = None
    for a, b, q in spans:
        if a <= line <= b and (best is None or a >= best[0] and b - a <= best[1] - best[0]):
            best = (a, b, q)
    return best[2] if best else None


def _common(r: dict, text: str, part: dict, ctx: dict) -> None:
    syms = r["symbols"]
    lines = text.split("\n")
    # owner spans include the attached doc and decorators
    spans = []
    for s in syms:
        a = s.pop("_start", s["line"])
        if s.get("doc"):
            a = min(a, s["doc"]["line"])
        spans.append((a, s["end"], s["qual"]))
    owner = lambda ln: _owner(spans, ln)  # noqa: E731

    # refs from docs
    refs = []
    for s in syms:
        d = s.get("doc")
        if d:
            for t, st, ln in d.pop("_refs", []):
                refs.append({"text": t, "style": st, "line": ln, "from": s["qual"]})
            d.pop("_file", None)
    fd = r.get("file_doc")
    if fd:
        for t, st, ln in fd.pop("_refs", []):
            refs.append({"text": t, "style": st, "line": ln, "from": None})
        fd.pop("_file", None)
    r["refs"] = refs

    # REQ ids anywhere in the text
    reqs = [] if not r["reqs"] else list(r["reqs"])
    seen = {(q["id"], q["line"]) for q in reqs}
    for i, ln in enumerate(lines, 1):
        for m in _REQ.finditer(ln):
            if (m.group(), i) not in seen:
                seen.add((m.group(), i))
                reqs.append({"id": m.group(), "line": i, "from": owner(i)})
    reqs.sort(key=lambda q: (q["line"], q["id"]))
    r["reqs"] = reqs

    # mentions in comments, docs and string literals
    blobs = list(part.get("_texts", []))
    for s in syms:
        if s.get("doc"):
            blobs.append(s["doc"]["text"])
    if fd:
        blobs.append(fd["text"])
    ments = set()
    for b in blobs:
        for m in _MENTION.finditer(b):
            ments.add(m.group())
    r["mentions"] = sorted(ments)

    # SQL table names in string literals
    strs = list(r["strings"])
    for ln, val in part.get("_strings", []):
        for m in _SQL.finditer(val):
            kw = m.group(1).split()[0]
            strs.append({"kind": "sql", "value": m.group(2), "op": kw, "line": ln, "from": owner(ln)})
    for s in strs:
        if s.get("from") is None and s.get("line"):
            s["from"] = owner(s["line"])
    strs.sort(key=lambda s: (s["line"], s["kind"], s["value"]))
    r["strings"] = strs

    # wiki: ignore / wiki: skip
    ign = {}
    for i, ln in enumerate(lines, 1):
        m = _IGNORE.search(ln)
        if m:
            ign[i] = [c.strip() for c in m.group(1).split(",") if c.strip()]
    skip_all = any(_SKIP.search(ln) for ln in lines[:5])
    for s in syms:
        codes = list(s.get("ignore") or [])
        for ln in (s["line"], s["line"] - 1):
            for c in ign.get(ln, []):
                if c not in codes:
                    codes.append(c)
        if skip_all:
            for c in ("UNDOC", "DOCSIG"):
                if c not in codes:
                    codes.append(c)
        s["ignore"] = codes
        if ctx["test_file"] and s["kind"] in ("function", "method") and s["name"].startswith("test"):
            s["test"] = True
        if s["kind"] == "test":
            s["test"] = True
    syms.sort(key=lambda s: (s["line"], s["qual"]))
    r["imports"].sort(key=lambda m: (m["line"], m["target"], m.get("alias") or ""))
