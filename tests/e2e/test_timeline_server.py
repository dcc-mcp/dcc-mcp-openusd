"""Real HTTP/native regression: initialize OTIO before gateway callbacks."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap

import pytest

pytest.importorskip("pxr")
otio = pytest.importorskip("opentimelineio")


def test_otio_export_then_parity_survives_repeated_http_callbacks(tmp_path):
    """A subprocess turns a native abort into a bounded test failure."""
    from dcc_mcp_openusd.runtime import create_stage
    from dcc_mcp_openusd.timeline import import_timeline

    stage = tmp_path / "timeline.usda"
    reference = tmp_path / "input.otio"
    create_stage(str(stage))
    timeline = otio.schema.Timeline(name="native callback test")
    track = otio.schema.Track(name="V1", kind=otio.schema.TrackKind.Video)
    timeline.tracks.append(track)
    track.append(
        otio.schema.Clip(
            name="A",
            source_range=otio.opentime.TimeRange(otio.opentime.RationalTime(0, 24), otio.opentime.RationalTime(12, 24)),
        )
    )
    otio.adapters.write_to_file(timeline, str(reference))
    import_timeline(str(stage), otio_file=str(reference), start_time_code=1001)
    code = textwrap.dedent("""
        import json, pathlib, socket, sys, urllib.request
        from dcc_mcp_openusd.server import OpenUsdMcpServer
        root = pathlib.Path(sys.argv[1])
        # Do not import opentimelineio in this subprocess before server start.
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            gateway_port = listener.getsockname()[1]
        server = OpenUsdMcpServer(port=0, gateway_port=gateway_port,
            registry_dir=str(root / 'registry'), enable_gateway_failover=False,
            enable_file_logging=False, enable_job_persistence=False,
            enable_telemetry=False)
        server.register_builtin_actions()
        server.start()
        def call(name, arguments):
            if name == 'load_skill':
                path = '/v1/load_skill'
                body = dict(arguments, dcc_type='openusd', instance_id=server.instance_id)
            else:
                path = '/v1/call'
                body = {'tool_slug': 'openusd.' + server.instance_id[:8] + '.' + name,
                        'arguments': arguments}
            request = urllib.request.Request('http://127.0.0.1:' + str(gateway_port) + path,
                data=json.dumps(body).encode(), headers={'Content-Type': 'application/json', 'Accept': 'application/json'})
            with urllib.request.urlopen(request, timeout=15) as response:
                result = json.load(response)
            assert 'error' not in result, result
            return result.get('output', result)
        try:
            assert call('load_skill', {'skill_name': 'openusd-timeline'})['loaded']
            for index in range(3):
                assert call('openusd_timeline__export_timeline',
                    {'stage_file': str(root / 'timeline.usda'), 'output_file': str(root / 'export.otio')})['success']
                parity = call('openusd_timeline__verify_timeline_parity',
                    {'stage_file': str(root / 'timeline.usda'),
                     'otio_file': str(root / 'input.otio'), 'start_time_code': 1001})
                assert parity['success'] and parity['context']['parity'], parity
                print('roundtrip', index, flush=True)
        finally:
            server.stop()
    """)
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(sys.path), DCC_MCP_DISABLE_UPDATE_CHECK="1", RUST_LOG="warn")
    for variable, directory in [
        ("HOME", "home"),
        ("XDG_DATA_HOME", "data"),
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_CACHE_HOME", "cache"),
    ]:
        env[variable] = str(tmp_path / directory)
    result = subprocess.run(
        [sys.executable, "-X", "faulthandler", "-c", code, str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )
    assert result.returncode == 0, json.dumps(
        {"returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    )
    assert result.stdout.count("roundtrip") == 3
