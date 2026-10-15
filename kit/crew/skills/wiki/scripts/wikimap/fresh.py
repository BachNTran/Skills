"""Doc freshness: findings, the committed baseline, and the ratchet.

Findings say where code docs and the system map disagree with the code. The baseline
(``<root>/.wikimap/baseline.json``, committed) records each symbol's
``[sig_hash, body_hash, doc_hash]`` and the findings that already existed when it was created
(debt). Only ``W map``, ``W sync`` and a hook in an opted-in repo write it; ``check`` and
``open_map()`` never do.

Works against the ``Map`` contract (spec §6): ``nodes``, ``children``, ``edges``, ``files``,
``modules``, ``diagrams``, ``anc()``, ``module_of()``. Repo text is data, never executed.
"""
from __future__ import annotations

import copy
import json
import os
import re
import stat
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = ".wikimap"
BASELINE = "baseline.json"
ACKS = "acks.jsonl"
CONFIG = "config.json"

CODES = ("XCALL", "DOCSTALE", "DOCSIG", "UNDOC", "DOCREVIEW", "ICDSYM", "DEADLINK", "DIAGNODE", "UNDRAWN")
SYMBOL_CODES = frozenset({"UNDOC", "DOCSIG", "DOCSTALE", "DOCREVIEW", "DEADLINK"})
DOC_CODES = frozenset({"DIAGNODE", "UNDRAWN", "ICDSYM"})
STALE_CODES = frozenset({"DOCSTALE", "DOCREVIEW"})
_ORDER = {c: i for i, c in enumerate(CODES)}
NONE = "-"


class BaselineError(Exception):
    """``.wikimap/baseline.json`` exists but cannot be parsed."""


class ConfigError(Exception):
    """``.wikimap/config.json`` exists but is not valid JSON / not an object."""


@dataclass
class Finding:
    """One finding; ``line()`` is modgate's ``Finding.line`` algorithm verbatim."""

    code: str
    severity: str
    module: str
    id: str
    files: list[str]
    action: str
    node: str | None = None
    src: tuple = field(default=(), repr=False, compare=False)  # repo-rel files that scope it

    @property
    def label(self) -> str:
        return ("E:" if self.severity == "violation" else "") + self.code

    @property
    def key(self) -> str:
        return f"{self.code}|{self.module}|{self.id}"

    def line(self) -> str:
        parts = [f"{self.label:<10}", self.module]
        if self.id:
            parts.append(self.id)
        if self.files:
            parts.append(" ".join(self.files))
        text = "  ".join(parts)
        return f"{text}  → {self.action}" if self.action else text

    def json(self) -> dict:
        return {"code": self.code, "severity": self.severity, "module": self.module, "id": self.id,
                "files": list(self.files), "action": self.action, "node": self.node, "key": self.key}


def sort_findings(fs: list[Finding]) -> list[Finding]:
    return sorted(fs, key=lambda f: (_ORDER.get(f.code, 99), f.module, f.id, f.files))


# ---- config and baseline files -------------------------------------------------------------

def load_config(root: Path) -> dict:
    """Read ``.wikimap/config.json`` (missing → ``{}``); raises ConfigError when invalid."""
    p = Path(root) / BASE_DIR / CONFIG
    try:
        raw = p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    except OSError as e:
        raise ConfigError(f"{BASE_DIR}/{CONFIG} unreadable: {e.strerror or e}") from None
    try:
        cfg = json.loads(raw) if raw.strip() else {}
    except ValueError as e:
        raise ConfigError(f"{BASE_DIR}/{CONFIG} is not valid JSON: {e}") from None
    if not isinstance(cfg, dict):
        raise ConfigError(f"{BASE_DIR}/{CONFIG} must be a JSON object")
    return cfg


def _cfg(m) -> dict:
    cfg = getattr(m, "config", None)
    if isinstance(cfg, dict):
        return cfg
    try:
        return load_config(m.root)
    except ConfigError:
        return {}


def violations_of(cfg: dict) -> set[str]:
    v = cfg.get("violations") or []
    return {str(c) for c in v} if isinstance(v, list) else set()


def empty_baseline() -> dict:
    return {"v": 1, "created": None, "symbols": {}, "debt": []}


