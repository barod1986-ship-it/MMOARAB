# REV15 — V1 evidence-closure gate

Audit date: 2026-08-19

## Why REV15 exists

REV14 closed the last known source-side privacy blocker, but the next real-evidence audit found a release-gate gap: `productionRoleSfxClassifierReady` and `productionInpainterRuntimeReady` existed in `release-control/release-state.json` yet were not independently enforced by `check:controlled-release-ready` for `private-v1` / `public-v1`.

That meant a future operator could theoretically complete the other immutable evidence while leaving those two production-readiness flags false without the controlled-release verifier deriving and rejecting the mismatch.

## Freeze v3

The first real production freeze has not been created yet, so REV15 strengthens the freeze format before any production artifact depends on it. `production-profile-freeze-v4-source-and-release-evidence-bound` retains the REV11 dependency-lock binding and additionally carries:

- `policyRevision` and `candidatePlanSha256`;
- `roleSafetyQualification`, including the exact production role-classifier revision, protected-SFX recall, the exact-zero destructive-edit fields, and independently annotated SFX page count;
- `inpaintingQualification`, including the selected inpainting candidate, selected-candidate human score, critical failures, reviewed-page count, and selected-review critical failures.

A freeze is structurally invalid unless it is candidate-plan-bound, has perfect protected-SFX recall, exact-zero destructive SFX outcomes, at least ten independent SFX pages, and zero critical inpainting failures. The release verifier additionally binds the freeze to the active `benchmark-thresholds-v3` policy bytes and active `candidate-plan-v3` bytes.

## Derived V1 readiness

For `private-v1` and `public-v1`, `verify_controlled_release_ready.py` now derives:

- role/SFX production readiness from the active policy plus the frozen `roleSafetyQualification` evidence;
- inpainting production readiness from the active policy threshold, frozen winner, frozen selected-artifact pin, human score/review coverage, and zero critical failures.

The derived values must exactly match `productionRoleSfxClassifierReady` and `productionInpainterRuntimeReady`. A JSON flag alone cannot satisfy the gate.

## Full V1 dry audit

`release-state.json` intentionally remains `developer-preview`. To expose future V1 blockers without mutating that state, the verifier now accepts `--target-class` and package.json provides:

```bash
npm run check:v1-evidence-closure
```

This evaluates the current tree as `private-v1`. It is an audit only: it does not rewrite release state, create evidence, generate a freeze, or promote an artifact.

## Current execution result

The available environment still cannot resolve the npm, PyPI, or Node distribution hosts, so registry-generated dependency locks cannot be produced here. No lockfile, model artifact, human review, benchmark pass, smoke record, native artifact, profile fingerprint, controlled manifest, or production freeze is fabricated.

The private-V1 dry audit therefore remains expected to fail until the real runner/evidence path is executed. In this REV15 environment it reports **14 concrete blockers**, including the two dependency locks, controlled manifest/profile privacy, browser and Engine smoke, the real Gate D freeze, role/SFX qualification, selected-inpainting qualification, native Engine support, and controlled V1 release metadata. Its purpose is to surface the complete set rather than hide later V1 blockers behind the current `developer-preview` class.
