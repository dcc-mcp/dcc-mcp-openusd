---
name: openusd-timeline
description: >-
  Domain skill for OpenTimelineIO timeline interop. Import an OTIO timeline
  into a USD stage time axis, export a stage back to OTIO, and assert
  round-trip parity.
license: MIT
compatibility: "Python 3.9+; dcc-mcp-core 0.18.2+; requires pxr (usd-core) OpenUSD runtime; requires opentimelineio (pip install \"dcc-mcp-openusd[timeline]\")"
allowed-tools: Bash Read Write
metadata:
  dcc-mcp:
    dcc: openusd
    version: "0.1.0"
    layer: domain
    search-hint: "openusd usd timeline otio opentimelineio edit clip track timecode round trip parity"
    tags: "openusd, usd, timeline, otio, opentimelineio, edit, clip, track, timecode"
    tools: tools.yaml
---

# OpenUSD Timeline

Move an edit between OpenTimelineIO and a USD stage without hand-converting
`RationalTime` into `startTimeCode` / `endTimeCode`.

Requires the optional `opentimelineio` package. When it is missing every tool
in this skill fails with an actionable error naming the extra instead of
returning an empty result:

```bash
pip install "dcc-mcp-openusd[timeline]"
```

## Model

`import_timeline` authors the edit under `/World/Timeline` (override with
`timeline_prim_path`) as `Scope` prims carrying a `dccMcpOtio` `customData`
dictionary — one prim per track, and one per clip or gap — next to the stage
time codes. That subtree is what `export_timeline` reads back, so a stage with
no authored timeline still exports a single video track covering its time axis.

## Time code convention

An OTIO `global_start_time` counts frames from zero while USD time codes are
one-based:

```text
startTimeCode = global_start_frames + 1
endTimeCode   = startTimeCode + duration_frames - 1
```

A 84-frame timeline at 24 fps with `global_start_time = 0` therefore becomes
`startTimeCode = 1`, `endTimeCode = 84`.

## Workflow

1. Ensure a stage exists.
2. `import_timeline` — apply an OTIO file or inline OTIO JSON to the stage.
3. `verify_timeline_parity` — assert the round trip conserved tracks, clips,
   total frames, clip names, and in-points.
4. `export_timeline` — write the stage's edit back out as OTIO when needed.

## Acceptance

The parity report is mechanical: track count, clip count, total frames, clip
names, clip in-points, clip durations, clip positions, and the derived
`startTimeCode` / `endTimeCode` are compared field by field. Exported OTIO is
always re-read through `opentimelineio` before it is reported, so a payload
that cannot be read back fails instead of being handed on.
