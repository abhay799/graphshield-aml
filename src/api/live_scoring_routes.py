from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.guarded_live_state_writer import LiveStateConflictError

if TYPE_CHECKING:
    from services.live_transaction_scoring_service import (
        LiveTransactionScoringService,
    )

router = APIRouter(prefix="/score", tags=["live-scoring"])


class TransactionScoreRequest(BaseModel):
    transaction_id: str
    event_ts: str
    from_bank: str
    from_account: str
    to_bank: str
    to_account: str
    amount_paid: float
    amount_received: float
    payment_currency: str
    receiving_currency: str
    payment_format: str


@lru_cache(maxsize=1)
def get_live_scoring_service() -> LiveTransactionScoringService:
    # Keep the heavy live-scoring/model import lazy. This ensures the router
    # itself is fully populated before api.app copies it into the FastAPI app,
    # while service initialization still enforces the model contract before
    # the first score is produced.
    from services.live_transaction_scoring_service import (
        LiveTransactionScoringService,
    )

    return LiveTransactionScoringService()


@router.post("/transaction")
def score_transaction(request: TransactionScoreRequest) -> dict[str, Any]:
    try:
        return get_live_scoring_service().score_transaction(
            request.model_dump(),
            commit_runtime_state=True,
        )
    except LiveStateConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error