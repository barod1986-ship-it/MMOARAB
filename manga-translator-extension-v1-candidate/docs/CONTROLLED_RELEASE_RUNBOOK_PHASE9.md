# Phase 9 — Controlled release runbook

## No feature changes

Phase 9 began as release hardening after the historical Phase 8 runtime freeze. Later audited V1-candidate corrections intentionally changed runtime behavior (qualification/source binding and remote-transfer consent); each accepted runtime transition has its own immutable baseline. The latest runtime baseline remains the REV16 qualified-evidence-promotion baseline because REV17 changes only release tooling/evidence collection, not `src/` or `engine/mte_engine/`.

## Private/developer release

0. Before spending a qualification/build cycle, dispatch `production-execution-readiness.yml` and require all selected protected-runner probes to pass. The static contract is `release-control/production-execution-contract.json`; qualification and exact-artifact smoke workflows re-run the relevant live probe themselves, so a stale readiness run cannot bypass the check.
1. Regenerate `SOURCE_SHA256SUMS.txt` only after intentional source changes with `python scripts/update_source_sha256s.py`, then require `python scripts/verify_source_integrity.py` to pass. Produce the extension ZIP using a genuine locked npm graph and run the full extension suite.
2. Test the exact ZIP as a fresh unpacked install on **Chrome 148** and on the **current Stable** channel. At the 2026-08-20 audit, Stable desktop is Chrome 151; refresh this value immediately before a later release.
3. Validate the genuine Engine lock with the pinned uv (`uv lock --check`), build Engine artifacts natively from `engine/uv.lock`, run fresh-machine smoke, and retain the final compatibility sidecar for each artifact. Public Windows/macOS sidecars must bind the post-sign/post-notarization bytes with `finalArtifact=true`; unsigned private/Linux artifacts are still bound by their exact compatibility hash.
4. In CI, verify every selected candidate run before downloading it: it must be successful, produced by the expected Extension/Linux/Windows/macOS workflow, and have `head_sha` equal to the controlled-release assembly `GITHUB_SHA`. Do not mix candidate artifacts from different source revisions.
5. Run `scripts/prepare_controlled_release.py` with the **exact tested ZIP** hash, exact Engine artifacts, and for V1 the locked metadata set (`extension.cyclonedx.json`, `engine.cyclonedx-1.5.json`, `engine.pylock.toml`, `MODEL_LICENSES.json`, `production-profile-freeze.json`). V1 assembly requires exactly Windows x86_64, macOS arm64 and Linux x86_64. The tool re-audits the exact ZIP permission/content contract, stages the archive transactionally, then atomically promotes exact bytes; it never rebuilds or re-zips them.
6. Hash the resulting `controlled-release.json`. Record smoke evidence in `release-control/smoke-records.json` with that exact `artifactManifestSha256`; for V1 Engine records also record `profileId=default-v1`, `profileStateAtTest=ready`, and the exact **target-specific** production profile fingerprint. The Linux/macOS/Windows fingerprints may differ because packaged runtime/codec identity is part of the fingerprint; `privacyDescriptor` and provider semantics must be identical across all three. Use `scripts/materialize_release_profile_privacy.py` rather than copying a fingerprint by hand. Then update `release-control/release-state.json` only to mirror validated evidence.
7. Run the exact archived Engine smoke workflow (`smoke-controlled-release-engine.yml`) on the three protected native runners. It re-hashes the controlled artifact, production freeze, qualified model/font bytes and source binding before a real production translation. Portable ZIP/TAR artifacts are clean-extracted; a public macOS `.pkg` is signature/staple/Gatekeeper-checked and installed with the system installer before smoke, then removed/forgotten before evidence is emitted. The workflow uploads observations only—never model/corpus bytes—and derives a candidate per-target profile/privacy descriptor.
8. Download the `native-smoke-complete` orchestration checkpoint produced by the Engine-smoke workflow, then run `scripts/record_exact_browser_smoke.py` on clean GUI machines for Chrome 148 and the current Stable channel against the same controlled archive and checkpoint. The tool verifies exact Extension + selected Engine artifact hashes, Chrome major, and orchestration-session identity; the four UX checks remain explicit human observations because Chrome permission/Side Panel/consent surfaces are user-mediated.
9. Advance the session to `browser-smoke-complete`, then promote the complete evidence set transactionally with `scripts/promote_release_smoke_evidence.py`. It refuses wrong-stage sessions, requires all three Engine targets plus Chrome 148/current-Stable records bound to one controlled manifest, materializes `profile-privacy.json`, seals `release-control/v1-orchestration.json`, and changes profile/privacy + smoke records + release state + source-integrity checksum state only after every validation succeeds.
10. Run `npm run check:controlled-release-ready`. The verifier re-hashes archive bytes and checks the evidence itself; state booleans cannot make a missing artifact pass. `developer-preview` may remain clearly labeled as such; `private-v1` additionally requires the validated production freeze/privacy/profile, all native targets, and V1 release metadata.

