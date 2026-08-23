# Install dcc-mcp-openusd

## Requirements

- Python 3.9 or newer.
- DCC-MCP Core 0.19.45 or newer.
- A wheel for `dcc-mcp-openusd` from PyPI or a trusted release/build source.
- Optional `usd-core` 24.11 or newer, below 27, for full Pixar `pxr` capabilities.

The base wheel is directly usable in **text-fallback** mode for bounded USDA
authoring and inspection. Material binding, cameras/lights, time-sampled
animation, and layer composition require the optional Pixar runtime. The
adapter never reports those capabilities as available in text-fallback mode.

## Supported versions and platforms

| Platform | Text fallback | `pxr` extra | Daemon mode |
| --- | --- | --- | --- |
| Windows | Supported | Supported when a compatible `usd-core` wheel exists | Detached process with explicit pidfile recommended |
| macOS | Supported | Supported when a compatible `usd-core` wheel exists | POSIX daemon with SIGTERM shutdown |
| Linux | Supported | Supported when a compatible `usd-core` wheel exists | POSIX daemon with SIGTERM shutdown |

`usd-core` distribution versions are checked against the 24.11 floor. The
runtime API may report a tuple such as `0.26.5`; that API label is reported for
diagnostics but is not incorrectly compared with the distribution floor.

## Agent quick path

Install a wheel, not an editable checkout. For repeatable automation, pin the
exact published version and verify its release/PyPI SHA-256 before installing
the downloaded file:

```text
python -m pip download --only-binary=:all: --no-deps "dcc-mcp-openusd==<version>" --dest wheels
python -m pip install wheels/dcc_mcp_openusd-<version>-py3-none-any.whl
dcc-mcp-openusd doctor --json
dcc-mcp-openusd verify --json
```

Replace `<version>` with an actual published version; agents must not infer a
future URL or checksum. To enable the complete pxr capability tier, install the
matching wheel with the OpenUSD extra:

```text
python -m pip install --only-binary=:all: "dcc-mcp-openusd[openusd]==<version>"
dcc-mcp-openusd verify --json
```

The intended catalog instructions URL is:

```text
https://raw.githubusercontent.com/dcc-mcp/dcc-mcp-openusd/main/install.md
```

Exit codes are stable:

| Code | Meaning |
| --- | --- |
| 0 | The detected capability tier is directly usable |
| 10 | Core, pxr version, or configuration preflight failed |
| 40 | Runtime verification could not create and reopen a temporary stage |

## Manual path

1. Create or select a Python 3.9+ environment.
2. Install the exact adapter wheel as shown above. The base wheel enables
   text-fallback; add `[openusd]` only when full pxr behavior is required.
3. Run `dcc-mcp-openusd doctor --json` to inspect the detected mode, package
   versions, capabilities, network configuration, and daemon plan.
4. Run `dcc-mcp-openusd verify --json`. Verification creates and reopens a
   temporary stage through the detected mode, then removes the temporary files.
5. Start the foreground standalone service:

   ```text
   dcc-mcp-openusd
   ```

The server binds to loopback on an OS-assigned port unless configured
otherwise. It has no external OpenUSD API endpoint or authentication token.
Discover the active endpoint through `dcc-mcp-cli list`.

## Verify

```text
dcc-mcp-openusd doctor --json
dcc-mcp-openusd verify --json
```

The JSON report includes:

- Core and optional `usd-core` versions and floors;
- `runtime.mode` (`pxr` or `text-fallback`) and `full_capabilities`;
- an explicit capability map so fallback cannot impersonate pxr;
- configured project/network/daemon values without starting a service;
- `directly_usable`, stable failure stage/reason, and executable next steps;
- an explicit no-provision/no-cache declaration.

Text-fallback may return exit 0 with `full_capabilities: false`; that is an
honest supported tier, not a failed or full-pxr installation.

## Daemon and pidfile lifecycle

Prefer an explicit, operator-owned pidfile rather than the temporary default:

```text
# Linux and macOS
dcc-mcp-openusd --daemon --pidfile <absolute-pidfile>

# Windows: use the module entry so Core can safely respawn Python
python -m dcc_mcp_openusd --daemon --pidfile <absolute-pidfile>
```

The Core daemon writes the PID after detaching. On POSIX it removes the pidfile
during a graceful exit. The pidfile is not sufficient proof of identity by
itself because a stale PID may have been reused.

