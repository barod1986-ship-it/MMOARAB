from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENGINE = ROOT / "engine"
sys.path.insert(0, str(ENGINE))

from mte_engine.benchmark.catalog import load_catalog  # noqa: E402
from mte_engine.benchmark.gate import load_policy  # noqa: E402


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


catalog_path = ENGINE / "model-catalog" / "model-candidates-v1.json"
policy_path = ENGINE / "benchmark" / "policies" / "benchmark-thresholds-v3.json"
catalog = load_catalog(catalog_path)
policy = load_policy(policy_path)
files = {
    "common": read("engine/mte_engine/benchmark/common.py"),
    "corpus": read("engine/mte_engine/benchmark/corpus.py"),
    "corpusSources": read("engine/mte_engine/benchmark/corpus_sources.py"),
    "corpusSourceRegistry": read("engine/benchmark/corpus/corpus-source-registry-v1.json"),
    "corpusSourceVerifier": read("engine/scripts/verify_corpus_sources.py"),
    "corpusRightsTests": read("engine/tests/test_corpus_rights.py"),
    "qualification": read("engine/scripts/run_production_qualification.py"),
    "preparedExecution": read("engine/scripts/execute_prepared_qualification.py"),
    "catalog": read("engine/mte_engine/benchmark/catalog.py"),
    "gate": read("engine/mte_engine/benchmark/gate.py"),
    "freeze": read("engine/mte_engine/benchmark/freeze.py"),
    "selection": read("engine/mte_engine/benchmark/selection.py"),
    "report": read("engine/mte_engine/benchmark/report_builder.py"),
    "profile": read("engine/mte_engine/profile.py"),
    "tests": read("engine/tests/test_benchmark_gate.py"),
    "runtime": read("engine/mte_engine/production_runtime.py"),
    "detectorRuntime": read("engine/mte_engine/pipeline/detector.py"),
    "translator": read("engine/mte_engine/pipeline/translator.py"),
    "roles": read("engine/mte_engine/pipeline/roles.py"),
    "inpaint": read("engine/mte_engine/pipeline/inpaint.py"),
    "productionTests": read("engine/tests/test_production_runtime.py"),
    "legacyTemplate": read("engine/benchmark/raw-benchmark.legacy-schema1.template.json"),
    "reviewTemplate": read("engine/benchmark/benchmark-review.template.json"),
    "execution": read("engine/mte_engine/benchmark/execution.py"),
    "executeCli": read("engine/scripts/execute_benchmark.py"),
    "reviewSealCli": read("engine/scripts/seal_benchmark_review.py"),
    "executorTests": read("engine/tests/test_benchmark_executor.py"),
    "provenance": read("engine/mte_engine/benchmark/provenance.py"),
    "candidatePlanModule": read("engine/mte_engine/benchmark/candidate_plan.py"),
    "runPlanModule": read("engine/mte_engine/benchmark/run_plan.py"),
    "candidatePlan": read("engine/benchmark/candidate-plan-v3.json"),
    "intake": read("engine/scripts/intake_model_artifact.py"),
    "preflight": read("engine/scripts/prepare_benchmark_run.py"),
    "sealCorpus": read("engine/scripts/seal_corpus_manifest.py"),
    "evaluateCli": read("engine/scripts/evaluate_benchmark.py"),
    "freezeCli": read("engine/scripts/freeze_production_profile.py"),
    "acquisitionTests": read("engine/tests/test_benchmark_acquisition.py"),
    "acquisition": read("engine/mte_engine/benchmark/acquisition.py"),
    "acquireCli": read("engine/scripts/acquire_official_artifact.py"),
    "sourceRegistry": read("engine/model-catalog/acquisition-source-registry-v3.json"),
    "sourceVerifier": read("engine/scripts/verify_acquisition_sources.py"),
    "acquisitionRecordVerifier": read("engine/scripts/verify_acquisition_record.py"),
    "manualArtifacts": read("engine/mte_engine/benchmark/manual_artifacts.py"),
    "manualPolicy": read("engine/model-catalog/manual-derived-artifact-policy-v1.json"),
    "manualPolicyVerifier": read("engine/scripts/verify_manual_artifact_policy.py"),
    "converterReviewTemplate": read("engine/model-catalog/converter-review.template.json"),
    "inpaintPackager": read("engine/scripts/prepare_inpaint_onnx_artifact.py"),
}
artifact_ids = {item["artifactId"] for item in catalog["artifacts"]}
coverage = policy.get("candidateCoverage", {})
checks = [
    ("REV10 corpus minimums are enforced", all(token in files["corpus"] for token in ['< 60', '< 10', 'zh-Hans', 'zh-Hant', 'groundTruthSfxPages', 'cleanReferencePages'])),
    ("every corpus page needs reviewed benchmark-use rights", 'rights.get("reviewed") is not True' in files["corpus"] and 'benchmarkUseAuthorized' in files["corpus"]),
    ("corpus rights review is attributable and evidence-bound", all(token in files["corpus"] for token in ["reviewRecordId", "reviewedBy", "reviewedAtUtc", "evidenceRef"])),
    ("production corpus schema-v2 is pinned to the active rights source registry", all(token in files["corpus"] for token in ["CORPUS_SCHEMA_VERSION = 2", "rev10-production-corpus-v2", "sourceRegistryRevision", "sourceRegistrySha256", "source_registry_digest"])),
    ("corpus rights records are content-addressed, page-scoped and independently rehashed", all(token in files["corpusSources"] for token in ["rights review digest mismatch", "rights review does not enumerate this page", "commercialV1QualificationAuthorized", "sourceWideEvidenceAllowed", "credential-free HTTPS"])),
    ("noncommercial public corpus is blocked while synthetic pages remain supplemental-only", all(token in files["corpusSourceRegistry"] for token in ["open-mantra-cc-by-nc-4.0", '"commercialQualificationAllowed": false', '"synthetic-self-authored"', '"supplemental-only"']) and "realDomainLanguageCounts" in files["corpus"]),
    ("corpus source verifier exposes production-eligible blocked and supplemental source classes", all(token in files["corpusSourceVerifier"] for token in ["productionEligibleSourceIds", "blockedSourceIds", "supplementalOnlySourceIds", "registrySha256"])),
    ("rights-chain regressions cover page scope tamper noncommercial exclusion and synthetic minimum bypass", all(token in files["corpusRightsTests"] for token in ["test_operator_rights_review_is_content_addressed_and_page_scoped", "test_tampered_rights_review_is_rejected", "test_noncommercial_public_source_is_blocked_for_production_v1", "test_synthetic_pages_cannot_satisfy_real_domain_minimums"])),
    ("two-phase production qualification separates stable reviewed prepare from execution/evaluation/freeze", all(token in files["qualification"] for token in ["rev13-production-qualification-prepare-v3", "acquire_official_artifact.py", "intake_model_artifact.py", "prepare_benchmark_run.py", "EXPECTED_AUTOMATED", "EXPECTED_MANUAL"]) and all(token in files["preparedExecution"] for token in ["rev11-prepared-qualification-execution-v1", "execute_benchmark.py", "evaluate_benchmark.py", "freeze_production_profile.py", "runPlanSha256", "gate_passed"])),
    ("corpus sealing computes hashes from bytes and refuses traversal/symlinks", all(token in files["sealCorpus"] for token in ["sha256_path(path)", "may not traverse symlinks", "conflicts with actual file bytes", "load_corpus(args.output, verify_files=True)"])),
    ("duplicate page hashes cannot inflate corpus counts", "duplicate imageSha256" in files["corpus"]),
    ("corpus images/annotations are bounded and path-contained", all(token in files["corpus"] for token in ["MAX_CORPUS_PAGES", "MAX_BLOCKS_PER_PAGE", "polygon leaves image bounds", "may not traverse symlinks"])),
    ("artifact catalog separates benchmark-use, code, artifact-license, redistribution and SHA state", all(token in files["catalog"] for token in ["benchmarkUseStatus", "artifactLicenseStatus", "redistributionStatus", "sha256_path"])),
    ("model paths cannot traverse symlinks or parent directories", all(token in files["catalog"] for token in ["safe relative path", "symlink model artifacts are refused", "artifact path escapes"])),
    ("PP-OCRv6 small/medium det+rec candidates are present", {"ppocrv6-small-det", "ppocrv6-medium-det", "ppocrv6-small-rec", "ppocrv6-medium-rec"}.issubset(artifact_ids)),
    ("Korean and manga-ocr routes have explicit candidates", {"ppocrv5-korean-mobile-rec", "manga-ocr-base-0.1.16"}.issubset(artifact_ids)),
    ("LaMa/AOT are explicit independent candidates", {"lama-big", "aot-gan-places2"}.issubset(artifact_ids)),
    ("Arabic production font is a separately pinned artifact", "noto-sans-arabic-production-font" in artifact_ids),
    ("comic-text-detector redistribution is not assumed from code license", next(item for item in catalog["artifacts"] if item["artifactId"] == "comic-text-detector-model")["redistributionStatus"] == "blocked"),
    ("comic-text-detector is explicitly excluded from V1 benchmark use", next(item for item in catalog["artifacts"] if item["artifactId"] == "comic-text-detector-model")["benchmarkUseStatus"] == "blocked" and "comic-text-detector-model" not in files["candidatePlan"]),
    ("candidate identities and artifact mappings are frozen independently of raw results", all(token in files["candidatePlanModule"] for token in ["compare_report_to_plan", "candidate_identity", "artifactIds"]) and "rev10-production-candidate-plan-v3" in files["candidatePlan"]),
    ("candidate plan contains exact current production candidates", all(token in files["candidatePlan"] for token in ["ppocrv6-small-detector-run", "ppocrv6-medium-detector-run", "ppocrv6-small-det", "ppocrv6-medium-det", "manga-ocr-base-0.1.16", "aot-gan-places2", "noto-sans-arabic-production-font"])),
    ("both V1 Paddle detector candidates have exact runtime artifact mappings", all(token in files["detectorRuntime"] for token in ['"ppocrv6-small-detector-run": "ppocrv6-small-det"', '"ppocrv6-medium-detector-run": "ppocrv6-medium-det"'])),
    ("artifact receipts bind bytes, catalog, review decisions and receipt content digest", all(token in files["provenance"] for token in ["receiptSha256", "artifactByteSize", "artifactFileCount", "reviewRecordId", "receipt artifactSha256 does not match catalog pin", "receipt does not match local artifact bytes"])),
    ("derived ONNX artifacts require independently reviewed checkpoint and converter provenance", all(token in files["provenance"] for token in ["sourceArtifactSha256", "converterReviewRecordId", "converterReviewFileSha256", "converterRevision", "converterSourceUrl", "derivation runtimeContract does not match catalog"]) and all(token in files["converterReviewTemplate"] for token in ["converterUseStatus", "converterLicenseStatus", "converterSourceSha256"])),
    ("manual-derived inpainting artifacts are dual-review bound, deterministic and runtime-smoke validated", all(token in files["manualArtifacts"] for token in ["rev10-inpaint-onnx-packager-v1", "load_converter_review", "inspect_inpaint_package", "validate_onnx_runtime", "CPUExecutionProvider", "smokeShapes"]) and all(token in files["inpaintPackager"] for token in ["source-checkpoint", "converter-review", "converter-source", "max(review['reviewedAtUtc']", "derivationSha256", "ZipInfo", "1980", "os.replace(tmp,args.output)"])),
    ("manual-derived policy exactly covers LaMa and AOT while the Arabic font is pinned to NotoSansArabic-v2.013", all(token in files["manualPolicy"] for token in ["lama-big", "aot-gan-places2", "mte-onnx-inpaint-contract-v1"]) and "NotoSansArabic-v2.013" in files["manualPolicyVerifier"]),
    ("artifact intake never downloads and only commits explicit local bytes after a review record", all(token in files["intake"] for token in ["No network download is performed", "--source", "--review", "--commit", "staged artifact digest changed during copy"])),
    ("primary-source acquisition registry is allowlisted, content-addressed and separate from review approval", all(token in files["acquisition"] for token in ["allowedHostSuffixes", "sourceRegistrySha256", "recordSha256", "outside the registered host allowlist"]) and "production-artifact-primary-sources-2026-08-19-v3" in files["sourceRegistry"] and "https-zip-member" in files["acquisition"]),
    ("official acquisition CLI is explicit-download, redirect-allowlisted, public-DNS-only, bounded and atomic", all(token in files["acquireCli"] for token in ["--download", "_AllowlistedRedirectHandler", "socket.getaddrinfo", "ipaddress.ip_address", "is_global", "Accept-Encoding", "identity", "max_bytes", "staging_root", "acquisition_record_digest"])),
    ("automated primary-source artifact intake requires the acquisition receipt", "Automated primary-source artifacts require --acquisition-record" in files["intake"] and "recordContentSha256" in files["provenance"]),
    ("active source verifier binds all V1 artifacts to catalog plan and policy without network access", all(token in files["sourceVerifier"] for token in ["candidate-plan-v3.json", "benchmark-thresholds-v3.json", "activeArtifactCount", "researchExcludedArtifactIds"])),
    ("acquisition-record verifier independently re-hashes local bytes and catalog/source identity without network access", all(token in files["acquisitionRecordVerifier"] for token in ["load_acquisition_record", "artifact_path=args.artifact", "catalogRevision mismatch", "verified"])),
    ("benchmark preflight pins corpus policy catalog candidate plan artifact receipt and executor digests", all(token in files["preflight"] for token in ["candidatePlanSha256", "artifactReceiptSha256s", "runPlanSha256", "corpusManifestSha256", "catalogSha256", "executor_pin"])),
    ("ready run plan is content-addressed and receipt-complete", all(token in files["runPlanModule"] for token in ["run plan content digest mismatch", "receipt map must exactly match artifact pins", "benchmark run plan is not ready"])),
    ("ready run plan pins the exact benchmark executor source", all(token in files["runPlanModule"] for token in ["benchmark run plan executor", "executor source digest is malformed", "rev10-production-benchmark-executor-v1"]) and "executor_source_digest" in files["execution"]),
    ("formal executor rehashes corpus policy catalog candidate plan artifacts and receipts before inference", all(token in files["execution"] for token in ["corpus manifest changed after run-plan creation", "benchmark policy changed after run-plan creation", "model catalog changed after run-plan creation", "candidate plan changed after run-plan creation", "artifact bytes changed after run-plan creation", "artifact receipt verification failed"])),
    ("schema-v2 raw evidence is executor-attested and machine-trace bound", all(token in files["execution"] for token in ["machineEvidence", "reviewSnapshot", "evidenceSha256", "raw benchmark was not produced for this run plan"]) and "_schema2_projection" in files["report"]),
    ("schema-v2 report recomputes candidate metrics instead of trusting candidate.metrics", all(token in files["report"] for token in ["detectorEvidence", "ocrEvidence", "review.inpaintingCandidates", "selected = select_winners(candidates, policy)"])),
    ("schema-v2 detector metrics are rebuilt from per-page traces rather than aggregate fields", "_rebuild_detection_from_page_rows" in files["report"] and "detectorPageRows" in files["report"]),
    ("schema-v2 execution coverage is bound exactly to corpus pages and eligible OCR blocks", "_check_schema2_execution_coverage" in files["gate"] and "does not exactly cover eligible corpus blocks" in files["gate"] and "performance execution evidence does not exactly cover corpus pages" in files["gate"]),
    ("benchmark performance measures the actual local detector OCR role inpaint path", "local-ml-detector-ocr-role-inpaint-v1" in files["execution"] and "production benchmark performance scope is missing or unsupported" in files["gate"]),
    ("long-webtoon detector scoring avoids one full-page mask per region and counts all binary foreground values", "_polygon_iou" in files["execution"] and "sum(histogram[1:])" in files["execution"] and "test_binary_mask_count_handles_direct_draw_and_imagechops_foreground_values" in files["executorTests"]),
    ("inpainting human-review release coverage is taken from the selected winner rather than summed across candidates", 'selected_inpaint_review' in files["report"] and 'selected["inpainter"]' in files["report"]),
    ("human review is sealed separately and bound into execution evidence", "reviewRecordSha256" in files["execution"] and "seal_review_draft" in files["reviewSealCli"] and "runPlanSha256" in files["reviewTemplate"]),
    ("official benchmark CLI consumes the ready run plan and writes executor evidence", all(token in files["executeCli"] for token in ["--run-plan", "--review", "execute_benchmark", "evidenceSha256"])),
    ("official evaluate and freeze CLIs require candidate plan receipts and run plan", all(token in files["evaluateCli"] and token in files["freezeCli"] for token in ["--candidate-plan", "--receipts-dir", "--run-plan"])),
    ("comparison matrix is versioned in release policy", coverage == {
        "detector": ["ppocrv6-small", "ppocrv6-medium"],
        "ocr-en": ["ppocrv6-small", "ppocrv6-medium"],
        "ocr-ja": ["manga-ocr", "ppocrv6"],
        "ocr-ko": ["korean-ppocrv5"],
        "ocr-zh": ["ppocrv6-small", "ppocrv6-medium"],
        "inpaint": ["lama", "aot"],
    }),
    ("release gate enforces the policy comparison matrix", "_check_candidate_coverage(report, policy)" in files["gate"]),
    ("every benchmarked winner or loser needs approved-use and a real matching local hash", all(token in files["gate"] for token in ["_check_benchmarked_artifacts", "benchmark use is not approved for artifact", "benchmarked artifact has no SHA-256 pin", "hash-mismatched"])),
    ("SFX release gates are exact zero", "EXACT_ZERO_SFX_FIELDS" in files["gate"] and '!= 0.0' in files["gate"]),
    ("production role revision and perfect protected-SFX recall are release-gated", policy.get("roleSafety", {}).get("productionRevision") == "visual-enclosure-sfx-guard-v1" and policy.get("roleSafety", {}).get("sfxProtectedRecallMin") == 1.0 and "roleClassifierSfxProtectedRecall" in files["gate"] and "classifier revision" in files["gate"]),
    ("production role runtime implements conservative visual enclosure grant", "VisualEnclosureRoleClassifier" in files["roles"] and "_enclosure_evidence" in files["roles"] and "_lexically_protect" in files["roles"]),
    ("language-specific detection/OCR/reading-order coverage is release-gated", all(token in files["gate"] for token in ["detectionByLanguage", "ocrSamplesMin", "readingOrderByLanguage", "translationPagesByLanguage"])),
    ("candidate winner is recomputed by the gate", "select_winners(report[\"candidates\"], policy)" in files["gate"]),
    ("unsafe detector is filtered before quality tie-breaking", "criticalFalseEraseCount" in files["selection"] and "dialogueRecall" in files["selection"]),
    ("Japanese OCR uses the same deterministic quality policy without a predetermined primary", 'component == "ocr-ja"' not in files["selection"] and 'policyRole' not in files["selection"] and "benchmark-frozen-japanese-winner" in read("engine/mte_engine/pipeline/ocr.py")),
    ("small OCR model only receives near-quality/latency exception", '+ 0.005' in files["selection"] and '* 0.85' in files["selection"]),
    ("raw benchmark metrics are recomputed rather than trusted", all(token in files["report"] for token in ["aggregate_ocr", "detection_metrics", "pairwise_order_accuracy"])),
    ("SFX safety metrics are recomputed from per-block raw evidence", all(token in files["report"] for token in ["sfxRows", "protectedFromEditing", "eraseInpaintOverlapPixels", "changedPixelsAfterEncodeDecode", "roleClassifierSfxProtectedRecall"])),
    ("SFX raw evidence is bound exactly to corpus annotation block IDs", all(token in files["gate"] for token in ["benchmark report is not the deterministic rebuild", "SFX raw evidence does not exactly cover corpus ground-truth SFX blocks", "groundTruthSfxBlocks"])),
    ("non-finite JSON numbers cannot bypass thresholds or hashes", "reject_nonfinite_numbers" in files["gate"] and "allow_nan=False" in files["common"]),
    ("legacy raw template is retained only as historical schema-v1 evidence", all(token in files["legacyTemplate"] for token in ["hardwareClass", "mangaOcrVersion", "torchVersion", "pillowVersion", "fontArtifactId", "ppocrv6-small-detector-run", "ppocrv6-medium-detector-run", "korean-ppocrv5", '"lama"', '"aot"'])),
    ("legacy raw schema already carried candidate/run hashes while active schema-v2 adds executor binding", all(token in files["legacyTemplate"] for token in ["candidatePlanSha256", "runPlanSha256"]) and "executorSourceSha256" in files["execution"]),
    ("freeze is content addressed and includes runtime, translation and renderer", all(token in files["freeze"] for token in ["freezeSha256", "canonical_json", '"runtime"', '"translation"', '"renderer"'])),
    ("profile fingerprint incorporates approved freeze data", '"benchmarkFreeze"' in files["profile"] and '"freezeSha256"' in files["profile"]),
    ("real model artifacts are rehashed before profile readiness", "_all_pinned_artifacts_present" in files["profile"] and "sha256_path(path) != expected" in files["profile"]),
    ("configured Arabic font must match frozen font digest", "_configured_font_matches_freeze" in files["profile"]),
    ("post-freeze runtime remains fail-closed on missing production dependencies/artifacts/provider config", 'assess_production_runtime' in files["profile"] and 'runtime-unavailable' in files["runtime"] and 'SUPPORTED_ROLE_CLASSIFIER_REVISIONS' in files["runtime"] and 'onnxruntime' in files["runtime"]),
    ("production inpainting runtime is frozen local ONNX and mask-bound", "mte-onnx-inpaint-contract-v1" in files["inpaint"] and "CPUExecutionProvider" in files["inpaint"] and "source * (1.0 - blend) + array * blend" in files["inpaint"]),
    ("LaMa/AOT catalog artifacts declare the MTE ONNX runtime contract", all(next(item for item in catalog["artifacts"] if item["artifactId"] == artifact).get("runtimeContract") == "mte-onnx-inpaint-contract-v1" for artifact in ("lama-big", "aot-gan-places2"))),
    ("production translation adapter is text-only, schema-constrained and explicit opt-in", all(token in files["translator"] for token in ["external-ocr-text-only-v1", "json_schema", "store", "manga/manhwa dialogue", "_OPENAI_RESPONSES_URL"]) and "external_text_translation_enabled" in files["runtime"]),
    ("production adapter regressions cover SFX fail-closed, visual grant, mask-bound inpaint and exact translation IDs", all(token in files["productionTests"] for token in ["test_unhinted_role_remains_protected", "test_production_role_gate_grants_only_strongly_enclosed_dialogue", "test_production_role_gate_preserves_sfx", "test_production_inpainter_changes_only_erase_mask_pixels", "test_openai_translator_sends_text_only", "test_openai_translator_rejects_missing_or_extra_ids"])),
    ("no production model weights are bundled in benchmark/model-artifacts", not any(p.is_file() for p in (ENGINE / "benchmark" / "model-artifacts").glob("**/*"))),
    ("no forged production freeze is bundled", not (ENGINE / "mte_engine" / "benchmark" / "production-profile-freeze.json").exists()),
    ("release policy declares itself project policy", policy.get("policyNature") == "project-release-policy-not-vendor-benchmark"),
    ("threshold revision is immutable by name", policy.get("policyRevision") == "benchmark-thresholds-v3"),
    ("artifact/executor regressions cover receipt tamper, conversion provenance, candidate swap, run-plan tamper and machine-trace override", all(token in files["acquisitionTests"] for token in ["test_artifact_receipt_binds_local_bytes_catalog_and_review", "test_derived_runtime_artifact_requires_conversion_provenance", "test_candidate_plan_exactly_binds_report_artifact_mapping", "test_ready_run_plan_is_content_addressed_and_receipt_complete", "test_active_v3_plan_has_exact_primary_source_registry_identity", "test_acquisition_record_binds_registered_url_local_bytes_and_registry", "test_intake_refuses_automated_primary_source_without_acquisition_record"]) and all(token in files["executorTests"] for token in ["test_schema2_manual_candidate_metric_override_cannot_change_report", "test_execution_attestation_rejects_trace_tamper_and_run_plan_reuse", "test_execution_input_rehash_rejects_artifact_changed_after_plan"])),
    ("tests cover exact-zero, freeze tamper, candidate coverage, losing-artifact approval, path containment and language gates", all(token in files["tests"] for token in [
        "test_any_nonzero_sfx_metric_blocks_freeze",
        "test_freeze_is_content_addressed_and_tamper_evident",
        "test_release_gate_requires_full_candidate_comparison_matrix",
        "test_benchmarked_loser_still_needs_approved_use_and_real_hash",
        "test_catalog_refuses_nested_symlink_artifact_path",
        "test_language_specific_quality_deficit_blocks_gate",
        "test_role_classifier_requires_perfect_sfx_recall_and_exact_production_revision",
    ])),
]
failed = False
for name, ok in checks:
    print(f"{'ok' if ok else 'not ok'} - {name}")
    failed |= not ok
print(f"# {len(checks)} Phase 5B benchmark-gate contract checks")
raise SystemExit(1 if failed else 0)
