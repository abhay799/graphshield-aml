from __future__ import annotations

from datetime import UTC, datetime, timedelta
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


MAX_FUTURE_SKEW = timedelta(minutes=5)


def _reject_excessive_future_event(event_ts: str) -> None:
    try:
        parsed = datetime.fromisoformat(event_ts.replace("Z", "+00:00"))
    except ValueError:
        # Preserve the existing scoring-service validation/error contract.
        return
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    else:
        parsed = parsed.astimezone(UTC)

    if parsed > datetime.now(UTC) + MAX_FUTURE_SKEW:
        raise HTTPException(
            status_code=422,
            detail=(
                "event_ts is more than 5 minutes ahead of server UTC time; "
                "use the current time"
            ),
        )


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
    _reject_excessive_future_event(request.event_ts)
    try:
        return get_live_scoring_service().score_transaction(
            request.model_dump(),
            commit_runtime_state=True,
        )
    except LiveStateConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error