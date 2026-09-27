"""OpenTimelineIO <-> USD timeline interop helpers.

``opentimelineio`` is an **optional** dependency declared as the ``timeline``
extra::

    pip install "dcc-mcp-openusd[timeline]"

Nothing here imports ``opentimelineio`` at module import time: the adapter must
keep importing and working in environments without it. Every entry point that
needs it calls :func:`require_otio` first, so a missing install surfaces as an
actionable :class:`~dcc_mcp_openusd.runtime.OpenUsdError` naming the extra
instead of an empty or silently truncated result.

Authored model
--------------
An OTIO timeline is authored into the stage as a small USD subtree built from
``Scope`` prims, each carrying a flat ``customData`` dictionary under
``dccMcpOtio``::

    /World/Timeline                kind="timeline"  name, rate, duration_frames
      /World/Timeline/V1           kind="track"     name, otio_kind, index
        /World/Timeline/V1/A       kind="clip"      name, source_start, ...
        /World/Timeline/V1/Gap_1   kind="gap"       duration

plus the stage time codes. Gaps are authored as prims so the total duration
survives a round trip even when a track ends with one.

Time code convention
--------------------
An OTIO ``global_start_time`` counts frames from zero while USD time codes are
one-based, so the conversion is::

    start_time_code = global_start_frames + 1
    end_time_code   = start_time_code + duration_frames - 1

Both directions live in :func:`_time_codes_from_otio` /
:func:`_global_start_from_time_code` so the rule is stated exactly once.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from dcc_mcp_openusd.runtime import OpenUsdError, detect_runtime, require_pxr

#: Where the timeline subtree is authored by default.
DEFAULT_TIMELINE_PRIM_PATH = "/World/Timeline"

#: ``customData`` key holding the flat OTIO payload dictionary.
OTIO_CUSTOM_DATA_KEY = "dccMcpOtio"

#: Fallback frame rate when neither OTIO nor the stage declares one.
DEFAULT_RATE = 24.0

#: Frame tolerance used by the parity comparison.
PARITY_TOLERANCE = 1e-6

_MISSING_OTIO_MESSAGE = (
    "OpenTimelineIO runtime is required for this tool but is not available. "
    'Install it with: pip install "dcc-mcp-openusd[timeline]"'
)

_MAX_SAMPLE_SCAN_PRIMS = 500
_MAX_REPORTED_SAMPLE_TIMES = 64


# ---------------------------------------------------------------------------
# Optional OpenTimelineIO runtime detection
# ---------------------------------------------------------------------------


@dataclass
class OtioRuntimeInfo:
    """Detected OpenTimelineIO availability."""

    has_otio: bool
    version: Optional[str] = None


_OTIO_RUNTIME_INFO: Optional[OtioRuntimeInfo] = None


def detect_otio() -> OtioRuntimeInfo:
    """Return OpenTimelineIO availability without importing it eagerly.

    The result is cached, mirroring :func:`~dcc_mcp_openusd.runtime.detect_runtime`.
    Tests reset the cache through the module global ``_OTIO_RUNTIME_INFO``.
    """
    global _OTIO_RUNTIME_INFO
    if _OTIO_RUNTIME_INFO is not None:
        return _OTIO_RUNTIME_INFO
    try:
        import opentimelineio as otio

        version = getattr(otio, "__version__", None)
        _OTIO_RUNTIME_INFO = OtioRuntimeInfo(has_otio=True, version=str(version) if version else None)
    except Exception:
        _OTIO_RUNTIME_INFO = OtioRuntimeInfo(has_otio=False)
    return _OTIO_RUNTIME_INFO


def require_otio(feature: str = "this operation") -> None:
    """Raise :class:`OpenUsdError` when ``opentimelineio`` is not installed."""
    if not detect_otio().has_otio:
        raise OpenUsdError(f"{feature} requires the OpenTimelineIO package. {_MISSING_OTIO_MESSAGE}")


def _otio():
    """Return the ``opentimelineio`` module, failing fast when it is missing."""
    require_otio("This timeline operation")
    import opentimelineio as otio

    return otio


# ---------------------------------------------------------------------------
# Small numeric / naming helpers
# ---------------------------------------------------------------------------


def _num(value: Any, digits: int = 6) -> float:
    """Round *value* to *digits* decimals so round trips compare exactly."""
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return 0.0


def _frames(time: Any, rate: float) -> float:
    """Convert an OTIO ``RationalTime`` to a frame count at *rate*."""
    if time is None:
        return 0.0
    try:
        denominator = float(time.rate)
    except (AttributeError, TypeError, ValueError):
        return 0.0
    if denominator <= 0:
        return 0.0
    return _num(float(time.value) * float(rate) / denominator)


def _rational_time(value: float, rate: float):
    """Build an OTIO ``RationalTime`` at *rate*."""
    from opentimelineio.opentime import RationalTime

    return RationalTime(float(value), float(rate))


def _time_range(start: float, duration: float, rate: float):
    """Build an OTIO ``TimeRange`` at *rate*."""
    from opentimelineio.opentime import TimeRange

    return TimeRange(_rational_time(start, rate), _rational_time(duration, rate))


def _timeline_rate(timeline: Any) -> float:
    """Return the timeline's frame rate, falling back to :data:`DEFAULT_RATE`."""
    rate = _num(getattr(timeline.duration(), "rate", 0.0))
    return rate if rate > 0 else DEFAULT_RATE


