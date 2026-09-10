from __future__ import annotations

from typing import Any

import httpx


class GraphShieldAPIClient:

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        timeout: float = 60.0,
    ) -> None:

        self.base_url = (
            base_url.rstrip("/")
        )

        self.timeout = timeout


    def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> Any:

        url = (
            f"{self.base_url}{path}"
        )

        try:

            response = httpx.request(
                method,
                url,
                timeout=self.timeout,
                **kwargs,
            )

        except httpx.RequestError as error:

            raise RuntimeError(
                "Unable to connect to GraphShield API. "
                "Make sure FastAPI is running on "
                "http://127.0.0.1:8000"
            ) from error


        if response.status_code >= 400:

            try:
                detail = response.json()
            except Exception:
                detail = response.text

            raise RuntimeError(
                f"API request failed "
                f"({response.status_code}): "
                f"{detail}"
            )


        return response.json()


    def health(
        self,
    ) -> dict[str, Any]:

        return self._request(
            "GET",
            "/health",
        )


    def governance(
        self,
    ) -> dict[str, Any]:

        return self._request(
            "GET",
            "/governance",
        )


    def list_cases(
        self,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:

        return self._request(
            "GET",
            "/cases",
            params={
                "limit":
                    limit,

                "offset":
                    offset,
            },
        )


    def get_case(
        self,
        case_id: str,
    ) -> dict[str, Any]:

        return self._request(
            "GET",
            f"/cases/{case_id}",
        )


    def overview(
        self,
        case_id: str,
    ) -> dict[str, Any]:

        return self._request(
            "GET",
            f"/cases/{case_id}/overview",
        )


    def paths(
        self,
        case_id: str,
    ) -> dict[str, Any]:

        return self._request(
            "GET",
            f"/cases/{case_id}/paths",
        )


    def history(
        self,
        case_id: str,
    ) -> dict[str, Any]:

        return self._request(
            "GET",
            f"/cases/{case_id}/history",
        )


    def snapshot(
        self,
        case_id: str,
    ) -> dict[str, Any]:

        return self._request(
            "GET",
            f"/cases/{case_id}/snapshot",
        )


    def search_evidence(
        self,
        case_id: str,
        query: str,
        top_k: int = 5,
    ) -> dict[str, Any]:

        return self._request(
            "POST",
            (
                f"/cases/{case_id}"
                "/evidence/search"
            ),
            json={
                "query":
                    query,

                "top_k":
                    top_k,
            },
        )


    def search_policy(
        self,
        query: str,
        top_k: int = 5,
        jurisdiction: str | None = None,
    ) -> dict[str, Any]:

        return self._request(
            "POST",
            "/policy/search",
            json={
                "query":
                    query,

                "top_k":
                    top_k,

                "jurisdiction":
                    jurisdiction,
            },
        )


    # ========================================================
    # ANALYST WORKFLOW
    # ========================================================

    def get_case_state(
        self,
        case_id: str,
    ) -> dict[str, Any]:

        return self._request(
            "GET",
            (
                f"/analyst/cases/"
                f"{case_id}/state"
            ),
        )


    def update_case_state(
        self,
        case_id: str,
        review_status: str,
        analyst_note: str | None,
        actor: str,
    ) -> dict[str, Any]:

        return self._request(
            "PUT",
            (
                f"/analyst/cases/"
                f"{case_id}/state"
            ),
            json={
                "review_status":
                    review_status,

                "analyst_note":
                    analyst_note,

                "actor":
                    actor,
            },
        )


    def audit_history(
        self,
        case_id: str,
        limit: int = 100,
    ) -> dict[str, Any]:

        return self._request(
            "GET",
            (
                f"/analyst/cases/"
                f"{case_id}/audit"
            ),
            params={
                "limit":
                    limit,
            },
        )


    def case_graph(
        self,
        case_id: str,
        max_edges: int = 250,
    ) -> dict[str, Any]:

        return self._request(
            "GET",
            f"/cases/{case_id}/graph",
            params={
                "max_edges":
                    max_edges,
            },
        )


    def case_intelligence(
        self,
        case_id: str,
        question: str | None = None,
        evidence_top_k: int = 5,
        include_policy: bool = True,
        policy_top_k: int = 5,
        jurisdiction: str | None = None,
    ) -> dict[str, Any]:

        return self._request(
            "POST",
            (
                f"/cases/{case_id}"
                "/intelligence"
            ),
            json={
                "question":
                    question,

                "evidence_top_k":
                    evidence_top_k,

                "include_policy":
                    include_policy,

                "policy_top_k":
                    policy_top_k,

                "jurisdiction":
                    jurisdiction,
            },
        )
