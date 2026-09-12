from __future__ import annotations

from fastapi import APIRouter, HTTPException

from enterprise.phase14_artifact_manifest import (
    verify_artifact_manifest,
)
from enterprise.phase14_runtime import (
    evaluate_readiness,
    get_runtime_config,
)

router = APIRouter(tags=["phase14-enterprise"])


@router.get("/live", include_in_schema=False)
def live() -> dict[str, str]:
    return {
        "status": "alive",
        "service": "graphshield-aml",
    }


@router.get("/ready", include_in_schema=False)
def ready() -> dict:
    config = get_runtime_config()
    result = evaluate_readiness(config)
    if not result["ready"]:
        raise HTTPException(
            status_code=503,
            detail=result,
        )
    return result


@router.get("/deployment")
def deployment_metadata() -> dict:
    config = get_runtime_config()
    return {
        "service": "graphshield-aml",
        "phase": 14,
        "runtime": config.public_metadata(),
        "safety_boundary": {
            "decision_support_only": True,
            "human_review_required": True,
            "autonomous_account_blocking": False,
            "autonomous_case_closure": False,
            "autonomous_regulatory_submission": False,
        },
    }


@router.get("/deployment/integrity")
def deployment_integrity() -> dict:
    result = verify_artifact_manifest()
    if not result["verified"]:
        raise HTTPException(
            status_code=503,
            detail=result,
        )
    return result