def _track_kind(track: Any) -> str:
    """Return a bare track kind token (``Video`` / ``Audio``)."""
    label = str(getattr(track, "kind", "") or "")
    # OTIO exposes the kind either as a plain string or as an enum whose repr
    # is fully qualified; keep only the last component so both agree.
    return label.rsplit(".", 1)[-1] or "Video"


def _media_reference_target(clip: Any) -> str:
    """Return the clip's media target URL, or an empty string when absent."""
    reference = getattr(clip, "media_reference", None)
    target = getattr(reference, "target_url", None)
    return str(target) if target else ""


def _safe_child_name(value: str, fallback: str, index: int) -> str:
    """Sanitize *value* into a USDA-safe prim name."""
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip()).strip("._")
    return cleaned or f"{fallback}_{index}"


def _time_codes_from_otio(global_start_frames: float, duration_frames: float) -> Dict[str, float]:
    """Convert OTIO frame positions into inclusive USD time codes."""
    start = _num(global_start_frames) + 1.0
    return {"start": start, "end": _num(start + duration_frames - 1.0)}


def _global_start_from_time_code(start_time_code: float) -> float:
    """Convert a USD start time code back into an OTIO global start (0-based)."""
    return _num(start_time_code) - 1.0


# ---------------------------------------------------------------------------
# OTIO reading and digesting
# ---------------------------------------------------------------------------


def load_otio_timeline(otio_file: Optional[str] = None, otio_json: Optional[str] = None) -> Any:
    """Read an OTIO timeline from a file path or an inline OTIO JSON string.

    Exactly one of *otio_file* / *otio_json* must be supplied. Unreadable input
    raises :class:`OpenUsdError` rather than returning ``None``, so a broken
    path is never mistaken for an empty timeline.
    """
    otio = _otio()
    if bool(otio_file) == bool(otio_json):
        raise OpenUsdError("Provide exactly one of otio_file or otio_json")

    if otio_json:
        try:
            timeline = otio.adapters.read_from_string(otio_json, "otio_json")
        except Exception as exc:
            raise OpenUsdError(f"Could not parse otio_json: {exc}") from exc
    else:
        path = Path(str(otio_file)).expanduser()
        if not path.is_file():
            raise OpenUsdError(f"OTIO file does not exist: {path}")
        try:
            timeline = otio.adapters.read_from_file(str(path))
        except Exception as exc:
            raise OpenUsdError(f"Could not read OTIO file {path}: {exc}") from exc

    if timeline is None:
        raise OpenUsdError("OTIO input produced no timeline")
    if not isinstance(timeline, otio.schema.Timeline):
        raise OpenUsdError(
            "OTIO input is a {}; a single Timeline is required".format(type(timeline).__name__),
        )
    return timeline


