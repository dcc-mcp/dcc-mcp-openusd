"""Structured ``ValidationIssue`` / ``ValidationResult`` schema.

This module is the frozen wire schema for :func:`dcc_mcp_openusd.runtime.validate_stage`.
It exists so that an agent can act on a validation report mechanically instead
of pattern-matching on strings.

Two decisions drive the shape:

``location`` is a *discriminated object*, not a string.
    The single string field used before this module overloaded three unrelated
    address spaces -- ``/Root/Mesh`` (a prim path), ``[stage.usda]`` (a layer)
    and ``[line 1]`` (a line number) -- and callers could only tell them apart
    by re-parsing the brackets. The ``kind`` member now carries that
    distinction; ``path`` and ``line`` hold exactly the one member that kind
    uses, and the other is always ``None``.

``label`` is display-only.
    It reproduces the *old* string value verbatim so logs and UI keep working
    through the migration window. Nothing may parse it -- parse ``kind``,
    ``path`` and ``line`` instead.

The schema maps onto the core :class:`~dcc_mcp_core.result_envelope.ToolResultEnvelope`
through :func:`to_tool_result_envelope`: structured diagnostics live in
``context``, ``error`` stays a plain string code, and ``_meta`` is left alone
for the runtime's own namespaced diagnostics.
"""

from __future__ import annotations

import json
import re
import warnings
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Tuple

from dcc_mcp_core.result_envelope import ToolResultEnvelope

#: Severity levels, most severe first. ``info`` is legal in the schema even
#: though no current rule emits it.
SEVERITIES: Tuple[str, ...] = ("error", "warning", "info")

#: Discriminator values accepted by :class:`ValidationLocation`.
LOCATION_KINDS: Tuple[str, ...] = ("prim", "layer", "line")

#: Envelope ``error`` code used when a stage has at least one error-severity
#: issue. ``error`` stays a string so the core envelope invariant holds.
VALIDATION_FAILED = "VALIDATION_FAILED"

#: Matches the ``[line N]`` legacy location marker.
_LINE_MARKER = re.compile(r"^line\s+(\d+)$")

#: Plural spelling used by :func:`format_summary_message`. ``info`` is listed
#: explicitly because it has no distinct plural in this context.
_SEVERITY_PLURALS = {"error": "errors", "warning": "warnings", "info": "info"}


def _is_mapping(value: Any) -> bool:
    """Return True for any mapping, so ``dict`` subclasses are accepted too."""
    return isinstance(value, Mapping)


def _copy_steps(steps: Any) -> List[Dict[str, Any]]:
    """Return *steps* as a list of plain dicts."""
    return [dict(step) for step in steps or ()]


def _step_key(step: Mapping[str, Any]) -> str:
    """Return a stable equality key for a next-step entry."""
    return json.dumps(step, sort_keys=True, ensure_ascii=False, default=str)


