"""Comment/string-aware lexer and shared token helpers for the brace-language adapters.

`strip()` is the public contract (spec §3.1). Adapters use `Lexed`, `tokenize`, `brackets`,
`DocIndex` and the hashing helpers so every language hashes and attaches docs the same way.
Repo text is data: nothing here evaluates it.
"""
from __future__ import annotations

import bisect
import hashlib
import re

DIALECTS = ("c", "cpp", "js", "ts", "go", "rust", "clike")

# previous-token values after which a `/` starts a regex literal (JS/TS)
_RX_WORDS = {"return", "typeof", "instanceof", "in", "of", "new", "delete", "void", "throw",
             "case", "do", "else", "yield", "await"}
_RX_AFTER = set("(,=:[!&|?{};+-*%<>~^")
_RAW_PREFIX = {"R", "u8R", "uR", "UR", "LR"}
_IDENT_START = re.compile(r"[^\W\d]|\$")
_IDENT = re.compile(r"[\w$]+")


def h12(s: str) -> str:
    """First 12 hex chars of sha256 over `s` (UTF-8)."""
    return hashlib.sha256(s.encode("utf-8", "surrogatepass")).hexdigest()[:12]


class Lexed:
    """One lexed file: original text, blanked code, spans and line lookup.

    spans: (kind, start, end) with kind 'c' comment, 's' string, 'r' regex, 'p' pp text,
    'j' JSX text. In `code`, comments/'p'/'j' become spaces; strings and regexes become a
    `"…"` placeholder of the same length (newlines kept), so offsets and lines never move.
    """

    def __init__(self, text: str, dialect: str, jsx: bool = False):
        self.text = text
        self.dialect = dialect
        self.nl = [m.start() for m in re.finditer("\n", text)]
        self.spans: list[tuple[str, int, int]] = []
        _Scanner(self, jsx).run()
        self.spans.sort(key=lambda s: s[1])
        buf = list(text)
        self.strmap: dict[int, int] = {}
        for kind, a, b in self.spans:
            if kind in ("s", "r"):
                self.strmap[a] = b
                for k in range(a, b):
                    if buf[k] != "\n":
                        buf[k] = " "
                if b - a >= 2:
                    buf[a] = '"'
                    # keep the closing quote on the last non-newline position
                    e = b - 1
                    while e > a and buf[e] == "\n":
                        e -= 1
                    buf[e] = '"' if e > a else buf[e]
                elif b - a == 1 and buf[a] != "\n":
                    buf[a] = " "
            else:
                for k in range(a, b):
                    if buf[k] != "\n":
                        buf[k] = " "
        self.code = "".join(buf)
        self.nocomment = None

    def line_of(self, pos: int) -> int:
        return bisect.bisect_right(self.nl, pos - 1) + 1 if pos > 0 else 1

    def line_start(self, line: int) -> int:
        return 0 if line <= 1 else (self.nl[line - 2] + 1 if line - 2 < len(self.nl) else len(self.text))

    def comments(self) -> list[tuple[int, int, int, int, str]]:
        """[(start, end, start_line, end_line, raw)] in file order."""
        out = []
        for kind, a, b in self.spans:
            if kind == "c":
                out.append((a, b, self.line_of(a), self.line_of(max(a, b - 1)), self.text[a:b]))
        return out

    def literal(self, a: int) -> str:
        """Content of the string literal starting at `a` (delimiters stripped)."""
        b = self.strmap.get(a)
        if b is None:
            return ""
        return _unquote(self.text[a:b])

    def strings(self) -> list[tuple[int, str]]:
        return [(self.line_of(a), _unquote(self.text[a:b])) for kind, a, b in self.spans if kind == "s"]