def _iter_tracks(timeline: Any) -> List[Any]:
    """Return the tracks of *timeline*, flattening one level of nested stacks."""
    otio = _otio()
    tracks: List[Any] = []
    for child in timeline.tracks:
        if isinstance(child, otio.schema.Track):
            tracks.append(child)
        elif isinstance(child, otio.schema.Stack):
            tracks.extend(item for item in child if isinstance(item, otio.schema.Track))
    return tracks


def timeline_summary(timeline: Any) -> Dict[str, Any]:
    """Return a JSON-serializable digest of an OTIO timeline.

    The digest is the parity unit: two timelines round-trip identically when
    their digests compare equal field by field (clip names, in-points,
    durations, track layout, and total frame count).
    """
    otio = _otio()
    rate = _timeline_rate(timeline)
    global_start = getattr(timeline, "global_start_time", None)

    track_records: List[Dict[str, Any]] = []
    clip_records: List[Dict[str, Any]] = []
    for track_index, track in enumerate(_iter_tracks(timeline)):
        clips = [item for item in track if isinstance(item, otio.schema.Clip)]
        track_records.append(
            {
                "index": track_index,
                "name": str(track.name or ""),
                "kind": _track_kind(track),
                "clip_count": len(clips),
            }
        )
        for clip_index, clip in enumerate(clips):
            source_range = clip.source_range
            source_start = source_range.start_time if source_range is not None else _rational_time(0, rate)
            source_duration = source_range.duration if source_range is not None else clip.duration()
            position = clip.range_in_parent()
            clip_records.append(
                {
                    "track_index": track_index,
                    "track": str(track.name or ""),
                    "index": clip_index,
                    "name": str(clip.name or ""),
                    "source_start": _frames(source_start, rate),
                    "source_duration": _frames(source_duration, rate),
                    "start": _frames(position.start_time, rate) if position is not None else 0.0,
                    "media_reference": _media_reference_target(clip),
                }
            )

    duration_frames = _frames(timeline.duration(), rate)
    global_start_frames = _frames(global_start, rate) if global_start is not None else 0.0
    time_codes = _time_codes_from_otio(global_start_frames, duration_frames)
    return {
        "name": str(timeline.name or ""),
        "rate": rate,
        "global_start_time": global_start_frames,
        "duration_frames": duration_frames,
        "track_count": len(track_records),
        "clip_count": len(clip_records),
        "start_time_code": time_codes["start"],
        "end_time_code": time_codes["end"],
        "tracks": track_records,
        "clips": clip_records,
    }


# ---------------------------------------------------------------------------
# USD side: stage access and authored timeline primitives
# ---------------------------------------------------------------------------


def _stage_path(stage_file: str) -> Path:
    """Resolve *stage_file* and raise when it is not an existing file."""
    resolved = Path(str(stage_file)).expanduser().resolve()
    if not resolved.is_file():
        raise OpenUsdError(f"Stage file does not exist: {resolved}")
    return resolved


def _open_stage(path: Path) -> Any:
    """Open an existing stage, failing fast on a missing pxr runtime."""
    require_pxr("Timeline interop")
    from pxr import Usd  # type: ignore

    stage = Usd.Stage.Open(str(path))
    if stage is None:
        raise OpenUsdError(f"Could not open stage: {path}")
    return stage


def _validate_prim_path(value: str) -> str:
    """Validate an absolute prim path naming a prim."""
    path = str(value or "").strip()
    if not path.startswith("/") or "//" in path or path.endswith("/") or len(path) <= 1:
        raise OpenUsdError("timeline_prim_path must be an absolute prim path with a name, for example /World/Timeline")
    return path


def _define_prim_with_parents(stage: Any, prim_path: str, type_name: str) -> Any:
    """Define *prim_path* as *type_name*, creating missing ancestors as Xforms."""
    from pxr import Sdf  # type: ignore

    path = Sdf.Path(prim_path)
    ancestors: List[Any] = []
    parent = path.GetParentPath()
    while parent != Sdf.Path.emptyPath and parent != Sdf.Path.absoluteRootPath:
        if stage.GetPrimAtPath(parent).IsValid():
            break
        ancestors.append(parent)
        parent = parent.GetParentPath()
    for ancestor in reversed(ancestors):
        stage.DefinePrim(ancestor, "Xform")
    return stage.DefinePrim(path, type_name)


