from __future__ import annotations

import os

from fastapi import FastAPI, Request
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.cors import CORSMiddleware


DEFAULT_ALLOWED_HOSTS = '127.0.0.1,localhost,api,testserver'


def install_security(app: FastAPI) -> None:
    raw = os.getenv('GS_ALLOWED_HOSTS', DEFAULT_ALLOWED_HOSTS)
    allowed_hosts = [host.strip() for host in raw.split(',') if host.strip()]

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=allowed_hosts,
    )

    # CORS middleware
    allowed_origins_raw = os.getenv('GS_ALLOWED_ORIGINS', '')
    allowed_origins = [origin.strip() for origin in allowed_origins_raw.split(',') if origin.strip()]
    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type", "Accept"],
            allow_credentials=False,
        )

    @app.middleware('http')
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'DENY')
        response.headers.setdefault('Referrer-Policy', 'no-referrer')
        response.headers.setdefault('Cache-Control', 'no-store')
        return response