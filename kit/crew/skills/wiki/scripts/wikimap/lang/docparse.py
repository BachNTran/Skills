"""Parse doc comments (Doxygen, JSDoc, rustdoc, godoc, plain line) and Python docstrings.

Both entry points return the Doc object of spec §3.1 plus a private `_refs` list
[(text, style, line)] that `extract` turns into the file's `refs` and then drops.
The text is kept verbatim (markers stripped); nothing here renders or evaluates it.
"""
from __future__ import annotations

import re
import textwrap

from .lex import h12

MAX_TEXT = 16384
MAX_BRIEF = 200

_MARK = re.compile(r"^\s*(?:/\*\*<?|/\*!<?|/\*+|///<?|//!<?|//+|\*(?!/))?")
_END = re.compile(r"\s*\*+/\s*$")
_TAG = re.compile(r"^[@\\](\w+)(\[[^\]]*\])?\s*(.*)$")
_INLINE = re.compile(r"\{@(?:link|linkcode|linkplain)\s+([^}\s|]+)[^}]*\}|[@\\]ref\s+([\w:.#~]+)")
_SPHINX_ROLE = re.compile(r":(?:py:)?(func|class|meth|attr|exc|obj|data|const|mod):`~?([^`]+)`")


def _doc(style: str, line: int) -> dict:
    return {"style": style, "brief": "", "text": "", "params": {}, "explicit_params": False,
            "returns": "", "raises": [], "see": [], "deprecated": False, "line": line, "end": line,
            "hash": "", "_refs": []}


def _collapse(s: str) -> str:
    return " ".join(s.split())


def _first_sentence(par: str) -> str:
    par = _collapse(par)
    m = re.match(r"^(.+?[.!?])(?:\s|$)", par)
    s = m.group(1) if m else par
    return s[:MAX_BRIEF]


def _finish(d: dict, text: str) -> dict:
    d["text"] = text[:MAX_TEXT]
    d["hash"] = h12(_collapse(text))
    seen = []
    for t, _st, _ln in d["_refs"]:
        if t not in seen:
            seen.append(t)
    d["see"] = seen
    return d


def _clean_ref(s: str) -> str:
    return s.strip().strip("`'\"").rstrip(".,;:")


def _strip_markers(raw: str) -> list[str]:
    out = []
    for ln in raw.split("\n"):
        ln = _END.sub("", ln)
        m = _MARK.match(ln)
        rest = ln[m.end():] if m else ln
        if rest.startswith(" "):
            rest = rest[1:]
        out.append(rest.rstrip())
    return out


