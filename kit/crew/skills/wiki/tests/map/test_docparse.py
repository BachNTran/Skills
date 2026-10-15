"""Doc comment and docstring parsing (spec §3.1 Doc object)."""
from wikimap.lang.docparse import parse_block, parse_docstring

KEYS = {"style", "brief", "text", "params", "explicit_params", "returns", "raises", "see", "deprecated",
        "line", "end", "hash", "_refs"}


def refs(d):
    return [(t, s) for t, s, _ in d["_refs"]]


def test_doxygen_block():
    raw = """/**
 * @brief Sample the battery.
 *
 * Longer text. See \\ref BatteryMonitor::reset for more.
 * @param[in] now_ms monotonic time in ms
 * @param adc  the ADC port
 * @return millivolts, 0 on error
 * @throws std::runtime_error when the ADC is gone
 * @see update_brownout()
 * @deprecated use sample2
 */"""
    d = parse_block(raw, "doxygen", 10)
    assert set(d) == KEYS
    assert d["brief"] == "Sample the battery."
    assert d["params"] == {"now_ms": "monotonic time in ms", "adc": "the ADC port"}
    assert d["explicit_params"] is True
    assert d["returns"] == "millivolts, 0 on error"
    assert d["raises"] == ["std::runtime_error"]
    assert d["deprecated"] is True
    assert refs(d) == [("BatteryMonitor::reset", "ref"), ("update_brownout()", "see")]
    assert d["see"] == ["BatteryMonitor::reset", "update_brownout()"]
    assert d["line"] == 10 and d["end"] == 20
    assert "*" not in d["text"].split("\n")[0]
    assert len(d["hash"]) == 12


def test_backslash_commands_and_multiline_param():
    raw = "/*!\n \\brief Reset.\n \\param mode how hard\n        to reset\n \\sa Recorder::stop\n */"
    d = parse_block(raw, "doxygen", 1)
    assert d["brief"] == "Reset."
    assert d["params"] == {"mode": "how hard to reset"}
    assert d["see"] == ["Recorder::stop"]


def test_triple_slash_lines_and_line_numbers():
    raw = "/// Average of n values.\n/// @param values the samples\n/// @see util_sum"
    d = parse_block(raw, "doxygen", 40)
    assert d["brief"] == "Average of n values."
    assert d["params"] == {"values": "the samples"}
    assert d["_refs"] == [("util_sum", "see", 42)]
    assert d["end"] == 42


def test_inline_see_mid_line():
    d = parse_block("/** Apply fn to every value. @see util_sum */", "doxygen", 3)
    assert d["brief"] == "Apply fn to every value."
    assert d["see"] == ["util_sum"]


def test_see_url_is_not_a_ref():
    d = parse_block("/** Docs. @see https://example.org/x */", "doxygen", 1)
    assert d["see"] == []


def test_trailing_member_marker():
    d = parse_block("///< east offset", "doxygen", 5)
    assert d["brief"] == "east offset"


def test_plain_line_comment():
    d = parse_block("// Call every 100 ms.\n// Second line.", "line", 7)
    assert d["style"] == "line"
    assert d["brief"] == "Call every 100 ms."
    assert d["explicit_params"] is False


def test_jsdoc():
    raw = """/**
 * Multiply two numbers.
 * @param {number} a - first factor
 * @param {number} [b=1] - second factor
 * @param {Object} opts - options
 * @param {string} opts.mode - nested property
 * @returns {number} the product, see {@link add}
 */"""
    d = parse_block(raw, "jsdoc", 1)
    assert d["brief"] == "Multiply two numbers."
    assert d["params"] == {"a": "first factor", "b": "second factor", "opts": "options"}
    assert d["returns"] == "the product, see {@link add}"
    assert d["see"] == ["add"]


def test_rustdoc_sections():
    raw = "/// Adds two numbers.\n///\n/// # Arguments\n///\n/// * `x` - the first\n/// * `y` - the second\n///\n/// # Errors\n/// Overflow returns Err."
    d = parse_block(raw, "rustdoc", 1)
    assert d["brief"] == "Adds two numbers."
    assert d["params"] == {"x": "the first", "y": "the second"}
    assert d["explicit_params"] is True
    assert d["raises"] == ["Overflow returns Err."]