def _unique_child_name(stage: Any, parent_path: str, name: str) -> str:
    """Return *name*, suffixed when a sibling already claims it."""
    candidate = name
    suffix = 1
    while stage.GetPrimAtPath(f"{parent_path}/{candidate}").IsValid() and suffix < 1000:
        candidate = f"{name}_{suffix}"
        suffix += 1
    return candidate


def _write_otio_data(prim: Any, payload: Dict[str, Any]) -> None:
    """Store a flat OTIO payload dictionary in the prim's ``customData``."""
    prim.SetCustomDataByKey(OTIO_CUSTOM_DATA_KEY, dict(payload))


def _read_otio_data(prim: Any) -> Dict[str, Any]:
    """Return the prim's OTIO ``customData`` payload, or an empty dict."""
    try:
        data = prim.GetCustomDataByKey(OTIO_CUSTOM_DATA_KEY)
    except Exception:
        return {}
    if not data:
        return {}
    try:
        return {str(key): value for key, value in dict(data).items()}
    except Exception:
        return {}


def _as_float(data: Dict[str, Any], key: str, default: float = 0.0) -> float:
    value = data.get(key)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(data: Dict[str, Any], key: str, default: int = 0) -> int:
    return int(_as_float(data, key, float(default)))


def _as_str(data: Dict[str, Any], key: str, default: str = "") -> str:
    value = data.get(key)
    return str(value) if value is not None else default


def _collect_time_sample_info(stage: Any) -> Dict[str, Any]:
    """Report the stage's time-sampled animation (bounded scan).

    The scan is capped so a large stage cannot turn a timeline export into a
    full attribute walk; it drives the range fallback and is reported for
    context, but never participates in parity.
    """
    times: set = set()
    animated_prims = 0
    animated_attributes = 0
    scanned = 0
    for prim in stage.Traverse():
        if scanned >= _MAX_SAMPLE_SCAN_PRIMS:
            break
        scanned += 1
        prim_is_animated = False
        for attribute in prim.GetAttributes():
            if not _attribute_has_samples(attribute):
                continue
            prim_is_animated = True
            animated_attributes += 1
            if len(times) < _MAX_REPORTED_SAMPLE_TIMES:
                try:
                    times.update(float(sample) for sample in attribute.GetTimeSamples())
                except Exception:
                    pass
        if prim_is_animated:
            animated_prims += 1

    all_times = sorted(times)
    return {
        "scanned_prim_count": scanned,
        "animated_prim_count": animated_prims,
        "animated_attribute_count": animated_attributes,
        "sample_count": len(all_times),
        "sample_times": all_times[:_MAX_REPORTED_SAMPLE_TIMES],
    }


def _attribute_has_samples(attribute: Any) -> bool:
    """Return True when *attribute* carries time samples."""
    try:
        return bool(attribute.GetNumTimeSamples())
    except Exception:
        return False


# ---------------------------------------------------------------------------
# OTIO -> USD
# ---------------------------------------------------------------------------


def import_timeline(
    stage_file: str,
    otio_file: Optional[str] = None,
    otio_json: Optional[str] = None,
    timeline_prim_path: str = DEFAULT_TIMELINE_PRIM_PATH,
    frames_per_second: Optional[float] = None,
    author_clips: bool = True,
) -> Dict[str, Any]:
    """Read an OTIO timeline and apply it to a USD stage.

    Sets ``startTimeCode`` / ``endTimeCode`` / ``timeCodesPerSecond`` from the
    timeline and, unless *author_clips* is false, authors the track/clip/gap
    subtree under *timeline_prim_path* so the timeline can be exported again.
    The import is idempotent: an existing subtree at that path is replaced.
    """
    require_otio("Importing an OTIO timeline")
    path = _stage_path(stage_file)
    timeline = load_otio_timeline(otio_file=otio_file, otio_json=otio_json)

    rate = _num(frames_per_second) if frames_per_second is not None else _timeline_rate(timeline)
    if rate <= 0:
        raise OpenUsdError("frames_per_second must be greater than 0")

    summary = timeline_summary(timeline)
    duration_frames = float(summary["duration_frames"])
    if duration_frames <= 0:
        raise OpenUsdError("OTIO timeline has zero duration; there is nothing to import into the stage")
    time_codes = _time_codes_from_otio(float(summary["global_start_time"]), duration_frames)

    stage = _open_stage(path)
    stage.SetStartTimeCode(time_codes["start"])
    stage.SetEndTimeCode(time_codes["end"])
    stage.SetTimeCodesPerSecond(rate)

    prim_path = _validate_prim_path(timeline_prim_path)
    if author_clips:
        if stage.GetPrimAtPath(prim_path).IsValid():
            stage.RemovePrim(prim_path)
        _author_timeline(stage, timeline, prim_path, rate)
    stage.GetRootLayer().Save()

    return {
        "stage_file": str(path),
        "timeline_prim_path": prim_path,
        "timeline_name": summary["name"],
        "start_time_code": time_codes["start"],
        "end_time_code": time_codes["end"],
        "frames_per_second": rate,
        "duration_frames": duration_frames,
        "track_count": summary["track_count"],
        "clip_count": summary["clip_count"],
        "tracks": summary["tracks"],
        "clips": summary["clips"],
        "runtime": "pxr" if detect_runtime().has_pxr else "text-fallback",
    }


