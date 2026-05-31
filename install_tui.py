#!/usr/bin/env python3
import glob
import os
import re
import shutil
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
SKILLS_SRC = SCRIPT_DIR / "skills"
TEMPLATES_SRC = SCRIPT_DIR / "templates"

PROJECT_DIRS = [
    "ProjectManagement/ideas",
    "ProjectManagement/features",
    "docs/architecture",
    "docs/decisions",
    "docs/knowledge-base",
]
ROOT_TEMPLATES = ["CLAUDE.md", "AGENTS.md", "PROJECT_CONTEXT.md", "CODING_STANDARDS.md"]
PROJECTMGMT_TEMPLATES = ["ROADMAP.md", "DEV_TRACKER.md", "RISK_LOG.md"]


def _codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))


TARGETS = [
    ("Global — Claude Code",                              lambda: Path.home() / ".claude/skills"),
    ("Global — Codex",                                    lambda: _codex_home() / "skills"),
    ("A project  (skills only)",                          "project"),
    ("Bootstrap a project  (skills + scaffold docs)",     "bootstrap"),
]


# ── frontmatter ──────────────────────────────────────────────────────────────

def _frontmatter(skill_md: Path) -> str | None:
    if not skill_md.exists():
        return None
    content = skill_md.read_text(encoding="utf-8")
    match = re.search(r"\A---\n(.*?)\n---(?:\n|\Z)", content, re.DOTALL)
    return match.group(1) if match else None


def _parse_description(skill_dir: Path) -> str:
    skill_md = skill_dir / "SKILL.md"
    frontmatter = _frontmatter(skill_md)
    if frontmatter is None:
        return ""
    # Handle single-line and multi-line (folded/literal block) description
    desc_match = re.search(r"^description:\s*(.+)$", frontmatter, re.MULTILINE)
    return desc_match.group(1).strip() if desc_match else ""


def _frontmatter_value(frontmatter: str, key: str) -> str | None:
    match = re.search(rf"^{re.escape(key)}:\s*(.+)$", frontmatter, re.MULTILINE)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def validate_skill_dir(skill_dir: Path) -> list[str]:
    errors = []
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return [f"{skill_dir.name}: missing SKILL.md"]

    frontmatter = _frontmatter(skill_md)
    if frontmatter is None:
        return [f"{skill_dir.name}: missing frontmatter delimited by ---"]

    name = _frontmatter_value(frontmatter, "name")
    if name is None:
        errors.append(f"{skill_dir.name}: missing non-empty name")
    elif name != skill_dir.name:
        errors.append(f"{skill_dir.name}: name '{name}' must match directory name")

    description = _frontmatter_value(frontmatter, "description")
    if description is None:
        errors.append(f"{skill_dir.name}: missing non-empty single-line description")

    return errors


def validate_all_skills(skills_src: Path = SKILLS_SRC) -> list[str]:
    if not skills_src.exists():
        return [f"{skills_src}: skills directory does not exist"]

    errors = []
    for skill_dir in sorted(skills_src.iterdir()):
        if skill_dir.is_dir():
            errors.extend(validate_skill_dir(skill_dir))
    return errors


# ── helpers ───────────────────────────────────────────────────────────────────

def _trunc(s: str, n: int = 72) -> str:
    return s[:n] + "…" if len(s) > n else s


