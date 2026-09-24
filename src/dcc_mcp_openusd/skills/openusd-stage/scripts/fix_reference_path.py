"""Report and repair broken reference paths in an OpenUSD stage."""

from __future__ import annotations

from typing import Any, Dict, List

from dcc_mcp_core.skill import run_main, skill_entry, skill_error, skill_success, skill_warning

from dcc_mcp_openusd.runtime import fix_reference_path


def _summarize(entries: List[Dict[str, Any]]) -> str:
    return "; ".join("{}: {}".format(entry.get("prim_path") or "<stage>", entry.get("detail", "")) for entry in entries)


@skill_entry
def main(**kwargs) -> dict:
    # Branch on what the caller asked for, not on what happened. ``applied`` is
    # only true once something was written, so using it to pick the envelope
    # would turn "apply=true and nothing could be fixed" into a success.
    requested_apply = bool(kwargs.get("apply", False))
    requested_prim = kwargs.get("prim_path") or ""

    result = fix_reference_path(**kwargs)
    applied = result["applied"]
    failed = result["failed"]
    unresolved = result["unresolved"]
    targets = result["targets"]
    stage_file = result["stage_file"]

    # A failed rewrite is never a success: the stage is not in the state the
    # caller asked for, so it is reported instead of being skipped.
    if failed:
        return skill_error(
            "Reference fix failed for {} — {}".format(stage_file, _summarize(failed)),
            "reference_fix_failed",
            prompt="Fix the reported prims manually, or pass an asset_path that exists on disk.",
            stage_file=stage_file,
            targets=targets,
            failed=failed,
            unresolved=unresolved,
        )

    if not targets:
        # Nothing matched at all -- either the stage is clean or the filter
        # missed. Both are true whether or not a write was requested, so this
        # is checked before the apply branch: a second apply=true on an
        # already-fixed stage must stay a success, and a filter that missed
        # must still warn instead of being reported as a failed fix.
        message = "No broken references found in {}".format(stage_file)
        if requested_prim:
            return skill_warning(
                message,
                warning="No broken reference matched prim_path '{}'".format(requested_prim),
                prompt="Check the prim path, or drop prim_path to cover the whole stage.",
                stage_file=stage_file,
                targets=targets,
                prim_path=requested_prim,
            )
        return skill_success(message, stage_file=stage_file, targets=targets)

    if requested_apply:
        # The caller asked for a write. Anything less than a complete, verified
        # fix is a failure: a warning here would let a caller that promised a
        # fix read the envelope as success.
        if unresolved or not applied:
            summary = _summarize(unresolved or targets) or "no replacement could be applied"
            return skill_error(
                "No reference was fixed in {} — {}".format(stage_file, summary),
                "reference_unresolved",
                prompt="Pass asset_path or search_dirs so a replacement can be found for every broken reference.",
                stage_file=stage_file,
                targets=targets,
                unresolved=unresolved,
            )
        return skill_success(
            "Rewrote {} broken reference(s) in {}".format(
                len([target for target in targets if target["status"] == "fixed"]),
                stage_file,
            ),
            prompt="Re-run validate_stage to confirm the stage is clean.",
            verified=result["verified"],
            postcondition={"method": "stage_readback", "expected": "reference resolves", "actual": "fixed"},
            stage_file=stage_file,
            runtime=result["runtime"],
            targets=targets,
        )

    # ── dry run: nothing was written and nothing was meant to be ────────────
    if unresolved:
        message = "{} broken reference(s) reported; nothing written".format(len(targets))
        return skill_warning(
            message,
            warning="{} reference(s) still unresolved — {}".format(len(unresolved), _summarize(unresolved)),
            prompt="Pass the chosen asset_path (or search_dirs) and apply=true to write the fix.",
            stage_file=stage_file,
            targets=targets,
            unresolved=unresolved,
        )

    # Every target has a planned replacement. Reporting a postcondition here
    # would claim a write that never happened, so the envelope stays honest.
    return skill_success(
        "{} broken reference(s) reported; nothing written".format(len(targets)),
        prompt="Re-run with apply=true to write the planned replacement(s).",
        stage_file=stage_file,
        runtime=result["runtime"],
        targets=targets,
    )


if __name__ == "__main__":
    run_main(main)
