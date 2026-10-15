"""Lexer torture tests (spec §3.1 `lex.strip`, §9 WP1)."""
import pytest

from wikimap.lang import lex
from wikimap.lang.extract import extract


def strip(text, dialect):
    code, comments, strings = lex.strip(text, dialect)
    assert len(code) == len(text), "offsets must not move"
    assert code.count("\n") == text.count("\n"), "newlines kept"
    return code, comments, strings


def braces(code):
    return code.count("{"), code.count("}")


def test_cpp_raw_string_with_brace():
    text = 'auto s = R"x(})x";\nint f() { return 1; }\n'
    code, _, strings = strip(text, "cpp")
    assert braces(code) == (1, 1)
    assert (1, "})") not in strings and (1, "}") in strings


def test_cpp_raw_string_prefixes_and_multiline():
    text = 'auto a = u8R"(a { b)";\nauto b = LR"d(\n}\n)d";\n'
    code, _, strings = strip(text, "cpp")
    assert "{" not in code and "}" not in code
    assert [s for _, s in strings] == ["a { b", "\n}\n"]


def test_char_literals_and_escapes():
    text = "char a = '{'; char b = '\\''; char c = '}';\nconst char* s = \"\\\"}\";\n"
    code, _, strings = strip(text, "c")
    assert braces(code) == (0, 0)
    assert [s for _, s in strings] == ["{", "\\'", "}", '\\"}']


def test_cpp_digit_separator_is_not_a_char():
    code, _, strings = strip("int n = 1'000'000; char c = '{';\n", "cpp")
    assert strings == [(1, "{")]
    assert "1'000'000" in code


def test_comments_lines_and_text():
    text = "int a; // tail\n/* one\n two */ int b;\n/// doc\n"
    code, comments, _ = strip(text, "c")
    assert comments == [(1, 1, "// tail"), (2, 3, "/* one\n two */"), (4, 4, "/// doc")]
    assert "tail" not in code and "two" not in code and "int b" in code


def test_comment_markers_inside_strings_are_not_comments():
    text = 'const char* u = "http://x/*y*/";\nint z; // real\n'
    _, comments, strings = strip(text, "c")
    assert comments == [(2, 2, "// real")]
    assert strings == [(1, "http://x/*y*/")]


def test_include_angle_and_error_text():
    text = "#include <it's.h>\n#error don't do { this\nint f() { return 0; }\n"
    code, _, strings = strip(text, "c")
    assert strings == []
    assert braces(code) == (1, 1)


def test_if0_brace_is_skipped_by_c_adapter():
    text = "#if 0\nvoid dead() {\n#endif\nint live(void) { return 1; }\n"
    r = extract("a.c", text.encode())
    assert r["conf"] == "high"
    assert [s["qual"] for s in r["symbols"]] == ["live"]


def test_js_regex_vs_division():
    text = "const re = /}/g;\nconst x = a / b / c;\nfunction f() { return /\\/{/.test(s); }\n"
    code, _, strings = strip(text, "js")
    assert braces(code) == (1, 1)
    assert "a / b / c" in code
    assert strings == []  # regex literals are blanked but are not string literals


def test_js_regex_after_keyword_and_paren():
    text = "if (ok) return /a}/.test(s);\nlet y = (n) / 2;\n"
    code, _, _ = strip(text, "js")
    assert "}" not in code
    assert "(n) / 2" in code


def test_js_nested_template_literals():
    text = "const s = `a ${`b ${x} }`} c`;\nfunction g() { return 1; }\n"
    code, _, strings = strip(text, "js")
    assert braces(code) == (1, 1)
    assert "x" in code.split("\n")[0]  # the ${x} hole is code
    assert [s for _, s in strings] == ["a ", "b ", " }", " c"]


def test_ts_template_hole_with_object_literal():
    text = "const s = `v=${ {a: 1}.a }`;\n"
    code, _, strings = strip(text, "ts")
    assert braces(code) == (1, 1)
    assert [s for _, s in strings] == ["v=", ""]


def test_jsx_text_is_blanked_but_holes_are_code():
    lx = lex.Lexed("const v = <div title=\"}\">don't {go(1)}</div>;\nfunction h() {}\n", "js", jsx=True)
    assert "go(1)" in lx.code
    assert "don" not in lx.code
    assert lx.code.count("{") == lx.code.count("}") == 1


def test_rust_lifetimes_raw_strings_nested_comments():
    text = (
        "fn f<'a>(x: &'a str) -> char {\n"
        "    let r = r#\"}\"#;\n"
        "    /* outer /* inner } */ still comment { */\n"
        "    let c = '}';\n"
        "    let b = b'{';\n"
        "    'outer: loop { break 'outer; }\n"
        "    'x'\n"
        "}\n"
    )
    code, comments, strings = strip(text, "rust")
    assert braces(code) == (2, 2)
    assert [s for _, s in strings] == ["}", "}", "{", "x"]
    assert comments[0][2].startswith("/* outer") and comments[0][2].endswith("{ */")


def test_go_backtick_raw_string():
    text = "func f() string {\n\treturn `}{\n\\n`\n}\n"
    code, _, strings = strip(text, "go")
    assert braces(code) == (1, 1)
    assert strings == [(2, "}{\n\\n")]


def test_clike_verbatim_and_text_block():
    text = 'var p = @"C:\\x""}";\nString t = """\n}\n""";\nclass A { }\n'
    code, _, strings = strip(text, "clike")
    assert braces(code) == (1, 1)
    assert len(strings) == 2


def test_unterminated_string_stops_at_eol():
    code, _, _ = strip('char* s = "oops;\nint f() { }\n', "c")
    assert braces(code) == (1, 1)


def test_unknown_dialect_rejected():
    with pytest.raises(ValueError):
        lex.strip("x", "cobol")


def test_tokenize_and_brackets():
    lx = lex.Lexed("a::b->c(x, \"s\") { [1] }", "cpp")
    toks = lex.tokenize(lx)
    assert [t.t for t in toks][:6] == ["a", "::", "b", "->", "c", "("]
    match, ok = lex.brackets(toks)
    assert ok
    o = [t.t for t in toks].index("{")
    assert toks[match[o]].t == "}"


def test_hash_tokens_ignores_whitespace_and_comments():
    a = lex.Lexed("{ return f(1, \"x\"); }", "c")
    b = lex.Lexed("{\n  // note\n  return f( 1,\"x\" ) ; /* c */\n}", "c")
    c = lex.Lexed("{ return f(1, \"y\"); }", "c")

    def h(lx):
        toks = lex.tokenize(lx)
        return lex.hash_tokens(lx, toks, 0, len(toks))
    assert h(a) == h(b)
    assert h(a) != h(c)  # string contents are kept


def test_src_text_drops_comments_collapses_space():
    lx = lex.Lexed("int /* c */ f(int a,\n      int b) // t\n", "c")
    toks = lex.tokenize(lx)
    assert lex.src_text(lx, toks, 0, len(toks)) == "int f(int a, int b)"


def test_long_file_lexes_fast():
    import time
    text = "int f(int x) { return x /* c */ + 1; } // t\n" * 6000
    t0 = time.perf_counter()
    lex.strip(text, "cpp")
    assert time.perf_counter() - t0 < 1.0
