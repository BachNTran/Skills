#!/usr/bin/env python3
"""Deterministic prompt-injection / supply-chain scan for third-party skill files.

Usage: python3 -I skill_scan.py <dir> [--json]
Flags lines a human must read. It never decides "safe" — it narrows where to look.
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

HIDDEN = {
    0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF, 0x00AD,          # zero-width / soft hyphen
    0x202A, 0x202B, 0x202C, 0x202D, 0x202E,                  # bidi embedding / override
    0x2066, 0x2067, 0x2068, 0x2069,                          # bidi isolates
}

RULES = [
    ("override", r"ignore (all |any )?(previous|prior|above|earlier) (instructions|rules|messages)"),
    ("override", r"disregard (the |all |any )?(system|previous|prior|above)"),
    ("override", r"(you are now|from now on you are|new instructions:|system prompt|developer message)"),
    ("override", r"do not (tell|inform|mention to) the user|without (telling|asking|informing) the user"),
    ("authority", r"(anthropic|openai|claude) (requires|instructs|says you must)|admin(istrator)? override"),
    ("secrets", r"(\.ssh/|id_rsa|\.aws/credentials|\.env\b|api[_-]?key|secret|token|password|keychain)"),
    ("exfil", r"(curl|wget|fetch\(|https?\.request|urllib|requests\.(get|post)|XMLHttpRequest|nc -|/dev/tcp)"),
    ("exec", r"(\beval\(|\bexec\(|child_process|subprocess|os\.system|spawn\(|execSync|\| *(ba|z)?sh\b)"),
    ("destructive", r"(rm -rf|git push --force|git reset --hard|chmod 777|sudo\b|mkfs|dd if=)"),
    ("persistence", r"(settings\.json|\.bashrc|\.zshrc|crontab|launchctl|LaunchAgents|hooks?\b.*(add|install|write))"),
    ("permissions", r"(dangerously|--no-verify|skip ?permissions|bypassPermissions|allowedTools|permission mode)"),
    ("encoded", r"[A-Za-z0-9+/]{120,}={0,2}"),
    ("html-comment", r"<!--"),
    ("url", r"https?://[^\s)\"'>]+"),
]
COMPILED = [(k, re.compile(p, re.I)) for k, p in RULES]


def scan_file(path: Path):
    findings = []
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [{"line": 0, "kind": "binary", "text": "not utf-8"}]
    for n, line in enumerate(text.splitlines(), 1):
        for ch in line:
            cp = ord(ch)
            if cp in HIDDEN or 0xE0000 <= cp <= 0xE007F or (unicodedata.category(ch) == "Cf" and cp not in (0x200D,)):
                findings.append({"line": n, "kind": "hidden-unicode", "text": f"U+{cp:04X} in: {line[:120]!r}"})
                break
        for kind, rx in COMPILED:
            m = rx.search(line)
            if m:
                findings.append({"line": n, "kind": kind, "text": line.strip()[:200]})
    return findings


def main():
    root = Path(sys.argv[1])
    as_json = "--json" in sys.argv
    report = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            f = scan_file(p)
            if f:
                report[str(p.relative_to(root))] = f
    if as_json:
        print(json.dumps(report, indent=1))
        return
    for path, items in report.items():
        kinds = {}
        for i in items:
            kinds[i["kind"]] = kinds.get(i["kind"], 0) + 1
        print(f"\n## {path}  " + " ".join(f"{k}={v}" for k, v in sorted(kinds.items())))
        for i in items:
            if i["kind"] not in ("url",):
                print(f"  {i['line']:>5} [{i['kind']}] {i['text']}")
        urls = sorted({u for i in items if i["kind"] == "url" for u in re.findall(r"https?://[^\s)\"'>`]+", i["text"])})
        if urls:
            print("  urls: " + ", ".join(urls))


if __name__ == "__main__":
    main()
