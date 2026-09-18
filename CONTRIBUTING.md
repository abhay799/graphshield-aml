# Contributing to GraphShield AML

This repository is a research and portfolio project for AML investigation support. Keep changes small, scoped, and evidence-backed.

## Local setup

Use the documented local workflow before proposing changes:

- [docs/RUNNING.md](docs/RUNNING.md)

## Branch and PR expectations

- Prefer small, reviewable changes over broad refactors.
- Keep implementation changes aligned with the existing Phase 1–15 architecture.
- Do not broaden scope into redesigns or unsupported production claims.
- Open PRs that clearly explain scope, validation performed, and any evidence/provenance impact.

## Validation expected before submission

Run the minimum checks relevant to your change and record the result in the PR:

- affected tests or validation script(s)
- Python compile check for changed modules when applicable
- `git diff --check`
- a quick review of any documentation or evidence file changed

## Commit hygiene

- Do not commit secrets, local `.env` values, customer data, model binaries, generated data artifacts, or cached runtime state.
- Keep generated/demo/cloud artifacts out of the committed patch unless they are explicitly required as project evidence.
- Keep review artifacts separate from source changes when possible.

## Claim and evidence boundaries

- Preserve human-investigator authority over investigation outcome and disposition.
- Do not add claims of autonomous enforcement, production deployment, regulatory filing, or legal conclusion.
- Treat historical reports and synthetic data as supporting evidence, not live production proof.
- Any documentation claim must be backed by repository evidence or a clearly labeled limitation statement.

## Documentation

When updating docs, prefer reused repository evidence over broad statements. Keep descriptions consistent with:

- [README.md](README.md)
- [docs/LIMITATIONS.md](docs/LIMITATIONS.md)
- [docs/VALIDATION.md](docs/VALIDATION.md)
- [docs/architecture/SAFETY_INVARIANTS.md](docs/architecture/SAFETY_INVARIANTS.md)
