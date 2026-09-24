"""Shared fixtures and stage builders for the openusd fix-skill tests.

The partial-pxr finder lives here rather than in one test module so both fix
skill suites can use it without importing private helpers across modules.
"""

from __future__ import annotations

import importlib.abc
import importlib.util
import sys
from pathlib import Path

import pytest

from dcc_mcp_openusd.runtime import RuntimeInfo, detect_runtime

#: A .usdc-style binary layer. The collector keys off this magic, so the file
#: needs no real payload to exercise the "cannot be inspected" path.
BINARY_MAGIC = b"PXR-USDC"


def binary_stage(tmp_path, name="scene.usdc") -> Path:
    """A binary USD layer that only a working pxr could read."""
    target = tmp_path / name
    target.write_bytes(BINARY_MAGIC + bytes(64))
    return target


def headerless_stage(tmp_path, name="scene.usda") -> Path:
    """A text file that is not a USD layer at all."""
    target = tmp_path / name
    target.write_text('def Xform "World"\n{\n}\n', encoding="utf-8")
    return target


class _PartialPxrFinder(importlib.abc.MetaPathFinder):
    """Serve ``pxr`` and ``pxr.Usd``, but make ``pxr.Sdf`` fail to import."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname == "pxr":
            return importlib.util.spec_from_loader("pxr", _EmptyPackageLoader(), is_package=True)
        if fullname == "pxr.Usd":
            return importlib.util.spec_from_loader("pxr.Usd", _UsdLoader())
        if fullname == "pxr.Sdf":
            raise ImportError("No module named 'pxr.Sdf'")
        return None


class _EmptyPackageLoader(importlib.abc.Loader):
    def create_module(self, spec):
        return None

    def exec_module(self, module):
        module.__path__ = []


class _UsdLoader(importlib.abc.Loader):
    def create_module(self, spec):
        return None

    def exec_module(self, module):
        module.GetVersion = lambda: (0, 26, 5)


def _drop_pxr_modules():
    sys.modules.pop("pxr", None)
    for name in [name for name in sys.modules if name.startswith("pxr.")]:
        del sys.modules[name]


@pytest.fixture
def partial_pxr(monkeypatch):
    """Force detect_runtime() to report pxr while pxr.Sdf stays unimportable.

    ``detect_runtime()`` only imports ``pxr.Usd``, but the pxr collector also
    needs ``pxr.Sdf``. A partial or broken usd-core install therefore reports
    ``has_pxr=True`` while the collector raises ImportError and never fills the
    facts -- which must not be read as a stage with nothing wrong with it.
    """
    finder = _PartialPxrFinder()
    _drop_pxr_modules()
    monkeypatch.setattr("dcc_mcp_openusd.runtime._RUNTIME_INFO", None)
    sys.meta_path.insert(0, finder)
    try:
        assert detect_runtime().has_pxr is True, "the fixture must report pxr as available"
        monkeypatch.setattr("dcc_mcp_openusd.runtime._RUNTIME_INFO", RuntimeInfo(has_pxr=True))
        yield
    finally:
        sys.meta_path.remove(finder)
        _drop_pxr_modules()
        monkeypatch.setattr("dcc_mcp_openusd.runtime._RUNTIME_INFO", None)
