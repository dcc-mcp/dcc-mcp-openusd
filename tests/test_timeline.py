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


def _build_nested_stack_timeline():
    """A Stack nested inside a Track — valid OTIO the authored subtree drops."""
    otio = _otio()
    from opentimelineio.opentime import RationalTime, TimeRange

    timeline = otio.schema.Timeline(name="nested")
    track = otio.schema.Track(name="V1", kind=otio.schema.TrackKind.Video)
    timeline.tracks.append(track)
    track.append(otio.schema.Clip(name="outer", source_range=TimeRange(RationalTime(0, 24), RationalTime(24, 24))))
    nested = otio.schema.Stack(name="nested")
    nested_track = otio.schema.Track(name="V2", kind=otio.schema.TrackKind.Video)
    nested_track.append(
        otio.schema.Clip(name="inner", source_range=TimeRange(RationalTime(0, 24), RationalTime(24, 24)))
    )
    nested.append(nested_track)
    track.append(nested)
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
@pytest.mark.parametrize(
    ("start", "end", "label"),
    [
        (1001.0, 1100.0, "1001-based stage, no authored timeline"),
        (1001.0, 1084.0, "1001-based stage with an authored timeline"),
        (0.0, 0.0, "stage with no time axis set at all"),
    ],
)
def test_self_check_accepts_any_timecode_base(tmp_path, start, end, label):
    """The self-check must not assert a conversion the caller never asked for.

    Regression: it used to compare the stage time codes against the hard-coded
    0-based to 1-based rule, so every stage that did not start at frame 1 was
    reported as a mismatch.
    """
    otio_file = _write_otio(_build_reference_timeline(), tmp_path / "shot.otio")
    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file), name="shot_001")
    import_timeline(str(stage_file), otio_file=str(otio_file))
    set_time_codes(str(stage_file), start_time_code=start, end_time_code=end, frames_per_second=24.0)

    report = verify_timeline_parity(str(stage_file))

    assert report["source"] == "stage_self_check"
    assert report["parity"] is True, f"{label}: {report['differences']}"
    assert report["differences"] == []


@needs_pxr_and_otio
def test_self_check_reports_only_the_claims_it_can_make(tmp_path):
    """The advertised `checked` list must match what the self-check compares.

    The edit is compared with itself there, so the per-clip and time code
    fields have no discriminating power and must not be advertised.
    """
    otio_file = _write_otio(_build_reference_timeline(), tmp_path / "shot.otio")
    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file), name="shot_001")
    import_timeline(str(stage_file), otio_file=str(otio_file))

    self_check = verify_timeline_parity(str(stage_file))
    with_reference = verify_timeline_parity(str(stage_file), otio_file=str(otio_file))

    assert self_check["checked"] == ["exported_otio_re_readable", "duration_frames"]
    assert "start_time_code" not in self_check["checked"]
    assert "clip_names" not in self_check["checked"]
    assert len(with_reference["checked"]) == 9
    assert "start_time_code" in with_reference["checked"]


@needs_pxr_and_otio
def test_verify_timeline_parity_still_fails_when_the_edit_does_not_round_trip(tmp_path):
    """The verifier must stay falsifiable, not become a rubber stamp.

    A Stack nested inside a Track is valid OTIO whose children the authored
    subtree does not represent, so the clip is dropped on import and the
    exported edit is shorter than the reference.
    """
    otio_file = _write_otio(_build_nested_stack_timeline(), tmp_path / "nested.otio")
    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file), name="nested")

    report = verify_timeline_parity(str(stage_file), otio_file=str(otio_file))

    assert report["parity"] is False
    assert "duration_frames" in {item["field"] for item in report["differences"]}


@needs_pxr_and_otio
def test_nested_stacks_are_imported_instead_of_silently_dropped(tmp_path):
    """Stacks nested more than one level deep must still yield their tracks."""
    otio = _otio()
    from opentimelineio.opentime import RationalTime, TimeRange

    timeline = otio.schema.Timeline(name="deep")
    for outer_name, inner_name in (("A", "A1"), ("B", "B1")):
        outer = otio.schema.Stack(name=outer_name)
        inner = otio.schema.Stack(name=f"{outer_name}_nested")
        track = otio.schema.Track(name=inner_name, kind=otio.schema.TrackKind.Video)
        track.append(
            otio.schema.Clip(
                name=f"{inner_name}_clip",
                source_range=TimeRange(RationalTime(0, 24), RationalTime(24, 24)),
            )
        )
        inner.append(track)
        outer.append(inner)
        timeline.tracks.append(outer)

    otio_file = _write_otio(timeline, tmp_path / "deep.otio")
    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file), name="deep")

    imported = import_timeline(str(stage_file), otio_file=str(otio_file))

    assert imported["track_count"] == 2
    assert imported["clip_count"] == 2


