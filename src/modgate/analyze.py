"""Module analysis: states, drift, lint, pending items. Everything the LLM must not do by hand."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import trace
from .hashing import HashCache, module_hash, short, text_hash
from .project import (
    CONFIG,
    GENERIC_STEMS,
    TOOL_NAMES,
    Module,
    ModgateError,
    discover,
    is_vendored,
    entries,
    expand_bound,
    features,
    find_root,
    load_bind,
    load_config,
    module_files,
    read_frontmatter,
    requirements,
    role_of,
    scan_tests,
)

WARN_SIZE, FAIL_SIZE = 8, 12
HEADING_RE = re.compile(r"^### (\d{4}-\d{2}-\d{2}-[0-9a-f]{4}) · v\d+ · \S.* · \S.*$")
LEGACY_ID_RE = re.compile(r"^### (\S+)")
BACKLOG_RE = re.compile(r"^\s*- \[ \]\s+(.*)$")
ANY_ID_RE = re.compile(r"\b(?:FEAT|REQ|TC)-[A-Z0-9]+-\d{3}\b")
PENDING_ORDER = ["CONFIG", "DRAFT", "DRIFT", "STALE", "DEPCHANGED", "UNTESTED", "UNBOUND", "BACKLOG"]


@dataclass
class Finding:
    code: str
    module: str
    id: str = ""
    files: list[str] = field(default_factory=list)
    action: str = ""
    violation: bool = False

    @property
    def label(self) -> str:
        return ("E:" if self.violation else "") + self.code

    def line(self) -> str:
        parts = [f"{self.label:<10}", self.module]
        if self.id:
            parts.append(self.id)
        if self.files:
            parts.append(" ".join(self.files))
        text = "  ".join(parts)
        return f"{text}  → {self.action}" if self.action else text

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": "violation" if self.violation else "finding",
            "module": self.module,
            "id": self.id,
            "files": self.files,
            "action": self.action,
        }


@dataclass
class ModuleAnalysis:
    module: Module
    criticality: str | None
    files: dict[str, str]
    dep_hashes: dict[str, str]
    module_hash: str
    state: dict
    reqs: dict[str, dict]
    features: dict[str, dict]
    tests: dict[str, list[str]]
    bind: dict[str, list[str]]
    pending: list[Finding] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    status: str = "verified"


class Project:
    def __init__(self, start: Path):
        self.root = find_root(start)
        self.config = load_config(self.root)
        self.modules = discover(self.config)
        self.cache = HashCache(self.root)
        self._files: dict[str, dict[str, str]] = {}
        self._hashes: dict[str, str] = {}
        self.graph_findings: list[Finding] = []

    # ---- hashing -------------------------------------------------------------------------
    def files(self, m: Module) -> dict[str, str]:
        if m.name not in self._files:
            self._files[m.name] = {rel: self.cache.hash(m.path / rel) for rel in module_files(m, self.config)}
        return self._files[m.name]

    def invalidate(self) -> None:
        self._files.clear()
        self._hashes.clear()

    def dep_hashes(self, m: Module, stack: tuple[str, ...] = ()) -> dict[str, str]:
        out = {}
        for d in m.deps:
            if d not in self.modules:
                out[d] = "missing"
                self._note(Finding("BADDEP", m.name, d, [], f"fix deps in {m.name}.md", violation=True))
            elif d in stack or d == m.name:
                out[d] = "cycle"
                self._note(Finding("DEPCYCLE", m.name, d, [], "break the dependency cycle", violation=True))
            else:
                out[d] = self.module_hash(self.modules[d], (*stack, m.name))
        return out

    def module_hash(self, m: Module, stack: tuple[str, ...] = ()) -> str:
        if m.name not in self._hashes:
            h = module_hash(self.files(m), self.dep_hashes(m, stack))
            if stack:  # don't memoize a hash computed inside a cycle check
                return h
            self._hashes[m.name] = h
        return self._hashes[m.name]

    def _note(self, f: Finding) -> None:
        if all(f.line() != g.line() for g in self.graph_findings):
            self.graph_findings.append(f)

    def icd_hash(self, name: str) -> str | None:
        m = self.modules.get(name)
        if not m:
            return None
        return self.files(m).get(f"docs/{m.name}.icd.md")

    # ---- selection -----------------------------------------------------------------------
    def select(self, paths: list[str] | None) -> list[Module]:
        mods = sorted(self.modules.values(), key=lambda m: m.rel)
        if not paths:
            return mods
        chosen: dict[str, Module] = {}
        for raw in paths:
            p = Path(raw).resolve()
            inside = [m for m in mods if p == m.path or m.path in p.parents]
            below = [m for m in mods if p in m.path.parents]
            if inside:
                best = max(inside, key=lambda m: len(m.path.parts))
                chosen[best.name] = best
            for m in below:
                chosen[m.name] = m
            if not inside and not below and raw in self.modules:
                chosen[raw] = self.modules[raw]
        return sorted(chosen.values(), key=lambda m: m.rel)

    # ---- analysis ------------------------------------------------------------------------
    def analyze(self, m: Module) -> ModuleAnalysis:
        files = self.files(m)
        a = ModuleAnalysis(
            module=m,
            criticality=m.criticality(self.config),
            files=files,
            dep_hashes=self.dep_hashes(m),
            module_hash=self.module_hash(m),
            state=trace.load_state(m.trace_path),
            reqs=requirements(m),
            features=features(m),
            tests=scan_tests(m, list(files)),
            bind={r: expand_bound(m, fs, list(files)) for r, fs in load_bind(m).items()},
        )
        self._check(a)
        return a

    def gate_owner(self, a: ModuleAnalysis, role: str) -> str:
        crit = a.criticality or "L3"
        ai = role in self.config.presets.get(crit, [])
        return f"({'developer or ai-reviewer' if ai else 'developer'}, {a.criticality or 'criticality unset'})"

    def _check(self, a: ModuleAnalysis) -> None:
        m, st, files = a.module, a.state, a.files
        base_files: dict = st.get("files") or {}
        base_reqs: dict = st.get("reqs") or {}
        req_appr: dict = st.get("req_approvals") or {}
        approvals: dict = st.get("approvals") or {}
        approved_once = bool(st.get("module_hash"))
        explained: set[str] = set()
        drafts: list[Finding] = []

        # controlled docs: draft / edited-while-approved
        for rel, h in files.items():
            role = role_of(m, rel)
            if role is None:
                continue
            if role == "bind":
                if (approvals.get(rel) or {}).get("hash") != h:
                    drafts.append(Finding("DRAFT", m.name, Path(rel).name, [], "approve " + self.gate_owner(a, role)))
                    explained.add(rel)
                continue
            fm = read_frontmatter(m.path / rel)
            if str(fm.get("status", "draft")) != "approved":
                ident = f"{Path(rel).name} v{fm.get('version', 1)}"
                drafts.append(Finding("DRAFT", m.name, ident, [], "approve " + self.gate_owner(a, role)))
                explained.add(rel)
            elif short(h) not in str(fm.get("approved") or ""):
                a.findings.append(
                    Finding("REDRAFT", m.name, Path(rel).name, [], "approved doc changed: status draft, version +1, changelog entry")
                )

        # requirements: section changes and drift
        sections = {r: text_hash(v["text"]) for r, v in a.reqs.items()}
        drift: dict[str, list[str]] = {}
        for rid, bound in a.bind.items():
            rec = req_appr.get(rid) or {}
            base_section = rec.get("section") or base_reqs.get(rid)
            if base_section is None or sections.get(rid) != base_section:
                explained.update(bound)  # requirement revisited (or new): the req gate covers it
                continue
            changed = [f for f in bound if files.get(f) != (rec.get("files") or {}).get(f, base_files.get(f))]
            if changed and (approved_once or rec):
                drift[rid] = changed
                explained.update(changed)
        for rid, changed in sorted(drift.items()):
            f = Finding("DRIFT", m.name, rid, changed, f"revisit {rid} + its TCs, or approve {m.name} {rid}")
            a.findings.append(f)
            a.pending.append(f)

        # binding hygiene
        bound_all = {f for fs in a.bind.values() for f in fs}
        for rid, fs in sorted(a.bind.items()):
            missing = [f for f in fs if f not in files]
            if missing:
                a.findings.append(Finding("BADBIND", m.name, rid, missing, f"fix {m.name}.bind.yaml (file not found)"))
            if a.reqs and rid not in a.reqs:
                a.findings.append(Finding("BADBIND", m.name, rid, [], f"{rid} not in {m.name}.req.md: fix bind.yaml"))
        srcs = m.sources
        unbound = [
            f
            for f in files
            if any(f == s or f.startswith(s + "/") for s in srcs)
            and f not in bound_all
            and not is_vendored(_root_rel(m, f), self.config.vendor)
        ]
        if unbound:
            f = Finding("UNBOUND", m.name, "", unbound, f"bind to a REQ in {m.name}.bind.yaml")
            a.findings.append(f)
            a.pending.append(f)

        # changed files nobody explained
        changed = sorted(f for f in set(files) | set(base_files) if files.get(f) != base_files.get(f))
        rest = [f for f in changed if f not in explained]
        stale = False
        if rest and approved_once:
            stale = True
            a.pending.append(Finding("STALE", m.name, "", rest, f"deep review, then approve {m.name} all"))
        elif rest:
            drafts.append(Finding("DRAFT", m.name, "code", rest, f"approve {m.name} all " + self.gate_owner(a, "code")))

        # dependencies
        depchanged = False
        rec_deps: dict = st.get("deps") or {}
        if approved_once:
            for d, h in a.dep_hashes.items():
                rec = rec_deps.get(d)
                if rec and rec.get("module") == h:
                    continue
                depchanged = True
                if rec and rec.get("icd") == self.icd_hash(d):
                    act = (
                        f"ICD unchanged: sync {m.rel} --test {m.targets[0]}" if m.targets else f"ICD unchanged: approve {m.name} all"
                    )
                else:
                    act = f"deep review ({d} ICD changed), then approve {m.name} all"
                a.pending.append(Finding("DEPCHANGED", m.name, d, [], act))
            for d in set(rec_deps) - set(a.dep_hashes):
                depchanged = True
                a.pending.append(Finding("DEPCHANGED", m.name, d, [], f"dependency removed: approve {m.name} all"))

        # tests
        untested = []
        for t in m.targets:
            if t not in self.config.targets:
                a.findings.append(Finding("CONFIG", m.name, t, [], f"add target {t} to {CONFIG}"))
            rec = (st.get("tests") or {}).get(t)
            if not rec or rec.get("module_hash") != a.module_hash:
                untested.append(Finding("UNTESTED", m.name, t, [], f"sync {m.rel} --test {t}"))
        a.pending.extend(untested)
        a.pending[:0] = drafts

        # backlog
        act = m.doc("activity.md")
        if act.is_file():
            for line in act.read_text(encoding="utf-8").splitlines():
                b = BACKLOG_RE.match(line)
                if b:
                    ids = ANY_ID_RE.findall(b.group(1))
                    text = b.group(1).strip()
                    if ids and text.startswith(ids[0]):
                        text = text[len(ids[0]) :].lstrip(" ·-:")
                    a.pending.append(Finding("BACKLOG", m.name, ids[0] if ids else "", [], text))

        # approver vs criticality
        allowed = self.config.presets.get(a.criticality or "L3", [])
        for rel, rec in approvals.items():
            role = role_of(m, rel) or "code"
            if str(rec.get("by", "")).startswith("ai-reviewer:") and role not in allowed:
                a.findings.append(
                    Finding("APPROVER", m.name, Path(rel).name, [], f"ai-reviewer at {a.criticality}: developer must approve", True)
                )
        for rid, rec in req_appr.items():
            if str(rec.get("by", "")).startswith("ai-reviewer:") and "code" not in allowed:
                a.findings.append(
                    Finding("APPROVER", m.name, rid, [], f"ai-reviewer at {a.criticality}: developer must approve", True)
                )
        if str((st.get("approved") or {}).get("by", "")).startswith("ai-reviewer:"):
            if not set(("overview", "brief", "req", "icd", "tests", "bind", "code")) <= set(allowed):
                a.findings.append(
                    Finding("APPROVER", m.name, "all", [], f"ai-reviewer at {a.criticality}: developer must approve", True)
                )

        a.pending.sort(key=lambda f: PENDING_ORDER.index(f.code))
        a.status = (
            "draft" if drafts
            else "unreviewed change" if drift
            else "stale" if stale or (approved_once and not depchanged and a.module_hash != st.get("module_hash"))
            else "dependency changed" if depchanged
            else "approved, untested" if untested
            else "verified"
        )

    # ---- project-level lint --------------------------------------------------------------
    def config_findings(self) -> list[Finding]:
        missing = [k for k in ("criticality", "diagrams", "coding_standard") if not self.config.data.get(k)]
        if not missing:
            return []
        name = str(self.config.data.get("project") or self.root.name)
        return [Finding("CONFIG", name, " ".join(missing), [], f"ask the developer once, save in {CONFIG}")]

    def lint_dirs(self, dirs: list[Path]) -> list[Finding]:
        out: list[Finding] = []
        for d in dirs:
            items = [p for p in entries(d, self.root, self.config.ignore) if p.name != CONFIG]
            n = len(items)
            rel = d.relative_to(self.root).as_posix() if d != self.root else "."
            if is_vendored(rel, self.config.vendor):
                continue  # third-party layout is not ours to split
            owner = self._owner(d)
            if n > WARN_SIZE:
                out.append(
                    Finding("SIZE", owner, rel + "/", [], f"{n} entries (> {WARN_SIZE}): split into child modules", n > FAIL_SIZE)
                )
            for p in items:
                if p.is_file() and p.name.lower() not in TOOL_NAMES and p.name.split(".")[0].lower() in GENERIC_STEMS:
                    out.append(
                        Finding("NAMING", owner, p.relative_to(self.root).as_posix(), [], "use a module-prefixed name", True)
                    )
        return out

    def _owner(self, d: Path) -> str:
        best = None
        for m in self.modules.values():
            if d == m.path or m.path in d.parents:
                if best is None or len(m.path.parts) > len(best.path.parts):
                    best = m
        return best.name if best else "-"

    def module_dirs(self, m: Module) -> list[Path]:
        dirs = {m.path}
        for rel in self.files(m):
            p = m.path / rel
            while p.parent != m.path and m.path in p.parents:
                p = p.parent
                dirs.add(p)
        return sorted(dirs)

    def all_dirs(self) -> list[Path]:
        out: list[Path] = []

        def walk(d: Path) -> None:
            out.append(d)
            for p in entries(d, self.root, self.config.ignore):
                if p.is_dir() and not (p / CONFIG).exists():
                    walk(p)

        walk(self.root)
        return out

    def lint_module_docs(self, m: Module) -> list[Finding]:
        out: list[Finding] = []
        docs = m.path / "docs"
        if docs.is_dir():
            for p in sorted(docs.glob("*.md")):
                if not p.name.startswith(m.name + ".") and p.name.split(".")[0].lower() not in GENERIC_STEMS:
                    out.append(Finding("NAMING", m.name, f"docs/{p.name}", [], f"prefix with {m.name}."))
        log = m.doc("changelog.md")
        if log.is_file():
            out += self.lint_changelog(m, log)
        return out

    def lint_changelog(self, m: Module, log: Path) -> list[Finding]:
        out: list[Finding] = []
        text = log.read_text(encoding="utf-8")
        seen: set[str] = set()
        for line in text.splitlines():
            if not line.startswith("### "):
                continue
            h = HEADING_RE.match(line)
            ident = h.group(1) if h else LEGACY_ID_RE.match(line).group(1)
            if not h:
                out.append(Finding("CHANGELOG", m.name, ident, [], "heading: ### YYYY-MM-DD-xxxx · vN · <doc> · <author>"))
            if ident in seen:
                out.append(Finding("CHANGELOG", m.name, ident, [], "duplicate entry id"))
            seen.add(ident)
        head = git_head_text(log)
        if head is not None:
            norm = lambda s: "\n".join(x.rstrip() for x in s.replace("\r\n", "\n").split("\n")).rstrip("\n")  # noqa: E731
            if not norm(text).startswith(norm(head)):
                out.append(
                    Finding("APPEND", m.name, log.name, [], "changelog is append-only: restore HEAD entries, add new ones", True)
                )
        return out

    def drawio(self, m: Module) -> list[Finding]:
        out: list[Finding] = []
        ddir = m.path / "docs" / "diagrams"
        if not ddir.is_dir():
            return out
        exe = shutil.which("drawio") or shutil.which("draw.io")
        for src in sorted(ddir.glob("*.drawio")):
            svg = src.with_suffix(".svg")
            if svg.exists() and svg.stat().st_mtime >= src.stat().st_mtime:
                continue
            if not exe:
                out.append(Finding("DRAWIO", m.name, src.name, [], "drawio CLI not found: install it or export the SVG by hand"))
                continue
            r = subprocess.run([exe, "-x", "-f", "svg", "-o", str(svg), str(src)], capture_output=True, text=True)
            if r.returncode != 0:
                out.append(Finding("DRAWIO", m.name, src.name, [], f"export failed (exit {r.returncode})"))
        return out

    # ---- verbs ---------------------------------------------------------------------------
    def run_tests(self, mods: list[Module], target: str) -> list[Finding]:
        cmd = self.config.targets.get(target)
        if cmd is None:
            raise ModgateError(f"target {target!r} not defined in {CONFIG} targets")
        out: list[Finding] = []
        ran = 0
        for m in mods:
            if target not in m.targets:
                continue
            ran += 1
            full = cmd.replace("{root}", str(self.root)).replace("{module}", m.name).replace("{python}", sys.executable)
            log = self.root / ".modgate" / "logs" / f"{m.name}.{target}.log"
            before = self.module_hash(m)
            ok, result = trace.run_target(full, m.path, log)
            self.invalidate()
            if not ok:
                rel_log = log.relative_to(self.root).as_posix()
                out.append(Finding("TESTFAIL", m.name, target, [], f"{result}; output in {rel_log}"))
                continue
            a = self.analyze(m)
            if a.module_hash != before:
                out.append(Finding("TESTFAIL", m.name, target, [], "module files changed during the run: re-run"))
                continue
            state = a.state
            state.setdefault("tests", {})[target] = {
                "module_hash": a.module_hash,
                "result": result,
                "date": trace.today(),
                "env": trace.environment(),
                "deps": {d: short(h) for d, h in a.dep_hashes.items()},
            }
            self._rebase_deps(a)
            self.write_trace(m, state)
        if ran == 0:
            out.append(Finding("CONFIG", "-", target, [], "no module in scope lists this target in its overview targets:"))
        return out

    def _rebase_deps(self, a: ModuleAnalysis) -> None:
        """Deps changed but their ICDs didn't, own files unchanged: a passing test re-baselines (§4)."""
        st = a.state
        if a.status != "dependency changed" or not st.get("module_hash"):
            return
        if any(f.code in ("STALE", "DRIFT", "DRAFT") for f in a.pending):
            return
        rec = st.get("deps") or {}
        if any((rec.get(d) or {}).get("icd") != self.icd_hash(d) for d in a.dep_hashes):
            return
        st["deps"] = self.dep_record(a)
        st["module_hash"] = a.module_hash

    def dep_record(self, a: ModuleAnalysis) -> dict:
        return {d: {"module": h, "icd": self.icd_hash(d)} for d, h in a.dep_hashes.items()}

    def write_trace(self, m: Module, state: dict | None = None) -> ModuleAnalysis:
        a = self.analyze(m)
        if state is not None:
            a.state = state
            self._recheck(a)
        trace.write_if_changed(m.trace_path, trace.render(a))
        return a

    def _recheck(self, a: ModuleAnalysis) -> None:
        a.pending.clear()
        a.findings.clear()
        self._check(a)

    def sync(self, paths: list[str] | None, test: str | None = None) -> list[Finding]:
        mods = self.select(paths)
        findings: list[Finding] = self.config_findings()
        for m in mods:
            findings += self.drawio(m)
        if test:
            findings += self.run_tests(mods, test)
        for m in mods:
            a = self.write_trace(m)
            findings += a.findings
            findings += self.lint_module_docs(m)
        dirs = self.all_dirs() if not paths else sorted({d for m in mods for d in self.module_dirs(m)})
        findings += self.lint_dirs(dirs)
        findings += self.graph_findings
        self.cache.save()
        return dedupe(findings)

    def pending(self) -> tuple[list[list[Finding]], dict[str, ModuleAnalysis]]:
        analyses = {m.name: self.analyze(m) for m in self.select(None)}
        items = {n: a.pending for n, a in analyses.items() if a.pending}
        self.cache.save()
        groups = components(self.modules, analyses)
        out = []
        cfg = self.config_findings()
        if cfg:
            out.append(cfg)
        for g in groups:
            fs = [f for n in g for f in items.get(n, [])]
            if fs:
                out.append(fs)
        return out, analyses


def components(modules: dict[str, Module], analyses: dict[str, ModuleAnalysis]) -> list[list[str]]:
    """Dependency-disjoint module sets (undirected dependency graph), in module path order."""
    parent = {n: n for n in modules}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for m in modules.values():
        for d in m.deps:
            if d in parent:
                parent[find(m.name)] = find(d)
    order = [m.name for m in sorted(modules.values(), key=lambda m: m.rel)]
    groups: dict[str, list[str]] = {}
    for n in order:
        groups.setdefault(find(n), []).append(n)
    return list(groups.values())


def dedupe(fs: list[Finding]) -> list[Finding]:
    seen, out = set(), []
    for f in fs:
        if f.line() not in seen:
            seen.add(f.line())
            out.append(f)
    return out


def git_head_text(path: Path) -> str | None:
    try:
        r = subprocess.run(
            ["git", "-C", str(path.parent), "show", f"HEAD:./{path.name}"], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout if r.returncode == 0 else None


def _root_rel(m, f: str) -> str:
    """A module-relative file path, relative to the project root instead."""
    return f if m.rel in (".", "") else f"{m.rel}/{f}"
