# Production Corpus Rights Chain — REV10 V1

## Release rule

A production benchmark page is not admitted because it is public, downloadable, or because a caller sets `benchmarkUseAuthorized: true`. V1 requires a versioned source identity plus a content-addressed rights review record that is rehashed from disk when the corpus is loaded.

The active corpus contract is:

- schema: `2`;
- policy: `rev10-production-corpus-v2`;
- source registry: `engine/benchmark/corpus/corpus-source-registry-v1.json`;
- rights review schema: `engine/benchmark/corpus/rights-review.template.json`.

## Source classes

### Operator-owned or explicitly permissioned

`operator-owned-or-explicitly-permissioned` is the preferred path for English, Korean, Chinese and any page set for which the operator controls benchmark rights. Its review record must enumerate each covered `pageId`. Source-wide assertions are intentionally refused.

### Manga109-s

`manga109-s-v2026` is a conditional Japanese source. V1 treats it as eligible only after access has actually been granted and the operator records review of the current terms. Corpus bytes remain outside this repository and redistribution is not inferred from benchmark eligibility.

### OpenMantra

`open-mantra-cc-by-nc-4.0` is blocked from the default production/commercial V1 qualification path. It may not become eligible by changing a page boolean. If the operator obtains separate permission, those pages must instead use a separately reviewed operator-rights record.

### Synthetic/self-authored

`synthetic-self-authored` is useful for renderer, security and edge-case coverage. It is `supplemental-only`: such pages count toward structural coverage but cannot satisfy the real manga/manhwa/webtoon minimums for English, Japanese, Korean or Chinese.

## Rights review binding

Each page points to a review record with:

- stable `reviewRecordId`;
- source ID and revision;
- reviewer and UTC review time;
- explicit benchmark-use authorization;
- explicit production-V1 qualification authorization;
- redistribution decision;
- page-list or permitted source-wide coverage;
- at least one evidence reference;
- SHA-256 of the exact review file.

`seal_corpus_manifest.py` computes that digest from bytes. `load_corpus(..., verify_files=True)` recomputes it and validates page coverage, source policy, reviewer attribution, authorization fields and safe contained paths. Editing a review after sealing invalidates the corpus.

## Real-domain minimums

The production gate separately tracks `realDomainLanguageCounts`. Synthetic pages therefore cannot satisfy the minimum of 60 English pages, 10 Japanese pages, 10 Korean pages or 10 Chinese pages across Simplified/Traditional Chinese. Existing visual/SFX/clean-reference requirements continue to apply.

## Workflow

1. Place corpus bytes and annotations outside the repository.
2. Create reviewed rights records under the secure corpus root.
3. Fill `corpus-draft.template.json` with source identity and review paths.
4. Run `seal_corpus_manifest.py`; it hashes rights, image, annotation and clean-reference bytes.
5. Run `npm run check:corpus-sources` for the active source policy.
6. Run `prepare_benchmark_run.py` or the unified `run_production_qualification.py`. A ready run plan is impossible if the corpus rights chain fails.

This mechanism is a release-control policy and evidence chain. It does not fabricate legal permission; the operator must possess and review the underlying rights evidence.