@needs_pxr_and_otio
def test_import_can_anchor_the_shot_on_a_pipeline_timecode_base(tmp_path):
    """A 1001 base must survive the import instead of being overwritten."""
    from pxr import Usd  # type: ignore

    otio_file = _write_otio(_build_reference_timeline(), tmp_path / "shot.otio")
    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file), name="shot_001")

    imported = import_timeline(str(stage_file), otio_file=str(otio_file), start_time_code=1001.0)

    assert imported["start_time_code"] == 1001.0
    # 84 frames keep their duration and only move onto the new base.
    assert imported["end_time_code"] == 1084.0
    assert imported["duration_frames"] == 84.0

    stage = Usd.Stage.Open(str(stage_file))
    assert stage.GetStartTimeCode() == 1001.0
    assert stage.GetEndTimeCode() == 1084.0

    # And the anchored stage verifies cleanly against its own export.
    assert verify_timeline_parity(str(stage_file))["parity"] is True


@needs_pxr_and_otio
def test_verify_with_reference_keeps_the_anchor_it_was_given(tmp_path):
    """A reference run must not rewrite the anchor and then call it a match.

    Regression: verify re-imports the reference and used to do so without the
    caller's `start_time_code`, so a 1001-based shot was silently moved back to
    1..84 — and compared against that very rewrite, which reported green.
    """
    from pxr import Usd  # type: ignore

    reference = _build_reference_timeline()
    otio_file = _write_otio(reference, tmp_path / "shot.otio")
    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file), name="shot_001")
    import_timeline(str(stage_file), otio_file=str(otio_file), start_time_code=1001.0)

    report = verify_timeline_parity(str(stage_file), otio_file=str(otio_file), start_time_code=1001.0)

    assert report["parity"] is True
    assert report["differences"] == []

    # The anchor survives, which is the whole point of the parameter.
    stage = Usd.Stage.Open(str(stage_file))
    assert stage.GetStartTimeCode() == 1001.0
    assert stage.GetEndTimeCode() == 1084.0


@needs_pxr_and_otio
def test_verify_without_the_anchor_still_documents_the_default_conversion(tmp_path):
    """Without `start_time_code` the reference run uses the 1-based default.

    This pins the documented conversion rather than the silent rewrite: the
    caller decides the base, and omitting the argument means frame 1.
    """
    from pxr import Usd  # type: ignore

    otio_file = _write_otio(_build_reference_timeline(), tmp_path / "shot.otio")
    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file), name="shot_001")

    report = verify_timeline_parity(str(stage_file), otio_file=str(otio_file))

    assert report["parity"] is True
    stage = Usd.Stage.Open(str(stage_file))
    assert stage.GetStartTimeCode() == 1.0
    assert stage.GetEndTimeCode() == 84.0


@needs_pxr_and_otio
def test_self_check_echo_matches_what_it_compared(tmp_path):
    """The echo must not show time codes the self-check never compared.

    Reporting `expected 1.0` against `actual 1001.0` next to a green verdict
    reads as a broken comparison, so those fields are omitted instead.
    """
    otio_file = _write_otio(_build_reference_timeline(), tmp_path / "shot.otio")
    stage_file = tmp_path / "scene.usda"
    create_stage(str(stage_file), name="shot_001")
    import_timeline(str(stage_file), otio_file=str(otio_file), start_time_code=1001.0)

    self_check = verify_timeline_parity(str(stage_file))
    anchored = verify_timeline_parity(str(stage_file), otio_file=str(otio_file), start_time_code=1001.0)
    default = verify_timeline_parity(str(stage_file), otio_file=str(otio_file))

    for block in (self_check["expected"], self_check["actual"]):
        assert "start_time_code" not in block
        assert "end_time_code" not in block
        assert block["clip_count"] == 3

    # Anchored: the expectation follows the anchor, not the conversion.
    assert anchored["parity"] is True
    assert anchored["expected"]["start_time_code"] == 1001.0
    assert anchored["actual"]["start_time_code"] == 1001.0

    # Unanchored: the documented 1-based conversion still applies.
    assert default["parity"] is True
    assert default["expected"]["start_time_code"] == 1.0
    assert default["actual"]["start_time_code"] == 1.0


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

    # The script must surface a real mismatch as a failed envelope. A Stack
    # nested inside a Track does not survive the authored subtree, so the
    # exported edit is shorter than the reference.
    nested_file = _write_otio(_build_nested_stack_timeline(), tmp_path / "nested.otio")
    nested_stage = tmp_path / "nested.usda"
    create_stage(str(nested_stage), name="nested")

    drifted = verify_tool.main(stage_file=str(nested_stage), otio_file=str(nested_file))
    assert drifted["success"] is False
    assert drifted["error"] == "timeline_parity_mismatch"
    assert drifted["context"]["differences"]
