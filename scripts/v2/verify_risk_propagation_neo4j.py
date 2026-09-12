from __future__ import annotations

import os
from pathlib import Path

import polars as pl
from neo4j import GraphDatabase


PROJECT_ROOT = Path(__file__).resolve().parents[2]
INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "graph"
    / "account_risk_propagation_v1.parquet"
)
ENV_PATH = PROJECT_ROOT / "infra" / "v2" / ".env"
VERSION = "account_risk_propagation_v1"


def parse_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def resolve_auth() -> tuple[str, str, str]:
    file_env = parse_dotenv(ENV_PATH)

    uri = (
        os.environ.get("NEO4J_URI")
        or os.environ.get("GRAPHSHIELD_NEO4J_URI")
        or file_env.get("NEO4J_URI")
        or file_env.get("GRAPHSHIELD_NEO4J_URI")
        or "bolt://127.0.0.1:7687"
    )

    user = (
        os.environ.get("NEO4J_USER")
        or os.environ.get("NEO4J_USERNAME")
        or os.environ.get("GRAPHSHIELD_NEO4J_USER")
        or file_env.get("NEO4J_USER")
        or file_env.get("NEO4J_USERNAME")
        or file_env.get("GRAPHSHIELD_NEO4J_USER")
    )

    password = (
        os.environ.get("NEO4J_PASSWORD")
        or os.environ.get("GRAPHSHIELD_NEO4J_PASSWORD")
        or file_env.get("NEO4J_PASSWORD")
        or file_env.get("GRAPHSHIELD_NEO4J_PASSWORD")
    )

    auth = os.environ.get("NEO4J_AUTH") or file_env.get("NEO4J_AUTH")

    if auth and "/" in auth:
        auth_user, auth_password = auth.split("/", 1)
        user = user or auth_user
        password = password or auth_password

    user = user or "neo4j"

    if not password:
        raise RuntimeError(
            "Neo4j password not found. Load NEO4J_AUTH in this PowerShell session first."
        )

    return uri, user, password


def main() -> None:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(INPUT_PATH)

    expected = pl.read_parquet(INPUT_PATH, columns=["account_key"]).height

    uri, user, password = resolve_auth()
    driver = GraphDatabase.driver(uri, auth=(user, password))

    try:
        driver.verify_connectivity()
        with driver.session(database="neo4j") as session:
            record = session.run(
                """
                MATCH (n:Account)
                WHERE n.propagation_version = $version
                RETURN count(n) AS loaded
                """,
                version=VERSION,
            ).single()

        loaded = int(record["loaded"])
    finally:
        driver.close()

    print(f"EXPECTED={expected}")
    print(f"NEO4J_LOADED={loaded}")

    if loaded == expected:
        print("PROPAGATION_LOAD_COUNT=COMPLETE")
    else:
        print("PROPAGATION_LOAD_COUNT=INCOMPLETE")


if __name__ == "__main__":
    main()