def load_baseline(root: Path) -> dict | None:
    """Missing → None. Unparseable or wrong shape → BaselineError. Never re-baselines."""
    p = Path(root) / BASE_DIR / BASELINE
    try:
        raw = p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as e:
        raise BaselineError(str(e)) from None
    try:
        data = json.loads(raw)
    except ValueError as e:
        raise BaselineError(str(e)) from None
    if not isinstance(data, dict) or data.get("v") != 1:
        raise BaselineError("not a v1 baseline")
    syms, debt = data.get("symbols"), data.get("debt")
    if not isinstance(syms, dict) or not isinstance(debt, list):
        raise BaselineError("symbols/debt missing")
    for k, v in syms.items():
        if not (isinstance(v, list) and len(v) == 3 and all(isinstance(x, str) for x in v)):
            raise BaselineError(f"bad entry {k!r}")
    if not all(isinstance(k, str) for k in debt):
        raise BaselineError("bad debt entry")
    return {"v": 1, "created": data.get("created"), "symbols": dict(syms), "debt": list(debt)}


def dumps_baseline(base: dict) -> str:
    """The hand-rolled shape: keys sorted, one entry per line, trailing newline."""
    def s(x) -> str:
        return json.dumps(x, ensure_ascii=False)

    out = ['{"v": 1,', f' "created": {s(base.get("created"))},']
    syms = sorted(base.get("symbols", {}).items())
    if syms:
        out.append(' "symbols": {')
        out += [f"  {s(k)}: {s(list(v))}" + ("," if i < len(syms) - 1 else "") for i, (k, v) in enumerate(syms)]
        out.append(" },")
    else:
        out.append(' "symbols": {},')
    debt = sorted(set(base.get("debt", [])))
    if debt:
        out.append(' "debt": [')
        out += [f"  {s(k)}" + ("," if i < len(debt) - 1 else "") for i, k in enumerate(debt)]
        out.append(" ]")
    else:
        out.append(' "debt": []')
    out.append("}")
    return "\n".join(out) + "\n"


def _atomic_write(path: Path, text: str) -> None:
    """Temp file + rename. Writes through a symlink (dotfile managers) and keeps the file's mode
    (0644 for a new file) instead of mkstemp's 0600."""
    path = Path(path)
    if path.is_symlink():
        path = path.resolve()
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
    except OSError:
        mode = 0o644
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save_baseline(root: Path, base: dict) -> None:
    _atomic_write(Path(root) / BASE_DIR / BASELINE, dumps_baseline(base))


def append_ack(root: Path, key: str, reason: str, hashes: list[str]) -> None:
    p = Path(root) / BASE_DIR / ACKS
    p.parent.mkdir(parents=True, exist_ok=True)
    rec = {"ts": now_iso(), "key": key, "reason": reason, "hashes": list(hashes)}
    with p.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---- symbol view over the Map --------------------------------------------------------------

_CALLABLE = {"function", "method", "ctor", "test", "macro"}


def _pname(p) -> str:
    if isinstance(p, dict):
        p = p.get("name") or ""
    return str(p or "").strip()


def _norm_param(p: str) -> str:
    p = p.split("=", 1)[0].split(":", 1)[0].strip()
    return p.lstrip("*&.").strip()


def mod_name(m, nid: str | None) -> str:
    try:
        name = m.module_of(nid) if nid else None
    except Exception:
        name = None
    return name or "(root)"


def mod_dir(m, name: str) -> str | None:
    info = m.modules.get(name) if name and name != "(root)" else None
    return (info or {}).get("id")


def modrel(m, name: str, rel: str) -> str:
    """Module-relative path (repo-relative for ``(root)`` or the repo-root module)."""
    mid = mod_dir(m, name)
    if mid and mid != "." and rel.startswith(mid + "/"):
        return rel[len(mid) + 1:]
    return rel


def _rec_index(m) -> dict:
    idx: dict = {}
    for rel, f in m.files.items():
        rec = (f or {}).get("rec") or {}
        for s in rec.get("symbols") or []:
            idx.setdefault((rel, s.get("qual")), []).append(s)
    return idx


def _find_rec(idx: dict, rel: str | None, qual: str | None, line) -> dict | None:
    cands = idx.get((rel, qual)) or []
    for s in cands:
        if s.get("line") == line:
            return s
    return cands[0] if cands else None


