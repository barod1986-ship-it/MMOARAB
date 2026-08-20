# REV12 — Real qualification execution attempt

Attempt date: 2026-08-19

## Result

The real production qualification was **attempted but not completed in this execution environment**. No production freeze was created, and no model/corpus/review evidence was fabricated.

The source qualification path remains fail-closed. A direct `prepare` attempt using the shipped corpus template failed before network acquisition because the template is intentionally unsealed and its source-registry digest is not valid production evidence.

## Verified locally

- Engine tests: 113/113 passed when executed from `engine/`.
- Phase 9 contracts: 153/153 passed.
- Release-ready regression smoke: 6/6 passed.
- Source integrity passed before REV12 changes.
- Acquisition registry resolves the active topology to exactly 7 automated primary-source artifacts plus 2 manual-derived artifacts (LaMa/AOT).
- Manual artifact policy validation passed.

## Environment blockers observed

The available execution container had Node 22.16.0, npm 10.9.2, Python 3.13.5 and uv 0.10.0 rather than the pinned qualification toolchain. Direct outbound DNS/socket access was unavailable, so registry-backed npm/uv resolution and the seven primary-source downloads could not be performed here. The only connected GitHub repository was not this manga-translator source tree, so the GitHub Actions workflow could not truthfully be dispatched against this project.

The archive also contains only corpus/review templates, not an operator-authorized production corpus, final artifact reviews, reviewed LaMa/AOT ONNX packages, or a sealed benchmark review. Those inputs must remain externally supplied real evidence.

## New diagnostic probe

`engine/scripts/probe_real_qualification_readiness.py` records the exact pinned-toolchain match, DNS/TCP reachability for required primary endpoints, source lock/freeze presence and optional operator-input-root inventory. Its output is explicitly diagnostic and cannot create a freeze, download artifacts, or mutate operator inputs.

Example on the protected runner:

```bash
python engine/scripts/probe_real_qualification_readiness.py \
  --input-root "$MTE_QUALIFICATION_INPUT_ROOT" \
  --output /secure/qualification/readiness.json \
  --strict
```

A passing readiness probe does not replace the `prepare -> sealed human review -> execute` qualification workflow. It only prevents wasting a protected run on an obviously incomplete runner/input setup.

## Release status

V1 remains blocked on the first real passing qualification execution and resulting lock-bound `production-profile-freeze.json`. REV12 is an execution-attempt/readiness-hardening revision, **not** a production qualification pass.