def _unquote(s: str) -> str:
    m = re.match(r'^(?:u8|[uUL]|b|br|r|@\$?|\$@?)?R?"([^(\s"]{0,16})\((.*)\)\1"$', s, re.S)
    if m and (s.startswith(("R", "u8R", "uR", "UR", "LR"))):
        return m.group(2)
    m = re.match(r'^(?:b?r)(#*)"(.*)"\1$', s, re.S)
    if m:
        return m.group(2)
    for q in ('"""', "'''"):
        if s.startswith(q) and s.endswith(q) and len(s) >= 6:
            return s[3:-3]
    s2 = s.lstrip("@$bLuU8")
    if s2[:1] in ('"', "'", "`") and len(s2) >= 2 and s2[-1] == s2[0]:
        return s2[1:-1]
    # JS template pieces: "`abc${", "}abc${", "}abc`"
    if s[:1] in ("`", "}"):
        s = s[1:]
        if s.endswith("${"):
            s = s[:-2]
        elif s.endswith("`"):
            s = s[:-1]
        return s
    return s[1:-1] if len(s) >= 2 else s


class _Scanner:
    def __init__(self, lx: Lexed, jsx: bool):
        self.lx = lx
        self.t = lx.text
        self.n = len(self.t)
        d = lx.dialect
        self.js = d in ("js", "ts")
        self.cfam = d in ("c", "cpp")
        self.cpp = d == "cpp"
        self.rust = d == "rust"
        self.go = d == "go"
        self.clike = d == "clike"
        self.jsx = jsx and self.js
        self.prev = ""  # last significant code token

    def add(self, kind, a, b):
        if b > a:
            self.lx.spans.append((kind, a, b))

    def run(self):
        i = 0
        while i < self.n:
            i = self.code(i, False)
            if i < self.n:  # stray closing brace at top level
                i += 1

    def regex_ok(self) -> bool:
        p = self.prev
        return p == "" or p in _RX_AFTER or p in _RX_WORDS

    def code(self, i: int, until_brace: bool) -> int:
        """Scan code from i; with until_brace, return the index of the unmatched `}`."""
        t, n = self.t, self.n
        depth = 0
        while i < n:
            c = t[i]
            if c in " \t\r\n\f\v":
                i += 1
                continue
            nx = t[i + 1] if i + 1 < n else ""
            if c == "/" and nx == "/":
                j = t.find("\n", i)
                j = n if j < 0 else j
                self.add("c", i, j)
                i = j
                continue
            if c == "/" and nx == "*":
                j = self.block_comment(i)
                self.add("c", i, j)
                i = j
                continue
            if until_brace and c == "}" and depth == 0:
                return i
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            if c == "#" and self.cfam and self.at_line_start(i):
                i = self.directive(i)
                continue
            if c == '"':
                if (self.clike and t.startswith('"""', i)) or (self.js and False):
                    j = t.find('"""', i + 3)
                    j = n if j < 0 else j + 3
                else:
                    j = self.quoted(i, '"')
                self.add("s", i, j)
                self.prev = '"'
                i = j
                continue
            if c == "'":
                if self.rust:
                    j = self.rust_quote(i)
                    if j is None:  # lifetime
                        self.prev = "'"
                        i += 1
                        continue
                else:
                    j = self.quoted(i, "'")
                self.add("s", i, j)
                self.prev = '"'
                i = j
                continue
            if c == "`":
                if self.js:
                    j = self.template(i)
                    self.prev = '"'
                    i = j
                    continue
                if self.go:
                    j = t.find("`", i + 1)
                    j = n if j < 0 else j + 1
                    self.add("s", i, j)
                    self.prev = '"'
                    i = j
                    continue
            if c == "@" and self.clike and nx == '"':
                j = self.verbatim(i + 1)
                self.add("s", i, j)
                self.prev = '"'
                i = j
                continue
            if c == "/" and self.js and self.regex_ok():
                j = self.regex(i)
                if j is not None:
                    self.add("r", i, j)
                    self.prev = '"'
                    i = j
                    continue
            if c == "<" and self.jsx and self.regex_ok() and (nx.isalpha() or nx == ">"):
                j = self.jsx_element(i)
                self.prev = '"'
                i = j
                continue
            if c.isdigit():
                j = i + 1
                while j < n and (t[j].isalnum() or t[j] in "._" or
                                 (self.cpp and t[j] == "'" and j + 1 < n and t[j + 1].isalnum())):
                    j += 1
                self.prev = "0"
                i = j
                continue
            if _IDENT_START.match(c):
                m = _IDENT.match(t, i)
                j = m.end()
                word = t[i:j]
                if j < n and t[j] == '"':
                    if self.cpp and word in _RAW_PREFIX:
                        k = self.raw_cpp(j)
                        self.add("s", i, k)
                        self.prev = '"'
                        i = k
                        continue
                    if self.cfam and word in ("u8", "u", "U", "L"):
                        k = self.quoted(j, '"')
                        self.add("s", i, k)
                        self.prev = '"'
                        i = k
                        continue
                    if self.rust and word in ("b", "r", "br"):
                        k = self.rust_raw(j) if "r" in word else self.quoted(j, '"')
                        self.add("s", i, k)
                        self.prev = '"'
                        i = k
                        continue
                if self.rust and word in ("r", "br") and j < n and t[j] == "#":
                    k = j
                    while k < n and t[k] == "#":
                        k += 1
                    if k < n and t[k] == '"':
                        k2 = self.rust_raw(j)
                        self.add("s", i, k2)
                        self.prev = '"'
                        i = k2
                        continue
                if self.rust and word == "b" and j < n and t[j] == "'":
                    k = self.rust_quote(j)
                    if k is not None:
                        self.add("s", i, k)
                        self.prev = '"'
                        i = k
                        continue
                self.prev = word
                i = j
                continue
            self.prev = c
            i += 1
        return n

    # -- helpers -------------------------------------------------------------------------
    def at_line_start(self, i: int) -> bool:
        k = self.t.rfind("\n", 0, i)
        return self.t[k + 1:i].strip() == ""

    def directive(self, i: int) -> int:
        """C/C++ preprocessor line: `<…>` include targets and #error text are not code."""
        t, n = self.t, self.n
        m = re.compile(r"#\s*(\w*)").match(t, i)
        name = m.group(1) if m else ""
        j = m.end() if m else i + 1
        if name in ("include", "import", "include_next"):
            k = j
            while k < n and t[k] in " \t":
                k += 1
            if k < n and t[k] == "<":
                e = t.find(">", k)
                nl = t.find("\n", k)
                if e >= 0 and (nl < 0 or e < nl):
                    self.add("p", k, e + 1)
                    return e + 1
            return j
        if name in ("error", "warning"):
            e = t.find("\n", j)
            e = n if e < 0 else e
            self.add("p", j, e)
            return e
        self.prev = ""
        return j

    def block_comment(self, i: int) -> int:
        t, n = self.t, self.n
        if not self.rust:
            j = t.find("*/", i + 2)
            return n if j < 0 else j + 2
        depth, j = 0, i
        while j < n:
            if t.startswith("/*", j):
                depth += 1
                j += 2
            elif t.startswith("*/", j):
                depth -= 1
                j += 2
                if depth == 0:
                    return j
            else:
                j += 1
        return n

    def quoted(self, i: int, q: str) -> int:
        t, n = self.t, self.n
        j = i + 1
        while j < n:
            c = t[j]
            if c == "\\":
                j += 2
                continue
            if c == q:
                return j + 1
            if c == "\n" and not (self.rust or self.go and q == "`"):
                return j  # unterminated: stop at end of line
            j += 1
        return n

    def verbatim(self, i: int) -> int:  # C# @"…" with "" escapes
        t, n = self.t, self.n
        j = i + 1
        while j < n:
            if t[j] == '"':
                if j + 1 < n and t[j + 1] == '"':
                    j += 2
                    continue
                return j + 1
            j += 1
        return n

    def raw_cpp(self, i: int) -> int:  # i at the quote of R"delim( … )delim"
        t = self.t
        k = t.find("(", i + 1)
        if k < 0 or k - i - 1 > 16:
            return self.quoted(i, '"')
        delim = t[i + 1:k]
        e = t.find(")" + delim + '"', k + 1)
        return self.n if e < 0 else e + len(delim) + 2

    def rust_raw(self, i: int) -> int:  # i at first '#' or the quote
        t = self.t
        k = i
        while k < self.n and t[k] == "#":
            k += 1
        hashes = k - i
        if k >= self.n or t[k] != '"':
            return k
        e = t.find('"' + "#" * hashes, k + 1)
        return self.n if e < 0 else e + 1 + hashes

    def rust_quote(self, i: int):
        """Char literal end, or None for a lifetime / label like 'a."""
        t, n = self.t, self.n
        if i + 1 < n and t[i + 1] == "\\":
            j = t.find("'", i + 2)
            if t[i + 2:i + 3] == "'":  # '\''
                j = t.find("'", i + 3)
            return n if j < 0 else j + 1
        if i + 2 < n and t[i + 2] == "'":
            return i + 3
        return None

    def regex(self, i: int):
        t, n = self.t, self.n
        j, cls = i + 1, False
        while j < n:
            c = t[j]
            if c == "\n":
                return None
            if c == "\\":
                j += 2
                continue
            if cls:
                if c == "]":
                    cls = False
            elif c == "[":
                cls = True
            elif c == "/":
                j += 1
                while j < n and (t[j].isalnum() or t[j] == "_"):
                    j += 1
                return j
            j += 1
        return None

    def template(self, i: int) -> int:
        t, n = self.t, self.n
        start, j = i, i + 1
        while j < n:
            c = t[j]
            if c == "\\":
                j += 2
                continue
            if c == "`":
                self.add("s", start, j + 1)
                return j + 1
            if c == "$" and j + 1 < n and t[j + 1] == "{":
                self.add("s", start, j + 2)
                saved = self.prev
                self.prev = "("
                k = self.code(j + 2, True)
                self.prev = saved
                if k >= n:
                    return n
                start, j = k, k + 1
                continue
            j += 1
        self.add("s", start, n)
        return n

    def jsx_element(self, i: int) -> int:
        """Blank a JSX element as text, scanning `{…}` holes as code."""
        t, n = self.t, self.n
        depth, j, seg = 0, i, i
        while j < n:
            c = t[j]
            if c == "<":
                closing = j + 1 < n and t[j + 1] == "/"
                k = j + 1
                while k < n and t[k] != ">":
                    if t[k] in "\"'":
                        k = self.quoted(k, t[k])
                        continue
                    if t[k] == "{":
                        self.add("j", seg, k + 1)
                        saved = self.prev
                        self.prev = "("
                        k = self.code(k + 1, True)
                        self.prev = saved
                        seg = k
                    k += 1
                if k >= n:
                    break
                self_close = t[k - 1] == "/"
                if closing:
                    depth -= 1
                elif not self_close:
                    depth += 1
                j = k + 1
                if depth <= 0:
                    self.add("j", seg, j)
                    return j
                continue
            if c == "{":
                self.add("j", seg, j + 1)
                saved = self.prev
                self.prev = "("
                k = self.code(j + 1, True)
                self.prev = saved
                seg = k
                j = k + 1
                continue
            j += 1
        self.add("j", seg, n)
        return n


