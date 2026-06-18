# Project Context

## Purpose

This file gives humans and AI agents a fast orientation to the project.
Keep it short, durable, and updated only when project-level context changes.

## Criticality & Autonomy

Governs how much the agent decides autonomously vs. defers to you. The agent reads this
at session start; workflow hooks enforce it.

- **criticality:** STANDARD   <!-- EXPLORE | STANDARD | CRITICAL -->

| Tier     | You do                                  | Agent does                                   | Trace                    |
|----------|-----------------------------------------|----------------------------------------------|--------------------------|
| EXPLORE  | Grill the idea, then step back          | Ships autonomously; may auto-merge           | Light                    |
| STANDARD | Approve PRD + test plan + slice plan    | Implements solo                              | Full                     |
| CRITICAL | Review every slice, diff, and line      | Grunt work + second eye only; never auto-merges | Full + rationale required |

A feature may override this in its `BRIEF.md` (`criticality:` + a reason). If this field
is unset, the agent runs a short config grill, proposes a setting, and writes it here.

## Product Sentence

We are building:

> TODO

## Target Users / Systems

- TODO

## Core Problem

This project exists to solve:

> TODO

## Design Principles

1. Keep the system understandable
2. Build incrementally with tested behavior
3. Keep module boundaries clear and explicit
4. Make the project easy for a new developer or agent to understand
5. Prefer deep modules with thin public interfaces
6. Keep documentation close to decisions

## Non-Goals

- TODO

## Quality Bar

The project should be:
- Correct — behavior matches specification
- Testable — every module independently verifiable
- Maintainable — easy to change without breaking other things
- Understandable — new developer productive within one session
- Safe to change — regression suite protects existing behavior

## Tech Stack / Platform

- Language: TODO
- Target: TODO (e.g., embedded target, host OS, specific hardware)
- Test runner: TODO
- Linter/static analysis: TODO
- Build system: TODO

## Current Development Workflow

This project uses the AI-assisted development workflow.
See [AGENTS.md](AGENTS.md).
