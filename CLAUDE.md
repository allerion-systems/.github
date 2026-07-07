# CLAUDE.md

## What this repo is

This is the **`allerion-systems/.github`** repository — GitHub's special
org-wide "community health files" repo. Its contents are used as
**org-wide fallback defaults** for every other repository in the
`allerion-systems` organization that doesn't provide its own copy of the
same file.

This repo is currently **almost empty**. It contains exactly one file
beyond git metadata:

```
profile/README.md
```

There is one commit in history: `Initialize organization profile`.

## Inventory

- **`profile/README.md`** — the org profile README. GitHub renders this
  file on the organization's public homepage (`github.com/allerion-systems`).
  It currently contains marketing copy describing Allerion as building
  "autonomous intelligence for the built world" (digital twin / BIM,
  construction ERP, multi-agent orchestration, sovereign/self-hosted AI).
  This is the *only* content in the repo — there is no other file, at
  root or under `.github/`.

Everything else GitHub *permits* an org `.github` repo to hold —
`workflow-templates/`, `ISSUE_TEMPLATE/` or `.github/ISSUE_TEMPLATE/`,
`PULL_REQUEST_TEMPLATE.md` (root or `.github/`), `CODEOWNERS`,
`SECURITY.md`, `CONTRIBUTING.md`, `FUNDING.yml`, reusable `action.yml`
files — **does not exist here yet**. Do not assume any of it is present;
verify with `git ls-files` before referencing it.

## How changes here propagate (read before editing)

GitHub treats specific files in an org's `.github` repo as **implicit,
org-wide defaults**:

- `profile/README.md` renders on the org's public GitHub homepage —
  changing it changes what every visitor to `github.com/allerion-systems`
  sees, immediately.
- If files like `CODEOWNERS`, `SECURITY.md`, `CONTRIBUTING.md`,
  issue templates, or a pull request template are ever added here, they
  become the **fallback used by any repo in the org that does not have
  its own copy of that same file**. A repo-local file always wins, but a
  repo with no local file silently inherits whatever lives here.
- Similarly, anything placed under `workflow-templates/` becomes an
  org-wide reusable GitHub Actions template offered to every repo via
  "Actions → New workflow", regardless of whether any single repo owner
  asked for it.

This is non-obvious and has a wide blast radius: a small, well-intentioned
edit in this repo can silently change behavior/defaults/branding across
every other repository in the org that hasn't opted out with its own
local override.

## Conventions

There is no established pattern yet for workflow templates or issue
templates in this repo — none exist. If asked to add one, follow
GitHub's documented conventions (`workflow-templates/*.yml` +
matching `workflow-templates/*.properties.json`;
`.github/ISSUE_TEMPLATE/*.yml` or `.md`) rather than inventing a
repo-specific structure, since none is established here to follow.

## What an AI agent must NOT casually change here

- **`profile/README.md`** — this is live org branding/marketing copy
  visible on the public org homepage. Treat content/tone changes as
  editorial decisions requiring explicit user sign-off, not routine edits.
- **Any future `CODEOWNERS`, `SECURITY.md`, security policy, or
  workflow-template file** — because these become silent org-wide
  fallbacks (see above), adding, editing, or removing them can change
  default behavior in every other `allerion-systems` repo that lacks its
  own copy. Confirm the intended blast radius with the user before
  touching such a file.
- Do not invent or assume the existence of files this repo does not
  currently have (issue templates, PR template, CONTRIBUTING, FUNDING,
  reusable actions). Verify with `git ls-files` first.
