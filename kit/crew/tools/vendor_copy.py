"""Copy inspected upstream skill files from quarantine into kit/crew/skills, apply
documented edits with asserted anchors, and write vendor.lock.json.
Usage: python3 -I vendor_copy.py <quarantine> <kit/crew>"""
import hashlib
import json
import sys
from pathlib import Path

Q, R = Path(sys.argv[1]), Path(sys.argv[2])
sha = lambda b: "sha256:" + hashlib.sha256(b).hexdigest()

UP = {
    "ponytail": ("DietrichGebert/ponytail", "9b58c1ffb790c075ca32e70a89cf1d80588f4abf", "MIT", "DietrichGebert_ponytail"),
    "caveman": ("JuliusBrussee/caveman", "2e08b9177c07bb7249a8a2d1a6758e5db281d002", "Apache-2.0", "JuliusBrussee_caveman"),
    "drawio": ("jgraph/drawio-mcp", "eebe7def96409a15511a51fda958f4a620c2300a", "Apache-2.0", "jgraph_drawio-mcp"),
    "graphify": ("Graphify-Labs/graphify", "565b22bca14036a07acd9fd4abc5905b867a9e89", "Apache-2.0", "Graphify-Labs_graphify"),
    "mattpocock": ("mattpocock/skills", "49dd158d1076134a641b33efb035946536778336", "MIT", "mattpocock_skills"),
}
# (upstream key, upstream path, destination in repo)
FILES = [
    ("ponytail", "skills/ponytail/SKILL.md", "skills/ponytail/SKILL.md"),
    ("ponytail", "skills/ponytail-review/SKILL.md", "skills/ponytail-review/SKILL.md"),
    ("ponytail", "skills/ponytail-audit/SKILL.md", "skills/ponytail-audit/SKILL.md"),
    ("ponytail", "skills/ponytail-debt/SKILL.md", "skills/ponytail-debt/SKILL.md"),
    ("caveman", "plugins/caveman/skills/caveman/SKILL.md", "skills/caveman/SKILL.md"),
    ("caveman", "skills/caveman-commit/SKILL.md", "skills/caveman-commit/SKILL.md"),
    ("caveman", "skills/caveman-review/SKILL.md", "skills/caveman-review/SKILL.md"),
    ("drawio", "plugins/claude-code/skills/drawio/SKILL.md", "skills/drawio/SKILL.md"),
    ("drawio", "shared/xml-reference.md", "skills/drawio/references/xml-reference.md"),
    ("drawio", "shared/style-reference.md", "skills/drawio/references/style-reference.md"),
    ("drawio", "shared/mermaid-reference.md", "skills/drawio/references/mermaid-reference.md"),
    ("graphify", "graphify/skill.md", "skills/graphify/SKILL.md"),
] + [("graphify", f"graphify/skills/claude/references/{n}.md", f"skills/graphify/references/{n}.md")
     for n in ("add-watch", "exports", "extraction-spec", "github-and-merge", "hooks", "query", "transcribe", "update")] + [
    ("mattpocock", "skills/productivity/grilling/SKILL.md", "skills/grilling/SKILL.md"),
    ("mattpocock", "skills/productivity/grill-me/SKILL.md", "skills/grill-me/SKILL.md"),
]

LICENSES = {
    "ponytail": ["LICENSE"],
    "caveman": ["LICENSE", "NOTICE"],
    "drawio": ["LICENSE"],
    "graphify": ["LICENSE", "NOTICE"],
    "mattpocock": ["LICENSE"],
}

