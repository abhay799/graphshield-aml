from __future__ import annotations

import json
from pathlib import Path


ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)


def test_phase7_certification_exists():

    path = (
        ROOT
        / "reports"
        / "final"
        / "phase7_artifact_freeze.json"
    )

    assert path.exists()


def test_phase7_certification_status():

    path = (
        ROOT
        / "reports"
        / "final"
        / "phase7_artifact_freeze.json"
    )

    payload = json.loads(
        path.read_text(
            encoding="utf-8-sig"
        )
    )

    assert payload[
        "status"
    ] == "CERTIFIED"


def test_phase1_6_read_only_governance():

    path = (
        ROOT
        / "reports"
        / "final"
        / "phase7_artifact_freeze.json"
    )

    payload = json.loads(
        path.read_text(
            encoding="utf-8-sig"
        )
    )

    assert payload[
        "governance"
    ][
        "phase1_6_artifacts"
    ] == "read_only"

    assert payload[
        "governance"
    ][
        "human_review_required"
    ] is True
