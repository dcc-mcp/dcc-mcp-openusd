# Changelog

## [0.6.0](https://github.com/dcc-mcp/dcc-mcp-openusd/compare/v0.5.0...v0.6.0) (2026-06-23)


### Features

* add 4 new domain skills — material, light-camera, animation, composition ([2b6e766](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/2b6e766d45a8f54c1c3da6d908b2d4feaa771d00))
* add e2e golden-path tests, CI matrix, and pxr runtime documentation ([4dd9f6d](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/4dd9f6d96179dc43db6119a383d49c8899b94c91))
* add e2e golden-path tests, CI matrix, and pxr runtime documentation ([6b62887](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/6b62887f82a06809683a88a8f122a08c7fd09dd5))
* bootstrap OpenUSD MCP adapter ([03d4931](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/03d4931c2be9325579defd5be9de173babc8a934))
* daemon runtime + uvx launch + default OpenUSD dep ([#7](https://github.com/dcc-mcp/dcc-mcp-openusd/issues/7)) ([b97cc82](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/b97cc82f6276600e4fddbe7e9796d1e7fff3ba9f))
* implement asset_source() and import_to_scene() for asset_import contract ([7bb80a7](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/7bb80a761e2547fe1bda866f0f38bfc3af6f8c78))
* implement asset_source() and import_to_scene() for asset_import contract (PIP-1925) ([63c5540](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/63c554014820d19ddf3a004c472db5876025a81a))


### Bug Fixes

* **ci:** add __version__.py to Release PR allowed files list ([f89e36b](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/f89e36ba40ed99d2a5a6154d623dbed7a1ff4d8a))
* **ci:** apply ruff format to test_agent_instruction_files.py ([ec12a4a](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/ec12a4a2fbcaff601c0998cc3be81006568909a5))
* **ci:** fix ruff import organization in test_agent_instruction_files.py ([f294fb3](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/f294fb3626c69a0670f2c1c2f41a54a0d38e64dd))
* **ci:** isolate workflow_dispatch from push concurrency in release workflow ([#11](https://github.com/dcc-mcp/dcc-mcp-openusd/issues/11)) ([417b500](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/417b500ded581a6535a08d41069415726960c9e8))
* **ci:** remove github.token fallback from release-please token ([0eae227](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/0eae227218284c1ac06ca7a0bf7d9322f0460bd6))
* **ci:** remove github.token fallback from release-please token ([fea7224](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/fea722420d62438b6a037668d9dc97d84b3cab38))
* **ci:** remove github.token fallback from release-please token ([#14](https://github.com/dcc-mcp/dcc-mcp-openusd/issues/14)) ([0eae227](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/0eae227218284c1ac06ca7a0bf7d9322f0460bd6))
* **deps:** document core 0.18.2 floor ([63cd81c](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/63cd81cb9c6bcdd32dcc33d9c5dab317565e0496))
* **docs:** sync README compatibility floor to dcc-mcp-core&gt;=0.18.7 ([60cb842](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/60cb8425c8fc4f30fcc6f5b708478783bdaabb2b))
* move pxr imports after _require_pxr gate in pxr-required functions ([b8beff8](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/b8beff80cfb6e5cc01c27d005e027bc3165e3551))
* move pxr imports after _require_pxr gate in pxr-required functions ([c03f6d5](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/c03f6d5fbc1f568fcaa265f930222093694e3f2f))
* port 0 semantics and signal handler immediate shutdown ([c2e3601](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/c2e36010f281e3bf54efc6e53139b90c3fe5c65d))
* port 0 semantics and signal handler stop_server call ([e7d4096](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/e7d40960e1601e9f1946cc2f42afc5b84329e08f))
* **release:** restore GITHUB_TOKEN fallback for release-please-action ([e8e3ed9](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/e8e3ed90d735da3013c6b57b8fc4d7fe88651c48))
* resolve CI failures in asset_import text-fallback path ([db0ace5](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/db0ace595adf244896c0bc27c51f99f12a7c99fd))
* resolve merge conflict in pyproject.toml, bump dcc-mcp-core to &gt;=0.18.34 ([d62d48b](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/d62d48b16d5ac62749a3ec08ffa37a20b86359f6))
* runtime boundary governance — pxr guard, hierarchy, base tools ([#10](https://github.com/dcc-mcp/dcc-mcp-openusd/issues/10)) ([5b9b263](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/5b9b26386846c8d86d25dee3f6fcde2877174f93))
* set standalone_main_thread=True for OpenUSD headless server ([7c3119c](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/7c3119c57823823019249a176e797b0a8a7a674a))


### Documentation

* sync README and skill index with all 7 bundled skills, fix version pin ([#29](https://github.com/dcc-mcp/dcc-mcp-openusd/issues/29)) ([37dcf86](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/37dcf8638035d787280e1ad6c15a5b3c18e06096))

## [0.5.0](https://github.com/dcc-mcp/dcc-mcp-openusd/compare/v0.4.1...v0.5.0) (2026-06-21)


### Features

* implement asset_source() and import_to_scene() for asset_import contract ([a86ee16](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/a86ee16ede7cfca8afe14a2d8eeffa24fdcdc946))
* implement asset_source() and import_to_scene() for asset_import contract (PIP-1925) ([ab21645](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/ab21645c967fbc397b9ed970fa67de7a501dd2cb))


### Bug Fixes

* resolve CI failures in asset_import text-fallback path ([0e4492c](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/0e4492c13964a2a06b9887e1ecbe479f530911cc))
* resolve merge conflict in pyproject.toml, bump dcc-mcp-core to &gt;=0.18.34 ([a838ac0](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/a838ac03702d1cdc5bb0446add0e14df4c6038cd))


### Documentation

* sync README and skill index with all 7 bundled skills, fix version pin ([#29](https://github.com/dcc-mcp/dcc-mcp-openusd/issues/29)) ([85e662b](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/85e662b2c0ff5dbeadd1849a7c9edd50fdf80cc0))

## [0.4.1](https://github.com/dcc-mcp/dcc-mcp-openusd/compare/v0.4.0...v0.4.1) (2026-06-08)


### Bug Fixes

* set standalone_main_thread=True for OpenUSD headless server ([4d12257](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/4d12257fcab2395dadade8e2768617a966a558cb))

## [0.4.0](https://github.com/dcc-mcp/dcc-mcp-openusd/compare/v0.3.0...v0.4.0) (2026-06-08)


### Features

* add e2e golden-path tests, CI matrix, and pxr runtime documentation ([c5f7955](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/c5f795588349de0093370cd5df2d08a5b8255793))


### Bug Fixes

* move pxr imports after _require_pxr gate in pxr-required functions ([83e8ad5](https://github.com/dcc-mcp/dcc-mcp-openusd/commit/83e8ad59b9d9a51aa3d1f6c05022e9beaf03ad15))

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
