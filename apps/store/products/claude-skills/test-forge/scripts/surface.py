#!/usr/bin/env python3
"""List the testable surface of a source file: callables, params, branch points.

Supports Python precisely (via the `ast` module) and falls back to regex
heuristics for JS/TS/Go/Java/Ruby so the skill still gets a useful map of what
to test in any language.

    python3 surface.py path/to/module.py
    python3 surface.py src/handler.ts
"""
from __future__ import annotations

import ast
import re
import sys


def python_surface(src: str) -> list[str]:
    out: list[str] = []
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return [f"(could not parse as Python: {e})"]

    branch_types = (ast.If, ast.For, ast.While, ast.Try, ast.With,
                    ast.BoolOp, ast.IfExp, ast.Raise, ast.Match)

    def describe(fn: ast.AST, qualname: str) -> str:
        args = fn.args  # type: ignore[attr-defined]
        names = [a.arg for a in args.args if a.arg not in ("self", "cls")]
        if args.vararg:
            names.append("*" + args.vararg.arg)
        if args.kwarg:
            names.append("**" + args.kwarg.arg)
        branches = sum(1 for n in ast.walk(fn) if isinstance(n, branch_types))
        raises = sum(1 for n in ast.walk(fn) if isinstance(n, ast.Raise))
        returns = sum(1 for n in ast.walk(fn) if isinstance(n, ast.Return))
        bits = [f"branches={branches}", f"raises={raises}", f"returns={returns}"]
        return f"  def {qualname}({', '.join(names)})  [{', '.join(bits)}]"

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_"):
                out.append(describe(node, node.name))
        elif isinstance(node, ast.ClassDef):
            out.append(f"  class {node.name}")
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                        and not sub.name.startswith("_"):
                    out.append(describe(sub, f"{node.name}.{sub.name}"))
    return out or ["  (no public callables found)"]


DEF_PATTERNS = [
    re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)"),
    re.compile(r"^\s*(?:export\s+)?(?:const|let)\s+(\w+)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>"),
    re.compile(r"^\s*func\s+(?:\([^)]*\)\s*)?(\w+)\s*\(([^)]*)\)"),          # Go
    re.compile(r"^\s*def\s+(\w+)\s*\(([^)]*)\)"),                            # Ruby
    re.compile(r"^\s*(?:public|protected|private)?\s*\w[\w<>\[\]]*\s+(\w+)\s*\(([^)]*)\)\s*\{"),  # Java
]
BRANCH_RE = re.compile(r"\b(if|for|while|switch|case|catch|else)\b|\?\s*[^:]+:")


def generic_surface(src: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for line in src.splitlines():
        for pat in DEF_PATTERNS:
            m = pat.match(line)
            if m and m.group(1) not in seen and m.group(1) not in ("if", "for", "while", "switch"):
                seen.add(m.group(1))
                params = ", ".join(p.strip() for p in m.group(2).split(",") if p.strip())
                out.append(f"  {m.group(1)}({params})")
                break
    branches = len(BRANCH_RE.findall(src))
    out.append(f"  [~{branches} branch point(s) across file — cover each]")
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: surface.py <source-file>", file=sys.stderr)
        return 2
    path = sys.argv[1]
    src = open(path, encoding="utf-8", errors="replace").read()
    print(f"Testable surface of {path}:\n")
    rows = python_surface(src) if path.endswith(".py") else generic_surface(src)
    print("\n".join(rows))
    print("\nWrite one test per branch / boundary / error case listed above.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
