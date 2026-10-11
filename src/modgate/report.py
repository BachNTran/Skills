"""`pending --report`: one static HTML page with the whole project, top to bottom."""

from __future__ import annotations

import html
from pathlib import Path

from .analyze import Finding, ModuleAnalysis, Project
from .hashing import short

CSS = """
:root{--bg:#fbfbfa;--fg:#1d1d1f;--mut:#6b6b70;--line:#e3e3e0;--ok:#1f7a4d;--warn:#a15c00;--bad:#b3261e}
@media (prefers-color-scheme:dark){:root{--bg:#161618;--fg:#ececef;--mut:#9a9aa1;--line:#2c2c30;
--ok:#5cc58f;--warn:#e7a54a;--bad:#f07c73}}
body{background:var(--bg);color:var(--fg);font:14px/1.45 -apple-system,system-ui,sans-serif;margin:0;padding:24px 16px}
main{max-width:1100px;margin:auto}h1{font-size:20px;margin:0 0 4px}h2{font-size:16px;margin:28px 0 8px}
.mut{color:var(--mut)}table{border-collapse:collapse;width:100%;margin:6px 0 14px}
td,th{border-bottom:1px solid var(--line);padding:4px 8px;text-align:left;vertical-align:top}
th{font-weight:600;color:var(--mut)}code{font:12px ui-monospace,Menlo,monospace}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px}
.verified{background:var(--ok)}.draft,.untested{background:var(--warn)}.bad{background:var(--bad)}
pre{font:12px ui-monospace,Menlo,monospace;white-space:pre-wrap;border-left:3px solid var(--line);padding-left:10px}
details{margin:4px 0}summary{cursor:pointer}
"""


def _dot(status: str) -> str:
    cls = {"verified": "verified", "draft": "draft", "approved, untested": "untested"}.get(status, "bad")
    return f'<span class="dot {cls}"></span>{html.escape(status)}'


def render(project: Project, groups: list[list[Finding]], analyses: dict[str, ModuleAnalysis]) -> str:
    e = html.escape
    cfg = project.config.data
    rows = []
    for a in sorted(analyses.values(), key=lambda a: a.module.rel):
        m = a.module
        depth = 0 if m.rel == "." else m.rel.count("/") + 1
        indent = "&nbsp;" * 4 * depth
        rows.append(
            f"<tr><td>{indent}<code>{e(m.name)}</code></td><td>{e(m.kind)}</td><td>{e(a.criticality or '–')}</td>"
            f"<td>{_dot(a.status)}</td><td><code>{short(a.module_hash)}</code></td>"
            f"<td>{e(', '.join(m.deps) or '–')}</td><td>{e(', '.join(m.targets) or '–')}</td></tr>"
        )
    pend = "\n".join(f.line() for g in groups for f in g) or "nothing open"
    mats = []
    for a in sorted(analyses.values(), key=lambda a: a.module.rel):
        m = a.module
        tr = [f"<tr><th>FEAT / parent</th><th>REQ</th><th>Test cases</th>{''.join(f'<th>{e(t)}</th>' for t in m.targets)}</tr>"]
        res = []
        for t in m.targets:
            rec = (a.state.get("tests") or {}).get(t)
            ok = rec and rec.get("module_hash") == a.module_hash
            res.append(f"<td>{'✓ ' + e(rec['result']) if ok else ('old record' if rec else '–')}</td>")
        for rid, req in sorted(a.reqs.items()):
            tcs = "<br>".join(f"<code>{e(t)}</code>" for t in a.tests.get(rid, [])) or "–"
            tr.append(f"<tr><td>{e(', '.join(req['parents']) or '–')}</td><td>{e(rid)}</td><td>{tcs}</td>{''.join(res)}</tr>")
        mats.append(
            f"<details><summary><code>{e(m.rel)}</code> · {e(m.kind)} · {_dot(a.status)} · {len(a.reqs)} REQ</summary>"
            f"<table>{''.join(tr)}</table></details>"
        )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>modgate report</title>
<style>{CSS}</style></head><body><main>
<h1>{e(str(cfg.get('project') or project.root.name))}</h1>
<div class="mut">criticality {e(str(cfg.get('criticality') or 'unset'))} · diagrams {e(str(cfg.get('diagrams') or 'unset'))}
 · coding standard {e(str(cfg.get('coding_standard') or 'unset'))} · targets {e(', '.join(project.config.targets) or 'none')}</div>
<h2>Open items</h2><pre>{e(pend)}</pre>
<h2>Modules</h2><table><tr><th>Module</th><th>Kind</th><th>Crit.</th><th>State</th><th>Hash</th><th>Deps</th><th>Targets</th></tr>
{''.join(rows)}</table>
<h2>Trace</h2>{''.join(mats)}
</main></body></html>
"""


def write(project: Project, groups: list[list[Finding]], analyses: dict[str, ModuleAnalysis]) -> Path:
    out = project.root / ".modgate" / "report.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(project, groups, analyses), encoding="utf-8")
    return out
