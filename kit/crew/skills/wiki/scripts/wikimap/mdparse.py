"""Markdown, YAML-subset and Mermaid flowchart parsing for the wiki map (stdlib only, never executes repo text).

Line numbers are 1-based file lines. `parse_flowchart(src, line0)` numbers src line i (0-based) as `line0 + 1 + i`,
so passing the fence line from `mermaid_blocks` gives file lines.
"""
from __future__ import annotations

import html
import re

__all__ = [
    "yaml_lite", "frontmatter", "headings", "code_fences", "mermaid_blocks", "parse_flowchart", "pick_diagram",
    "label_candidates", "label_head", "norm", "bind_yaml", "req_lines", "trace_state", "first_heading", "summary",
    "doc_title",
]

# ---------- YAML subset (frontmatter, modgate.yaml, bind.yaml) ----------

_INT_RE = re.compile(r"-?\d+$")


def _strip_comment(s: str) -> str:
    """Drop a trailing `# comment` that is outside quotes and preceded by whitespace (or starts the line)."""
    q = None
    for i, ch in enumerate(s):
        if q:
            if ch == q:
                q = None
        elif ch in "'\"" and (i == 0 or s[i - 1] in " \t[,:"):
            q = ch
        elif ch == "#" and (i == 0 or s[i - 1] in " \t"):
            return s[:i].rstrip()
    return s.rstrip()


def _scalar(v: str):
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        return v[1:-1]
    if v in ("", "~", "null", "Null", "NULL"):
        return None if v else ""
    if v in ("true", "True", "TRUE"):
        return True
    if v in ("false", "False", "FALSE"):
        return False
    if _INT_RE.match(v):
        try:
            return int(v)
        except ValueError:
            return v
    return v


def _flow_list(v: str) -> list:
    inner = v.strip()[1:-1]
    out, cur, q = [], "", None
    for ch in inner:
        if q:
            cur += ch
            if ch == q:
                q = None
        elif ch in "'\"":
            q = ch
            cur += ch
        elif ch == ",":
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return [_scalar(x) for x in out if x.strip()]


def _value(v: str):
    v = v.strip()
    if v.startswith("[") and v.endswith("]"):
        return _flow_list(v)
    if v == "{}":
        return {}
    return _scalar(v)


