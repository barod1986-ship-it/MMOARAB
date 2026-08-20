# Manga Translator Extension — Phase 9 Controlled Release

REV10 Phase 9 originally froze the Phase 8 runtime and added release-only controls: exact tested-artifact archiving, Engine compatibility binding, fresh-environment smoke evidence, support/rollback state, production download verification, and a fail-closed controlled-release gate. Subsequent audited V1-candidate revisions intentionally changed runtime code to close qualification, privacy-consent, and evidence-verification blockers; each change has a child runtime baseline while the original Phase 8/REV10 baselines remain immutable history. Unreviewed feature work is still forbidden during release hardening.

The source tree is currently **not release-ready**: no real registry-generated dependency locks, production qualification freeze, final controlled extension/Engine artifacts, or Chrome 148/current-Stable fresh-install smoke have been produced in this environment. The default release class remains `developer-preview`, and public distribution remains unchosen. Use `npm run check:v1-evidence-closure` to audit all private-V1 evidence gates without changing that committed release class. REV19 extends the content-addressed V1 state machine through the public Store lifecycle: exact controlled Store candidate handoff, Store-installed Chrome 148/current-Stable evidence, post-Store public evidence promotion, and an attested finalizer. See `docs/REV19_PUBLIC_STORE_EVIDENCE_CLOSURE.md`.

See `docs/PHASE9_STATUS.md`, `docs/CONTROLLED_RELEASE_RUNBOOK_PHASE9.md`, `docs/PROTOCOL_COMPATIBILITY_POLICY.md`, and `release-control/`.

---

# Manga Translator Extension — Phase 8 Chrome Web Store Readiness

REV10 Phase 8 adds the optional public Chrome Web Store submission layer on top of Phase 7 without claiming that the production model/native release gates have passed. It includes a versioned **first-run in-product privacy consent gate**, Store listings/privacy/permission/reviewer material, real-asset contracts, publisher/2-Step Verification blockers, and an exact-byte Store-candidate promotion workflow.

On first toolbar use, the Side Panel opens but no page session/content script is created until the user accepts the prominent disclosure. Local-processing consent explicitly does **not** authorize transfer to an external translation provider. Public release remains fail-closed until the frozen production privacy descriptor and all native/model/account/Store-smoke gates are complete.

The Store upload contract is strict: the candidate ZIP is copied byte-for-byte from the tested ZIP and re-hashed; it is never re-zipped after testing. The first Store submission remains a manual Developer Dashboard flow.

See `docs/PHASE8_STATUS.md`, `docs/STORE_READINESS_RUNBOOK_PHASE8.md`, `docs/PHASE8_RESEARCH_NOTES.md`, and `store/README.md`.

---

# Manga Translator Extension — Phase 6 UI Productionization

REV10 Phase 6 turns the Phase 1–5B architecture into a user-facing Chrome extension workflow without weakening the production ML gate. The primary interface is a **React + TypeScript Side Panel**; advanced setup lives in a full **Options page**. Background/content/pipeline code remains framework-independent TypeScript.

## Phase 6 user workflow

1. Invoke the extension action or its `_execute_action` shortcut on an HTTP(S) reader page.
2. On first use, the trusted action path opens the Side Panel synchronously and waits for the versioned privacy disclosure to be accepted before creating the `PageSession`; later activations proceed normally while that disclosure version remains accepted.
3. The Side Panel shows page/session state, candidates, actual queue/engine progress, grouped failures, result visibility controls, and translation actions.
4. The Options page owns Local Engine setup: exact loopback host permission, LNA-aware `/healthz` probe, masked pairing token, capabilities/profile readiness, privacy disclosures, cache settings, diagnostics, locale/theme, and controls.
5. Translation settings are converted into the trusted `ProcessingSpec` inside the Background. Target remains Arabic and `sfx|uncertain` remain `preserve-original`.
6. Results may be auto-presented or retained as `ready-result`; an optional extension-owned Shadow DOM button switches original/translation without reprocessing.

`default-v1` remains fail-closed until Phase 5B's real corpus/model benchmark produces an approved production freeze. Phase 6 exposes that blocker instead of bypassing it. `fixture-v1` remains development-only for protocol/UI acceptance work.

See `docs/PHASE6_STATUS.md` and `docs/PHASE6_USER_ACCEPTANCE.md`.

---

# Phase 5B Production Benchmark Gate retained

REV10 Phase 5B sits between the staged Engine implementation and production model readiness. It adds the **legal corpus / benchmark / model provenance / deterministic winner / profile-freeze** gate needed before `default-v1` can be represented as a real production profile.

## What Phase 5B adds