def symbols(m) -> dict[str, dict]:
    """``{node id: sym}`` for every symbol node, with hashes and flags joined from the extract
    records. Cached on the Map per ``rev``."""
    cache = getattr(m, "_wk_syms", None)
    rev = getattr(m, "rev", None)
    if cache and cache[0] == rev and cache[1] is not None and rev is not None:
        return cache[1]
    idx = _rec_index(m)
    out: dict[str, dict] = {}
    for nid, n in m.nodes.items():
        if n.get("type") != "symbol":
            continue
        src = n.get("src") or [None, None, None]
        rel, line = src[0], (src[1] if len(src) > 1 else None)
        rec = _find_rec(idx, rel, n.get("qual"), line) or {}
        decl = n.get("decl") or None
        drec = _find_rec(idx, decl[0], n.get("qual"), decl[1]) if decl else None
        doc = n.get("doc") or None
        sig = n.get("sig_hash") or rec.get("sig_hash") or NONE
        body = n.get("body_hash") or rec.get("body_hash") or NONE
        ignore = set(rec.get("ignore") or []) | set((drec or {}).get("ignore") or [])
        flags = {k: bool(n.get(k, rec.get(k)) or (drec or {}).get(k)) for k in ("override", "test", "static")}
        params = n.get("params") if n.get("params") is not None else rec.get("params") or []
        files = {rel} if rel else set()
        if decl and decl[0]:
            files.add(decl[0])
        module = mod_name(m, nid)
        out[nid] = {
            "id": nid, "key": n.get("key") or nid, "qual": n.get("qual") or n.get("name") or nid,
            "name": n.get("name") or rec.get("name") or "", "kind": n.get("kind") or rec.get("kind") or "",
            "lang": (m.files.get(rel) or {}).get("lang") or n.get("lang") or "",
            "file": rel, "line": line, "end": src[2] if len(src) > 2 else line, "files": files,
            "pub": bool(n.get("pub", rec.get("pub"))),
            "doc": doc, "doc_hash": (doc or {}).get("hash") or (NONE if not doc else _doc_hash(doc)),
            "sig": sig, "body": body, "ignore": ignore, "params": [_pname(p) for p in params],
            "sig_text": n.get("sig") or rec.get("sig") or "", "module": module, **flags,
        }
    try:
        m._wk_syms = (rev, out)
    except Exception:
        pass
    return out


def _doc_hash(doc: dict) -> str:
    import hashlib
    text = " ".join(str(doc.get("text") or doc.get("brief") or "").split())
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def entry(sym: dict) -> list[str]:
    return [sym["sig"] or NONE, sym["body"] or NONE, sym["doc_hash"] if sym["doc"] else NONE]


def current_entries(m, files: set[str] | None = None) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for sym in symbols(m).values():
        if files is not None and not (sym["files"] & files):
            continue
        out.setdefault(sym["key"], entry(sym))
    return out


def create_baseline(m) -> dict:
    """A new baseline: every symbol's hashes, every current finding recorded as debt."""
    base = empty_baseline()
    base["created"] = now_iso()
    base["symbols"] = current_entries(m)
    base["debt"] = sorted({f.key for f, _ in _raw(m, empty_baseline())})
    return base


def changed_files(m, base: dict | None) -> set[str]:
    """Files holding a symbol that is new or whose hashes differ from the baseline."""
    syms = (base or {}).get("symbols") or {}
    out: set[str] = set()
    for sym in symbols(m).values():
        if syms.get(sym["key"]) != entry(sym):
            out |= sym["files"]
    return out


# ---- finding rules -------------------------------------------------------------------------

def _undoc_exempt(sym: dict) -> bool:
    name, kind, sig = sym["name"].split("::")[-1], sym["kind"], sym["sig_text"]
    if sym["override"] or sym["test"] or kind in ("test", "macro", "ctor", "namespace", "table"):
        return True
    if name.startswith("~") or "= default" in sig or ".setter" in sig or "@setter" in sig:
        return True
    if name.startswith("__") and name.endswith("__"):
        return True
    if kind == "const" and sym["lang"] == "python":
        return True
    return False


def _undoc_action(sym: dict) -> str:
    name = sym["name"].split("::")[-1].split(".")[-1]
    call = f"{name}()" if sym["kind"] in _CALLABLE else name
    lang = sym["lang"]
    if lang in ("c", "cpp"):
        return f"add a /// doc comment above {call}: what it does, units, errors"
    if lang == "python":
        return f"add a docstring to {call}: what it does, units, errors"
    if lang in ("js", "ts"):
        return f"add a /** JSDoc */ above {call}: what it does, units, errors"
    return f"add a doc comment above {call}: what it does, units, errors"