GRAPHIFY_STEP1_NEW = '''### Step 1 - Check the engine (never install it from here)

```bash
GRAPHIFY_BIN=$(command -v graphify 2>/dev/null)
if [ -z "$GRAPHIFY_BIN" ]; then echo "graphify engine missing"; exit 1; fi
PYTHON=$(head -1 "$GRAPHIFY_BIN" | tr -d '#!')
case "$PYTHON" in *[!a-zA-Z0-9/_.@-]*) echo "unexpected interpreter path"; exit 1;; esac
"$PYTHON" -c "import graphify" || exit 1
mkdir -p graphify-out
"$PYTHON" -c "import sys; open('graphify-out/.graphify_python', 'w', encoding='utf-8').write(sys.executable)"
"$PYTHON" -c "import os, sys; out_path = os.path.abspath('graphify-out/.graphify_root'); os.chdir(sys.stdin.readline().rstrip('\\n')); open(out_path, 'w', encoding='utf-8').write(os.getcwd())" <<'GRAPHIFY_ROOT_EOF'
INPUT_PATH
GRAPHIFY_ROOT_EOF
```

If the engine is missing, stop and tell the user the pinned install command from `UPSTREAM.md`. Do not run `pip install` or `uv tool install` yourself: the engine is third-party code and the user approves its version.
'''

GRILL_OLD = """Work the tree in **rounds**. The **frontier** is every decision whose prerequisites are already settled: the questions you can ask _now_ without guessing at answers you haven't heard yet. Ask the whole frontier in one round: number each question and give your recommended answer. Then wait for the user's answers before the next round.

Format a round like so:

```
❓ **Q1** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>

---

❓ **Q2** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>
```

Word each question so "yes" accepts your recommended answer.

Each round the user answers reshapes the tree: settled decisions push the frontier outward and unblock questions that depended on them. Recompute the frontier and ask the next round. A question whose answer depends on another question still open in this round belongs to a _later_ round, not this one."""
GRILL_NEW = """Work the tree **one question at a time**. The **frontier** is every decision whose prerequisites are already settled: the questions you can ask _now_ without guessing at answers you haven't heard yet. From the frontier, ask the one question that unblocks the most others, with your recommended answer. Then wait for the answer.

Format each question like so:

```
❓ **<question title>**: <question body, including the choices>

➡️ <your recommended answer>
```

Word each question so "yes" accepts your recommended answer.

Each answer reshapes the tree: settled decisions push the frontier outward and unblock questions that depended on them. Recompute the frontier before the next question. Keep a short list of what is settled; show it every few questions and whenever the user asks."""