# ---------------------------------------------------------------------------
# location
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ValidationLocation:
    """Where an issue was found.

    Exactly one of ``path`` / ``line`` is populated, chosen by ``kind``:

    ==========  ==============================  ==========
    ``kind``    ``path``                        ``line``
    ==========  ==============================  ==========
    ``prim``    SdfPath, e.g. ``/Root/Mesh``    ``None``
    ``layer``   layer / file path               ``None``
    ``line``    ``None``                        line number
    ==========  ==============================  ==========

    ``label`` is the legacy string form, kept so existing logs and UI keep
    rendering through the migration window. It is display-only: parsing must
    read ``kind``, ``path`` and ``line``.
    """

    kind: str
    path: Optional[str] = None
    line: Optional[int] = None
    label: Optional[str] = None

    def __post_init__(self) -> None:
        """Fill ``label`` and reject combinations the schema forbids."""
        if self.kind not in LOCATION_KINDS:
            raise ValueError(f"unknown location kind {self.kind!r}; expected one of {', '.join(LOCATION_KINDS)}")
        if self.kind == "line":
            if self.path is not None:
                raise ValueError("a 'line' location must not carry a path")
            if not isinstance(self.line, int) or isinstance(self.line, bool) or self.line < 1:
                raise ValueError("a 'line' location requires a positive integer line number")
        else:
            if self.line is not None:
                raise ValueError(f"a {self.kind!r} location must not carry a line number")
            if not self.path:
                raise ValueError(f"a {self.kind!r} location requires a non-empty path")
        if self.label is None:
            object.__setattr__(self, "label", self.legacy_value)

    @property
    def legacy_value(self) -> str:
        """Return the pre-schema string form of this location."""
        if self.kind == "line":
            return f"[line {self.line}]"
        if self.kind == "layer":
            return f"[{self.path}]"
        return str(self.path)

    @classmethod
    def prim(cls, path: str) -> ValidationLocation:
        """Return a location pointing at a prim path."""
        return cls(kind="prim", path=path)

    @classmethod
    def layer(cls, path: str) -> ValidationLocation:
        """Return a location pointing at a layer or file."""
        return cls(kind="layer", path=path)

    @classmethod
    def at_line(cls, number: int) -> ValidationLocation:
        """Return a location pointing at a line number.

        Named ``at_line`` rather than ``line`` because ``line`` is itself a
        field: a same-named classmethod would silently become that field's
        dataclass default.
        """
        return cls(kind="line", line=number)

    @classmethod
    def from_value(cls, value: Any, *, warn: bool = True) -> ValidationLocation:
        """Normalize *value* into a :class:`ValidationLocation`.

        Accepts the current object form and, for one migration window, the
        legacy string form (``/Root/Mesh``, ``[stage.usda]``, ``[line 1]``).
        The string form is **deprecated**: writers must emit objects, and this
        branch is removed once the window closes.
        """
        if isinstance(value, ValidationLocation):
            return value
        if _is_mapping(value):
            kind = value.get("kind")
            legacy = kind is None
            if legacy:
                # A mapping without a discriminator predates ``kind``; infer it
                # from whichever payload member is populated, as for strings.
                if value.get("line") is not None:
                    kind = "line"
                elif value.get("path"):
                    kind = _parse_legacy_string(str(value["path"]))[0]
                else:
                    raise ValueError("cannot infer location kind from an empty mapping")
                _warn_legacy_location(value, warn)
            return cls(
                kind=str(kind),
                path=value.get("path"),
                line=value.get("line"),
                label=value.get("label"),
            )
        if isinstance(value, str):
            kind, path, line = _parse_legacy_string(value)
            _warn_legacy_location(value, warn)
            if kind == "line":
                return cls.at_line(int(line))  # type: ignore[arg-type]
            if kind == "layer":
                return cls.layer(str(path))
            return cls.prim(str(path))
        raise TypeError(f"location must be a ValidationLocation, mapping or string, got {type(value).__name__}")

    def to_dict(self) -> Dict[str, Any]:
        """Return the wire form: a discriminated object with stable keys."""
        return {
            "kind": self.kind,
            "path": self.path,
            "line": self.line,
            "label": self.label,
        }


def _warn_legacy_location(value: Any, warn: bool) -> None:
    """Emit the deprecation notice for a legacy ``location`` value."""
    if not warn:
        return
    warnings.warn(
        "reading a legacy validation 'location' string/mapping is deprecated and "
        "will be removed; emit and read {'kind', 'path', 'line', 'label'} objects",
        DeprecationWarning,
        stacklevel=4,
    )


def _parse_legacy_string(text: str) -> Tuple[str, Optional[str], Optional[int]]:
    """Split a legacy ``location`` string into ``(kind, path, line)``."""
    stripped = text.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        inner = stripped[1:-1].strip()
        match = _LINE_MARKER.match(inner)
        if match:
            return "line", None, int(match.group(1))
        return "layer", inner, None
    return "prim", stripped, None


def prim_location(path: str) -> ValidationLocation:
    """Shorthand for :meth:`ValidationLocation.prim`."""
    return ValidationLocation.prim(path)


def layer_location(path: str) -> ValidationLocation:
    """Shorthand for :meth:`ValidationLocation.layer`."""
    return ValidationLocation.layer(path)


def line_location(number: int) -> ValidationLocation:
    """Shorthand for :meth:`ValidationLocation.at_line`."""
    return ValidationLocation.at_line(number)


# ---------------------------------------------------------------------------
# issue
# ---------------------------------------------------------------------------