def yaml_lite(text: str) -> dict:
    """Parse the YAML subset modgate files use: nested mappings by indent, block and flow lists, scalars.

    Never raises; unknown constructs are skipped. Returns {} for anything that is not a mapping.
    """
    lines = []
    for raw in (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw.strip() in ("---", "...") and not raw.startswith((" ", "\t")):
            continue
        s = _strip_comment(raw.replace("\t", "  "))
        if s.strip():
            lines.append((len(s) - len(s.lstrip(" ")), s.strip()))

    def block(i: int, ind: int):
        """Parse lines[i:] at indent `ind`; returns (value, next index)."""
        if i < len(lines) and lines[i][1].startswith("- ") or (i < len(lines) and lines[i][1] == "-"):
            out: list = []
            while i < len(lines) and lines[i][0] == ind and (lines[i][1].startswith("- ") or lines[i][1] == "-"):
                item = lines[i][1][1:].strip()
                i += 1
                if not item:
                    if i < len(lines) and lines[i][0] > ind:
                        v, i = block(i, lines[i][0])
                        out.append(v)
                    else:
                        out.append(None)
                    continue
                k, sep, rest = item.partition(": ")
                if (sep or item.endswith(":")) and not item.startswith(("'", '"', "[")) and " " not in k.strip():
                    d: dict = {}
                    if item.endswith(":") and not sep:
                        d[item[:-1].strip()] = None
                    else:
                        d[k.strip()] = _value(rest)
                    if i < len(lines) and lines[i][0] > ind:
                        more, i = block(i, lines[i][0])
                        if isinstance(more, dict):
                            d.update(more)
                    out.append(d)
                else:
                    out.append(_value(item))
            return out, i
        out_d: dict = {}
        while i < len(lines) and lines[i][0] == ind:
            s = lines[i][1]
            m = re.match(r"""("[^"]*"|'[^']*'|[^:]+?)\s*:(?:\s+(.*)|$)""", s)
            i += 1
            if not m:
                continue
            key = str(_scalar(m.group(1)))
            rest = (m.group(2) or "").strip()
            if rest and rest not in ("|", ">", "|-", ">-"):
                out_d[key] = _value(rest)
            elif i < len(lines) and (lines[i][0] > ind or (lines[i][0] == ind and lines[i][1].startswith("-"))):
                v, i = block(i, lines[i][0])
                out_d[key] = v
            else:
                out_d[key] = None
        while i < len(lines) and lines[i][0] > ind:  # stray deeper lines
            i += 1
        return out_d, i

    try:
        val, i = block(0, lines[0][0]) if lines else ({}, 0)
        while isinstance(val, dict) and i < len(lines):  # dedented trailing keys
            more, i = block(i, lines[i][0])
            if isinstance(more, dict):
                for k, v in more.items():
                    val.setdefault(k, v)
            else:
                break
    except (RecursionError, IndexError):
        return {}
    return val if isinstance(val, dict) else {}


# ---------- Markdown structure ----------

_FM_RE = re.compile("\\A\\ufeff?---[ \\t]*\\r?\\n(?:(.*?)\\r?\\n)?---[ \\t]*(?:\\r?\\n|\\Z)", re.S)
_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})([^`]*)$")  # info string; lang = its first word
# linear: the optional closing `#` sequence is stripped in code (a lazy `.+?` before it is quadratic)
_HEAD_RE = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.*)$")


def _heading(line: str) -> tuple[int, str] | None:
    """ATX heading → (level, text without the closing `#` sequence), else None."""
    m = _HEAD_RE.match(line)
    if not m:
        return None
    t = m.group(2).rstrip(" \t")
    u = t.rstrip("#")
    if u != t and (not u or u[-1] in " \t"):
        t = u.rstrip(" \t")
    return (len(m.group(1)), t) if t else None


def frontmatter(text: str) -> tuple[dict, int]:
    """(frontmatter mapping, 1-based line where the body starts). No frontmatter → ({}, 1)."""
    m = _FM_RE.match(text or "")
    if not m:
        return {}, 1
    return yaml_lite(m.group(1) or ""), text[: m.end()].count("\n") + 1


def _lines(text: str) -> list[str]:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")


def _walk(text: str):
    """Yield (line_no, line, in_fence) for body lines (frontmatter skipped)."""
    _, start = frontmatter(text)
    fence = None
    for n, line in enumerate(_lines(text), 1):
        if n < start:
            continue
        if fence:
            if re.match(rf"^ {{0,3}}{re.escape(fence[0])}{{{len(fence)},}}[ \t]*$", line):
                fence = None
            yield n, line, True
            continue
        m = _FENCE_OPEN.match(line)
        if m:
            fence = m.group(1)
            yield n, line, True
            continue
        yield n, line, False


def headings(text: str) -> list[tuple[int, str, int]]:
    """ATX headings outside fences: [(level, text, line)]."""
    out = []
    for n, line, fenced in _walk(text):
        if fenced:
            continue
        h = _heading(line)
        if h:
            out.append((h[0], h[1].strip(), n))
    return out


def code_fences(text: str) -> list[dict]:
    """Fenced code blocks: [{"lang","body","line" (opening fence line),"heading" (nearest heading above or "")}]."""
    out: list[dict] = []
    heading = ""
    fence = None
    cur: dict | None = None
    _, start = frontmatter(text)
    for n, line in enumerate(_lines(text), 1):
        if n < start:
            continue
        if fence:
            if re.match(rf"^ {{0,3}}{re.escape(fence[0])}{{{len(fence)},}}[ \t]*$", line):
                cur["body"] = "\n".join(cur.pop("_b"))
                out.append(cur)
                fence, cur = None, None
            else:
                cur["_b"].append(line)
            continue
        m = _FENCE_OPEN.match(line)
        if m:
            fence = m.group(1)
            cur = {"lang": (m.group(2).split() or [""])[0].lower(), "line": n, "heading": heading, "_b": []}
            continue
        h = _heading(line)
        if h:
            heading = h[1].strip()
    if cur is not None:  # unterminated fence runs to EOF
        body = cur.pop("_b")
        while body and not body[-1].strip():
            body.pop()
        cur["body"] = "\n".join(body)
        out.append(cur)
    return [{"lang": c["lang"], "body": c["body"], "line": c["line"], "heading": c["heading"]} for c in out]


def mermaid_blocks(text: str) -> list[dict]:
    """[{"line" (fence line),"heading","src"}] for every ```mermaid fence."""
    return [{"line": f["line"], "heading": f["heading"], "src": f["body"]} for f in code_fences(text) if f["lang"] == "mermaid"]


_DIAG_HEAD = re.compile(r"interaction|subsystem|architecture|overview", re.I)
_FLOW_HDR = re.compile(r"^(flowchart|graph)\b(?:\s+(\w+))?", re.I)


def _first_stmt(src: str) -> str:
    in_cfg = False
    for i, line in enumerate(_lines(src)):
        s = line.strip()
        if not s or s.startswith("%%"):
            continue
        if s == "---":
            in_cfg = not in_cfg
            continue
        if in_cfg:
            continue
        return s
    return ""


def pick_diagram(text: str) -> tuple[dict | None, int]:
    """The container's interaction flowchart: the first flowchart/graph fence under an
    interaction/subsystem/architecture/overview heading, else the first such fence. → (parse result | None, fence line)."""
    flows = [b for b in mermaid_blocks(text) if _FLOW_HDR.match(_first_stmt(b["src"]))]
    if not flows:
        return None, 0
    pick = next((b for b in flows if _DIAG_HEAD.search(b["heading"] or "")), flows[0])
    return parse_flowchart(pick["src"], pick["line"]), pick["line"]


# ---------- Mermaid flowchart ----------

_ID_RE = re.compile(r"[A-Za-z0-9_]+(?:-[A-Za-z0-9_]+)*")
_SHAPES = [("(((", (")))",)), ("([", ("])",)), ("[[", ("]]",)), ("[(", (")]",)), ("[/", ("/]", "\\]")),
           ("[\\", ("\\]", "/]")), ("((", ("))",)), ("{{", ("}}",)), ("(", (")",)), ("[", ("]",)), ("{", ("}",)),
           (">", ("]",))]
_LINKS = [
    re.compile(r"(<?)(-{2,}>|={2,}>|-\.+->|-{3,}|={3,}|-\.+-)(?=[^-=.>]|$)\s*(?:\|([^|]*)\|)?"),
    re.compile(r"(<?)--\s*(\"[^\"]*\"|[^\"|]*?)\s*(-{2,}>|-{3,})"),
    re.compile(r"(<?)-\.\s*(\"[^\"]*\"|[^\"|]*?)\s*(\.-+>|\.-+)(?=[^-.>]|$)"),
    re.compile(r"(<?)==\s*(\"[^\"]*\"|[^\"|]*?)\s*(={2,}>|={3,})"),
]
_IGNORE_STMT = re.compile(r"^(classDef|style|linkStyle|click|direction|accTitle|accDescr|%%)\b")
_CLASS_STMT = re.compile(r"^class\s+([\w\-]+(?:\s*,\s*[\w\-]+)*)\s+([\w\-]+)\s*$")
_KEYWORDS = {"end", "subgraph", "graph", "flowchart", "class", "classDef", "style", "linkStyle", "click", "direction"}


def _clean(label: str, join: str = "\n") -> str:
    s = re.sub(r"<br\s*/?>", "\n", label or "", flags=re.I)
    s = re.sub(r"#(\d+);", r"&#\1;", s)
    s = re.sub(r"#([A-Za-z]+);", r"&\1;", s)
    s = re.sub(r"<[^>]*>", "", s)
    s = html.unescape(s)
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] == "`":  # markdown string
        s = s[1:-1]
    parts = [" ".join(p.split()) for p in s.split("\n")]
    return join.join(p for p in parts if p)