def parse_block(raw: str, style: str, line: int) -> dict:
    """Doxygen / JSDoc / line / rustdoc / godoc comment block starting at `line`."""
    d = _doc(style, line)
    raw = raw.replace("\r", "")
    lines = _strip_markers(raw)
    d["end"] = line + raw.count("\n")
    if any("<summary>" in ln for ln in lines):
        return _xml(d, lines, line)
    # drop leading/trailing blank lines but remember the offset
    off = 0
    while lines and not lines[0].strip():
        lines.pop(0)
        off += 1
    while lines and not lines[-1].strip():
        lines.pop()
    body = textwrap.dedent("\n".join(lines))
    lines = body.split("\n") if body else []
    desc: list[str] = []
    brief = None
    cur = None  # (kind, key, list)
    section = None  # rustdoc "# Arguments" etc.
    logical = []
    for idx, ln in enumerate(lines):
        # a mid-line @see/\sa starts its own paragraph (Doxygen semantics)
        parts = re.split(r"\s+(?=[@\\](?:see|sa)\s)", ln)
        for k, part in enumerate(parts):
            logical.append((line + off + idx, part if k == 0 else part.strip()))
    for lno, ln in logical:
        s = ln.strip()
        for m in _INLINE.finditer(s):
            tgt = m.group(1) or m.group(2)
            d["_refs"].append((_clean_ref(tgt), "link" if m.group(1) else "ref", lno))
        if style == "rustdoc" and s.startswith("#") and not s.startswith("#["):
            section = s.lstrip("#").strip().lower()
            cur = None
            if section in ("arguments", "parameters"):
                d["explicit_params"] = True
            continue
        if section in ("arguments", "parameters"):
            m = re.match(r"^[*-]\s+`?(\w+)`?\s*[-:–]?\s*(.*)$", s)
            if m:
                d["params"][m.group(1)] = m.group(2)
                continue
        if section == "errors" and s:
            d["raises"].append(s)
            continue
        m = _TAG.match(s)
        if m:
            tag, _dir, rest = m.group(1).lower(), m.group(2), m.group(3)
            cur = None
            if tag in ("brief", "short", "summary"):
                brief = rest
                cur = ("brief", None, [rest])
            elif tag in ("param", "arg", "argument", "prop"):
                rest = re.sub(r"^\{[^}]*\}\s*", "", rest)
                pm = re.match(r"^\[?([\w$.*]+)(?:=[^\]]*)?\]?\s*(?:-\s*)?(.*)$", rest)
                if pm:
                    name = pm.group(1).split(".")[0]
                    d["explicit_params"] = True
                    if name not in d["params"]:
                        d["params"][name] = pm.group(2)
                    cur = ("param", name, None)
            elif tag in ("return", "returns", "retval", "result"):
                rest = re.sub(r"^\{[^}]*\}\s*", "", rest)
                d["returns"] = (d["returns"] + " " + rest).strip() if d["returns"] else rest
                cur = ("returns", None, None)
            elif tag in ("throws", "throw", "exception", "raises"):
                rest = re.sub(r"^\{([^}]*)\}\s*", r"\1 ", rest)
                if rest.split():
                    d["raises"].append(rest.split()[0])
            elif tag in ("see", "sa"):
                tgt = rest.strip()
                lm = re.match(r"^\{@link\w*\s+([^}\s|]+)", tgt)
                if lm:
                    tgt = lm.group(1)
                elif tgt:
                    tgt = tgt.split()[0]
                tgt = _clean_ref(tgt)
                if tgt and not re.match(r"^https?://", tgt) and not any(r[0] == tgt and r[2] == lno for r in d["_refs"]):
                    d["_refs"].append((tgt, "see", lno))
            elif tag == "deprecated":
                d["deprecated"] = True
            elif tag == "file":
                d["_file"] = True
            elif tag in ("details", "note", "warning", "pre", "post", "remark", "remarks"):
                desc.append(rest)
            continue
        if cur is not None and s:
            if cur[0] == "param":
                d["params"][cur[1]] = (d["params"][cur[1]] + " " + s).strip()
            elif cur[0] == "returns":
                d["returns"] = (d["returns"] + " " + s).strip()
            elif cur[0] == "brief":
                brief = (brief or "") + " " + s
            continue
        if not s:
            cur = None if cur and cur[0] == "brief" else cur
        if cur is None:
            desc.append(ln)
    if brief is not None:
        d["brief"] = _collapse(brief)[:MAX_BRIEF]
    else:
        par = []
        for ln in desc:
            if not ln.strip():
                if par:
                    break
                continue
            par.append(ln)
        d["brief"] = _first_sentence(" ".join(par)) if par else ""
    return _finish(d, body)


def _xml(d: dict, lines: list[str], line: int) -> dict:
    body = "\n".join(lines).strip()
    m = re.search(r"<summary>(.*?)</summary>", body, re.S)
    d["brief"] = _first_sentence(re.sub(r"<[^>]+>", "", m.group(1))) if m else ""
    for pm in re.finditer(r'<param\s+name="([^"]+)"\s*>(.*?)</param>', body, re.S):
        d["params"][pm.group(1)] = _collapse(re.sub(r"<[^>]+>", "", pm.group(2)))
        d["explicit_params"] = True
    rm = re.search(r"<returns>(.*?)</returns>", body, re.S)
    if rm:
        d["returns"] = _collapse(re.sub(r"<[^>]+>", "", rm.group(1)))
    for em in re.finditer(r'<exception\s+cref="([^"]+)"', body):
        d["raises"].append(em.group(1))
    for sm in re.finditer(r'<see(?:also)?\s+cref="([^"]+)"', body):
        d["_refs"].append((sm.group(1), "see", line))
    return _finish(d, body)


# ---------------------------------------------------------------------------------------
# Python docstrings
# ---------------------------------------------------------------------------------------

_G_SECTIONS = {
    "args": "params", "arguments": "params", "parameters": "params", "params": "params",
    "keyword args": "params", "keyword arguments": "params", "other parameters": "params",
    "returns": "returns", "return": "returns", "yields": "returns", "yield": "returns",
    "raises": "raises", "exceptions": "raises", "except": "raises", "raise": "raises",
    "see also": "see", "warns": "other", "note": "other", "notes": "other", "example": "other",
    "examples": "other", "attributes": "other", "todo": "other", "warning": "other",
    "warnings": "other", "references": "other", "methods": "other",
}


