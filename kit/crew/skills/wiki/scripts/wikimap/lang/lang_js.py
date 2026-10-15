"""JS/TS adapter: lexer (regex vs division, template `${}` stack, JSX as text) + token patterns.

Pass 1 finds symbols and their body token ranges; pass 2 scans every token once for calls
and attributes each to the innermost owning symbol (module-level code gets `from: null`).
"""
from __future__ import annotations

import re

from . import docparse
from .lex import src_text, DocIndex, Lexed, brackets, h12, hash_tokens, is_ident, symbol, tokenize, words

KW = {"if", "for", "while", "switch", "catch", "function", "return", "typeof", "instanceof", "in", "of",
      "new", "delete", "void", "throw", "case", "do", "else", "yield", "await", "class", "const", "let",
      "var", "import", "export", "default", "extends", "super", "this", "try", "finally", "with", "async",
      "static", "get", "set", "true", "false", "null", "undefined", "interface", "type", "enum",
      "namespace", "declare", "abstract", "implements", "public", "private", "protected", "readonly",
      "keyof", "as", "from", "is", "infer", "satisfies", "break", "continue", "debugger"}
CALL_SKIP = {"if", "for", "while", "switch", "catch", "function", "return", "typeof", "instanceof",
             "void", "delete", "throw", "case", "with", "super", "import", "require", "await", "yield",
             "in", "of", "else", "do", "new", "class", "constructor", "get", "set", "async", "static",
             "keyof", "as", "satisfies"}
MODS = {"static", "async", "get", "set", "public", "private", "protected", "readonly", "abstract",
        "override", "declare", "accessor", "*"}
TEST_FNS = {"test", "it"}
NOT_TARGS = {"&&", "||", "??", "?", "==", "===", "!=", "!==", "<=", ">=", "=", "+", "-", "/", "%", "!", "^", "return"}


# tokens after which `function`/`class` starts an expression, not a declaration
EXPR_PREV = {"(", ",", "=", ":", "?", "[", "return", "&&", "||", "??", "!", "=>", "yield", "await", "new", "+", "typeof", "void"}

