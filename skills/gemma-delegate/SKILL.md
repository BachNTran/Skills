---
name: gemma-delegate
description: Delegate bounded, test-driven local work to Gemma 4 26B MoE through opencode --pure. Works best for single-module implementations, repetitive audits, summaries, fixtures, and mechanical edits with explicit allowed files, tests, and parent verification.
---

# Gemma Delegate

Use local Gemma 4 26B MoE through `opencode --pure` when a task can be reduced to a clear packet: exact files, exact rules, exact tests, and an evidence report. Gemma is useful as a local worker, but the parent agent owns integration and correctness.

Do not use this skill to let Gemma explore the current project freely. For calibration or hard coding tests, create a disposable project under `/private/tmp` and run Gemma there.

## What Works Best

Prefer Gemma when the task has all of these:

- A small write scope: ideally one implementation file, sometimes one module folder.
- Existing tests or tests written by the parent before delegation.
- A command that proves success, such as `python3 -m unittest -v`.
- A simple integration point: fill an existing API, normalize existing data, or apply a repeated rule.
- Low blast radius: a bad patch can be rejected without blocking the project.

Good fits:

- Implement one pure function, class, parser, validator, or data transform against tests.
- Apply a mechanical rule across a bounded file list.
- Produce file-by-file summaries or checklist findings in a fixed table.
- Draft boilerplate tests from a visible local pattern when tests are allowed in scope.
- Normalize docs/frontmatter/fixtures where the rule is explicit.

Poor fits:

- Architecture, roadmap, PRD, requirements, or product decisions.
- Broad refactors, dependency upgrades, migrations, auth, crypto, security, or data-loss-prone changes.
- Tasks where Gemma must decide where code belongs.
- Tasks where it may edit tests to make them pass.
- Tasks whose result you cannot verify faster than doing the task yourself.

## Calibration Result

See `README.md` in this skill directory for the full token/speed study.

The reliable pattern was:

1. Parent created a disposable lab in `/private/tmp`.
2. Parent wrote failing tests and a skeleton implementation.
3. Gemma was allowed to edit only the implementation file.
4. Gemma ran `python3 -m unittest -v`.
5. Parent re-ran tests and extra edge checks before accepting the result.

The unreliable pattern was:

- Letting Gemma work inside this skills repo on installer integration.
- Allowing production directories as fixture space.
- Asking for a hard integration change without tightly preserving existing entry points.

Use the reliable pattern by default.

Measured result:

- Successful RangeMap lab: 73,108 input + 5,395 output Gemma tokens, 285 seconds.
- Parent-visible artifact estimate: about 1,699 tokens for packet + tests + final implementation.
- Interpretation: delegation saved premium parent-agent implementation work, but did not reduce total model tokens. Gemma spent about 46x the parent artifact estimate locally, which is acceptable only when local Gemma throughput is cheap enough and the task is well scoped.

## Safety Defaults

- Always use `opencode --pure` unless the developer explicitly asks for configured plugins/MCP tools.
- Do not use `--dangerously-skip-permissions` by default.
- Do not run Gemma on this repository for skill development tests; use `/private/tmp`.
- Use one Gemma worker for write-capable tasks until it passes a pilot shard.
- For parallel work, every worker must have a disjoint write set.
- Parent writes or owns the tests for code tasks unless the task explicitly delegates test drafting.

## Packet Template

Write one packet per shard. Keep it concrete and short.

```markdown
You are a local Gemma coding worker running through opencode --pure.

Task:
[one sentence]

Allowed files:
- [exact file path]

Do not edit:
- [tests, docs, config, generated files, or anything outside the allowed list]

Rules:
- Stay inside the allowed files.
- Do not add dependencies.
- Do not change public APIs unless explicitly requested.
- Do not edit tests unless tests are listed under Allowed files.
- Preserve existing behavior not covered by this task.
- If requirements conflict, stop and report the conflict.

Verification:
- [exact command]

Evidence report:
- Files changed:
- Commands run:
- Test result:
- Integration feedback: how the change connects to the existing API/flow,
  whether default behavior changes, and what risks remain.
```

## Opencode Command

Use the developer's local Gemma model. In this environment it was:

```bash
GEMMA_MODEL="ollama/gemma4-256k"
```

Important: put the short positional prompt before `--file`. With this opencode CLI, placing the prompt after `--file` can be parsed as another file argument.

```bash
opencode run --pure \
  "Execute the attached task. Stay inside the allowed files. Run verification and return the evidence report." \
  --dir "$WORKDIR" \
  --model "$GEMMA_MODEL" \
  --title "gemma-delegate-S01" \
  --file "$PACKET"
```

If a custom opencode agent is required, add `--agent "$GEMMA_AGENT"` after `--model`.

For calibration or risky hard-code tests:

```bash
mkdir -p /private/tmp/gemma-lab
# Parent creates files/tests in /private/tmp/gemma-lab first.
opencode run --pure \
  "Execute the attached task. Edit only the allowed implementation file." \
  --dir /private/tmp/gemma-lab \
  --model "$GEMMA_MODEL" \
  --title "gemma-calibration-1" \
  --file /private/tmp/gemma-lab/task.md
```

## Collaboration Loop

After Gemma returns:

1. Inspect `git status` or the file list.
2. Reject immediately if any forbidden file changed.
3. Read the diff; check that it integrates with existing functions instead of replacing unrelated code.
4. Re-run the stated verification command yourself.
5. Run at least one parent-owned edge check that was not in the prompt.
6. If it fails, send one feedback packet with exact failures and the same allowed file list.
7. If it fails again, stop. Do not let Gemma churn.

Feedback packet:

```markdown
Your previous patch failed verification.

Failure:
[paste exact failing assertion, traceback, or behavior]

Allowed files remain:
- [same file list]

Do not edit:
- [same forbidden files]

Fix only the failure. Run:
[verification command]

Return the evidence report.
```

## Parent Adjudication

Accept a Gemma result only when all are true:

- It changed only allowed files.
- Tests pass when the parent reruns them.
- Parent edge checks pass.
- Existing entry points still exist.
- The integration feedback matches the actual diff.
- The patch is simpler to review than to rewrite.

Reject if Gemma:

- Edits tests to pass implementation work.
- Creates fake production data as fixtures.
- Removes or replaces existing helpers unnecessarily.
- Changes unrelated paths, install targets, config, lockfiles, or generated files.
- Invents APIs or project conventions.
- Repeats patch-application errors instead of making progress.
