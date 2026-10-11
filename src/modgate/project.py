"""Project model: config, module discovery, frontmatter, requirements, tests, bindings."""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from pathlib import Path

from ._vendor import yaml

from .hashing import normalize_text, split_frontmatter

CONFIG = "modgate.yaml"
GENERATED_SUFFIXES = (".trace.md", ".changelog.md", ".activity.md")
DEFAULT_IGNORE = {"__pycache__", "node_modules", "build", "dist", "venv", "CLAUDE.md"}  # CLAUDE.md = agent context, like .claude/
TOOL_NAMES = {"cmakelists.txt", "pyproject.toml", "package.json", "modgate.yaml", "claude.md", "skill.md"}
GENERIC_STEMS = {"readme", "changelog", "notes", "todo", "index", "docs", "history", "contributing", "doc"}
ROLES = ("overview", "brief", "req", "icd", "tests", "bind", "resource", "code")

# Which gates an AI reviewer may approve, per criticality preset (§2). Everything else needs
# the developer. `code` = REQ-level reviews ("requirement unaffected by this code change").
DEFAULT_PRESETS: dict[str, list[str]] = {
    "L0": ["overview", "brief", "req", "tests", "bind", "resource", "code"],
    "L1": ["icd", "tests", "bind", "code"],
    "L2": ["bind", "code"],
    "L3": [],
}

ID_RE = r"(?:FEAT|REQ)-[A-Z0-9]+-\d{3}"
ITEM_RE = re.compile(rf"^- \*\*({ID_RE})\*\*(.*)$")
PARENTS_RE = re.compile(r"\(parents?:\s*([^)]*)\)")
REQ_REF_RE = re.compile(r"REQ[-_]([A-Z0-9]+)[-_](\d{3})")


class ModgateError(Exception):
    """Unrecoverable problem (exit 3)."""


@dataclass
class Config:
    root: Path
    data: dict

    @property
    def criticality(self) -> str | None:
        return self.data.get("criticality") or None

    @property
    def targets(self) -> dict[str, str]:
        return {k: str(v) for k, v in (self.data.get("targets") or {}).items()}

    @property
    def presets(self) -> dict[str, list[str]]:
        merged = dict(DEFAULT_PRESETS)
        for level, spec in (self.data.get("criticality_presets") or {}).items():
            merged[str(level)] = list((spec or {}).get("ai_may_approve", []))
        return merged

    @property
    def ignore(self) -> list[str]:
        return [str(p) for p in self.data.get("ignore") or []]

    @property
    def vendor(self) -> list[str]:
        """Third-party paths (root-relative): hashed like everything else, exempt from SIZE and UNBOUND."""
        return [str(p).rstrip("/") for p in self.data.get("vendor") or []]


def is_vendored(rel: str, vendor: list[str]) -> bool:
    return any(rel == v or rel.startswith(v + "/") or fnmatch.fnmatch(rel, v) for v in vendor)


def find_root(start: Path) -> Path:
    p = start.resolve()
    if p.is_file() or not p.exists():
        p = p.parent
    for cand in (p, *p.parents):
        if (cand / CONFIG).is_file():
            return cand
    raise ModgateError(f"no {CONFIG} found above {start}")


def load_config(root: Path) -> Config:
    try:
        data = yaml.safe_load((root / CONFIG).read_text()) or {}
    except yaml.YAMLError as e:
        raise ModgateError(f"{CONFIG}: {e}") from e
    return Config(root, data)


def read_frontmatter(path: Path) -> dict:
    text = normalize_text(path.read_bytes()) or ""
    fm, _ = split_frontmatter(text)
    if fm is None:
        return {}
    try:
        data = yaml.safe_load(fm)
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def set_frontmatter(path: Path, updates: dict[str, str]) -> None:
    """Line-based update of frontmatter keys; the body is left byte-identical."""
    raw = path.read_text(encoding="utf-8")
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.split(nl)
    if lines and lines[0].rstrip() == "---" and "---" in [x.rstrip() for x in lines[1:]]:
        end = 1 + [x.rstrip() for x in lines[1:]].index("---")
        fm, rest = lines[1:end], lines[end:]
    else:
        fm, rest = [], ["---", *lines]
    for key, value in updates.items():
        line = f"{key}: {value}".rstrip()
        idx = next((i for i, x in enumerate(fm) if re.match(rf"{re.escape(key)}\s*:", x)), None)
        if idx is None:
            fm.append(line)
        else:
            fm[idx] = line
    path.write_text(nl.join(["---", *fm, *rest]), encoding="utf-8")


