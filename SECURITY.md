# Security policy

This repository is a research and portfolio project for AML investigation support. It is not a deployed banking product and should not be treated as a live production security boundary.

## How to report a security issue

If you believe you have found a sensitive code-level issue, use the repository’s GitHub Security reporting flow if it is available. If a private reporting path is not available, do not disclose the issue publicly and wait for a maintainer to provide a safe handling path.

## Do not disclose

- secrets or credentials
- customer or regulated-data examples
- local environment values from `.env` or other config files
- model artifacts, generated data, or private runtime state

## Scope and boundaries

This project includes code-level controls, validation, and guardrails for research use. Those are not equivalent to live operational security controls for a regulated financial system.

The repository does not claim production security certification, external cloud hardening approval, or live-system regulatory readiness. Security claims must stay aligned with the project’s evidence and limitations documentation.

## Operational reality

- This is not a deployed banking environment.
- The repository is not a live production compliance engine.
- Human investigator review remains required for any investigation outcome or external action.
- Security concerns should be handled conservatively and proportionally to the project’s research/portfolio scope.
