"""C/C++ adapter: lexer + preprocessor blanking + a scope-stack walk over tokens.

No compiler, no macro expansion. Out-of-line `A::B::f` definitions keep the qualifier as
written in the file (plus enclosing namespaces). At file scope, when exactly one non-std
`using namespace X;` precedes it and `A` is not a class or namespace of this file, the
definition is re-qualified as `X::A::B::f` (so it shares its key with the header
declaration). Every `using namespace X;` is also reported as an import of kind `using`.
"""
from __future__ import annotations

import re

from . import docparse
from .lex import (src_text, DocIndex, Lexed, Tok, brackets, doc_style, h12, hash_tokens, is_ident, skip_angles, symbol, tokenize, words)

NONFUNC = {"if", "for", "while", "switch", "catch", "return", "sizeof", "decltype", "alignof",
           "static_assert", "do", "else", "alignas", "__attribute__", "__declspec", "noexcept",
           "throw", "typeid", "new", "delete", "case", "goto", "defined", "_Static_assert",
           "__typeof__", "typeof", "_Alignof", "_Generic", "requires", "co_await", "co_return", "co_yield"}
PRIM = {"void", "int", "char", "short", "long", "float", "double", "bool", "unsigned", "signed",
        "auto", "wchar_t", "char8_t", "char16_t", "char32_t", "size_t", "_Bool"}
CASTS = {"static_cast", "dynamic_cast", "reinterpret_cast", "const_cast", "bit_cast"}
CALL_SKIP = NONFUNC | PRIM | CASTS | {"this", "operator", "template", "typename", "using", "namespace",
                                      "struct", "class", "union", "enum", "const", "volatile", "constexpr"}
EXPR_KW = {"return", "else", "case", "throw", "co_return", "co_yield", "co_await", "delete", "do", "goto"}
DECL_SPEC = {"virtual", "override", "final", "explicit", "inline", "static", "extern", "friend",
             "__inline", "__forceinline", "consteval", "constinit"}
TYPE_DROP = {"const", "volatile", "&", "*", "&&", "struct", "class", "union", "enum", "typename",
             "static", "mutable", "constexpr", "inline", "extern", "register", "thread_local", "unsigned_"}
TEST_MACROS = {"TEST": "test", "TEST_F": "test", "TEST_P": "test", "TEST_CASE": "test",
               "TYPED_TEST": "test", "SCENARIO": "test"}
ALLCAPS = re.compile(r"^[A-Z][A-Z0-9_]*$")
# tokens that cannot appear inside template arguments: their presence makes `a < b … > (` a comparison
NOT_TARGS = {"&&", "||", "?", "==", "!=", "<=", ">=", "=", "+", "-", "/", "%", "!", "|", "^", "+=", "-=", "return"}
MAKE_FNS = {"make_unique", "make_shared", "make_optional"}
HEADER = (".h", ".hh", ".hpp", ".hxx")


# ---------------------------------------------------------------------------------------
# preprocessor
# ---------------------------------------------------------------------------------------

def _preprocess(lx: Lexed, first_only: bool):
    """Blank directive and inactive lines. Returns (code, includes, macros, active_lines)."""
    code_lines = lx.code.split("\n")
    text_lines = lx.text.split("\n")
    out = list(code_lines)
    includes, macros = [], []
    stack: list[dict] = []  # {"active", "taken", "parent"}
    active = True
    i = 0
    n = len(code_lines)
    while i < n:
        ln = code_lines[i]
        s = ln.lstrip()
        if s.startswith("#"):
            j = i
            while j < n - 1 and code_lines[j].rstrip().endswith("\\"):
                j += 1
            full = " ".join(code_lines[k].rstrip().rstrip("\\") for k in range(i, j + 1))
            m = re.match(r"\s*#\s*(\w*)\s*(.*)$", full)
            d, rest = (m.group(1), m.group(2).strip()) if m else ("", "")
            if d in ("if", "ifdef", "ifndef"):
                zero = d == "if" and re.match(r"^(0|false)\b", rest) is not None
                one = d == "if" and re.match(r"^(1|true)\b", rest) is not None
                me = {"parent": active, "taken": False, "zero": zero, "one": one}
                me["active"] = active and not zero
                me["taken"] = me["active"]
                stack.append(me)
                active = me["active"]
            elif d in ("elif", "else", "elifdef", "elifndef") and stack:
                me = stack[-1]
                if me["zero"]:
                    # `#if 0 … #else` : the else branch is the live one
                    on = me["parent"] and not me["taken"] and (d == "else" or not re.match(r"^(0|false)\b", rest))
                elif me["one"]:
                    on = False
                elif first_only:
                    on = False
                else:
                    on = me["parent"]
                if d == "elif" and re.match(r"^(0|false)\b", rest):
                    on = False
                me["active"] = on
                me["taken"] = me["taken"] or on
                active = on
            elif d == "endif" and stack:
                me = stack.pop()
                active = me["parent"]
            elif active and d in ("include", "import", "include_next"):
                tm = re.match(r"\s*#\s*\w+\s*([<\"])([^>\"]*)[>\"]", text_lines[i])
                if tm:
                    includes.append({"target": tm.group(2), "names": [], "alias": None, "line": i + 1,
                                     "kind": "include", "level": 0, "system": tm.group(1) == "<"})
            elif active and d == "define":
                dm = re.match(r"(\w+)(\()?([^)]*\))?", rest)
                if dm:
                    name = dm.group(1)
                    body = rest[dm.end():].strip()
                    fn = dm.group(2) is not None
                    if fn or body:
                        params = []
                        if fn:
                            params = [p.strip() for p in (dm.group(3) or "").rstrip(")").split(",") if p.strip()]
                        macros.append((name, i + 1, j + 1, fn, params, full.strip()))
            for k in range(i, j + 1):
                out[k] = " " * len(code_lines[k])
            i = j + 1
            continue
        if not active:
            out[i] = " " * len(ln)
        i += 1
    return "\n".join(out), includes, macros


