# Phase 9 status — Controlled release

## Outcome

The **controlled-release implementation is complete and the final gate has been hardened after the REV10 V1 audit**, but the release Exit Gate is intentionally open. This phase does not claim that an Extension V1 or public Store release has happened.

Phase 9 itself made no feature changes to the browser or Engine runtime. That historical freeze remains preserved in `release-control/runtime-baseline-phase8.json`. After the REV10 final audit, V1 blocker closure resumed intentionally; subsequent candidate baselines remain append-only children rather than rewriting historical evidence. The latest intentional runtime rebaseline is REV16 at `release-control/runtime-baseline-v1-candidate-qualified-evidence-promotion.json`; REV17–REV27 change release/evidence/operations tooling without modifying `src/` or `engine/mte_engine/`. All earlier baselines remain immutable history.

## Implemented

- exact tested extension ZIP + Engine artifact archiver; assembly is transactional, promotion copies bytes atomically and never rebuilds/re-zips;
- extension ZIP safety/Manifest V3/Chrome 148 validation plus exact required/optional permission and packaged-content drift checks before controlled archiving;
- Engine compatibility sidecars bound to artifact SHA-256 and `protocolMajor=1`;
- public Windows artifacts require signed metadata; public macOS artifacts require signed + notarized metadata;
- post-sign/post-notarization compatibility metadata generation for final native bytes;
- deterministic candidate selector that prefers final signed/notarized metadata for public releases;
- fresh-unpacked / Store-installed / Engine smoke evidence schemas;
- private/developer versus private-V1 versus public-V1 release classes;
- production Engine URL verifier: HTTPS only, reviewed public host allowlist, DNS public-address validation, redirect revalidation, exact size and SHA-256;
- support-channel state and rollback evidence;
- protocol backward-compatibility policy;
- GitHub controlled-archive workflow that accepts only successful candidate runs from the same commit and expected producer workflows, archives exact bytes plus V1 SBOM/license metadata, attests them, and never publishes to Chrome Web Store itself;
- byte-level Phase 8 runtime freeze to prevent feature drift during release hardening.

## Current Chrome audit

On 2026-08-18 the normal Stable desktop channel was Chrome 151 (`151.0.7922.169/.170` on Windows/macOS and `.169` on Linux). Chrome 152 was also in early Stable for a small percentage of users. Phase 9 therefore records **Chrome 151** as current Stable at the 2026-08-19 audit while retaining explicit Chrome 148 baseline testing.

## Tests run in this environment

Current REV27 verification (2026-08-20):

- Engine pytest: 126/126.
- Phase 5 contracts: 22/22.
- Phase 5B contracts: 79/79.
- Phase 6 contracts: 30/30.
- Phase 7 contracts: 172/172.
- Phase 8 contracts: 152/152.
- Phase 9 contracts: 299/299.
- Remote-transfer consent contract: 12/12.
- Store tooling smoke: 2/2.
- Controlled-release tooling smoke: 6/6.
- Release-evidence tooling smoke: 6/6.
- V1 orchestration tooling smoke: 8/8.
- Public-release evidence tooling smoke: 4/4.
- Final-release capsule tooling smoke: 5/5.
- Production-execution readiness tooling smoke: 3/3.
- GitHub production-infrastructure audit tooling smoke: 8/8.
- First-real-run handoff tooling smoke: 10/10.
- Production-infrastructure bootstrap tooling smoke: 11/11.
- Production-workflow trust tooling smoke: 6/6.
- Release-ready regression smoke: 11/11.
- GitHub Workflow YAML: 16/16 valid.
- TypeScript structural compilation: PASS.
- Python compileall: PASS.
- Source Integrity: 403/403.

## Current release blockers

The REV10 final audit found that the original Phase 9 ready gate could be fooled by fabricated state booleans/manifest fields and empty lockfiles. That false-positive path is fixed. The gate now re-hashes the actual controlled artifacts, checks exact `SHA256SUMS`, validates smoke records against the controlled-manifest digest, validates dependency-lock structure, production freeze/privacy/native evidence and V1 release metadata.

For the current `developer-preview` source state the remaining blockers are real external/build evidence: a genuine `package-lock.json`, a genuine `engine/uv.lock`, the exact controlled archive, and fresh-unpacked Chrome 148/current-Stable smoke bound to that archive. Registry-backed npm resolution in this environment timed out/DNS-failed and offline npm/uv resolution confirmed the required registry objects are not cached; no lock was fabricated. `bootstrap-dependency-locks` now provides a pinned, audited registry-backed path that generates both locks, validates them with clean installs/tests, regenerates source integrity, and uploads the exact lock artifact without auto-committing it.

