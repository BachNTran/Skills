"""`modgate approve`: the one human verb. Records hashes, sets status, appends the changelog."""

from __future__ import annotations

import secrets
import subprocess
from pathlib import Path

from . import trace
from .analyze import ModuleAnalysis, Project
from .hashing import short, text_hash
from .project import ModgateError, read_frontmatter, role_of, set_frontmatter

ALL_ROLES = {"overview", "brief", "req", "icd", "tests", "bind", "resource", "code"}


class Rejected(Exception):
    """Approval refused by policy (exit 2)."""


def default_approver(root: Path) -> str:
    try:
        r = subprocess.run(["git", "-C", str(root), "config", "user.name"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        r = None
    name = r.stdout.strip() if r and r.returncode == 0 else ""
    if not name:
        raise ModgateError("no approver: pass --by <name> or set git config user.name")
    return name


def resolve_doc(a: ModuleAnalysis, what: str) -> str:
    m = a.module
    controlled = [rel for rel in a.files if role_of(m, rel)]
    for rel in controlled:
        name = Path(rel).name
        if what in (rel, name, name.removeprefix(m.name + "."), name.removeprefix(m.name + ".").rsplit(".", 1)[0]):
            return rel
    if what == "overview":
        return f"{m.name}.md"
    raise ModgateError(f"{m.name}: no controlled doc or requirement named {what!r}")


def approve(project: Project, module: str, what: str, by: str | None) -> list[str]:
    m = project.modules.get(module)
    if m is None:
        raise ModgateError(f"unknown module {module!r}")
    by = by or default_approver(project.root)
    a = project.analyze(m)
    st = a.state
    crit = a.criticality or "L3"
    allowed = set(project.config.presets.get(crit, []))

    if what == "all":
        docs = [rel for rel in a.files if role_of(m, rel)]
        roles = {role_of(m, rel) for rel in docs} | {"code"}
    elif what in a.reqs or what in a.bind:
        docs, roles = [], {"code"}
    else:
        docs = [resolve_doc(a, what)]
        roles = {role_of(m, docs[0])}

    if by.startswith("ai-reviewer:") and not roles <= allowed:
        denied = ", ".join(sorted(roles - allowed))
        raise Rejected(f"E:APPROVER  {m.name}  {what}  ai-reviewer may not approve {denied} at {a.criticality or 'unset criticality'}")

    date = trace.today()
    files_state = st.setdefault("files", {})
    approvals = st.setdefault("approvals", {})
    req_appr = st.setdefault("req_approvals", {})
    sections = {r: text_hash(v["text"]) for r, v in a.reqs.items()}
    out: list[str] = []
    entries: list[str] = []

    for rel in docs:
        h = a.files[rel]
        version = 1
        if rel.endswith(".md"):
            fm = read_frontmatter(m.path / rel)
            version = int(fm.get("version") or 1)
            set_frontmatter(m.path / rel, {"status": "approved", "approved": f"{version} {short(h)}", "approved_by": by})
        approvals[rel] = {"version": version, "hash": h, "by": by, "date": date}
        files_state[rel] = h
        out.append(f"APPROVED  {m.name}  {Path(rel).name} v{version}  {short(h)}  by {by}")
        entries.append(f"- APPROVED {Path(rel).name} v{version} {short(h)} by {by}.")
        if role_of(m, rel) == "req" and what != "all":
            base = st.get("reqs") or {}
            for rid, sec in sections.items():
                prev = (req_appr.get(rid) or {}).get("section") or base.get(rid)
                if prev != sec:
                    _record_req(a, rid, sections, by, date)
            st["reqs"] = sections

    if what == "all":
        st["files"] = dict(a.files)
        st["reqs"] = sections
        st["req_approvals"] = {}
        st["deps"] = project.dep_record(a)
        st["module_hash"] = a.module_hash
        st["approved"] = {"by": by, "date": date}
        out.append(f"APPROVED  {m.name}  all  module {short(a.module_hash)}  by {by}")
        entries.append(f"- APPROVED all gates and code: module {short(a.module_hash)} by {by}.")
    elif not docs:
        if what not in a.reqs:
            raise ModgateError(f"{m.name}: {what} is bound in bind.yaml but missing from the req doc")
        _record_req(a, what, sections, by, date)
        bound = a.bind.get(what, [])
        out.append(f"REVIEWED  {m.name}  {what}  {' '.join(bound)}  by {by}")
        entries.append(f"- REVIEWED {what}: requirement unaffected; accepted {', '.join(bound) or 'no bound files'} by {by}.")
    _promote_files(a)
    if what != "all" and _matches(project, a):
        st["module_hash"] = a.module_hash

    ver = int(read_frontmatter(m.overview).get("version") or 1) if what == "all" else None
    subject = what if what == "all" or not docs else Path(docs[0]).name
    if ver is None:
        ver = approvals.get(docs[0], {}).get("version", 1) if docs else _req_doc_version(a)
    append_changelog(m.doc("changelog.md"), m.name, f"{date}-{secrets.token_hex(2)} · v{ver} · {subject} · {by}", entries)
    project.invalidate()
    project.write_trace(m, st)
    project.cache.save()
    return out


def _record_req(a: ModuleAnalysis, rid: str, sections: dict, by: str, date: str) -> None:
    a.state.setdefault("req_approvals", {})[rid] = {
        "section": sections.get(rid),
        "files": {f: a.files[f] for f in a.bind.get(rid, []) if f in a.files},
        "by": by,
        "date": date,
    }


def _promote_files(a: ModuleAnalysis) -> None:
    """A bound file becomes module-approved once every REQ binding it accepts its current hash."""
    st = a.state
    files_state = st.setdefault("files", {})
    req_appr = st.get("req_approvals") or {}
    for f, h in a.files.items():
        binders = [r for r, fs in a.bind.items() if f in fs]
        if not binders or files_state.get(f) == h:
            continue
        if all((req_appr.get(r) or {}).get("files", {}).get(f) == h for r in binders):
            files_state[f] = h


def _matches(project: Project, a: ModuleAnalysis) -> bool:
    st = a.state
    deps = st.get("deps") or {}
    same_deps = {d: (r or {}).get("module") for d, r in deps.items()} == a.dep_hashes
    return bool(st.get("module_hash")) and st.get("files") == a.files and same_deps


def _req_doc_version(a: ModuleAnalysis) -> int:
    p = a.module.doc("req.md")
    return int(read_frontmatter(p).get("version") or 1) if p.is_file() else 1


def append_changelog(path: Path, module: str, heading: str, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.is_file() else f"# {module} · changelog\n"
    if not text.endswith("\n"):
        text += "\n"
    text += "\n### " + heading + "\n" + "\n".join(lines) + "\n"
    path.write_text(text, encoding="utf-8")
