from __future__ import annotations

from dcc_mcp_openusd.server import OpenUsdMcpServer


def test_optional_otio_is_detected_before_http_start(monkeypatch):
    from dcc_mcp_core.server_base import DccServerBase

    from dcc_mcp_openusd import timeline

    order = []
    monkeypatch.setattr(timeline, "detect_otio", lambda: order.append("optional runtime"))
    monkeypatch.setattr(DccServerBase, "start", lambda self, **kwargs: order.append("http start"))
    server = object.__new__(OpenUsdMcpServer)
    assert server.start() is server
    assert order == ["optional runtime", "http start"]
