"""Tests for tools/trace_index.py — the traceability index generator."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import trace_index as ti  # noqa: E402


def _scaffold(root: Path, *, with_test: bool = True, with_covers: bool = True) -> Path:
    feat = root / "ProjectManagement" / "features" / "FEAT-0007-watchdog"
    feat.mkdir(parents=True)
    (feat / "DECISIONS.md").write_text(
        "# Decision Ledger — FEAT-0007\n\n"
        "## DEC-001 — ring buffer for RX\n"
        "- **date:** 2026-06-17\n"
        "- **with:** bach\n"
        "- **status:** active\n"
        "- **serves:** REQ-001\n"
        "- **superseded_by:** —\n\n"
        "Decided: ring buffer.\nWhy: no heap in ISR.\nRejected: malloc.\n\n"
        "## DEC-002 — unused decision\n"
        "- **status:** active\n"
        "- **serves:**\n"
    )
    (feat / "PRD.md").write_text(
        "# PRD\n\n## Functional Requirements\n\n"
        "### REQ-001 — no heap in ISR\n"
        "- **statement (EARS):** While in an ISR, the driver shall not allocate heap.\n"
        "- **priority:** must\n"
        "- **from:** DEC-001\n"
        "- **testable:** yes\n\n"
        "### REQ-002 — bounded write\n"
        "- **statement (EARS):** The driver shall not write past the buffer.\n"
        "- **priority:** should\n"
        "- **from:**\n"
        "- **testable:** yes\n"
    )
    if with_test:
        (feat / "TEST_PLAN.md").write_text(
            "| TC | REQ | level |\n|----|-----|-------|\n"
            "| TC-001 | REQ-001 | unit |\n"
            "| TC-009 | REQ-999 | unit |\n"  # references unknown REQ → orphan warning
        )
    if with_covers:
        src = root / "src"
        src.mkdir()
        (src / "dma.c").write_text("// @covers FEAT-0007:REQ-001\nint rx(void){return 0;}\n")
    return feat


def test_clean_links_and_tables(tmp_path):
    feat = _scaffold(tmp_path)
    content, orphans = ti.build_trace(feat, tmp_path)

    assert ti.GENERATED_MARKER in content
    assert "# TRACE — FEAT-0007" in content
    # REQ-001 is fully traced: DEC, TC, and code.
    assert "[DEC-001](DECISIONS.md#dec-001)" in content
    assert "TC-001" in content
    assert "dma.c:1" in content
    assert "```mermaid" in content
    assert "DEC-001 --> REQ-001" in content
    assert "REQ-001 --> TC-001" in content


def test_orphans_detected(tmp_path):
    feat = _scaffold(tmp_path)
    content, orphans = ti.build_trace(feat, tmp_path)
    blob = "\n".join(orphans)
    # REQ-002 has no test and no code coverage.
    assert "REQ-002" in blob
    # TC referencing a non-existent REQ is flagged.
    assert any("REQ-999" in o for o in orphans)
    # DEC-002 serves nothing → informational, not a ⚠️ orphan.
    assert "DEC-002" not in blob


def test_main_writes_file_and_check_exit(tmp_path):
    _scaffold(tmp_path)
    assert ti.main([str(tmp_path)]) == 0
    trace = tmp_path / "ProjectManagement" / "features" / "FEAT-0007-watchdog" / "TRACE.md"
    assert trace.exists()
    assert "# TRACE — FEAT-0007" in trace.read_text()
    # --check fails because REQ-002 is an orphan.
    assert ti.main([str(tmp_path), "--check"]) == 1


def test_fully_traced_is_clean(tmp_path):
    feat = _scaffold(tmp_path)
    # Fully wire both requirements end to end: DEC ↔ REQ ↔ TC ↔ code.
    (feat / "DECISIONS.md").write_text(
        "## DEC-001 — ring buffer\n- **status:** active\n- **serves:** REQ-001\n\n"
        "## DEC-002 — bounds check\n- **status:** active\n- **serves:** REQ-002\n"
    )
    (feat / "PRD.md").write_text(
        "### REQ-001 — no heap\n- **from:** DEC-001\n\n"
        "### REQ-002 — bounded write\n- **from:** DEC-002\n"
    )
    (feat / "TEST_PLAN.md").write_text(
        "| TC-001 | REQ-001 |\n| TC-002 | REQ-002 |\n"
    )
    (tmp_path / "src" / "dma.c").write_text(
        "// @covers FEAT-0007:REQ-001\n// @covers FEAT-0007:REQ-002\n"
    )
    content, orphans = ti.build_trace(feat, tmp_path)
    warn = [o for o in orphans if "⚠️" in o]
    assert warn == [], f"unexpected orphans: {warn}"
    assert "✅ No orphans" in content


def test_no_features_dir_is_noop(tmp_path):
    assert ti.main([str(tmp_path)]) == 0