def _split_stmts(line: str) -> list[str]:
    """Split on `;` outside quotes and brackets."""
    out, cur, q, depth = [], "", None, 0
    for ch in line:
        if q:
            cur += ch
            if ch == q:
                q = None
            continue
        if ch == '"':
            q = ch
        elif ch in "[({":
            depth += 1
        elif ch in "])}":
            depth = max(0, depth - 1)
        elif ch == ";" and depth == 0:
            out.append(cur)
            cur = ""
            continue
        cur += ch
    out.append(cur)
    return [s.strip() for s in out if s.strip()]


def _parse_node(s: str, i: int):
    """→ ((id, label|None, ext), next index) or (None, i)."""
    while i < len(s) and s[i] in " \t":
        i += 1
    m = _ID_RE.match(s, i)
    if not m:
        return None, i
    nid, j = m.group(), m.end()
    label = None
    for op, closers in _SHAPES:
        if not s.startswith(op, j):
            continue
        k = j + len(op)
        while k < len(s) and s[k] in " \t":
            k += 1
        if k < len(s) and s[k] == '"':
            q = s.find('"', k + 1)
            if q < 0:
                return None, i
            label = s[k + 1:q]
            k = q + 1
            ends = [(s.find(c, k), c) for c in closers if s.find(c, k) >= 0]
            if not ends:
                return None, i
            e, c = min(ends)
            j = e + len(c)
        else:
            ends = [(s.find(c, k), c) for c in closers if s.find(c, k) >= 0]
            if not ends:
                return None, i
            e, c = min(ends)
            label = s[k:e]
            j = e + len(c)
        break
    ext = False
    cm = re.compile(r":::([\w\-]+)").match(s, j)
    if cm:
        ext = cm.group(1) == "ext"
        j = cm.end()
    return (nid, label, ext), j


