import pytest

from modgate.analyze import Project
from modgate.project import ModgateError, find_root, parse_items, scan_tests, set_frontmatter, read_frontmatter

from conftest import write


@pytest.mark.req("REQ-MG-004")
def test_root_and_module_discovery(proj):
    assert find_root(proj / "lib" / "src") == proj
    p = Project(proj / "lib" / "src")
    assert set(p.modules) == {"lib", "app"}
    assert p.modules["app"].deps == ["lib"]


@pytest.mark.req("REQ-MG-004")
def test_folder_without_kind_is_not_a_module_and_nested_project_is_opaque(proj):
    write(proj, {
        "notes/notes.md": "---\ntitle: no kind\n---\n",
        "sub/modgate.yaml": "project: sub\n",
        "sub/inner/inner.md": "---\nkind: code\n---\n",
    })
    assert set(Project(proj).modules) == {"lib", "app"}


@pytest.mark.req("REQ-MG-004")
def test_missing_root_is_an_error(tmp_path):
    with pytest.raises(ModgateError):
        find_root(tmp_path)


@pytest.mark.req("REQ-MG-005")
def test_criticality_inherits_unless_set(proj):
    write(proj, {
        "lib/kid/kid.md": "---\nkind: code\n---\n",
        "lib/kid/grand/grand.md": "---\nkind: study\ncriticality: L0\n---\n",
        "app/app.md": "---\nkind: code\ncriticality: L1\ndeps: [lib]\n---\n",
    })
    p = Project(proj)
    c = {n: m.criticality(p.config) for n, m in p.modules.items()}
    assert c == {"lib": "L2", "kid": "L2", "grand": "L0", "app": "L1"}


@pytest.mark.req("REQ-MG-006")
def test_requirement_items_parents_and_continuation():
    text = (
        "---\nstatus: draft\n---\n# R\n\n"
        "- **REQ-A-001** (parents: FEAT-A-001, REQ-SYS-004) — First.\n"
        "  more of first\n\n"
        "  still first after a blank line\n"
        "- **REQ-A-002** — Second.\n"
        "Paragraph ends it.\n"
        "  - **REQ-A-009** nested items are not requirements\n"
    )
    items = parse_items(text)
    assert list(items) == ["REQ-A-001", "REQ-A-002"]
    assert items["REQ-A-001"]["parents"] == ["FEAT-A-001", "REQ-SYS-004"]
    assert "still first" in items["REQ-A-001"]["text"]
    assert items["REQ-A-002"]["text"] == "- **REQ-A-002** — Second.\n"


@pytest.mark.req("REQ-MG-010")
def test_test_scan_python_cpp_js(proj):
    write(proj, {
        "lib/test/test_more.py": (
            '@pytest.mark.req("REQ-LIB-002", "REQ-LIB-001")\n'
            "def test_negative():\n    pass\n\n"
            "def test_REQ_LIB_002_by_name():\n    pass\n"
        ),
        "lib/test/test_cpp.cpp": "TEST(Lib, REQ_LIB_002_rejects_negative) {}\n",
        "lib/test/lib.test.ts": 'it("REQ-LIB-001 adds", () => {});\n',
        "lib/src/not_a_test.py": '@pytest.mark.req("REQ-LIB-001")\ndef test_x(): pass\n',
    })
    p = Project(proj)
    m = p.modules["lib"]
    links = scan_tests(m, list(p.files(m)))
    assert links["REQ-LIB-002"] == [
        "Lib.REQ_LIB_002_rejects_negative",
        "test/test_more.py::test_negative",
        "test/test_more.py::test_REQ_LIB_002_by_name",
    ]
    assert "REQ-LIB-001 adds" in links["REQ-LIB-001"]
    assert not any("not_a_test" in t for t in links["REQ-LIB-001"])


@pytest.mark.req("REQ-MG-016")
def test_set_frontmatter_keeps_body_bytes(tmp_path):
    f = tmp_path / "d.md"
    f.write_text("---\ntitle: t\nstatus: draft\n---\n\nbody  \n")
    set_frontmatter(f, {"status": "approved", "approved": "1 sha256:abc"})
    assert f.read_text().endswith("---\n\nbody  \n")
    assert read_frontmatter(f)["status"] == "approved"
    g = tmp_path / "plain.md"
    g.write_text("no frontmatter\n")
    set_frontmatter(g, {"status": "approved"})
    assert g.read_text() == "---\nstatus: approved\n---\nno frontmatter\n"
