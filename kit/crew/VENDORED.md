# Vendored skills — sources and security review

Third-party skills are copied in as our own files (no clone, no submodule). Each file is pinned to an
upstream commit and hashed in `kit/crew/vendor.lock.json`. They sit flat in `kit/crew/skills/` with our own skills; a skills folder is exempt from the folder-size rule. Reviewed 2026-10-10.

| Skill dir | Upstream @ commit | License | Changed? |
|---|---|---|---|
| `ponytail`, `ponytail-review`, `ponytail-audit`, `ponytail-debt` | DietrichGebert/ponytail @ 9b58c1f | MIT | no |
| `caveman`, `caveman-review` | JuliusBrussee/caveman @ 2e08b91 | Apache-2.0 | caveman: yes |
| `caveman-commit` | JuliusBrussee/caveman @ 2e08b91 | Apache-2.0 | yes |
| `drawio` (+ 3 references) | jgraph/drawio-mcp @ eebe7de | Apache-2.0 | yes |
| `graphify` (+ 8 references) | Graphify-Labs/graphify @ 565b22b | Apache-2.0 | yes |
| `grilling`, `grill-me` | mattpocock/skills @ 49dd158 | MIT | grilling: yes |

Our own skills, not vendored: `caveman-plus`, `crew`, `wiki`.

## How the review was done
1. Fetched raw files with `gh api` at the pinned commit into a quarantine folder outside the repo.
2. Ran `tools/skill_scan.py`: hidden Unicode (zero-width, bidi, tag characters), override and authority phrases, secret paths, network and exec calls, persistence (settings, shell rc, cron), encoded blobs, HTML comments, every URL.
3. Read every SKILL.md and reference in full.
4. Copied with `tools/vendor_copy.py`, which applies the edits below with asserted anchors and writes the lock.

## Findings and what changed
- **ponytail:** clean. Its plugin hooks (JavaScript) were not taken; `ponytail-gain` (benchmark scoreboard) and `ponytail-help` skipped.
- **caveman:** clean text. Not taken: `caveman-compress` (it calls the `claude` CLI or an HTTP endpoint and rewrites files in place), `ultracave`, `megacave`, `cavecrew`, hooks. Edits: the alias paragraph pointing at skills we did not take; the commit skill's "no AI attribution" line now defers to the project's or harness's attribution rule.
- **drawio:** clean text. Risk: it told the agent to fetch its references at run time from `raw.githubusercontent.com/.../main`, an unpinned remote instruction source. Fixed: pinned copies in `references/`, read locally. `url` mode (loads app.diagrams.net) only on explicit request. Needs draw.io Desktop (Apache-2.0, offline) for Mermaid conversion and export.
- **graphify:** no injection found. Risks: Step 1 auto-installed the unpinned `graphifyy` package with `--upgrade`, falling back to `--break-system-packages`; an optional Gemini backend sends docs to Google when an API key is set; a sponsor line. Fixed: the skill only checks for the engine and stops if missing (pinned install command in `skills/graphify/UPSTREAM.md`, needs the developer's approval); offline only; sponsor line removed. Kept: `/graphify add <url>` and GitHub cloning, which run only on a URL the user gives.

- **grilling / grill-me:** clean (no URLs, no commands). `grill-me` is upstream's alias that loads `grilling`. Edit: one question at a time instead of a numbered round of questions, to match how the developer likes to be asked. Upstream's rule that facts are looked up by sub-agents, never asked, is kept. The Lead runs it, because the Lead owns all communication with the developer.

## Keep it honest
- `python3 -I kit/crew/tools/vendor_check.py` — local copies match the lock.
- `python3 -I kit/crew/tools/vendor_check.py --upstream` — also proves each `upstream_sha256` against GitHub.
- To update a skill: fetch the new upstream into quarantine, scan, read the diff, bump the commit in `vendor_copy.py`, re-run it, review the new lock.
