---
name: pr-review-pro
description: >-
  Senior-engineer pull-request review. Use when the user asks to review a PR,
  review a diff, check changes before merge, or asks "is this ready to ship".
  Produces a triaged, severity-ranked review covering correctness, security,
  tests, and maintainability — and tells the user plainly whether to merge.
license: Commercial — Allerion Systems. One seat per purchase. See LICENSE.txt.
---

# PR Review Pro

A disciplined review pass that mirrors how a strong senior engineer reads a diff:
correctness first, then security, then the things that cost you later.

## When to use

Trigger this skill when the user wants a pull request, diff, or branch reviewed —
phrases like "review this PR", "check my changes", "anything wrong before I merge",
"look over this diff".

## How to run the review

Work in this order. Do **not** reorder — correctness bugs that ship are far more
expensive than style nits, so they come first and get the most attention.

### 1. Establish the change's intent
- Read the PR title/description (or ask the user) for the *intended* behavior.
- Get the diff. If in a git repo: `git diff main...HEAD` (or the stated base).
- Run `scripts/diffstat.py` against the diff to get a size/risk profile before
  reading line-by-line — it flags oversized diffs, test coverage gaps, and
  high-risk file touches so you know where to spend attention.

### 2. Correctness (highest priority)
For each changed hunk, ask:
- Does this do what the description claims?
- Off-by-one, null/undefined, empty-collection, and boundary cases?
- Error paths: are failures handled, or swallowed? Are resources released?
- Concurrency: shared state, races, ordering assumptions?
- Did a refactor change behavior that callers depend on?

### 3. Security & data safety
- Untrusted input reaching a sink (SQL, shell, filesystem path, HTML, eval)?
- Secrets, tokens, or PII added to code, logs, or fixtures?
- AuthZ/AuthN checks present on new endpoints and state-changing actions?
- Dependency or supply-chain additions — are they necessary and pinned?

### 4. Tests
- Is the new behavior covered? Would the tests fail if the change were reverted?
- Are edge cases from step 2 tested, not just the happy path?
- Flag assertions that can't fail (e.g. `assert True`, mocked-away logic).

### 5. Maintainability (lowest priority — keep brief)
- Naming, dead code, duplicated logic, premature abstraction.
- Only raise these if they genuinely impede the next reader. Do not pad the
  review with nits.

## Output format

Lead with the verdict, then the findings:

```
VERDICT: <merge | merge after fixes | do not merge>  — one-line reason.

BLOCKING
  [correctness] file.py:42 — <what's wrong, why it breaks, the fix>
SHOULD-FIX
  [security] api.py:88 — <issue + fix>
CONSIDER
  [maintainability] util.py:12 — <suggestion>
```

Rules for the output:
- Every finding cites `file:line` and states the *fix*, not just the problem.
- Rank by severity (BLOCKING → SHOULD-FIX → CONSIDER), not by file order.
- If you're uncertain a finding is real, say so and put it in CONSIDER.
- If the diff is clean, say so plainly and merge — do not invent issues.

## Calibration

- A 4-line config change and a 400-line auth rewrite get *different* reviews.
  Use the `diffstat.py` risk profile to scale depth.
- Prefer one precise blocking finding over ten speculative nits.
- Never approve code you could not explain back to the author.
