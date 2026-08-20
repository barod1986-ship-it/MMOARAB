# REV23 — Repository Bootstrap Audit + First Real Run Resume Ledger

REV23 closes three source-side production-operations defects found after REV22:

1. GitHub REST collection endpoints are now fully paginated. The infrastructure audit no longer assumes that runners, environments, environment variables, or environment secrets fit on their first API page.
2. `production-qualification-promotion`, which is used by the qualification-evidence promotion workflow, is now part of the protected-environment contract and therefore cannot silently escape the readiness audit.
3. The audit token permission contract now includes `Actions:read` in addition to `Administration:read` and `Environments:read`, matching the GitHub endpoints used for repository environments, runners, environment variables, and environment secret names.

REV23 also adds `scripts/first_real_run_handoff.py`. It creates a content-addressed operator resume ledger outside the tracked source tree. The ledger is bound to the exact production-execution contract, accepts only the canonical stage order, requires explicit review acknowledgement at manual review boundaries, and enforces minimum recorded workflow-run IDs for automated stages. It is operational state only and is never accepted as qualification, smoke, signing, or release evidence.

The ledger does not weaken existing workflow provenance checks. Promotion, controlled assembly, smoke and finalization workflows continue to verify their referenced run IDs, source identities and artifact hashes independently.


REV25 supersedes manual source-SHA entry at ledger initialization: the ledger now requires `--onboarding-config` and inherits the immutable repository ID/default branch/source head/workflow-set binding from the sealed REV25 bootstrap config.
