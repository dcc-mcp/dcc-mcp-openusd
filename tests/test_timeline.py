"""OTIO <-> USD timeline interop tests.

The round-trip tests need both ``pxr`` and ``opentimelineio`` and are skipped
when either is missing, mirroring the animation suite. The dependency-guard
tests run everywhere: a missing optional runtime must fail loudly instead of
returning an empty timeline.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

import dcc_mcp_openusd.runtime as runtime_module
import dcc_mcp_openusd.timeline as timeline_module
from dcc_mcp_openusd.runtime import (
    OpenUsdError,
    RuntimeInfo,
    author_xform_samples,
    create_stage,
    define_xform,
    detect_runtime,
    list_stage,
    set_time_codes,
)
from dcc_mcp_openusd.timeline import (
    OtioRuntimeInfo,
    detect_otio,
    export_timeline,
    import_timeline,
    load_otio_timeline,
    require_otio,
    timeline_summary,
    verify_timeline_parity,
)

_HAS_PXR = detect_runtime().has_pxr
_HAS_OTIO = detect_otio().has_otio

needs_otio = pytest.mark.skipif(not _HAS_OTIO, reason="opentimelineio is not installed")
needs_pxr_and_otio = pytest.mark.skipif(not (_HAS_PXR and _HAS_OTIO), reason="pxr and opentimelineio are both required")


def _otio():
    """Return the opentimelineio module, skipping the test when absent."""
    return pytest.importorskip("opentimelineio")


def _build_reference_timeline():
    """Three clips on one video track: 84 frames at 24 fps (issue scenario)."""
    otio = _otio()
    from opentimelineio.opentime import RationalTime, TimeRange

    timeline = otio.schema.Timeline(name="shot_001", global_start_time=RationalTime(0, 24))
    track = otio.schema.Track(name="V1", kind=otio.schema.TrackKind.Video)
    timeline.tracks.append(track)
    for name, duration, source_start in (("plate_a", 24, 0), ("plate_b", 36, 12), ("plate_c", 24, 100)):
        track.append(
            otio.schema.Clip(
                name=name,
                source_range=TimeRange(RationalTime(source_start, 24), RationalTime(duration, 24)),
                media_reference=otio.schema.ExternalReference(target_url=f"/media/{name}.mov"),
            )
        )
    return timeline


def _build_multi_track_timeline():
    """Two tracks with a gap between clips so the total duration needs it."""
    otio = _otio()
    from opentimelineio.opentime import RationalTime, TimeRange

    timeline = otio.schema.Timeline(name="multi", global_start_time=RationalTime(0, 24))
    video = otio.schema.Track(name="V1", kind=otio.schema.TrackKind.Video)
    audio = otio.schema.Track(name="A1", kind=otio.schema.TrackKind.Audio)
    timeline.tracks.append(video)
    timeline.tracks.append(audio)
    video.append(
        otio.schema.Clip(
            name="shot_010",
            source_range=TimeRange(RationalTime(10, 24), RationalTime(20, 24)),
            media_reference=otio.schema.ExternalReference(target_url="/media/010.mov"),
        )
    )
    video.append(otio.schema.Gap(source_range=TimeRange(RationalTime(0, 24), RationalTime(4, 24))))
    video.append(
        otio.schema.Clip(
            name="shot_020",
            source_range=TimeRange(RationalTime(0, 24), RationalTime(30, 24)),
            media_reference=otio.schema.ExternalReference(target_url="/media/020.mov"),
        )
    )
    audio.append(otio.schema.Clip(name="ambience", source_range=TimeRange(RationalTime(0, 24), RationalTime(54, 24))))
    return timeline


def _write_otio(timeline, path: Path) -> Path:
    _otio().adapters.write_to_file(timeline, str(path))
    return path


# --- optional dependency guards --------------------------------------------


def test_detect_otio_reports_availability_without_importing_eagerly():
    info = detect_otio()
    assert isinstance(info.has_otio, bool)
    assert info.has_otio is _HAS_OTIO


def test_require_otio_names_the_timeline_extra(monkeypatch):
    monkeypatch.setattr(timeline_module, "_OTIO_RUNTIME_INFO", OtioRuntimeInfo(has_otio=False))

    with pytest.raises(OpenUsdError) as caught:
        require_otio("Importing an OTIO timeline")

    message = str(caught.value)
    assert "Importing an OTIO timeline" in message
    assert "opentimelineio" in message.lower()
    assert "dcc-mcp-openusd[timeline]" in message


@needs_otio
def test_timeline_tools_fail_loudly_when_otio_is_missing(monkeypatch, tmp_path):
    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file))
    monkeypatch.setattr(timeline_module, "_OTIO_RUNTIME_INFO", OtioRuntimeInfo(has_otio=False))

    with pytest.raises(OpenUsdError, match="dcc-mcp-openusd"):
        import_timeline(str(stage_file), otio_json="{}")
    with pytest.raises(OpenUsdError, match="dcc-mcp-openusd"):
        export_timeline(str(stage_file))
    with pytest.raises(OpenUsdError, match="dcc-mcp-openusd"):
        verify_timeline_parity(str(stage_file))


def test_timeline_tools_fail_cleanly_without_pxr(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime_module, "_RUNTIME_INFO", RuntimeInfo(has_pxr=False))
    if not _HAS_OTIO:
        pytest.skip("opentimelineio is not installed")

    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file))
    otio_json = _build_reference_timeline().to_json_string()

    with pytest.raises(OpenUsdError, match="pxr"):
        import_timeline(str(stage_file), otio_json=otio_json)
    with pytest.raises(OpenUsdError, match="pxr"):
        export_timeline(str(stage_file))
    with pytest.raises(OpenUsdError, match="pxr"):
        verify_timeline_parity(str(stage_file))


# --- OTIO reading -----------------------------------------------------------


@needs_otio
def test_load_otio_timeline_rejects_unusable_input(tmp_path):
    with pytest.raises(OpenUsdError, match="exactly one"):
        load_otio_timeline()
    with pytest.raises(OpenUsdError, match="exactly one"):
        load_otio_timeline(otio_file=str(tmp_path / "a.otio"), otio_json="{}")
    with pytest.raises(OpenUsdError, match="does not exist"):
        load_otio_timeline(otio_file=str(tmp_path / "missing.otio"))
    with pytest.raises(OpenUsdError, match="Could not parse"):
        load_otio_timeline(otio_json="{not otio")


@needs_otio
def test_timeline_summary_digests_tracks_clips_and_frames():
    summary = timeline_summary(_build_reference_timeline())

    assert summary["track_count"] == 1
    assert summary["clip_count"] == 3
    assert summary["duration_frames"] == 84.0
    assert summary["global_start_time"] == 0.0
    assert summary["start_time_code"] == 1.0
    assert summary["end_time_code"] == 84.0
    assert [clip["name"] for clip in summary["clips"]] == ["plate_a", "plate_b", "plate_c"]
    assert [clip["source_start"] for clip in summary["clips"]] == [0.0, 12.0, 100.0]
    assert [clip["source_duration"] for clip in summary["clips"]] == [24.0, 36.0, 24.0]


@needs_otio
def test_load_otio_timeline_reads_inline_json_and_files(tmp_path):
    reference = _build_reference_timeline()
    otio_file = _write_otio(reference, tmp_path / "shot.otio")

    from_file = timeline_summary(load_otio_timeline(otio_file=str(otio_file)))
    from_json = timeline_summary(load_otio_timeline(otio_json=reference.to_json_string()))

    assert from_file == from_json


# --- round trip -------------------------------------------------------------


@needs_pxr_and_otio
def test_import_sets_time_codes_from_the_otio_timeline(tmp_path):
    otio_file = _write_otio(_build_reference_timeline(), tmp_path / "shot.otio")
    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file), name="shot_001")

    result = import_timeline(str(stage_file), otio_file=str(otio_file))

    assert result["runtime"] == "pxr"
    assert result["frames_per_second"] == 24.0
    assert result["duration_frames"] == 84.0
    assert result["start_time_code"] == 1.0
    assert result["end_time_code"] == 84.0
    assert result["timeline_prim_path"] == "/World/Timeline"

    # Read the time codes back out of the stage instead of trusting the result.
    from pxr import Usd  # type: ignore

    stage = Usd.Stage.Open(str(stage_file))
    assert stage.GetStartTimeCode() == 1.0
    assert stage.GetEndTimeCode() == 84.0
    assert stage.GetTimeCodesPerSecond() == 24.0


@needs_pxr_and_otio
def test_round_trip_conserves_clip_count_track_count_and_frames(tmp_path):
    otio = _otio()
    reference = _build_reference_timeline()
    otio_file = _write_otio(reference, tmp_path / "shot.otio")
    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file), name="shot_001")

    import_timeline(str(stage_file), otio_file=str(otio_file))
    exported_file = tmp_path / "round_trip.otio"
    export_timeline(str(stage_file), output_file=str(exported_file))

    assert exported_file.is_file()
    assert exported_file.stat().st_size > 0

    reread = otio.adapters.read_from_file(str(exported_file))
    before = timeline_summary(reference)
    after = timeline_summary(reread)

    assert after["track_count"] == before["track_count"] == 1
    assert after["clip_count"] == before["clip_count"] == 3
    assert after["duration_frames"] == before["duration_frames"] == 84.0
    assert after["clips"] == before["clips"]


@needs_pxr_and_otio
def test_verify_timeline_parity_matches_field_by_field(tmp_path):
    otio_file = _write_otio(_build_reference_timeline(), tmp_path / "shot.otio")
    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file), name="shot_001")

    report = verify_timeline_parity(str(stage_file), otio_file=str(otio_file))

    assert report["parity"] is True
    assert report["verified"] is True
    assert report["differences"] == []
    assert report["source"] == "reference_timeline"
    assert report["expected"]["clip_count"] == report["actual"]["clip_count"] == 3
    assert report["expected"]["duration_frames"] == report["actual"]["duration_frames"] == 84.0
    assert report["expected"]["start_time_code"] == report["actual"]["start_time_code"] == 1.0
    assert report["expected"]["end_time_code"] == report["actual"]["end_time_code"] == 84.0
    assert report["expected"]["clips"] == report["actual"]["clips"]


@needs_pxr_and_otio
def test_verify_timeline_parity_accepts_inline_otio_json_and_is_idempotent(tmp_path):
    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file), name="shot_001")
    otio_json = _build_reference_timeline().to_json_string()

    first = verify_timeline_parity(str(stage_file), otio_json=otio_json)
    second = verify_timeline_parity(str(stage_file), otio_json=otio_json)

    assert first["parity"] is True
    assert second["parity"] is True
    assert second["actual"]["clips"] == first["actual"]["clips"]


@needs_pxr_and_otio
def test_multi_track_round_trip_conserves_gaps_and_track_kinds(tmp_path):
    reference = _build_multi_track_timeline()
    otio_file = _write_otio(reference, tmp_path / "multi.otio")
    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file), name="multi")

    imported = import_timeline(str(stage_file), otio_file=str(otio_file))

    assert imported["track_count"] == 2
    assert imported["clip_count"] == 3
    # 20 + 4 (gap) + 30 = 54 frames, and the audio track is the same length.
    assert imported["duration_frames"] == 54.0

    report = verify_timeline_parity(str(stage_file), otio_file=str(otio_file))

    assert report["parity"] is True
    assert report["differences"] == []
    exported = export_timeline(str(stage_file))
    assert [track["kind"] for track in exported["tracks"]] == ["Video", "Audio"]
    assert [clip["name"] for clip in exported["clips"]] == ["shot_010", "shot_020", "ambience"]
    assert [clip["start"] for clip in exported["clips"]] == [0.0, 24.0, 0.0]


@needs_pxr_and_otio
def test_verify_timeline_parity_flags_drifted_stage_time_codes(tmp_path):
    otio_file = _write_otio(_build_reference_timeline(), tmp_path / "shot.otio")
    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file), name="shot_001")
    import_timeline(str(stage_file), otio_file=str(otio_file))

    # Another tool moves the shot range without touching the authored edit.
    set_time_codes(str(stage_file), start_time_code=1.0, end_time_code=200.0, frames_per_second=24.0)

    report = verify_timeline_parity(str(stage_file))

    assert report["parity"] is False
    assert "end_time_code" in {item["field"] for item in report["differences"]}


@needs_pxr_and_otio
def test_export_synthesizes_a_track_when_no_timeline_is_authored(tmp_path):
    otio = _otio()
    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file), name="plain_stage")
    set_time_codes(str(stage_file), start_time_code=1001.0, end_time_code=1100.0, frames_per_second=25.0)

    exported = export_timeline(str(stage_file), output_file=str(tmp_path / "plain.otio"))

    assert exported["authored_source"] == "stage_time_codes"
    assert exported["clip_count"] == 1
    assert exported["duration_frames"] == 100.0

    reread = otio.adapters.read_from_file(str(tmp_path / "plain.otio"))
    assert reread.duration() == otio.opentime.RationalTime(100, 25)


@needs_pxr_and_otio
def test_export_falls_back_to_time_samples_when_the_stage_range_is_inverted(tmp_path):
    from pxr import Usd  # type: ignore

    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file), name="sampled")
    define_xform(str(stage_file), "/World/Asset")
    author_xform_samples(
        str(stage_file),
        "/World/Asset",
        [
            {"time": 4.0, "translate": [0, 0, 0]},
            {"time": 12.0, "translate": [1, 0, 0]},
            {"time": 40.0, "translate": [2, 0, 0]},
        ],
    )

    # An inverted range carries no duration, so the samples have to define it.
    stage = Usd.Stage.Open(str(stage_file))
    stage.SetStartTimeCode(10.0)
    stage.SetEndTimeCode(5.0)
    stage.GetRootLayer().Save()

    exported = export_timeline(str(stage_file))

    assert exported["time_samples"]["animated_attribute_count"] >= 1
    assert exported["start_time_code"] == 4.0
    assert exported["end_time_code"] == 40.0
    assert exported["duration_frames"] == 37.0


@needs_pxr_and_otio
def test_authored_timeline_reads_back_identically_in_text_fallback(tmp_path, monkeypatch):
    otio_file = _write_otio(_build_reference_timeline(), tmp_path / "shot.otio")
    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file), name="shot_001")
    import_timeline(str(stage_file), otio_file=str(otio_file))

    from_pxr = [prim["path"] for prim in list_stage(str(stage_file))["prims"]]

    monkeypatch.setattr(runtime_module, "_RUNTIME_INFO", RuntimeInfo(has_pxr=False))
    from_text = [prim["path"] for prim in list_stage(str(stage_file))["prims"]]

    assert from_text == from_pxr
    assert "/World/Timeline/V1/plate_b" in from_text


@needs_pxr_and_otio
def test_import_rejects_unusable_arguments(tmp_path):
    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file))
    otio_json = _build_reference_timeline().to_json_string()

    with pytest.raises(OpenUsdError, match="does not exist"):
        import_timeline(str(tmp_path / "missing.usda"), otio_json=otio_json)
    with pytest.raises(OpenUsdError, match="absolute prim path"):
        import_timeline(str(stage_file), otio_json=otio_json, timeline_prim_path="Timeline")
    with pytest.raises(OpenUsdError, match="greater than 0"):
        import_timeline(str(stage_file), otio_json=otio_json, frames_per_second=0)


# --- skill entry points -----------------------------------------------------


def _load_skill_script(name: str):
    path = (
        Path(__file__).parents[1] / "src" / "dcc_mcp_openusd" / "skills" / "openusd-timeline" / "scripts" / f"{name}.py"
    )
    spec = importlib.util.spec_from_file_location(f"openusd_timeline_{name}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@needs_pxr_and_otio
def test_skill_scripts_wire_the_timeline_helpers(tmp_path):
    import_tool = _load_skill_script("import_timeline")
    export_tool = _load_skill_script("export_timeline")
    verify_tool = _load_skill_script("verify_timeline_parity")

    otio_file = _write_otio(_build_reference_timeline(), tmp_path / "shot.otio")
    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file), name="shot_001")

    imported = import_tool.main(stage_file=str(stage_file), otio_file=str(otio_file))
    assert imported["success"] is True
    assert imported["context"]["clip_count"] == 3

    exported = export_tool.main(stage_file=str(stage_file), output_file=str(tmp_path / "out.otio"))
    assert exported["success"] is True
    assert exported["context"]["duration_frames"] == 84.0

    verified = verify_tool.main(stage_file=str(stage_file), otio_file=str(otio_file))
    assert verified["success"] is True
    assert verified["context"]["parity"] is True

    set_time_codes(str(stage_file), start_time_code=1.0, end_time_code=200.0, frames_per_second=24.0)
    drifted = verify_tool.main(stage_file=str(stage_file))
    assert drifted["success"] is False
    assert drifted["error"] == "timeline_parity_mismatch"