@dataclass
class ValidationIssue:
    """One rule violation found in a stage.

    ``strict_promoted`` distinguishes an issue that is an error on its own from
    one that only became an error because the caller asked for a strict run,
    which is what lets an agent explain *why* a stage is now invalid.
    """

    code: str
    severity: str
    message: str
    location: ValidationLocation
    strict_promoted: bool = False
    suggested_fix: Optional[Dict[str, Any]] = None
    next_steps: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Coerce the location and enforce the invariants callers rely on."""
        if self.severity not in SEVERITIES:
            raise ValueError(f"unknown severity {self.severity!r}; expected one of {', '.join(SEVERITIES)}")
        if not self.message:
            raise ValueError("a validation issue requires a non-empty message")
        if not isinstance(self.location, ValidationLocation):
            self.location = ValidationLocation.from_value(self.location)
        self.strict_promoted = bool(self.strict_promoted)
        self.next_steps = _copy_steps(self.next_steps)

    @classmethod
    def from_value(cls, value: Any) -> ValidationIssue:
        """Build an issue from a wire mapping or another issue.

        The legacy string ``location`` form is accepted for one migration
        window; every other member keeps its current meaning.
        """
        if isinstance(value, cls):
            return value
        if not _is_mapping(value):
            raise TypeError(f"validation issue must be a mapping, got {type(value).__name__}")
        return cls(
            code=str(value["code"]),
            severity=str(value["severity"]),
            message=str(value["message"]),
            location=ValidationLocation.from_value(value["location"]),
            strict_promoted=bool(value.get("strict_promoted", False)),
            suggested_fix=value.get("suggested_fix"),
            next_steps=_copy_steps(value.get("next_steps")),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Return the wire form of this issue."""
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "location": self.location.to_dict(),
            "strict_promoted": self.strict_promoted,
            "suggested_fix": dict(self.suggested_fix) if self.suggested_fix else None,
            "next_steps": _copy_steps(self.next_steps),
        }


def summarize_issues(issues: List[Any]) -> Dict[str, int]:
    """Count *issues* by severity and add a ``total``.

    All four keys are always present, including the zero counts, so a caller
    can index ``summary["error"]`` without guarding for ``KeyError``.
    """
    counts: Dict[str, int] = dict.fromkeys(SEVERITIES, 0)
    for issue in issues:
        severity = issue["severity"] if _is_mapping(issue) else issue.severity
        counts[severity] = counts.get(severity, 0) + 1
    counts["total"] = len(issues)
    return counts


def format_summary_message(summary: Mapping[str, int]) -> str:
    """Render ``summary`` as the human-readable ``ValidationResult.message``.

    Only non-zero severities are spelled out: ``"3 issues (1 error, 2 warnings)"``.
    """
    total = int(summary.get("total", 0))
    if total == 0:
        return "No validation issues"
    parts = [_count_noun(summary[severity], severity) for severity in SEVERITIES if summary.get(severity)]
    return f"{_count_noun(total, 'issue')} ({', '.join(parts)})"


def _count_noun(count: int, singular: str) -> str:
    """Render ``count`` next to *singular*, pluralized only above one."""
    plural = _SEVERITY_PLURALS.get(singular, singular + "s")
    return f"{count} {singular if count == 1 else plural}"


def aggregate_next_steps(issues: List[Any]) -> List[Dict[str, Any]]:
    """Return every issue's ``next_steps`` in order, without duplicates.

    Identical entries are collapsed: two issues of the same rule with the same
    arguments are one action for an agent, and the per-severity counts in
    ``summary`` already carry how many times it applies.
    """
    merged: List[Dict[str, Any]] = []
    seen: set = set()
    for issue in issues:
        steps = issue["next_steps"] if _is_mapping(issue) else issue.next_steps
        for step in steps or ():
            key = _step_key(step)
            if key in seen:
                continue
            seen.add(key)
            merged.append(dict(step))
    return merged


# ---------------------------------------------------------------------------
# result
# ---------------------------------------------------------------------------

#: Members of :class:`ValidationResult` that belong to the frozen schema.
#: Anything else on a payload is adapter metadata and lands in ``extra``.
_RESULT_KEYS = frozenset({"success", "message", "stage_file", "issues", "summary", "next_steps"})