def strip(text: str, dialect: str) -> tuple[str, list[tuple[int, int, str]], list[tuple[int, str]]]:
    """Return (code with comments+strings blanked, newlines kept), comments, string literals.

    comments: [(start_line, end_line, raw_comment_text)]; strings: [(line, literal_content)].
    """
    if dialect not in DIALECTS:
        raise ValueError(f"unknown dialect {dialect!r}")
    lx = Lexed(text, dialect)
    return lx.code, [(c[2], c[3], c[4]) for c in lx.comments()], lx.strings()


# ---------------------------------------------------------------------------------------
# tokens
# ---------------------------------------------------------------------------------------

_TOK = re.compile(r'"[ \n]*"|(?:[^\W\d]|\$)[\w$]*|\d[\w.\']*|::|->|\.\.\.|\?\.|=>|[=!]==?|[<>+\-*/%&|^]=|&&|\|\||\+\+|--|\S')


class Tok:
    __slots__ = ("t", "pos", "line")

    def __init__(self, t, pos, line):
        self.t, self.pos, self.line = t, pos, line

    def __repr__(self):
        return f"Tok({self.t!r}@{self.line})"


def tokenize(lx: Lexed, code: str | None = None) -> list[Tok]:
    code = lx.code if code is None else code
    out = []
    nl = lx.nl
    for m in _TOK.finditer(code):
        p = m.start()
        out.append(Tok(m.group(), p, bisect.bisect_right(nl, p - 1) + 1 if p > 0 else 1))
    return out


