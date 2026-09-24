"""Suggest material bindings for prims and materials that need one."""

from __future__ import annotations

from typing import Any, Dict, List

from dcc_mcp_core.skill import run_main, skill_entry, skill_error, skill_success, skill_warning

from dcc_mcp_openusd.runtime import suggest_material_bind

_REASON_PROMPT = {
    "dangling_material_binding": "Bind one of the listed materials onto the prim.",
    "non_material_binding_target": "Rebind the prim to a real Material prim.",
    "unbound_material": "Bind the material onto one of the listed prims.",
    "explicit_request": "Apply the requested binding.",
}

#: Recovery hints keyed by the marker in the failure detail. Installing usd-core
#: only helps one of the three causes, so the others must not suggest it.
_CAUSE_HINTS = (
    (
        "requires both prim_path and material_path",
        "Pass both prim_path and material_path, then retry.",
        ["suggest_material_bind(stage_file, prim_path=..., material_path=..., apply=True)"],
    ),
    (
        "requires the pxr runtime",
        "Install the pxr runtime, or apply the suggestion through bind_material on a host that has it.",
        ["python -m pip install 'usd-core>=24.11,<27'"],
    ),
    (
        "not visible after re-reading",
        "Re-read the stage and confirm the prim and material still exist; the write did not take.",
        ["openusd_stage__list_stage"],
    ),
)


def _prompt(suggestions: List[Dict[str, Any]]) -> str:
    for suggestion in suggestions:
        prompt = _REASON_PROMPT.get(suggestion.get("reason", ""))
        if prompt:
            return prompt
    return "Review the suggestions and apply one with apply=true."


def _summarize(suggestions: List[Dict[str, Any]]) -> str:
    return "; ".join(
        "{} -> {}: {}".format(
            suggestion.get("prim_path") or "<no prim>",
            suggestion.get("material_path") or "<no material>",
            suggestion.get("detail", ""),
        )
        for suggestion in suggestions
    )


def _hint_for(detail: str) -> tuple[str, List[str]]:
    """Pick the prompt and solutions that match the actual failure cause."""
    for marker, prompt, solutions in _CAUSE_HINTS:
        if marker in detail:
            return prompt, solutions
    return "Check the reported failure and retry.", []


@skill_entry
def main(**kwargs) -> dict:
    requested_prim = kwargs.get("prim_path") or ""
    requested_material = kwargs.get("material_path") or ""

    result = suggest_material_bind(**kwargs)
    suggestions = result["suggestions"]
    unresolved = result["unresolved"]
    failed = result["failed"]

    if failed:
        detail = failed[0].get("detail", "")
        prompt, solutions = _hint_for(detail)
        return skill_error(
            "Material binding could not be applied — {}".format(_summarize(failed)),
            "material_bind_failed",
            prompt=prompt,
            possible_solutions=solutions,
            stage_file=result["stage_file"],
            suggestions=suggestions,
            failed=failed,
        )

    if result["applied"]:
        return skill_success(
            "Bound {} to {}".format(result["suggestions"][0]["material_path"], result["suggestions"][0]["prim_path"]),
            prompt="Re-run validate_stage to confirm the binding resolved.",
            verified=result["verified"],
            postcondition={"method": "stage_readback", "expected": "binding present", "actual": "applied"},
            stage_file=result["stage_file"],
            runtime=result["runtime"],
            suggestions=suggestions,
        )

    message = "{} material binding suggestion(s) for {}".format(len(suggestions), result["stage_file"])

    # No library to search means no candidate for some issue; that is worth a
    # warning rather than an empty success the agent would read as "all good".
    if unresolved:
        return skill_warning(
            message,
            warning="{} suggestion(s) have no candidate — {}".format(len(unresolved), _summarize(unresolved)),
            prompt="Create the missing material or prim, then re-run this tool.",
            stage_file=result["stage_file"],
            suggestions=suggestions,
            unresolved=unresolved,
        )

    if not suggestions:
        # A filter that matched nothing is not the same as a clean stage.
        if requested_prim or requested_material:
            filter_text = ", ".join(
                "{} '{}'".format(name, value)
                for name, value in (("prim_path", requested_prim), ("material_path", requested_material))
                if value
            )
            return skill_warning(
                message,
                warning="No binding issue matched {}".format(filter_text),
                prompt="Check the prim or material path, or drop the filters to cover the whole stage.",
                stage_file=result["stage_file"],
                suggestions=suggestions,
                prim_path=requested_prim,
                material_path=requested_material,
            )
        return skill_success(
            "No material binding suggestions for {}".format(result["stage_file"]),
            stage_file=result["stage_file"],
            suggestions=suggestions,
        )

    return skill_success(
        message,
        prompt=_prompt(suggestions),
        stage_file=result["stage_file"],
        runtime=result["runtime"],
        suggestions=suggestions,
    )


if __name__ == "__main__":
    run_main(main)
