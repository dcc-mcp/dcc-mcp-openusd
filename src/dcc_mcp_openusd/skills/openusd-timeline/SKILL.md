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

## Retrying after a parity failure

`verify_timeline_parity` offers `import_timeline` as its `on-failure`
follow-up so a failed assertion can be repaired by re-applying the edit.
`next-tools` carries **tool names only** — dcc-mcp-core does not interpolate
argument values into a suggested call. A retry taken straight from that
suggestion therefore runs `import_timeline` without `start_time_code`, which
resets an anchored shot to a 1-based range:

```text
anchored  1001..1084   ──on-failure retry (no start_time_code)──▶  1..84
```

This is silent — no warning is raised and the parity result is not invalidated,
because the retry produced a self-consistent stage, just on the wrong base.

Always re-supply `start_time_code` when retrying an anchored import:

```bash
# not: import_timeline(stage_file, otio_file)              # resets to 1..84
dcc-mcp-cli call openusd_timeline__import_timeline \
  stage_file=shot.usda otio_file=shot.otio start_time_code=1001
```

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

## Native runtime initialization

The server detects the optional OTIO runtime on its startup thread before
accepting tool calls. This avoids a native OTIO 0.18.1 crash observed when the
first import happened inside a gateway worker and a later call deserialized a
timeline. OTIO remains optional; the base install still reports a clear missing
runtime error when a timeline tool is requested without it.
