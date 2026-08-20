# Dependency lock bootstrap — V1 reproducibility gate

Audit date: 2026-08-19

## Decision

Dependency locks must be produced by real package-registry resolution and then committed as source. They must never be hand-written, replaced by empty placeholders, or inferred from the currently installed environment.

The canonical release toolchain is recorded once in `release-control/toolchain.json`:

- Extension build: Node.js `24.19.0` + npm `12.0.2`.
- Extension compatibility CI remains Node major 22 and 24.
- Engine packaging: Python `3.13.15` + uv `0.12.5`.
- Engine compatibility CI remains Python 3.11 and 3.13.

`.nvmrc`, `.python-version`, `package.json#packageManager`, release workflows and `scripts/verify-toolchain-pins.mjs` are required to agree with that policy.

## Why Node 24 is canonical

Node 22 and Node 24 are both supported LTS lines at this audit. The canonical build is moved to the newer LTS line, Node 24, while Node 22 remains a compatibility lane. This does not change the extension runtime contract or minimum supported development line.

## Why Uvicorn stays at 0.52.3

Uvicorn 0.52.4 was published on the audit date, while the upstream release-notes page had not yet documented that release. The project therefore retains the already-pinned 0.52.3 for this lock bootstrap rather than changing an Engine dependency immediately before reproducibility freeze without a reviewed changelog.

This is deliberate stability policy, not a claim that 0.52.4 is defective. A later dependency refresh may upgrade it after review and tests.

## Generating the real locks

Run the GitHub Actions workflow `bootstrap-dependency-locks` from the exact commit to be locked. The workflow:

1. installs Node 24.19.0 and npm 12.0.2;
2. deletes any pre-existing npm lock and runs registry-backed `npm install --package-lock-only`;
3. rejects a missing/empty/non-v3 npm lock;
4. performs a clean `npm ci` and Extension structural/tests/build/manifest checks;
5. installs Python 3.13.15 and uv 0.12.5;
6. deletes any pre-existing Engine lock and runs `uv lock`;
7. runs `uv lock --check`, locked sync, Engine tests and benchmark/model-catalog contracts;
8. regenerates and verifies `SOURCE_SHA256SUMS.txt` with both locks present;
9. uploads `package-lock.json`, `uv.lock`, the matching source-integrity manifest, and a SHA-256 report as the `dependency-locks` artifact.

The workflow intentionally does **not** commit to the repository. Review the generated artifact, then commit these exact files:

- `package-lock.json`
- `engine/uv.lock`
- `SOURCE_SHA256SUMS.txt`

After they are committed, rerun normal CI. `npm run check:controlled-release-ready` must still remain fail-closed for all unrelated browser/production/native blockers.

## Local environment result in this audit

The current execution environment cannot resolve package-registry DNS and has no usable npm/uv registry cache. Attempts to run registry-backed npm resolution and offline uv/npm resolution therefore fail before a genuine lock can be produced. No placeholder lockfile is included in this archive.

That environmental limitation is now isolated to the explicit lock-bootstrap step; it is not converted into a green release state.

## Real qualification integration (REV11)

For the first production qualification, `qualify-production-ml-self-hosted.yml` now performs the same pinned registry-backed lock generation as an upstream hosted `bootstrap-locks` job and transfers those exact bytes to the protected self-hosted prepare job. The prepared workspace seals those exact locks beside its run plan; execute mode restores them rather than resolving dependencies again. This removes the former prerequisite that a reviewed `engine/uv.lock` already be present before qualification while preserving the rule that no lock may be fabricated.

The standalone `bootstrap-dependency-locks` workflow remains the review/commit path for source-controlled locks. Controlled release still consumes committed locks and must not regenerate them during promotion.
