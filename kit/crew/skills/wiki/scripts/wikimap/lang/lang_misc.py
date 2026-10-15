"""Adapters for proto, SQL, shell, and a generic brace adapter for Go, Rust and Java/Kotlin/C#/Swift.

proto: `service` → kind `interface`, `rpc` → kind `method` (spec §2.2 kinds).
Go/Rust/clike: definitions, docs, imports, visibility, bare-name calls only.
"""
from __future__ import annotations

import re

from . import docparse
from .lex import src_text, DocIndex, Lexed, brackets, doc_style, h12, hash_tokens, is_ident, symbol, tokenize, words


def extract_misc(text: str, ctx: dict, lang: str) -> dict:
    if lang == "proto":
        return _proto(text, ctx)
    if lang == "sql":
        return _sql(text, ctx)
    if lang == "shell":
        return _shell(text, ctx)
    if lang == "go":
        return _Go(text, ctx).run()
    if lang == "rust":
        return _Rust(text, ctx).run()
    return _Clike(text, ctx).run()


class _Base:
    dialect = "c"
    doc_name = "doxygen"
    kw: set = set()

    def __init__(self, text, ctx):
        self.lx = Lexed(text, self.dialect)
        self.ctx = ctx
        self.toks = tokenize(self.lx)
        self.match, self.balanced = brackets(self.toks)
        self.docs = DocIndex(self.lx)
        self.syms, self.calls, self.imports = [], [], []
        self.file_doc = None

    def t(self, i):
        return self.toks[i].t if 0 <= i < len(self.toks) else ""

    def close(self, i):
        return self.match.get(i, len(self.toks) - 1)

    def lit(self, i):
        tk = self.toks[i] if 0 <= i < len(self.toks) else None
        return self.lx.literal(tk.pos) if tk is not None and tk.t.startswith('"') else None

    def text_of(self, a, b):
        return src_text(self.lx, self.toks, a, b)

    def style_of(self, raw):
        return doc_style(raw, "line", self.doc_name)

    def attach_doc(self, i):
        tk = self.toks[i]
        blk = self.docs.leading(tk.line, tk.pos)
        if not blk or blk["used"]:
            return None
        blk["used"] = True
        return docparse.parse_block(blk["raw"], self.style_of(blk["raw"]), blk["sl"])

    def sym(self, start, name, qual, kind, end_idx, sig, **kw):
        toks = self.toks
        s = symbol(qual, name, kind, toks[start].line, toks[min(end_idx, len(toks) - 1)].line, sig=sig,
                   sig_hash=h12(sig.replace(name, "", 1)), **kw)
        s["doc"] = self.attach_doc(start)
        self.syms.append(s)
        return s

    def params(self, o, c, name_first=True):
        groups, cur, depth = [], [], 0
        for k in range(o + 1, c):
            t = self.t(k)
            if t in ("(", "[", "{", "<"):
                depth += 1
            elif t in (")", "]", "}", ">"):
                depth -= 1
            if t == "," and depth == 0:
                groups.append(cur)
                cur = []
                continue
            cur.append(self.t(k))
        if cur:
            groups.append(cur)
        names = []
        for g in groups:
            g = [x for x in g if x not in ("mut", "&", "*", "ref", "out", "in", "params", "final", "val", "var",
                                           "inout", "this", "...")]
            if not g:
                continue
            if name_first:
                if is_ident(g[0]) and g[0] != "self":
                    names.append(g[0] if not (len(g) > 1 and is_ident(g[1]) and g[1] != "_" and self.dialect == "clike" and ":" in g) else g[1])
            else:
                ids = [x for x in g if is_ident(x)]
                if "=" in g:
                    ids = [x for x in g[:g.index("=")] if is_ident(x)]
                if len(ids) >= 2 or (ids and len(g) == 1 and False):
                    names.append(ids[-1])
        return names, len(groups)

    def bare_calls(self, a, b, owner):
        toks = self.toks
        for k in range(a + 1, b):
            if toks[k].t != "(" or k - 1 <= a:
                continue
            nm = toks[k - 1].t
            before = toks[k - 2].t if k >= 2 else ""
            if not is_ident(nm) or nm in self.kw:
                continue
            if before in (".", "?.", "::", "fn", "func", "fun", "new", "def"):
                continue
            if self.dialect != "go" and nm[0].isupper():
                continue  # constructors / enum variants: not bare function calls
            self.calls.append({"from": owner, "name": nm, "recv": None, "recv_type": None,
                               "line": toks[k - 1].line, "kind": "call"})

    def result(self):
        texts = [c[4] for c in self.lx.comments()] + [v for _, v in self.lx.strings()]
        return {"symbols": self.syms, "calls": self.calls, "imports": self.imports, "file_doc": self.file_doc,
                "conf": "high" if self.balanced else "low", "_strings": self.lx.strings(), "_texts": texts}


# ---------------------------------------------------------------------------------------
# protobuf
# ---------------------------------------------------------------------------------------

