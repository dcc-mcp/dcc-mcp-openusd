# AGENTS.md — dcc-mcp-openusd

> OpenUSD adapter and skills for the DCC-MCP ecosystem: a headless OpenUSD-oriented MCP server that authors portable USD projects, stages, references, and USDZ-like archives.
> Navigation map for AI agents, not a reference manual. Detailed API lives in `README.md`; install and lifecycle in `install.md`.

## Build & test

```bash
vx just dev          # pip install -e ".[dev]"
vx just test         # python -m pytest
vx just lint         # ruff check src tests tools
vx just lint-format  # ruff format --check src tests tools
vx just lint-skills  # python tools/lint_skills.py --warnings-as-errors
vx just preflight    # lint + lint-format + lint-skills + test + check-dist
```

Other recipes: `serve` (`python -m dcc_mcp_openusd`), `build`, `check-dist`, `clean`, `format`.
Run `vx just --list` for the authoritative list — **never invent a recipe name.**

- **Python:** `>=3.9`. Ruff target `py39`, line-length 120.
- **Base install runs in text-fallback mode** — it reads and writes USDA text without the Pixar USD runtime. Install `python -m pip install --only-binary=:all: "dcc-mcp-openusd[openusd]"` for native `pxr` behavior (`usd-core>=24.11,<27`).
- `detect_runtime()` in `src/dcc_mcp_openusd/runtime.py` reports which mode is active (`has_pxr`, `version`). Do not assume `pxr` is importable.
- Post-install checks: `dcc-mcp-openusd doctor --json` and `dcc-mcp-openusd verify --json`.

## Repo layout

| Path | Role |
|---|---|
| `src/dcc_mcp_openusd/` | Adapter package — `server.py`, `runtime.py`, `cli.py`, `doctor.py`, `validation.py`, `__version__.py` |
| `src/dcc_mcp_openusd/skills/` | 7 shipped skills (`openusd-animation`, `-composition`, `-light-camera`, `-material`, `-project`, `-stage`, `-validate`) plus `recipes/` and `SKILLS_INDEX.md`; shipped as wheel artifacts |
| `tests/` | pytest suite (`testpaths = ["tests"]`, `pythonpath = ["src"]`) |
| `tools/lint_skills.py` | Skill contract linter; runs as part of `preflight` |
| `docs/assets/` | Logo and images |
| `install.md` | Wheel-first install and lifecycle guide |

## Release

- release-please drives versioning from Conventional Commits on `main`.
- Whether a release is cut at all is a changelog question, not a prefix question: if every
  commit in the batch lands in a `hidden: true` section the changelog entry is empty, and
  release-please skips the whole batch — no release pull request, **no version bump**
  (`strategies/base.ts` logs “No user facing commits found since … - skipping” when
  `changelogEmpty()` finds only the heading line).
- For `release-type: python`: `chore:`/`ci:`/`style:`/`refactor:`/`test:`/`build:` are
  `hidden: true`; `docs:` is a **visible** `Documentation` section.
- Only once a release *is* cut does the prefix choose the bump: breaking → major,
  `feat:` → minor, anything else → patch
  (`DefaultVersioningStrategy.determineReleaseType()`).
- Use `chore:` when the batch should **not** cut a release; use `docs:` when doc-only work
  should cut a patch release.
- Version is bumped in `pyproject.toml` (`$.project.version`) and `src/dcc_mcp_openusd/__version__.py`.

## Do / Don't

- **Do** single-source agent instructions here. This is the only agent contract file at the repo root.
- **Do** prefer typed skills and tools over raw scripts, and drive the host through `dcc-mcp-cli` (`search` / `describe` / `call` / `load-skill`) rather than adapter-local Python.
- **Don't** add `CLAUDE.md` / `GEMINI.md` / `CURSOR.md` / `ANTHROPIC.md` / `OPENAI.md` / `COPILOT.md` / `CODEBUDDY.md` / `.cursorrules` / `.clinerules` / `.windsurfrules` at the root. This repo has no `docs/integrations/`; keep any vendor-specific notes here.
- **Don't** hardcode an exact version in tests (`assert __version__ == "X.Y.Z"`) — release-please bumps will break it. Use `>=` or read package metadata.
- **Don't** commit build artifacts to the repo root (`dist/`, `build/`, `*.egg-info`, `coverage.json`).
