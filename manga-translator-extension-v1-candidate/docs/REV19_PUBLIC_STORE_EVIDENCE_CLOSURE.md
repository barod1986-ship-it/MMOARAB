# REV19 — Public Store evidence closure

REV18 made private-V1 evidence ordering content-addressed, but a real public V1 still had a circular/impossible path. The tracked `evidence-promoted` checkpoint sealed `smoke-records.json` and `release-state.json` before Chrome Web Store submission, while the final public gate required later Store-installed smoke and public release-state updates. Changing those files after Store submission necessarily invalidated the REV18 checkpoint. In addition, the Store candidate workflow rebuilt a new ZIP from source instead of consuming the already controlled Extension ZIP.

REV19 separates public release into a pre-Store immutable handoff and a post-Store evidence promotion. The private-V1 path remains unchanged.

## Public sequence

1. Complete qualification, exact controlled assembly, native smoke, unpacked Chrome 148/current-Stable smoke, and normal `evidence-promoted` promotion.
2. Run the public pre-Store gate (`verify_controlled_release_ready.py --target-class public-v1 --gate-stage store-candidate`). It enforces the public signed/native artifact contract and all immutable V1 evidence, but intentionally does not require Store-installed smoke or post-submission public flags.
3. `v1_evidence_orchestrator.py store-handoff` seals `store-submission-handoff.json`, binding the passing pre-Store gate to the exact `evidence-promoted` session, controlled-manifest digest, Extension digest, assembly commit and qualified runtime commit.
4. `prepare-store-candidate.yml` downloads the successful controlled-release artifact, verifies its workflow provenance against the orchestration assembly commit, and copies the exact controlled Extension ZIP. It never runs `npm run zip`. `candidate.json` schema v2 binds the exact ZIP to the controlled manifest and Store handoff.
5. Upload/stage that exact candidate through the Chrome Web Store manual flow. On clean Chrome 148 and current Stable profiles, run `record_store_installed_smoke.py` against the staged/published Store item and the exact controlled Engine. Each observation is bound to the pre-Store orchestration session, Store handoff and candidate SHA-256.
6. After all manual public facts are truthful (publisher/dashboard/support/download/rollback state), run `promote_public_release_evidence.py` with exactly the two Store-installed observations. It preserves the original Engine + unpacked-browser records, derives only the Store-smoke/hash mirrors, advances orchestration to `public-evidence-promoted`, and updates source-integrity state transactionally.
7. `finalize-v1-release.yml` restores the exact controlled archive and, for public V1, the exact Store candidate/handoff artifact. It then runs the final controlled gate and can emit an attested `release-ready.json` only from `public-evidence-promoted`.

## Fail-closed properties

- A public session cannot advance directly from `evidence-promoted` to `release-ready`.
- Store candidate bytes must equal the Extension bytes already recorded in `controlled-release.json`.
- Pre-Store handoff tampering is detected by its canonical digest.
- Store-installed evidence requires both Chrome 148 and the audited Stable major, and each observation names the exact candidate/handoff identities.
- Post-Store promotion does not invent publisher approval, support readiness, download verification, archive/rollback state, or Store submission facts; those remain explicit operator-controlled evidence.
- Final public verification re-hashes the post-Store tracked evidence plus the downloaded Store candidate metadata/handoff and controlled archive.

No Store candidate, Store-installed observation, public-evidence checkpoint, or release-ready checkpoint is pre-populated by REV19.

## REV19 verification snapshot

Local source/tooling verification after the public lifecycle correction:

- Engine tests: 126 collected and all passed through `engine/scripts/run_tests.py`.
- Phase 5: 22/22; Phase 5B: 79/79; Phase 6: 30/30; Phase 7: 151/151; Phase 8: 152/152; Phase 9: 232/232.
- Store tooling: 2/2; controlled-release tooling: 6/6; release-evidence tooling: 6/6; V1 orchestration tooling: 7/7; public-release evidence tooling: 4/4; release-ready regressions: 11/11; remote-transfer consent: 12/12.
- Workflow YAML: 15/15; TypeScript structural compilation: pass.
- Current source-only dry audit remains blocked: private-v1 19 blockers; public pre-Store 19 blockers; final public-v1 28 blockers. These are absent real release inputs/evidence, not pre-populated successes.