_IGNORABLE = {"self", "cls", "this"}


def _docsig(sym: dict) -> tuple[list[str], list[str]] | None:
    doc = sym["doc"]
    if not doc or not doc.get("explicit_params"):
        return None
    documented = [_norm_param(str(k)) for k in (doc.get("params") or {})]
    documented = [d for d in documented if d]
    dset = set(documented)
    sig: list[str] = []
    for raw in sym["params"]:
        p = _norm_param(raw)
        if not p or p == "void":
            continue
        var = raw.lstrip().startswith(("*", "..."))
        if (p in _IGNORABLE or var) and p not in dset:
            continue
        sig.append(p)
    if dset == set(sig):
        return None
    return documented, sig


def _py_module_id(m, name: str, rel: str) -> str:
    r = modrel(m, name, rel)
    parts = r[:-3].split("/") if r.endswith(".py") else r.split("/")
    if len(parts) > 1 and parts[0] in ("src", "lib"):
        parts = parts[1:]
    if parts and parts[-1] == "__init__" and len(parts) > 1:
        parts = parts[:-1]
    return ".".join(parts)


def broken_files(m) -> set[str]:
    """Files whose extract fell back to the regex scanner (``ok: false``, e.g. a half-typed edit):
    their docs and hashes are unknown, so symbol checks and baseline transitions skip them."""
    return {rel for rel, f in (m.files or {}).items() if ((f or {}).get("rec") or {}).get("ok") is False}


def _symbol_findings(m, base: dict, syms: dict, files: set[str] | None, cfg: dict) -> list[tuple]:
    """UNDOC, DOCSIG, DOCSTALE, DOCREVIEW → list of (code, sym, extra)."""
    undoc_on = cfg.get("undoc", "public") != "off"
    bsyms = base.get("symbols") or {}
    broken = broken_files(m)
    out = []
    for sym in syms.values():
        if files is not None and not (sym["files"] & files):
            continue
        if sym["files"] & broken:
            continue
        finfo = m.files.get(sym["file"]) or {}
        old = bsyms.get(sym["key"])
        doc = sym["doc"]
        if not doc:
            if (undoc_on and sym["pub"] and finfo.get("insrc") and not finfo.get("test")
                    and not finfo.get("vendor") and not _undoc_exempt(sym) and "UNDOC" not in sym["ignore"]):
                out.append(("UNDOC", sym, None))
            continue
        ds = _docsig(sym)
        if ds and "DOCSIG" not in sym["ignore"]:
            out.append(("DOCSIG", sym, ds))
        if old and old[2] == sym["doc_hash"]:
            if old[0] != sym["sig"]:
                if "DOCSTALE" not in sym["ignore"]:
                    out.append(("DOCSTALE", sym, None))
            elif old[1] != sym["body"] and "DOCREVIEW" not in sym["ignore"]:
                out.append(("DOCREVIEW", sym, None))
    return out


def _py_module_undoc(m, syms: dict, files: set[str] | None, cfg: dict) -> list[Finding]:
    if cfg.get("undoc", "public") == "off":
        return []
    by_file: dict[str, list[dict]] = {}
    for sym in syms.values():
        by_file.setdefault(sym["file"], []).append(sym)
    quals = {(s["module"], s["qual"]) for s in syms.values()}
    out = []
    for rel, f in m.files.items():
        if files is not None and rel not in files:
            continue
        f = f or {}
        if f.get("lang") != "python" or not f.get("insrc") or f.get("test") or f.get("vendor"):
            continue
        base = rel.rsplit("/", 1)[-1]
        if base in ("__main__.py", "conftest.py", "setup.py"):
            continue
        rec = f.get("rec") or {}
        if rec.get("skip") or rec.get("file_doc") or rec.get("ok") is False:
            continue  # a file that does not parse cannot prove its docstring is missing
        mine = by_file.get(rel) or []
        if not any(s["pub"] for s in mine) or all("UNDOC" in s["ignore"] for s in mine):
            continue
        name = mod_name(m, f.get("node") or rel)
        mid = _py_module_id(m, name, rel)
        if (name, mid) in quals:
            mid = modrel(m, name, rel)  # `decode` in decode.py: keep the module key apart from the symbol's
        out.append(Finding("UNDOC", "finding", name, mid, [f"{modrel(m, name, rel)}:1"],
                           "add a module docstring: what it is for", f.get("node") or rel, (rel,)))
    return out


