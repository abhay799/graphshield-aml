from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_REQUIRED_PATHS = (
    "models/lightgbm_graph_v1.joblib",
    "models/probability_calibrator_graph_v1.joblib",
    "models/v2/phase10_fusion_calibrator_v1.joblib",
    "reports/v2/phase13/phase13_final_certification_v1_report.json",
)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value.")


def _required_paths_from_env() -> tuple[str, ...]:
    raw = os.getenv("GS_READINESS_REQUIRED_PATHS", "").strip()
    if not raw:
        return DEFAULT_REQUIRED_PATHS
    values = tuple(item.strip() for item in raw.split(",") if item.strip())
    if not values:
        return DEFAULT_REQUIRED_PATHS
    return values


@dataclass(frozen=True)
class Phase14RuntimeConfig:
    environment: str
    release: str
    commit_sha: str
    region: str
    instance_id: str
    strict_readiness: bool
    enable_hsts: bool
    required_paths: tuple[str, ...]

    def public_metadata(self) -> dict[str, Any]:
        return {
            "environment": self.environment,
            "release": self.release,
            "commit_sha": self.commit_sha,
            "region": self.region,
            "instance_id": self.instance_id,
            "strict_readiness": self.strict_readiness,
        }


def get_runtime_config() -> Phase14RuntimeConfig:
    return Phase14RuntimeConfig(
        environment=os.getenv("GS_ENVIRONMENT", "local"),
        release=os.getenv("GS_RELEASE", "phase14-dev"),
        commit_sha=os.getenv("GS_COMMIT_SHA", "unknown"),
        region=os.getenv("GS_REGION", "local"),
        instance_id=os.getenv("GS_INSTANCE_ID", "local-instance"),
        strict_readiness=_env_bool("GS_STRICT_READINESS", True),
        enable_hsts=_env_bool("GS_ENABLE_HSTS", False),
        required_paths=_required_paths_from_env(),
    )


def evaluate_readiness(
    config: Phase14RuntimeConfig,
    *,
    project_root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    missing: list[str] = []

    for rel in config.required_paths:
        path = project_root / rel
        exists = path.exists()
        checks.append(
            {
                "name": rel,
                "status": "pass" if exists else "fail",
            }
        )
        if not exists:
            missing.append(rel)

    ready = (not config.strict_readiness) or not missing

    return {
        "status": "ready" if ready else "not_ready",
        "ready": ready,
        "strict_readiness": config.strict_readiness,
        "checks": checks,
        "missing_required_paths": missing,
        "governance": {
            "certified_artifacts_are_read_only": True,
            "readiness_check_does_not_modify_artifacts": True,
            "readiness_check_does_not_trigger_training": True,
        },
    }


def install_enterprise_security(app: FastAPI) -> None:
    config = get_runtime_config()

    @app.middleware("http")
    async def phase14_enterprise_headers(
        request: Request,
        call_next,
    ):
        response = await call_next(request)
        response.headers.setdefault(
            "Permissions-Policy",
            "camera=(), microphone=(), geolocation=()",
        )
        response.headers.setdefault(
            "X-Permitted-Cross-Domain-Policies",
            "none",
        )
        response.headers.setdefault(
            "Cross-Origin-Resource-Policy",
            "same-site",
        )
        if config.enable_hsts:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response
