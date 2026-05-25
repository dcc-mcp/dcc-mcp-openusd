# dcc-mcp-openusd justfile

set shell := ["sh", "-cu"]
set windows-shell := ["pwsh.exe", "-NoProfile", "-Command"]

python := "python"

@default:
    just --list

dev:
    {{python}} -m pip install -e ".[dev]"

serve:
    {{python}} -m dcc_mcp_openusd --port 8765

test:
    {{python}} -m pytest

lint:
    ruff check src tests tools

format:
    ruff format src tests tools

lint-format:
    ruff format --check src tests tools

lint-skills:
    {{python}} tools/lint_skills.py --warnings-as-errors

build:
    {{python}} -m build

check-dist: build
    {{python}} -m twine check dist/*

clean:
    {{python}} -c "import shutil; [shutil.rmtree(p, ignore_errors=True) for p in ['dist', 'build', 'src/dcc_mcp_openusd.egg-info']]"

preflight: lint lint-format lint-skills test check-dist
    @echo "preflight passed"