def is_ident(s: str) -> bool:
    return bool(s) and (s[0].isalpha() or s[0] in "_$") and s.replace("$", "_").isidentifier()


def brackets(toks: list[Tok]) -> tuple[dict[int, int], bool]:
    """Map each opening ( [ { index to its closer and back; second value False on imbalance."""
    pairs = {"(": ")", "[": "]", "{": "}"}
    closers = {")": "(", "]": "[", "}": "{"}
    stack: list[int] = []
    match: dict[int, int] = {}
    ok = True
    for i, tk in enumerate(toks):
        t = tk.t
        if t in pairs:
            stack.append(i)
        elif t in closers:
            # tolerate a mismatched ( ) inside braces: pop to the matching opener kind
            k = len(stack) - 1
            while k >= 0 and toks[stack[k]].t != closers[t]:
                k -= 1
            if k < 0:
                ok = False
                continue
            if k != len(stack) - 1:
                ok = False
            o = stack[k]
            del stack[k:]
            match[o] = i
            match[i] = o
    if stack:
        ok = False
    return match, ok


def skip_angles(toks: list[Tok], i: int, stop: int | None = None) -> int:
    """i at '<': index just past the matching '>' (or i+1 when it does not look like a template)."""
    stop = len(toks) if stop is None else stop
    depth, j = 0, i
    while j < stop:
        t = toks[j].t
        if t == "<":
            depth += 1
        elif t == ">":
            depth -= 1
            if depth == 0:
                return j + 1
        elif t == ">=":
            depth -= 1
            if depth == 0:
                return j + 1
        elif t in (";", "{", "}") or (t == ")" and depth > 0 and False):
            return i + 1
        elif t == "(":
            # skip balanced parens inside template args
            d2 = 0
            while j < stop:
                if toks[j].t == "(":
                    d2 += 1
                elif toks[j].t == ")":
                    d2 -= 1
                    if d2 == 0:
                        break
                j += 1
        j += 1
    return i + 1


