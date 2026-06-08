# Changelog

## [0.3.0](https://github.com/dcc-mcp/dcc-mcp-openusd/compare/v0.2.2...v0.3.0) (2026-06-08)


### Features

* add 4 new domain skills — material, light-camera, animation, composition ([7f46052](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/7f46052313ce0c417b92d2b664770748920d45de))

## [0.2.2](https://github.com/dcc-mcp/dcc-mcp-openusd/compare/v0.2.1...v0.2.2) (2026-06-08)


### Bug Fixes

* **ci:** add __version__.py to Release PR allowed files list ([35f3924](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/35f39244659a19bd9d2b0bb97790b99d5ad3eb4e))
* **ci:** apply ruff format to test_agent_instruction_files.py ([f230f36](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/f230f36cc87e2d416edb617305406ece1491f6e2))
* **ci:** fix ruff import organization in test_agent_instruction_files.py ([d024da1](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/d024da12c58443a43ef4e85a1a5a74461a2b2771))

## [0.2.1](https://github.com/dcc-mcp/dcc-mcp-openusd/compare/v0.2.0...v0.2.1) (2026-06-07)


### Bug Fixes

* **ci:** isolate workflow_dispatch from push concurrency in release workflow ([#11](https://github.com/dcc-mcp/dcc-mcp-openusd/issues/11)) ([aceb95f](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/aceb95f4ed6a86bee884d7d0e51df864c50624f9))
* **ci:** remove github.token fallback from release-please token ([411e3c6](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/411e3c6486c4812b0375a108e35c8c5b2d1d67c8))
* **ci:** remove github.token fallback from release-please token ([fdf9c20](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/fdf9c2002a5ab1d09e4052f0e77855ee069cd6bb))
* **ci:** remove github.token fallback from release-please token ([#14](https://github.com/dcc-mcp/dcc-mcp-openusd/issues/14)) ([411e3c6](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/411e3c6486c4812b0375a108e35c8c5b2d1d67c8))
* **docs:** sync README compatibility floor to dcc-mcp-core&gt;=0.18.7 ([d095135](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/d0951357e3c374b0a4ab6a9c92d312ff9009fe10))
* **release:** restore GITHUB_TOKEN fallback for release-please-action ([364c502](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/364c502fbf8894b23d60acd3c766069457f22853))
* runtime boundary governance — pxr guard, hierarchy, base tools ([#10](https://github.com/dcc-mcp/dcc-mcp-openusd/issues/10)) ([01bc970](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/01bc970da745ea6b36434a54ae1055b73e85b92f))

## [0.2.0](https://github.com/dcc-mcp/dcc-mcp-openusd/compare/v0.1.1...v0.2.0) (2026-06-06)


### Features

* daemon runtime + uvx launch + default OpenUSD dep ([#7](https://github.com/dcc-mcp/dcc-mcp-openusd/issues/7)) ([be9a13a](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/be9a13a6abd78a5ffab4027c18a0349d153f944c))


### Bug Fixes

* port 0 semantics and signal handler immediate shutdown ([e213dca](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/e213dcae2a6705e332eafae661a8896bf5c7dfcd))
* port 0 semantics and signal handler stop_server call ([d2e51dd](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/d2e51ddb3ded374a84a80ab2d22df587d47140fd))

## [0.1.1](https://github.com/dcc-mcp/dcc-mcp-openusd/compare/v0.1.0...v0.1.1) (2026-06-05)


### Bug Fixes

* **deps:** document core 0.18.2 floor ([187d49a](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/187d49a184c3a269c9bae264c8e32694bcbd48c8))

## 0.1.0 (2026-05-25)


### Features

* bootstrap OpenUSD MCP adapter ([03d4931](https://github.com/loonghao/dcc-mcp-openusd/commit/03d4931c2be9325579defd5be9de173babc8a934))

## 0.0.0

Initial development baseline. `release-please` owns public release versions.