def _author_timeline(stage: Any, timeline: Any, prim_path: str, rate: float) -> None:
    """Author the OTIO track/clip/gap structure under *prim_path*."""
    otio = _otio()
    summary = timeline_summary(timeline)

    timeline_prim = _define_prim_with_parents(stage, prim_path, "Scope")
    _write_otio_data(
        timeline_prim,
        {
            "kind": "timeline",
            "name": summary["name"],
            "rate": rate,
            "global_start_time": summary["global_start_time"],
            "duration_frames": summary["duration_frames"],
            "track_count": summary["track_count"],
            "clip_count": summary["clip_count"],
        },
    )

    for track_index, track in enumerate(_iter_tracks(timeline)):
        track_name = _unique_child_name(stage, prim_path, _safe_child_name(track.name, "Track", track_index))
        track_path = f"{prim_path}/{track_name}"
        track_prim = _define_prim_with_parents(stage, track_path, "Scope")
        _write_otio_data(
            track_prim,
            {
                "kind": "track",
                "name": str(track.name or ""),
                "otio_kind": _track_kind(track),
                "index": track_index,
            },
        )

        cursor = 0.0
        for item_index, item in enumerate(track):
            if isinstance(item, otio.schema.Clip):
                source_range = item.source_range
                source_start = source_range.start_time if source_range is not None else _rational_time(0, rate)
                source_duration = source_range.duration if source_range is not None else item.duration()
                position = item.range_in_parent()
                payload = {
                    "kind": "clip",
                    "index": item_index,
                    "name": str(item.name or ""),
                    "source_start": _frames(source_start, rate),
                    "source_duration": _frames(source_duration, rate),
                    "start": _frames(position.start_time, rate) if position is not None else cursor,
                    "media": _media_reference_target(item),
                }
                fallback = "Clip"
            elif isinstance(item, otio.schema.Gap):
                gap_duration = _frames(
                    item.source_range.duration if item.source_range is not None else item.duration(), rate
                )
                payload = {
                    "kind": "gap",
                    "index": item_index,
                    "duration": gap_duration,
                    "start": cursor,
                }
                fallback = "Gap"
            else:
                continue

            item_name = _unique_child_name(
                stage, track_path, _safe_child_name(payload.get("name"), fallback, item_index)
            )
            item_prim = _define_prim_with_parents(stage, f"{track_path}/{item_name}", "Scope")
            _write_otio_data(item_prim, payload)
            cursor += _as_float(payload, "source_duration", _as_float(payload, "duration", 0.0))


# ---------------------------------------------------------------------------
# USD -> OTIO
# ---------------------------------------------------------------------------