_URL = re.compile(r"^[a-z][a-z0-9+.-]*://", re.I)


def _ref_target(text: str) -> str:
    t = (text or "").strip().split()[0] if (text or "").strip() else ""
    t = t.strip("`'\"<>[]{}").rstrip(".,;:")
    if t.endswith("()"):
        t = t[:-2]
    return t.lstrip("~!")


def _deadlinks(m, syms: dict, files: set[str] | None) -> list[Finding]:
    names: set[str] = set()
    quals: set[str] = set()
    for sym in syms.values():
        q = sym["qual"]
        quals.add(q)
        names.add(re.split(r"::|\.|#", q)[-1])
        if sym["name"]:
            names.add(sym["name"].split("::")[-1].split(".")[-1])
    names |= set(m.modules)
    bases = {rel.rsplit("/", 1)[-1] for rel in m.files} | set(m.files)
    by_fq = {(s["file"], s["qual"]): s for s in syms.values()}
    out = []
    for rel, f in m.files.items():
        if files is not None and rel not in files:
            continue
        f = f or {}
        if f.get("vendor"):
            continue
        for ref in (f.get("rec") or {}).get("refs") or []:
            text = str(ref.get("text") or "")
            if _URL.match(text.strip()):
                continue
            tgt = _ref_target(text)
            if not tgt or tgt in bases or tgt in quals or tgt.replace("#", ".") in quals:
                continue
            if re.split(r"::|\.|#", tgt)[-1] in names:
                continue
            frm = ref.get("from")
            sym = by_fq.get((rel, frm)) if frm else None
            if sym and "DEADLINK" in sym["ignore"]:
                continue
            name = sym["module"] if sym else mod_name(m, f.get("node") or rel)
            ident = frm or modrel(m, name, rel)
            out.append(Finding("DEADLINK", "finding", name, ident, [f"{modrel(m, name, rel)}:{ref.get('line') or 1}"],
                               f'@see target "{tgt}" matches no symbol; fix the name or drop it',
                               sym["id"] if sym else f.get("node"), (rel,)))
    return out


_ICD_LANGS = {"", "c", "cpp", "c++", "h", "hpp", "py", "python", "ts", "typescript", "js", "javascript"}
_ICD_HEAD = re.compile(r"api|interface", re.I)
_ICD_IDENT = re.compile(r"\b([A-Za-z_]\w*(?:::\w+)*)\(")
_KEYWORDS = set("""if for while switch catch return sizeof decltype alignof alignas static_assert do else new
delete throw typeof typeid noexcept operator template def class lambda assert yield await async function
constructor super print isinstance len range defined elif not and or in is with except raise import from
const let var static inline virtual explicit constexpr typename struct union enum namespace using""".split())
_PRIMS = set("""void int char float double bool long short unsigned signed auto size_t ssize_t ptrdiff_t
intptr_t uintptr_t wchar_t str bytes list dict tuple set frozenset object string number boolean any never
unknown bigint symbol Promise Array Map Set Record""".split())


def _icd_skip(ident: str) -> bool:
    last = ident.split("::")[-1]
    if last in _KEYWORDS or last in _PRIMS or ident in _KEYWORDS:
        return True
    if re.fullmatch(r"u?int\d+_t", last) or re.fullmatch(r"[A-Z0-9_]+", last):
        return True
    return ident.startswith("std::")


def _read_doc(m, rel: str) -> str | None:
    try:
        root = Path(m.root).resolve()
        p = (root / rel).resolve()
        if root not in p.parents or not p.is_file() or p.stat().st_size > 1_000_000:
            return None
        return p.read_bytes().decode("utf-8", "replace")
    except OSError:
        return None


