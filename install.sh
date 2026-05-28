#!/usr/bin/env bash
# install.sh — install the AI-assisted development workflow
#               (Claude Code slash-command skills + tool-agnostic project docs)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_SRC="$SCRIPT_DIR/skills"
TEMPLATES_SRC="$SCRIPT_DIR/templates"

GLOBAL_SKILLS="$HOME/.claude/skills"
PROJECT_SKILLS=".claude/skills"

# Directories created on bootstrap.
# ProjectManagement/ holds transient work-tracking artifacts (ideas, features, roadmap, risks).
# docs/ holds durable context (architecture, decisions, hardware knowledge).
PROJECT_DIRS=(
  "ProjectManagement/ideas"
  "ProjectManagement/features"
  "docs/architecture"
  "docs/decisions"
  "docs/knowledge-base"
)

# Permanent context files at project root.
ROOT_TEMPLATES=(
  "CLAUDE.md"
  "AGENTS.md"
  "PROJECT_CONTEXT.md"
  "CODING_STANDARDS.md"
)

# Work-tracking files placed under ProjectManagement/.
PROJECTMGMT_TEMPLATES=(
  "ROADMAP.md"
  "DEV_TRACKER.md"
  "RISK_LOG.md"
)

usage() {
  echo "Usage: ./install.sh [global|project|bootstrap]"
  echo ""
  echo "  global     Install skills globally (~/.claude/skills/)"
  echo "             Available in all Claude Code sessions on this machine"
  echo ""
  echo "  project    Install skills to current project (.claude/skills/)"
  echo "             Available only in this project"
  echo ""
  echo "  bootstrap  Install skills (project) + create full project docs structure"
  echo "             Run this once when setting up a new project"
  echo ""
  echo "After install: open Claude Code and type /workflow to get started"
  exit 1
}

install_skills() {
  local target="$1"
  mkdir -p "$target"

  local count=0
  for skill_dir in "$SKILLS_SRC"/*/; do
    skill_name="$(basename "$skill_dir")"
    dest="$target/$skill_name"
    rm -rf "$dest"
    mkdir -p "$dest"
    cp -R "$skill_dir"* "$dest"/
    echo "  installed: /$skill_name"
    count=$((count + 1))
  done

  echo ""
  echo "✓ $count skills installed to $target"
}

bootstrap_project() {
  echo ""
  echo "Bootstrapping project structure..."
  echo ""

  # Create directories
  for dir in "${PROJECT_DIRS[@]}"; do
    mkdir -p "$dir"
    echo "  created:  $dir/"
  done

  echo ""

  # Copy permanent context files to project root (skip if already exist)
  for file in "${ROOT_TEMPLATES[@]}"; do
    if [ ! -f "$file" ]; then
      cp "$TEMPLATES_SRC/$file" "$file"
      echo "  created:  $file"
    else
      echo "  skipped:  $file (already exists — not overwritten)"
    fi
  done

  # Copy work-tracking files to ProjectManagement/ (skip if already exist)
  for file in "${PROJECTMGMT_TEMPLATES[@]}"; do
    dest="ProjectManagement/$file"
    if [ ! -f "$dest" ]; then
      cp "$TEMPLATES_SRC/$file" "$dest"
      echo "  created:  $dest"
    else
      echo "  skipped:  $dest (already exists — not overwritten)"
    fi
  done

  # Copy architecture guide
  if [ ! -f "docs/architecture/README.md" ]; then
    cp "$TEMPLATES_SRC/architecture/README.md" "docs/architecture/README.md"
    echo "  created:  docs/architecture/README.md"
  else
    echo "  skipped:  docs/architecture/README.md (already exists — not overwritten)"
  fi

  echo ""
  echo "✓ Project structure ready"
  echo ""
  echo "Next steps:"
  echo "  1. Fill in PROJECT_CONTEXT.md — describe your project"
  echo "  2. Fill in CODING_STANDARDS.md — your language and linter"
  echo "  3. Open Claude Code and type /workflow — or point any AGENTS.md-aware agent at AGENTS.md"
}

# Require argument
if [ $# -eq 0 ]; then
  usage
fi

case "$1" in
  global)
    echo "Installing skills globally..."
    install_skills "$GLOBAL_SKILLS"
    echo ""
    echo "Open any Claude Code session and type /workflow to get started."
    ;;

  project)
    echo "Installing skills to current project..."
    install_skills "$PROJECT_SKILLS"
    echo ""
    echo "Open Claude Code in this project and type /workflow to get started."
    ;;

  bootstrap)
    echo "Bootstrapping project..."
    install_skills "$PROJECT_SKILLS"
    bootstrap_project
    ;;

  *)
    usage
    ;;
esac
