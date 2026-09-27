# AGENTS.md — dcc-mcp-openusd

> Navigation map, not a reference manual. Follow the links; don't read
> everything upfront.

dcc-mcp-openusd is the OpenUSD adapter for the DCC Model Context Protocol
(MCP) ecosystem. It is a `uvx`-launchable MCP server with a daemon runtime
that defaults to the Pixar USD bindings.

---

## Repository Contract

**This repository has a `justfile`; run everything through `vx just`.**

| Task | Command |
|------|---------|
| Install dev environment | `vx just dev` |
| Run the server | `vx just serve` |
| Test | `vx just test` |
| Lint | `vx just lint` |
| Format | `vx just format` |
| Lint skills | `vx just lint-skills` |
| Build distributions | `vx just build` |
| Pre-PR gate (lint + format + skills + test + dist) | `vx just preflight` |

**Repository layout**

| Path | Role |
|------|------|
| `src/dcc_mcp_openusd/` | Adapter package — server, daemon runtime, skills |
| `docs/` | Documentation |
| `tests/` | pytest suite |
| `tools/` | Dev helper scripts |
| `justfile` | Canonical task entrypoint |

**Release flow** — `release-please` on `main` drives `CHANGELOG.md` and the version in
`pyproject.toml` from Conventional Commit subjects. Tagging and
publishing run in CI. Never edit `CHANGELOG.md` or a version string by hand.

**Prohibitions**

- Do not bypass the justfile — no direct `uv run pytest` or `ruff` invocations.
- Do not edit `CHANGELOG.md` or version strings manually.
- Do not add a second agent contract file at the repository root; `AGENTS.md` is the single source.
- Do not commit build artefacts produced by `vx just build`.

---

## Agent Contract Files

`AGENTS.md` is the **only** agent contract file at the repository root. It is the
native instruction file for Codex, OpenCode, Cursor, GitHub Copilot, Windsurf,
Cline, Roo Code, Kiro, Trae, and Augment, and Claude Code falls back to it when
no `CLAUDE.md` exists — so do not add `CLAUDE.md`, `GEMINI.md`, `CURSOR.md`, or
any other vendor-specific variant.

**Gemini CLI exception:** Gemini CLI defaults its context file to `GEMINI.md`. To
make it read `AGENTS.md`, set `context.fileName` once in `~/.gemini/settings.json`:

```json
{
  "context": {
    "fileName": ["AGENTS.md", "GEMINI.md"]
  }
}
```
