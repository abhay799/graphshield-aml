from __future__ import annotations

from functools import lru_cache

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
)

from pydantic import (
    BaseModel,
    Field,
)

from services.analyst_state import (
    AnalystStateService,
)

from services.graphshield_service import (
    GraphShieldService,
)


router = APIRouter(
    prefix="/analyst",
    tags=["analyst-workflow"],
)


@lru_cache(maxsize=1)
def get_state_service():

    return AnalystStateService()


@lru_cache(maxsize=1)
def get_graphshield_service():

    return GraphShieldService(
        enable_policy_reranker=False
    )


class CaseStateUpdate(
    BaseModel
):

    review_status: str = Field(
        min_length=1,
        max_length=64,
    )

    analyst_note: str | None = Field(
        default=None,
        max_length=5000,
    )

    actor: str = Field(
        default="local_analyst",
        min_length=1,
        max_length=128,
    )


def validate_case(
    case_id: str,
) -> None:

    try:

        get_graphshield_service().get_case(
            case_id
        )

    except KeyError as error:

        raise HTTPException(
            status_code=404,
            detail=(
                f"Unknown case_id: "
                f"{case_id}"
            ),
        ) from error


@router.get(
    "/cases/{case_id}/state"
)
def get_case_state(
    case_id: str,
):

    validate_case(
        case_id
    )

    return (
        get_state_service()
        .get_case_state(
            case_id
        )
    )


@router.put(
    "/cases/{case_id}/state"
)
def update_case_state(
    case_id: str,
    request: CaseStateUpdate,
):

    validate_case(
        case_id
    )

    try:

        return (
            get_state_service()
            .update_case_state(
                case_id=
                    case_id,

                review_status=
                    request.review_status,

                analyst_note=
                    request.analyst_note,

                actor=
                    request.actor,
            )
        )

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error


@router.get(
    "/cases/{case_id}/audit"
)
def case_audit_history(
    case_id: str,
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
):

    validate_case(
        case_id
    )

    events = (
        get_state_service()
        .case_audit_history(
            case_id=
                case_id,

            limit=
                limit,
        )
    )

    return {
        "case_id":
            case_id,

        "count":
            len(events),

        "events":
            events,
    }
