# REV20 — Final Release Capsule + Provenance Closure

## Scope

REV20 closes the delivery boundary after a V1 orchestration session reaches `release-ready`. Earlier revisions proved qualification, exact controlled assembly, native/browser smoke and public Store evidence, but the final workflow still uploaded only `release-ready.json`. That checkpoint proves the gate state; it is not itself the Extension/Engine payload a user receives.

## Fixes

1. `scripts/final_release_capsule.py` now assembles one fail-closed final capsule only after the final controlled-release gate is green.
2. The capsule copies the exact files already present in the controlled archive; it never rebuilds the Extension or Engine.
3. The controlled directory must contain exactly the manifest-declared files plus `SHA256SUMS`. Extra/unmanifested files, symlinks, missing files or hash changes are rejected.
4. The capsule includes the exact npm lock, uv lock, production freeze, release-state, smoke records, profile/privacy descriptor, pre-final orchestration checkpoint, final `release-ready` checkpoint and source-integrity manifest. Public V1 additionally carries Store publication/support/download/candidate/handoff evidence.
5. `release-manifest.json` distinguishes three source identities: the production-qualified runtime commit, the controlled-assembly commit, and the finalization/evidence commit. It also binds the final and pre-final orchestration hashes.
6. `CAPSULE_SHA256SUMS.txt` content-addresses every capsule subject except itself. The final workflow attests all subjects from that checksum list, then separately attests the checksum index.
7. Every workflow using `actions/attest@v4` now grants `artifact-metadata: write` in addition to `id-token: write` and `attestations: write`, matching the current action requirements.
8. A REV19 orchestration bug was corrected: private `release-ready` sessions no longer incorrectly enter the public-only `public-evidence-promoted` validation branch.

## Final capsule layout

```text
release/final/<release-id>/
  release-manifest.json
  CAPSULE_SHA256SUMS.txt
  artifacts/
    <exact controlled Extension ZIP>
    <exact Linux/macOS/Windows Engine artifacts>
    <compatibility metadata>
    <SBOM/license/freeze metadata>
    controlled-release.json
    SHA256SUMS
  evidence/
    release-ready.json
    v1-orchestration-pre-final.json
    package-lock.json
    uv.lock
    production-profile-freeze.json
    profile-privacy.json
    smoke-records.json
    release-state.json
    SOURCE_SHA256SUMS.txt
    <public-only Store/support/download evidence when applicable>
```

## Attestation infrastructure note

GitHub's current `actions/attest@v4` documentation states that artifact attestations are available for public repositories on current plans; private/internal repositories require GitHub Enterprise Cloud, and GitHub Enterprise Server is not supported. The production repository/organization must therefore satisfy that external platform prerequisite or the mandatory attestation jobs will fail closed.

## Non-claims

REV20 does not fabricate dependency locks, production model bytes, a production freeze, browser/native smoke observations, Store approval, support readiness or rollout evidence. The source-only V1 gate remains blocked until those real inputs are promoted.

## REV20 verification

- Engine regression suite: PASS (runtime tree unchanged from REV16 audited baseline; 126 tests in the established suite).
- Phase 5: 22/22.
- Phase 5B: 79/79.
- Phase 6: 30/30.
- Phase 7: 153/153.
- Phase 8: 152/152.
- Phase 9: 247/247.
- Remote-transfer consent: 12/12.
- Store tooling: 2/2.
- Controlled-release tooling: 6/6.
- Release-evidence tooling: 6/6.
- V1 orchestration tooling: 8/8 (includes private `release-ready` regression).
- Public-release evidence tooling: 4/4.
- Final-release capsule tooling: 5/5.
- Release-ready gate regression: 11/11.
- TypeScript structural check: PASS.
- Workflow YAML: 15/15 parsed.
- Source integrity: 383/383 after REV20 sources are registered.
- Source-only dry audit remains fail-closed: private V1 has 19 missing real-evidence blockers; final public V1 has 28.