def _parse_group(s: str, i: int):
    nodes = []
    while True:
        n, j = _parse_node(s, i)
        if n is None:
            return (nodes or None), i
        nodes.append(n)
        k = j
        while k < len(s) and s[k] in " \t":
            k += 1
        if k < len(s) and s[k] == "&":
            i = k + 1
            continue
        return nodes, j


def _parse_link(s: str, i: int):
    while i < len(s) and s[i] in " \t":
        i += 1
    for n, rx in enumerate(_LINKS):
        m = rx.match(s, i)
        if not m:
            continue
        if n == 0:
            arrow, label = m.group(2), m.group(3)
        else:
            arrow, label = m.group(3), m.group(2)
        label = (label or "").strip()
        if len(label) >= 2 and label[0] == label[-1] == '"':
            label = label[1:-1]
        return {"label": _clean(label, " "), "dash": "." in arrow, "thick": "=" in arrow}, m.end()
    return None, i


MAX_STMT = 4096   # characters per Mermaid line
MAX_FAN = 16      # nodes per `&` group: at most 256 edges per link step
MAX_EDGES = 2000  # edges per diagram
MAX_NODES = 500   # nodes per diagram


def parse_flowchart(src: str, line0: int = 0) -> dict:
    """Parse a Mermaid flowchart.

    → {"dir","nodes":{id:{"label","ext","line"}},"subgraphs":{id:{"label","members","line"}},
       "edges":[{"s","t","label","dash","thick","line"}],"skipped":int}
    Node labels are HTML-unescaped with tags stripped; `<br>` becomes a newline.
    """
    nodes: dict[str, dict] = {}
    subs: dict[str, dict] = {}
    edges: list[dict] = []
    ext_ids: set[str] = set()
    stack: list[str] = []
    skipped = 0
    seen_header = False
    direction = None
    in_cfg = False

    def touch(nid: str, label, ext: bool, ln: int) -> None:
        nonlocal skipped
        n = nodes.get(nid)
        if n is None:
            if len(nodes) >= MAX_NODES:
                skipped += 1
                return
            n = nodes[nid] = {"label": None, "ext": False, "line": ln}
        if label is not None and n["label"] is None:
            n["label"] = _clean(label)
            n["line"] = ln
        if ext:
            ext_ids.add(nid)
        if stack and nid not in subs[stack[-1]]["members"]:
            subs[stack[-1]]["members"].append(nid)

    for idx, raw in enumerate(_lines(src)):
        ln = line0 + 1 + idx
        line = raw.strip()
        if not line or line.startswith("%%"):
            continue
        if len(line) > MAX_STMT:  # repo text is untrusted: a huge statement is skipped, not parsed
            skipped += 1
            continue
        if not seen_header:
            if line == "---":
                in_cfg = not in_cfg
                continue
            if in_cfg:
                continue
            m = _FLOW_HDR.match(line)
            if m:
                seen_header = True
                direction = (m.group(2) or "TB").upper()
                rest = line[m.end():].strip().lstrip(";").strip()
                if not rest:
                    continue
                line = rest
            else:
                seen_header = True  # tolerate a missing header
        for st in _split_stmts(line):
            if st.startswith("%%"):
                break
            if st == "end":
                if stack:
                    stack.pop()
                else:
                    skipped += 1
                continue
            if st.startswith("subgraph"):
                rest = st[len("subgraph"):].strip()
                m = re.match(r"^([\w\-]+)\s*\[\s*(\"?)(.*?)\2\s*\]\s*$", rest)
                if m:
                    sid, slabel = m.group(1), m.group(3)
                elif re.match(r"^[\w\-]+$", rest):
                    sid, slabel = rest, rest
                elif rest:
                    sid = slabel = rest.strip('"')
                else:
                    skipped += 1
                    continue
                if stack and sid not in subs[stack[-1]]["members"]:
                    subs[stack[-1]]["members"].append(sid)
                if sid not in subs:
                    subs[sid] = {"label": _clean(slabel), "members": [], "line": ln}
                stack.append(sid)
                continue
            cm = _CLASS_STMT.match(st)
            if cm:
                if cm.group(2) == "ext":
                    ext_ids.update(x.strip() for x in cm.group(1).split(","))
                continue
            if _IGNORE_STMT.match(st):
                continue
            g, i = _parse_group(st, 0)
            if not g or g[0][0] in _KEYWORDS:
                skipped += 1
                continue
            groups, links, ok = [g], [], True
            while True:
                while i < len(st) and st[i] in " \t":
                    i += 1
                if i >= len(st):
                    break
                lk, i2 = _parse_link(st, i)
                if lk is None:
                    ok = False
                    break
                g2, i3 = _parse_group(st, i2)
                if not g2:
                    ok = False
                    break
                links.append(lk)
                groups.append(g2)
                i = i3
            if not ok:
                skipped += 1
                continue
            for grp in groups:
                for nid, label, ext in grp:
                    touch(nid, label, ext, ln)
            for k, lk in enumerate(links):
                pairs = [(a, b) for a in groups[k][:MAX_FAN] for b in groups[k + 1][:MAX_FAN]]
                if len(pairs) < len(groups[k]) * len(groups[k + 1]):
                    skipped += 1  # `A & B & … --> …` fan-out capped
                for a, b in pairs:
                    if len(edges) >= MAX_EDGES:
                        skipped += 1
                        break
                    edges.append({"s": a[0], "t": b[0], "label": lk["label"], "dash": lk["dash"],
                                  "thick": lk["thick"], "line": ln})
    for sid in subs:
        nodes.pop(sid, None)
    for nid, n in nodes.items():
        if n["label"] is None:
            n["label"] = nid
        n["ext"] = nid in ext_ids
    for sid, sg in subs.items():
        sg["ext"] = sid in ext_ids
    return {"dir": direction, "nodes": nodes, "subgraphs": subs, "edges": edges, "skipped": skipped}