For `private-v1`/`public-v1`, additional blockers remain: a real Phase 5B production freeze; real corpus evidence proving the exact production role/SFX revision preserves every annotated SFX block; reviewed/hash-pinned ONNX packages for both inpainting candidates and a benchmark-selected LaMa/AOT winner. REV15 now derives both readiness states from the release-evidence-bound freeze and refuses mismatched state flags; release-specific frozen translation/privacy metadata; all three final native targets; clean-machine production-profile smoke; and final SBOM/license metadata. The production detector/OCR/role/translator/inpainting runtime adapters are implemented and fail-closed. REV14 also implements a separate versioned remote-transfer disclosure/consent and enforces its proof independently in both the Extension gateway and Engine create/start paths. `default-v1` still remains deliberately `runtime-unavailable` until the exact artifacts, dependencies and freeze evidence exist. Public release additionally inherits all Phase 8 Store/support/download/rollback requirements.

The detailed audit and exact interpretation are recorded in `docs/V1_FINAL_RELEASE_AUDIT.md`.

## Reproducible dependency bootstrap

The canonical release toolchain is now centralized in `release-control/toolchain.json`: Node 24.19.0 + npm 12.0.2 for the Extension candidate, and Python 3.13.15 + uv 0.12.5 for Engine packaging. Node 22/24 and Python 3.11/3.13 remain compatibility test lanes. `scripts/verify-toolchain-pins.mjs` prevents workflow/toolchain drift. See `docs/DEPENDENCY_LOCK_BOOTSTRAP.md`.

## Public rollout semantics

Chrome Web Store currently supports deferred/staged publishing and rollback to the previously published version. Percentage rollout can be changed without a new review for eligible items; current API documentation states percentage updates require more than 10,000 seven-day active users. Phase 9 does not assume that eligibility.

## Post-Phase9 V1 closure update — production runtime wiring

After the REV10 final audit, runtime development intentionally resumed to close V1 production blockers. Therefore the earlier statement that the runtime is byte-identical to Phase 8 is historical to Phase 9 itself, not the current working tree. The original `runtime-baseline-phase8.json` has not been rewritten. The corpus-rights candidate baseline remains preserved in `runtime-baseline-v1-candidate.json`, the manual-artifact baseline remains preserved in `runtime-baseline-v1-candidate-artifact-derivation.json`, and the REV11 lock-bound baseline remains preserved in `runtime-baseline-v1-candidate-real-qualification.json`. REV13 `src/` and `engine/mte_engine/` bytes remain frozen in `runtime-baseline-v1-candidate-qualification-input-bundle.json`; REV14 adds a new child baseline for the audited remote-consent/runtime closure rather than rewriting it. All Phase 5–9 contracts must be rerun after each intentional rebaseline.

The post-Phase9 implementation now includes freeze-driven PaddleOCR/manga-ocr adapters, safe local model-archive materialization, a strict text-only translation provider, `visual-enclosure-sfx-guard-v1`, and mask-bound `mte-onnx-inpaint-contract-v1` execution for the frozen LaMa/AOT winner. The SFX benchmark is also raw-evidence bound: the report is deterministically rebuilt from per-block measurements and those block IDs must exactly cover the independent corpus annotations. It **does not** mark V1 ready; real corpus/model/provenance/freeze evidence remains mandatory. See `docs/PRODUCTION_RUNTIME_WIRING.md` and `docs/ROLE_SFX_AND_INPAINT_PRODUCTION.md`.

## Post-Phase9 V1 closure update — ML acquisition chain of custody

The production benchmark prerequisites are now fail-closed before measurement starts. The active policy/plan pair is v3; v1/v2 remain immutable history, and v3 removes the conflicting preselected Japanese OCR primary. `candidate-plan-v3.json` freezes the active V1 candidate/artifact identity independently of raw results; the superseded v1 plan remains historical evidence; artifact intake produces content-addressed provenance receipts from explicitly supplied local bytes and reviewed decisions; corpus sealing computes exact file hashes from page-level reviewed rights records; and `prepare_benchmark_run.py` produces a content-addressed run plan that pins corpus, policy, catalog, candidate plan, artifacts and receipts. The official evaluate/freeze CLIs require the candidate plan, receipt directory and ready run plan. No production weight, corpus, approval or benchmark result has been fabricated by this work.

## Post-Phase9 V1 closure update — benchmark execution harness