def _icdsym(m, syms: dict, files: set[str] | None) -> list[Finding]:
    try:
        from . import mdparse
    except ImportError:
        return []
    by_mod: dict[str, list[dict]] = {}
    for sym in syms.values():
        by_mod.setdefault(sym["module"], []).append(sym)
    out = []
    for name, info in m.modules.items():
        icd = (info or {}).get("icd")
        if isinstance(icd, dict):
            icd = icd.get("item")
        if not icd or (files is not None and icd not in files):
            continue
        text = _read_doc(m, icd)
        if text is None:
            continue
        mid = info.get("id") or ""
        mods = {n for n, i in m.modules.items()
                if mid in (".", "") or (i or {}).get("id") == mid or str((i or {}).get("id", "")).startswith(mid + "/")}
        names: set[str] = set()
        quals: list[str] = []
        for mn in mods:
            for s in by_mod.get(mn, []):
                names.add(s["name"].split("::")[-1].split(".")[-1])
                quals.append(s["qual"])
        seen: set[str] = set()
        for fence in mdparse.code_fences(text):
            if (fence.get("lang") or "").strip().lower() not in _ICD_LANGS:
                continue
            if not _ICD_HEAD.search(fence.get("heading") or ""):
                continue
            body = fence.get("body") or ""
            for mt in _ICD_IDENT.finditer(body):
                ident = mt.group(1)
                if ident in seen or _icd_skip(ident):
                    continue
                last = ident.split("::")[-1]
                if "::" not in ident and last in names:
                    continue
                if any(q == ident or q.endswith("::" + ident) or q.endswith("." + ident) for q in quals):
                    continue
                seen.add(ident)
                line = int(fence.get("line") or 0) + 1 + body[:mt.start()].count("\n")
                out.append(Finding("ICDSYM", "finding", name, ident, [f"{modrel(m, name, icd)}:{line}"],
                                   f"ICD names {ident}(), no such symbol; fix the ICD (modgate: version +1, "
                                   f"status draft, changelog) or restore it", info.get("id"), (icd,)))
    return out


def _is_within(a: str, b: str) -> bool:
    """True when module dir ``a`` is ``b`` or below it."""
    return b in (".", "") or a == b or a.startswith(b + "/")


def _xcall(m, files: set[str] | None) -> list[Finding]:
    if not getattr(m, "modgate", False):
        return []
    first: dict[tuple, dict] = {}
    for e in m.edges:
        if e.get("k") not in ("import", "call", "inherit") or float(e.get("conf") or 0) < 0.8:
            continue
        s, t = e.get("s"), e.get("t")
        a, b = mod_name(m, s), mod_name(m, t)
        if a == "(root)" or b == "(root)" or a == b:
            continue
        ainfo, binfo = m.modules.get(a) or {}, m.modules.get(b) or {}
        if b in set(ainfo.get("closure") or []) or b in set(ainfo.get("deps") or []):
            continue
        ad, bd = ainfo.get("id") or "", binfo.get("id") or ""
        if not ad or not bd or _is_within(ad, bd) or _is_within(bd, ad):
            continue
        tn = m.nodes.get(t) or {}
        if tn.get("vendor") or (m.files.get(str(t).split("#", 1)[0]) or {}).get("vendor"):
            continue
        site = (str(e.get("file") or ""), int(e.get("line") or 0))
        cur = first.get((a, b))
        if cur is None or site < (str(cur.get("file") or ""), int(cur.get("line") or 0)):
            first[(a, b)] = e
    out = []
    for (a, b), e in first.items():
        rel = str(e.get("file") or "")
        if files is not None and rel not in files:
            continue
        loc = [f"{modrel(m, a, rel)}:{e.get('line') or 1}"] if rel else []
        out.append(Finding("XCALL", "finding", a, b, loc,
                           f"{a} uses {b} but {b} is not reachable through {a}'s deps; "
                           f"add it to deps (needs approval) or remove the coupling", e.get("s"), (rel,)))
    return out


def _diagram_findings(m, files: set[str] | None) -> list[Finding]:
    out = []
    for cid, d in (m.diagrams or {}).items():
        doc = (d or {}).get("doc")
        if not doc or (files is not None and doc not in files):
            continue
        name = mod_name(m, cid)
        drel = modrel(m, name, doc)
        dnodes = d.get("nodes") or {}
        for mid, n in dnodes.items():
            if n.get("ref") or n.get("ext") or n.get("shape") != "module":
                continue
            label = str(n.get("label") or mid).splitlines()[0] if (n.get("label") or mid) else mid
            out.append(Finding("DIAGNODE", "finding", name, mid, [f"{drel}:{n.get('line') or 1}"],
                               f'Mermaid node "{label}" matches no module; use the module name or mark it :::ext',
                               cid, (doc,)))
        refs = {n.get("ref") for n in dnodes.values() if n.get("ref")}
        for sg in (d.get("subgraphs") or {}).values():
            if isinstance(sg, dict) and sg.get("ref"):
                refs.add(sg["ref"])
        lines = [n.get("line") for n in dnodes.values() if n.get("line")]
        line = d.get("line") or (min(lines) if lines else 1)
        for ch in m.children.get(cid, []):
            cn = m.nodes.get(ch) or {}
            if cn.get("tier") != "sys" or cn.get("type") not in ("module", "group"):
                continue
            if any(r == ch or str(r).startswith(ch + "/") or str(r).startswith(ch + "#") for r in refs):
                continue
            cname = cn.get("name") or ch.rsplit("/", 1)[-1]
            out.append(Finding("UNDRAWN", "finding", name, cname, [f"{drel}:{line}"],
                               f'add {cname} to "Subsystems and interactions" in {doc} with a labelled edge',
                               ch, (doc,)))
    return out


