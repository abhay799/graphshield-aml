from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRAINER = PROJECT_ROOT / "src" / "temporal" / "train_tgn.py"
CONFIG_DIR = PROJECT_ROOT / "configs" / "v2" / "training"


def load_profile(name: str) -> dict:
    path = CONFIG_DIR / f"tgn_{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Profile not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    config["_path"] = str(path)
    return config


def build_env(profile: str, config: dict) -> tuple[dict, dict]:
    env = os.environ.copy()

    run_name = str(config.get("profile", f"tgn_{profile}"))
    model_dir = PROJECT_ROOT / "models" / "v2" / run_name
    report_dir = PROJECT_ROOT / "reports" / "v2" / "training" / run_name
    prediction_dir = (
        PROJECT_ROOT / "data" / "processed" / "modeling" / "v2" / run_name
    )
    checkpoint = model_dir / "tgn_risk.pt"

    overrides = {
        "GS_TGN_MODEL_DIR": str(model_dir),
        "GS_TGN_REPORT_DIR": str(report_dir),
        "GS_TGN_PREDICTION_DIR": str(prediction_dir),
        "GS_TGN_CHECKPOINT_PATH": str(checkpoint),
        "PYTHONHASHSEED": str(config.get("seed", 42)),
    }

    for key, value in (config.get("env") or {}).items():
        overrides[str(key)] = str(value)

    certified_v1 = (PROJECT_ROOT / "models" / "tgn_risk_v1.pt").resolve()
    if checkpoint.resolve() == certified_v1:
        raise RuntimeError("Refusing to overwrite certified v1 TGN checkpoint.")

    env.update(overrides)
    return env, overrides


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run GraphShield v2 TGN training from a reproducible profile."
    )
    parser.add_argument("profile", choices=["smoke", "full"])
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print the run configuration without importing/running TGN.",
    )
    args = parser.parse_args()

    config = load_profile(args.profile)
    env, overrides = build_env(args.profile, config)

    print("=" * 72)
    print("GraphShield v2 TGN profile runner")
    print("=" * 72)
    print(f"PROFILE={config.get('profile', args.profile)}")
    print(f"CONFIG={config['_path']}")
    print(f"DEVICE_REQUEST={config.get('device', 'auto')}")
    for key in sorted(overrides):
        print(f"{key}={overrides[key]}")

    if args.dry_run:
        print("GRAPHSHIELD_TGN_PROFILE_DRY_RUN=PASS")
        return 0

    if not TRAINER.exists():
        raise FileNotFoundError(f"Trainer not found: {TRAINER}")

    completed = subprocess.run(
        [sys.executable, str(TRAINER)],
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
    )
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