The formal production benchmark is now executable rather than hand-authored. A schema-v2 ready run plan pins the exact executor source digest. `execute_benchmark.py` re-hashes the corpus, policy, catalog, candidate plan, every artifact and every receipt immediately before inference, then emits per-page/per-block machine evidence plus a separately sealed human-review snapshot. The report builder ignores duplicate caller aggregates and reconstructs detector/OCR/inpainting selection inputs from traces/review evidence. The release gate also binds trace coverage back to every expected corpus page/block so difficult cases cannot simply be omitted.

Performance evidence is explicitly scoped to `local-ml-detector-ocr-role-inpaint-v1` and runs on detector-produced regions. It does not pretend to include external translation-network latency or Arabic rendering. Long-webtoon detector geometry scoring uses local polygon rasterization instead of one page-sized mask per prediction, and binary mask accounting was corrected to count both direct-draw and Pillow `ImageChops` foreground representations. Inpainting review coverage is checked on the selected winner only.

This is tamper-evident/reproducible local evidence, **not** hardware-backed attestation against a malicious operator with arbitrary local-code access. No real production benchmark is claimed until authorized corpus/model artifacts and the resulting schema-v2 evidence exist. See `docs/PRODUCTION_BENCHMARK_EXECUTION_HARNESS.md`.

### Post-Phase9 ML acquisition hardening

Primary-source ML acquisition is now explicit and auditable but does not claim V1 readiness. A manual hosted workflow can acquire only allowlisted official Paddle/manga-ocr/Noto artifacts, re-hash them, and return evidence tied to the workflow commit; downloaded model/font bytes are removed before hosted artifact upload. It never updates catalog approval state or creates a production freeze. LaMa/AOT remain manual-derived with separate checkpoint and converter reviews, and the protected self-hosted qualification workflow retains production bytes locally. The active Japanese OCR policy is v3 and has no predetermined primary.


### Post-Phase9 manual artifact derivation and self-hosted qualification

LaMa/AOT production packaging is now governed by `manual-derived-artifact-policy-v1.json`. The deterministic packager requires an approved source-checkpoint review **and** an independently approved converter review bound to the exact converter bytes, URL and revision, validates the generated ONNX with CPU ONNX Runtime on multiple dynamic shapes, and embeds both review record IDs/file hashes into the derivation manifest. Receipt verification re-opens the package and checks the packaged derivation fields. The runtime additionally binds each candidate to its exact artifact family (`lama-inpaint` → `lama-big`, `aot-inpaint` → `aot-gan-places2`).

Noto Sans Arabic is pinned to the upstream `NotoSansArabic-v2.013` release and acquired as one exact ZIP member; the acquisition record binds the release ZIP hash and extracted TTF hash. REV11 hardens `.github/workflows/qualify-production-ml-self-hosted.yml` into separate `prepare` and `execute` phases: prepare generates real locks on a network runner, validates corpus/reviews/LaMa/AOT before downloads, acquires exactly seven automated artifacts and seals a stable lock-bound run plan; execute restores that exact workspace and locks and requires a review bound to the same `runPlanSha256`. Only safe run-plan/freeze attestations are uploaded; model/corpus/OCR-trace/checkpoint bytes remain local.

## REV12 real qualification execution attempt

The first real qualification execution was attempted on 2026-08-19. The available container cannot satisfy the pinned production toolchain or outbound DNS/socket requirements, and the source archive intentionally contains only corpus/review templates rather than operator-authorized production inputs. No lockfile, model artifact, human review or production freeze was fabricated.

The direct prepare attempt remained fail-closed and stopped on the unsealed corpus template before any model download. A new diagnostic-only readiness probe (`engine/scripts/probe_real_qualification_readiness.py`) records pinned-toolchain matches, required network reachability, lock/freeze presence and optional operator-input inventory. It cannot generate a freeze or mutate production evidence. See `docs/REV12_REAL_QUALIFICATION_EXECUTION_ATTEMPT.md`.


## REV13 sealed qualification input handoff

REV13 removes the last ambiguous prepare-time operator handoff. The protected qualification workflow no longer accepts independently selected corpus/review/manual paths for prepare. Operators must first create one `rev13-production-qualification-input-bundle-v1` that content-binds the authorized corpus manifest, all nine active artifact reviews, both reviewed LaMa/AOT runtime packages, and the active catalog/source-registry/manual-policy/benchmark-policy/candidate-plan controls.

