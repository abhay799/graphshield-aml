from __future__ import annotations

from functools import lru_cache

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
)

from services.online_graph_service import (
    OnlineGraphService,
)


router = APIRouter(
    prefix="/online-graph",
    tags=["phase9-online-graph"],
)


@lru_cache(maxsize=1)
def get_online_graph_service() -> OnlineGraphService:
    return OnlineGraphService()


def not_found(error: KeyError) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail=str(error).strip("'"),
    )


@router.get("/status")
def online_graph_status():
    return get_online_graph_service().status()


@router.get("/accounts/{account_key}")
def account_state(
    account_key: str,
):
    try:
        return (
            get_online_graph_service()
            .account(account_key)
        )

    except KeyError as error:
        raise not_found(error) from error


@router.get(
    "/accounts/{account_key}/counterparties"
)
def account_counterparties(
    account_key: str,
    limit: int = Query(
        default=50,
        ge=1,
        le=500,
    ),
):
    try:
        results = (
            get_online_graph_service()
            .counterparties(
                account_key,
                limit,
            )
        )

        return {
            "account_key": account_key,
            "count": len(results),
            "counterparties": results,
        }

    except KeyError as error:
        raise not_found(error) from error


@router.get(
    "/accounts/{account_key}/transfers"
)
def recent_transfers(
    account_key: str,
    limit: int = Query(
        default=50,
        ge=1,
        le=500,
    ),
):
    try:
        results = (
            get_online_graph_service()
            .recent_transfers(
                account_key,
                limit,
            )
        )

        return {
            "account_key": account_key,
            "count": len(results),
            "transfers": results,
        }

    except KeyError as error:
        raise not_found(error) from error


@router.get(
    "/accounts/{account_key}/neighborhood"
)
def account_neighborhood(
    account_key: str,
    limit: int = Query(
        default=50,
        ge=1,
        le=250,
    ),
):
    try:
        results = (
            get_online_graph_service()
            .neighborhood(
                account_key,
                limit,
            )
        )

        return {
            "account_key": account_key,
            "count": len(results),
            "neighbors": results,
        }

    except KeyError as error:
        raise not_found(error) from error