## Public release, only if explicitly chosen

Public release inherits every private/V1 gate plus Phase 8 Store readiness, but it has a deliberate two-step evidence boundary. `evidence-promoted` is the pre-Store immutable checkpoint; `public-evidence-promoted` is created only after Store-installed evidence exists.

1. Assemble a `public-v1` controlled archive with final signed/notarized native artifacts and complete the normal native + unpacked Chrome 148/current-Stable evidence promotion to `evidence-promoted`.
2. Run `prepare-store-candidate.yml` against that successful controlled-release run. It runs the pre-Store public gate, seals the Store submission handoff, and copies the **exact controlled Extension ZIP**; it never rebuilds/re-zips it.
3. Submit/stage that exact candidate manually in the Chrome Web Store and record the real Store item/version.
4. Run `record_store_installed_smoke.py` on clean Chrome 148 and audited-current-Stable profiles using the exact controlled Engine artifact. Both observations must bind the Store candidate SHA-256 and Store handoff.
5. Verify all production Engine download links by downloading complete bytes and checking size/SHA-256; make the support channel available and make rollback/archive/publisher/dashboard state truthful before public evidence promotion.
6. Run `promote_public_release_evidence.py` with exactly the two Store observations. It advances the tracked session to `public-evidence-promoted` transactionally without inventing manual public facts.
7. Run `finalize-v1-release.yml`; for public V1 it restores both the exact controlled archive and exact Store candidate/handoff and emits `release-ready.json` only after the final public gate passes.

Chrome Web Store supports deferred publishing and partial rollout. Percentage rollout through the API is only available for eligible items; current documentation states the item needs more than **10,000** seven-day active users for percentage updates. Do not configure a partial rollout percentage unless eligibility is confirmed. Otherwise use deferred/manual controlled publication without claiming a percentage rollout.

## Rollout observation

During a public rollout, do not add features. Observe only release-health signals that do not require new telemetry: Store/dashboard status, support reports, reproducible fixture failures, Engine download integrity, and explicit manual smoke. If a blocker appears, freeze expansion and use `release-control/rollback-runbook.md`.

## Release evidence

A valid controlled archive includes:

- extension artifact and SHA-256;
- one or more compatible Engine artifacts and SHA-256;
- Engine compatibility metadata;
- `controlled-release.json` tying the exact artifacts together;
- `SHA256SUMS`;
- clean-environment smoke records outside the artifact bytes;
- SBOM/license metadata generated in Phase 7;
- provenance attestations from CI where available.

No secret, API key, pairing token, certificate, model weight without reviewed redistribution status, or remote executable code is added during controlled release.

## Final release capsule (REV20)

A green final gate is followed by `finalize-v1-release.yml`, which must build and verify `release/final/<release-id>/` with `scripts/final_release_capsule.py`. Treat that capsule—not a rebuilt ZIP and not `release-ready.json` alone—as the exact final handoff. The workflow attests every subject listed in `CAPSULE_SHA256SUMS.txt` and separately attests the checksum index.

All production workflows using `actions/attest@v4` require `id-token: write`, `attestations: write` and `artifact-metadata: write`. GitHub currently limits private/internal repository attestations to GitHub Enterprise Cloud; a production repository that cannot satisfy the attestation platform prerequisite must not bypass the job.

## REV30 controller-assisted first real run

After repository onboarding, runner provisioning, GitHub-side verification and initialization of the external first-run ledger, automated GitHub Actions stages should be launched with `scripts/first_real_run_controller.py` rather than manually copying run IDs.

The controller requires the local-only `MTE_PRODUCTION_CONTROLLER_TOKEN` with fine-grained repository `Actions:write`, `Contents:read`, and `Pull requests:read`. Do not store that token in repository secrets or the bootstrap JSON. Run `plan` before `advance` to see the exact next stage and any required non-secret operator inputs. Local release/public evidence PR creation additionally requires the separate local-only `MTE_PRODUCTION_EVIDENCE_PR_TOKEN` with `Contents:write` and `Pull requests:write`; it is never stored in repository or environment secrets.

Every controller launch is sealed into the external ledger before dispatch and carries a controller-generated `run_intent_nonce`. All production workflows include that nonce in `run-name`; success is recorded only if the returned run ID, workflow path, default branch, source SHA, authorized actor ID, conclusion and nonce all agree. If the controller process is interrupted, run `resume`/`advance` against the same ledger. If the run failed, inspect the failure and use `retry-failed`; the failed intent remains in ledger history and a new nonce is created.