def export_timeline(
    stage_file: str,
    output_file: Optional[str] = None,
    timeline_prim_path: str = DEFAULT_TIMELINE_PRIM_PATH,
    name: Optional[str] = None,
    include_json: Optional[bool] = None,
) -> Dict[str, Any]:
    """Read a USD stage's time axis and produce an OTIO timeline.

    The timeline is rebuilt from the authored track/clip/gap subtree when one
    exists under *timeline_prim_path*. Otherwise a single video track with one
    clip covering the stage range is synthesized, so any stage with a usable
    time axis exports a non-empty, re-readable timeline.

    *include_json* defaults to ``True`` when no *output_file* is given.
    """
    require_otio("Exporting an OTIO timeline")
    otio = _otio()
    path = _stage_path(stage_file)
    stage = _open_stage(path)
    prim_path = _validate_prim_path(timeline_prim_path)

    rate = _num(stage.GetTimeCodesPerSecond())
    if rate <= 0:
        rate = DEFAULT_RATE
    start = _num(stage.GetStartTimeCode())
    end = _num(stage.GetEndTimeCode())

    time_samples = _collect_time_sample_info(stage)
    sample_times = time_samples["sample_times"]
    if end < start and sample_times:
        # An inverted or unset range carries no duration, so the authored
        # samples define the shot range instead.
        start = _num(sample_times[0])
        end = _num(sample_times[-1])
    if end < start:
        end = start
    duration_frames = _num(end - start + 1.0)
    time_samples["sample_times"] = [time for time in sample_times if start <= time <= end]

    spec = _read_authored_timeline(stage, prim_path)
    authored = spec is not None
    if spec is None:
        spec = _synthesize_timeline_spec(stage, path, start, end, rate, name)
    if name:
        spec["name"] = str(name)
    spec["rate"] = rate

    timeline = _build_otio_timeline(otio, spec, rate)
    otio_json = timeline.to_json_string()

    written_file = None
    if output_file:
        target = Path(str(output_file)).expanduser()
        if target.parent and not target.parent.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
        try:
            otio.adapters.write_to_file(timeline, str(target))
        except Exception as exc:
            raise OpenUsdError(f"Could not write OTIO file {target}: {exc}") from exc
        written_file = str(target)

    summary = timeline_summary(timeline)
    result: Dict[str, Any] = {
        "stage_file": str(path),
        "timeline_prim_path": prim_path,
        "timeline_name": summary["name"],
        "authored_source": "usd_prims" if authored else "stage_time_codes",
        "start_time_code": start,
        "end_time_code": end,
        "frames_per_second": rate,
        "duration_frames": duration_frames,
        "track_count": summary["track_count"],
        "clip_count": summary["clip_count"],
        "tracks": summary["tracks"],
        "clips": summary["clips"],
        "time_samples": time_samples,
        "output_file": written_file,
        "runtime": "pxr" if detect_runtime().has_pxr else "text-fallback",
    }
    if include_json is None:
        include_json = output_file is None
    if include_json:
        result["otio_json"] = otio_json
    return result


def _read_authored_timeline(stage: Any, prim_path: str) -> Optional[Dict[str, Any]]:
    """Return the authored timeline spec under *prim_path*, or ``None``."""
    prim = stage.GetPrimAtPath(prim_path)
    if not prim.IsValid():
        return None
    data = _read_otio_data(prim)
    if data.get("kind") != "timeline":
        return None

    tracks: List[Dict[str, Any]] = []
    for track_child in prim.GetChildren():
        track_data = _read_otio_data(track_child)
        if track_data.get("kind") != "track":
            continue
        items: List[Dict[str, Any]] = []
        for item_child in track_child.GetChildren():
            item_data = _read_otio_data(item_child)
            kind = item_data.get("kind")
            if kind == "clip":
                items.append(
                    {
                        "type": "clip",
                        "name": _as_str(item_data, "name"),
                        "source_start": _as_float(item_data, "source_start"),
                        "source_duration": _as_float(item_data, "source_duration"),
                        "start": _as_float(item_data, "start"),
                        "media": _as_str(item_data, "media"),
                    }
                )
            elif kind == "gap":
                items.append(
                    {
                        "type": "gap",
                        "duration": _as_float(item_data, "duration"),
                        "start": _as_float(item_data, "start"),
                    }
                )
        tracks.append(
            {
                "index": _as_int(track_data, "index", len(tracks)),
                "name": _as_str(track_data, "name", track_child.GetName()),
                "kind": _as_str(track_data, "otio_kind", "Video"),
                "items": items,
            }
        )

    if not tracks:
        return None
    tracks.sort(key=lambda track: track["index"])
    return {
        "name": _as_str(data, "name"),
        "rate": _as_float(data, "rate", DEFAULT_RATE) or DEFAULT_RATE,
        "global_start_time": _as_float(data, "global_start_time") if "global_start_time" in data else None,
        "tracks": tracks,
    }


