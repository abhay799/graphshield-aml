from pathlib import Path


def test_hpa_and_pdb_exist() -> None:
    hpa = Path("infra/phase14/k8s/hpa.yaml").read_text(
        encoding="utf-8"
    )
    pdb = Path("infra/phase14/k8s/pdb.yaml").read_text(
        encoding="utf-8"
    )

    assert "minReplicas: 2" in hpa
    assert "maxReplicas: 6" in hpa
    assert "averageUtilization: 70" in hpa
    assert "minAvailable: 1" in pdb


def test_service_account_token_is_not_mounted() -> None:
    sa = Path(
        "infra/phase14/k8s/serviceaccount.yaml"
    ).read_text(encoding="utf-8")
    deployment = Path(
        "infra/phase14/k8s/deployment.yaml"
    ).read_text(encoding="utf-8")

    assert "automountServiceAccountToken: false" in sa
    assert "serviceAccountName: graphshield-api" in deployment
    assert "seccompProfile:" in deployment
    assert "type: RuntimeDefault" in deployment


def test_zero_unavailable_rolling_update_contract() -> None:
    deployment = Path(
        "infra/phase14/k8s/deployment.yaml"
    ).read_text(encoding="utf-8")

    assert "maxUnavailable: 0" in deployment
    assert "maxSurge: 1" in deployment
    assert "startupProbe:" in deployment
    assert "topologySpreadConstraints:" in deployment
