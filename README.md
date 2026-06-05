# dcc-mcp-openusd

OpenUSD adapter and skills for the DCC Model Context Protocol ecosystem.

`dcc-mcp-openusd` runs a headless OpenUSD-oriented MCP server that can create
portable USD project folders, author simple stages, add references, validate
stages, and package USDZ-like archives. It is designed to plug into the
`dcc-mcp-core` gateway and skills-first workflow.

## Install

```bash
pip install dcc-mcp-openusd
```

This release train requires `dcc-mcp-core>=0.18.2`.

For full OpenUSD runtime behavior, install the optional Pixar USD bindings:

```bash
pip install "dcc-mcp-openusd[openusd]"
```

## Run

```bash
dcc-mcp-openusd --port 8765
```

Then connect an MCP client to:

```text
http://127.0.0.1:8765/mcp
```

## Bundled Skills

The first version ships three bundled skills:

| Skill | Purpose |
| --- | --- |
| `openusd-project` | Create self-contained project folders and snapshots. |
| `openusd-stage` | Create stages, list prims, define xforms, and add references. |
| `openusd-validate` | Validate stage invariants and package a USDZ-style archive. |

Agents should follow the normal DCC-MCP flow:

1. `search_skills(query="openusd stage")`
2. `load_skill("openusd-stage")`
3. Call a typed tool such as `openusd_stage__create_stage`
4. Validate with `openusd_validate__validate_stage`

## Scope

This repository is intentionally an adapter/domain-skill package, not a new
core USD engine. `dcc-mcp-core` remains the shared transport, gateway,
validation, telemetry, and skill-loading foundation. This package owns
OpenUSD-specific project semantics, stage authoring tools, validation policy,
and packaging workflows.

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check src tests tools
python -m build
```

## Release

The repository uses `release-please`. The baseline version is `0.0.0` so the
first release PR will cut `v0.1.0`. PyPI publishing is wired through the
`pypi` GitHub environment.