def test_godoc_first_sentence():
    d = parse_block("// Hello says hi. It never fails.", "godoc", 3)
    assert d["brief"] == "Hello says hi."
    assert d["style"] == "godoc"


def test_csharp_xml_doc():
    raw = '/// <summary>Adds numbers.</summary>\n/// <param name="a">first</param>\n/// <returns>the sum</returns>'
    d = parse_block(raw, "doxygen", 1)
    assert d["brief"] == "Adds numbers."
    assert d["params"] == {"a": "first"}
    assert d["returns"] == "the sum"


def test_brief_and_text_limits():
    d = parse_block("/** " + "word " * 100 + "*/", "doxygen", 1)
    assert len(d["brief"]) <= 200
    big = parse_block("/**\n" + (" * " + "x" * 100 + "\n") * 400 + " */", "doxygen", 1)
    assert len(big["text"]) <= 16384


def test_hash_ignores_whitespace_only():
    a = parse_block("/** Read the  value. */", "doxygen", 1)
    b = parse_block("/**\n * Read the\n * value.\n */", "doxygen", 9)
    c = parse_block("/** Read the values. */", "doxygen", 1)
    assert a["hash"] == b["hash"]
    assert a["hash"] != c["hash"]


def test_google_docstring():
    text = """Run the loop.

Args:
    n: number of samples.
    mode (str): how strictly to
        validate.
    *args: extra positional.

Returns:
    Number of rows stored.

Raises:
    ValueError: when n < 0.

See Also:
    step, Engine.flush
"""
    d = parse_docstring(text, 12)
    assert d["style"] == "docstring"
    assert d["brief"] == "Run the loop."
    assert d["params"] == {"n": "number of samples.", "mode": "how strictly to validate.", "*args": "extra positional."}
    assert d["explicit_params"] is True
    assert d["returns"] == "Number of rows stored."
    assert d["raises"] == ["ValueError"]
    assert d["see"] == ["step", "Engine.flush"]
    assert d["line"] == 12


def test_numpy_docstring():
    text = """Store one sample.

Parameters
----------
i : int
    Sample index.
x, y : float
    Coordinates.

Returns
-------
int
    The new row count.

Raises
------
KeyError
    If missing.
"""
    d = parse_docstring(text, 1)
    assert d["brief"] == "Store one sample."
    assert d["params"] == {"i": "Sample index.", "x": "Coordinates.", "y": "Coordinates."}
    assert d["returns"] == "int The new row count."
    assert d["raises"] == ["KeyError"]


def test_sphinx_docstring_and_roles():
    text = """Build an engine. Uses :func:`traced` and :class:`~pkg.core.Store`.

:param store: target store
:type store: Store
:param int retries: how often
:returns: the engine
:rtype: Engine
:raises ValueError: when store is None
"""
    d = parse_docstring(text, 5)
    assert d["brief"] == "Build an engine."
    assert d["params"] == {"store": "target store", "retries": "how often"}
    assert d["returns"] == "the engine"
    assert d["raises"] == ["ValueError"]
    assert refs(d) == [("traced", "func"), ("pkg.core.Store", "class")]
    assert d["_refs"][0][2] == 5


def test_docstring_without_sections():
    d = parse_docstring("Decode one frame.\n\nMore words.", 3)
    assert d["brief"] == "Decode one frame."
    assert d["params"] == {} and d["explicit_params"] is False


def test_evil_text_kept_verbatim():
    t = 'Return markup. <script>alert(1)</script> <img src=x onerror=alert(1)>'
    d = parse_docstring(t, 1)
    assert d["text"] == t
    assert "<script>alert(1)</script>" in d["brief"] or d["brief"] == "Return markup."
    blk = parse_block("/** <script>x()</script> */", "doxygen", 1)
    assert blk["text"] == "<script>x()</script>"