def parse_docstring(text: str, line: int) -> dict:
    """Google, NumPy or Sphinx docstring (already cleaned, e.g. by ast.get_docstring)."""
    d = _doc("docstring", line)
    text = (text or "").replace("\r", "")
    lines = text.split("\n")
    d["end"] = line + len(lines) - 1
    section = None
    sec_indent = 0
    cur_param = None
    desc_done = False
    par: list[str] = []
    i = 0
    while i < len(lines):
        ln = lines[i]
        s = ln.strip()
        lno = line + i
        ind = len(ln) - len(ln.lstrip())
        for m in _SPHINX_ROLE.finditer(ln):
            d["_refs"].append((_clean_ref(m.group(2)), m.group(1), lno))
        if s.startswith(".. deprecated::"):
            d["deprecated"] = True
        # NumPy header: word line followed by dashes
        if s and i + 1 < len(lines) and re.match(r"^-{3,}\s*$", lines[i + 1].strip()) and s.lower() in _G_SECTIONS:
            section = _G_SECTIONS[s.lower()]
            sec_indent = ind
            if section == "params":
                d["explicit_params"] = True
            cur_param = None
            desc_done = True
            i += 2
            numpy = True
            while i < len(lines):
                ln2 = lines[i]
                s2 = ln2.strip()
                ind2 = len(ln2) - len(ln2.lstrip())
                if s2 and i + 1 < len(lines) and re.match(r"^-{3,}\s*$", lines[i + 1].strip()):
                    break
                for m in _SPHINX_ROLE.finditer(ln2):
                    d["_refs"].append((_clean_ref(m.group(2)), m.group(1), line + i))
                if s2 and ind2 <= sec_indent:
                    if section == "params":
                        names = s2.split(":")[0]
                        cur_param = []
                        for nm in names.split(","):
                            nm = nm.strip()
                            if nm:
                                d["params"][nm] = ""
                                cur_param.append(nm)
                    elif section == "returns":
                        d["returns"] = (d["returns"] + " " + s2).strip()
                    elif section == "raises":
                        d["raises"].append(re.split(r"[\s:]", s2)[0])
                    elif section == "see":
                        for nm in re.split(r"[,\s]+", s2.split(" : ")[0]):
                            nm = _clean_ref(nm)
                            if nm and re.match(r"^[\w.]+$", nm):
                                d["_refs"].append((nm, "see", line + i))
                elif s2 and cur_param and section == "params":
                    for nm in cur_param:
                        d["params"][nm] = (d["params"][nm] + " " + s2).strip()
                elif s2 and section == "returns":
                    d["returns"] = (d["returns"] + " " + s2).strip()
                i += 1
            del numpy
            continue
        # Sphinx fields
        m = re.match(r"^:(param|parameter|arg|argument|key|keyword)\s+(?:[^:]*\s)?([\w*]+)\s*:\s*(.*)$", s)
        if m:
            d["explicit_params"] = True
            d["params"][m.group(2)] = m.group(3)
            cur_param = ("sphinx", m.group(2))
            desc_done = True
            i += 1
            continue
        m = re.match(r"^:(returns?|return)\s*:\s*(.*)$", s)
        if m:
            d["returns"] = m.group(2)
            cur_param = ("sphinx-ret", None)
            desc_done = True
            i += 1
            continue
        m = re.match(r"^:(raises?|except|exception)\s+([\w.]+)\s*:", s)
        if m:
            d["raises"].append(m.group(2))
            desc_done = True
            i += 1
            continue
        if re.match(r"^:(type|rtype|vartype|ivar|cvar|var)\b", s):
            desc_done = True
            i += 1
            continue
        # Google section header
        m = re.match(r"^([A-Za-z][A-Za-z ]*):\s*$", s)
        if m and m.group(1).lower() in _G_SECTIONS:
            section = _G_SECTIONS[m.group(1).lower()]
            sec_indent = ind
            if section == "params":
                d["explicit_params"] = True
            cur_param = None
            desc_done = True
            i += 1
            continue
        if section and s and ind > sec_indent:
            item_ind = None
            if section == "params":
                pm = re.match(r"^(\*{0,2}\w+)\s*(?:\(([^)]*)\))?\s*:\s*(.*)$", s)
                if pm and (cur_param is None or isinstance(cur_param, tuple) or ind <= cur_param[1]):
                    d["params"][pm.group(1)] = pm.group(3)
                    cur_param = [pm.group(1), ind]
                elif isinstance(cur_param, list):
                    d["params"][cur_param[0]] = (d["params"][cur_param[0]] + " " + s).strip()
            elif section == "returns":
                d["returns"] = (d["returns"] + " " + s).strip()
            elif section == "raises":
                rm = re.match(r"^([\w.]+)\s*:", s)
                if rm:
                    d["raises"].append(rm.group(1))
            elif section == "see":
                for nm in re.split(r"[,\s]+", s.split(":")[0]):
                    nm = _clean_ref(nm)
                    if nm and re.match(r"^[\w.]+$", nm):
                        d["_refs"].append((nm, "see", lno))
            del item_ind
            i += 1
            continue
        if section and s and ind <= sec_indent:
            section = None
        if cur_param and isinstance(cur_param, tuple) and s and cur_param[0] == "sphinx" and ind > 0:
            d["params"][cur_param[1]] = (d["params"][cur_param[1]] + " " + s).strip()
            i += 1
            continue
        if not desc_done:
            if s:
                par.append(s)
            elif par:
                desc_done = True
        i += 1
    d["brief"] = _first_sentence(" ".join(par)) if par else ""
    return _finish(d, text)
