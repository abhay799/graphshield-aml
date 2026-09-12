from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import (
    FastAPI,
    HTTPException,
    Query,
)

from pydantic import (
    BaseModel,
    Field,
)

from api.analyst_routes import (
    router as analyst_router,
)

from api.graph_routes import (
    router as graph_router,
)

from api.intelligence_routes import (
    router as intelligence_router,
)

from api.online_graph_routes import (
    router as online_graph_router,
)

from services.graphshield_service import (
    GraphShieldService,
)


app = FastAPI(
    title="GraphShield AML API",
    version="0.1.0",
    description=(
        "Read-only analyst API for GraphShield AML. "
        "Certified artifacts are treated as immutable inputs."
    ),
)


# ============================================================
# ROUTER REGISTRATION
# ============================================================

# PHASE 7 ANALYST ROUTER
app.include_router(
    analyst_router
)

# PHASE 7 GRAPH ROUTER
app.include_router(
    graph_router
)

# PHASE 7 CASE INTELLIGENCE ROUTER
app.include_router(
    intelligence_router
)

# PHASE 9 ONLINE GRAPH ROUTER
app.include_router(
    online_graph_router
)


@lru_cache(maxsize=1)
def get_service() -> GraphShieldService:

    return GraphShieldService(
        enable_policy_reranker=False
    )


class EvidenceSearchRequest(
    BaseModel
):

    query: str = Field(
        min_length=1,
    )

    top_k: int = Field(
        default=5,
        ge=1,
        le=50,
    )


class PolicySearchRequest(
    BaseModel
):

    query: str = Field(
        min_length=1,
    )

    top_k: int = Field(
        default=5,
        ge=1,
        le=50,
    )

    jurisdiction: str | None = None


def case_not_found(
    error: KeyError,
) -> HTTPException:

    return HTTPException(
        status_code=404,
        detail=str(error).strip("'"),
    )


@app.get(
    "/",
    tags=["system"],
)
def root() -> dict[str, Any]:

    return {
        "service":
            "GraphShield AML API",

        "status":
            "running",

        "mode":
            "read_only",

        "docs":
            "/docs",
    }


@app.get(
    "/health",
    tags=["system"],
)
def health() -> dict[str, Any]:

    return get_service().health()


@app.get(
    "/governance",
    tags=["system"],
)
def governance() -> dict[str, Any]:

    return {
        "mode":
            "decision_support_only",

        "certified_artifacts":
            "read_only",

        "autonomous_account_blocking":
            False,

        "autonomous_case_closure":
            False,

        "autonomous_regulatory_filing":
            False,

        "human_review_required":
            True,
    }


@app.get(
    "/cases",
    tags=["cases"],
)
def list_cases(
    limit: int = Query(
        default=50,
        ge=1,
        le=500,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
) -> dict[str, Any]:

    service = get_service()

    cases = service.list_cases(
        limit=limit,
        offset=offset,
    )

    return {
        "offset":
            offset,

        "limit":
            limit,

        "count":
            len(cases),

        "cases":
            cases,
    }


@app.get(
    "/cases/{case_id}",
    tags=["cases"],
)
def get_case(
    case_id: str,
) -> dict[str, Any]:

    try:

        return get_service().get_case(
            case_id
        )

    except KeyError as error:

        raise case_not_found(
            error
        ) from error


@app.get(
    "/cases/{case_id}/overview",
    tags=["investigation"],
)
def case_overview(
    case_id: str,
) -> dict[str, Any]:

    try:

        result = (
            get_service()
            .case_overview(
                case_id
            )
        )

        return {
            "case_id":
                case_id,

            "overview":
                result,
        }

    except KeyError as error:

        raise case_not_found(
            error
        ) from error


@app.get(
    "/cases/{case_id}/paths",
    tags=["investigation"],
)
def case_paths(
    case_id: str,
) -> dict[str, Any]:

    try:

        result = (
            get_service()
            .path_evidence(
                case_id
            )
        )

        return {
            "case_id":
                case_id,

            "paths":
                result,
        }

    except KeyError as error:

        raise case_not_found(
            error
        ) from error


@app.get(
    "/cases/{case_id}/history",
    tags=["investigation"],
)
def case_history(
    case_id: str,
) -> dict[str, Any]:

    try:

        result = (
            get_service()
            .history_evidence(
                case_id
            )
        )

        return {
            "case_id":
                case_id,

            "history":
                result,
        }

    except KeyError as error:

        raise case_not_found(
            error
        ) from error


@app.get(
    "/cases/{case_id}/snapshot",
    tags=["investigation"],
)
def investigation_snapshot(
    case_id: str,
) -> dict[str, Any]:

    try:

        return (
            get_service()
            .investigation_snapshot(
                case_id
            )
        )

    except KeyError as error:

        raise case_not_found(
            error
        ) from error


@app.post(
    "/cases/{case_id}/evidence/search",
    tags=["retrieval"],
)
def evidence_search(
    case_id: str,
    request: EvidenceSearchRequest,
) -> dict[str, Any]:

    try:

        results = (
            get_service()
            .search_evidence(
                case_id=case_id,
                query=request.query,
                top_k=request.top_k,
            )
        )

        return {
            "case_id":
                case_id,

            "query":
                request.query,

            "top_k":
                request.top_k,

            "results":
                results,
        }

    except KeyError as error:

        raise case_not_found(
            error
        ) from error

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error


@app.post(
    "/policy/search",
    tags=["retrieval"],
)
def policy_search(
    request: PolicySearchRequest,
) -> dict[str, Any]:

    try:

        results = (
            get_service()
            .search_policy(
                query=request.query,
                top_k=request.top_k,
                jurisdiction=
                    request.jurisdiction,
            )
        )

        return {
            "query":
                request.query,

            "jurisdiction":
                request.jurisdiction,

            "top_k":
                request.top_k,

            "results":
                results,
        }

    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error


# ============================================================
# PHASE 8 OBSERVABILITY
# ============================================================

from api.observability import (
    install_observability,
)

install_observability(
    app
)


# ============================================================
# PHASE 8 SECURITY HARDENING
# ============================================================

from api.security import (
    install_security,
)

install_security(
    app
)

# GraphShield Phase 11 explainability routes
from api.explainability_routes import router as phase11_explainability_router
app.include_router(phase11_explainability_router)

# GraphShield Phase 12 investigation routes
from api.phase12_routes import router as phase12_investigation_router
app.include_router(phase12_investigation_router)
