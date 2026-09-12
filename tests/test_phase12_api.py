from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.phase12_routes import router


def test_phase12_tool_catalog_is_read_only():
    app = FastAPI()
    app.include_router(router)

    response = TestClient(
        app
    ).get(
        "/phase12/tools"
    )

    assert response.status_code == 200

    body = response.json()

    assert body["mode"] == "read_only"
    assert body[
        "human_review_required"
    ] is True

    prohibited = {
        "block_account",
        "close_case",
        "file_sar",
        "file_str",
        "shell",
        "python",
    }

    assert prohibited.isdisjoint(
        {
            item.lower()
            for item in body["tools"]
        }
    )
