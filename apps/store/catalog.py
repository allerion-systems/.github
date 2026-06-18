"""Product catalog for the Allerion Skills Store.

Each product is a digital download (Claude Skill or Codex plugin) sold as a
one-time Stripe purchase. `source` paths are relative to this file and are zipped
on the fly at delivery time (see fulfillment.py).

Prices are in USD cents. To use pre-created Stripe Price ids instead of inline
price_data, set the matching env var (e.g. STRIPE_PRICE_PR_REVIEW_PRO).
"""
from __future__ import annotations

import os

# slug -> product definition
PRODUCTS: dict[str, dict] = {
    "pr-review-pro": {
        "name": "PR Review Pro",
        "kind": "Claude Skill",
        "price": 4900,  # $49.00
        "tagline": "Senior-engineer pull-request reviews, on demand.",
        "blurb": "A Claude Agent Skill that reviews diffs the way a strong senior "
                 "engineer does — correctness and security first, severity-ranked "
                 "findings with fixes, and a plain merge / don't-merge verdict. "
                 "Ships with a diff risk-profiler script.",
        "sources": ["products/claude-skills/pr-review-pro"],
        "price_env": "STRIPE_PRICE_PR_REVIEW_PRO",
    },
    "changelog-craft": {
        "name": "Changelog Craft",
        "kind": "Claude Skill",
        "price": 2900,  # $29.00
        "tagline": "Git history → release notes a human can read.",
        "blurb": "Turns raw commits into grouped, rewritten release notes, flags "
                 "breaking changes, and recommends the semver bump. Includes a "
                 "Conventional-Commit grouping script.",
        "sources": ["products/claude-skills/changelog-craft"],
        "price_env": "STRIPE_PRICE_CHANGELOG_CRAFT",
    },
    "test-forge": {
        "name": "Test Forge",
        "kind": "Claude Skill",
        "price": 3900,  # $39.00
        "tagline": "Tests that pin behavior, not restate the code.",
        "blurb": "Maps a file's testable surface, enumerates real edge cases, and "
                 "writes tests that would fail on regression. Includes a "
                 "surface-mapping script (precise for Python, heuristic elsewhere).",
        "sources": ["products/claude-skills/test-forge"],
        "price_env": "STRIPE_PRICE_TEST_FORGE",
    },
    "codex-devkit": {
        "name": "Allerion DevKit for Codex",
        "kind": "Codex Plugin (MCP)",
        "price": 7900,  # $79.00
        "tagline": "review · changelog · test — inside OpenAI Codex.",
        "blurb": "A Model Context Protocol server that adds review_diff, "
                 "draft_changelog, and scaffold_tests to OpenAI Codex. Pure Python, "
                 "local-only, no API key. Drop one block into ~/.codex/config.toml.",
        "sources": ["products/codex-devkit"],
        "price_env": "STRIPE_PRICE_CODEX_DEVKIT",
    },
    "devkit-bundle": {
        "name": "Allerion DevKit — Complete Bundle",
        "kind": "Bundle",
        "price": 14900,  # $149.00 (vs $196 a la carte)
        "tagline": "All three skills + the Codex plugin. Save 24%.",
        "blurb": "Everything: PR Review Pro, Changelog Craft, Test Forge, and the "
                 "Codex DevKit MCP plugin — the same toolkit across Claude and Codex. "
                 "One download, one license.",
        "sources": [
            "products/claude-skills/pr-review-pro",
            "products/claude-skills/changelog-craft",
            "products/claude-skills/test-forge",
            "products/codex-devkit",
        ],
        "price_env": "STRIPE_PRICE_DEVKIT_BUNDLE",
    },
}

LICENSE_TEMPLATE = """\
ALLERION SYSTEMS — COMMERCIAL LICENSE
=====================================

Product : {product}
Licensee: {email}
License : {license_key}
Issued  : {issued}

Grant
-----
Allerion Systems grants the licensee a non-exclusive, non-transferable license
to use this product for internal software-development purposes, for one (1)
developer seat.

You MAY: use it in personal and commercial projects, modify it for your own use,
and run it on any machine you personally develop on.

You MAY NOT: resell, sublicense, or redistribute the product or substantial
portions of it as a competing product; remove this license notice.

No warranty. Provided "as is". Questions: https://allerion.io

This license key is tied to the licensee email above and was issued at purchase.
"""


def usd(cents: int) -> str:
    return f"${cents / 100:,.2f}".rstrip("0").rstrip(".") if cents % 100 else f"${cents // 100}"


def price_id(slug: str) -> str:
    p = PRODUCTS.get(slug, {})
    return os.environ.get(p.get("price_env", ""), "").strip()
