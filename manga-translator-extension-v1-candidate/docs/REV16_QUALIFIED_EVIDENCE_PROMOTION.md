# REV16 — Qualified evidence promotion and source-bound production freeze

## Why this revision exists

REV15 correctly exposed the remaining V1 evidence blockers, but a successful protected qualification still did not have a safe, deterministic path back into the release source tree. The execute workflow uploaded only the production freeze while the real npm/uv locks remained transient prepare evidence. The final release verifier, however, requires those exact locks and the freeze to exist in the release checkout.

REV16 closes that handoff without weakening the two-phase human-review boundary and without uploading model, corpus, checkpoint or OCR-trace bytes.

## Freeze v4: source-bound qualification

`production-profile-freeze-v4-source-and-release-evidence-bound` retains all REV15 lock/policy/candidate/role/SFX/inpainting bindings and additionally records:

- the exact `runPlanSha256`;
- the benchmark `executorSourceSha256`;
- the qualified Git source-head identity;
- deterministic `src` and `engine/mte_engine` runtime-tree digests.

The runtime-tree binding deliberately excludes only `engine/mte_engine/benchmark/production-profile-freeze.json`, because that file is created after the benchmark passes and must be promotable into the reviewed release commit. Any other Extension or Engine runtime-source change invalidates the release freeze.

## Release-safe evidence export

After a successful execute-mode qualification, `export_qualification_release_evidence.py` emits one artifact containing only:

- `package-lock.json`;
- `uv.lock`;
- `production-profile-freeze.json`;
- `qualification-execution-summary.json`;
- `qualification-session.json`;
- a content-addressed `qualification-release-evidence.json` envelope.

The envelope is rejected unless the session, execution summary, run plan, dependency locks, freeze, qualified source head and source binding all agree. It explicitly declares that it contains no model bytes, corpus bytes or OCR-text traces.

## Reviewed promotion workflow

`.github/workflows/promote-production-qualification.yml` accepts only a successful `qualify-production-ml-self-hosted.yml` execute run from the same source commit. It downloads the exact release-evidence artifact and then:

1. rehashes every evidence file;
2. validates both dependency lock graphs against the current `package.json` / `engine/pyproject.toml`;
3. verifies the current runtime trees still equal the trees qualified by the freeze;
4. validates the active role/SFX and inpainting thresholds;
5. promotes only the locks, freeze, evidence-derived release-state mirrors and source checksum manifest;
6. rejects every changed path outside that fixed allowlist;
7. opens a review pull request instead of mutating the release branch directly.

The final release verifier independently repeats the runtime-source binding check after promotion.

## What REV16 does not claim

REV16 does not create real dependency locks, production model artifacts, a production corpus, browser smoke evidence or a production freeze in this archive. Those remain external execution facts. The revision makes the first passing qualification promotable and source-verifiable; it does not fabricate that qualification.

The next evidence stage after promotion is controlled artifact assembly plus exact-byte browser/native smoke and profile/privacy materialization.
