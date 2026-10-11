---
title: modgate · test plan
version: 1
status: draft
approved:
---

# modgate · test plan

## Strategy
L1 — representative cases per requirement, plus the edge that motivated it (CRLF, frontmatter-only
edits, nested modules, dependency cycles of one). Every test builds a throwaway project in `tmp_path`
(`test/conftest.py`: modules `lib` ← `app`, target `unit` that prints "3 passed", target `broken`) and
drives the real CLI entry point. Git-dependent cases init a throwaway repo. `install.sh` runs against a
fake `uv` on PATH so no network is needed. Each test carries `@pytest.mark.req("REQ-MG-###")`; the
trace file lists them per REQ.

## REQ → TC
| REQ | Test file | Level |
|---|---|---|
| REQ-MG-001, 002, 003, 022 | `test/test_hashing.py` | unit |
| REQ-MG-004, 005, 006, 010 | `test/test_project.py` | unit |
| REQ-MG-007, 008, 009, 015, 016, 023 | `test/test_gates.py` | module (API) |
| REQ-MG-012, 013, 014, 015, 021 | `test/test_lint.py` | module (API) |
| REQ-MG-011, 016, 017, 018, 020 | `test/test_cli.py` | CLI |
| REQ-MG-019 | `test/test_hooks.py` | CLI with hook JSON |
| REQ-MG-019, 024, 025 | `test/test_kit.py` | kit + installer |
