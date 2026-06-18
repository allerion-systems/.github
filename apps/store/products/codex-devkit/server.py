#!/usr/bin/env python3
"""Allerion DevKit — an MCP server for OpenAI Codex (and any MCP client).

Pure Python standard library. Speaks the Model Context Protocol over stdio
(newline-delimited JSON-RPC 2.0). Exposes three deterministic, local-only dev
tools — no network, no API key, nothing leaves the machine:

    review_diff       risk-profile a unified diff (churn, missing tests, secrets)
    draft_changelog   group conventional commits + suggest a semver bump
    scaffold_tests    map a source file's testable surface (Python + heuristics)

Install into Codex by adding to ~/.codex/config.toml:

    [mcp_servers.allerion_devkit]
    command = "python3"
    args = ["/abs/path/to/codex-devkit/server.py"]

Then in Codex the tools appear as allerion_devkit.review_diff, etc.

Run the built-in self-test (no MCP client needed):

    python3 server.py --selftest
"""
from __future__ import annotations

import json
import re
import sys

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "allerion-devkit", "version": "1.0.0"}

# --------------------------------------------------------------------- tool impls
TEST_HINT = re.compile(r"(^|/)(tests?|spec)/|\.(test|spec)\.|_test\.|test_", re.I)
SECRET_HINT = re.compile(
    r"(api[_-]?key|secret|password|passwd|token|private[_-]?key|"
    r"aws_access_key_id|-----BEGIN)", re.I)
DEBUG_HINT = re.compile(r"\b(console\.log|println!|print\(|debugger|binding\.pry|fmt\.Println)\b")
CC_HEADER = re.compile(r"^(?P<type>\w+)(?:\((?P<scope>[^)]+)\))?(?P<bang>!)?:\s*(?P<desc>.+)$")
CC_SECTIONS = {
    "feat": "Added", "fix": "Fixed", "perf": "Performance", "refactor": "Changed",
    "docs": "Documentation", "test": "Tests", "build": "Build", "ci": "CI",
    "chore": "Chores", "style": "Style", "revert": "Changed",
}


def review_diff(diff: str) -> str:
    files: dict[str, dict] = {}
    cur = None
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
            if SECRET_HINT.search(line[1:]):
                files[cur]["secrets"] += 1
            if DEBUG_HINT.search(line[1:]):
                files[cur]["debug"] += 1
        elif line.startswith("-") and not line.startswith("---"):
            files[cur]["del"] += 1

    if not files:
        return "No diff detected on input."

    add = sum(f["add"] for f in files.values())
    dele = sum(f["del"] for f in files.values())
    has_tests = any(TEST_HINT.search(p) for p in files)
    code_files = [p for p in files if not TEST_HINT.search(p)]
    out = [f"Files changed: {len(files)}   +{add} / -{dele}", ""]
    flags: list[str] = []
    for path, s in sorted(files.items(), key=lambda kv: -(kv[1]["add"] + kv[1]["del"])):
        mark = "  (test)" if TEST_HINT.search(path) else ""
        out.append(f"  +{s['add']:<5} -{s['del']:<5} {path}{mark}")
        if s["secrets"]:
            flags.append(f"possible secret added in {path} ({s['secrets']} line(s))")
        if s["debug"]:
            flags.append(f"debug statement(s) in {path} ({s['debug']})")
        if s["add"] + s["del"] > 400:
            flags.append(f"oversized change in {path} — consider splitting")
    if code_files and not has_tests:
        flags.append("code changed but no test files touched — verify coverage")
    if add + dele > 800:
        flags.append("large PR overall — review in sittings")
    out.append("")
    out.append("RISK FLAGS" if flags else "No automatic risk flags.")
    out += [f"  ! {f}" for f in flags]
    return "\n".join(out)


def draft_changelog(commits: str) -> str:
    buckets: dict[str, list[str]] = {}
    breaking: list[str] = []
    feats = fixes = 0
    for raw in commits.splitlines():
        if not raw.strip():
            continue
        parts = raw.split("\t")
        subject = parts[1] if len(parts) > 1 else parts[0]
        short = parts[0][:7] if len(parts) > 1 else ""
        m = CC_HEADER.match(subject)
        if not m:
            buckets.setdefault("Other", []).append(subject)
            continue
        typ = m.group("type").lower()
        entry = m.group("desc") + (f" ({m.group('scope')})" if m.group("scope") else "")
        entry += f"  [{short}]" if short else ""
        buckets.setdefault(CC_SECTIONS.get(typ, "Other"), []).append(entry)
        if m.group("bang") or "BREAKING CHANGE" in subject:
            breaking.append(entry)
        feats += typ == "feat"
        fixes += typ == "fix"
    if not buckets:
        return "No commits on input."
    out: list[str] = []
    if breaking:
        out += ["### ⚠ Breaking changes"] + [f"- {e}" for e in breaking] + [""]
    for section in ["Added", "Fixed", "Performance", "Changed", "Documentation",
                    "Build", "CI", "Tests", "Style", "Chores", "Other"]:
        if buckets.get(section):
            out.append(f"### {section}")
            out += [f"- {e}" for e in buckets[section]]
            out.append("")
    bump = "major" if breaking else "minor" if feats else "patch"
    out.append(f"SUGGESTED BUMP: {bump}")
    return "\n".join(out).rstrip()