@dataclass
class Module:
    name: str
    path: Path
    rel: str  # relative to project root ("." for the root)
    fm: dict
    parent: Module | None = None
    children: list[Module] = field(default_factory=list)

    @property
    def kind(self) -> str:
        return str(self.fm.get("kind"))

    @property
    def deps(self) -> list[str]:
        return [str(d) for d in self.fm.get("deps") or []]

    @property
    def targets(self) -> list[str]:
        return [str(t) for t in self.fm.get("targets") or []]

    @property
    def sources(self) -> list[str]:
        return [str(s).rstrip("/") for s in self.fm.get("sources") or ["src", "include"]]

    def criticality(self, config: Config) -> str | None:
        m: Module | None = self
        while m is not None:
            if m.fm.get("criticality"):
                return str(m.fm["criticality"])
            m = m.parent
        return config.criticality

    def doc(self, suffix: str) -> Path:
        return self.path / "docs" / f"{self.name}.{suffix}"

    @property
    def overview(self) -> Path:
        return self.path / f"{self.name}.md"

    @property
    def trace_path(self) -> Path:
        return self.doc("trace.md")


def is_ignored(path: Path, root: Path, extra: list[str]) -> bool:
    name = path.name
    if name.startswith(".") or name in DEFAULT_IGNORE or name.endswith((".egg-info", ".pyc")):
        return True
    rel = path.relative_to(root).as_posix() if path != root else "."
    return any(fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(name, pat) for pat in extra)


def entries(d: Path, root: Path, extra: list[str]) -> list[Path]:
    """Visible entries of a directory; nested projects (own modgate.yaml) are opaque."""
    try:
        items = sorted(d.iterdir())
    except OSError:
        return []
    return [p for p in items if not is_ignored(p, root, extra)]


def overview_of(d: Path) -> Path | None:
    """`X/X.md` (case-insensitive) with `kind:` in its frontmatter makes X a module."""
    want = d.name.lower() + ".md"
    for p in d.iterdir():
        if p.is_file() and p.name.lower() == want and "kind" in read_frontmatter(p):
            return p
    return None


def discover(config: Config) -> dict[str, Module]:
    root = config.root
    modules: dict[str, Module] = {}

    def walk(d: Path, parent: Module | None) -> None:
        if d != root and (d / CONFIG).exists():
            return  # nested project
        current = parent
        ov = overview_of(d)
        if ov is not None:
            name = ov.stem
            rel = d.relative_to(root).as_posix() if d != root else "."
            if name in modules:
                raise ModgateError(f"duplicate module name {name}: {modules[name].rel} and {rel}")
            current = Module(name, d, rel, read_frontmatter(ov), parent)
            modules[name] = current
            if parent is not None:
                parent.children.append(current)
        for p in entries(d, root, config.ignore):
            if p.is_dir():
                walk(p, current)

    walk(root, None)
    return modules


def module_files(m: Module, config: Config) -> list[str]:
    """Relative paths of the module's own files (children, trace, changelog, activity excluded)."""
    child_dirs = {c.path for c in m.children}
    out: list[str] = []

    def walk(d: Path) -> None:
        for p in entries(d, config.root, config.ignore):
            if p.is_dir():
                if p not in child_dirs and not (p / CONFIG).exists():
                    walk(p)
            elif p.is_file() and not p.name.endswith(GENERATED_SUFFIXES):
                out.append(p.relative_to(m.path).as_posix())

    walk(m.path)
    return sorted(out)


def role_of(m: Module, rel: str) -> str | None:
    """Gate role of a controlled file, or None if the file is not a controlled doc."""
    if rel == f"{m.name}.md":
        return "overview"
    if rel == f"docs/{m.name}.bind.yaml":
        return "bind"
    if rel.startswith("docs/resources/") and rel.endswith(".md"):
        return "resource"
    if rel.startswith("docs/") and rel.count("/") == 1 and rel.endswith(".md"):
        stem = rel[5:-3]
        if stem.startswith(m.name + "."):
            return stem[len(m.name) + 1 :]
    return None