### Safe stop on Linux and macOS

Read the exact pidfile, verify that the live process belongs to the expected
user and its command line contains `dcc-mcp-openusd`, then send SIGTERM:

```bash
pidfile="$HOME/.dcc-mcp/run/openusd.pid"
pid="$(cat "$pidfile")"
command="$(ps -p "$pid" -o command=)"
owner="$(ps -p "$pid" -o user= | tr -d ' ')"
case "$owner:$command" in
  "$(id -un)":*dcc-mcp-openusd*) kill -TERM "$pid" ;;
  *) echo "PID identity mismatch; refusing to stop" >&2; exit 1 ;;
esac
```

Wait for the process to exit and the pidfile to disappear. Do not escalate to
SIGKILL automatically. A stale pidfile may be removed only after confirming
that the recorded PID is no longer running.

### Safe stop on Windows

Windows detached processes do not have POSIX SIGTERM semantics. Start them
through `python -m dcc_mcp_openusd` as shown above. Verify the
exact PID and command line, terminate that one process without `-Force`, wait
for exit, then remove a same-PID stale pidfile if Core could not clean it:

```powershell
$pidFile = "$env:LOCALAPPDATA\dcc-mcp\openusd.pid"
$daemonPid = [int](Get-Content -Raw -LiteralPath $pidFile)
$process = Get-CimInstance Win32_Process -Filter "ProcessId=$daemonPid"
if (-not $process -or $process.CommandLine -notmatch 'dcc[-_]mcp[-_]openusd') {
    throw 'PID identity mismatch; refusing to stop'
}
Stop-Process -Id $daemonPid
Wait-Process -Id $daemonPid -ErrorAction SilentlyContinue
if (-not (Get-Process -Id $daemonPid -ErrorAction SilentlyContinue) -and
    (Test-Path -LiteralPath $pidFile)) {
    $recorded = [int](Get-Content -Raw -LiteralPath $pidFile)
    if ($recorded -eq $daemonPid) { Remove-Item -LiteralPath $pidFile }
}
```

Do not use name-wide process termination. The standalone service owns no second
adapter thread, pump, or job registry beyond Core's existing runtime.

## Upgrade

1. If daemonized, follow the identity-verified stop procedure above. If running
   in the foreground, stop it with Ctrl+C and wait for shutdown.
2. Download and checksum-verify an exact newer wheel.
3. Upgrade the wheel file:

   ```text
   python -m pip install --upgrade <verified-dcc-mcp-openusd-wheel>
   ```

4. Reinstall the matching `[openusd]` extra if full pxr capability is needed.
5. Run `doctor --json` and `verify --json` before restarting the daemon.

The adapter does not download or auto-provision external binaries and has no
persistent adapter cache. Verification uses self-cleaning temporary files.
Python package-manager caches are owned by pip, not by this adapter; manage them
with the operator's normal pip cache policy.

## Uninstall

Stop the foreground or daemon service first, then uninstall the wheel:

```text
python -m pip uninstall dcc-mcp-openusd
```

This does not remove user USD projects or pip's shared cache. If a stale
operator-selected pidfile remains, remove it only after confirming its PID is
not an active OpenUSD service.

## Troubleshooting

### `core_version_below_floor` / exit 10

Upgrade DCC-MCP Core to at least 0.19.45 in the same Python environment.

### `pxr_version_below_floor` / exit 10

The `pxr` module is importable but its `usd-core` distribution is missing or
older than 24.11. Install a compatible, exact wheel and rerun verification.

### Text fallback is reported

This is a supported limited tier. Basic USDA stage/project/reference operations
remain available. Install the `[openusd]` extra only when native material,
light/camera, animation, or composition tools are required.

### `runtime_smoke_failed` / exit 40

The detected mode could not create and reopen a temporary stage. Check wheel
compatibility, filesystem temporary-directory access, and native pxr library
loading, then rerun `dcc-mcp-openusd verify --json`.

### `invalid_port` or `invalid_gateway_port` / exit 10

Use `0` for OS assignment or a value from 1 through 65535.

### Service is not discovered

Doctor does not start the server. Start `dcc-mcp-openusd`, then use
`dcc-mcp-cli list`. The adapter uses a local standalone MCP endpoint and has no
remote OpenUSD authentication/configuration step.

### Pidfile exists but the service does not

Treat it as stale only after verifying that its recorded PID is absent. Never
signal a different process that reused the PID.
