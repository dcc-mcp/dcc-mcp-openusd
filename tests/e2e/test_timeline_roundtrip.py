"""End-to-end OTIO <-> USD timeline golden path (requires pxr and opentimelineio)."""

from __future__ import annotations

import pytest

otio = pytest.importorskip("opentimelineio")
from opentimelineio.opentime import RationalTime, TimeRange  # noqa: E402

from dcc_mcp_openusd.runtime import create_stage, define_xform, set_time_codes  # noqa: E402
from dcc_mcp_openusd.timeline import export_timeline, import_timeline, verify_timeline_parity  # noqa: E402


def _shot_timeline() -> "otio.schema.Timeline":
    """Three clips on one video track — 84 frames at 24 fps."""
    timeline = otio.schema.Timeline(name="shot_001", global_start_time=RationalTime(0, 24))
    track = otio.schema.Track(name="V1", kind=otio.schema.TrackKind.Video)
    timeline.tracks.append(track)
    for name, duration in (("plate_a", 24), ("plate_b", 36), ("plate_c", 24)):
        track.append(
            otio.schema.Clip(
                name=name,
                source_range=TimeRange(RationalTime(0, 24), RationalTime(duration, 24)),
                media_reference=otio.schema.ExternalReference(target_url=f"/media/{name}.mov"),
            )
        )
    return timeline


def test_otio_shot_timeline_survives_the_usd_round_trip(tmp_path, stage_file):
    """Import a shot timeline, author against it, and export it unchanged."""
    otio_file = tmp_path / "shot.otio"
    otio.adapters.write_to_file(_shot_timeline(), str(otio_file))

    imported = import_timeline(str(stage_file), otio_file=str(otio_file))
    assert (imported["start_time_code"], imported["end_time_code"]) == (1.0, 84.0)

    # Author against the imported range the way the shot build would.
    set_time_codes(str(stage_file), start_time_code=1.0, end_time_code=84.0, frames_per_second=24.0)
    define_xform(str(stage_file), "/World/Shot")

    report = verify_timeline_parity(str(stage_file), otio_file=str(otio_file))
    assert report["parity"] is True, report["differences"]

    exported_file = tmp_path / "shot_exported.otio"
    exported = export_timeline(str(stage_file), output_file=str(exported_file))
    assert exported["clip_count"] == 3
    assert exported["duration_frames"] == 84.0

    reread = otio.adapters.read_from_file(str(exported_file))
    assert reread.name == "shot_001"
    assert reread.duration() == RationalTime(84, 24)
    assert [clip.name for clip in reread.tracks[0].find_clips()] == ["plate_a", "plate_b", "plate_c"]


def test_a_stage_with_only_time_codes_exports_a_readable_timeline(tmp_path):
    """Any stage with a usable time axis exports non-empty, re-readable OTIO."""
    stage_file = tmp_path / "shot.usda"
    create_stage(str(stage_file), name="shot_002")
    set_time_codes(str(stage_file), start_time_code=1.0, end_time_code=48.0, frames_per_second=24.0)

    exported_file = tmp_path / "shot_002.otio"
    exported = export_timeline(str(stage_file), output_file=str(exported_file))

    assert exported["authored_source"] == "stage_time_codes"
    reread = otio.adapters.read_from_file(str(exported_file))
    assert reread.duration() == RationalTime(48, 24)
    assert verify_timeline_parity(str(stage_file))["parity"] is True
