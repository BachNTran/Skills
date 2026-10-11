import json
import os
import subprocess

import pytest

from conftest import SRC_ROOT

KIT = SRC_ROOT / "kit"
KINDS = {"code", "system", "adapter", "protocol", "data", "host-service", "deploy", "tool", "study"}
DOCS = {"brief.md", "req.md", "icd.md", "tests.md", "changelog.md", "activity.md", "bind.yaml"}


@pytest.mark.req("REQ-MG-025")
def test_skill_is_short_with_frontmatter():
    text = (KIT / "skill/SKILL.md").read_text()
    assert len(text.splitlines()) <= 40
    assert text.startswith("---\nname: modgate\ndescription: ")
    assert "guideline/Dev-Guideline-with-LLMs.md" in text


@pytest.mark.req("REQ-MG-025")
def test_one_template_per_kind():
    found = {p.parent.name: p for p in KIT.glob("templates/*/*/{{module}}.md")}
    assert set(found) == KINDS
    for kind, ov in found.items():
        assert f"kind: {kind}\n" in ov.read_text() and "status: draft" in ov.read_text()
        docs = {p.name.removeprefix("{{module}}.") for p in (ov.parent / "docs").iterdir()}
        assert docs == DOCS, kind


@pytest.mark.req("REQ-MG-019")
def test_hooks_snippet_shape():
    h = json.loads((KIT / "hooks.json").read_text())
    assert h["hooks"]["SessionStart"][0]["hooks"][0]["command"] == "modgate pending --hook"
    assert h["hooks"]["PostToolUse"][0]["matcher"] == "Edit|Write|MultiEdit"
    assert h["hooks"]["Stop"][0]["hooks"][0]["command"] == "modgate sync --hook"
    assert h["permissions"]["ask"] == ["Bash(modgate approve:*)"]


@pytest.mark.req("REQ-MG-024")
def test_install_is_idempotent_and_additive(tmp_path):
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "uv").write_text("#!/bin/sh\necho \"$@\" >> \"$(dirname \"$0\")/uv.log\"\n")
    (fake / "uv").chmod(0o755)
    proj = tmp_path / "p"
    (proj / ".claude").mkdir(parents=True)
    (proj / ".claude/settings.json").write_text(json.dumps({"model": "x", "permissions": {"ask": ["Bash(rm:*)"]}}))
    (proj / ".gitignore").write_text("node_modules/\n")
    env = {**os.environ, "PATH": f"{fake}:/usr/bin:/bin:/opt/homebrew/bin"}
    for _ in range(2):
        subprocess.run(["bash", str(SRC_ROOT / "install.sh"), str(proj)], check=True, env=env, capture_output=True)
    s = json.loads((proj / ".claude/settings.json").read_text())
    assert s["model"] == "x"
    assert s["permissions"]["ask"] == ["Bash(rm:*)", "Bash(modgate approve:*)"]
    assert [len(s["hooks"][e]) for e in ("SessionStart", "PostToolUse", "Stop")] == [1, 1, 1]
    assert (proj / ".gitignore").read_text() == "node_modules/\n.modgate/\n"
    assert "criticality:" in (proj / "modgate.yaml").read_text()
    assert (proj / ".claude/skills/modgate/SKILL.md").is_file()
    assert (proj / ".claude/skills/modgate/templates/blocks/code/{{module}}.md").is_file()
    assert (fake / "uv.log").read_text().count("tool install --force") == 2


@pytest.mark.req("REQ-MG-026")
def test_zero_runtime_dependencies_yaml_is_vendored():
    import tomllib

    data = tomllib.loads((SRC_ROOT / "pyproject.toml").read_text())
    assert data["project"]["dependencies"] == []
    from modgate._vendor import yaml

    assert yaml.safe_load("a: [1, 2]") == {"a": [1, 2]}
    assert (SRC_ROOT / "src/modgate/_vendor/LICENSE").is_file()


@pytest.mark.req("REQ-MG-026")
def test_vendored_paths_are_exempt_from_size_and_unbound():
    from modgate.project import is_vendored

    assert is_vendored("src/modgate/_vendor/yaml/scanner.py", ["src/modgate/_vendor"])
    assert not is_vendored("src/modgate/cli.py", ["src/modgate/_vendor"])


@pytest.mark.req("REQ-MG-024")
def test_install_no_cli_wires_plain_modgate(tmp_path):
    subprocess.run(["bash", str(SRC_ROOT / "install.sh"), "--no-cli", str(tmp_path)], check=True, capture_output=True)
    settings = json.loads((tmp_path / ".claude/settings.json").read_text())
    cmds = [h["command"] for groups in settings["hooks"].values() for g in groups for h in g["hooks"]]
    assert cmds and all(c.startswith("modgate ") for c in cmds)
    assert not (tmp_path / ".modgate/venv").exists()
    assert (tmp_path / ".claude/skills/modgate/SKILL.md").is_file()
