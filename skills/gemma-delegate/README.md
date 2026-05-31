# Gemma Delegation Notes

This skill is calibrated for local Gemma 4 26B MoE running through:

```bash
opencode run --pure ... --model ollama/gemma4-256k
```

Use it to shift bounded implementation loops off the parent agent. It is not a general-purpose architecture worker.

## Best Operating Envelope

Gemma worked best when the parent agent:

- Created or selected tests before delegation.
- Limited writes to one implementation file.
- Used `opencode --pure`.
- Put the positional prompt before `--file`.
- Re-ran tests and parent-owned edge checks after Gemma returned.

The best prompt shape was:

```bash
opencode run --pure \
  "Execute the attached task. Edit only the allowed implementation file." \
  --dir /private/tmp/gemma-lab \
  --model ollama/gemma4-256k \
  --title gemma-calibration-1 \
  --file /private/tmp/gemma-lab/task.md
```

## Token And Speed Study

Environment:

- Local model: `ollama/gemma4-256k`
- Runner: `opencode --pure`
- Hardware: user's local machine
- Date: 2026-05-30 local time
- Token source for Gemma: opencode SQLite `session` table
- Token source for parent estimate: `cl100k_base` count over visible artifacts

The exact Codex chat token counter for the parent agent is not exposed in this environment. Parent-side numbers below are reproducible artifact estimates, not provider billing counters.

Gemma query used:

```sql
select
  title,
  tokens_input,
  tokens_output,
  (time_updated - time_created) / 1000.0 as seconds
from session
where title = 'gemma-rangemap-calibration-1';
```

### Successful Task

Task: implement a half-open integer `RangeMap` against parent-written tests in a disposable `/private/tmp/gemma-opencode-lab`.

Gemma was allowed to edit only `rangemap.py`. It ran `python3 -m unittest -v`; the parent re-ran that command and extra hidden edge checks.

| Metric | Value |
|---|---:|
| Gemma input tokens | 73,108 |
| Gemma output tokens | 5,395 |
| Gemma total tokens | 78,503 |
| Wall time | 285.252s |
| Tests | 8/8 passed |
| Parent artifact estimate | 1,699 tokens |

Parent artifact estimate counted the delegation packet, visible tests, and final implementation. It does not include hidden chain-of-thought or the full parent chat session because those counters are not exposed here.

Interpretation:

- Delegation did not reduce total model tokens. Gemma used about 46x the parent artifact estimate.
- It did reduce premium parent-agent implementation load: Codex only needed to write the packet, verify the diff, and run edge checks.
- The task was comfortable for a 256K local context: the successful run used 73K input tokens total in opencode accounting, well below 256K.
- Speed was acceptable for background work, but not for blocking critical-path edits: about 4m45s.

### Failed Task

Task: add installer validation directly inside this Skills repo.

| Metric | Value |
|---|---:|
| Gemma input tokens | 491,656 |
| Gemma output tokens | 4,562 |
| Gemma total tokens | 496,218 |
| Wall time | 331.102s |
| Result | rejected |

Failure modes:

- Edited production skill directories as fake fixtures.
- Replaced an existing installer helper instead of integrating with it.
- Introduced a runtime `NameError`.
- Changed an unrelated bootstrap target.

Interpretation:

- The task was too broad and too integrated for Gemma as configured.
- Even with a 256K model, cumulative opencode tool-loop tokens can grow past the model's single-context comfort zone.
- Hard tasks are viable only when the parent narrows them to a one-file implementation with tests.

## Practical Rule

Use Gemma when the local-token burn is cheap and the parent can keep the delegated task below this shape:

```text
one clear API + one allowed implementation file + parent-written tests + exact verification command
```

Do not use Gemma to decide integration boundaries. Have the parent decide the boundary, then let Gemma fill it.
