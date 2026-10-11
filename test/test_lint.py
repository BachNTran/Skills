import subprocess

import pytest

from modgate.analyze import Project
from modgate.approve import approve

from conftest import write


def lint(proj, paths=None) -> dict[str, list]:
    out: dict[str, list] = {}
    for f in Project(proj).sync(paths):
        out.setdefault(f.label, []).append(f)
    return out


@pytest.mark.req("REQ-MG-012")
def test_generic_names_forbidden_tool_names_allowed(proj):
    write(proj, {"lib/README.md": "x\n", "lib/CMakeLists.txt": "x\n", "CLAUDE.md": "x\n", "lib/docs/notes.md": "x\n"})
    fs = lint(proj)
    assert sorted(f.id for f in fs["E:NAMING"]) == ["lib/README.md", "lib/docs/notes.md"]
    assert "NAMING" not in fs


@pytest.mark.req("REQ-MG-012")
def test_docs_must_be_module_prefixed(proj):
    write(proj, {"lib/docs/design.md": "x\n"})
    assert [f.id for f in lint(proj)["NAMING"]] == ["docs/design.md"]


@pytest.mark.req("REQ-MG-013")
def test_folder_size_warn_above_8_fail_above_12(proj):
    write(proj, {f"lib/src/f{i}.py": "x\n" for i in range(9)})
    fs = lint(proj)
    assert [f.id for f in fs["SIZE"]] == ["lib/src/"]
    write(proj, {f"lib/src/g{i}.py": "x\n" for i in range(4)})
    assert [f.id for f in lint(proj)["E:SIZE"]] == ["lib/src/"]


@pytest.mark.req("REQ-MG-013")
def test_hidden_and_config_entries_do_not_count(proj):
    write(proj, {f"d{i}/x.txt": "x\n" for i in range(6)})  # root: modgate.yaml + lib + app + d0..d5 = 8 visible
    write(proj, {".hidden": "x\n"})
    assert "SIZE" not in lint(proj)


@pytest.mark.req("REQ-MG-014")
def test_changelog_heading_format_and_duplicates(proj):
    write(proj, {"lib/docs/lib.changelog.md": (
        "# lib · changelog\n\n### 2026-09-27-a1b2 · v1 · lib.req.md · AI\n- ok\n"
        "### 2026-09-27-a1b2 · v2 · lib.req.md · AI\n- dup\n### yesterday · lib\n- bad\n"
    )})
    fs = lint(proj)
    assert sorted(f.action.split(":")[0] for f in fs["CHANGELOG"]) == ["duplicate entry id", "heading"]


@pytest.mark.req("REQ-MG-014")
def test_changelog_append_only_against_git_head(git_proj):
    approve(Project(git_proj), "lib", "brief", "Tess Ter")
    subprocess.run(["git", "-C", str(git_proj), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(git_proj), "commit", "-qm", "approve"], check=True)
    log = git_proj / "lib/docs/lib.changelog.md"
    log.write_text(log.read_text() + "\n### 2026-09-27-beef · v1 · lib.md · AI\n- appended\n")
    assert "E:APPEND" not in lint(git_proj)
    log.write_text(log.read_text().replace("APPROVED", "approved (edited)"))
    assert [f.module for f in lint(git_proj)["E:APPEND"]] == ["lib"]


@pytest.mark.req("REQ-MG-015")
def test_ai_approval_above_level_is_a_violation(proj):
    approve(Project(proj), "lib", "bind", "ai-reviewer:m")  # allowed at L2
    assert "E:APPROVER" not in lint(proj)
    cfg = proj / "modgate.yaml"
    cfg.write_text(cfg.read_text().replace("criticality: L2", "criticality: L3"))
    assert [f.id for f in lint(proj)["E:APPROVER"]] == ["lib.bind.yaml"]


@pytest.mark.req("REQ-MG-015")
def test_custom_preset_in_config(proj):
    cfg = proj / "modgate.yaml"
    cfg.write_text(cfg.read_text().replace("criticality: L2", "criticality: L2b")
                   + "criticality_presets:\n  L2b: {ai_may_approve: [brief]}\n")
    assert approve(Project(proj), "lib", "brief", "ai-reviewer:m")


@pytest.mark.req("REQ-MG-021")
def test_drawio_missing_cli_is_one_finding_never_failure(proj, monkeypatch):
    monkeypatch.setenv("PATH", "/nonexistent")
    write(proj, {"lib/docs/diagrams/flow.drawio": "<mxfile/>\n"})
    fs = lint(proj)
    assert [f.id for f in fs["DRAWIO"]] == ["flow.drawio"]
    assert not [k for k in fs if k.startswith("E:")]


@pytest.mark.req("REQ-MG-021")
def test_drawio_exports_when_source_newer(proj, tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "drawio"
    fake.write_text('#!/bin/sh\n# args: -x -f svg -o OUT SRC\necho "<svg/>" > "$5"\n')
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")
    write(proj, {"lib/docs/diagrams/flow.drawio": "<mxfile/>\n"})
    assert "DRAWIO" not in lint(proj)
    assert (proj / "lib/docs/diagrams/flow.svg").read_text() == "<svg/>\n"
