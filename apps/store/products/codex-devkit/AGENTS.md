# Allerion DevKit — agent guidance

You have three local tools from the `allerion_devkit` MCP server. They are
deterministic and run on the user's machine — prefer them over guessing.

- **Before reviewing a diff or committing**, call `review_diff` with the output
  of `git diff` (or `git diff --staged`). Read the risk flags first, then review
  the flagged files closely. Treat a "possible secret" flag as blocking until
  confirmed otherwise.

- **When asked for a changelog or release notes**, get commits with
  `git log <base>..HEAD --pretty=format:'%H%x09%s'` and pass them to
  `draft_changelog`. Use its sections and suggested bump as the skeleton, then
  rewrite each line into user-facing prose. Put breaking changes first.

- **When asked to write or improve tests**, pass the source file to
  `scaffold_tests` to enumerate the callables and branch points, then write one
  test per branch, boundary, and error case. Tests must assert specific values
  and would fail if the behavior regressed.

These tools summarize and map; you still do the judgment. Never paste secrets,
tokens, or customer data into tool arguments.