- external corpus schema-v2 manifest with per-page SHA-256, a versioned source registry, and content-addressed rights-review evidence; public availability or a boolean authorization field alone cannot qualify a page;
- separate real-domain language minimums so synthetic/self-authored pages can supplement edge cases but cannot replace real manga/manhwa/webtoon qualification pages;
- REV10 corpus minimums and visual/language coverage checks;
- normalized raw benchmark format and metric recomputation for detection, OCR, reading order, SFX safety, performance, Arabic goldens, translation and inpainting review;
- deterministic candidate selection rather than a hand-edited "winner" field;
- model/checkpoint provenance catalog with separate code license, artifact-license status, redistribution/provisioning status and local SHA-256 pin;
- file **or directory-tree** model hashing; symlinks are refused;
- release evaluation that re-hashes selected local artifacts before passing;
- exact-zero SFX/uncertain safety gates using independent ground truth;
- tamper-evident `production-profile-freeze.json` whose digest and selected runtime/model semantics enter `EngineProfileFingerprint`;
- versioned project release policy (`benchmark-thresholds-v3`; v1/v2 retained as history) so threshold changes cannot happen silently.

The repository deliberately contains **no production corpus and no model weights**, and therefore no valid production freeze. `default-v1` remains fail-closed/non-ready.

The full reviewed-intake → ready-run-plan → optional executor/report/gate/freeze chain is available through `engine/scripts/run_production_qualification.py`. REV13 adds `seal_qualification_input_bundle.py`, `verify_qualification_input_bundle.py`, and `prepare_qualification_from_bundle.py` so the real prepare run consumes one content-addressed operator-input identity before network acquisition; benchmark execution remains a separately reviewed step.

See `docs/PRODUCTION_ML_BENCHMARK_GATE.md`, `docs/PRODUCTION_CORPUS_RIGHTS_CHAIN.md`, `docs/REV13_QUALIFICATION_INPUT_HANDOFF.md` and `docs/PHASE5B_STATUS.md`.

---

## Phase 5 staged Engine retained

REV10 Phase 5 implementation layered on the completed acquisition, BinaryStore/identity, queue/cache, and loopback Engine lifecycle.

## Phase 5 scope

The Local Engine is now a staged pipeline with explicit adapter boundaries:

```text
decode → detector → reading order → OCR router → OCR QA → role classifier
      → dialogue/narration translation lane
      → protected SFX/other/uncertain lane
      → safe mask → inpaint → Arabic RAQM render
      → protected-source composite → exact-lossless encode → result validation
```

Implemented contracts:

- detector, reading-order, OCR, role-classifier, translator, inpainter, and renderer interfaces;
- deterministic stable block IDs and structured `ResultManifestV1`;
- English-first OCR routing policy with Japanese/Korean/Chinese routes kept separate;
- fail-closed role classification: only `dialogue|narration` may become `translate-replace`;
- `sfx|other|uncertain` are always `preserve-original` under `sfx-preserve-v1`;
- protected-mask guard, destructive-mask overlap rejection, and final source-pixel recomposite;
- post-encode/decode protected-pixel verification across all RGBA channels;
- page-batch translator ID mapping rather than isolated unordered strings;
- Arabic rendering with Pillow + FreeType + libraqm, `direction="rtl"`, `language="ar"`, measured wrapping, and binary-searched font fitting;
- exact-lossless WebP first, PNG rescue second;
- manifest schema/size/count/string/geometry validation;
- profile fingerprint now covers detector/OCR/role/translator/inpaint/renderer/encoder semantics.

## Production profile versus fixture profile

`default-v1` is intentionally **not falsely marked ready**. REV10 requires the real comic benchmark and artifact-license/provenance gate before pinning:

- PP-OCRv6 small detector vs PP-OCRv6 medium detector;
- PP-OCRv6 small vs medium for English and Chinese;
- manga-ocr primary for Japanese with PP-OCRv6 challenger/fallback;
- `korean_PP-OCRv5_mobile_rec` for Korean;
- LaMa vs AOT according to the tested hardware profile;
- a trusted translation provider/model and glossary/prompt revision;
- an approved Arabic font artifact/license profile.

Until those artifacts are pinned, `default-v1` reports a non-ready capability state and job creation fails closed with `profile_not_ready`.

A development-only `fixture-v1` exists solely for protocol and safety tests. It is exposed only when `MTE_ENABLE_FIXTURE_PROFILE=1`; it must never be used as evidence that production OCR/translation quality passed.

## Arabic font configuration

Phase 5 does not bundle a font artifact. For local development/tests, configure a trusted Arabic-capable font:

```bash
export MTE_ARABIC_FONT_PATH=/absolute/path/to/approved-font.ttf
```

