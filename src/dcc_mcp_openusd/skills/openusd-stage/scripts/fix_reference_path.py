"""Report and repair broken reference paths in an OpenUSD stage."""

from __future__ import annotations

from typing import Any, Dict, List

from dcc_mcp_core.skill import run_main, skill_entry, skill_error, skill_success, skill_warning

from dcc_mcp_openusd.runtime import fix_reference_path

#: Statuses that mean "nothing was written and the caller must act".
_UNRESOLVED = "unresolved"
_FAILED = "failed"


def _summarize(entries: List[Dict[str, Any]]) -> str:
    return "; ".join("{}: {}".format(entry.get("prim_path") or "<stage>", entry.get("detail", "")) for entry in entries)


@skill_entry
def main(**kwargs) -> dict:
    result = fix_reference_path(**kwargs)
    applied = result["applied"]
    failed = result["failed"]
    unresolved = result["unresolved"]
    targets = result["targets"]

    if applied:
        message = "Rewrote {} broken reference(s) in {}".format(
            len([target for target in targets if target["status"] == "fixed"]),
            result["stage_file"],
        )
    else:
        message = "{} broken reference(s) reported; nothing written".format(len(targets))

    # A failed rewrite is never a success: the stage is not in the state the
    # caller asked for, so it is reported instead of being skipped.
    if failed:
        return skill_error(
            "{} — {} reference(s) could not be fixed".format(message, len(failed)),
            "reference_fix_failed",
            prompt="Fix the reported prims manually or pass an asset_path that exists on disk.",
            stage_file=result["stage_file"],
            targets=targets,
            failed=failed,
        )

    if unresolved:
        warning = "{} reference(s) still unresolved — {}".format(len(unresolved), _summarize(unresolved))
        if applied:
            # apply=True promised a fix; leaving a reference broken is a failure.
            return skill_error(
                "{} — {}".format(message, warning),
                "reference_unresolved",
                prompt="Pass asset_path or search_dirs so a replacement can be found for every broken reference.",
                stage_file=result["stage_file"],
                targets=targets,
                unresolved=unresolved,
            )
        return skill_warning(
            message,
            warning=warning,
            prompt="Pass the chosen asset_path (or search_dirs) and apply=true to write the fix.",
            stage_file=result["stage_file"],
            targets=targets,
            unresolved=unresolved,
        )

    if not targets:
        return skill_success(
            "No broken references found in {}".format(result["stage_file"]),
            stage_file=result["stage_file"],
            targets=targets,
        )

    return skill_success(
        message,
        prompt="Re-run validate_stage to confirm the stage is clean.",
        verified=result["verified"],
        postcondition={"method": "stage_readback", "expected": "reference resolves", "actual": "fixed"},
        stage_file=result["stage_file"],
        runtime=result["runtime"],
        targets=targets,
    )


if __name__ == "__main__":
    run_main(main)