A protected `input-preflight` job now configures the exact pinned Node/npm/Python/uv toolchain and requires `probe_real_qualification_readiness.py --strict` to pass against that sealed bundle before the hosted dependency-lock bootstrap can begin. Prepare re-verifies the bundle immediately before the seven automated artifact acquisitions and records the bundle SHA-256 in `qualification-summary.json`. No approval, model byte, legal corpus, benchmark result, or production freeze is invented. See `docs/REV13_QUALIFICATION_INPUT_HANDOFF.md`.


## REV14 final V1 source audit — remote-transfer consent closure

The final source audit found one remaining code-side privacy blocker: production translation can send extracted OCR dialogue/narration text to the frozen external provider, while the product previously had only the first-run local-processing consent. REV14 closes that gap without weakening production qualification. A second disclosure is now presented only for a ready profile that declares external transfer, and acceptance is bound to the exact profile ID/fingerprint, full privacy descriptor, ordered provider list, and disclosure revision `2026-08-19.remote-transfer.v1`.

This is enforced twice. The Extension obtains a current capabilities snapshot and refuses Engine job creation/start/resume when a matching proof is absent. The Engine independently rejects create and start/resume unless the proof exactly matches its current ready profile. `scripts/verify_remote_transfer_consent_contract.py` proves twelve executable source boundaries, and the controlled-release verifier dynamically invokes that proof instead of trusting `remoteTransferConsentImplemented` release metadata. Release-ready regression tests also prove that tampering away the Extension enforcement makes the release-state claim fail.

This closes `remoteTextTransferConsentReady` and the source-completeness `productionRuntimeAdaptersComplete` flag. It does **not** close `phase5bProductionFreezeReady`, role/SFX production qualification, inpainting artifact/winner readiness, dependency locks, native artifacts, browser smoke, or Store/public evidence. Those remain external immutable-evidence gates. See `docs/REV14_FINAL_V1_SOURCE_AUDIT.md`.

## REV15 V1 evidence-closure gate

REV15 found and closed a controlled-release verification gap: `productionRoleSfxClassifierReady` and `productionInpainterRuntimeReady` were tracked in release state but were not independently derived by the final private/public V1 gate. The first production freeze has not yet been created, so its revision is strengthened before production use to `production-profile-freeze-v4-source-and-release-evidence-bound`. It now carries candidate-plan identity and explicit role/SFX + selected-inpainting qualification summaries.

`verify_controlled_release_ready.py` binds that freeze to the active policy/candidate-plan bytes and derives both production readiness flags from frozen benchmark evidence. `npm run check:v1-evidence-closure` audits the current tree as `private-v1` without changing the committed developer-preview state, so later V1 blockers are visible before promotion. No external evidence is synthesized. See `docs/REV15_V1_EVIDENCE_CLOSURE_GATE.md`.


### REV16 qualification-evidence promotion
REV16 adds a source-bound freeze and a reviewed promotion handoff. A passing qualification now exports only safe lock/freeze/control evidence; a protected workflow revalidates the evidence against the exact qualified source commit and opens an allowlisted PR containing the real npm/uv locks, production freeze, evidence-derived release-state mirrors and refreshed source checksums. Runtime drift after qualification invalidates the freeze.

### REV17 exact controlled-artifact smoke evidence

REV17 closes the source-side evidence collection path after controlled assembly. `controlled-release.json` is source-bound schema v2 and V1 archives carry the exact production freeze. A protected workflow smokes the exact archived Engine bytes on Linux x86_64, macOS arm64 and Windows x86_64 against re-hashed qualified model/font bytes; public macOS `.pkg` evidence requires signature/stapling/Gatekeeper checks plus a real clean system install and verified cleanup. Real Chrome acceptance is recorded interactively from clean temporary profiles and is bound to both the exact controlled Extension ZIP and the exact Engine artifact used during the test.

Because the production profile fingerprint includes runtime/codec identity, REV17 corrects the release contract from one global fingerprint to `profileFingerprintsByTarget`. Linux/macOS/Windows fingerprints may differ, but the three explicit data-transfer booleans and external-provider list must be identical. `scripts/promote_release_smoke_evidence.py` promotes profile/privacy, smoke records and mirrored release state as one transaction only after all three native targets plus Chrome 148/current-Stable observations validate against the same controlled manifest/source commit. No smoke record is fabricated or pre-populated by this revision.


## REV18 orchestration closure

REV18 separates `qualifiedSourceHeadSha` from the later assembly `sourceHeadSha`, because reviewed qualification-evidence promotion necessarily creates a later commit while the frozen runtime-tree hashes remain unchanged. A content-addressed six-stage V1 orchestration session now gates controlled assembly, native smoke, interactive Chrome smoke, evidence promotion and the final release gate. Smoke promotion also updates `SOURCE_SHA256SUMS.txt` transactionally, eliminating the prior self-created source-integrity failure after otherwise-valid evidence promotion. See `docs/REV18_V1_EVIDENCE_ORCHESTRATION.md`.