EDITS = {
    "skills/grilling/SKILL.md": [
        (GRILL_OLD, GRILL_NEW),
        ("Don't block on it: a running exploration is an unsettled prerequisite, so only the questions downstream of it wait for the sub-agent to report; ask the rest of the frontier now.",
         "Don't block on it: a running exploration is an unsettled prerequisite, so only the questions downstream of it wait for the sub-agent to report; ask another frontier question now."),
    ],
    "skills/caveman/SKILL.md": [
        ("`/caveman ultra` and `/caveman wenyan` are aliases: follow the `ultracave` or `megacave` skill instead of this one. `/caveman status` reports the mode and changes nothing.",
         "`/caveman status` reports the mode and changes nothing."),
    ],
    "skills/caveman-commit/SKILL.md": [
        ('- "Generated with Claude Code" or any AI attribution — unless the user\'s own rule requires an `Assisted-by`/AI-attribution trailer, then add it as a trailer',
         "- AI attribution in the subject or body. Trailers follow the project's or harness's attribution rule (e.g. `Co-Authored-By:`)"),
    ],
    "skills/drawio/SKILL.md": [
        ("When authoring Mermaid, fetch and follow the shared Mermaid reference (all supported diagram types plus flowchart styling — `style`, `classDef`, `linkStyle`):\n\nhttps://raw.githubusercontent.com/jgraph/drawio-mcp/main/shared/mermaid-reference.md",
         "When authoring Mermaid, read and follow the local Mermaid reference (all supported diagram types plus flowchart styling — `style`, `classDef`, `linkStyle`): `references/mermaid-reference.md` beside this file. Never fetch references from the network."),
        ("For the complete draw.io XML reference including common styles, edge routing, containers, layers, tags, metadata, dark mode colors, and XML well-formedness rules, fetch and follow the instructions at:\nhttps://raw.githubusercontent.com/jgraph/drawio-mcp/main/shared/xml-reference.md",
         "For the complete draw.io XML reference including common styles, edge routing, containers, layers, tags, metadata, dark mode colors, and XML well-formedness rules, read `references/xml-reference.md` beside this file (styles: `references/style-reference.md`)."),
        ("If no format is mentioned, just produce the `.drawio` file and open it in draw.io. The user can always ask to export later.",
         "If no format is mentioned, just produce the `.drawio` file and open it in draw.io. The user can always ask to export later.\n\n`url` mode loads the online editor at app.diagrams.net. Use it only when the user asks for `url` by name; the default is a local file."),
    ],
    "skills/graphify/SKILL.md": [
        ("__STEP1__", GRAPHIFY_STEP1_NEW),
        ("""**Before semantic extraction:** check whether `GEMINI_API_KEY` or `GOOGLE_API_KEY` is set. If neither is set, print this one-liner to the user:
> Tip: set `GEMINI_API_KEY` or `GOOGLE_API_KEY` to use Gemini for semantic extraction (`pip install 'graphifyy[gemini]'`).

Print it once, then continue — do not wait for the user to supply a key. If `GEMINI_API_KEY` or `GOOGLE_API_KEY` IS set, use `graphify.llm.extract_corpus_parallel(files, backend="gemini")` for semantic extraction instead of dispatching subagents.""",
         """**Offline only:** never use a cloud extraction backend, even when `GEMINI_API_KEY` or `GOOGLE_API_KEY` is set. Semantic extraction always runs in the host agent's own subagents (Part B). Do not print a tip about API keys."""),
        ("If graphify saved you time, consider supporting it: https://github.com/sponsors/safishamsi\n", ""),
        ("Semantic extraction (only for docs, papers, and images) uses Gemini **only if** `GEMINI_API_KEY`/`GOOGLE_API_KEY` is already set; otherwise the host agent itself is the LLM.",
         "Semantic extraction (only for docs, papers, and images) runs in the host agent itself; this copy never uses a cloud backend."),
        ("__NOKEYS__", "> **No API keys are read.** Semantic extraction is done by the host agent itself — the running session is the LLM. On a host that dispatches subagents (e.g. Claude Code), dispatch them as written in Part B. On a host that cannot dispatch subagents, extract docs/papers/images inline yourself; a code-only corpus has no semantic work (write the empty semantic file, Part B \"Fast path\", and continue to Part C). Never prompt for any API key."),
    ],
}


def apply_edits(dest, text):
    for old, new in EDITS.get(dest, []):
        if old == "__NOKEYS__":
            i = text.index("> **No other API keys are read.**")
            text = text[:i] + new + text[text.index("\n", i):]
            continue
        if old == "__STEP1__":
            start = text.index("### Step 1 - Ensure graphify is installed")
            end = text.index("If the import succeeds, print nothing and move straight to Step 2.")
            end = text.index("\n", end) + 1
            text = text[:start] + new + text[end:]
            continue
        assert text.count(old) == 1, f"anchor not found once in {dest}: {old[:70]!r}"
        text = text.replace(old, new)
    return text


lock = {}
for key, upath, dest in FILES:
    repo, commit, lic, qdir = UP[key]
    raw = (Q / qdir / upath).read_bytes()
    text = apply_edits(dest, raw.decode("utf-8"))
    out = R / dest
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    lock[dest] = {"upstream": repo, "commit": commit, "path": upath, "license": lic,
                  "upstream_sha256": sha(raw), "sha256": sha(out.read_bytes()), "modified": dest in EDITS}

for key, names in LICENSES.items():
    repo, commit, lic, qdir = UP[key]
    for skill_dir in sorted({Path(d).parts[1] for k, _, d in FILES if k == key}):
        for n in names:
            src = (Q / qdir / n).read_bytes()
            (R / "skills" / skill_dir / n).write_bytes(src)

(R / "vendor.lock.json").write_text(json.dumps(lock, indent=1, sort_keys=True) + "\n")
print(f"{len(lock)} files vendored; {sum(v['modified'] for v in lock.values())} modified")