The font **content digest**, not its absolute path, enters the Engine profile fingerprint. The renderer refuses to run without libraqm or a valid configured font.

## Checks

```bash
npm run check:offline
npm run check:structural
npm run check:phase4-contracts
npm run check:phase5-contracts
python engine/scripts/run_tests.py
```

The Python tests include a synthetic/legal reference vertical slice with an independent ground-truth SFX annotation. That test requires zero SFX translator input and zero changed pixels inside the annotated SFX region after final encode/decode.

## Release boundary

The staged architecture and safety/reference gates are implemented. The **production Phase 5 exit gate is not claimed complete** until the real licensed comic corpus can run the actual PP-OCR/manga-ocr/detector/inpainting candidates and pin the benchmark winners plus model artifact hashes/licenses. This repository deliberately refuses to choose an unbenchmarked model merely because it is newer.

See `docs/PHASE5_STATUS.md`.


## Phase 7 — Packaging and distribution

Phase 7 adds a trusted Local Engine model installer, native packaging scaffolding for Windows/macOS/Linux candidates, locked-release/SBOM gates, immutable GitHub Actions references, signing/notarization gates, support-claim metadata, provenance attestations, and clean-machine smoke tooling. The production model distribution catalog remains deliberately empty until Phase 5B Gate D is frozen with legal, hashed artifacts. No operating system is advertised as publicly supported by this source tree yet; the machine-readable support matrix is fail-closed.

### REV20 final delivery closure

After a real V1 reaches the final green gate, `finalize-v1-release.yml` now emits a verified `v1-final-release-<release-id>` capsule containing the exact controlled Extension/Engine artifacts and their release evidence. `scripts/final_release_capsule.py` rejects extra controlled files, verifies the orchestration chain and lock/freeze bindings, records the finalization source commit, and produces `CAPSULE_SHA256SUMS.txt` for multi-subject provenance attestation. REV20 also fixes private-V1 `release-ready` validation so it no longer incorrectly requires public Store evidence.

## Production execution bootstrap (REV21–REV27)

Before the first real V1 qualification/release run, use `npm run check:production-execution-contract` for source/workflow drift and dispatch `.github/workflows/production-execution-readiness.yml`. REV22 makes that workflow audit the GitHub administration layer first: required protected environments must exist, every production role must resolve to an online correctly-labelled self-hosted runner, and required environment variable/secret names must be configured. The audit uses `MTE_INFRA_AUDIT_TOKEN` with read-only repository administration/environment visibility and never reads secret values. Only after that metadata audit passes do the four live protected-runner probes begin. Public macOS signing provisions an ephemeral keychain/API key; public Windows signing uses Microsoft Artifact Signing with GitHub OIDC. REV23 additionally paginates every GitHub infrastructure collection, audits the qualification-promotion environment, and adds an external operator resume ledger with ordered stage/run-ID enforcement. See `docs/REV21_PRODUCTION_EXECUTION_BOOTSTRAP.md`, `docs/REV22_GITHUB_INFRASTRUCTURE_AUDIT_FIRST_RUN_HANDOFF.md`, `docs/REV23_REPOSITORY_BOOTSTRAP_RESUME_LEDGER.md`, and `docs/REV25_REPOSITORY_ONBOARDING_IDENTITY_BOUND.md`.

### REV24 repository provisioning

REV24 provides non-destructive provisioning. REV25 fixes the sealed-config editing gap and adds a mandatory identity boundary: `template → set-runner ×4 → bind → runner-command → plan --live → apply → verify`. Binding proves the immutable repository ID, local origin/default branch/HEAD, the live default-branch head, the complete production workflow-set hash and Source Integrity hash. Generated runner commands are shell-safe and re-check repository/head drift before requesting a registration token. REV26 moves `MTE_INFRA_AUDIT_TOKEN` into the protected `production-infrastructure-audit` environment, requires every production environment to be exact-default-branch-only, and corrects the provisioning token permission contract to include `Actions:read` and `Contents:read` in addition to write permissions. REV27 adds a stable GitHub actor-ID allowlist to every production workflow and makes the first-real-run ledger commit-transition aware: evidence promotion PR creation is distinct from merge, `currentSourceHeadSha` advances only after an allowlisted merge is verified, and public V1 explicitly includes Store/post-Store evidence stages. See `docs/REV24_REPOSITORY_INFRASTRUCTURE_PROVISIONING.md`, `docs/REV25_REPOSITORY_ONBOARDING_IDENTITY_BOUND.md`, `docs/REV26_PRODUCTION_WORKFLOW_TRUST_BOUNDARY.md`, and `docs/REV27_PRODUCTION_RUN_PROVENANCE.md`.