## REV19 public Store evidence closure

The first real-orchestration attempt exposed a public-release sequencing defect: REV18 sealed smoke/release-state evidence before Store submission even though `public-v1` requires later Store-installed smoke and public-state changes. REV19 adds a pre-Store `store-candidate` gate and content-addressed Store submission handoff, makes the Store workflow consume the exact controlled Extension ZIP instead of rebuilding it, and adds a post-Store `public-evidence-promoted` checkpoint. Public finalization now requires that post-Store checkpoint; private-V1 continues to finalize from `evidence-promoted`. See `docs/REV19_PUBLIC_STORE_EVIDENCE_CLOSURE.md`.

REV19 verification: Engine 126 tests; Phase 7 151/151; Phase 8 152/152; Phase 9 232/232; public-release evidence tooling 4/4; release-ready regression 11/11; Workflow YAML 15/15. The source-only private audit remains blocked by 19 real-evidence requirements and final public V1 by 28 requirements.

## REV20 final release capsule / provenance closure

REV20 closes the boundary after the orchestration `release-ready` checkpoint. The finalization workflow now creates `release/final/<release-id>/` from the exact controlled archive plus the exact promoted release evidence, verifies the capsule offline, attests all checksum-listed subjects and uploads the complete final release capsule. No artifact is rebuilt during finalization.

The capsule records qualified runtime, assembly and finalization source commits separately and carries exact npm/uv lock bytes, production freeze, privacy/smoke/state evidence and the orchestration chain. Public V1 additionally carries Store candidate/handoff/publication/support/download evidence. Unmanifested controlled files are refused.

REV20 also fixes a private-V1 state-machine defect in REV19: a private `release-ready` session was incorrectly subjected to the public-only post-Store validation block. A regression now proves private `evidence-promoted -> release-ready` validation.

REV20 verification: Phase 7 153/153; Phase 8 152/152; Phase 9 247/247; V1 orchestration 8/8; final-release capsule 5/5; release-ready regression 11/11; Workflow YAML 15/15; Source Integrity 383/383. The source-only private/public dry audits remain blocked by 19/28 real-evidence requirements respectively.

## REV21 production execution bootstrap / signing provisioning closure

REV21 audits the first real production run boundary rather than adding product behavior. It introduces `release-control/production-execution-contract.json` as the authoritative contract for the protected qualification runner, the three protected native-smoke runners, their required labels/environments/paths/secrets, and the canonical toolchain. `scripts/probe_production_execution_environment.py` verifies source/workflow drift statically and can execute a fail-closed live probe on each protected runner without printing secret values. `.github/workflows/production-execution-readiness.yml` provides one operator preflight before qualification/release work begins; the actual qualification and native-smoke workflows also execute the role probe before expensive evidence work.

The audit also found that REV20 public signing assumed state that does not exist on clean GitHub-hosted runners. Public macOS now materializes Developer ID Application/Installer PKCS#12 material into an ephemeral runner keychain and materializes the team App Store Connect API key in `$RUNNER_TEMP`; `notarytool` receives the API key directly and the temporary keychain/key files are deleted by a trap. Public Windows no longer expects project-specific SignTool/dlib/metadata filesystem paths. It authenticates with GitHub OIDC through a commit-pinned Azure Login action, signs the exact PE payload with a commit-pinned Microsoft Artifact Signing v2 action, and independently requires `Get-AuthenticodeSignature` status `Valid` on every `.exe/.dll/.pyd` before packaging.

REV21 still does not create external facts. The protected runner fleet, protected environments, production input directories, signing credentials, Microsoft Artifact Signing account/role/federation, Apple Developer identities/team API key, real locks, production freeze, native/browser smoke and Store evidence must exist outside this source archive. The diagnostic record under `release/production-execution-attempt/` is explicitly non-release evidence and shows that the current local environment is not a production runner.


## REV22 GitHub infrastructure audit / first-real-run handoff

REV22 closes the repository-administration visibility gap left by REV21. The unified readiness workflow now audits GitHub-side metadata before scheduling protected self-hosted work: all contract environments must exist, each production role must have an online runner with the complete label set, and required environment variable/secret **names** must be configured. The audit uses only metadata endpoints and never reads secret values. Required-reviewer and prevent-self-review recommendations are reported as warnings unless explicitly promoted to blocking policy in the contract.

