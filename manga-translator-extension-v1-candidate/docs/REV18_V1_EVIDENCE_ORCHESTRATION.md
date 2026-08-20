# REV18 — V1 Evidence Orchestration / Release Candidate Promotion

REV18 closes the ordering and identity gap between a promoted production qualification and the final controlled V1 gate. It does **not** create any release evidence. It makes real evidence advance through one fail-closed, content-addressed state machine.

## Two source identities are intentional

A production qualification happens before its lock/freeze evidence can be merged by reviewed PR. Therefore a real V1 necessarily has two Git identities:

- `qualifiedSourceHeadSha`: the commit whose runtime trees (`src`, `engine/mte_engine`) were benchmark-qualified and frozen.
- `sourceHeadSha`: the later assembly/evidence commit from which the exact Extension/Engine candidates and controlled archive are produced.

These commits may differ only because release evidence was promoted. The v4 production freeze still re-hashes the current runtime trees and rejects any runtime drift. `controlled-release.json` now records both identities; treating them as one commit made the REV16/17 real promotion path impossible after a legitimate evidence PR merge.

## State machine

`scripts/v1_evidence_orchestrator.py` seals every checkpoint with `sessionSha256` and refuses stage skipping:

1. `qualification-promoted`
2. `controlled-assembled`
3. `native-smoke-complete`
4. `browser-smoke-complete`
5. `evidence-promoted`
6. `release-ready`

The session carries the release id/class, assembly commit, qualified runtime commit, lock/freeze identities, exact controlled-manifest digest, candidate/controlled workflow run ids, canonical Engine/browser observation digests, and the final promoted evidence digests.

## Automatic checkpoints

For `private-v1` / `public-v1`, `.github/workflows/controlled-release.yml` now:

- verifies candidate workflow provenance on the assembly commit;
- assembles the exact controlled archive;
- initializes orchestration from the already-promoted real locks/freeze;
- seals `controlled-assembled` with the four candidate run ids plus the current controlled-release run id;
- uploads that checkpoint beside the controlled archive.

`.github/workflows/smoke-controlled-release-engine.yml` downloads that exact checkpoint from the controlled-release run, executes all three protected native smoke jobs, validates the observations, and seals `native-smoke-complete` into the engine-smoke evidence artifact.

## Interactive Chrome handoff

Real Chrome acceptance remains intentionally interactive. Download the exact controlled archive and `native-smoke-complete.json`, then on each clean GUI machine run:

```bash
python scripts/record_exact_browser_smoke.py \
  --controlled-manifest /path/to/controlled-release.json \
  --orchestration-session /path/to/native-smoke-complete.json \
  --chrome /path/to/chrome \
  --expected-major 148 \
  --engine-target <target> \
  --fixture-url http://127.0.0.1:<port>/fixture.html \
  --output /secure/evidence/chrome-148.json
```

Repeat for the current audited Stable major. Each record contains the `native-smoke-complete` session digest and cannot be advanced by the orchestrator if it came from another checkpoint.

After both records exist:

```bash
python scripts/v1_evidence_orchestrator.py browser \
  --session /path/to/native-smoke-complete.json \
  --controlled-manifest /path/to/controlled-release.json \
  --browser-observation /secure/evidence/chrome-148.json \
  --browser-observation /secure/evidence/chrome-stable.json \
  --output /secure/evidence/browser-smoke-complete.json
```

## Transactional evidence promotion

Promotion now requires the `browser-smoke-complete` checkpoint. It stages profile/privacy, smoke records, release state, and the next `evidence-promoted` orchestration session before changing source state:

```bash
python scripts/promote_release_smoke_evidence.py \
  --controlled-manifest /path/to/controlled-release.json \
  --orchestration-session /secure/evidence/browser-smoke-complete.json \
  --engine-observation /secure/evidence/linux.json \
  --engine-observation /secure/evidence/macos.json \
  --engine-observation /secure/evidence/windows.json \
  --browser-observation /secure/evidence/chrome-148.json \
  --browser-observation /secure/evidence/chrome-stable.json
```

For real source paths the transaction now also updates `SOURCE_SHA256SUMS.txt`. If a replacement or the post-write source-integrity verification fails, already-replaced files are restored. This fixes the REV17 condition where valid smoke promotion would immediately make source-integrity stale.

The final V1 verifier requires `release-control/v1-orchestration.json` at `evidence-promoted` and re-hashes its referenced profile/privacy, smoke-records, release-state, controlled manifest and production freeze. `finalize` can produce a `release-ready` checkpoint only after `verify_controlled_release_ready.py` is actually green.

## What REV18 does not claim

No lockfile, production freeze, controlled archive, native smoke, browser smoke, profile fingerprint, or release-ready checkpoint is fabricated by REV18. The current developer-preview source remains fail-closed until the real evidence chain is executed.
