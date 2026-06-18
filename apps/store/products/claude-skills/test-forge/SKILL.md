---
name: test-forge
description: >-
  Generate a focused, runnable test suite for a source file or function. Use
  when the user asks to write tests, add unit tests, improve coverage, or "test
  this". Maps the public surface, enumerates real edge cases, and writes tests
  that would actually fail if the behavior regressed.
license: Commercial — Allerion Systems. One seat per purchase. See LICENSE.txt.
---

# Test Forge

Tests that pin behavior — not tests that restate the implementation.

## When to use

"Write tests for this", "add unit tests", "improve coverage on X", "test this
function", "what cases am I missing".

## Workflow

### 1. Map the surface
- Identify the public functions/methods/classes to test (skip private helpers
  unless they hold real logic).
- Run `scripts/surface.py <file>` to list callable definitions, their
  parameters, and detected branch points (`if`, loops, `try`, early returns,
  raises). Each branch is a case to cover.
- Detect the test framework already in use (pytest, unittest, jest, vitest, go
  test, JUnit). Match it — do not introduce a new one.

### 2. Enumerate cases before writing code
For each function, list cases across these axes — then write a test per case:
- **Happy path**: representative valid input → expected output.
- **Boundaries**: empty, single element, max, zero, negative, very large.
- **Invalid input**: wrong type, null/None, malformed — assert the error.
- **Branches**: every `if`/`else`/`except` from `surface.py` exercised.
- **Side effects**: files written, calls made, state mutated — assert them.

### 3. Write tests that can fail
- Each test asserts a *specific* expected value, not just "no exception".
- Name tests for the case: `test_parse_rejects_empty_input`, not `test_parse_2`.
- Isolate external I/O (network, clock, filesystem, randomness) with the
  framework's standard mocking/fixtures — but never mock away the logic under
  test.
- Add a one-line comment on any non-obvious expected value explaining *why*.

### 4. Verify
- Run the suite. It must pass against current code.
- Then sanity-check: would each test fail if the behavior were reverted? If a
  test passes no matter what, it's worthless — rewrite or delete it.

## Output
- A single test file in the project's framework and layout convention.
- A short note listing any cases you could *not* test and why (e.g. needs a live
  DB), so the gap is visible rather than hidden.

## Rules
- Coverage is a means, not the goal: one assertion that pins real behavior beats
  ten that exercise lines without checking anything.
- Don't test third-party libraries or language built-ins.
- If the code is hard to test, say so and name the smallest refactor that would
  make it testable — don't contort the test to fit untestable code.
