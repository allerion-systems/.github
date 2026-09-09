# Allerion DevKit — Codex plugin

A Model Context Protocol (MCP) server that adds three deterministic, local-only
developer tools to **OpenAI Codex** (or any MCP client). No API key, no network
calls — everything runs on your machine.

| Tool | What it does |
|------|--------------|
| `review_diff` | Risk-profiles a unified diff: per-file churn, missing tests, secrets, oversized hunks. |
| `draft_changelog` | Groups Conventional Commits into changelog sections and suggests a semver bump. |
| `scaffold_tests` | Maps a source file's testable surface (callables + branch counts) so you write one test per case. |

## Requirements

- Python 3.8+ (standard library only — nothing to `pip install`)
- OpenAI Codex CLI, or any MCP-compatible client

## Install into Codex

1. Note the absolute path to `server.py` in this folder.
2. Add the server to `~/.codex/config.toml`:

   ```toml
   [mcp_servers.allerion_devkit]
   command = "python3"
   args = ["/absolute/path/to/codex-devkit/server.py"]
   ```

3. Restart Codex. The tools appear as `allerion_devkit.review_diff`,
   `allerion_devkit.draft_changelog`, and `allerion_devkit.scaffold_tests`.

## Verify it works

```bash
python3 server.py --selftest
# selftest OK — 3 tools, protocol handshake verified
```

You can also drive it by hand over stdio (newline-delimited JSON-RPC):

```bash
printf '%s\n%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | python3 server.py
```

## Use it in Codex

> "Review the staged diff before I commit."
> Codex calls `allerion_devkit.review_diff` with `git diff --staged` and reports
> the risk profile.

> "Draft release notes from the commits since v1.2.0."
> Codex pipes `git log v1.2.0..HEAD --pretty=format:'%H%x09%s'` into
> `allerion_devkit.draft_changelog`.

> "What should I test in `parser.py`?"
> Codex passes the file to `allerion_devkit.scaffold_tests` and writes tests for
> each branch.

## What's included

- `server.py` — the MCP server (single file, stdlib only)
- `config.example.toml` — copy-paste Codex config
- `AGENTS.md` — guidance Codex reads automatically to use the tools well
- `LICENSE.txt` — commercial license (one seat per purchase)

## License

Commercial license, one developer seat per purchase. See `LICENSE.txt`.
Sold by Allerion Systems — https://allerion.io