class _Proto(_Base):
    dialect = "c"
    doc_name = "line"

    def style_of(self, raw):
        return doc_style(raw, "line", "doxygen")

    def run(self):
        toks = self.toks
        pkg = ""
        i = 0
        n = len(toks)
        while i < n:
            t = toks[i].t
            if t == "package":
                j = i + 1
                parts = []
                while j < n and toks[j].t != ";":
                    parts.append(toks[j].t)
                    j += 1
                pkg = "".join(parts)
                i = j + 1
                continue
            if t == "import":
                j = i + 1
                while j < n and not toks[j].t.startswith('"') and toks[j].t != ";":
                    j += 1
                if j < n and toks[j].t.startswith('"'):
                    self.imports.append({"target": self.lit(j), "names": [], "alias": None, "line": toks[i].line,
                                         "kind": "import", "level": 0, "system": False})
                i = j + 1
                continue
            if t in ("message", "enum", "service") and is_ident(self.t(i + 1)) and self.t(i + 2) == "{":
                i = self.block(i, [pkg] if pkg else [], None)
                continue
            i += 1
        return self.result()

    def block(self, i, scope, parent):
        toks = self.toks
        kw, name = toks[i].t, toks[i + 1].t
        o = i + 2
        c = self.close(o)
        qual = ".".join(scope + [name])
        kind = {"message": "message", "enum": "enum", "service": "interface"}[kw]
        s = self.sym(i, name, qual, kind, c, f"{kw} {name}", pub=True, parent=parent,
                     body_hash=hash_tokens(self.lx, toks, o, c + 1), words=words(toks, o + 1, c))
        k = o + 1
        while k < c:
            t = toks[k].t
            if t in ("message", "enum") and is_ident(self.t(k + 1)) and self.t(k + 2) == "{":
                k = self.block(k, scope + [name], qual)
                continue
            if t == "rpc" and is_ident(self.t(k + 1)):
                j = k + 2
                while j < c and toks[j].t not in (";", "{"):
                    j += 1
                end = self.close(j) if toks[j].t == "{" else j
                sig = self.text_of(k, j)
                args = []
                if self.t(k + 2) == "(":
                    pc = self.close(k + 2)
                    args = [toks[x].t for x in range(k + 3, pc) if is_ident(toks[x].t) and toks[x].t != "stream"]
                rs = self.sym(k, toks[k + 1].t, f"{qual}.{toks[k + 1].t}", "method", end, sig, pub=True,
                              parent=qual, arity=len(args), body_hash=hash_tokens(self.lx, toks, k, end + 1),
                              decl=True)
                rs["words"] = sorted(set(args))
                k = end + 1
                continue
            if t in ("oneof",) and self.t(k + 2) == "{":
                k += 3
                continue
            if kind == "message" and is_ident(t) and t not in ("option", "reserved", "extensions", "oneof"):
                # [repeated|optional] Type name = N;
                j = k
                while j < c and toks[j].t not in (";", "{", "}"):
                    j += 1
                seg = [toks[x].t for x in range(k, j)]
                if "=" in seg:
                    eq = seg.index("=")
                    if eq >= 2 and is_ident(seg[eq - 1]):
                        ty = [x for x in seg[:eq - 1] if x not in ("repeated", "optional", "required")]
                        s["members"][seg[eq - 1]] = "".join(ty)
                k = j + 1
                continue
            if kind == "enum" and is_ident(t) and self.t(k + 1) == "=":
                s["members"][t] = ""
            k += 1
        s["words"] = sorted(set(s["words"]) | set(s["members"]))[:200]
        return c + 1


def _proto(text, ctx):
    return _Proto(text, ctx).run()


# ---------------------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------------------

