from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, HTTPException, Query

from explainability.explanation_bundle import (
    Phase11ExplanationBundleService,
)
from explainability.case_explanation import (
    Phase11CaseExplanationService,
)


router = APIRouter(
    prefix="/explainability",
    tags=["explainability"],
)


@lru_cache(maxsize=1)
def get_transaction_service() -> Phase11ExplanationBundleService:
    return Phase11ExplanationBundleService()


@lru_cache(maxsize=1)
def get_case_service() -> Phase11CaseExplanationService:
    return Phase11CaseExplanationService()


@router.get("/transactions/{transaction_id}")
def explain_transaction(
    transaction_id: str,
    top_k: int = Query(
        default=8,
        ge=1,
        le=25,
    ),
):
    try:
        return get_transaction_service().build(
            transaction_id=transaction_id,
            top_k=top_k,
        )

    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Required artifact unavailable: {exc}",
        ) from exc


@router.get("/cases/{case_id}")
def explain_case(
    case_id: str,
    top_k: int = Query(
        default=8,
        ge=1,
        le=25,
    ),
):
    try:
        return get_case_service().explain_case(
            case_id=case_id,
            top_k=top_k,
        )

    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Required artifact unavailable: {exc}",
        ) from exc
