from __future__ import annotations

import sys

from scripts.live_scoring.bootstrap_case_queue_redis import parse_args


def test_bootstrap_namespace_matches_live_scoring_default(monkeypatch):
    monkeypatch.delenv("GS_LIVE_SCORING_NAMESPACE", raising=False)
    monkeypatch.setattr(sys, "argv", ["bootstrap_case_queue_redis.py"])
    args = parse_args()
    assert args.namespace == "gs:live:scoring:v1"


def test_bootstrap_namespace_honors_shared_env(monkeypatch):
    monkeypatch.setenv("GS_LIVE_SCORING_NAMESPACE", "gs:test:shared-live:v1")
    monkeypatch.setattr(sys, "argv", ["bootstrap_case_queue_redis.py"])
    args = parse_args()
    assert args.namespace == "gs:test:shared-live:v1"
