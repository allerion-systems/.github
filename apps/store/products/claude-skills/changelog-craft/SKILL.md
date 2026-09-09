---
name: changelog-craft
description: >-
  Turn raw git history into a clean, human-readable changelog or release notes.
  Use when the user asks to write a changelog, draft release notes, summarize
  commits since the last tag, or prepare a version bump. Groups changes by type,
  rewrites terse commit subjects into user-facing prose, and flags breaking
  changes.
license: Commercial — Allerion Systems. One seat per purchase. See LICENSE.txt.
---

# Changelog Craft

Release notes that a *user* can read — not a dump of commit subjects.

## When to use

"Write a changelog", "draft release notes", "what changed since v1.2.0",
"summarize the commits for this release", "prep the version bump".

## Workflow

### 1. Collect the commit range
- Find the last release tag: `git describe --tags --abbrev=0` (or ask the user
  for the base ref).
- Get the log in a parseable shape:
  `git log <base>..HEAD --pretty=format:'%H%x09%s%x09%an'`
- Pipe it through `scripts/group_commits.py` to bucket commits by Conventional
  Commit type (feat/fix/perf/docs/refactor/etc.) and surface anything marked
  breaking (`!` or `BREAKING CHANGE`).

### 2. Rewrite for the reader
Commit subjects are written for other developers; changelog entries are written
for users. For each entry:
- Lead with the user-visible effect, not the implementation.
  `fix: nil deref in cache` → "Fixed a crash when the cache was empty."
- Drop internal-only churn (lint, formatting, CI tweaks) unless the user wants a
  full technical log.
- Merge several commits that deliver one feature into a single entry.

### 3. Structure the output
Use Keep a Changelog conventions unless the project clearly uses another:

```
## [1.3.0] — 2026-06-18

### ⚠ Breaking changes
- <what broke, and the migration step>

### Added
- <new capability, user-facing>

### Fixed
- <bug the user would have noticed>

### Changed / Performance
- <behavior or speed changes>
```

### 4. Version suggestion
From the grouped commits, recommend a semver bump and say why:
- any breaking change → **major**
- any `feat` → **minor**
- only `fix`/`perf`/`docs` → **patch**
State the recommendation; let the user confirm.

## Rules
- Never invent changes that aren't in the log. If a commit is cryptic, ask or
  mark it `(needs description)` rather than guessing.
- Keep entries to one line where possible; link issue/PR numbers if present in
  the subject.
- Put breaking changes first and make the migration step explicit.
