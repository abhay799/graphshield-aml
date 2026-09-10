from __future__ import annotations

from functools import lru_cache

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
)

from services.case_graph_service import (
    CaseGraphService,
)


router = APIRouter(
    tags=[
        "graph-investigation"
    ]
)


@lru_cache(maxsize=1)
def get_graph_service():

    return CaseGraphService()


@router.get(
    "/cases/{case_id}/graph"
)
def case_graph(
    case_id: str,
    max_edges: int = Query(
        default=250,
        ge=1,
        le=1000,
    ),
):

    try:

        return (
            get_graph_service()
            .get_graph(
                case_id=
                    case_id,

                max_edges=
                    max_edges,
            )
        )

    except KeyError as error:

        raise HTTPException(
            status_code=404,
            detail=str(error).strip("'"),
        ) from error

    except FileNotFoundError as error:

        raise HTTPException(
            status_code=404,
            detail=str(error),
        ) from error

    except ValueError as error:

        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error