# ---------------------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------------------

class _Scope:
    __slots__ = ("kind", "qual", "access", "sym", "anon", "internal")

    def __init__(self, kind, qual, access="public", sym=None, anon=False, internal=False):
        self.kind, self.qual, self.access, self.sym = kind, qual, access, sym
        self.anon, self.internal = anon, internal


class _C:
    def __init__(self, lx: Lexed, code: str, ctx: dict, cpp: bool):
        self.lx = lx
        self.ctx = ctx
        self.cpp = cpp
        self.toks: list[Tok] = tokenize(lx, code)
        self.match, self.balanced = brackets(self.toks)
        self.docs = DocIndex(lx)
        self.syms: list[dict] = []
        self.calls: list[dict] = []
        self.imports: list[dict] = []
        self.header = ctx["rel"].lower().endswith(HEADER)
        self.classes: set[str] = set()
        self.namespaces: set[str] = set()
        self.usings: list[str] = []  # file-scope `using namespace X;` (not std), in order
        self.stray = False
        macros = dict(TEST_MACROS)
        for k, v in (ctx.get("cfg", {}).get("macros") or {}).items():
            if isinstance(k, str) and isinstance(v, str):
                macros[k] = v
        self.macros = macros
        self.file_doc = None

    # -- utils -----------------------------------------------------------------------
    def t(self, i):
        return self.toks[i].t if 0 <= i < len(self.toks) else ""

    def close(self, i):
        return self.match.get(i, len(self.toks) - 1)

    def text_of(self, a, b):
        return src_text(self.lx, self.toks, a, b)

    def attach_doc(self, head_idx):
        tk = self.toks[head_idx]
        blk = self.docs.leading(tk.line, tk.pos)
        if not blk or blk["used"]:
            return None
        blk["used"] = True
        return docparse.parse_block(blk["raw"], doc_style(blk["raw"]), blk["sl"])

    def trailing_doc(self, line):
        blk = self.docs.trailing_back(line)
        if blk and not blk["used"]:
            blk["used"] = True
            return docparse.parse_block(blk["raw"], "doxygen", blk["sl"])
        return None

    @staticmethod
    def qjoin(parts):
        return "::".join(p for p in parts if p)

    def is_pub(self, scopes, static=False):
        if not self.header:
            return False
        for sc in scopes:
            if sc.anon or sc.internal:
                return False
            if sc.kind == "class" and sc.access != "public":
                return False
        if static and scopes[-1].kind != "class":
            return False
        return True

    # -- driver ----------------------------------------------------------------------
    def run(self):
        # file doc: first block with @file
        for blk in self.docs.blocks:
            if re.search(r"[@\\]file\b", blk["raw"]):
                blk["used"] = True
                self.file_doc = docparse.parse_block(blk["raw"], "doxygen", blk["sl"])
                break
        root = _Scope("ns", [])
        i = self.scope(0, [root])
        while i < len(self.toks):  # stray closing braces at file scope
            self.stray = True
            i = self.scope(i + 1, [root])

    def scope(self, i, scopes):
        """Parse statements until the closing `}` of this scope; return its index."""
        toks = self.toks
        n = len(toks)
        sc = scopes[-1]
        start = i
        while i < n:
            t = toks[i].t
            if t == "}":
                return i
            if t == ";":
                if i > start:
                    self.stmt(start, i, scopes)
                i += 1
                start = i
                continue
            if t in ("(", "["):
                i = self.close(i) + 1
                continue
            if t == "{":
                i, reset = self.brace(start, i, scopes)
                if reset:
                    start = i
                continue
            if (sc.kind == "class" and i == start and t in ("public", "private", "protected")
                    and self.t(i + 1) == ":"):
                sc.access = t
                i += 2
                start = i
                continue
            if sc.kind == "class" and i == start and t in ("signals", "slots", "Q_SIGNALS", "Q_SLOTS") and self.t(i + 1) == ":":
                i += 2
                start = i
                continue
            i += 1
        return n

    # -- heads -----------------------------------------------------------------------
    def strip_head(self, a, b):
        """Skip leading template<…>, attributes and export-ish noise. Returns (a', template_start)."""
        toks = self.toks
        while a < b:
            t = toks[a].t
            if t == "template" and a + 1 < b and toks[a + 1].t == "<":
                a = skip_angles(toks, a + 1, b)
                continue
            if t == "[" and a + 1 < b and toks[a + 1].t == "[":
                a = self.close(a) + 1
                continue
            if t in ("__attribute__", "__declspec", "alignas") and a + 1 < b and toks[a + 1].t == "(":
                a = self.close(a + 1) + 1
                continue
            if t == "export" and self.cpp:
                a += 1
                continue
            break
        return a

    def find_fn(self, a, b):
        """Locate `name (` of a function head in a..b. Returns dict or None."""
        toks = self.toks
        k = a
        while k < b:
            t = toks[k].t
            if t == "=" :
                return None
            if t == "operator":
                # operator symbol up to the parameter paren
                j = k + 1
                if j < b and toks[j].t == "(" and j + 1 < b and toks[j + 1].t == ")":
                    j += 2
                    name = "operator()"
                else:
                    while j < b and toks[j].t != "(":
                        j += 1
                    name = "operator" + "".join(
                        (" " + toks[x].t if is_ident(toks[x].t) else toks[x].t) for x in range(k + 1, j))
                    name = name.replace("operator ", "operator ", 1)
                if j >= b or toks[j].t != "(":
                    return None
                return self._fn_parts(a, k, j, name)
            if t == "<" and k > a and is_ident(toks[k - 1].t) and toks[k - 1].t not in ("operator",):
                k = skip_angles(toks, k, b)
                continue
            if t == "(":
                prev = toks[k - 1].t if k > a else ""
                if is_ident(prev) and prev not in NONFUNC and prev not in PRIM:
                    if k - 2 >= a and toks[k - 2].t in (".", "->"):
                        return None
                    return self._fn_parts(a, k - 1, k, prev)
                k = self.close(k) + 1
                continue
            if t == "{":
                return None
            k += 1
        return None

    def _fn_parts(self, a, name_idx, paren, name):
        toks = self.toks
        q = []
        m = name_idx
        if name_idx > a and toks[name_idx - 1].t == "~":
            name = "~" + name
            m = name_idx - 1
        while m - 2 >= a and toks[m - 1].t == "::":
            p = m - 2
            if toks[p].t == ">":
                # A<T>::f
                d, x = 0, p
                while x >= a:
                    if toks[x].t == ">":
                        d += 1
                    elif toks[x].t == "<":
                        d -= 1
                        if d == 0:
                            break
                    x -= 1
                p = x - 1
            if p >= a and is_ident(toks[p].t):
                q.insert(0, toks[p].t)
                m = p
            else:
                break
        if m - 1 >= a and toks[m - 1].t == "::" and (m - 1 == a or not is_ident(toks[m - 2].t)):
            m -= 1  # leading ::
        return {"name": name, "quals": q, "name_start": m, "paren": paren, "close": self.close(paren)}

    def params(self, p, c):
        """Parameter names and types between paren p and close c."""
        toks = self.toks
        groups, cur, depth = [], [], 0
        for k in range(p + 1, c):
            t = toks[k].t
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
            ts = [toks[k].t for k in g]
            if "=" in ts:
                ts = ts[:ts.index("=")]
            if ts == ["void"] and len(groups) == 1:
                return [], {}, 0
            if ts == ["..."]:
                continue
            nm = ""
            # function pointer ( * name )
            if "(" in ts and len(ts) > 3:
                o = ts.index("(")
                if o + 2 < len(ts) and ts[o + 1] in ("*", "&", "^") and is_ident(ts[o + 2]):
                    nm = ts[o + 2]
            while ts and ts[-1] == "]":
                if "[" in ts:
                    ts = ts[:len(ts) - 1 - ts[::-1].index("[")]
                else:
                    break
            if not nm and len(ts) >= 2 and is_ident(ts[-1]) and ts[-1] not in PRIM and ts[-2] != "::" \
                    and ts[-1] not in ("const", "volatile"):
                nm = ts[-1]
                ty = [x for x in ts[:-1] if x not in TYPE_DROP]
                if ty:
                    types[nm] = "".join(ty)
            names.append(nm)
        return [n for n in names if n] if any(names) else [n for n in names if n], types, len(groups)

    # -- statements ------------------------------------------------------------------
    def brace(self, s, i, scopes):
        """Handle `{` at index i with head s..i. Returns (next index, reset_statement)."""
        toks = self.toks
        sc = scopes[-1]
        a = self.strip_head(s, i)
        head = [toks[k].t for k in range(a, i)]
        cl = self.close(i)
        if not head:
            return cl + 1, True
        h0 = head[0]
        # namespace
        if h0 == "namespace" or (h0 == "inline" and len(head) > 1 and head[1] == "namespace"):
            names = [x for x in head[head.index("namespace") + 1:] if is_ident(x)]
            anon = not names
            parts = names or ["(anon)"]
            internal = any(p in ("detail", "internal", "impl") for p in parts)
            self.namespaces.update(names)
            new = _Scope("ns", sc.qual + parts, anon=anon or sc.anon, internal=internal or sc.internal)
            j = self.scope(i + 1, scopes + [new])
            return j + 1, True
        if h0 == "extern" and len(head) == 2 and head[1].startswith('"'):
            j = self.scope(i + 1, scopes)
            return j + 1, True
        # test macros
        if h0 in self.macros and len(head) > 1 and head[1] == "(":
            return self.test_macro(s, a, i, cl, scopes), True
        # class / struct / union / enum
        ck = next((x for x in range(len(head)) if head[x] in ("class", "struct", "union", "enum")), None)
        if ck is not None and "(" not in head[:ck] and "=" not in head:
            return self.klass(s, a, a + ck, i, cl, scopes)
        # function definition
        fn = self.find_fn(a, i)
        if fn is not None and fn["close"] < i:
            after = [toks[k].t for k in range(fn["close"] + 1, i)]
            init = ":" in after
            if init:
                # brace-init members in a ctor init list: `x_{v}` -> keep collecting
                prev = toks[i - 1].t
                if prev not in (")", "}"):
                    return cl + 1, False
            ok = self.function(s, a, fn, i, cl, scopes, decl=False)
            if ok:
                return cl + 1, True
        # unknown block at namespace scope (e.g. an unlisted `MACRO(a, b) { … }`): end the statement
        if sc.kind == "ns" and "=" not in head:
            return cl + 1, True
        # anything else: initializer braces, lambdas, blocks
        return cl + 1, False

    def stmt(self, s, e, scopes):
        toks = self.toks
        sc = scopes[-1]
        a = self.strip_head(s, e)
        if a >= e:
            return
        head = [toks[k].t for k in range(a, e)]
        h0 = head[0]
        if h0 == "using":
            if len(head) > 1 and head[1] == "namespace":
                tgt = "".join(head[2:])
                if len(scopes) == 1 and tgt.lstrip(":").split("::")[0] != "std" and tgt not in self.usings:
                    self.usings.append(tgt.lstrip(":"))
                self.imports.append({"target": tgt, "names": [], "alias": None, "line": toks[a].line,
                                     "kind": "using", "level": 0, "system": False})
            elif len(head) > 2 and is_ident(head[1]) and head[2] == "=":
                self.simple(a, e, head[1], "type", scopes, sig=self.text_of(a, e))
            return
        if h0 == "typedef":
            name = None
            for k in range(a, e):
                if toks[k].t == "(" and k + 2 < e and toks[k + 1].t == "*" and is_ident(toks[k + 2].t):
                    name = toks[k + 2].t
                    break
            if name is None:
                ids = [x for x in head if is_ident(x)]
                name = ids[-1] if ids else None
            if name:
                self.simple(a, e, name, "type", scopes, sig=self.text_of(a, e))
            return
        if h0 in ("friend", "static_assert", "_Static_assert", "return", "goto"):
            return
        if h0 in ("class", "struct", "union", "enum") and len(head) <= 3 and "(" not in head:
            return  # forward declaration
        fn = self.find_fn(a, e)
        if fn is not None and not (sc.kind == "ns" and not fn["quals"] and fn["name_start"] == a
                                   and not self.cpp_ctorish(fn, scopes)):
            if ALLCAPS.match(fn["name"]) and fn["name_start"] == a and not self.cpp_ctorish(fn, scopes):
                return  # macro invocation
            self.function(s, a, fn, e, e, scopes, decl=True)
            return
        # variables / fields
        self.variable(a, e, scopes)

    def cpp_ctorish(self, fn, scopes):
        sc = scopes[-1]
        return sc.kind == "class" and fn["name"].lstrip("~") == sc.qual[-1]

    def simple(self, a, e, name, kind, scopes, sig):
        sc = scopes[-1]
        qual = self.qjoin(sc.qual + [name])
        s = symbol(qual, name, kind, self.toks[a].line, self.toks[e - 1].line if e > a else self.toks[a].line,
                   sig=sig, pub=self.is_pub(scopes), parent=self.qjoin(sc.qual) or None,
                   sig_hash=h12(sig.replace(name, "", 1)), body_hash=hash_tokens(self.lx, self.toks, a, e))
        s["doc"] = self.attach_doc(a) or self.trailing_doc(self.toks[e - 1].line if e > a else 0)
        self.syms.append(s)
        return s

    def variable(self, a, e, scopes):
        toks = self.toks
        sc = scopes[-1]
        head = [toks[k].t for k in range(a, e)]
        # first declarator: type + name
        depth, cut = 0, len(head)
        for x, t in enumerate(head):
            if t in ("(", "[", "{", "<"):
                depth += 1
            elif t in (")", "]", "}", ">"):
                depth -= 1
            elif depth == 0 and t in ("=", ",", ":") and x > 0:
                cut = x
                break
        decl = head[:cut]
        while decl and decl[-1] == "]" and "[" in decl:
            decl = decl[:len(decl) - 1 - decl[::-1].index("[")]
        if len(decl) < 2 or not is_ident(decl[-1]) or decl[-1] in PRIM:
            return
        name = decl[-1]
        ty = "".join(x for x in decl[:-1] if x not in TYPE_DROP)
        if sc.kind == "class" and sc.sym is not None:
            sc.sym["members"][name] = ty
            for extra in self.more_declarators(head[cut:]):
                sc.sym["members"][extra] = ty
            return
        if sc.kind == "ns" and ("constexpr" in decl or "const" in decl[:1]) and "extern" not in decl:
            s = self.simple(a, e, name, "const", scopes, sig=self.text_of(a, e))
            s["static"] = "static" in decl
            if s["static"]:
                s["pub"] = False

    @staticmethod
    def more_declarators(rest):
        out, depth = [], 0
        for x, t in enumerate(rest):
            if t in ("(", "[", "{", "<"):
                depth += 1
            elif t in (")", "]", "}", ">"):
                depth -= 1
            elif t == "," and depth == 0:
                y = x + 1
                while y < len(rest) and rest[y] in ("*", "&"):
                    y += 1
                if y < len(rest) and is_ident(rest[y]):
                    out.append(rest[y])
        return out

    def klass(self, s, a, kidx, i, cl, scopes):
        toks = self.toks
        sc = scopes[-1]
        kw = toks[kidx].t
        typedef = toks[a].t == "typedef"
        j = kidx + 1
        if kw == "enum" and j < i and toks[j].t in ("class", "struct"):
            j += 1
        name_parts, k = [], j
        while k < i and toks[k].t not in (":", "{", "final"):
            t = toks[k].t
            if t in ("[",) and k + 1 < i and toks[k + 1].t == "[":
                k = self.close(k) + 1
                continue
            if t in ("alignas", "__attribute__", "__declspec") and k + 1 < i and toks[k + 1].t == "(":
                k = self.close(k + 1) + 1
                continue
            if t == "<":
                k = skip_angles(toks, k, i)
                continue
            if is_ident(t):
                if name_parts and toks[k - 1].t != "::":
                    name_parts = [t]  # `class EXPORT Name` keeps the last word
                else:
                    name_parts.append(t)
            k += 1
        bases = []
        if k < i and toks[k].t == "final":
            k += 1
        if k < i and toks[k].t == ":" and kw != "enum":
            cur, depth = [], 0
            for x in range(k + 1, i):
                t = toks[x].t
                if t == "<":
                    depth += 1
                elif t == ">":
                    depth -= 1
                if t == "," and depth == 0:
                    bases.append(cur)
                    cur = []
                    continue
                if t not in ("public", "private", "protected", "virtual"):
                    cur.append(t)
            if cur:
                bases.append(cur)
            bases = ["".join(b) for b in bases if b]
        # name after the closing brace for `typedef struct {…} Name;`
        after_name = None
        if cl + 1 < len(toks) and is_ident(toks[cl + 1].t):
            x = cl + 1
            while x < len(toks) and toks[x].t not in (";", "{", "}"):
                x += 1
            ids = [toks[y].t for y in range(cl + 1, x) if is_ident(toks[y].t)]
            if typedef and ids:
                after_name = ids[-1]
        name = name_parts[-1] if name_parts else after_name
        if not name:
            # anonymous struct/union/enum: skip the body
            return cl + 1, False
        qual = self.qjoin(sc.qual + name_parts[:-1] + [name]) if name_parts else self.qjoin(sc.qual + [name])
        kind = {"class": "class", "struct": "struct", "union": "struct", "enum": "enum"}[kw]
        sig_end = i
        sig = self.text_of(a if not typedef else kidx, sig_end)
        if typedef and not name_parts:
            sig = f"typedef {kw} {name}"
        sym = symbol(qual, name, kind, toks[s].line, toks[cl].line,
                     sig=sig, pub=self.is_pub(scopes), parent=self.qjoin(sc.qual) or None, bases=bases,
                     sig_hash=h12(sig.replace(name, "", 1)))
        sym["doc"] = self.attach_doc(s)
        self.classes.add(name)
        self.syms.append(sym)
        if kind == "enum":
            sym["body_hash"] = hash_tokens(self.lx, toks, i, cl + 1)
            sym["words"] = words(toks, i + 1, cl, CALL_SKIP)
        else:
            new = _Scope("class", sc.qual + (name_parts[:-1] if name_parts else []) + [name],
                         access="private" if kw == "class" else "public", sym=sym,
                         anon=sc.anon, internal=sc.internal)
            n0 = len(self.syms)
            self.scope(i + 1, scopes + [new])
            # body hash: class body without nested function bodies
            skips = [(x["_body"][0], x["_body"][1]) for x in self.syms[n0:] if x.get("_body")]
            sym["body_hash"] = hash_tokens(self.lx, toks, i, cl + 1, skip=skips)
            sym["words"] = words(toks, i + 1, cl, CALL_SKIP)
        # continue after `}` to the end of the declaration
        x = cl + 1
        if x < len(toks) and toks[x].t == ";":
            return x + 1, True
        while x < len(toks) and toks[x].t not in (";", "{", "}"):
            x += 1
        if x < len(toks) and toks[x].t == ";":
            return x + 1, True
        return cl + 1, True

    def function(self, s, a, fn, i, cl, scopes, decl):
        """Record a function definition (body i..cl) or declaration (ends at i)."""
        toks = self.toks
        sc = scopes[-1]
        name, quals = fn["name"], list(fn["quals"])
        if (quals and len(scopes) == 1 and len(self.usings) == 1 and quals[0] not in self.classes
                and quals[0] not in self.namespaces and quals[0] != "std"):
            # `using namespace geo; Circle::area() {…}` defines geo::Circle::area
            quals = self.usings[0].split("::") + quals
        pre = [toks[k].t for k in range(a, fn["name_start"])]
        after = [toks[k].t for k in range(fn["close"] + 1, i)]
        # cut the ctor init list from the trailing part
        tail = []
        depth = 0
        for t in after:
            if t == ":" and depth == 0:
                break
            if t in ("(", "<"):
                depth += 1
            elif t in (")", ">"):
                depth -= 1
            tail.append(t)
        in_class = sc.kind == "class"
        cls_name = sc.qual[-1] if in_class else (quals[-1] if quals else None)
        is_ctor = cls_name is not None and name.lstrip("~") == cls_name
        ret_type = [x for x in pre if x not in DECL_SPEC]
        if not ret_type and not is_ctor and not quals and not name.startswith("operator"):
            if not in_class:
                return False
        method = in_class or bool(quals and (quals[-1] in self.classes or quals[-1][:1].isupper()))
        kind = "ctor" if is_ctor and not name.startswith("~") else ("method" if method else "function")
        qual = self.qjoin(sc.qual + quals + [name])
        parent = self.qjoin(sc.qual + quals) or None
        pnames, ptypes, arity = self.params(fn["paren"], fn["close"])
        # signature: head up to the end of the qualifiers
        sig_end = fn["close"] + 1 + len(tail)
        while sig_end > fn["close"] + 1 and toks[sig_end - 1].t in ("try",):
            sig_end -= 1
        sig = self.text_of(a, sig_end)
        if decl:
            sig = self.text_of(a, i)
        name_toks = set(range(fn["name_start"], fn["paren"]))
        sig_parts = []
        for k in range(a, (i if decl else sig_end)):
            if k in name_toks or toks[k].t in DECL_SPEC:
                continue
            tk = toks[k]
            sig_parts.append(self.lx.text[tk.pos:self.lx.strmap[tk.pos]] if tk.t.startswith('"') and tk.pos in self.lx.strmap else tk.t)
        static = "static" in pre
        tail_set = set(tail)
        pure = decl and len(tail) >= 2 and tail[-2:] == ["=", "0"]
        override = "override" in tail_set or "final" in tail_set
        virtual = "virtual" in pre or override or pure
        sym = symbol(qual, name, kind, toks[s].line, toks[cl].line if not decl else toks[i - 1].line,
                     sig=sig, params=pnames, arity=arity, decl=decl, parent=parent,
                     virtual=virtual, pure=pure, override=override, static=static,
                     sig_hash=h12("\x1f".join(sig_parts)))
        if self.header:
            sym["pub"] = self.is_pub(scopes, static=static)
            if not in_class and quals and method:
                sym["pub"] = self.is_pub(scopes)
        sym["doc"] = self.attach_doc(s)
        if decl:
            d2 = self.trailing_doc(toks[i - 1].line)
            if sym["doc"] is None and d2 is not None:
                sym["doc"] = d2
            sym["body_hash"] = h12("")
        else:
            sym["body_hash"] = hash_tokens(self.lx, toks, i, cl + 1)
            sym["words"] = words(toks, i + 1, cl, CALL_SKIP)
            sym["_body"] = (i, cl)
            self.body_calls(i, cl, qual, ptypes)
            self.init_calls(fn["close"] + 1, i, qual, ptypes)
        self.syms.append(sym)
        return True

    def init_calls(self, a, b, owner, ptypes):
        """Calls inside a ctor init list `: m_(f(x)), n_{g()}` (member names are not calls)."""
        toks = self.toks
        k = a
        while k < b and toks[k].t != ":":
            if toks[k].t in ("(", "["):
                k = self.close(k)
            k += 1
        while k < b:
            if toks[k].t in (":", ",") and k + 2 < b and is_ident(toks[k + 1].t):
                j = k + 1
                while j + 2 < b and toks[j + 1].t == "::" and is_ident(toks[j + 2].t):
                    j += 2
                if j + 1 < b and toks[j + 1].t == "<":
                    j = skip_angles(toks, j + 1, b) - 1
                if j + 1 < b and toks[j + 1].t in ("(", "{"):
                    c = self.close(j + 1)
                    self.body_calls(j + 1, c, owner, ptypes)
                    k = c + 1
                    continue
            k += 1

    def test_macro(self, s, a, i, cl, scopes):
        toks = self.toks
        p = a + 1
        c = self.close(p)
        args = []
        cur = []
        for k in range(p + 1, c):
            t = toks[k].t
            if t == ",":
                args.append(cur)
                cur = []
                continue
            cur.append(k)
        if cur:
            args.append(cur)
        names = []
        for g in args:
            if len(g) == 1 and toks[g[0]].t.startswith('"'):
                names.append(self.lx.literal(toks[g[0]].pos))
            else:
                names.append("".join(toks[k].t for k in g))
        names = [x for x in names if x]
        if toks[a].t == "TEST_CASE" and names:
            names = names[:1]
        name = ".".join(names)[:80] or toks[a].t
        sc = scopes[-1]
        qual = self.qjoin(sc.qual + [name])
        sig = self.text_of(a, c + 1)
        sym = symbol(qual, name, self.macros.get(toks[a].t, "test"), toks[a].line, toks[cl].line, sig=sig,
                     test=True, parent=self.qjoin(sc.qual) or None, sig_hash=h12(sig.replace(name, "")),
                     body_hash=hash_tokens(self.lx, toks, i, cl + 1), words=words(toks, i + 1, cl, CALL_SKIP))
        sym["doc"] = self.attach_doc(a)
        sym["_body"] = (i, cl)
        self.syms.append(sym)
        self.reqs_from_name(name, toks[a].line, qual)
        self.body_calls(i, cl, qual, {})
        return cl + 1

    def reqs_from_name(self, name, line, qual):
        for m in re.finditer(r"REQ_([A-Z][A-Z0-9]*)_(\d+)", name):
            self.reqs.append({"id": f"REQ-{m.group(1)}-{m.group(2)}", "line": line, "from": qual})

    # -- bodies ----------------------------------------------------------------------
    def type_before(self, k, lo):
        """Type chain ending just before index k (exclusive). Returns (type, start) or (None, k)."""
        toks = self.toks
        j = k - 1
        while j >= lo and toks[j].t in ("&", "*", "&&", "const"):
            j -= 1
        if j < lo:
            return None, k
        end = j
        if toks[j].t == ">":
            d = 0
            while j >= lo:
                if toks[j].t == ">":
                    d += 1
                elif toks[j].t == "<":
                    d -= 1
                    if d == 0:
                        break
                j -= 1
            j -= 1
        if j < lo or not is_ident(toks[j].t):
            return None, k
        while j - 2 >= lo and toks[j - 1].t == "::" and is_ident(toks[j - 2].t):
            j -= 2
        start = j
        while start - 1 >= lo and toks[start - 1].t in ("const", "struct", "volatile", "class", "typename", "static"):
            start -= 1
        ty = "".join(toks[x].t for x in range(j, end + 1))
        return ty, start

    def body_calls(self, a, b, owner, ptypes):
        toks = self.toks
        types = dict(ptypes)
        k = a + 1
        while k < b:
            t = toks[k].t
            if t == "new":
                x = k + 1
                chain = []
                while x < b and (is_ident(toks[x].t) or toks[x].t == "::"):
                    chain.append(toks[x].t)
                    x += 1
                nm = "".join(chain).lstrip(":")
                if nm and nm not in PRIM:
                    self.calls.append({"from": owner, "name": nm, "recv": None, "recv_type": None,
                                       "line": toks[k].line, "kind": "new"})
                k = x
                continue
            if is_ident(t) and t not in CALL_SKIP and k + 1 < b and toks[k + 1].t in ("=", "(", "{", ";", ","):
                # `T x = …`, `T x(…)`, `T x{…}`, `auto x = T(…)`
                ty, st = self.type_before(k, a + 1)
                bnd = toks[st - 1].t if st - 1 >= a else "{"
                if ty and bnd in ("{", ";", "}", "(", ")", ":") and ty not in EXPR_KW and ty not in ("return",):
                    if ty == "auto" and toks[k + 1].t == "=":
                        t2, _ = self._ctor_after(k + 2, b)
                        if t2:
                            types.setdefault(t, t2)
                    elif ty not in PRIM and ty != "auto":
                        types.setdefault(t, ty)
            if t == "(" and k > a + 1:
                ni = k - 1
                if toks[ni].t == ">":
                    d, x = 0, ni
                    while x > a:
                        if toks[x].t == ">":
                            d += 1
                        elif toks[x].t == "<":
                            d -= 1
                            if d == 0:
                                break
                        elif toks[x].t in (";", "{", "}") or toks[x].t in NOT_TARGS:
                            x = a  # `a < b && c > (d)` is a comparison, not `a<…>(d)`
                            break
                        x -= 1
                    ni = x - 1
                if ni <= a:
                    k += 1
                    continue
                nm = toks[ni].t
                if is_ident(nm) and nm not in CALL_SKIP and not ALLCAPS.match(nm):
                    chain = [nm]
                    m = ni
                    while (m - 2 > a and toks[m - 1].t == "::" and is_ident(toks[m - 2].t)
                           and toks[m - 2].t not in EXPR_KW and toks[m - 2].t not in NONFUNC):
                        chain.insert(0, toks[m - 2].t)
                        m -= 2
                    before = toks[m - 1].t if m - 1 > a else ""
                    recv = None
                    if before == "::":
                        # `::close(fd)`: global-scope call, never an implicit member call
                        chain.insert(0, "")
                        m -= 1
                        before = toks[m - 1].t if m - 1 > a else ""
                    if before in (".", "->"):
                        r = toks[m - 2].t if m - 2 > a else ""
                        # `adc().read()`, `v[0].f()`: a receiver that is not a plain name is unknown
                        recv = r if is_ident(r) and r not in CALL_SKIP or r == "this" else "?"
                        if chain[1:]:
                            chain = chain[-1:]
                    if before == "new" or before == "~":
                        k += 1
                        continue
                    if is_ident(before) and before not in EXPR_KW and before not in CALL_SKIP:
                        # `T x(…)` declaration: not a call
                        k += 1
                        continue
                    rt = types.get(recv) if recv else None
                    self.calls.append({"from": owner, "name": "::".join(chain), "recv": recv, "recv_type": rt,
                                       "line": toks[ni].line, "kind": "call"})
            k += 1

    def _ctor_after(self, k, b):
        toks = self.toks
        chain = []
        x = k
        if x < b and toks[x].t == "new":
            x += 1
        while x < b and (is_ident(toks[x].t) or toks[x].t == "::"):
            chain.append(toks[x].t)
            x += 1
        if chain and chain[-1] in MAKE_FNS and x < b and toks[x].t == "<":
            # `auto p = std::make_unique<T>(…)` → p is a T
            y = x + 1
            arg = []
            while y < b and (is_ident(toks[y].t) or toks[y].t == "::"):
                arg.append(toks[y].t)
                y += 1
            if arg and is_ident(arg[-1]) and y < b and toks[y].t in (">", ","):
                return "".join(arg), y
            return None, k
        if x < b and toks[x].t == "<":
            x = skip_angles(toks, x, b)
        if (chain and x < b and toks[x].t in ("(", "{") and is_ident(chain[-1]) and chain[-1] not in CALL_SKIP
                and (chain[-1][:1].isupper() or chain[-1] in self.classes)):
            # only a type-looking callee names the type: `auto x = make()` says nothing about x
            return "".join(chain), x
        return None, k


