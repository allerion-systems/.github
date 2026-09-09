#!/usr/bin/env python3
"""Group git commits by Conventional Commit type and flag breaking changes.

Input: lines of `HASH<TAB>SUBJECT<TAB>AUTHOR` (as produced by
`git log --pretty=format:'%H%x09%s%x09%an'`), from a file arg or stdin.

Output: commits bucketed by type, a breaking-change list, and a suggested
semver bump. The model then rewrites each bucket into user-facing prose.

    git log v1.2.0..HEAD --pretty=format:'%H%x09%s%x09%an' | python3 group_commits.py
"""
from __future__ import annotations

import re
import sys

# Conventional Commit type -> changelog section heading.
SECTIONS = {
    "feat": "Added",
    "fix": "Fixed",
    "perf": "Performance",
    "refactor": "Changed",
    "revert": "Changed",
    "docs": "Documentation",
    "build": "Build",
    "ci": "CI",
    "test": "Tests",
    "chore": "Chores",
    "style": "Style",
}
HEADER = re.compile(r"^(?P<type>\w+)(?:\((?P<scope>[^)]+)\))?(?P<bang>!)?:\s*(?P<desc>.+)$")


def main() -> int:
    src = open(sys.argv[1], encoding="utf-8", errors="replace") if len(sys.argv) > 1 else sys.stdin
    buckets: dict[str, list[str]] = {}
    breaking: list[str] = []
    other: list[str] = []
    feats = fixes = 0

    for raw in src:
        raw = raw.rstrip("\n")
        if not raw.strip():
            continue
        parts = raw.split("\t")
        subject = parts[1] if len(parts) > 1 else parts[0]
        short = (parts[0][:7]) if len(parts) > 1 else ""
        m = HEADER.match(subject)
        if not m:
            other.append(f"{subject}  ({short})" if short else subject)
            continue
        typ, scope, bang, desc = (
            m.group("type").lower(), m.group("scope"), m.group("bang"), m.group("desc"))
        entry = f"{desc}" + (f" ({scope})" if scope else "") + (f"  [{short}]" if short else "")
        section = SECTIONS.get(typ, "Other")
        buckets.setdefault(section, []).append(entry)
        if bang or "BREAKING CHANGE" in subject:
            breaking.append(entry)
        if typ == "feat":
            feats += 1
        elif typ == "fix":
            fixes += 1

    if not buckets and not other:
        print("No commits on input.")
        return 1

    if breaking:
        print("=== BREAKING CHANGES ===")
        for e in breaking:
            print(f"  ! {e}")
        print()

    order = ["Added", "Fixed", "Performance", "Changed", "Documentation",
             "Build", "CI", "Tests", "Style", "Chores", "Other"]
    for section in order:
        items = buckets.get(section)
        if not items:
            continue
        print(f"=== {section} ===")
        for e in items:
            print(f"  - {e}")
        print()

    if other:
        print("=== Unconventional (rewrite or drop) ===")
        for e in other:
            print(f"  - {e}")
        print()

    bump = "major" if breaking else "minor" if feats else "patch" if fixes else "patch"
    why = ("breaking change present" if breaking else
           "new features present" if feats else
           "fixes only" if fixes else "no feat/fix — likely patch or no release")
    print(f"SUGGESTED BUMP: {bump}  ({why})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