class _JS:
    def __init__(self, lx: Lexed, ctx: dict, ts: bool):
        self.lx = lx
        self.ctx = ctx
        self.ts = ts
        self.toks = tokenize(lx)
        self.match, self.balanced = brackets(self.toks)
        self.docs = DocIndex(lx)
        self.syms: list[dict] = []
        self.owners: list[tuple[int, int, str]] = []  # token range -> owner qual
        self.calls: list[dict] = []
        self.imports: list[dict] = []
        self.strings: list[dict] = []
        self.exported: set[str] = set()
        self.default_export: str | None = None   # qual of the `export default` symbol, "" for an expression
        self.decl_names: set[int] = set()  # token indexes that are definition names, not calls
        self.file_doc = None

    def t(self, i):
        return self.toks[i].t if 0 <= i < len(self.toks) else ""

    def close(self, i):
        return self.match.get(i, len(self.toks) - 1)

    def lit(self, i):
        tk = self.toks[i]
        return self.lx.literal(tk.pos) if tk.t.startswith('"') else None

    def text_of(self, a, b):
        return src_text(self.lx, self.toks, a, b)

    def attach_doc(self, i):
        tk = self.toks[i]
        blk = self.docs.leading(tk.line, tk.pos)
        if not blk or blk["used"]:
            return None
        blk["used"] = True
        raw = blk["raw"]
        style = "jsdoc" if raw.lstrip().startswith("/**") else "line"
        return docparse.parse_block(raw, style, blk["sl"])

    # -- pass 1 ------------------------------------------------------------------------
    def run(self):
        for blk in self.docs.blocks:
            if re.search(r"@(file|fileoverview|module|overview)\b", blk["raw"]):
                blk["used"] = True
                self.file_doc = docparse.parse_block(blk["raw"], "jsdoc", blk["sl"])
                break
        self.block(0, len(self.toks), prefix="", parent=None)
        # `export { a, b as c }` lists and CommonJS exports
        for s in self.syms:
            top = s["qual"].split(".")[0]
            if top in self.exported and s["parent"] is None:
                s["pub"] = True
        for s in self.syms:
            if s["parent"] is not None and not s["name"].startswith("#") and not s.get("_private"):
                par = next((x for x in self.syms if x["qual"] == s["parent"]), None)
                if par is not None and par["pub"]:
                    s["pub"] = True
        self.scan_calls()

    def block(self, a, b, prefix, parent, exported_ns=False):
        """Statements in token range a..b (module body or namespace body)."""
        toks = self.toks
        i = a
        while i < b:
            t = toks[i].t
            start = i
            exp = False
            dflt = False
            if t == "export":
                exp = True
                i += 1
                if self.t(i) == "default":
                    dflt = True
                    i += 1
                if self.t(i) == "{":
                    c = self.close(i)
                    names = self.export_list(i, c)
                    j = c + 1
                    if self.t(j) == "from" and self.t(j + 1).startswith('"'):
                        tgt = self.lit(j + 1)
                        for orig, alias in names:
                            self.add_import(tgt, [orig], alias if alias != orig else None, toks[start].line, "reexport")
                        i = j + 2
                    else:
                        for orig, alias in names:
                            self.exported.add(orig)
                        i = c + 1
                    continue
                if self.t(i) == "*":
                    j = i + 1
                    alias = None
                    if self.t(j) == "as":
                        alias = self.t(j + 1)
                        j += 2
                    if self.t(j) == "from" and self.t(j + 1).startswith('"'):
                        self.add_import(self.lit(j + 1), ["*"], alias, toks[start].line, "reexport")
                        i = j + 2
                        continue
                if self.t(i) == "=":  # TS `export = X`
                    i += 1
                    continue
            if self.t(i) == "declare":
                i += 1
            t = self.t(i)
            if t == "import" and self.t(i + 1) not in ("(", "."):
                i = self.import_stmt(i, b)
                continue
            if t == "async" and self.t(i + 1) == "function":
                i += 1
                t = "function"
            if t in ("function", "class", "abstract") and not exp and self.t(start - 1) in EXPR_PREV:
                # function/class expression (callback argument, operand): not a declaration
                i += 1
                continue
            if t == "function":
                i = self.function(start, i, b, prefix, parent, exp, dflt)
                continue
            if t == "abstract" and self.t(i + 1) == "class":
                i += 1
                t = "class"
            if t == "class":
                i = self.klass(start, i, b, prefix, parent, exp, dflt)
                continue
            if t in ("const", "let", "var"):
                i = self.variable(start, i, b, prefix, parent, exp)
                continue
            if self.ts and t == "interface" and is_ident(self.t(i + 1)):
                i = self.interface(start, i, b, prefix, parent, exp)
                continue
            if self.ts and t == "type" and is_ident(self.t(i + 1)) and self.t(i + 2) in ("=", "<"):
                e = self.stmt_end(i + 2, b)
                self.add_sym(start, i + 1, e, prefix, parent, "type", exp, sig=self.text_of(i, min(e, i + 2)))
                i = e
                continue
            if self.ts and t == "const" and self.t(i + 1) == "enum":
                i += 1
                t = "enum"
            if t == "enum" and is_ident(self.t(i + 1)) and self.t(i + 2) == "{":
                c = self.close(i + 2)
                s = self.add_sym(start, i + 1, c + 1, prefix, parent, "enum", exp, sig=f"enum {self.t(i + 1)}")
                s["members"] = {self.t(k): "" for k in range(i + 3, c) if is_ident(self.t(k)) and self.t(k - 1) in ("{", ",")}
                i = c + 1
                continue
            if self.ts and t in ("namespace", "module") and is_ident(self.t(i + 1)):
                j = i + 1
                while self.t(j + 1) == "." and is_ident(self.t(j + 2)):
                    j += 2
                if self.t(j + 1) == "{":
                    name = "".join(self.t(k) for k in range(i + 1, j + 1))
                    c = self.close(j + 1)
                    s = self.add_sym(start, i + 1, c + 1, prefix, parent, "namespace", exp, sig=f"namespace {name}",
                                     name=name)
                    self.owners.append((j + 1, c, s["qual"]))
                    self.block(j + 2, c, s["qual"] + ".", s["qual"], exp)
                    i = c + 1
                    continue
            if dflt and t not in ("function", "class"):
                # export default <expression>
                if is_ident(t):
                    self.exported.add(t)
                bare = is_ident(t) and (self.t(i + 1) in (";", "") or toks[i + 1].line > toks[i].line)
                self.default_export = t if bare else ""
                i = self.stmt_end(i, b)
                continue
            if t in TEST_FNS and self.t(i + 1) == "(" and self.t(i + 2).startswith('"'):
                self.test_call(i, prefix, parent)
            if t == "module" and self.t(i + 1) == "." and self.t(i + 2) == "exports":
                self.cjs_exports(i + 3, b)
            if t == "exports" and self.t(i + 1) == "." and is_ident(self.t(i + 2)):
                self.exported.add(self.t(i + 2))
            i += 1
            # nested test() calls inside describe() callbacks: keep scanning tokens linearly
        return b

    def export_list(self, o, c, colon=False):
        """`{a, b as c}` → [(a, a), (b, c)]; with colon=True also destructuring `{b: c}` → (b, c)."""
        names, cur = [], []
        for k in range(o + 1, c):
            t = self.t(k)
            if t == ",":
                if cur:
                    names.append(cur)
                cur = []
            elif t != "type":
                cur.append(t)
        if cur:
            names.append(cur)
        out = []
        for g in names:
            if len(g) >= 3 and (g[1] == "as" or (colon and g[1] == ":" and is_ident(g[2]))):
                out.append((g[0], g[2]))
            elif g:
                out.append((g[0], g[0]))
        return out

    def cjs_exports(self, j, b):
        if self.t(j) != "=":
            return
        k = j + 1
        if self.t(k) == "{":
            c = self.close(k)
            for x in range(k + 1, c):
                if is_ident(self.t(x)) and self.t(x - 1) in ("{", ",") and self.t(x + 1) in (",", "}", ":"):
                    self.exported.add(self.t(x + 1 + 1) if self.t(x + 1) == ":" and is_ident(self.t(x + 2)) else self.t(x))
        elif is_ident(self.t(k)):
            self.exported.add(self.t(k))

    def add_import(self, target, names, alias, line, kind):
        if target is None:
            return
        self.imports.append({"target": target, "names": names, "alias": alias, "line": line, "kind": kind,
                             "level": 0, "system": not target.startswith((".", "/"))})

    def import_stmt(self, i, b):
        toks = self.toks
        line = toks[i].line
        j = i + 1
        if self.t(j) == "type" and self.t(j + 1) != "from" and self.t(j + 1) != ",":
            j += 1
        if self.t(j).startswith('"'):
            self.add_import(self.lit(j), [], None, line, "import")
            return j + 1
        # TS `import x = require("m")`
        if is_ident(self.t(j)) and self.t(j + 1) == "=" and self.t(j + 2) == "require":
            if self.t(j + 4).startswith('"'):
                self.add_import(self.lit(j + 4), [], self.t(j), line, "require")
            return self.stmt_end(j, b)
        binds = []
        k = j
        while k < b and self.t(k) != "from" and self.t(k) != ";":
            t = self.t(k)
            if t == "{":
                c = self.close(k)
                for orig, alias in self.export_list(k, c):
                    binds.append(([orig], alias if alias != orig else None))
                k = c + 1
                continue
            if t == "*" and self.t(k + 1) == "as":
                binds.append((["*"], self.t(k + 2)))
                k += 3
                continue
            if is_ident(t) and t != "type":
                binds.append((["default"], t))
            k += 1
        if self.t(k) == "from" and self.t(k + 1).startswith('"'):
            tgt = self.lit(k + 1)
            for names, alias in binds:
                self.add_import(tgt, names, alias, line, "import")
            return k + 2
        return k + 1

    def stmt_end(self, i, b):
        """End of an expression statement starting at i (exclusive token index)."""
        toks = self.toks
        k = i
        cont = {"+", "-", "*", "/", ".", ",", "(", "[", "{", "=", "=>", "?", ":", "&&", "||", "??", "|", "&",
                "<", ">", "==", "===", "!=", "!==", "+=", "-=", "?.", "!", "extends", "keyof", "typeof", "new"}
        while k < b:
            t = toks[k].t
            if t in ("(", "[", "{"):
                k = self.close(k) + 1
                continue
            if t in (";",):
                return k + 1
            if t in (")", "]", "}"):
                return k
            if k + 1 < b and toks[k + 1].line > toks[k].line and t not in cont \
                    and toks[k + 1].t not in (".", "?.", "+", "-", "*", "/", "&&", "||", "??", "?", ":", "|", "&",
                                              "=>", ")", "]", "}", ",", "=", "==", "===", "as", "satisfies"):
                return k + 1
            k += 1
        return b

    def params(self, o, c):
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
            cur.append(k)
        if cur:
            groups.append(cur)
        names, types = [], {}
        for g in groups:
            ts = [self.t(k) for k in g]
            while ts and ts[0] in ("public", "private", "protected", "readonly", "override", "..."):
                ts = ts[1:]
            if not ts or not is_ident(ts[0]) or ts[0] == "this":
                continue
            nm = ts[0]
            names.append(nm)
            if len(ts) > 2 and ts[1] in (":", "?") :
                x = 2 if ts[1] == ":" else 3
                ty = []
                for y in ts[x:]:
                    if y == "=":
                        break
                    ty.append(y)
                if ty:
                    types[nm] = "".join(ty)
        return names, types, len(groups)

    def add_sym(self, start, name_idx, end_idx, prefix, parent, kind, exp, sig="", name=None, **kw):
        name = name or self.t(name_idx)
        qual = prefix + name
        toks = self.toks
        last = toks[min(end_idx, len(toks)) - 1] if end_idx > 0 else toks[start]
        s = symbol(qual, name, kind, toks[start].line, last.line, sig=sig, parent=parent,
                   pub=bool(exp), sig_hash=h12(sig.replace(name, "", 1)),
                   body_hash=hash_tokens(self.lx, toks, start, end_idx), **kw)
        s["doc"] = self.attach_doc(start)
        self.decl_names.add(name_idx)
        self.syms.append(s)
        return s

    def function(self, start, i, b, prefix, parent, exp, dflt):
        j = i + 1
        gen = self.t(j) == "*"
        if gen:
            j += 1
        if is_ident(self.t(j)):
            name_idx, name = j, self.t(j)
            j += 1
        else:
            name_idx, name = i, "default"
        if self.t(j) == "<":
            while j < b and self.t(j) != "(":
                j += 1
        if self.t(j) != "(":
            return j
        c = self.close(j)
        k = c + 1
        while k < b and self.t(k) != "{" and self.t(k) != ";":
            k += 1
        if self.t(k) == ";":  # TS overload signature
            return k + 1
        bc = self.close(k)
        names, types, ar = self.params(j, c)
        sig = self.text_of(i, k)
        s = self.add_sym(start, name_idx, bc + 1, prefix, parent, "function", exp, sig=sig, name=name,
                         params=names, arity=ar)
        if dflt:
            self.default_export = s["qual"]
        s["sig_hash"] = h12(self.text_of(i, k).replace(name, "", 1))
        s["body_hash"] = hash_tokens(self.lx, self.toks, k, bc + 1)
        s["words"] = words(self.toks, k + 1, bc, KW)
        s["_types"] = types
        self.owners.append((k, bc, s["qual"]))
        return bc + 1

    def klass(self, start, i, b, prefix, parent, exp, dflt):
        j = i + 1
        name_idx, name = (j, self.t(j)) if is_ident(self.t(j)) and self.t(j) not in ("extends", "implements") else (i, "default")
        if name_idx == j:
            j += 1
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
        bases = []
        while j < b and self.t(j) != "{":
            if self.t(j) in ("extends", "implements"):
                k = j + 1
                cur = []
                while k < b and self.t(k) not in ("{", "implements"):
                    if self.t(k) == ",":
                        if cur:
                            bases.append("".join(cur))
                        cur = []
                    elif self.t(k) == "<":
                        d = 0
                        while k < b:
                            if self.t(k) == "<":
                                d += 1
                            elif self.t(k) == ">":
                                d -= 1
                                if d == 0:
                                    break
                            k += 1
                    elif self.t(k) == "(":
                        k = self.close(k)
                    else:
                        cur.append(self.t(k))
                    k += 1
                if cur:
                    bases.append("".join(cur))
                j = k
                continue
            j += 1
        if self.t(j) != "{":
            return j
        bc = self.close(j)
        sig = self.text_of(i, j)
        s = self.add_sym(start, name_idx, bc + 1, prefix, parent, "class", exp, sig=sig, name=name, bases=bases)
        if dflt:
            self.default_export = s["qual"]
        self.owners.append((j, bc, s["qual"]))
        n0 = len(self.syms)
        self.class_body(j, bc, s)
        skips = [x["_body"] for x in self.syms[n0:] if x.get("_body")]
        s["body_hash"] = hash_tokens(self.lx, self.toks, j, bc + 1, skip=skips)
        s["words"] = words(self.toks, j + 1, bc, KW)
        return bc + 1

    def class_body(self, o, c, cls):
        toks = self.toks
        k = o + 1
        while k < c:
            t = toks[k].t
            if t in (";", ","):
                k += 1
                continue
            if t == "@":  # decorator
                k += 1
                if is_ident(self.t(k)):
                    k += 1
                    while self.t(k) == "." and is_ident(self.t(k + 1)):
                        k += 2
                if self.t(k) == "(":
                    k = self.close(k) + 1
                continue
            start = k
            mods = []
            while self.t(k) in MODS and self.t(k + 1) not in ("(", "=", ";", ":", "?", "<", "!") and k < c:
                mods.append(self.t(k))
                k += 1
            priv = False
            if self.t(k) == "#":
                priv = True
                k += 1
            name_idx = k
            if self.t(k) == "[":  # computed name
                k = self.close(k) + 1
                name = self.text_of(name_idx, k)
            elif self.t(k).startswith('"'):
                name = self.lit(k) or ""
                k += 1
            else:
                name = self.t(k)
                k += 1
            if priv:
                name = "#" + name
            if self.t(k) == "?" or self.t(k) == "!":
                k += 1
            if self.t(k) == "<":
                while k < c and self.t(k) != "(":
                    k += 1
            if self.t(k) == "(":
                pc = self.close(k)
                j = pc + 1
                while j < c and self.t(j) not in ("{", ";", "}"):
                    j += 1
                names, types, ar = self.params(k, pc)
                kind = "ctor" if name == "constructor" else "method"
                sig = self.text_of(start, j)
                qual = f"{cls['qual']}.{name}"
                is_priv = priv or "private" in mods or "protected" in mods
                if self.t(j) == "{":
                    bc = self.close(j)
                    s = symbol(qual, name, kind, toks[start].line, toks[bc].line, sig=sig, params=names, arity=ar,
                               parent=cls["qual"], static="static" in mods, sig_hash=h12(sig.replace(name, "", 1)),
                               body_hash=hash_tokens(self.lx, toks, j, bc + 1), words=words(toks, j + 1, bc, KW),
                               pure="abstract" in mods, virtual="abstract" in mods, override="override" in mods)
                    s["_body"] = (j, bc)
                    s["_types"] = types
                    s["_private"] = is_priv
                    s["doc"] = self.attach_doc(start)
                    self.decl_names.add(name_idx)
                    self.syms.append(s)
                    self.owners.append((j, bc, qual))
                    if name == "constructor":
                        self.param_props(k, pc, types, cls)
                        self.ctor_members(j, bc, cls, types)
                    k = bc + 1
                else:
                    s = symbol(qual, name, kind, toks[start].line, toks[min(j, c)].line, sig=sig, params=names,
                               arity=ar, parent=cls["qual"], decl=True, pure="abstract" in mods,
                               virtual="abstract" in mods, sig_hash=h12(sig.replace(name, "", 1)), body_hash=h12(""))
                    s["_private"] = is_priv
                    s["doc"] = self.attach_doc(start)
                    self.decl_names.add(name_idx)
                    self.syms.append(s)
                    k = j + 1 if self.t(j) == ";" else j
                continue
            # field
            ty = ""
            if self.t(k) == ":":
                j = k + 1
                tparts = []
                while j < c and self.t(j) not in ("=", ";") and not (toks[j].line > toks[j - 1].line and is_ident(self.t(j)) and self.t(j - 1) not in (":", "|", "&", "<", ",")):
                    if self.t(j) in ("(", "[", "{"):
                        e = self.close(j)
                        tparts.append(self.text_of(j, e + 1))
                        j = e + 1
                        continue
                    tparts.append(self.t(j))
                    j += 1
                ty = "".join(tparts)
                k = j
            if is_ident(name.lstrip("#")):
                cls["members"][name] = ty
            if self.t(k) == "=":
                e = self.stmt_end(k + 1, c)
                # `x = (…) => {…}` arrow fields are methods
                k = e
            continue

    def param_props(self, o, c, types, cls):
        """TS constructor parameter properties (`constructor(private readonly store: Store)`) are fields."""
        depth, head = 0, True
        for k in range(o + 1, c):
            t = self.t(k)
            if t in ("(", "[", "{", "<"):
                depth += 1
            elif t in (")", "]", "}", ">"):
                depth -= 1
            elif t == "," and depth == 0:
                head = True
                continue
            if depth or not head:
                continue
            if t in ("public", "private", "protected", "readonly") and is_ident(self.t(k + 1)):
                nm = self.t(k + 1)
                if nm in ("public", "private", "protected", "readonly", "override"):
                    continue
                if not cls["members"].get(nm):
                    cls["members"][nm] = types.get(nm, "")
                head = False
            elif t not in ("override",):
                head = False

    def ctor_members(self, a, b, cls, ptypes=None):
        for k in range(a, b):
            if self.t(k) == "this" and self.t(k + 1) == "." and is_ident(self.t(k + 2)) and self.t(k + 3) == "=":
                nm = self.t(k + 2)
                ty = ""
                if self.t(k + 4) == "new" and is_ident(self.t(k + 5)):
                    ty = self.t(k + 5)
                elif ptypes and self.t(k + 4) in ptypes and self.t(k + 5) in (";", "}", ""):
                    ty = ptypes[self.t(k + 4)]  # `this.x = p` with a typed ctor param p
                if nm not in cls["members"] or (ty and not cls["members"][nm]):
                    cls["members"][nm] = ty

    def interface(self, start, i, b, prefix, parent, exp):
        j = i + 2
        bases = []
        while j < b and self.t(j) != "{":
            if self.t(j) == "extends":
                k = j + 1
                while k < b and self.t(k) != "{":
                    if is_ident(self.t(k)) and self.t(k - 1) in ("extends", ","):
                        bases.append(self.t(k))
                    k += 1
                j = k
                continue
            j += 1
        if self.t(j) != "{":
            return j
        c = self.close(j)
        s = self.add_sym(start, i + 1, c + 1, prefix, parent, "interface", exp, sig=self.text_of(i, j), bases=bases)
        k = j + 1
        while k < c:
            if is_ident(self.t(k)) and self.t(k - 1) in ("{", ";", ",", "readonly") and self.t(k + 1) in (":", "?", "("):
                nm = self.t(k)
                x = k + 1
                if self.t(x) == "?":
                    x += 1
                ty = []
                if self.t(x) == ":":
                    x += 1
                    while x < c and self.t(x) not in (";", ","):
                        if self.t(x) in ("(", "[", "{"):
                            e = self.close(x)
                            ty.append(self.text_of(x, e + 1))
                            x = e + 1
                            continue
                        if self.toks[x].line > self.toks[x - 1].line and is_ident(self.t(x)) and self.t(x + 1) in (":", "?", "("):
                            break
                        ty.append(self.t(x))
                        x += 1
                elif self.t(x) == "(":
                    ty = ["(" + "…" + ")"]
                    x = self.close(x) + 1
                s["members"][nm] = "".join(ty)
                k = x
                continue
            k += 1
        return c + 1

    def variable(self, start, i, b, prefix, parent, exp):
        toks = self.toks
        j = i + 1
        if not is_ident(self.t(j)):
            # destructuring: `const { a, b } = require("x")`
            if self.t(j) in ("{", "[") :
                c = self.close(j)
                if self.t(c + 1) == "=" and self.t(c + 2) == "require" and self.t(c + 3) == "(" and self.t(c + 4).startswith('"'):
                    tgt = self.lit(c + 4)
                    for orig, alias in self.export_list(j, c, colon=True):
                        self.add_import(tgt, [orig], alias if alias != orig else None, toks[i].line, "require")
                    return c + 6
                return c + 1
            return j
        name_idx, name = j, self.t(j)
        k = j + 1
        ty = ""
        if self.t(k) == ":":
            x = k + 1
            tparts = []
            while x < b and self.t(x) not in ("=", ";", ","):
                if self.t(x) in ("(", "[", "{", "<"):
                    if self.t(x) == "<":
                        d = 0
                        while x < b:
                            if self.t(x) == "<":
                                d += 1
                            elif self.t(x) == ">":
                                d -= 1
                                if d == 0:
                                    break
                            tparts.append(self.t(x))
                            x += 1
                        tparts.append(">")
                        x += 1
                        continue
                    e = self.close(x)
                    tparts.append(self.text_of(x, e + 1))
                    x = e + 1
                    continue
                tparts.append(self.t(x))
                x += 1
            ty = "".join(tparts)
            k = x
        if self.t(k) != "=":
            return k
        v = k + 1
        if self.t(v) == "require" and self.t(v + 1) == "(" and self.t(v + 2).startswith('"'):
            self.add_import(self.lit(v + 2), [], name, toks[i].line, "require")
            return self.stmt_end(v, b)
        if self.t(v) == "await" or self.t(v) == "async":
            v2 = v + 1
        else:
            v2 = v
        # arrow function `(…) =>` / `x =>` / function expression
        arrow_params = None
        if self.t(v2) == "(":
            pc = self.close(v2)
            x = pc + 1
            if self.t(x) == ":":
                while x < b and self.t(x) != "=>" and self.t(x) not in (";", "{"):
                    x += 1
            if self.t(x) == "=>":
                arrow_params = (v2, pc, x)
        elif is_ident(self.t(v2)) and self.t(v2 + 1) == "=>":
            arrow_params = (v2 - 1, v2 + 1, v2 + 1)
        if arrow_params is not None:
            o, pc, arr = arrow_params
            if self.t(o) == "(":
                names, types, ar = self.params(o, pc)
            else:
                names, types, ar = [self.t(v2)], {}, 1
            body = arr + 1
            if self.t(body) == "{":
                bc = self.close(body)
                end = bc + 1
            else:
                end = self.stmt_end(body, b)
                bc = end - 1
            sig = self.text_of(i, arr + 1)
            s = self.add_sym(start, name_idx, end, prefix, parent, "function", exp, sig=sig, params=names, arity=ar)
            s["sig_hash"] = h12(self.text_of(i, arr + 1).replace(name, "", 1))
            s["body_hash"] = hash_tokens(self.lx, toks, body, end)
            s["words"] = words(toks, body, end, KW)
            s["_types"] = types
            self.owners.append((body, max(bc, body), s["qual"]))
            return end
        if self.t(v2) == "function":
            j2 = v2 + 1
            if self.t(j2) == "*":
                j2 += 1
            if is_ident(self.t(j2)):
                j2 += 1
            if self.t(j2) == "(":
                pc = self.close(j2)
                x = pc + 1
                while x < b and self.t(x) != "{":
                    x += 1
                bc = self.close(x)
                names, types, ar = self.params(j2, pc)
                sig = self.text_of(i, x)
                s = self.add_sym(start, name_idx, bc + 1, prefix, parent, "function", exp, sig=sig, params=names, arity=ar)
                s["sig_hash"] = h12(sig.replace(name, "", 1))
                s["body_hash"] = hash_tokens(self.lx, toks, x, bc + 1)
                s["words"] = words(toks, x + 1, bc, KW)
                s["_types"] = types
                self.owners.append((x, bc, s["qual"]))
                return bc + 1
        if self.t(v2) == "class":
            return self._class_expr(start, name_idx, v2, b, prefix, parent, exp)
        if self.t(v2) == "{" and parent is None:
            c = self.close(v2)
            self.object_methods(v2, c, name, exp, start)
            return c + 1
        # constants: ALLCAPS module-level values
        if parent is None and re.match(r"^[A-Z][A-Z0-9_]*$", name) and self.t(i) == "const":
            e = self.stmt_end(v, b)
            sig = self.text_of(i, min(e, v + 1))
            self.add_sym(start, name_idx, e, prefix, parent, "const", exp, sig=sig)
            return e
        return v

    def _class_expr(self, start, name_idx, ci, b, prefix, parent, exp):
        e = self.klass(start, ci, b, prefix, parent, exp, False)
        s = self.syms[-1] if self.syms else None
        # the class symbol was named by `class X` or "default"; use the variable name
        for x in reversed(self.syms):
            if x["kind"] == "class" and x["line"] == self.toks[start].line:
                old = x["qual"]
                nm = self.t(name_idx)
                x["name"] = nm
                x["qual"] = prefix + nm
                for y in self.syms:
                    if y["parent"] == old:
                        y["parent"] = x["qual"]
                        y["qual"] = x["qual"] + y["qual"][len(old):]
                self.owners = [(a, c, (x["qual"] + q[len(old):]) if q == old or q.startswith(old + ".") else q)
                               for a, c, q in self.owners]
                break
        del s
        return e

    def object_methods(self, o, c, obj, exp, start):
        toks = self.toks
        k = o + 1
        while k < c:
            t = self.t(k)
            if self.t(k - 1) in ("{", ",") or (self.t(k - 1) in ("async", "get", "set", "*") and self.t(k - 2) in ("{", ",")):
                name_idx = k
                if is_ident(t) and self.t(k + 1) == "(":
                    pc = self.close(k + 1)
                    if self.t(pc + 1) == "{":
                        bc = self.close(pc + 1)
                        self._obj_method(obj, t, name_idx, k + 1, pc, pc + 1, bc, exp)
                        k = bc + 1
                        continue
                if is_ident(t) and self.t(k + 1) == ":":
                    v = k + 2
                    if self.t(v) == "async":
                        v += 1
                    if self.t(v) == "function":
                        j = v + 1
                        if is_ident(self.t(j)):
                            j += 1
                        if self.t(j) == "(":
                            pc = self.close(j)
                            if self.t(pc + 1) == "{":
                                bc = self.close(pc + 1)
                                self._obj_method(obj, t, name_idx, j, pc, pc + 1, bc, exp)
                                k = bc + 1
                                continue
                    if self.t(v) == "(":
                        pc = self.close(v)
                        if self.t(pc + 1) == "=>":
                            if self.t(pc + 2) == "{":
                                bc = self.close(pc + 2)
                                self._obj_method(obj, t, name_idx, v, pc, pc + 2, bc, exp)
                                k = bc + 1
                                continue
            if t in ("(", "[", "{"):
                k = self.close(k) + 1
                continue
            k += 1
        del toks, start

    def _obj_method(self, obj, name, name_idx, po, pc, bo, bc, exp):
        toks = self.toks
        names, types, ar = self.params(po, pc)
        qual = f"{obj}.{name}"
        sig = self.text_of(name_idx, bo)
        s = symbol(qual, name, "method", toks[name_idx].line, toks[bc].line, sig=sig, params=names, arity=ar,
                   parent=None, pub=bool(exp), sig_hash=h12(sig.replace(name, "", 1)),
                   body_hash=hash_tokens(self.lx, toks, bo, bc + 1), words=words(toks, bo + 1, bc, KW))
        s["parent"] = obj
        s["doc"] = self.attach_doc(name_idx)
        s["_types"] = types
        s["_objexp"] = True
        self.decl_names.add(name_idx)
        self.syms.append(s)
        self.owners.append((bo, bc, qual))

    def test_call(self, i, prefix, parent):
        toks = self.toks
        o = i + 1
        c = self.close(o)
        title = (self.lit(i + 2) or "")[:80]
        if not title:
            return
        # body: first `{` after `=>` or `function(…)` among the args
        bo = None
        for k in range(i + 3, c):
            if self.t(k) == "{" and self.t(k - 1) in ("=>", ")"):
                bo = k
                break
        end = self.close(bo) if bo is not None else c
        s = symbol(title, title, "test", toks[i].line, toks[c].line, sig=self.text_of(i, i + 3) + ")", test=True,
                   parent=parent, sig_hash=h12(""), body_hash=hash_tokens(self.lx, toks, bo or o, end + 1),
                   words=words(toks, bo or o, end, KW))
        s["doc"] = self.attach_doc(i)
        self.decl_names.add(i)
        self.syms.append(s)
        self.owners.append((bo if bo is not None else o, end, title))

    # -- pass 2 ------------------------------------------------------------------------
    def owner_at(self, k):
        best = None
        for a, b, q in self.owners:
            if a <= k <= b and (best is None or b - a < best[1] - best[0]):
                best = (a, b, q)
        return best[2] if best else None

    def scan_calls(self):
        toks = self.toks
        n = len(toks)
        # owners sorted for a sweep: cheap enough per call site with small files
        types_by_owner = {s["qual"]: s.get("_types", {}) for s in self.syms}
        local_types: dict[str, dict] = {}
        for k in range(n):
            t = toks[k].t
            if t == "new" and k + 1 < n and is_ident(toks[k + 1].t):
                x = k + 1
                chain = [toks[x].t]
                while x + 2 < n and toks[x + 1].t == "." and is_ident(toks[x + 2].t):
                    chain.append(toks[x + 2].t)
                    x += 2
                own = self.owner_at(k)
                self.calls.append({"from": own, "name": chain[-1], "recv": ".".join(chain[:-1]) or None,
                                   "recv_type": None, "line": toks[k].line, "kind": "new"})
                # `const x = new T(…)` -> local type
                if k >= 2 and toks[k - 1].t == "=" and is_ident(toks[k - 2].t):
                    local_types.setdefault(own or "", {})[toks[k - 2].t] = chain[-1]
                continue
            if t != "(" or k == 0:
                continue
            ni = k - 1
            optional = False
            if toks[ni].t == "?.":
                ni -= 1
                optional = True
            if toks[ni].t == ">":  # generic call f<T>(…)
                d, x = 0, ni
                while x > 0:
                    if toks[x].t == ">":
                        d += 1
                    elif toks[x].t == "<":
                        d -= 1
                        if d == 0:
                            break
                    elif toks[x].t in (";", "{", "}", "(", ")") or toks[x].t in NOT_TARGS:
                        x = -1  # `lo < x && z > (y)` is a comparison, not a generic call
                        break
                    x -= 1
                if x <= 0:
                    continue
                ni = x - 1
            nm = toks[ni].t
            if not is_ident(nm) or ni in self.decl_names:
                continue
            before = toks[ni - 1].t if ni > 0 else ""
            if before == "#":  # this.#private(…)
                nm = "#" + nm
                ni -= 1
                if ni - 1 in self.decl_names or ni in self.decl_names:
                    continue
                before = toks[ni - 1].t if ni > 0 else ""
            if before == "function" or (before == "new"):
                continue
            if nm == "import" and k + 1 < n and toks[k + 1].t.startswith('"'):
                self.add_import(self.lx.literal(toks[k + 1].pos), [], None, toks[k].line, "dynamic")
                continue
            if nm == "require" and before not in (".",) and k + 1 < n and toks[k + 1].t.startswith('"'):
                # bare require("x") not bound to a name
                if not (ni >= 2 and toks[ni - 1].t == "=" ):
                    self.add_import(self.lx.literal(toks[k + 1].pos), [], None, toks[k].line, "require")
                continue
            if nm in CALL_SKIP and before not in (".", "?."):
                continue
            recv = None
            if before in (".", "?."):
                chain = []
                x = ni - 2
                plain = False
                while x >= 0 and is_ident(toks[x].t):
                    chain.insert(0, toks[x].t)
                    if x - 1 >= 0 and toks[x - 1].t in (".", "?."):
                        x -= 2
                        continue
                    plain = True
                    break
                # `[1,2].map(f)`, `"a".split(",")`, `getView().render()`: expression receiver, type unknown
                recv = ".".join(chain) if plain else "?"
            elif is_ident(before) and before not in ("return", "await", "yield", "typeof", "void", "else",
                                                      "do", "case", "throw", "in", "of", "delete", "new"):
                # `async name(`/`get name(` method heads, TS `function name(` already skipped
                continue
            own = self.owner_at(k)
            rt = None
            if recv and "." not in recv:
                rt = (types_by_owner.get(own or "", {}) or {}).get(recv) or local_types.get(own or "", {}).get(recv)
            self.calls.append({"from": own, "name": nm, "recv": recv, "recv_type": rt, "line": toks[ni].line,
                               "kind": "call"})
            if nm == "fetch" and recv in (None, "window", "globalThis") and k + 1 < n and toks[k + 1].t.startswith('"'):
                url = self.lx.literal(toks[k + 1].pos)
                op = "GET"
                c = self.close(k)
                for x in range(k + 2, c):
                    if toks[x].t == "method" and x + 2 < c and toks[x + 1].t == ":" and toks[x + 2].t.startswith('"'):
                        op = (self.lx.literal(toks[x + 2].pos) or "GET").upper()
                        break
                self.strings.append({"kind": "route", "value": url, "op": op, "line": toks[k].line, "from": own})
            del optional

    def finish(self):
        for s in self.syms:
            for k in ("_body", "_types", "_private", "_objexp"):
                s.pop(k, None)
        texts = [c[4] for c in self.lx.comments()] + [v for _, v in self.lx.strings()]
        out = {"symbols": self.syms, "calls": self.calls, "imports": self.imports, "strings": self.strings,
               "file_doc": self.file_doc, "conf": "high" if self.balanced else "low",
               "_strings": self.lx.strings(), "_texts": texts}
        if self.default_export is not None:
            out["default_export"] = self.default_export  # qual of `export default X`, "" for an expression
        return out


def extract_js(text: str, ctx: dict, lang: str) -> dict:
    rel = ctx.get("rel", "")
    jsx = rel.lower().endswith((".jsx", ".tsx"))
    lx = Lexed(text, "ts" if lang == "ts" else "js", jsx=jsx)
    p = _JS(lx, ctx, lang == "ts")
    p.run()
    for s in p.syms:
        if s.get("_private"):
            s["pub"] = False
    return p.finish()
