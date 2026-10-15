"""Python adapter: `ast.parse` only (never executed). Regex fallback on SyntaxError."""
from __future__ import annotations

import ast
import io
import keyword
import re
import tokenize

from . import docparse
from .lex import h12, symbol

_KEEP_DECO = ("staticmethod", "classmethod", "property", "abstractmethod", "setter", "getter", "deleter",
              "cached_property", "overload")
_CONST = re.compile(r"^[A-Z][A-Z0-9_]*$")
_KW = set(keyword.kwlist) | {"self", "cls", "True", "False", "None"}
_SKIP_TOK = {tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT,
             tokenize.ENCODING, tokenize.ENDMARKER}


def _dotted(n) -> str | None:
    if isinstance(n, ast.Name):
        return n.id
    if isinstance(n, ast.Attribute):
        b = _dotted(n.value)
        return f"{b}.{n.attr}" if b else None
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "super":
        return "super"
    return None


def _unparse(n) -> str:
    try:
        return ast.unparse(n)
    except Exception:
        return ""


def _deco_name(d) -> str:
    if isinstance(d, ast.Call):
        d = d.func
    s = _dotted(d) or ""
    return s.split(".")[-1]


class _Py:
    def __init__(self, text: str, ctx: dict):
        self.text = text
        self.lines = text.split("\n")
        self.ctx = ctx
        self.syms: list[dict] = []
        self.calls: list[tuple] = []
        self.imports: list[dict] = []
        self.doc_nodes: set[int] = set()
        self.all_names: set[str] | None = None

    # -- source helpers ---------------------------------------------------------------
    def seg(self, l1, c1, l2, c2) -> str:
        if l1 == l2:
            return self.lines[l1 - 1][c1:c2]
        out = [" " * c1 + self.lines[l1 - 1][c1:]]
        out += self.lines[l1:l2 - 1]
        out.append(self.lines[l2 - 1][:c2])
        return "\n".join(out)

    def tokens(self, src: str) -> list[str]:
        try:
            toks = [t.string for t in tokenize.generate_tokens(io.StringIO(src + "\n").readline)
                    if t.type not in _SKIP_TOK]
            return toks
        except (tokenize.TokenError, IndentationError, SyntaxError):
            src = re.sub(r"#[^\n]*", "", src)
            return re.findall(r"\w+|\S", src)

    def body_tokens(self, node, skip_doc=True, skip_defs=False) -> list[str]:
        body = list(node.body)
        if skip_doc and body and _is_doc(body[0]):
            body = body[1:]
        out: list[str] = []
        for st in body:
            if skip_defs and isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                out += ["def", st.name, _unparse(st.args) if not isinstance(st, ast.ClassDef) else "class"]
                continue
            src = self.seg(st.lineno, st.col_offset, st.end_lineno, st.end_col_offset)
            if hasattr(st, "decorator_list") and st.decorator_list:
                d0 = st.decorator_list[0]
                src = self.seg(d0.lineno, d0.col_offset - 1, st.end_lineno, st.end_col_offset)
            out += self.tokens(src)
        return out

    # -- docs ---------------------------------------------------------------------------
    def docof(self, node):
        body = getattr(node, "body", None)
        if not body:
            return None
        first = body[0]
        if not _is_doc(first):
            return None
        self.doc_nodes.add(id(first.value))
        raw = first.value.value
        txt = ast.get_docstring(node, clean=True) or ""
        lead = raw[:len(raw) - len(raw.lstrip())].count("\n")
        d = docparse.parse_docstring(txt, first.lineno + lead)
        d["line"] = first.lineno
        d["end"] = first.end_lineno
        return d

    # -- walk ---------------------------------------------------------------------------
    def run(self, tree):
        for st in tree.body:
            if isinstance(st, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__" for t in st.targets):
                try:
                    v = ast.literal_eval(st.value)
                    if isinstance(v, (list, tuple)):
                        self.all_names = {x for x in v if isinstance(x, str)}
                except Exception:
                    pass
        self.walk(tree.body, prefix="", parent=None, cls=None, owner=None, in_func=False)

    def pub(self, qual: str, in_func: bool) -> bool:
        if in_func:
            return False
        parts = qual.split(".")
        if any(p.startswith("_") for p in parts):
            return False
        if self.all_names is not None and parts[0] not in self.all_names:
            return False
        return True

    def walk(self, body, prefix, parent, cls, owner, in_func):
        for st in body:
            if isinstance(st, ast.ClassDef):
                self.klass(st, prefix, parent, owner, in_func)
            elif isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.func(st, prefix, parent, cls, owner, in_func)
            elif isinstance(st, (ast.Import, ast.ImportFrom)):
                self.imp(st)
            else:
                if (not in_func and cls is None and parent is None
                        and isinstance(st, (ast.Assign, ast.AnnAssign))):
                    self.const(st)
                for field, value in ast.iter_fields(st):
                    vals = value if isinstance(value, list) else [value]
                    if field in ("body", "orelse", "finalbody") and vals and isinstance(vals[0], ast.stmt):
                        self.walk(vals, prefix, parent, cls, owner, in_func)
                    elif field == "handlers":
                        for h in vals:
                            if h.type is not None:
                                self.scan(h.type, owner)
                            self.walk(h.body, prefix, parent, cls, owner, in_func)
                    elif field == "cases":
                        for c in vals:
                            if c.guard is not None:
                                self.scan(c.guard, owner)
                            self.walk(c.body, prefix, parent, cls, owner, in_func)
                    else:
                        for v in vals:
                            if isinstance(v, ast.AST):
                                self.scan(v, owner)

    def scan(self, node, owner, types=None):
        stack = [node]
        while stack:
            n = stack.pop()
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(n, ast.Call):
                self.call(n, owner, types)
            stack.extend(ast.iter_child_nodes(n))

    def call(self, n: ast.Call, owner, types):
        f = n.func
        recv = None
        if isinstance(f, ast.Name):
            name = f.id
        elif isinstance(f, ast.Attribute):
            name = f.attr
            # `", ".join(x)`, `get().add(t)`: the receiver is an expression, so its type is unknown ("?")
            recv = _dotted(f.value) or "?"
        else:
            return
        rt = None
        if recv and types and recv in types:
            rt = types[recv]
        self.calls.append((n.lineno, n.col_offset, {"from": owner, "name": name, "recv": recv, "recv_type": rt,
                                                    "line": n.lineno, "kind": "call"}))

    def imp(self, st):
        if isinstance(st, ast.Import):
            for a in st.names:
                self.imports.append({"target": a.name, "names": [], "alias": a.asname, "line": st.lineno,
                                     "kind": "import", "level": 0, "system": False})
        else:
            for a in st.names:
                self.imports.append({"target": st.module or "", "names": [a.name], "alias": a.asname,
                                     "line": st.lineno, "kind": "from", "level": st.level or 0, "system": False})

    def const(self, st):
        targets = st.targets if isinstance(st, ast.Assign) else [st.target]
        for t in targets:
            if isinstance(t, ast.Name) and _CONST.match(t.id) and t.id != "__all__":
                val = _unparse(st.value) if st.value is not None else ""
                ann = (": " + _unparse(st.annotation)) if isinstance(st, ast.AnnAssign) else ""
                sig = f"{t.id}{ann} = {val}"[:200]
                s = symbol(t.id, t.id, "const", st.lineno, st.end_lineno, sig=sig,
                           pub=self.pub(t.id, False), sig_hash=h12(sig[len(t.id):]),
                           body_hash=h12("\x1f".join(self.tokens(val))))
                self.syms.append(s)

    def func(self, st, prefix, parent, cls, owner, in_func):
        name = st.name
        qual = prefix + name
        decos = [_deco_name(d) for d in st.decorator_list]
        keep = [d for d in decos if d in _KEEP_DECO]
        args = _unparse(st.args)
        ret = f" -> {_unparse(st.returns)}" if st.returns is not None else ""
        asy = "async " if isinstance(st, ast.AsyncFunctionDef) else ""
        pre = "".join(f"@{d} " for d in keep)
        sig = f"{pre}{asy}def {name}({args}){ret}"
        sig_nm = f"{pre}{asy}def ({args}){ret}"
        a = st.args
        params = [x.arg for x in a.posonlyargs + a.args]
        if a.vararg:
            params.append("*" + a.vararg.arg)
        params += [x.arg for x in a.kwonlyargs]
        if a.kwarg:
            params.append("**" + a.kwarg.arg)
        arity = len([p for p in params if not p.startswith("*")])
        is_method = cls is not None
        if is_method and params and params[0] in ("self", "cls") and "staticmethod" not in decos:
            arity -= 1
        kind = "method" if is_method else "function"
        toks = self.body_tokens(st)
        s = symbol(qual, name, kind, st.lineno, st.end_lineno, sig=sig, params=params, arity=max(arity, 0),
                   pub=self.pub(qual, in_func), parent=parent, doc=self.docof(st),
                   static="staticmethod" in decos, virtual="abstractmethod" in decos,
                   pure="abstractmethod" in decos, sig_hash=h12(sig_nm), body_hash=h12("\x1f".join(toks)),
                   words=sorted({t for t in toks if t.isidentifier() and t not in _KW})[:200])
        if st.decorator_list:
            s["_start"] = st.decorator_list[0].lineno
        self.syms.append(s)
        # decorators and defaults run in the enclosing scope
        for d in st.decorator_list:
            self.scan(d, owner)
        for dflt in a.defaults + [x for x in a.kw_defaults if x is not None]:
            self.scan(dflt, owner)
        types = self.local_types(st)
        if cls is not None and cls.get("_members") is not None:
            self.self_members(st, cls["_members"], types)
        self.walk_func(st.body, qual, types)

    def walk_func(self, body, owner, types):
        for st in body:
            if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.func(st, owner + ".", owner, None, owner, True)
            elif isinstance(st, ast.ClassDef):
                self.klass(st, owner + ".", owner, owner, True)
            elif isinstance(st, (ast.Import, ast.ImportFrom)):
                self.imp(st)
            else:
                for field, value in ast.iter_fields(st):
                    vals = value if isinstance(value, list) else [value]
                    if field in ("body", "orelse", "finalbody") and vals and isinstance(vals[0], ast.stmt):
                        self.walk_func(vals, owner, types)
                    elif field == "handlers":
                        for h in vals:
                            if h.type is not None:
                                self.scan(h.type, owner, types)
                            self.walk_func(h.body, owner, types)
                    elif field == "cases":
                        for c in vals:
                            if c.guard is not None:
                                self.scan(c.guard, owner, types)
                            self.walk_func(c.body, owner, types)
                    else:
                        for v in vals:
                            if isinstance(v, ast.AST):
                                self.scan(v, owner, types)

    def local_types(self, fn) -> dict:
        types = {}
        a = fn.args
        for x in a.posonlyargs + a.args + a.kwonlyargs:
            if x.annotation is not None:
                types[x.arg] = _unparse(x.annotation)
        stack = list(fn.body)
        while stack:
            n = stack.pop()
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                continue
            if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
                t = _ctor_type(n.value)
                if t:
                    types.setdefault(n.targets[0].id, t)
            elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
                types.setdefault(n.target.id, _unparse(n.annotation))
            stack.extend(ast.iter_child_nodes(n))
        return types

    def self_members(self, fn, members: dict, types: dict):
        for n in ast.walk(fn):
            tgt, val, ann = None, None, None
            if isinstance(n, ast.Assign) and len(n.targets) == 1:
                tgt, val = n.targets[0], n.value
            elif isinstance(n, ast.AnnAssign):
                tgt, val, ann = n.target, n.value, n.annotation
            if (isinstance(tgt, ast.Attribute) and isinstance(tgt.value, ast.Name)
                    and tgt.value.id == "self"):
                t = _unparse(ann) if ann is not None else (_ctor_type(val) if val is not None else None)
                if not t and isinstance(val, ast.Name) and val.id in types:
                    t = types[val.id]
                if t:
                    members.setdefault(tgt.attr, t)
                else:
                    members.setdefault(tgt.attr, "")

    def klass(self, st, prefix, parent, owner, in_func):
        name = st.name
        qual = prefix + name
        bases = [_unparse(b) for b in st.bases]
        sig = f"class {name}({', '.join(bases)})" if bases else f"class {name}"
        members: dict = {}
        for b in st.body:
            if isinstance(b, ast.AnnAssign) and isinstance(b.target, ast.Name):
                members[b.target.id] = _unparse(b.annotation)
            elif isinstance(b, ast.Assign):
                for t in b.targets:
                    if isinstance(t, ast.Name):
                        members.setdefault(t.id, _ctor_type(b.value) or "")
        toks = self.body_tokens(st, skip_defs=True)
        s = symbol(qual, name, "class", st.lineno, st.end_lineno, sig=sig, pub=self.pub(qual, in_func),
                   parent=parent, bases=bases, doc=self.docof(st), sig_hash=h12(sig.replace(name, "", 1)),
                   body_hash=h12("\x1f".join(toks)), members=members,
                   words=sorted({t for t in toks if t.isidentifier() and t not in _KW})[:200])
        if st.decorator_list:
            s["_start"] = st.decorator_list[0].lineno
        self.syms.append(s)
        for d in st.decorator_list:
            self.scan(d, owner)
        for b in st.bases + [k.value for k in st.keywords]:
            self.scan(b, owner)
        holder = {"_members": members}
        for b in st.body:
            if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.func(b, qual + ".", qual, holder, qual, in_func)
            elif isinstance(b, ast.ClassDef):
                self.klass(b, qual + ".", qual, qual, in_func)
            elif isinstance(b, (ast.Import, ast.ImportFrom)):
                self.imp(b)
            elif not _is_doc(b):
                self.scan(b, qual)

    def finish(self, tree) -> dict:
        calls = [c for _, _, c in sorted(self.calls, key=lambda x: (x[0], x[1]))]
        strings, texts = [], []
        for n in ast.walk(tree):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in self.doc_nodes:
                strings.append((n.lineno, n.value))
                texts.append(n.value)
        try:
            for t in tokenize.generate_tokens(io.StringIO(self.text).readline):
                if t.type == tokenize.COMMENT:
                    texts.append(t.string)
        except (tokenize.TokenError, IndentationError, SyntaxError):
            pass
        file_doc = None
        if tree.body and _is_doc(tree.body[0]):
            file_doc = self.docof(tree)
        return {"symbols": self.syms, "calls": calls, "imports": self.imports, "file_doc": file_doc,
                "_strings": strings, "_texts": texts}


def _is_doc(st) -> bool:
    return (isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant)
            and isinstance(st.value.value, str))


