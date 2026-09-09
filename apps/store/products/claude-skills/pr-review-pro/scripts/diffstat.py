#!/usr/bin/env python3
"""Risk profile for a unified diff — read it before reviewing line-by-line.

Reads a unified diff from a file argument or stdin and prints a compact risk
profile: per-file churn, whether tests moved alongside code, and heuristic flags
worth a closer look (debug statements, secrets, oversized hunks).

    git diff main...HEAD | python3 diffstat.py
    python3 diffstat.py changes.diff
"""
from __future__ import annotations

import re
import sys

TEST_HINT = re.compile(r"(^|/)(tests?|spec)/|\.(test|spec)\.|_test\.|test_", re.I)
SECRET_HINT = re.compile(
    r"(api[_-]?key|secret|password|passwd|token|private[_-]?key|"
    r"aws_access_key_id|-----BEGIN)", re.I)
DEBUG_HINT = re.compile(r"\b(console\.log|println!|print\(|debugger|binding\.pry|fmt\.Println)\b")


def parse(diff: str):
    files, cur = {}, None
    for line in diff.splitlines():
        if line.startswith("diff --git") or line.startswith("+++ "):
            m = re.search(r"[ab]/(\S+)$", line) or re.search(r"\+\+\+ b/(\S+)", line)
            if m:
                cur = m.group(1)
                files.setdefault(cur, {"add": 0, "del": 0, "secrets": 0, "debug": 0})
            continue
        if cur is None:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            files[cur]["add"] += 1
            body = line[1:]
            if SECRET_HINT.search(body):
                files[cur]["secrets"] += 1
            if DEBUG_HINT.search(body):
                files[cur]["debug"] += 1
        elif line.startswith("-") and not line.startswith("---"):
            files[cur]["del"] += 1
    return files


def main() -> int:
    src = open(sys.argv[1], encoding="utf-8", errors="replace").read() if len(sys.argv) > 1 \
        else sys.stdin.read()
    files = parse(src)
    if not files:
        print("No diff detected on input.")
        return 1

    total_add = sum(f["add"] for f in files.values())
    total_del = sum(f["del"] for f in files.values())
    has_tests = any(TEST_HINT.search(p) for p in files)
    code_files = [p for p in files if not TEST_HINT.search(p)]
    flags: list[str] = []

    print(f"Files changed: {len(files)}   +{total_add} / -{total_del}\n")
    for path, s in sorted(files.items(), key=lambda kv: -(kv[1]["add"] + kv[1]["del"])):
        mark = "  (test)" if TEST_HINT.search(path) else ""
        print(f"  +{s['add']:<5} -{s['del']:<5} {path}{mark}")
        if s["secrets"]:
            flags.append(f"possible secret/credential added in {path} ({s['secrets']} line(s))")
        if s["debug"]:
            flags.append(f"debug statement(s) in {path} ({s['debug']})")
        if s["add"] + s["del"] > 400:
            flags.append(f"oversized change in {path} — consider splitting")

    if code_files and not has_tests:
        flags.append("code changed but no test files touched — verify coverage")
    if total_add + total_del > 800:
        flags.append("large PR overall — review in sittings, watch for unrelated changes")

    print("\nRISK FLAGS" if flags else "\nNo automatic risk flags.")
    for f in flags:
        print(f"  ! {f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