The contract revision `rev22-production-infrastructure-audit-v1` also records the canonical first-real-run ordering and requires resume to preserve recorded workflow run identities. `MTE_INFRA_AUDIT_TOKEN` is the single administration bootstrap secret for the metadata audit; it requires read-only repository administration/environment visibility and is not release evidence. REV22 still creates no external runner, environment, credential, lock, freeze, smoke record or release artifact.


## REV23 repository-bootstrap/resume addendum

REV23 fixes first-page-only GitHub infrastructure discovery, adds the previously unaudited `production-qualification-promotion` protected environment, and corrects the fine-grained audit-token permission contract to include Actions read. A separate contract-bound operator resume ledger now enforces canonical stage ordering, manual-review acknowledgements, and minimum workflow run-ID retention. The ledger is deliberately external operational state and is not release evidence.

## REV24 repository infrastructure provisioning

REV24 closes the provisioning handoff immediately before the first real production run. The production execution contract now declares a separate write-scoped bootstrap credential and a sealed, untracked provisioning configuration. The provisioning tool creates missing environments without replacing existing protection rules, sets variables/secrets from local source environment variables, adds runner labels non-destructively, emits just-in-time runner registration commands, and verifies the result with the same GitHub-side audit used by readiness. No qualification, smoke, signing, or release-ready evidence is created by this layer.


## REV25 repository onboarding identity binding

REV25 closes repository/commit ambiguity in the operator bootstrap. A provisioning template is now deliberately unbound; runner mappings are changed only through the resealing `set-runner` command, then `bind` proves the live immutable repository ID, live default branch/head, matching local origin/branch/HEAD, the SHA-256 of all 16 production workflows, and the current Source Integrity manifest. Runner registration, live planning, apply and verify require that binding. Generated Bash/PowerShell runner commands validate conservative identifiers, quote shell arguments, and re-check live repository/head identity immediately before requesting a short-lived registration token. The first-real-run ledger now inherits repository/source identity from the sealed onboarding config rather than accepting a manually typed source SHA. This layer remains operational state only and creates no release evidence.


## REV26 production workflow trust boundary

REV26 makes GitHub environment branch trust a blocking part of production readiness. `MTE_INFRA_AUDIT_TOKEN` is now stored in the dedicated `production-infrastructure-audit` environment, and every production environment must use a custom deployment branch policy containing exactly the live default branch and no alternate branch/tag pattern. Provisioning creates new environments in that state, may add the default branch only to an already-custom empty policy, and otherwise fails closed rather than deleting or silently replacing existing policies. The provisioning token contract now includes `Actions:read` and `Contents:read` because live planning/binding actually use those endpoints. Runtime source remains unchanged from the REV16 runtime baseline; this revision creates no release evidence.


## REV27 production workflow authorization and commit-transition provenance

REV27 makes every production job self-enforcing for `workflow_dispatch`, the live default branch and a sealed stable GitHub actor-ID allowlist. The onboarding config resolves operator logins to actor IDs, provisions the repository variable used by the guards, and the live audit verifies that variable by name/value without treating it as a secret. The first-real-run ledger now verifies workflow run provenance and advances its source commit only after an allowlisted evidence PR merge is proven. Private and public release plans are separate; public V1 explicitly includes Store candidate, Store-installed Chrome smoke and post-Store public evidence merge before finalization. Runtime source remains unchanged from the REV16 runtime baseline; this revision creates no release evidence.

## REV28 real-run launch/resume automation

REV27 verified run IDs after manual dispatch but did not bind the dispatch itself to the resume ledger. REV28 adds `first_real_run_controller.py`: before each automated stage it seals a crash-recoverable `pendingLaunch`, generates an immutable run-intent nonce, dispatches the exact workflow on the ledger default-branch commit, waits for completion, rechecks live branch identity and run provenance, and only then commits success to the operational ledger. All 13 production workflows require the nonce and include it in their Actions run title. A lost local response is recoverable by nonce; a failed launch is retained and can only be retried explicitly with a fresh nonce. Qualification execute also inherits the workspace recorded by the successful prepare stage instead of accepting it a second time from the operator. Manual reviews, interactive browser evidence, local evidence promotion and PR merges remain explicit fail-closed boundaries. No release evidence is created by this automation.

## REV29 manual-boundary provenance closure