def extract_c(text: str, ctx: dict, lang: str) -> dict:
    lx = Lexed(text, "cpp" if lang == "cpp" else "c")
    code, includes, macros = _preprocess(lx, first_only=False)
    p = _C(lx, code, ctx, lang == "cpp")
    p.reqs = []
    p.run()
    conf, ok = "high", True
    if not p.balanced or p.stray:
        code2, includes, macros = _preprocess(lx, first_only=True)
        p2 = _C(lx, code2, ctx, lang == "cpp")
        p2.reqs = []
        p2.run()
        if p2.balanced and not p2.stray:
            p = p2
        conf = "low"
    for name, line, end, fn, params, full in macros:
        sig = full[:200]
        s = symbol(name, name, "macro", line, end, sig=sig, params=params, arity=len(params),
                   pub=p.header and not name.startswith("_"), sig_hash=h12(sig.replace(name, "", 1)),
                   body_hash=h12(full))
        blk = p.docs.leading(line)
        if blk and not blk["used"]:
            blk["used"] = True
            s["doc"] = docparse.parse_block(blk["raw"], doc_style(blk["raw"]), blk["sl"])
        p.syms.append(s)
    for s in p.syms:
        s.pop("_body", None)
    texts = [c[4] for c in lx.comments()] + [v for _, v in lx.strings()]
    return {"symbols": p.syms, "calls": p.calls, "imports": includes + p.imports, "file_doc": p.file_doc,
            "conf": conf, "ok": ok, "reqs": p.reqs, "_strings": lx.strings(), "_texts": texts}
