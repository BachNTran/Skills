from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import install_tui


def write_skill(base: Path, name: str, body: str) -> None:
    skill_dir = base / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(body, encoding="utf-8")


class SkillValidationTests(unittest.TestCase):
    def test_validate_all_skills_accepts_valid_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_skill(
                base,
                "example",
                "---\nname: example\ndescription: Example skill.\n---\n\n# Example\n",
            )

            self.assertEqual(install_tui.validate_all_skills(base), [])

    def test_validate_all_skills_reports_frontmatter_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_skill(base, "bad-name", "---\nname: other\ndescription: Example.\n---\n")
            write_skill(base, "missing-description", "---\nname: missing-description\n---\n")
            (base / "missing-file").mkdir()

            errors = install_tui.validate_all_skills(base)

        self.assertIn("bad-name: name 'other' must match directory name", errors)
        self.assertIn(
            "missing-description: missing non-empty single-line description",
            errors,
        )
        self.assertIn("missing-file: missing SKILL.md", errors)

    def test_parse_description_uses_frontmatter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            write_skill(
                base,
                "example",
                "---\nname: example\ndescription: Short description.\n---\n",
            )

            self.assertEqual(
                install_tui._parse_description(base / "example"),
                "Short description.",
            )


if __name__ == "__main__":
    unittest.main()