# ---------- label matching helpers ----------

def norm(s: str) -> str:
    """Lowercase, `-` → `_`, drop every other character that is not [a-z0-9_/]."""
    return re.sub(r"[^a-z0-9_/]", "", (s or "").lower().replace("-", "_"))


def _first_line(label: str) -> str:
    return re.split(r"<br\s*/?>|\n", label or "", maxsplit=1, flags=re.I)[0].strip()


def label_head(label: str) -> str:
    """Label first line cut at the first of `<br`, `:`, ` (`, `·`, newline (raw, not normalised)."""
    first = _first_line(label)
    cut = len(first)
    for sep in (":", " (", "·"):
        k = first.find(sep)
        if 0 <= k < cut:
            cut = k
    return first[:cut].strip()


def label_candidates(label: str, mid: str) -> list[str]:
    """Normalised match candidates, in order: head, first `( … )` text, full first line, Mermaid id."""
    paren = re.search(r"\(([^()]*)\)", label or "")
    raw = [label_head(label), paren.group(1) if paren else "", _first_line(label), mid or ""]
    out: list[str] = []
    for r in raw:
        n = norm(r).strip("/")
        if n and n not in out:
            out.append(n)
    return out


# ---------- module doc readers ----------

_REQ_ITEM = re.compile(r"^- \*\*((?:REQ|FEAT)-[A-Z0-9]+-\d+)\*\*(.*)$")
_PARENTS = re.compile(r"\(parents?:([^()]*)\)")  # `[^()]` keeps repeated unclosed openers linear
_STATE = re.compile(r"^State: \*\*(.+?)\*\*", re.M)