REV28 automated workflow launches but still allowed the three human boundaries to be represented in the operator ledger by a boolean review flag. REV29 removes that weak transition. `scripts/manual_boundary_checkpoint.py` creates content-addressed checkpoints for benchmark review, exact Chrome 148/current-Stable acceptance and public Store-installed Chrome acceptance. The tool validates the stage-specific evidence semantics, records hashes/sizes instead of evidence contents, authenticates the GitHub actor ID, and verifies repository ID/default branch/head against the ledger cursor. `record-manual` then requires the same evidence files, re-runs the semantic checks and hashes, and re-authenticates operator/source identity before the checkpoint can enter the ledger. This is operational provenance only; it does not synthesize or replace release evidence.

REV29 verification: Engine 126/126; Phase 5 22/22; Phase 5B 79/79; Phase 6 30/30; Phase 7 172/172; Phase 8 152/152; Phase 9 308/308; manual-boundary checkpoint tooling 8/8; handoff 11/11; controller 7/7; infrastructure bootstrap 11/11; GitHub infrastructure audit 8/8; workflow trust 7/7; orchestration 8/8; public evidence 4/4; final capsule 5/5; release-ready regression 11/11; Workflow YAML 16/16. Private/public dry gates remain blocked by 19/28 real-evidence requirements respectively.

## REV30 evidence-PR creation and merge handoff closure

REV29 still left local evidence promotion and PR creation as separate operational steps. REV30 makes those boundaries recoverable and atomic. `pendingEvidencePr` is sealed before remote mutation; `evidence_transition_pr.py` uploads only stage-allowlisted files through Git Database API objects, creates/reuses a deterministic branch and PR, and re-hashes the remote PR file bytes against the local promotion. The ledger now has explicit `release-evidence-pr-created` and `public-evidence-pr-created` stages, while qualification PR creation is also discovered and recorded by exact PR number/head SHA after its workflow. Merge stages use only that recorded PR identity and remain human decisions; the controller merely waits for/validates the exact merge and requires the live default branch to equal that merge commit before advancing the source cursor. Write-capable PR credentials are split into the local-only `MTE_PRODUCTION_EVIDENCE_PR_TOKEN` rather than expanding the normal controller token.

REV30 verification: Engine 126/126; Phase 5 22/22; Phase 5B 79/79; Phase 6 30/30; Phase 7 172/172; Phase 8 152/152; Phase 9 317/317; production readiness 3/3; GitHub infrastructure audit 8/8; infrastructure bootstrap 11/11; first-run handoff 11/11; first-run controller 7/7; manual-boundary checkpoint 8/8; evidence-transition PR tooling 6/6; evidence-transition controller 3/3; workflow trust 7/7; Store tooling 2/2; controlled release 6/6; release evidence 6/6; orchestration 8/8; public evidence 4/4; Final Capsule 5/5; release-ready regression 11/11; Workflow YAML 16/16; TypeScript structural PASS. Private/public dry gates remain 19/28 blockers respectively because no production evidence was fabricated.

## REV31 post-merge checkout reconciliation

REV30 sealed the exact evidence PR identity and merge commit but left the operator working tree outside the ledger provenance chain. REV31 inserts mandatory checkout reconciliation immediately after qualification, release-evidence, and public-evidence merges. `reconcile_first_real_run_checkout.py` requires the sealed default branch/origin, verifies the live/fetched target commit, rejects staged or unrelated dirty source paths, and only permits dirty reviewed files when their bytes already equal the exact reviewed merge blobs. It then resets only to that merge SHA, never runs `git clean`, preserves operational untracked material under `release/`, and requires Source Integrity. The reconciliation snapshot is itself validated by the first-run ledger against the preceding merge changed-path set and source cursor.

REV31 verification: Engine 126/126; Phase 5 22/22; Phase 5B 79/79; Phase 6 30/30; Phase 7 172/172; Phase 8 152/152; Phase 9 328/328; production readiness 3/3; GitHub infrastructure audit 8/8; infrastructure bootstrap 11/11; first-run handoff 11/11; first-run controller 7/7; manual-boundary checkpoint 8/8; evidence-transition PR tooling 6/6; evidence-transition controller 3/3; production workflow trust 7/7; local checkout reconciliation 8/8; Store tooling 2/2; controlled release 6/6; release evidence 6/6; orchestration 8/8; public evidence 4/4; Final Capsule 5/5; release-ready regression 11/11; Workflow YAML 16/16; TypeScript structural PASS. Private/public dry gates remain 19/28 blockers respectively because no production evidence was fabricated.

## REV32 artifact-retention/disaster-recovery closure