def hash_tokens(lx: Lexed, toks: list[Tok], a: int, b: int, skip: list[tuple[int, int]] | None = None) -> str:
    """sha12 over tokens a..b-1 (comments gone, whitespace gone, string contents kept)."""
    parts = []
    k = a
    skip = sorted(skip or [])
    si = 0
    while k < b:
        while si < len(skip) and skip[si][1] < k:
            si += 1
        if si < len(skip) and skip[si][0] <= k <= skip[si][1]:
            parts.append("{}")
            k = skip[si][1] + 1
            continue
        tk = toks[k]
        if tk.t.startswith('"') and tk.pos in lx.strmap:
            parts.append(lx.text[tk.pos:lx.strmap[tk.pos]])
        else:
            parts.append(tk.t)
        k += 1
    return h12("\x1f".join(parts))


def words(toks: list[Tok], a: int, b: int, kw: set[str] | frozenset = frozenset()) -> list[str]:
    s = {toks[k].t for k in range(a, b) if is_ident(toks[k].t) and toks[k].t not in kw}
    return sorted(s)[:200]


def pretty(parts: list[str]) -> str:
    """Join signature tokens with C-ish spacing."""
    out = ""
    for p in parts:
        if not out:
            out = p
            continue
        last = out[-1]
        if p in (",", ")", "]", ";", "::", ">", ":", "?", "!") or p.startswith("::"):
            out += p
        elif p == "..." and last in "(,":
            out += p
        elif p in ("(", "[", "<"):
            out += p
        elif last in "([<~!" or out.endswith("::") or out.endswith("..."):
            out += p
        elif p in ("&", "*", "&&") and (last.isalnum() or last in "_>)"):
            out += p
        else:
            out += " " + p
    out = re.sub(r"(,|(?<!:):(?!:))(?=[^\s:,)\]>])", r"\1 ", out)
    return out


def src_text(lx: Lexed, toks: list[Tok], a: int, b: int) -> str:
    """Source text of tokens a..b-1: comments dropped, whitespace collapsed, literals kept."""
    if b <= a:
        return ""
    start = toks[a].pos
    last = toks[b - 1]
    end = lx.strmap.get(last.pos, last.pos + len(last.t)) if last.t.startswith('"') else last.pos + len(last.t)
    if lx.nocomment is None:
        buf = list(lx.text)
        for kind, x, y in lx.spans:
            if kind in ("c", "p", "j"):
                for k in range(x, y):
                    if buf[k] != "\n":
                        buf[k] = " "
        lx.nocomment = "".join(buf)
    return " ".join(lx.nocomment[start:end].split())