def _raw(m, base: dict, *, files: set[str] | None = None) -> list[tuple[Finding, bool]]:
    """Every finding in file scope, paired with ``hidden`` (true when it is recorded debt)."""
    cfg = _cfg(m)
    viol = violations_of(cfg)
    syms = symbols(m)
    bsyms = base.get("symbols") or {}
    debt = set(base.get("debt") or [])
    fs: list[Finding] = []
    for code, sym, extra in _symbol_findings(m, base, syms, files, cfg):
        name = sym["module"]
        loc = [f"{modrel(m, name, sym['file'])}:{sym['line']}"] if sym["file"] else []
        if code == "UNDOC":
            action = _undoc_action(sym)
        elif code == "DOCSIG":
            action = f"doc names [{', '.join(extra[0])}], signature has [{', '.join(extra[1])}]: fix the params section"
        elif code == "DOCSTALE":
            action = (f"signature changed since its doc was confirmed; update the doc, or: "
                      f'wiki ack {sym["key"]} --unchanged "<why>"')
        else:
            action = f'body changed, doc unchanged; check every claim in the doc, or: wiki ack {sym["key"]} --unchanged "<why>"'
        fs.append(Finding(code, "finding", name, sym["qual"], loc, action, sym["id"], tuple(sorted(sym["files"]))))
    fs += _py_module_undoc(m, syms, files, cfg)
    fs += _deadlinks(m, syms, files)
    fs += _icdsym(m, syms, files)
    fs += _xcall(m, files)
    fs += _diagram_findings(m, files)
    sym_by_id = syms
    out = []
    for f in sort_findings(fs):
        if f.code in viol:
            f.severity = "violation"
        hidden = f.key in debt
        if hidden and f.code == "UNDOC":
            sym = sym_by_id.get(f.node or "")
            if sym is not None:
                old = bsyms.get(sym["key"])
                hidden = bool(old) and old[0] == sym["sig"] and old[1] == sym["body"]
        out.append((f, hidden))
    return out


def compute(m, base: dict | None, *, files: set[str] | None = None, modules: set[str] | None = None,
            codes: set[str] | None = None, all_: bool = False) -> list[Finding]:
    """Findings in scope, sorted. Default hides recorded debt (UNDOC re-surfaces once its code
    changes); ``all_`` shows it."""
    base = base or empty_baseline()
    out = []
    for f, hidden in _raw(m, base, files=files):
        if hidden and not all_:
            continue
        if modules is not None and f.module not in modules:
            continue
        if codes is not None and f.code not in codes:
            continue
        out.append(f)
    return out


def annotate(m) -> None:
    """Set ``m.findings`` (default scope) and node badges ``stale/findings/debt``. Never writes
    the baseline and never raises: an absent or unreadable baseline means empty debt."""
    try:
        try:
            base = load_baseline(m.root) or empty_baseline()
        except BaselineError:
            base = empty_baseline()
        raw = _raw(m, base)
        m.findings = [f for f, hidden in raw if not hidden]
        for n in m.nodes.values():
            b = n.get("badges")
            if not isinstance(b, dict):
                b = n["badges"] = {}
            b["stale"] = b["findings"] = b["debt"] = 0
        for f, hidden in raw:
            nid = f.node if f.node in m.nodes else None
            if nid is None:
                continue
            try:
                chain = list(m.anc(nid)) + [nid]
            except Exception:
                chain = [nid]
            for a in chain:
                b = (m.nodes.get(a) or {}).get("badges")
                if b is None:
                    continue
                if hidden:
                    b["debt"] += 1
                else:
                    b["findings"] += 1
                    if f.code in STALE_CODES:
                        b["stale"] += 1
    except Exception:
        try:
            m.findings = []
        except Exception:
            pass


# ---- the ratchet ---------------------------------------------------------------------------