The controller deliberately stops at benchmark review, interactive Chrome acceptance, local evidence-promotion preparation and merged-PR transitions. For the three human-review boundaries, create a content-addressed checkpoint with `manual_boundary_checkpoint.py` and record it with `first_real_run_handoff.py record-manual` while supplying the same evidence files. The recording step revalidates semantics/hashes and rechecks the GitHub operator/repository/default-branch cursor. Local evidence promotions and PR merges retain their existing explicit recording paths. Qualification execute automatically reuses `workspace_relative` from the successful prepare record.


REV30 source-transition rule: local evidence promotion is not recorded separately. `advance` seals `pendingEvidencePr`, creates/recovers the exact allowlisted PR, verifies remote bytes, and records promotion + PR-created identity atomically. At the subsequent merge stage the controller stops for human review/merge, then accepts only the same PR number/head SHA and requires its merge commit to be the live default-branch HEAD.

## REV31 post-merge checkout reconciliation

After each evidence PR merge, do not continue from a stale local checkout. The controller inserts a `*-checkout-reconciled` stage and runs `scripts/reconcile_first_real_run_checkout.py`. It verifies repository/default-branch identity, fetches the exact ledger merge commit, rejects staged or unrelated dirty paths, proves any reviewed dirty file already matches the merged bytes, then resets only to that exact commit and re-runs Source Integrity. It never runs `git clean`; generated operational material under `release/` is preserved.

This stage is mandatory after qualification evidence, pre-Store release evidence, and post-Store public evidence merges. Local evidence promotion therefore always starts with `HEAD == currentSourceHeadSha` on the sealed default branch.

## REV32 recovery bundle during the first real run

Do not rely on GitHub Actions artifact retention to keep intermediate release material alive. The first-run controller now archives each verified automated stage under `release/recovery/<releaseId>/` before recording success; `record-manual` does the same for the exact reviewed manual checkpoint inputs. If a local recovery snapshot is missing or its SHA-256 changes, controller continuation fails closed.

Periodically export the current recovery state to independent storage:

```bash
python scripts/first_real_run_recovery.py export \
  --ledger release/first-real-run-ledger.json \
  --output /secure/independent-storage/<releaseId>-recovery.zip
python scripts/first_real_run_recovery.py verify-bundle \
  --bundle /secure/independent-storage/<releaseId>-recovery.zip
```

The exported ZIP is operational recovery material. It must not be copied into release-control files or used to mark any qualification/smoke/Store gate successful.

## REV33 recovery restore / rehydration

If the original runner/workspace is lost or GitHub Actions artifacts have expired after a REV32/REV33 recovery bundle was exported, use a **fresh checkout at the bundle's exact source cursor** and run `first_real_run_recovery.py restore`. Do not manually copy individual snapshots into `release/` and do not edit recovery paths in the ledger by hand.

The restore validates the checkout origin, default branch, exact HEAD, contract bytes, production workflow-set and full Source Integrity before staging anything. It then activates one content-addressed directory under `release/rehydrated/` atomically. The restored ledger changes only local recovery-snapshot paths and is resealed; the original ledger SHA remains recorded separately in `RESTORE_MANIFEST.json`.

After activation, delete or move the source recovery ZIP if desired and run `verify-restored`, followed by `first_real_run_controller.py plan --ledger <rehydrated-root>/ledger.json`. These operations do not require GitHub artifact storage. The next networked `advance` still revalidates the sealed numeric repository ID, default branch and source cursor before launching a workflow.

Restore provenance is operational state only. A successful rehydration never turns a missing qualification, Chrome/native smoke, signing, Store or final-release fact into a passing release gate.

## REV34 recovery rotation / independent backup generations

A verified REV33 Recovery Bundle is not sufficient as the only copy. After every sealed first-real-run ledger checkpoint, export the current bundle and run `first_real_run_recovery_rotation.py rotate` using a sealed operational config with at least two non-overlapping destinations and one operator-declared off-site destination. The rotation HMAC key is local/offline operational secret material and must never be committed or embedded in a recovery bundle.

A generation becomes active only after all destination copies re-hash correctly, signed receipts are written, and the actual REV33 restore + `verify-restored` path succeeds from a copied bundle. `prune` is dry-run by default and cannot reduce retained history below two complete generations. Physical off-site geography is an infrastructure assertion; the tool proves exact bytes, distinct storage IDs/paths and restoreability, not geography.

See `docs/REV34_RECOVERY_ROTATION_OFFSITE_DURABILITY.md`.
