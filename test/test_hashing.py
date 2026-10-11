import pytest

from modgate.analyze import Project
from modgate.hashing import HashCache, content_hash, module_hash, normalize_text, short, split_frontmatter

from conftest import write


@pytest.mark.req("REQ-MG-001")
def test_normalization_crlf_trailing_ws_final_newline():
    a = content_hash(b"line one  \r\nline two\t\r\n\r\n\r\n", "x.txt")
    b = content_hash(b"line one\nline two", "x.txt")
    assert a == b
    assert normalize_text(b"a \r\nb\n\n") == "a\nb\n"


@pytest.mark.req("REQ-MG-001")
def test_binary_is_hashed_raw():
    blob = b"\x89PNG\x00\x01\r\n  "
    assert normalize_text(blob) is None
    assert content_hash(blob, "x.png") != content_hash(blob.replace(b"\r\n", b"\n"), "x.png")


@pytest.mark.req("REQ-MG-002")
def test_doc_hash_excludes_frontmatter():
    body = "# Title\n\nBody text.\n"
    a = content_hash(("---\nstatus: draft\nversion: 1\n---\n" + body).encode(), "x.md")
    b = content_hash(("---\nstatus: approved\napproved: 1 sha256:abc\n---\n" + body).encode(), "x.md")
    assert a == b
    assert a != content_hash(("---\nstatus: draft\n---\n# Title\n\nOther.\n").encode(), "x.md")
    fm, rest = split_frontmatter("---\na: 1\n---\nbody\n")
    assert fm == "a: 1\n" and rest == "body\n"


@pytest.mark.req("REQ-MG-002")
def test_frontmatter_only_stripped_for_markdown():
    text = b"---\na: 1\n---\nx\n"
    assert content_hash(text, "x.md") != content_hash(text, "x.yaml")


@pytest.mark.req("REQ-MG-003")
def test_module_hash_is_order_independent_and_includes_deps():
    files = {"b.txt": "sha256:2", "a.txt": "sha256:1"}
    h = module_hash(files, {})
    assert h == module_hash(dict(reversed(list(files.items()))), {})
    assert h != module_hash(files, {"dep": "sha256:9"})
    assert module_hash(files, {"dep": "sha256:9"}) != module_hash(files, {"dep": "sha256:8"})
    assert short(h).startswith("sha256:") and len(short(h)) == 19


@pytest.mark.req("REQ-MG-003")
def test_module_hash_excludes_children_and_logs(proj):
    p = Project(proj)
    lib = p.modules["lib"]
    before = p.module_hash(lib)
    write(proj, {
        "lib/docs/lib.changelog.md": "# lib\n",
        "lib/docs/lib.trace.md": "x\n",
        "lib/child/child.md": "---\nkind: code\n---\n# child\n",
        "lib/child/src/c.py": "x = 1\n",
    })
    p2 = Project(proj)
    assert p2.modules["child"].parent.name == "lib"
    assert p2.module_hash(p2.modules["lib"]) == before
    write(proj, {"lib/src/new.py": "y = 2\n"})
    assert Project(proj).module_hash(Project(proj).modules["lib"]) != before


@pytest.mark.req("REQ-MG-003")
def test_dependency_change_changes_dependent_hash(proj):
    before = Project(proj)
    app_before = before.module_hash(before.modules["app"])
    write(proj, {"lib/src/add.py": "def add(a, b):\n    return b + a\n"})
    after = Project(proj)
    assert after.module_hash(after.modules["app"]) != app_before


@pytest.mark.req("REQ-MG-022")
def test_incremental_cache_reuses_and_invalidates(proj):
    c = HashCache(proj)
    f = proj / "lib/src/add.py"
    h1 = c.hash(f)
    c.save()
    c2 = HashCache(proj)
    assert c2.data["lib/src/add.py"][2] == h1
    assert c2.hash(f) == h1 and not c2.dirty
    f.write_text("changed = True\n")
    assert c2.hash(f) != h1
    assert (proj / ".modgate" / "cache.json").is_file()


@pytest.mark.req("REQ-MG-003")
def test_agent_context_is_not_module_content(proj):
    before = Project(proj).module_hash(Project(proj).modules["lib"])
    write(proj, {"lib/CLAUDE.md": "# hazard rules\n", "lib/.claude/settings.json": "{}\n"})
    assert Project(proj).module_hash(Project(proj).modules["lib"]) == before