def bind_yaml(text: str) -> dict[str, list[str]]:
    """`REQ-X-001: [paths]` → {REQ: [paths]} (module-relative, trailing `/` dropped)."""
    out: dict[str, list[str]] = {}
    for k, v in yaml_lite(text).items():
        if v is None:
            vals = []
        elif isinstance(v, list):
            vals = v
        else:
            vals = [v]
        out[str(k)] = [str(x).rstrip("/") for x in vals if x is not None and str(x).strip()]
    return out


def req_lines(text: str) -> dict[str, dict]:
    """`- **REQ-…** (parents: …) — text` items → {id: {"title","parents","line"}}."""
    out: dict[str, dict] = {}
    for n, line, fenced in _walk(text):
        if fenced:
            continue
        m = _REQ_ITEM.match(line)
        if not m or m.group(1) in out:
            continue
        rest = m.group(2)
        pm = _PARENTS.search(rest)
        parents = [p.strip() for p in pm.group(1).split(",") if p.strip()] if pm else []
        title = _PARENTS.sub("", rest, count=1).strip().lstrip("—–-:").strip()
        title = title.replace("**", "").replace("`", "")
        out[m.group(1)] = {"title": title[:200], "parents": parents, "line": n}
    return out


def trace_state(text: str) -> str | None:
    m = _STATE.search(text or "")
    return m.group(1).strip() if m else None


def first_heading(text: str) -> str | None:
    for level, t, _ in headings(text):
        if level == 1:
            return t
    h = headings(text)
    return h[0][1] if h else None


def summary(text: str, limit: int = 200) -> str:
    """First plain paragraph of the body (no headings, quotes, tables, lists, fences, HTML)."""
    block: list[str] = []
    for n, line, fenced in _walk(text):
        if fenced:
            if block:
                break
            continue
        s = line.strip()
        if not s:
            if block:
                break
            continue
        if not block and (s[0] in "#>|<!-*+=`~" or re.match(r"\d+[.)]\s", s)):
            continue
        block.append(s)
    out = " ".join(" ".join(block).split())
    out = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", out)
    out = re.sub(r"\[\[(?:[^\]|]*\|)?([^\]]*)\]\]", r"\1", out).replace("**", "").replace("`", "")
    return out if len(out) <= limit else out[: limit - 1].rstrip() + "…"


def doc_title(text: str, fallback: str) -> str:
    fm, _ = frontmatter(text)
    t = fm.get("title")
    if isinstance(t, (str, int)) and str(t).strip():
        return str(t).strip()
    return first_heading(text) or fallback
