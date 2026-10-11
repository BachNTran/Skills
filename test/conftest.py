"""Fixtures: a tiny two-module project built in tmp_path, plus a CLI runner."""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from modgate import cli

SRC_ROOT = Path(__file__).resolve().parents[1]

CONFIG = """\
project: demo
criticality: L2
diagrams: mermaid
coding_standard: google
targets:
  unit: "{python} -c \\"print('3 passed')\\""
  broken: "{python} -c \\"import sys; sys.exit(4)\\""
"""


def overview(name: str, kind: str = "code", deps: str = "[]", extra: str = "") -> str:
    return (
        f"---\ntitle: {name}\nkind: {kind}\ndeps: {deps}\nversion: 1\nstatus: draft\napproved:\n{extra}---\n\n"
        f"# {name}\n\nOverview of {name}.\n"
    )


def req_doc(mod: str, items: list[str]) -> str:
    return "---\ntitle: req\nversion: 1\nstatus: draft\napproved:\n---\n\n# Requirements\n\n" + "\n".join(items) + "\n"


LIB = {
    "lib/lib.md": overview("lib", extra="targets: [unit]\n"),
    "lib/docs/lib.req.md": req_doc(
        "LIB",
        [
            "- **REQ-LIB-001** (parents: FEAT-LIB-001) — Add two numbers.",
            "- **REQ-LIB-002** (parents: FEAT-LIB-001) — Reject negative input.",
            "  Continuation line of REQ-LIB-002.",
        ],
    ),
    "lib/docs/lib.brief.md": "---\ntitle: brief\nversion: 1\nstatus: draft\n---\n\n- **FEAT-LIB-001** — Arithmetic.\n",
    "lib/docs/lib.bind.yaml": "REQ-LIB-001: [src/add.py, test/test_add.py]\nREQ-LIB-002: [src/check.py]\n",
    "lib/src/add.py": "def add(a, b):\n    return a + b\n",
    "lib/src/check.py": "def check(a):\n    return a >= 0\n",
    "lib/test/test_add.py": '@pytest.mark.req("REQ-LIB-001")\ndef test_adds():\n    assert True\n',
    "lib/docs/lib.activity.md": "# lib · activity\n\n- [ ] FEAT-LIB-002 · multiply · after: approve\n",
}
APP = {
    "app/app.md": overview("app", deps="[lib]"),
    "app/docs/app.req.md": req_doc("APP", ["- **REQ-APP-001** (parents: REQ-LIB-001) — Show a sum."]),
    "app/docs/app.bind.yaml": "REQ-APP-001: [src/main.py]\n",
    "app/src/main.py": "print(1)\n",
}


def write(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)


@pytest.fixture
def proj(tmp_path, monkeypatch) -> Path:
    root = tmp_path / "demo"
    write(root, {"modgate.yaml": CONFIG, **LIB, **APP})
    monkeypatch.chdir(root)
    return root


@pytest.fixture
def git_proj(proj) -> Path:
    for cmd in (["init", "-q"], ["config", "user.name", "Tess Ter"], ["config", "user.email", "t@example.com"]):
        subprocess.run(["git", "-C", str(proj), *cmd], check=True)
    subprocess.run(["git", "-C", str(proj), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(proj), "commit", "-qm", "init"], check=True)
    return proj


class Result:
    def __init__(self, code: int, out: str, err: str):
        self.code, self.out, self.err = code, out, err

    @property
    def lines(self) -> list[str]:
        return [x for x in self.out.splitlines() if x.strip()]

    def json(self):
        return json.loads(self.out)


@pytest.fixture
def run(monkeypatch, capsys):
    def _run(*args: str, stdin: str = "") -> Result:
        monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
        code = cli.main(list(args))
        out = capsys.readouterr()
        return Result(code, out.out, out.err)

    return _run