def scaffold_tests(source: str, filename: str = "module.py") -> str:
    if filename.endswith(".py"):
        import ast
        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            return f"(could not parse as Python: {e})"
        rows = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                    and not node.name.startswith("_"):
                params = [a.arg for a in node.args.args if a.arg not in ("self", "cls")]
                branches = sum(1 for n in ast.walk(node)
                               if isinstance(n, (ast.If, ast.For, ast.While, ast.Try, ast.Raise)))
                rows.append(f"  def {node.name}({', '.join(params)})  [branches={branches}]")
            elif isinstance(node, ast.ClassDef):
                rows.append(f"  class {node.name}")
        body = "\n".join(rows) or "  (no public callables found)"
        return ("Testable surface:\n" + body +
                "\n\nWrite one test per branch / boundary / error case above "
                "(happy path, empty, invalid input, each branch).")
    # generic fallback
    defs = re.findall(r"(?:function|func|def)\s+(\w+)\s*\(", source)
    branches = len(re.findall(r"\b(if|for|while|switch|catch)\b", source))
    listing = "\n".join(f"  {d}()" for d in dict.fromkeys(defs)) or "  (no defs detected)"
    return (f"Callables in {filename}:\n{listing}\n\n~{branches} branch point(s) — "
            "cover each, plus boundaries and invalid input.")


TOOLS = {
    "review_diff": {
        "fn": lambda a: review_diff(a.get("diff", "")),
        "description": "Risk-profile a unified diff: churn per file, missing tests, "
                       "secrets, oversized hunks. Run before reviewing line-by-line.",
        "schema": {"type": "object",
                   "properties": {"diff": {"type": "string",
                                           "description": "Unified diff text (git diff output)."}},
                   "required": ["diff"]},
    },
    "draft_changelog": {
        "fn": lambda a: draft_changelog(a.get("commits", "")),
        "description": "Group Conventional Commits into changelog sections and suggest a "
                       "semver bump. Input: lines of 'HASH<TAB>SUBJECT' from git log.",
        "schema": {"type": "object",
                   "properties": {"commits": {"type": "string",
                                              "description": "git log lines: HASH<TAB>SUBJECT."}},
                   "required": ["commits"]},
    },
    "scaffold_tests": {
        "fn": lambda a: scaffold_tests(a.get("source", ""), a.get("filename", "module.py")),
        "description": "Map a source file's testable surface (callables, branch counts) so "
                       "you can write one test per branch/boundary/error case.",
        "schema": {"type": "object",
                   "properties": {
                       "source": {"type": "string", "description": "Source file contents."},
                       "filename": {"type": "string",
                                    "description": "Filename, used to pick the parser."}},
                   "required": ["source"]},
    },
}


# ----------------------------------------------------------------------- protocol
def handle(msg: dict) -> dict | None:
    mid = msg.get("id")
    method = msg.get("method")
    if method == "initialize":
        return _ok(mid, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        })
    if method == "notifications/initialized" or method is None:
        return None  # notification, no response
    if method == "tools/list":
        return _ok(mid, {"tools": [
            {"name": n, "description": t["description"], "inputSchema": t["schema"]}
            for n, t in TOOLS.items()
        ]})
    if method == "tools/call":
        params = msg.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        tool = TOOLS.get(name)
        if not tool:
            return _err(mid, -32602, f"unknown tool: {name}")
        try:
            text = tool["fn"](args)
        except Exception as e:  # noqa: BLE001 — surface as a tool error, not a crash
            return _ok(mid, {"content": [{"type": "text", "text": f"error: {e}"}],
                             "isError": True})
        return _ok(mid, {"content": [{"type": "text", "text": text}]})
    if method == "ping":
        return _ok(mid, {})
    return _err(mid, -32601, f"method not found: {method}")


def _ok(mid, result):
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def _err(mid, code, message):
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": code, "message": message}}


def serve() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = handle(msg)
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


def selftest() -> int:
    diff = ("diff --git a/app.py b/app.py\n+++ b/app.py\n"
            "+print('debug')\n+api_key = 'x'\n-old = 1\n")
    assert "RISK FLAGS" in review_diff(diff)
    assert "secret" in review_diff(diff).lower()
    cl = draft_changelog("abc1234\tfeat: add export\ndef5678\tfix!: drop old flag")
    assert "Added" in cl and "Breaking" in cl and "major" in cl
    surf = scaffold_tests("def add(a, b):\n    if a:\n        return a\n    return b\n", "m.py")
    assert "add" in surf and "branches=1" in surf
    init = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init["result"]["serverInfo"]["name"] == "allerion-devkit"
    listed = handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert {t["name"] for t in listed["result"]["tools"]} == set(TOOLS)
    called = handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                     "params": {"name": "review_diff", "arguments": {"diff": diff}}})
    assert called["result"]["content"][0]["text"]
    print("selftest OK — 3 tools, protocol handshake verified")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    serve()