def parse_items(text: str) -> dict[str, dict]:
    """Top-level `- **ID** ...` list items with indented continuation lines."""
    norm = normalize_text(text.encode("utf-8")) or ""
    _, body = split_frontmatter(norm)
    items: dict[str, dict] = {}
    cur: list[str] | None = None
    blank = 0
    for line in body.split("\n"):
        m = ITEM_RE.match(line)
        if m:
            cur = [line]
            pm = PARENTS_RE.search(m.group(2))
            parents = [p.strip() for p in pm.group(1).split(",") if p.strip()] if pm else []
            items[m.group(1)] = {"lines": cur, "parents": parents}
            blank = 0
        elif cur is not None and line.strip() == "":
            blank += 1
        elif cur is not None and line.startswith((" ", "\t")):
            cur.extend([""] * blank + [line])
            blank = 0
        else:
            cur = None
    for item in items.values():
        item["text"] = "\n".join(item.pop("lines")) + "\n"
    return items


def load_items(path: Path) -> dict[str, dict]:
    return parse_items(path.read_text(encoding="utf-8")) if path.is_file() else {}


def requirements(m: Module) -> dict[str, dict]:
    """REQs of a module: its req doc, or any merged controlled doc in docs/ that holds them."""
    reqs = load_items(m.doc("req.md"))
    if not reqs:
        for p in sorted((m.path / "docs").glob(f"{m.name}.*.md")):
            if not p.name.endswith((".trace.md", ".changelog.md", ".activity.md")):
                reqs.update(load_items(p))
    return {k: v for k, v in reqs.items() if k.startswith("REQ-")}


def features(m: Module) -> dict[str, dict]:
    return {k: v for k, v in load_items(m.doc("brief.md")).items() if k.startswith("FEAT-")}


def load_bind(m: Module) -> dict[str, list[str]]:
    p = m.doc("bind.yaml")
    if not p.is_file():
        return {}
    try:
        data = yaml.safe_load(p.read_text()) or {}
    except yaml.YAMLError as e:
        raise ModgateError(f"{m.name}: bind.yaml: {e}") from e
    return {str(k): [str(f).rstrip("/") for f in (v or [])] for k, v in data.items()}


def expand_bound(m: Module, bound: list[str], files: list[str]) -> list[str]:
    """Bound entries may name files or directories (all files below)."""
    out: list[str] = []
    for b in bound:
        hits = [f for f in files if f == b or f.startswith(b + "/")]
        out.extend(hits or [b])
    return sorted(set(out))


PY_DEF = re.compile(r"^\s*(?:async\s+)?def\s+(test\w*)")
PY_MARK = re.compile(r"@pytest\.mark\.req\(([^)]*)\)")
CPP_TEST = re.compile(r"\bTEST(?:_F|_P)?\(\s*(\w+)\s*,\s*(\w+)\s*\)")
JS_TEST = re.compile(r"\b(?:it|test)\(\s*([\"'`])(.+?)\1")


def _refs(s: str) -> list[str]:
    return [f"REQ-{a}-{b}" for a, b in REQ_REF_RE.findall(s)]


def scan_tests(m: Module, files: list[str]) -> dict[str, list[str]]:
    """REQ -> test case names, found textually in the module's test/ (or tests/) files."""
    links: dict[str, list[str]] = {}

    def add(reqs: list[str], tc: str) -> None:
        for r in reqs:
            links.setdefault(r, [])
            if tc not in links[r]:
                links[r].append(tc)

    for rel in files:
        if not rel.startswith(("test/", "tests/")):
            continue
        try:
            text = (m.path / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        pending: list[str] = []
        for line in text.splitlines():
            if rel.endswith(".py"):
                mk = PY_MARK.search(line)
                if mk:
                    pending += _refs(mk.group(1))
                d = PY_DEF.match(line)
                if d:
                    add(pending + _refs(d.group(1)), f"{rel}::{d.group(1)}")
                    pending = []
                continue
            c = CPP_TEST.search(line)
            if c:
                add(_refs(c.group(2)), f"{c.group(1)}.{c.group(2)}")
                continue
            j = JS_TEST.search(line)
            if j:
                add(_refs(j.group(2)), j.group(2))
    return links
