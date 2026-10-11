#!/usr/bin/env python3
"""Verify vendored skill files against vendor.lock.json.

  python3 -I kit/crew/tools/vendor_check.py            # local copies match the lock?
  python3 -I kit/crew/tools/vendor_check.py --upstream # also re-fetch each upstream file at its pinned
                                                     # commit (gh api) and confirm upstream_sha256
Exit 0 clean, 1 on any mismatch. One line per problem.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # kit/crew


def sha(b: bytes) -> str:
    return "sha256:" + hashlib.sha256(b).hexdigest()


def upstream_bytes(e: dict) -> bytes:
    return subprocess.run(
        ["gh", "api", "-H", "Accept: application/vnd.github.raw",
         f"repos/{e['upstream']}/contents/{e['path']}?ref={e['commit']}"],
        check=True, capture_output=True).stdout


def check(lock: dict, upstream: bool) -> list[str]:
    bad = []
    for dest, e in sorted(lock.items()):
        p = ROOT / dest
        if not p.is_file():
            bad.append(f"MISSING   {dest}")
        elif sha(p.read_bytes()) != e["sha256"]:
            bad.append(f"CHANGED   {dest}  → edited outside kit/crew/tools/vendor_copy.py; review, then re-run it")
        if upstream and sha(upstream_bytes(e)) != e["upstream_sha256"]:
            bad.append(f"UPSTREAM  {dest}  ≠ {e['upstream']}@{e['commit'][:7]}:{e['path']}")
    return bad


def main() -> int:
    lock = json.loads((ROOT / "vendor.lock.json").read_text())
    bad = check(lock, "--upstream" in sys.argv)
    print("\n".join(bad) if bad else f"vendor: {len(lock)} files match the lock")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