def _key_file(key: str) -> str | None:
    return None if key.startswith("cpp:") else key.split("#", 1)[0]


def _key_qual(key: str) -> str:
    if key.startswith("cpp:"):
        rest = key[4:].split(":", 1)
        q = rest[1] if len(rest) > 1 else rest[0]
        return q.rsplit("~", 1)[0]
    q = key.split("#", 1)[1] if "#" in key else key
    return re.sub(r"~\d+$", "", q)


def _key_moddir(m, key: str) -> str | None:
    if key.startswith("cpp:"):
        return key[4:].split(":", 1)[0]
    rel = _key_file(key) or ""
    f = m.files.get(rel)
    if f and f.get("mod") in m.modules:
        return m.modules[f["mod"]].get("id")
    best = None
    for info in m.modules.values():
        mid = (info or {}).get("id")
        if mid and (mid == "." or rel.startswith(mid + "/")) and (best is None or len(mid) > len(best) or best == "."):
            best = mid
    return best


def advance(m, base: dict, *, files: set[str] | None) -> dict:
    """Apply the baseline transitions (spec §7.3 rule 3) for ``files`` (None = everything) and
    return the new baseline. Call after computing findings."""
    new = copy.deepcopy(base)
    bsyms: dict = new.setdefault("symbols", {})
    syms = symbols(m)
    broken = broken_files(m)
    cur_all: dict[str, list[str]] = {}
    key_dir: dict[str, str | None] = {}
    for s in syms.values():
        if s["files"] & broken:
            continue  # unknown until the file parses again: leave its entries and debt alone
        cur_all.setdefault(s["key"], entry(s))
        key_dir.setdefault(s["key"], mod_dir(m, s["module"]))
    if files is not None:
        cur = {k: e for k, e in current_entries(m, files).items() if k in cur_all}
    else:
        cur = cur_all
    scope_dirs = {mod_dir(m, mod_name(m, (m.files.get(r) or {}).get("node") or r)) for r in (files or set())}

    def in_scope(k: str) -> bool:
        if files is None:
            return True
        kf = _key_file(k)
        return kf in files if kf is not None else _key_moddir(m, k) in scope_dirs

    vanished = sorted(k for k in bsyms if k not in cur_all and in_scope(k) and _key_file(k) not in broken)
    fresh_keys = sorted(k for k in cur if k not in bsyms)
    claimed: set[str] = set()
    renames: dict[str, str] = {}
    for k in vanished:
        old = bsyms.pop(k)
        kd = _key_moddir(m, k)
        for nk in fresh_keys:
            if nk not in claimed and key_dir.get(nk) == kd and cur[nk][:2] == old[:2]:
                bsyms[nk] = old
                claimed.add(nk)
                renames[k] = nk
                break
    for k, e in cur.items():
        if k in claimed:
            continue
        old = bsyms.get(k)
        if old is None or old[2] != e[2]:
            bsyms[k] = list(e)
    # debt: renamed symbols carry their debt; keys no longer produced leave it.
    debt = []
    for d in new.get("debt") or []:
        code, _, rest = d.partition("|")
        mod, _, ident = rest.partition("|")
        for ok, nk in renames.items():
            if ident == _key_qual(ok):
                d = f"{code}|{mod}|{_key_qual(nk)}"
                break
        debt.append(d)
    produced = {f.key for f, _ in _raw(m, new, files=files)}
    paused = {_key_qual(k) for k in bsyms if _key_file(k) in broken}
    paused |= {_py_module_id(m, mod_name(m, (m.files.get(r) or {}).get("node") or r), r)
               for r in broken if r.endswith(".py")}
    produced |= {d for d in debt if d.partition("|")[0] in SYMBOL_CODES and d.split("|", 2)[-1] in paused}
    if files is None:
        debt = [d for d in debt if d in produced]
    else:
        mods = {mod_name(m, (m.files.get(r) or {}).get("node") or r) for r in files}
        idents = {_key_qual(k) for k in list(cur) + vanished}
        idents |= {_py_module_id(m, mod_name(m, (m.files.get(r) or {}).get("node") or r), r)
                   for r in files if r.endswith(".py")}

        def droppable(d: str) -> bool:
            code, mod, ident = (d.split("|", 2) + ["", ""])[:3]
            return code in SYMBOL_CODES and mod in mods and ident in idents and d not in produced
        debt = [d for d in debt if not droppable(d)]
    new["debt"] = sorted(set(debt))
    return new