def _synthesize_timeline_spec(
    stage: Any,
    stage_path: Path,
    start: float,
    end: float,
    rate: float,
    name: Optional[str],
) -> Dict[str, Any]:
    """Build a single-track spec covering the stage's time axis."""
    label = name
    if not label:
        default_prim = stage.GetDefaultPrim()
        label = default_prim.GetName() if default_prim.IsValid() else stage_path.stem
    return {
        "name": str(label),
        "rate": rate,
        "global_start_time": None,
        "tracks": [
            {
                "index": 0,
                "name": "V1",
                "kind": "Video",
                "items": [
                    {
                        "type": "clip",
                        "name": str(label),
                        "source_start": 0.0,
                        "source_duration": _num(end - start + 1.0),
                        "start": 0.0,
                        "media": str(stage_path),
                    }
                ],
            }
        ],
    }


def _build_otio_timeline(otio: Any, spec: Dict[str, Any], rate: float) -> Any:
    """Build an OTIO timeline from a timeline spec dict."""
    global_start = spec.get("global_start_time")
    if global_start is None:
        global_start = 0.0
    timeline = otio.schema.Timeline(
        name=spec.get("name") or "usd_timeline",
        global_start_time=_rational_time(global_start, rate),
    )

    for track_spec in spec.get("tracks", []):
        kind_name = str(track_spec.get("kind") or "Video")
        kind = getattr(otio.schema.TrackKind, kind_name, otio.schema.TrackKind.Video)
        track = otio.schema.Track(name=track_spec.get("name") or "V1", kind=kind)
        cursor = 0.0
        for item in track_spec.get("items", []):
            start = _num(item.get("start", cursor))
            if start > cursor + PARITY_TOLERANCE:
                track.append(otio.schema.Gap(source_range=_time_range(0.0, start - cursor, rate)))
                cursor = start
            if item.get("type") == "gap":
                duration = _num(item.get("duration"))
                track.append(otio.schema.Gap(source_range=_time_range(0.0, duration, rate)))
                cursor += duration
                continue
            duration = _num(item.get("source_duration"))
            clip = otio.schema.Clip(
                name=item.get("name") or "clip",
                source_range=_time_range(_num(item.get("source_start")), duration, rate),
            )
            media = item.get("media")
            if media:
                clip.media_reference = otio.schema.ExternalReference(target_url=str(media))
            track.append(clip)
            cursor += duration
        timeline.tracks.append(track)
    return timeline


# ---------------------------------------------------------------------------
# Round-trip parity
# ---------------------------------------------------------------------------