def _read(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except (KeyboardInterrupt, EOFError):
        print("\nAborted.")
        sys.exit(0)


# ── skill list ────────────────────────────────────────────────────────────────

def _load_skills() -> list[tuple[str, str, Path]]:
    skills = []
    for d in sorted(SKILLS_SRC.iterdir()):
        if d.is_dir():
            skills.append((d.name, _parse_description(d), d))
    return skills


# ── prompts ───────────────────────────────────────────────────────────────────

def _path_completer(text: str, state: int) -> str | None:
    expanded = os.path.expanduser(text)
    matches = glob.glob(expanded + "*")
    matches = [m + "/" if os.path.isdir(m) else m for m in sorted(matches)]
    return matches[state] if state < len(matches) else None


def prompt_project_path() -> Path:
    try:
        import readline
        readline.set_completer_delims(" \t\n")
        readline.set_completer(_path_completer)
        # macOS ships libedit masquerading as readline; binding syntax differs
        if "libedit" in (readline.__doc__ or ""):
            readline.parse_and_bind("bind ^I rl_complete")
        else:
            readline.parse_and_bind("tab: complete")
    except ImportError:
        pass

    cwd = Path.cwd()
    raw = _read(f"  Project path [{cwd}]: ")

    try:
        import readline
        readline.set_completer(None)
    except ImportError:
        pass

    base = Path(os.path.expanduser(raw)) if raw else cwd
    if not base.exists():
        print(f"  Directory '{base}' does not exist. Creating it.")
        base.mkdir(parents=True, exist_ok=True)
    return base


def prompt_target() -> tuple[str, Path, str]:
    print("\nWhere do you want to install?\n")
    for i, (label, path_fn) in enumerate(TARGETS, 1):
        suffix = f"  ({path_fn()})" if callable(path_fn) else ""
        print(f"  [{i}] {label}{suffix}")
    while True:
        raw = _read("\nChoice: ")
        if raw.isdigit() and 1 <= int(raw) <= len(TARGETS):
            label, path_fn = TARGETS[int(raw) - 1]
            if callable(path_fn):
                return label, path_fn(), "install"
            # project or bootstrap — ask for path
            base = prompt_project_path()
            mode = path_fn  # "project" or "bootstrap"
            return label, base / ".claude/skills", mode
        print(f"  Please enter a number between 1 and {len(TARGETS)}.")


def prompt_skills(skills: list) -> list:
    print("\nSelect skills to install (* = all, or numbers separated by spaces):\n")
    for i, (name, desc, _) in enumerate(skills, 1):
        print(f"  [{i}] {name:<12} — {_trunc(desc)}")
    while True:
        raw = _read("\nChoice: ")
        if raw == "*":
            return skills
        parts = raw.split()
        if parts and all(p.isdigit() and 1 <= int(p) <= len(skills) for p in parts):
            return [skills[int(p) - 1] for p in parts]
        print(f"  Enter * or space-separated numbers between 1 and {len(skills)}.")


# ── install logic ─────────────────────────────────────────────────────────────

def _conflict(name: str, incoming_desc: str, target: Path) -> str | None:
    existing_md = target / name / "SKILL.md"
    if not existing_md.exists():
        return None
    existing_desc = _parse_description(target / name)
    return "same" if existing_desc == incoming_desc else existing_desc


def _copy_skill(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)


def install_skill(name: str, desc: str, src: Path, target: Path) -> None:
    conflict = _conflict(name, desc, target)
    if conflict is None:
        _copy_skill(src, target / name)
        print(f"  ✓ installed:   /{name}")
    elif conflict == "same":
        _copy_skill(src, target / name)
        print(f"  ↺ updated:     /{name}")
    else:
        print(f"\n  ⚠  '{name}' already exists with a different description.")
        print(f"     Installed : \"{_trunc(conflict, 80)}\"")
        print(f"     Incoming  : \"{_trunc(desc, 80)}\"")
        ans = _read("     Overwrite? [y/N]: ").lower()
        if ans == "y":
            _copy_skill(src, target / name)
            print(f"  ✓ overwritten: /{name}")
        else:
            print(f"  — skipped:     /{name}")


def install_all(skills: list, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for name, desc, src in skills:
        install_skill(name, desc, src, target)
    print(f"\n  {len(skills)} skill(s) → {target}\n")


# ── bootstrap ─────────────────────────────────────────────────────────────────

def bootstrap_project(base: Path) -> None:
    print(f"Bootstrapping project structure in {base}...\n")
    for d in PROJECT_DIRS:
        (base / d).mkdir(parents=True, exist_ok=True)
        print(f"  created:  {d}/")
    print()
    for fname in ROOT_TEMPLATES:
        dest = base / fname
        if not dest.exists():
            shutil.copy(TEMPLATES_SRC / fname, dest)
            print(f"  created:  {fname}")
        else:
            print(f"  skipped:  {fname} (already exists)")
    for fname in PROJECTMGMT_TEMPLATES:
        dest = base / "ProjectManagement" / fname
        if not dest.exists():
            shutil.copy(TEMPLATES_SRC / fname, dest)
            print(f"  created:  ProjectManagement/{fname}")
        else:
            print(f"  skipped:  ProjectManagement/{fname} (already exists)")
    arch = base / "docs/architecture/README.md"
    if not arch.exists():
        shutil.copy(TEMPLATES_SRC / "architecture/README.md", arch)
        print(f"  created:  docs/architecture/README.md")
    else:
        print(f"  skipped:  docs/architecture/README.md (already exists)")
    print("\n✓ Project structure ready")
    print("\nNext steps:")
    print("  1. Fill in PROJECT_CONTEXT.md — describe your project")
    print("  2. Fill in CODING_STANDARDS.md — your language and linter")
    print("  3. Open Claude Code and type /workflow to get started\n")


# ── CLI passthrough ───────────────────────────────────────────────────────────

def run_cli(arg: str) -> None:
    if arg == "validate":
        errors = validate_all_skills()
        if errors:
            print("Skill validation failed:", file=sys.stderr)
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
            sys.exit(1)
        print(f"Validated {len(_load_skills())} skill(s).")
        return

    skills = _load_skills()
    targets = {
        "global":    Path.home() / ".claude/skills",
        "codex":     _codex_home() / "skills",
        "project":   Path(".claude/skills"),
        "bootstrap": Path(".claude/skills"),
    }
    if arg not in targets:
        print(f"Unknown target '{arg}'. Valid: global, codex, project, bootstrap, validate")
        sys.exit(1)
    target = targets[arg]
    print(f"Installing skills to {target}...")
    install_all(skills, target)
    if arg == "bootstrap":
        bootstrap_project(Path.cwd())


# ── TUI entry ─────────────────────────────────────────────────────────────────

def run_tui() -> None:
    print("\n── Skills Installer ──")
    label, target, mode = prompt_target()
    skills = _load_skills()
    selected = prompt_skills(skills)

    if mode == "bootstrap":
        print(f"\nBootstrapping + installing {len(selected)} skill(s) to {target}...\n")
        install_all(selected, target)
        bootstrap_project(target.parent.parent)  # base project dir
    else:
        print(f"\nInstalling {len(selected)} skill(s) to {target}...\n")
        install_all(selected, target)
        print("Done.")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        run_cli(sys.argv[1])
    else:
        run_tui()
