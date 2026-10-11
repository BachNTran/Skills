# graphify — upstream and engine

- Skill text: `Graphify-Labs/graphify` @ `565b22b`, Apache-2.0. Exact files and hashes: `kit/crew/vendor.lock.json`.
- Local changes: never auto-installs the engine; offline only (no Gemini or other cloud backend); sponsor line removed.

## Engine (needs the developer's approval before install)
The skill drives the `graphify` CLI (package `graphifyy` 0.9.84). It installs only from the developer's frozen private mirror `git@github.com:BachNTran/graphify.git`, tag `bach-0.9.84` (commit `0b23519`, upstream `v0.9.84` at `2cb81c6` plus a `frozen/` folder). Never from PyPI or upstream: the mirror holds hash-locked dependencies and a prebuilt wheel, so an install runs no build and pulls nothing unpinned.

```bash
git clone --depth 1 --branch bach-0.9.84 git@github.com:BachNTran/graphify.git /tmp/graphify-frozen
python3 -m venv ~/.local/share/graphify
~/.local/share/graphify/bin/pip install --require-hashes -r /tmp/graphify-frozen/frozen/requirements.lock
echo "6d1dd1ff2aea3c9abe326010a7d3a2f16ab01ea18e2d478473d1d2120162f233  /tmp/graphify-frozen/frozen/graphifyy-0.9.84-py3-none-any.whl" | sha256sum -c -
~/.local/share/graphify/bin/pip install --no-deps /tmp/graphify-frozen/frozen/graphifyy-0.9.84-py3-none-any.whl
mkdir -p ~/.local/bin && ln -sf ~/.local/share/graphify/bin/graphify ~/.local/bin/graphify
```

Never run `graphify install` / `graphify claude install` / `graphify hook install`: they would overwrite this reviewed copy with upstream's skill, CLAUDE.md section and hooks.

Upgrade only by adding a new `bach-<version>` tag to the mirror (steps in its `frozen/FROZEN.md`) after reading the upstream diff, then changing the pin here.
