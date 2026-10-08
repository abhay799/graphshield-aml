from __future__ import annotations

from collections import deque
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from threading import Lock
from time import monotonic
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.routing import APIRoute
from pydantic import BaseModel
from starlette.responses import JSONResponse

from services.guarded_live_state_writer import LiveStateConflictError

if TYPE_CHECKING:
    from services.live_transaction_scoring_service import (
        LiveTransactionScoringService,
    )

RATE_LIMIT_REQUESTS = 30
GLOBAL_RATE_LIMIT_REQUESTS = 300
RATE_LIMIT_WINDOW_SECONDS = 60.0
MAX_REQUEST_BODY_BYTES = 16 * 1024


class _LiveScoringRateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = {}
        self._global_events: deque[float] = deque()
        self._lock = Lock()

    @staticmethod
    def _prune(events: deque[float], cutoff: float) -> None:
        while events and events[0] <= cutoff:
            events.popleft()

    def _evict_idle_locked(self, cutoff: float) -> None:
        for client_ip, events in list(self._events.items()):
            self._prune(events, cutoff)
            if not events:
                del self._events[client_ip]

    def decision(self, client_ip: str, *, now: float | None = None) -> str | None:
        current = monotonic() if now is None else now
        cutoff = current - RATE_LIMIT_WINDOW_SECONDS
        with self._lock:
            self._prune(self._global_events, cutoff)
            self._evict_idle_locked(cutoff)

            if len(self._global_events) >= GLOBAL_RATE_LIMIT_REQUESTS:
                return "global"

            events = self._events.setdefault(client_ip, deque())
            if len(events) >= RATE_LIMIT_REQUESTS:
                return "per_ip"

            events.append(current)
            self._global_events.append(current)
            return None

    def allow(self, client_ip: str, *, now: float | None = None) -> bool:
        return self.decision(client_ip, now=now) is None

    def clear(self) -> None:
        with self._lock:
            self._events.clear()
            self._global_events.clear()


_rate_limiter = _LiveScoringRateLimiter()


def _client_ip(request: Request) -> str:
    # Railway's edge proxy provides X-Forwarded-For. The public spoof test
    # verifies which hop is authoritative before relying on this in production.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        first = forwarded.split(",", 1)[0].strip()
        if first:
            return first

    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()

    return request.client.host if request.client else "unknown"


class LiveScoringGuardRoute(APIRoute):
    def get_route_handler(self):
        original_handler = super().get_route_handler()

        async def guarded_handler(request: Request):
            body = await request.body()
            if len(body) > MAX_REQUEST_BODY_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": (
                            "request body exceeds the 16 KiB limit for "
                            "POST /score/transaction"
                        )
                    },
                )

            client_ip = _client_ip(request)
            rate_limit = _rate_limiter.decision(client_ip)
            if rate_limit == "global":
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": (
                            "global rate limit exceeded for POST /score/transaction: "
                            "maximum 300 requests per minute total"
                        )
                    },
                )
            if rate_limit == "per_ip":
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": (
                            "rate limit exceeded for POST /score/transaction: "
                            "maximum 30 requests per minute per client IP"
                        )
                    },
                )

            return await original_handler(request)

        return guarded_handler


router = APIRouter(
    prefix="/score",
    tags=["live-scoring"],
    route_class=LiveScoringGuardRoute,
)


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