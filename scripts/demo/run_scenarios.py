#!/usr/bin/env python3
"""Fail-closed deterministic verification for documented demo scenarios."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

import polars as pl

REPO_ROOT = Path(__file__).resolve().parents[2]
CASE_QUEUE_PATH = REPO_ROOT / "data" / "processed" / "cases" / "case_queue.parquet"
CASE_PATHS_PATH = REPO_ROOT / "data" / "processed" / "cases" / "case_paths.jsonl"
CASE_BUNDLES_DIR = REPO_ROOT / "data" / "processed" / "cases" / "bundles"
GRAPH_DIR = REPO_ROOT / "data" / "processed" / "graph"
OUTPUT_PATH = REPO_ROOT / "docs" / "demo" / "scenario_run_output.json"
MANIFEST_PATH = REPO_ROOT / "docs" / "evidence" / "EVIDENCE_MANIFEST.json"
QUEUE_CASE_ID = "CASE_IBM_LI_SMALL_4310302"
REVERSE_PATH_CASE_ID = "CASE_IBM_LI_SMALL_4417139"


def relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def assert_exists(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Missing required {label}: {relative(path)}")


def read_case_queue() -> pl.DataFrame:
    assert_exists(CASE_QUEUE_PATH, "case queue")
    return pl.read_parquet(CASE_QUEUE_PATH).sort(["risk_rank", "case_id"])


def read_case_paths() -> list[dict[str, Any]]:
    assert_exists(CASE_PATHS_PATH, "case path catalog")
    with CASE_PATHS_PATH.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def bundle_for(case_id: str) -> dict[str, Any]:
    path = CASE_BUNDLES_DIR / f"{case_id}.json"
    assert_exists(path, f"case bundle for {case_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def result(scenario_id: str, title: str, source: str, expected: dict[str, Any], checkpoints: dict[str, Any], checks: dict[str, bool]) -> dict[str, Any]:
    failed_checks = sorted(name for name, passed in checks.items() if not passed)
    return {"id": scenario_id, "title": title, "status": "PASS" if not failed_checks else "FAIL", "source": source,
            "expected": expected, "checkpoints": checkpoints, "failed_checks": failed_checks,
            "provenance": "LOCAL READ-ONLY ARTIFACT"}


def scenario_queue() -> dict[str, Any]:
    queue = read_case_queue()
    columns = ["risk_rank", "case_id", "transaction_id", "from_account_key", "to_account_key", "case_status", "review_capacity"]
    top_rows = queue.head(5).select(columns).to_dicts()
    first = top_rows[0] if top_rows else {}
    checkpoints = {"queue_rows": int(queue.height), "top_case_ids": [row["case_id"] for row in top_rows],
                   "first_case_id": first.get("case_id"), "first_rank": first.get("risk_rank"),
                   "first_status": first.get("case_status"), "first_review_capacity": first.get("review_capacity"),
                   "first_transaction_id": first.get("transaction_id"), "first_from_account_key": first.get("from_account_key"),
                   "first_to_account_key": first.get("to_account_key")}
    checks = {"queue_has_rows": queue.height > 0, "first_case_id": first.get("case_id") == QUEUE_CASE_ID,
              "risk_rank": first.get("risk_rank") == 1, "case_status": first.get("case_status") == "OPEN",
              "review_capacity": first.get("review_capacity") == 0.01,
              "transaction_id_non_empty": bool(str(first.get("transaction_id") or "").strip()),
              "from_account_key_non_empty": bool(str(first.get("from_account_key") or "").strip()),
              "to_account_key_non_empty": bool(str(first.get("to_account_key") or "").strip())}
    return result("GS-AML-001", "Queue triage and analyst prioritization", relative(CASE_QUEUE_PATH),
                  {"case_id": QUEUE_CASE_ID, "risk_rank": 1, "case_status": "OPEN", "review_capacity": 0.01}, checkpoints, checks)


def scenario_graph_path() -> dict[str, Any]:
    match = next((row for row in read_case_paths() if row.get("case_id") == REVERSE_PATH_CASE_ID), {})
    checkpoints = {"case_id": match.get("case_id"), "transaction_id": match.get("transaction_id"),
                   "reverse_prior_path": match.get("reverse_prior_path"), "closes_multi_hop_cycle": match.get("closes_multi_hop_cycle"),
                   "supporting_edges_strictly_prior": match.get("supporting_edges_strictly_prior"), "max_search_depth": match.get("max_search_depth")}
    checks = {"case_exists": bool(match), "transaction_id_matches_anchor": match.get("transaction_id") == "IBM_LI_SMALL_4417139",
              "reverse_prior_path_non_empty": bool(match.get("reverse_prior_path")),
              "closes_multi_hop_cycle": match.get("closes_multi_hop_cycle") is True,
              "supporting_edges_strictly_prior": match.get("supporting_edges_strictly_prior") is True}
    return result("GS-AML-002", "Graph evidence and reverse-prior path review", relative(CASE_PATHS_PATH),
                  {"case_id": REVERSE_PATH_CASE_ID, "transaction_id": "IBM_LI_SMALL_4417139", "reverse_prior_path_non_empty": True,
                   "closes_multi_hop_cycle": True, "supporting_edges_strictly_prior": True}, checkpoints, checks)


def graph_artifact(path: Path, essential_columns: set[str]) -> tuple[dict[str, Any], dict[str, bool]]:
    if not path.exists():
        return {"exists": False, "rows": 0, "columns": []}, {"exists": False, "rows_non_empty": False, "essential_columns": False}
    frame = pl.read_parquet(path)
    columns = sorted(frame.columns)
    return {"exists": True, "rows": int(frame.height), "columns": columns}, {
        "exists": True, "rows_non_empty": frame.height > 0, "essential_columns": essential_columns.issubset(columns)}


def scenario_graph_motif() -> dict[str, Any]:
    communities, community_checks = graph_artifact(GRAPH_DIR / "suspicious_communities_v1.parquet", {"community_id", "member_count", "high_risk_seed_count"})
    motifs, motif_checks = graph_artifact(GRAPH_DIR / "account_motif_intelligence_v1.parquet", {"account_key", "has_any_motif_signal", "is_in_suspicious_community"})
    checkpoints = {"context_only": True, "suspicious_communities": communities, "account_motif_intelligence": motifs}
    checks = {f"communities_{name}": passed for name, passed in community_checks.items()}
    checks.update({f"motifs_{name}": passed for name, passed in motif_checks.items()})
    checks["context_only"] = True
    return result("GS-AML-003", "Suspicious community and motif context", relative(GRAPH_DIR),
                  {"suspicious_communities_rows": ">0", "motif_rows": ">0", "context_only": True}, checkpoints, checks)


def scenario_bundle_review_gate() -> dict[str, Any]:
    bundle = bundle_for(QUEUE_CASE_ID)
    metadata, policy = bundle.get("case_metadata", {}), bundle.get("investigation_policy", {})
    checkpoints = {"case_id": metadata.get("case_id"), "decision": policy.get("decision"),
                   "autonomous_account_block": policy.get("autonomous_account_block"),
                   "autonomous_case_closure": policy.get("autonomous_case_closure"), "ground_truth_exposed": policy.get("ground_truth_exposed")}
    checks = {"case_id": metadata.get("case_id") == QUEUE_CASE_ID, "decision": policy.get("decision") == "analyst_review_required",
              "autonomous_account_block": policy.get("autonomous_account_block") is False,
              "autonomous_case_closure": policy.get("autonomous_case_closure") is False,
              "ground_truth_exposed": policy.get("ground_truth_exposed") is False}
    return result("GS-AML-004", "Human review gate from the case bundle", relative(CASE_BUNDLES_DIR / f"{QUEUE_CASE_ID}.json"),
                  {"case_id": QUEUE_CASE_ID, "decision": "analyst_review_required", "autonomous_account_block": False,
                   "autonomous_case_closure": False, "ground_truth_exposed": False}, checkpoints, checks)


SCENARIOS: dict[str, Callable[[], dict[str, Any]]] = {"GS-AML-001": scenario_queue, "GS-AML-002": scenario_graph_path,
                                                       "GS-AML-003": scenario_graph_motif, "GS-AML-004": scenario_bundle_review_gate}


def execute(scenario_id: str) -> dict[str, Any]:
    try:
        return SCENARIOS[scenario_id]()
    except Exception as error:
        return {"id": scenario_id, "title": scenario_id, "status": "FAIL", "source": None, "expected": {}, "checkpoints": {},
                "failed_checks": [f"verification_error: {type(error).__name__}: {error}"], "provenance": "LOCAL READ-ONLY ARTIFACT"}


def run_all() -> dict[str, Any]:
    scenarios = [execute(scenario_id) for scenario_id in SCENARIOS]
    return {"repo_root": ".", "provenance": "LOCAL READ-ONLY ARTIFACT", "scenario_count": len(scenarios),
            "all_passed": all(item["status"] == "PASS" for item in scenarios), "scenarios": scenarios}


def validate_manifest() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    status_classes, provenance_classes = set(manifest["status_classes"]), set(manifest["provenance_classes"])
    for entry in manifest["evidence"]:
        unknown = set(entry["classification"]) - provenance_classes
        if unknown:
            raise ValueError(f"{entry['name']}: undeclared provenance {sorted(unknown)}")
        if "status" in entry and entry["status"] not in status_classes:
            raise ValueError(f"{entry['name']}: undeclared status {entry['status']}")
        reference = entry.get("file")
        if reference and not reference.startswith("data/") and not (REPO_ROOT / reference).exists():
            raise FileNotFoundError(f"{entry['name']}: missing tracked evidence {reference}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run fail-closed deterministic GraphShield AML demo verification.")
    parser.add_argument("--list", action="store_true", help="List scenario IDs")
    parser.add_argument("--validate-manifest", action="store_true", help="Validate evidence manifest taxonomy and tracked references")
    parser.add_argument("--scenario", choices=["all", *SCENARIOS], default="all", help="Scenario to run")
    args = parser.parse_args()
    if args.list:
        print("\n".join(SCENARIOS))
        return 0
    if args.validate_manifest:
        validate_manifest(); print("Evidence manifest validation: PASS"); return 0
    if args.scenario == "all":
        payload = run_all()
        OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"provenance": payload["provenance"], "scenario_count": payload["scenario_count"],
                          "all_passed": payload["all_passed"], "output_path": relative(OUTPUT_PATH)}, indent=2))
        for scenario in payload["scenarios"]:
            print(f"{scenario['id']}: {scenario['title']} -> {scenario['status']}")
        return 0 if payload["all_passed"] else 1
    payload = execute(args.scenario)
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