REV31 made the local source cursor recoverable after evidence merges but the first-real-run ledger still depended on GitHub Actions artifact retention. REV32 archives verified run metadata plus every uploaded artifact ZIP before an automated run may be committed to the ledger, validates GitHub artifact digests when present, preserves `expires_at`, and rechecks the complete local recovery chain before any controller continuation. Manual boundary recording similarly archives the exact reviewed checkpoint/evidence bytes. `first_real_run_recovery.py export/verify-bundle` creates a content-addressed offline recovery bundle. This is operational preservation only and does not reduce V1 evidence blockers.

REV32 verification: Engine 126/126; Phase 5 22/22; Phase 5B 79/79; Phase 6 30/30; Phase 7 172/172; Phase 8 152/152; Phase 9 338/338; production readiness 3/3; GitHub infrastructure audit 8/8; infrastructure bootstrap 11/11; first-run handoff 11/11; first-run controller 7/7; manual-boundary checkpoint 8/8; evidence-transition PR tooling 6/6; evidence-transition controller 3/3; local checkout reconciliation 8/8; first-run recovery 7/7; production workflow trust 7/7; Store tooling 2/2; controlled release 6/6; release evidence 6/6; orchestration 8/8; public evidence 4/4; Final Capsule 5/5; release-ready regression 11/11; Workflow YAML 16/16; TypeScript structural PASS. Private/public dry gates remain 19/28 blockers respectively because disaster-recovery copies are not release evidence.

## REV33 recovery restore / rehydration closure

REV32 made intermediate Actions artifacts durable outside GitHub retention but did not prove that the exported bundle could reconstruct a usable controller state on a different checkout. REV33 adds an atomic `restore`/`verify-restored` path. A fresh Git checkout must match the sealed repository origin, default branch, source cursor, contract, workflow-set and complete Source Integrity. The restore then rewrites only operational recovery-snapshot paths into a single content-addressed `release/rehydrated/` root, reseals the ledger, restores manual checkpoint material, indexes preserved artifact ZIP bytes and records a separate restore manifest. The regression deletes the source bundle after restoration and successfully runs the real controller `plan` from the new checkout, proving that GitHub artifact retention is no longer needed for continuation after capture/export.

REV33 restore provenance remains operational only and does not reduce private/public V1 evidence blockers.

REV33 verification: Engine 126/126; Phase 5 22/22; Phase 5B 79/79; Phase 6 30/30; Phase 7 172/172; Phase 8 152/152; Phase 9 344/344; remote-transfer consent 12/12; production readiness 3/3; GitHub infrastructure audit 8/8; infrastructure bootstrap 11/11; first-run handoff 11/11; first-run controller 7/7; manual-boundary checkpoint 8/8; evidence-transition PR tooling 6/6; evidence-transition controller 3/3; local checkout reconciliation 8/8; first-run recovery 7/7; first-run rehydration 8/8; production workflow trust 7/7; Store tooling 2/2; controlled release 6/6; release evidence 6/6; orchestration 8/8; public evidence 4/4; Final Capsule 5/5; release-ready regression 11/11; Workflow YAML 16/16; TypeScript structural PASS. Private/public dry gates remain 19/28 blockers respectively because restore provenance is operational only.

## REV34 recovery rotation / off-site durability

REV34 adds authenticated recovery-generation rotation above REV33 rehydration. Every active generation requires at least two exact Recovery Bundle copies on distinct non-overlapping storage identities, including one operator-declared off-site destination, plus a real restore/verify probe from a copied bundle. Rotation state and copy receipts are HMAC-SHA256 authenticated with a local/offline key that is never stored in source or recovery bundles. Safe pruning cannot remove the active generation and preserves at least two complete generations. This is operational durability only and does not close any V1 evidence gate. See `docs/REV34_RECOVERY_ROTATION_OFFSITE_DURABILITY.md`.

REV34 verification: Engine 126/126; Phase 5 22/22; Phase 5B 79/79; Phase 6 30/30; Phase 7 172/172; Phase 8 152/152; Phase 9 352/352; remote-transfer consent 12/12; production readiness 3/3; GitHub infrastructure audit 8/8; infrastructure bootstrap 11/11; first-run handoff 11/11; first-run controller 7/7; manual-boundary checkpoint 8/8; evidence-transition PR tooling 6/6; evidence-transition controller 3/3; local checkout reconciliation 8/8; first-run recovery 7/7; first-run rehydration 8/8; recovery rotation 8/8; production workflow trust 7/7; Store tooling 2/2; controlled release 6/6; release evidence 6/6; orchestration 8/8; public evidence 4/4; Final Capsule 5/5; release-ready regression 11/11; Workflow YAML 16/16; TypeScript structural PASS. Private/public dry gates remain 19/28 blockers respectively because backup durability is operational state, not release evidence.