def _ctor_type(v) -> str | None:
    if isinstance(v, ast.Call):
        d = _dotted(v.func)
        if d and d != "super" and d.split(".")[-1][:1].isupper():
            return d
    return None


def extract_py(text: str, ctx: dict) -> dict:
    try:
        tree = ast.parse(text, filename=ctx.get("rel", "<file>"))
    except (SyntaxError, ValueError, MemoryError):
        return _fallback(text, ctx)
    p = _Py(text, ctx)
    p.run(tree)
    return p.finish(tree)


_DEF = re.compile(r"^(\s*)(?:async\s+)?def\s+(\w+)\s*\(([^)]*)|^(\s*)class\s+(\w+)")
# anchored at the start of a dotted chain so each chain is scanned once (no quadratic backtracking)
_CALL = re.compile(r"(?<![\w.])([A-Za-z_][\w.]*)\s*\(")
MAX_SCAN_LINE = 2000
_IMP = re.compile(r"^\s*(?:from\s+(\.*)([\w.]*)\s+import\s+([\w, ]+)|import\s+([\w.]+)(?:\s+as\s+(\w+))?)")


def _fallback(text: str, ctx: dict) -> dict:
    """Regex scanner for files that do not parse: defs, classes, imports, bare calls."""
    lines = text.split("\n")
    syms, stack, calls, imports = [], [], [], []
    for i, ln in enumerate(lines, 1):
        m = _DEF.match(ln)
        if m:
            ind = len(m.group(1) if m.group(2) else m.group(4))
            while stack and stack[-1][0] >= ind:
                stack.pop()
            name = m.group(2) or m.group(5)
            kind = "function" if m.group(2) else "class"
            if kind == "function" and stack and stack[-1][2] == "class":
                kind = "method"
            prefix = ".".join(s[1] for s in stack)
            qual = f"{prefix}.{name}" if prefix else name
            params = [p.strip().split(":")[0].split("=")[0].strip() for p in (m.group(3) or "").split(",") if p.strip()]
            sig = (f"def {name}({m.group(3) or ''})" if m.group(2) else f"class {name}")
            s = symbol(qual, name, kind, i, i, sig=sig, params=params, arity=len(params),
                       pub=not any(p.startswith("_") for p in qual.split(".")),
                       parent=prefix or None, sig_hash=h12(sig.replace(name, "", 1)), body_hash=h12(""))
            syms.append(s)
            stack.append((ind, name, kind, s))
            continue
        im = _IMP.match(ln)
        if im:
            if im.group(3):
                for nm in im.group(3).split(","):
                    nm = nm.strip().split(" as ")[0].strip()
                    if nm:
                        imports.append({"target": im.group(2), "names": [nm], "alias": None, "line": i,
                                        "kind": "from", "level": len(im.group(1)), "system": False})
            else:
                imports.append({"target": im.group(4), "names": [], "alias": im.group(5), "line": i,
                                "kind": "import", "level": 0, "system": False})
            continue
        code = re.sub(r"#.*", "", ln)
        if not code.strip():
            continue
        ind = len(ln) - len(ln.lstrip())
        while stack and stack[-1][0] >= ind:
            stack.pop()
        for s in [x[3] for x in stack]:
            s["end"] = i
        owner = stack[-1][3]["qual"] if stack and stack[-1][2] != "class" else None
        if len(code) > MAX_SCAN_LINE:
            continue
        for cm in _CALL.finditer(code):
            recv, _, nm = cm.group(1).rpartition(".")
            if not nm or nm in _KW or keyword.iskeyword(nm):
                continue
            calls.append({"from": owner, "name": nm, "recv": recv or None, "recv_type": None, "line": i,
                          "kind": "call"})
    return {"ok": False, "conf": "low", "symbols": syms, "calls": calls, "imports": imports,
            "errors": ["SyntaxError: fell back to the regex scanner"], "_strings": [], "_texts": []}