def verify_timeline_parity(
    stage_file: str,
    otio_file: Optional[str] = None,
    otio_json: Optional[str] = None,
    timeline_prim_path: str = DEFAULT_TIMELINE_PRIM_PATH,
    frames_per_second: Optional[float] = None,
    tolerance: float = PARITY_TOLERANCE,
) -> Dict[str, Any]:
    """Assert that a USD stage and an OTIO timeline describe the same edit.

    With *otio_file* / *otio_json* supplied the reference timeline is imported
    into the stage and exported again, then the two digests are compared field
    by field (track count, clip count, total frames, clip names, in-points,
    durations, positions, and the derived USD time codes). Without a reference
    the stage's own export is re-read through OTIO and compared against itself,
    which proves the exported payload is non-empty and re-readable.

    The result is a report, not an exception: ``parity`` is ``False`` and
    ``differences`` lists every mismatching field when the round trip drifts.
    """
    require_otio("Verifying timeline parity")
    path = _stage_path(stage_file)

    if otio_file or otio_json:
        expected = timeline_summary(load_otio_timeline(otio_file=otio_file, otio_json=otio_json))
        import_timeline(
            str(path),
            otio_file=otio_file,
            otio_json=otio_json,
            timeline_prim_path=timeline_prim_path,
            frames_per_second=frames_per_second,
        )
        source = "reference_timeline"
    else:
        expected = None
        source = "stage_self_check"

    exported = export_timeline(str(path), timeline_prim_path=timeline_prim_path, include_json=True)
    actual = timeline_summary(load_otio_timeline(otio_json=str(exported["otio_json"])))
    if expected is None:
        expected = actual

    exported_time_codes = {
        "start_time_code": _num(exported["start_time_code"]),
        "end_time_code": _num(exported["end_time_code"]),
    }
    differences = _compare_summaries(expected, actual, tolerance)
    differences.extend(_compare_time_codes(expected, exported_time_codes, tolerance))

    return {
        "stage_file": str(path),
        "timeline_prim_path": _validate_prim_path(timeline_prim_path),
        "verified": not differences,
        "parity": not differences,
        "source": source,
        "differences": differences,
        "checked": [
            "track_count",
            "clip_count",
            "duration_frames",
            "clip_names",
            "clip_in_points",
            "clip_durations",
            "clip_positions",
            "start_time_code",
            "end_time_code",
        ],
        "expected": {
            "track_count": expected["track_count"],
            "clip_count": expected["clip_count"],
            "duration_frames": expected["duration_frames"],
            "start_time_code": expected["start_time_code"],
            "end_time_code": expected["end_time_code"],
            "clips": expected["clips"],
        },
        "actual": {
            "track_count": actual["track_count"],
            "clip_count": actual["clip_count"],
            "duration_frames": actual["duration_frames"],
            "start_time_code": exported_time_codes["start_time_code"],
            "end_time_code": exported_time_codes["end_time_code"],
            "clips": actual["clips"],
        },
        "runtime": "pxr" if detect_runtime().has_pxr else "text-fallback",
    }


def _close(expected: Any, actual: Any, tolerance: float) -> bool:
    """Compare two numeric or scalar values within *tolerance*."""
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return abs(float(expected) - float(actual)) <= tolerance
    return expected == actual


def _compare_summaries(expected: Dict[str, Any], actual: Dict[str, Any], tolerance: float) -> List[Dict[str, Any]]:
    """Return the list of differing fields between two timeline digests."""
    differences: List[Dict[str, Any]] = []

    def check(field: str, expected_value: Any, actual_value: Any) -> None:
        if not _close(expected_value, actual_value, tolerance):
            differences.append({"field": field, "expected": expected_value, "actual": actual_value})

    check("track_count", expected["track_count"], actual["track_count"])
    check("clip_count", expected["clip_count"], actual["clip_count"])
    check("duration_frames", _num(expected["duration_frames"]), _num(actual["duration_frames"]))

    expected_clips = expected["clips"]
    actual_clips = actual["clips"]
    for index in range(max(len(expected_clips), len(actual_clips))):
        prefix = f"clips[{index}]"
        if index >= len(expected_clips):
            differences.append({"field": prefix, "expected": None, "actual": actual_clips[index].get("name")})
            continue
        if index >= len(actual_clips):
            differences.append({"field": prefix, "expected": expected_clips[index].get("name"), "actual": None})
            continue
        before = expected_clips[index]
        after = actual_clips[index]
        check(f"{prefix}.name", before["name"], after["name"])
        check(f"{prefix}.track_index", before["track_index"], after["track_index"])
        check(f"{prefix}.source_start", _num(before["source_start"]), _num(after["source_start"]))
        check(
            f"{prefix}.source_duration",
            _num(before["source_duration"]),
            _num(after["source_duration"]),
        )
        check(f"{prefix}.start", _num(before["start"]), _num(after["start"]))
    return differences


def _compare_time_codes(
    expected: Dict[str, Any],
    actual: Dict[str, Any],
    tolerance: float,
) -> List[Dict[str, Any]]:
    """Compare the time codes an OTIO digest implies against the stage's."""
    differences: List[Dict[str, Any]] = []

    def check(field: str, expected_value: float, actual_value: float) -> None:
        if abs(float(expected_value) - float(actual_value)) > tolerance:
            differences.append({"field": field, "expected": expected_value, "actual": actual_value})

    check("start_time_code", _num(expected["start_time_code"]), _num(actual["start_time_code"]))
    check("end_time_code", _num(expected["end_time_code"]), _num(actual["end_time_code"]))
    return differences