def _sql_strip(text):
    out = list(text)
    comments = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if text.startswith("--", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            comments.append((i, j))
            for k in range(i, j):
                out[k] = " "
            i = j
            continue
        if text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            comments.append((i, j))
            for k in range(i, j):
                if out[k] != "\n":
                    out[k] = " "
            i = j
            continue
        if c == "'":
            j = i + 1
            while j < n:
                if text[j] == "'" and j + 1 < n and text[j + 1] == "'":
                    j += 2
                    continue
                if text[j] == "'":
                    break
                j += 1
            for k in range(i + 1, min(j, n)):
                if out[k] != "\n":
                    out[k] = " "
            i = j + 1
            continue
        i += 1
    return "".join(out), comments


_CREATE = re.compile(r"\bCREATE\s+(?:TEMP(?:ORARY)?\s+|VIRTUAL\s+)?(TABLE|VIEW)\s+(?:IF\s+NOT\s+EXISTS\s+)?"
                     r"([`\"\[]?[\w.]+[`\"\]]?)", re.I)
_CONSTRAINT = {"primary", "foreign", "unique", "check", "constraint", "key", "index"}


def _sql(text, ctx):
    code, comments = _sql_strip(text)
    nl = [m.start() for m in re.finditer("\n", text)]
    import bisect

    def line_of(p):
        return bisect.bisect_right(nl, p - 1) + 1 if p > 0 else 1
    cblocks = []
    for a, b in comments:
        sl, el = line_of(a), line_of(max(a, b - 1))
        if cblocks and cblocks[-1][1] == sl - 1 and text[a:a + 2] == "--":
            cblocks[-1] = (cblocks[-1][0], el, cblocks[-1][2] + "\n" + text[a:b])
        else:
            cblocks.append((sl, el, text[a:b]))
    by_end = {el: (sl, raw) for sl, el, raw in cblocks}
    syms = []
    for m in _CREATE.finditer(code):
        name = m.group(2).strip('`"[]')
        line = line_of(m.start())
        members = {}
        end_pos = code.find(";", m.end())
        end_pos = len(code) if end_pos < 0 else end_pos
        o = code.find("(", m.end())
        if m.group(1).upper() == "TABLE" and 0 <= o < end_pos:
            depth, j = 0, o
            while j < len(code):
                if code[j] == "(":
                    depth += 1
                elif code[j] == ")":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            inner = code[o + 1:j]
            parts, cur, d = [], "", 0
            for ch in inner:
                if ch == "(":
                    d += 1
                elif ch == ")":
                    d -= 1
                if ch == "," and d == 0:
                    parts.append(cur)
                    cur = ""
                    continue
                cur += ch
            parts.append(cur)
            for p in parts:
                w = p.split()
                if not w or w[0].lower() in _CONSTRAINT:
                    continue
                members[w[0].strip('`"[]')] = w[1] if len(w) > 1 else ""
        sig = " ".join(code[m.start():(o if 0 <= o < end_pos else end_pos)].split())
        s = symbol(name, name, "table", line, line_of(end_pos), sig=sig, pub=True, members=members,
                   sig_hash=h12(sig.replace(name, "", 1)), body_hash=h12(" ".join(code[m.start():end_pos].split())),
                   words=sorted(members)[:200])
        blk = by_end.get(line - 1)
        if blk:
            s["doc"] = docparse.parse_block(blk[1].replace("--", "//", ), "line", blk[0])
        syms.append(s)
    texts = [text[a:b] for a, b in comments]
    return {"symbols": syms, "_strings": [], "_texts": texts}


# ---------------------------------------------------------------------------------------
# shell
# ---------------------------------------------------------------------------------------

_SH_FN = re.compile(r"^\s*(?:function\s+([\w:.-]+)\s*(?:\(\s*\))?|([\w:.-]+)\s*\(\s*\))\s*\{?\s*(?:#.*)?$")


def _shell(text, ctx):
    lines = text.split("\n")
    syms = []
    texts = []
    for i, ln in enumerate(lines, 1):
        if ln.lstrip().startswith("#"):
            texts.append(ln)
        m = _SH_FN.match(ln)
        if not m:
            continue
        name = m.group(1) or m.group(2)
        end = i
        ind = len(ln) - len(ln.lstrip())
        for j in range(i, len(lines)):
            s2 = lines[j]
            if s2.strip() == "}" and len(s2) - len(s2.lstrip()) <= ind:
                end = j + 1
                break
        sig = f"{name}()"
        body = "\x1f".join(" ".join(x.split("#")[0].split()) for x in lines[i:end - 1])
        s = symbol(name, name, "function", i, end, sig=sig, pub=not name.startswith("_"), sig_hash=h12("()"),
                   body_hash=h12(body))
        doc = []
        k = i - 2
        while k >= 0 and lines[k].lstrip().startswith("#") and not lines[k].startswith("#!"):
            doc.insert(0, lines[k].lstrip()[1:])
            k -= 1
        if doc:
            s["doc"] = docparse.parse_block("\n".join("// " + d.strip() for d in doc), "line", k + 2)
        syms.append(s)
    return {"symbols": syms, "_strings": [], "_texts": texts}


# ---------------------------------------------------------------------------------------
# Go
# ---------------------------------------------------------------------------------------

class _Go(_Base):
    dialect = "go"
    doc_name = "godoc"
    kw = {"if", "for", "switch", "select", "return", "func", "go", "defer", "range", "case", "map", "chan",
          "struct", "interface", "type", "var", "const", "package", "import", "else", "default", "break",
          "continue", "goto", "fallthrough"}

    def style_of(self, raw):
        return "godoc" if raw.lstrip().startswith("//") else doc_style(raw, "line", "godoc")

    def run(self):
        toks = self.toks
        n = len(toks)
        i = 0
        while i < n:
            t = toks[i].t
            if t == "package" and i + 1 < n:
                blk = self.docs.leading(toks[i].line, toks[i].pos)
                if blk:
                    blk["used"] = True
                    self.file_doc = docparse.parse_block(blk["raw"], "godoc", blk["sl"])
                i += 2
                continue
            if t == "import":
                i = self.imp(i)
                continue
            if t == "func":
                i = self.func(i)
                continue
            if t == "type":
                i = self.typ(i)
                continue
            if t in ("const", "var") and i + 1 < n:
                i = self.consts(i, t)
                continue
            i += 1
        return self.result()

    def imp(self, i):
        toks = self.toks
        line = toks[i].line
        if self.t(i + 1) == "(":
            c = self.close(i + 1)
            k = i + 2
            while k < c:
                alias = None
                if toks[k].t != "" and not toks[k].t.startswith('"'):
                    alias = toks[k].t
                    k += 1
                if k < c and toks[k].t.startswith('"'):
                    self.imports.append({"target": self.lit(k), "names": [], "alias": alias, "line": toks[k].line,
                                         "kind": "import", "level": 0, "system": "." not in (self.lit(k) or "").split("/")[0]})
                k += 1
            return c + 1
        k = i + 1
        alias = None
        if not self.t(k).startswith('"'):
            alias = self.t(k)
            k += 1
        if self.t(k).startswith('"'):
            tgt = self.lit(k)
            self.imports.append({"target": tgt, "names": [], "alias": alias, "line": line, "kind": "import",
                                 "level": 0, "system": "." not in tgt.split("/")[0]})
        return k + 1

    def func(self, i):
        toks = self.toks
        k = i + 1
        recv_type = None
        if self.t(k) == "(":
            rc = self.close(k)
            ids = [toks[x].t for x in range(k + 1, rc) if is_ident(toks[x].t)]
            recv_type = ids[-1] if ids else None
            k = rc + 1
        if not is_ident(self.t(k)):
            return k
        name = self.t(k)
        k += 1
        if self.t(k) == "[":
            k = self.close(k) + 1
        if self.t(k) != "(":
            return k
        pc = self.close(k)
        j = pc + 1
        while j < len(toks) and toks[j].t not in ("{",) and toks[j].line == toks[pc].line:
            if toks[j].t == "(":
                j = self.close(j) + 1
                continue
            j += 1
        names, ar = self.params(k, pc, name_first=True)
        qual = f"{recv_type}.{name}" if recv_type else name
        sig = self.text_of(i, j)
        if self.t(j) != "{":
            self.sym(i, name, qual, "method" if recv_type else "function", j - 1, sig, params=names, arity=ar,
                     decl=True, pub=name[:1].isupper(), parent=recv_type, body_hash=h12(""))
            return j
        bc = self.close(j)
        self.sym(i, name, qual, "method" if recv_type else "function", bc, sig, params=names, arity=ar,
                 pub=name[:1].isupper(), parent=recv_type, body_hash=hash_tokens(self.lx, toks, j, bc + 1),
                 words=words(toks, j + 1, bc, self.kw))
        self.bare_calls(j, bc, qual)
        return bc + 1

    def typ(self, i):
        toks = self.toks
        if self.t(i + 1) == "(":
            c = self.close(i + 1)
            k = i + 2
            while k < c:
                if is_ident(toks[k].t) and toks[k - 1].line < toks[k].line:
                    k = self.one_type(k, k, c)
                    continue
                k += 1
            return c + 1
        if is_ident(self.t(i + 1)):
            return self.one_type(i, i + 1, len(toks))
        return i + 1

    def one_type(self, start, k, lim):
        toks = self.toks
        name = toks[k].t
        j = k + 1
        if self.t(j) == "[":
            j = self.close(j) + 1
        if self.t(j) == "=":
            j += 1
        kind = "type"
        if self.t(j) == "struct":
            kind = "struct"
        elif self.t(j) == "interface":
            kind = "interface"
        if kind != "type" and self.t(j + 1) == "{":
            o = j + 1
            c = self.close(o)
            s = self.sym(start, name, name, kind, c, f"type {name} {self.t(j)}", pub=name[:1].isupper(),
                         body_hash=hash_tokens(self.lx, toks, o, c + 1), words=words(toks, o + 1, c, self.kw))
            x = o + 1
            while x < c:
                if is_ident(toks[x].t) and (toks[x - 1].line < toks[x].line or toks[x - 1].t in ("{", ";")):
                    y = x
                    while y < c and toks[y].line == toks[x].line:
                        y += 1
                    seg = [toks[z].t for z in range(x, y)]
                    if kind == "struct":
                        if len(seg) == 1 or (len(seg) >= 2 and seg[1].startswith('"')):
                            s["bases"].append(seg[0])
                        else:
                            names = [seg[0]]
                            z = 1
                            while z + 1 < len(seg) and seg[z] == ",":
                                names.append(seg[z + 1])
                                z += 2
                            ty = "".join(w for w in seg[z:] if not w.startswith('"'))
                            for nm in names:
                                s["members"][nm] = ty
                    else:
                        s["members"][seg[0]] = ""
                    x = y
                    continue
                x += 1
            return c + 1
        e = j
        while e < lim and toks[e].line == toks[k].line:
            e += 1
        self.sym(start, name, name, "type", e - 1, self.text_of(start, e), pub=name[:1].isupper(),
                 body_hash=hash_tokens(self.lx, toks, j, e))
        return e

    def consts(self, i, kw):
        toks = self.toks
        if self.t(i + 1) == "(":
            c = self.close(i + 1)
            if kw == "const":
                k = i + 2
                while k < c:
                    if is_ident(toks[k].t) and toks[k - 1].line < toks[k].line:
                        nm = toks[k].t
                        self.sym(k, nm, nm, "const", k, nm, pub=nm[:1].isupper(), body_hash=h12(nm))
                    k += 1
            return c + 1
        if kw == "const" and is_ident(self.t(i + 1)):
            nm = self.t(i + 1)
            e = i + 1
            while e < len(toks) and toks[e].line == toks[i].line:
                e += 1
            self.sym(i, nm, nm, "const", e - 1, self.text_of(i, e), pub=nm[:1].isupper(),
                     body_hash=hash_tokens(self.lx, toks, i, e))
            return e
        return i + 1


# ---------------------------------------------------------------------------------------
# Rust
# ---------------------------------------------------------------------------------------

class _Rust(_Base):
    dialect = "rust"
    doc_name = "rustdoc"
    kw = {"if", "while", "for", "loop", "match", "return", "fn", "let", "mut", "impl", "struct", "enum",
          "trait", "mod", "use", "pub", "where", "as", "in", "move", "async", "await", "unsafe", "dyn",
          "ref", "box", "else", "break", "continue", "crate", "super", "self", "Self", "type", "const",
          "static", "extern"}

    def style_of(self, raw):
        s = raw.lstrip()
        return "rustdoc" if s.startswith(("///", "/**")) else "line"

    def run(self):
        # inner docs at the top of the file
        inner = [b for b in self.docs.blocks if b["raw"].lstrip().startswith(("//!", "/*!"))]
        if inner:
            b0 = inner[0]
            b0["used"] = True
            self.file_doc = docparse.parse_block(b0["raw"], "rustdoc", b0["sl"])
        for b in self.docs.blocks:
            if b["raw"].lstrip().startswith(("//!", "/*!")):
                b["used"] = True
        self.items(0, len(self.toks), [], None, None, False)
        return self.result()

    def skip_attrs(self, k, lim):
        while k < lim and self.t(k) == "#" and self.t(k + 1) in ("[", "!"):
            k = self.close(k + 1 if self.t(k + 1) == "[" else k + 2) + 1
        return k

    def items(self, a, b, path, impl_type, trait, in_trait):
        toks = self.toks
        k = a
        while k < b:
            start = k
            k = self.skip_attrs(k, b)
            if k >= b:
                break
            if k > start:
                start = start  # docs attach above attributes
            pub = False
            if self.t(k) == "pub":
                pub = True
                k += 1
                if self.t(k) == "(":
                    k = self.close(k) + 1
            while self.t(k) in ("async", "const", "unsafe", "default", "extern") and self.t(k + 1) not in ("{", "=", ":"):
                if self.t(k) == "const" and is_ident(self.t(k + 1)) and self.t(k + 1) != "fn":
                    break
                k += 1
                if self.t(k).startswith('"'):
                    k += 1
            t = self.t(k)
            if t == "fn" and is_ident(self.t(k + 1)):
                k = self.fn(start, k, b, path, impl_type, trait, in_trait, pub)
                continue
            if t in ("struct", "enum", "union", "trait") and is_ident(self.t(k + 1)):
                k = self.adt(start, k, b, path, pub)
                continue
            if t == "impl":
                k = self.impl(start, k, b, path)
                continue
            if t == "mod" and is_ident(self.t(k + 1)):
                if self.t(k + 2) == "{":
                    c = self.close(k + 2)
                    self.items(k + 3, c, path + [self.t(k + 1)], None, None, False)
                    k = c + 1
                else:
                    self.imports.append({"target": self.t(k + 1), "names": [], "alias": None, "line": toks[k].line,
                                         "kind": "mod", "level": 0, "system": False})
                    k += 3
                continue
            if t == "use":
                k = self.use(k, b)
                continue
            if t == "extern" and self.t(k + 1) == "crate":
                self.imports.append({"target": self.t(k + 2), "names": [], "alias": None, "line": toks[k].line,
                                     "kind": "crate", "level": 0, "system": True})
                k += 3
                continue
            if t in ("const", "static") and is_ident(self.t(k + 1)):
                e = k
                while e < b and self.t(e) != ";":
                    if self.t(e) in ("(", "[", "{"):
                        e = self.close(e)
                    e += 1
                nm = self.t(k + 1) if self.t(k + 1) != "mut" else self.t(k + 2)
                qual = "::".join(path + ([impl_type] if impl_type else []) + [nm])
                self.sym(start, nm, qual, "const", e, self.text_of(k, e), pub=pub, parent=impl_type,
                         body_hash=hash_tokens(self.lx, toks, k, e))
                k = e + 1
                continue
            if t == "type" and is_ident(self.t(k + 1)):
                e = k
                while e < b and self.t(e) != ";":
                    e += 1
                nm = self.t(k + 1)
                self.sym(start, nm, "::".join(path + [nm]), "type", e, self.text_of(k, e), pub=pub,
                         body_hash=hash_tokens(self.lx, toks, k, e))
                k = e + 1
                continue
            if t == "macro_rules" and self.t(k + 1) == "!" and is_ident(self.t(k + 2)):
                o = k + 3
                c = self.close(o) if self.t(o) in ("{", "(", "[") else o
                nm = self.t(k + 2)
                self.sym(start, nm, "::".join(path + [nm]), "macro", c, f"macro_rules! {nm}", pub=pub,
                         body_hash=hash_tokens(self.lx, toks, o, c + 1))
                k = c + 1
                continue
            if t in ("{", "(", "["):
                k = self.close(k) + 1
                continue
            k += 1

    def fn(self, start, k, b, path, impl_type, trait, in_trait, pub):
        toks = self.toks
        name = self.t(k + 1)
        j = k + 2
        if self.t(j) == "<":
            d = 0
            while j < b:
                if self.t(j) == "<":
                    d += 1
                elif self.t(j) == ">":
                    d -= 1
                    if d == 0:
                        j += 1
                        break
                j += 1
        if self.t(j) != "(":
            return j
        pc = self.close(j)
        names = []
        for g in self._groups(j, pc):
            g = [x for x in g if x not in ("mut", "&", "'")]
            if g and is_ident(g[0]) and g[0] != "self" and ":" in g:
                names.append(g[0])
        ar = len(self._groups(j, pc))
        e = pc + 1
        while e < b and self.t(e) not in ("{", ";"):
            e += 1
        sig = self.text_of(k, e)
        qual = "::".join(path + ([impl_type] if impl_type else []) + [name])
        kind = "method" if impl_type else "function"
        is_pub = pub or bool(in_trait) or bool(trait)
        if self.t(e) == ";":
            self.sym(start, name, qual, kind, e, sig, params=names, arity=ar, decl=True, pub=is_pub,
                     parent=impl_type, virtual=in_trait, pure=in_trait, body_hash=h12(""))
            return e + 1
        bc = self.close(e)
        self.sym(start, name, qual, kind, bc, sig, params=names, arity=ar, pub=is_pub, parent=impl_type,
                 virtual=in_trait, override=bool(trait), body_hash=hash_tokens(self.lx, toks, e, bc + 1),
                 words=words(toks, e + 1, bc, self.kw))
        self.bare_calls(e, bc, qual)
        return bc + 1

    def _groups(self, o, c):
        groups, cur, depth = [], [], 0
        for x in range(o + 1, c):
            t = self.t(x)
            if t in ("(", "[", "{", "<"):
                depth += 1
            elif t in (")", "]", "}", ">"):
                depth -= 1
            if t == "," and depth == 0:
                groups.append(cur)
                cur = []
                continue
            cur.append(t)
        if cur:
            groups.append(cur)
        return groups

    def adt(self, start, k, b, path, pub):
        toks = self.toks
        kw, name = self.t(k), self.t(k + 1)
        j = k + 2
        while j < b and self.t(j) not in ("{", ";", "("):
            j += 1
        kind = {"struct": "struct", "union": "struct", "enum": "enum", "trait": "interface"}[kw]
        qual = "::".join(path + [name])
        sig = self.text_of(k, j)
        if self.t(j) == ";":
            self.sym(start, name, qual, kind, j, sig, pub=pub, body_hash=h12(""))
            return j + 1
        c = self.close(j)
        s = self.sym(start, name, qual, kind, c, sig, pub=pub, body_hash=hash_tokens(self.lx, toks, j, c + 1),
                     words=words(toks, j + 1, c, self.kw))
        if kw == "trait":
            n0 = len(self.syms)
            self.items(j + 1, c, path, name, None, True)
            del n0
        elif kw == "struct" and self.t(j) == "{":
            for g in self._groups(j, c):
                g = [x for x in g if x not in ("pub",)]
                if self.t(j) == "{" and len(g) >= 3 and g[1] == ":":
                    s["members"][g[0]] = "".join(g[2:])
        e = c + 1
        if self.t(e) == ";":
            e += 1
        return e

    def impl(self, start, k, b, path):
        j = k + 1
        if self.t(j) == "<":
            d = 0
            while j < b:
                if self.t(j) == "<":
                    d += 1
                elif self.t(j) == ">":
                    d -= 1
                    if d == 0:
                        j += 1
                        break
                j += 1
        head = []
        while j < b and self.t(j) != "{":
            head.append(self.t(j))
            j += 1
        if self.t(j) != "{":
            return j
        trait = None
        if "for" in head:
            fi = head.index("for")
            trait = "".join(x for x in head[:fi])
            ty = head[fi + 1:]
        else:
            ty = head
        if "where" in ty:
            ty = ty[:ty.index("where")]
        ids = []
        depth = 0
        for x in ty:
            if x == "<":
                depth += 1
            elif x == ">":
                depth -= 1
            elif depth == 0 and is_ident(x) and x not in ("dyn", "mut"):
                ids.append(x)
        tname = ids[-1] if ids else "_"
        c = self.close(j)
        self.items(j + 1, c, path, tname, trait, False)
        return c + 1

    def use(self, k, b):
        toks = self.toks
        e = k
        while e < b and self.t(e) != ";":
            e += 1
        line = toks[k].line
        seg = [self.t(x) for x in range(k + 1, e)]
        if seg and seg[0] == "pub":
            seg = seg[1:]

        def expand(parts, prefix):
            out, i = [], 0
            cur = list(prefix)
            while i < len(parts):
                p = parts[i]
                if p == "{":
                    d, j = 0, i
                    while j < len(parts):
                        if parts[j] == "{":
                            d += 1
                        elif parts[j] == "}":
                            d -= 1
                            if d == 0:
                                break
                        j += 1
                    inner = parts[i + 1:j]
                    groups, g, dd = [], [], 0
                    for x in inner:
                        if x == "{":
                            dd += 1
                        elif x == "}":
                            dd -= 1
                        if x == "," and dd == 0:
                            groups.append(g)
                            g = []
                            continue
                        g.append(x)
                    if g:
                        groups.append(g)
                    for g in groups:
                        out += expand(g, cur)
                    return out
                if p == "::":
                    i += 1
                    continue
                if p == "as" and i + 1 < len(parts):
                    out.append(("::".join(cur), parts[i + 1]))
                    return out
                cur.append(p)
                i += 1
            if cur:
                if cur[-1] == "self":
                    cur = cur[:-1]
                out.append(("::".join(cur), None))
            return out
        for tgt, alias in expand(seg, []):
            root = tgt.split("::")[0]
            self.imports.append({"target": tgt, "names": [], "alias": alias, "line": line, "kind": "use", "level": 0,
                                 "system": root not in ("crate", "self", "super")})
        return e + 1


# ---------------------------------------------------------------------------------------
# Java / Kotlin / C# / Swift
# ---------------------------------------------------------------------------------------

class _Clike(_Base):
    dialect = "clike"
    doc_name = "doxygen"
    kw = {"if", "for", "while", "switch", "catch", "return", "new", "throw", "synchronized", "using", "lock",
          "foreach", "when", "fun", "func", "init", "guard", "sizeof", "typeof", "nameof", "default", "super",
          "this", "else", "do", "try", "is", "as", "in", "assert", "yield", "await", "repeat", "defer"}
    MODS = {"public", "protected", "private", "internal", "static", "final", "abstract", "sealed", "open",
            "override", "virtual", "async", "readonly", "partial", "data", "inline", "suspend", "fileprivate",
            "mutating", "extern", "unsafe", "new", "const", "native", "synchronized", "transient", "volatile",
            "strictfp", "default", "lateinit", "operator", "infix", "tailrec", "external", "annotation",
            "enum", "inner", "value", "companion", "convenience", "required", "dynamic", "lazy", "weak",
            "unowned", "nonisolated", "actor", "public(set)", "expect", "actual", "noinline", "crossinline"}
    TYPES = {"class", "interface", "struct", "record", "object", "protocol", "extension", "enum", "trait"}

    def __init__(self, text, ctx):
        super().__init__(text, ctx)
        ext = ctx.get("rel", "").rsplit(".", 1)[-1].lower()
        self.ext = ext
        self.default_pub = ext in ("kt", "swift")

    def run(self):
        self.body(0, len(self.toks), [], None)
        return self.result()

    def visible(self, mods):
        if self.default_pub:
            return not ({"private", "internal", "fileprivate"} & set(mods))
        return bool({"public", "protected"} & set(mods))

    def body(self, a, b, path, cls):
        toks = self.toks
        k = a
        while k < b:
            t = toks[k].t
            start = k
            if t in ("package", "import", "using") and cls is None and not (t == "using" and self.t(k + 1) == "("):
                e = k + 1
                while e < b and self.t(e) != ";" and toks[e].line == toks[k].line:
                    e += 1
                parts = [self.t(x) for x in range(k + 1, e) if self.t(x) not in ("static",)]
                tgt = "".join(parts)
                if t == "package":
                    path = tgt.split(".") if tgt else []
                else:
                    self.imports.append({"target": tgt, "names": [], "alias": None, "line": toks[k].line,
                                         "kind": t, "level": 0, "system": False})
                k = e + 1 if self.t(e) == ";" else e
                continue
            if t == "namespace" and cls is None:
                e = k + 1
                parts = []
                while e < b and self.t(e) not in ("{", ";"):
                    parts.append(self.t(e))
                    e += 1
                ns = "".join(parts).split(".")
                if self.t(e) == "{":
                    c = self.close(e)
                    self.body(e + 1, c, path + ns, None)
                    k = c + 1
                else:
                    path = path + ns
                    k = e + 1
                continue
            # annotations / attributes
            if t == "@" and is_ident(self.t(k + 1)):
                k += 2
                while self.t(k) == "." and is_ident(self.t(k + 1)):
                    k += 2
                if self.t(k) == "(":
                    k = self.close(k) + 1
                continue
            if t == "[" and cls is not None or (t == "[" and toks[k - 1].line < toks[k].line if k else t == "["):
                c = self.close(k)
                if c > k and all(is_ident(self.t(x)) or self.t(x) in (",", "(", ")", ".", "=") or self.t(x).startswith('"') for x in range(k + 1, c)):
                    k = c + 1
                    continue
            mods = []
            while self.t(k) in self.MODS and not (self.t(k) == "enum" and self.t(k + 1) in ("class", "struct")) \
                    and not (self.t(k) in ("enum",) and is_ident(self.t(k + 1)) and self.t(k + 2) in ("{", ":", "(")):
                mods.append(self.t(k))
                k += 1
            t = self.t(k)
            if t == "enum" and self.t(k + 1) == "class":
                k += 1
                t = "class"
            if t in self.TYPES and is_ident(self.t(k + 1)):
                k = self.typedecl(start, k, b, path, cls, mods)
                continue
            if t in ("fun", "func") and (is_ident(self.t(k + 1)) or self.t(k + 1) == "<"):
                k = self.method(start, k + 1, b, path, cls, mods, kw_fn=True)
                continue
            if t == "init" and self.t(k + 1) in ("(", "?", "<"):
                k = self.method(start, k, b, path, cls, mods, kw_fn=False, ctor=True)
                continue
            if cls is not None and is_ident(t):
                # Java/C#: [Type] name ( … ) { … }
                j = k
                while j < b and self.t(j) not in ("(", ";", "{", "=", "}") and toks[j].line == toks[k].line:
                    if self.t(j) == "<":
                        d = 0
                        while j < b:
                            if self.t(j) == "<":
                                d += 1
                            elif self.t(j) == ">":
                                d -= 1
                                if d == 0:
                                    break
                            j += 1
                    j += 1
                if self.t(j) == "(" and is_ident(self.t(j - 1)) and self.t(j - 1) not in self.kw:
                    k = self.method(start, j - 1, b, path, cls, mods, kw_fn=False,
                                    ctor=self.t(j - 1) == cls["name"])
                    continue
                if self.t(j) in (";", "=") and j - 1 > k and is_ident(self.t(j - 1)):
                    if not self.default_pub:
                        cls["members"][self.t(j - 1)] = "".join(self.t(x) for x in range(k, j - 1))
                    e = j
                    while e < b and self.t(e) not in (";",) and not (toks[e].line > toks[j].line and self.t(e - 1) not in ("=", ",", "+", ".")):
                        if self.t(e) in ("(", "[", "{"):
                            e = self.close(e)
                        e += 1
                    k = e + 1 if self.t(e) == ";" else e
                    continue
            if t in ("val", "var", "let") and is_ident(self.t(k + 1)):
                nm = self.t(k + 1)
                ty = ""
                if self.t(k + 2) == ":":
                    x = k + 3
                    parts = []
                    while x < b and self.t(x) not in ("=", ";", "{") and toks[x].line == toks[k].line:
                        parts.append(self.t(x))
                        x += 1
                    ty = "".join(parts)
                if cls is not None:
                    cls["members"][nm] = ty
                k += 2
                continue
            if t in ("{", "(", "["):
                k = self.close(k) + 1
                continue
            k += 1

    def typedecl(self, start, k, b, path, cls, mods):
        toks = self.toks
        kw, name = self.t(k), self.t(k + 1)
        j = k + 2
        bases = []
        while j < b and self.t(j) not in ("{", ";") and not (toks[j].line > toks[k].line + 3):
            t = self.t(j)
            if t == "(":
                j = self.close(j) + 1
                continue
            if t == "<":
                d = 0
                while j < b:
                    if self.t(j) == "<":
                        d += 1
                    elif self.t(j) == ">":
                        d -= 1
                        if d == 0:
                            break
                    j += 1
                j += 1
                continue
            if is_ident(t) and t not in ("extends", "implements", "where") and self.t(j - 1) in (":", ",", "extends", "implements"):
                bases.append(t)
            j += 1
        kind = {"class": "class", "record": "class", "object": "class", "struct": "struct",
                "interface": "interface", "protocol": "interface", "trait": "interface", "enum": "enum",
                "extension": "class"}[kw]
        prefix = path + ([cls["qual"]] if cls else [])
        qual = ".".join(prefix + [name]) if not cls else f"{cls['qual']}.{name}"
        sig = self.text_of(k, j)
        if self.t(j) != "{":
            self.sym(start, name, qual, kind, j, sig, pub=self.visible(mods), bases=bases,
                     parent=cls["qual"] if cls else None, body_hash=h12(""))
            return j + 1
        c = self.close(j)
        s = self.sym(start, name, qual, kind, c, sig, pub=self.visible(mods), bases=bases,
                     parent=cls["qual"] if cls else None, body_hash=hash_tokens(self.lx, toks, j, c + 1),
                     words=words(toks, j + 1, c, self.kw))
        s["_iface"] = kind == "interface"
        self.body(j + 1, c, path, s)
        s.pop("_iface", None)
        return c + 1

    def method(self, start, k, b, path, cls, mods, kw_fn, ctor=False):
        toks = self.toks
        j = k
        if self.t(j) == "<":
            d = 0
            while j < b:
                if self.t(j) == "<":
                    d += 1
                elif self.t(j) == ">":
                    d -= 1
                    if d == 0:
                        j += 1
                        break
                j += 1
        # Kotlin extension receivers: fun Type.name(
        while is_ident(self.t(j)) and self.t(j + 1) == ".":
            j += 2
        name = self.t(j)
        if name == "?":
            name = "init"
        o = j + 1
        if self.t(o) == "?":
            o += 1
        if self.t(o) == "<":
            while o < b and self.t(o) != "(":
                o += 1
        if self.t(o) != "(":
            return o
        pc = self.close(o)
        names, ar = self.params(o, pc, name_first=self.ext in ("kt", "swift"))
        e = pc + 1
        while e < b and self.t(e) not in ("{", ";", "=", "}") and not (toks[e].line > toks[pc].line + 2):
            if self.t(e) in ("(",):
                e = self.close(e)
            e += 1
        qual = f"{cls['qual']}.{name}" if cls else ".".join(path + [name])
        kind = "ctor" if ctor else ("method" if cls else "function")
        sig = self.text_of(start, e)
        iface = bool(cls and cls.get("_iface"))
        pub = self.visible(mods) or (iface and not ({"private"} & set(mods)))
        common = dict(params=names, arity=ar, pub=pub, parent=cls["qual"] if cls else None,
                      static="static" in mods, override="override" in mods,
                      virtual="virtual" in mods or "abstract" in mods or "override" in mods or iface,
                      pure="abstract" in mods)
        if self.t(e) == "{":
            bc = self.close(e)
            self.sym(start, name, qual, kind, bc, sig, body_hash=hash_tokens(self.lx, toks, e, bc + 1),
                     words=words(toks, e + 1, bc, self.kw), **common)
            self.bare_calls(e, bc, qual)
            return bc + 1
        if self.t(e) == "=":
            x = e + 1
            while x < b and toks[x].line == toks[e].line and self.t(x) != ";":
                if self.t(x) in ("(", "[", "{"):
                    x = self.close(x)
                x += 1
            self.sym(start, name, qual, kind, x - 1, sig, body_hash=hash_tokens(self.lx, toks, e, x), **common)
            self.bare_calls(e, x, qual)
            return x
        common["pure"] = common["pure"] or iface
        self.sym(start, name, qual, kind, e, sig, decl=True, body_hash=h12(""), **common)
        return e + 1 if self.t(e) == ";" else e