# ---------------------------------------------------------------------------------------
# symbols and doc attachment
# ---------------------------------------------------------------------------------------

def symbol(qual: str, name: str, kind: str, line: int, end: int, **kw) -> dict:
    s = {"qual": qual, "name": name, "kind": kind, "line": line, "end": max(end, line), "sig": "",
         "params": [], "arity": 0, "decl": False, "pub": False, "parent": None, "bases": [],
         "virtual": False, "pure": False, "override": False, "static": False, "members": {},
         "doc": None, "sig_hash": "", "body_hash": "", "test": False, "words": [], "ignore": []}
    s.update(kw)
    return s


_LINE_MARK = re.compile(r"^\s*(//[/!]?<?|#)")


class DocIndex:
    """Groups comments into blocks and finds the doc block attached to a code line."""

    def __init__(self, lx: Lexed, code: str | None = None):
        self.lx = lx
        code = lx.code if code is None else code
        self.code = code
        self.blocks: list[dict] = []
        prev = None
        for a, b, sl, el, raw in lx.comments():
            ls = lx.line_start(sl)
            trailing = code[ls:a].strip() != ""
            marker = raw[:4]
            is_line = raw.startswith("//")
            back = raw.startswith(("///<", "//!<", "/**<", "/*!<"))
            if (prev is not None and is_line and prev["line"] and not trailing and not back
                    and not prev["back"] and sl == prev["el"] + 1 and _same_style(prev["raw0"], raw)):
                prev["raw"] += "\n" + raw
                prev["el"] = el
                prev["end"] = b
                continue
            prev = {"sl": sl, "el": el, "start": a, "end": b, "raw": raw, "raw0": raw, "line": is_line,
                    "trailing": trailing, "back": back, "used": False}
            del marker
            self.blocks.append(prev)
        self.by_end = {}
        for blk in self.blocks:
            if not blk["trailing"] and not blk["back"]:
                self.by_end[blk["el"]] = blk
        self.back_by_line = {blk["sl"]: blk for blk in self.blocks if blk["back"]}
        lines = code.split("\n")
        self.blank = [ln.strip() == "" for ln in lines]

    def line_blank(self, line: int) -> bool:
        return 1 <= line <= len(self.blank) and self.blank[line - 1]

    def leading(self, head_line: int, head_pos: int | None = None):
        """Block ending on head_line-1, or head_line-2 with a blank line between, no code between."""
        if head_pos is not None:
            blk = self.by_end.get(head_line)
            if blk and blk["end"] <= head_pos:
                return blk
        for gap in (1, 2):
            blk = self.by_end.get(head_line - gap)
            if blk is None:
                if not self.line_blank(head_line - gap):
                    return None
                continue
            # the lines between must be blank in code (comments are already blanked)
            if gap == 2 and not self.line_blank(head_line - 1):
                return None
            if not self.code_free(blk):
                return None
            return blk
        return None

    def code_free(self, blk) -> bool:
        # code must not share the comment's last line after the comment
        lx = self.lx
        e = blk["end"]
        nl = lx.text.find("\n", e)
        nl = len(lx.text) if nl < 0 else nl
        return self.code[e:nl].strip() == ""

    def trailing_back(self, line: int):
        return self.back_by_line.get(line)


def _same_style(a: str, b: str) -> bool:
    def st(s):
        if s.startswith(("///", "//!")):
            return "doc"
        return "plain"
    return st(a) == st(b)


def doc_style(raw: str, default_line: str = "line", doc_style_name: str = "doxygen") -> str:
    """Style for a C-family comment block: doxygen markers or @cmd/\\cmd, else plain line."""
    s = raw.lstrip()
    if s.startswith(("/**", "/*!", "///", "//!")) and not s.startswith("/**/"):
        return doc_style_name
    if re.search(r"(?:^|\s)[@\\](?:brief|param|return|returns|see|sa|ref|file|throws?|note|deprecated|retval|details)\b", raw):
        return doc_style_name
    return default_line