@dataclass
class ValidationResult:
    """The structured outcome of validating one stage.

    ``success`` is ``summary["error"] == 0``: warnings never invalidate a stage
    on their own. ``next_steps`` aggregates every issue's steps so an agent can
    act without walking ``issues``.

    ``extra`` carries adapter metadata that is deliberately *outside* the frozen
    schema -- the collector ``runtime`` label and the ``rules`` registry -- and
    is merged last by :meth:`to_dict`, so it can never shadow a schema key.
    """

    success: bool
    message: str
    stage_file: str = ""
    issues: List[ValidationIssue] = field(default_factory=list)
    summary: Dict[str, int] = field(default_factory=dict)
    next_steps: List[Dict[str, Any]] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Derive every member that the caller did not supply."""
        self.issues = [
            issue if isinstance(issue, ValidationIssue) else ValidationIssue.from_value(issue) for issue in self.issues
        ]
        self.summary = dict(self.summary) if self.summary else summarize_issues(self.issues)
        self.success = bool(self.success)
        self.next_steps = _copy_steps(self.next_steps) if self.next_steps else aggregate_next_steps(self.issues)
        self.extra = dict(self.extra or {})
        if not self.message:
            self.message = format_summary_message(self.summary)

    @classmethod
    def from_issues(
        cls,
        stage_file: str,
        issues: List[Any],
        *,
        extra: Optional[Mapping[str, Any]] = None,
    ) -> ValidationResult:
        """Build a result from an ordered issue list.

        ``success``, ``summary`` and the aggregate ``next_steps`` are all
        derived from *issues*, so they cannot drift out of sync with it.
        """
        normalized = [
            issue if isinstance(issue, ValidationIssue) else ValidationIssue.from_value(issue) for issue in issues
        ]
        summary = summarize_issues(normalized)
        return cls(
            success=int(summary.get("error", 0)) == 0,
            message="",
            stage_file=stage_file,
            issues=normalized,
            summary=summary,
            next_steps=aggregate_next_steps(normalized),
            extra=dict(extra or {}),
        )

    @classmethod
    def from_value(cls, value: Any) -> ValidationResult:
        """Build a result from a wire payload or another result.

        Unknown members are preserved in ``extra`` so a caller can round-trip a
        payload produced by :func:`dcc_mcp_openusd.runtime.validate_stage`
        without losing the adapter metadata riding alongside the schema.
        """
        if isinstance(value, cls):
            return value
        if not _is_mapping(value):
            raise TypeError(f"validation result must be a mapping, got {type(value).__name__}")
        issues = [ValidationIssue.from_value(issue) for issue in value.get("issues", ())]
        summary = dict(value.get("summary") or ()) or summarize_issues(issues)
        success = value.get("success")
        if not isinstance(success, bool):
            success = int(summary.get("error", 0)) == 0
        next_steps = value.get("next_steps")
        return cls(
            success=success,
            message=str(value.get("message") or ""),
            stage_file=str(value.get("stage_file") or ""),
            issues=issues,
            summary=summary,
            next_steps=_copy_steps(next_steps) if next_steps else aggregate_next_steps(issues),
            extra={key: item for key, item in value.items() if key not in _RESULT_KEYS},
        )

    def to_dict(self) -> Dict[str, Any]:
        """Return the wire form: schema keys first, then ``extra``."""
        payload: Dict[str, Any] = {
            "success": self.success,
            "message": self.message,
            "stage_file": self.stage_file,
            "issues": [issue.to_dict() for issue in self.issues],
            "summary": dict(self.summary),
            "next_steps": _copy_steps(self.next_steps),
        }
        for key, value in self.extra.items():
            payload.setdefault(key, value)
        return payload


# ---------------------------------------------------------------------------
# core envelope mapping
# ---------------------------------------------------------------------------


def to_tool_result_envelope(result: ValidationResult) -> ToolResultEnvelope:
    """Map a :class:`ValidationResult` onto the core tool result envelope.

    ===============  ==========================================================
    envelope field   value
    ===============  ==========================================================
    ``success``      ``result.success`` (``summary["error"] == 0``)
    ``message``      ``result.message``, the severity summary
    ``error``        ``"VALIDATION_FAILED"`` when failing, otherwise ``None``
    ``context``      the :class:`ValidationResult` payload
    ``postcondition`` unused: validating a stage is a read, not a mutation
    ===============  ==========================================================

    Structured diagnostics stay in ``context``; ``_meta`` is left to the
    runtime for namespaced entries such as ``dcc.error``.
    """
    if not isinstance(result, ValidationResult):
        result = ValidationResult.from_value(result)
    return ToolResultEnvelope(
        success=result.success,
        message=result.message,
        error=None if result.success else VALIDATION_FAILED,
        context=result.to_dict(),
    )


__all__ = [
    "LOCATION_KINDS",
    "SEVERITIES",
    "VALIDATION_FAILED",
    "ValidationIssue",
    "ValidationLocation",
    "ValidationResult",
    "aggregate_next_steps",
    "format_summary_message",
    "layer_location",
    "line_location",
    "prim_location",
    "summarize_issues",
    "to_tool_result_envelope",
]
