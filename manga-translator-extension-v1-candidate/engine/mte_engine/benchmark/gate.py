from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .catalog import artifact_by_id, load_catalog, resolve_artifact_path, selected_artifacts_release_ready
from .candidate_plan import candidate_plan_digest, compare_report_to_plan, load_candidate_plan, plan_artifact_ids
from .provenance import verify_receipts
from .run_plan import load_run_plan
from .execution import validate_raw_execution
from .common import canonical_json, finite_nonnegative, is_sha256, reject_nonfinite_numbers, require_dict, require_list, sha256_bytes
from .corpus import load_corpus, production_corpus_gate, validate_corpus
from .selection import SelectionError, select_winners

REPORT_SCHEMA_VERSION = 1
POLICY_SCHEMA_VERSION = 1
EXACT_ZERO_SFX_FIELDS = (
    "sentToTranslatorRate",
    "eraseInpaintMaskOverlapRate",
    "changedPixelRateAfterEncodeDecode",
    "uncertainDestructiveEditRate",
    "protectedConflictSilentOverwriteCount",
)


class BenchmarkGateError(ValueError):
    pass


def _check_schema2_execution_coverage(raw: dict[str, Any], corpus: dict[str, Any], *, corpus_path: Path) -> list[str]:
    """Bind executor traces to every corpus page/block expected for each component."""
    if raw.get("schemaVersion") != 2:
        return []
    reasons: list[str] = []
    try:
        execution = require_dict(raw.get("execution"), label="raw.execution")
        machine = require_dict(execution.get("machineEvidence"), label="raw.execution.machineEvidence")
        pages = require_list(corpus.get("pages"), label="corpus.pages")
        page_languages = {str(page["pageId"]): str(page["language"]) for page in pages}
        expected_pages = set(page_languages)

        detectors = require_dict(machine.get("detectorCandidates"), label="machineEvidence.detectorCandidates")
        for candidate_id, raw_evidence in detectors.items():
            evidence = require_dict(raw_evidence, label=f"detectorEvidence.{candidate_id}")
            rows = [require_dict(v, label=f"detectorEvidence.{candidate_id}.pageRow") for v in require_list(evidence.get("pageRows"), label=f"detectorEvidence.{candidate_id}.pageRows")]
            keys = [str(row.get("pageId", "")) for row in rows]
            if len(keys) != len(set(keys)) or set(keys) != expected_pages:
                reasons.append(f"detector execution evidence does not exactly cover corpus pages for {candidate_id}")
            elif any(row.get("language") != page_languages[str(row.get("pageId"))] for row in rows):
                reasons.append(f"detector execution evidence language mismatch for {candidate_id}")
            if len(require_list(evidence.get("durationsMs"), label=f"detectorEvidence.{candidate_id}.durationsMs")) != len(expected_pages):
                reasons.append(f"detector timing evidence does not exactly cover corpus pages for {candidate_id}")

        annotations: dict[str, dict[str, Any]] = {}
        expected_reading_pages: set[str] = set()
        expected_ocr: dict[str, set[tuple[str, str, str]]] = {"ocr-en": set(), "ocr-ja": set(), "ocr-ko": set(), "ocr-zh": set()}
        for page in pages:
            page_id = str(page["pageId"])
            language = str(page["language"])
            annotation_path = (corpus_path.parent / str(page["annotationPath"])).resolve()
            annotation = require_dict(json.loads(annotation_path.read_text(encoding="utf-8")), label=f"{page_id}.annotation")
            annotations[page_id] = annotation
            text_blocks: list[dict[str, Any]] = []
            for block in require_list(annotation.get("blocks"), label=f"{page_id}.annotation.blocks"):
                item = require_dict(block, label=f"{page_id}.block")
                if item.get("kind") not in {"dialogue", "narration"}:
                    continue
                text_blocks.append(item)
                component = {"en": "ocr-en", "ja": "ocr-ja", "ko": "ocr-ko", "zh-Hans": "ocr-zh", "zh-Hant": "ocr-zh"}[language]
                expected_ocr[component].add((page_id, str(item["blockId"]), language))
            if len(text_blocks) >= 2 and all(isinstance(item.get("readingOrder"), int) and not isinstance(item.get("readingOrder"), bool) for item in text_blocks):
                expected_reading_pages.add(page_id)

        components = {str(item.get("candidateId")): str(item.get("component")) for item in require_list(raw.get("candidates"), label="raw.candidates") if isinstance(item, dict)}
        ocr_candidates = require_dict(machine.get("ocrCandidates"), label="machineEvidence.ocrCandidates")
        for candidate_id, raw_evidence in ocr_candidates.items():
            component = components.get(str(candidate_id), "")
            expected = expected_ocr.get(component)
            if expected is None:
                reasons.append(f"OCR execution evidence has unsupported component for {candidate_id}")
                continue
            evidence = require_dict(raw_evidence, label=f"ocrEvidence.{candidate_id}")
            rows = [require_dict(v, label=f"ocrEvidence.{candidate_id}.row") for v in require_list(evidence.get("rows"), label=f"ocrEvidence.{candidate_id}.rows")]
            actual = [(str(row.get("pageId", "")), str(row.get("blockId", "")), str(row.get("language", ""))) for row in rows]
            if len(actual) != len(set(actual)) or set(actual) != expected:
                reasons.append(f"OCR execution evidence does not exactly cover eligible corpus blocks for {candidate_id}")
            if len(require_list(evidence.get("durationsMs"), label=f"ocrEvidence.{candidate_id}.durationsMs")) != len(expected):
                reasons.append(f"OCR timing evidence does not exactly cover eligible corpus blocks for {candidate_id}")

        expected_clean_pages = {str(page["pageId"]) for page in pages if isinstance(page.get("cleanReferencePath"), str)}
        inpaint_candidates = require_dict(machine.get("inpaintCandidates"), label="machineEvidence.inpaintCandidates")
        for candidate_id, raw_evidence in inpaint_candidates.items():
            evidence = require_dict(raw_evidence, label=f"inpaintEvidence.{candidate_id}")
            rows = [require_dict(v, label=f"inpaintEvidence.{candidate_id}.cleanReferenceRow") for v in require_list(evidence.get("cleanReferenceRows"), label=f"inpaintEvidence.{candidate_id}.cleanReferenceRows")]
            actual = [str(row.get("pageId", "")) for row in rows]
            if len(actual) != len(set(actual)) or set(actual) != expected_clean_pages:
                reasons.append(f"inpainting execution evidence does not exactly cover clean-reference pages for {candidate_id}")
            if len(require_list(evidence.get("durationsMs"), label=f"inpaintEvidence.{candidate_id}.durationsMs")) != len(expected_clean_pages):
                reasons.append(f"inpainting timing evidence does not exactly cover clean-reference pages for {candidate_id}")

        reading_rows = [require_dict(v, label="readingOrderRow") for v in require_list(machine.get("readingOrderRows"), label="machineEvidence.readingOrderRows")]
        reading_pages = [str(row.get("pageId", "")) for row in reading_rows if "pageId" in row]
        # Legacy executor rows did not carry pageId; schema-v2 production rows must.
        if set(reading_pages) != expected_reading_pages or len(reading_pages) != len(set(reading_pages)):
            reasons.append("reading-order execution evidence does not exactly cover eligible corpus pages")
        if len(require_list(machine.get("pageSeconds"), label="machineEvidence.pageSeconds")) != len(expected_pages):
            reasons.append("performance execution evidence does not exactly cover corpus pages")
    except (OSError, json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
        reasons.append(f"schema-v2 execution coverage cannot be validated: {exc}")
    return reasons


def load_policy(path: Path) -> dict[str, Any]:
    try:
        policy = require_dict(json.loads(path.read_text(encoding="utf-8")), label="benchmark policy")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise BenchmarkGateError(f"Cannot read benchmark policy: {exc}") from exc
    try:
        reject_nonfinite_numbers(policy, label="benchmark policy")
    except ValueError as exc:
        raise BenchmarkGateError(str(exc)) from exc
    if policy.get("schemaVersion") != POLICY_SCHEMA_VERSION or not isinstance(policy.get("policyRevision"), str):
        raise BenchmarkGateError("Benchmark policy schema/revision is invalid")
    return policy


def load_report(path: Path) -> dict[str, Any]:
    try:
        report = require_dict(json.loads(path.read_text(encoding="utf-8")), label="benchmark report")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise BenchmarkGateError(f"Cannot read benchmark report: {exc}") from exc
    validate_report(report)
    return report


def validate_report(report: dict[str, Any]) -> None:
    try:
        reject_nonfinite_numbers(report, label="benchmark report")
    except ValueError as exc:
        raise BenchmarkGateError(str(exc)) from exc
    if report.get("schemaVersion") != REPORT_SCHEMA_VERSION:
        raise BenchmarkGateError("Unsupported benchmark report schemaVersion")
    for key in ("reportId", "reportBuilderRevision", "rawBenchmarkSha256", "corpusId", "corpusManifestSha256", "policyRevision"):
        if not isinstance(report.get(key), str) or not report[key]:
            raise BenchmarkGateError(f"Benchmark report requires {key}")
    if not is_sha256(report.get("corpusManifestSha256")):
        raise BenchmarkGateError("corpusManifestSha256 is malformed")
    if not is_sha256(report.get("rawBenchmarkSha256")):
        raise BenchmarkGateError("rawBenchmarkSha256 is malformed")
    if report.get("reportBuilderRevision") != "phase5b-report-builder-v4-executor-bound":
        raise BenchmarkGateError("Unsupported reportBuilderRevision")
    runtime = require_dict(report.get("runtime"), label="runtime")
    for key in ("pythonVersion", "os", "cpu", "gpu", "hardwareClass", "paddlePaddleVersion", "paddleOcrVersion", "mangaOcrVersion", "torchVersion", "pillowVersion"):
        if not isinstance(runtime.get(key), str) or not runtime[key].strip():
            raise BenchmarkGateError(f"runtime.{key} is required")
    candidates = require_list(report.get("candidates"), label="candidates")
    if not candidates or len(candidates) > 64:
        raise BenchmarkGateError("Benchmark must contain 1..64 candidate results")
    candidate_ids: set[str] = set()
    allowed_components = {"detector", "ocr-en", "ocr-ja", "ocr-ko", "ocr-zh", "inpaint"}
    for idx, raw in enumerate(candidates):
        candidate = require_dict(raw, label=f"candidates[{idx}]")
        for key in ("candidateId", "component", "family", "artifactIds"):
            if key not in candidate:
                raise BenchmarkGateError(f"candidate is missing {key}")
        if not isinstance(candidate["candidateId"], str) or not candidate["candidateId"] or len(candidate["candidateId"]) > 128 or candidate["candidateId"] in candidate_ids:
            raise BenchmarkGateError("candidate IDs must be unique bounded strings")
        candidate_ids.add(candidate["candidateId"])
        if candidate["component"] not in allowed_components:
            raise BenchmarkGateError("candidate component is unsupported")
        if not isinstance(candidate["family"], str) or not candidate["family"] or len(candidate["family"]) > 128:
            raise BenchmarkGateError("candidate family must be a bounded string")
        artifact_ids = require_list(candidate["artifactIds"], label="candidate.artifactIds")
        if not artifact_ids or len(artifact_ids) > 16 or any(not isinstance(v, str) or not v for v in artifact_ids):
            raise BenchmarkGateError("candidate artifactIds must be a non-empty bounded string array")
        if len(set(artifact_ids)) != len(artifact_ids):
            raise BenchmarkGateError("candidate artifactIds must not contain duplicates")
        metrics = require_dict(candidate.get("metrics"), label="candidate.metrics")
        _validate_candidate_metrics(candidate, metrics)
    sfx = require_dict(report.get("sfxSafety"), label="sfxSafety")
    for field in EXACT_ZERO_SFX_FIELDS:
        finite_nonnegative(sfx.get(field), label=f"sfxSafety.{field}")
    _rate(sfx.get("roleClassifierSfxProtectedRecall"), label="sfxSafety.roleClassifierSfxProtectedRecall")
    evidence = require_dict(sfx.get("evidence"), label="sfxSafety.evidence")
    _evidence_tuples(require_list(evidence.get("sfxBlocks"), label="sfxSafety.evidence.sfxBlocks"), label="sfx")
    _evidence_tuples(require_list(evidence.get("uncertainBlocks"), label="sfxSafety.evidence.uncertainBlocks"), label="uncertain")
    require_dict(report.get("quality"), label="quality")
    require_dict(report.get("performance"), label="performance")
    require_dict(report.get("humanReview"), label="humanReview")
    renderer = require_dict(report.get("renderer"), label="renderer")
    for key in ("adapterRevision", "fontArtifactId", "goldenSuiteRevision"):
        if not isinstance(renderer.get(key), str) or not renderer[key].strip():
            raise BenchmarkGateError(f"renderer.{key} is required")
    translation = require_dict(report.get("translation"), label="translation")
    for key in ("adapterId", "modelOrProviderRevision", "contextMode", "privacyMode", "roleClassifierRevision"):
        if not isinstance(translation.get(key), str) or not translation[key].strip():
            raise BenchmarkGateError(f"translation.{key} is required")


def _rate(value: object, *, label: str) -> float:
    number = finite_nonnegative(value, label=label)
    if number > 1.0:
        raise BenchmarkGateError(f"{label} must be in the range 0..1")
    return number


def _nonnegative_integer(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise BenchmarkGateError(f"{label} must be a non-negative integer")
    return value


def _validate_candidate_metrics(candidate: dict[str, Any], metrics: dict[str, Any]) -> None:
    label = str(candidate.get("candidateId", "candidate"))
    component = candidate.get("component")
    if component == "detector":
        for key in ("dialogueRecall", "precision", "f1", "artworkFalsePositiveAreaRate"):
            _rate(metrics.get(key), label=f"{label}.metrics.{key}")
        _nonnegative_integer(metrics.get("criticalFalseEraseCount"), label=f"{label}.metrics.criticalFalseEraseCount")
        finite_nonnegative(metrics.get("p95Ms"), label=f"{label}.metrics.p95Ms")
        finite_nonnegative(metrics.get("peakMemoryMiB"), label=f"{label}.metrics.peakMemoryMiB")
    elif isinstance(component, str) and component.startswith("ocr-"):
        finite_nonnegative(metrics.get("cer"), label=f"{label}.metrics.cer")
        finite_nonnegative(metrics.get("p95Ms"), label=f"{label}.metrics.p95Ms")
        _nonnegative_integer(metrics.get("modelBytes"), label=f"{label}.metrics.modelBytes")
    elif component == "inpaint":
        _nonnegative_integer(metrics.get("humanCriticalFailures"), label=f"{label}.metrics.humanCriticalFailures")
        score = finite_nonnegative(metrics.get("humanScore"), label=f"{label}.metrics.humanScore")
        if score > 5.0:
            raise BenchmarkGateError(f"{label}.metrics.humanScore must be in the range 0..5")
        finite_nonnegative(metrics.get("p95Ms"), label=f"{label}.metrics.p95Ms")
        finite_nonnegative(metrics.get("peakMemoryMiB"), label=f"{label}.metrics.peakMemoryMiB")


def evaluate_release_gate(*, corpus_path: Path, raw_path: Path, report_path: Path, policy_path: Path, catalog_path: Path, artifacts_dir: Path, candidate_plan_path: Path | None = None, receipts_dir: Path | None = None, run_plan_path: Path | None = None, verify_corpus_files: bool = True) -> dict[str, Any]:
    corpus = load_corpus(corpus_path, verify_files=verify_corpus_files)
    corpus_summary = validate_corpus(corpus, base_dir=corpus_path.parent, verify_files=verify_corpus_files)
    corpus_ok, corpus_reasons = production_corpus_gate(corpus_summary)
    policy = load_policy(policy_path)
    report = load_report(report_path)
    catalog = load_catalog(catalog_path)

    reasons: list[str] = list(corpus_reasons)
    raw: dict[str, Any] | None = None
    try:
        raw = require_dict(json.loads(raw_path.read_text(encoding="utf-8")), label="raw benchmark")
        reject_nonfinite_numbers(raw, label="raw benchmark")
        from .report_builder import build_report
        rebuilt_report = build_report(raw, policy)
        if canonical_json(rebuilt_report) != canonical_json(report):
            reasons.append("benchmark report is not the deterministic rebuild of the supplied raw evidence")
    except (OSError, json.JSONDecodeError, ValueError, TypeError, KeyError) as exc:
        reasons.append(f"raw benchmark evidence cannot be deterministically rebuilt: {exc}")
    if raw is not None and verify_corpus_files:
        reasons.extend(_check_schema2_execution_coverage(raw, corpus, corpus_path=corpus_path))
    if report["corpusId"] != corpus["corpusId"]:
        reasons.append("benchmark report corpusId does not match corpus manifest")
    expected_corpus_digest = sha256_bytes(canonical_json(corpus))
    if report["corpusManifestSha256"] != expected_corpus_digest:
        reasons.append("benchmark report corpus manifest digest mismatch")
    if report["policyRevision"] != policy["policyRevision"]:
        reasons.append("benchmark report policyRevision mismatch")

    candidate_plan = None
    if candidate_plan_path is not None:
        try:
            candidate_plan = load_candidate_plan(candidate_plan_path, catalog=catalog, policy=policy)
            reasons.extend(compare_report_to_plan(report, candidate_plan))
            expected_plan_digest = candidate_plan_digest(candidate_plan)
            if report.get("candidatePlanSha256") != expected_plan_digest:
                reasons.append("benchmark report candidatePlanSha256 does not match the frozen candidate plan")
            if raw is None or raw.get("candidatePlanSha256") != expected_plan_digest:
                reasons.append("raw benchmark candidatePlanSha256 does not match the frozen candidate plan")
        except (ValueError, OSError) as exc:
            reasons.append(f"candidate plan cannot be validated: {exc}")

    receipt_ids: list[str] = []
    if candidate_plan is not None:
        receipt_ids = plan_artifact_ids(candidate_plan)
    else:
        for candidate in report["candidates"]:
            for artifact_id in candidate["artifactIds"]:
                if artifact_id not in receipt_ids:
                    receipt_ids.append(artifact_id)
        font_id = require_dict(report.get("renderer"), label="renderer").get("fontArtifactId")
        if isinstance(font_id, str) and font_id not in receipt_ids:
            receipt_ids.append(font_id)
    if receipts_dir is not None:
        receipts_ok, receipt_reasons, _ = verify_receipts(catalog, receipt_ids, receipts_dir=receipts_dir, artifacts_dir=artifacts_dir)
        if not receipts_ok:
            reasons.extend(receipt_reasons)

    run_plan = None
    if run_plan_path is not None:
        try:
            run_plan = load_run_plan(run_plan_path, require_ready=True)
            if raw is None or raw.get("runPlanSha256") != run_plan["runPlanSha256"]:
                reasons.append("raw benchmark runPlanSha256 does not match the ready benchmark run plan")
            if report.get("runPlanSha256") != run_plan["runPlanSha256"]:
                reasons.append("benchmark report runPlanSha256 does not match the ready benchmark run plan")
            if raw is None:
                reasons.append("production benchmark raw evidence is missing")
            else:
                try:
                    validate_raw_execution(raw, run_plan=run_plan)
                except ValueError as exc:
                    reasons.append(f"production benchmark executor evidence is invalid: {exc}")
            if run_plan["corpusManifestSha256"] != expected_corpus_digest:
                reasons.append("benchmark run plan corpus digest does not match corpus")
            if run_plan["policySha256"] != sha256_bytes(canonical_json(policy)):
                reasons.append("benchmark run plan policy digest does not match policy")
            if run_plan["catalogSha256"] != sha256_bytes(canonical_json(catalog)):
                reasons.append("benchmark run plan catalog digest does not match catalog")
            if candidate_plan is not None and run_plan["candidatePlanSha256"] != candidate_plan_digest(candidate_plan):
                reasons.append("benchmark run plan candidate-plan digest mismatch")
        except (ValueError, OSError) as exc:
            reasons.append(f"benchmark run plan cannot be validated: {exc}")

    reasons.extend(_check_sfx(report, corpus_summary, policy))
    reasons.extend(_check_quality(report, policy))
    reasons.extend(_check_human_review(report, policy))
    reasons.extend(_check_performance(report, policy, corpus_summary))
    reasons.extend(_check_candidate_coverage(report, policy))
    reasons.extend(_check_benchmarked_artifacts(report, catalog, artifacts_dir))
    try:
        expected_selected = select_winners(report["candidates"], policy)
    except (SelectionError, ValueError, KeyError, TypeError) as exc:
        expected_selected = None
        reasons.append(f"candidate selection cannot be reproduced: {exc}")
    if expected_selected is not None and report.get("selected") != expected_selected:
        reasons.append("selected candidates do not match deterministic selection policy")
    selected_ids = _selected_artifacts(report)
    artifacts_ok, artifact_reasons = selected_artifacts_release_ready(catalog, selected_ids, artifacts_dir=artifacts_dir)
    if not artifacts_ok:
        reasons.extend(artifact_reasons)

    selectors = require_dict(report.get("selected"), label="selected")
    for component in ("detector", "ocrEnglish", "ocrJapanese", "ocrKorean", "ocrChinese", "inpainter"):
        if not isinstance(selectors.get(component), str) or not selectors[component]:
            reasons.append(f"selected.{component} is required")

    by_artifact_id = artifact_by_id(catalog)
    selected_pins = [
        {
            "artifactId": artifact_id,
            "kind": by_artifact_id[artifact_id]["kind"],
            "expectedFilename": by_artifact_id[artifact_id]["expectedFilename"],
            "sha256": by_artifact_id[artifact_id].get("sha256"),
            "provisioning": by_artifact_id[artifact_id]["redistributionStatus"],
            "artifactLicenseStatus": by_artifact_id[artifact_id]["artifactLicenseStatus"],
            "codeLicense": by_artifact_id[artifact_id]["codeLicense"],
            "upstreamProject": by_artifact_id[artifact_id]["upstreamProject"],
            "upstreamRevision": by_artifact_id[artifact_id]["upstreamRevision"],
        }
        for artifact_id in selected_ids if artifact_id in by_artifact_id
    ]
    gate = {
        "schemaVersion": 1,
        "gateRevision": "production-ml-benchmark-gate-v1",
        "passed": corpus_ok and not reasons,
        "reasons": sorted(set(reasons)),
        "corpusSummary": corpus_summary,
        "selectedArtifactIds": selected_ids,
        "selectedArtifacts": selected_pins,
        "reportSha256": sha256_bytes(canonical_json(report)),
        "policySha256": sha256_bytes(canonical_json(policy)),
        "catalogSha256": sha256_bytes(canonical_json(catalog)),
        "candidatePlanSha256": candidate_plan_digest(candidate_plan) if candidate_plan is not None else None,
        "runPlanSha256": report.get("runPlanSha256") if run_plan_path is not None else None,
        "dependencyLocks": run_plan.get("dependencyLocks") if isinstance(run_plan, dict) else None,
    }
    return gate


def _check_candidate_coverage(report: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    by_component: dict[str, set[str]] = {}
    for candidate in report["candidates"]:
        by_component.setdefault(str(candidate["component"]), set()).add(str(candidate["family"]))
    requirements = require_dict(policy.get("candidateCoverage"), label="candidateCoverage")
    reasons: list[str] = []
    for component, raw_families in requirements.items():
        required = require_list(raw_families, label=f"candidateCoverage.{component}")
        actual = by_component.get(component, set())
        for family in required:
            if not isinstance(family, str) or not family:
                raise BenchmarkGateError(f"candidateCoverage.{component} contains an invalid family")
            if family not in actual:
                reasons.append(f"benchmark candidate coverage is incomplete for {component}: missing family {family}")
    return reasons


def _check_benchmarked_artifacts(report: dict[str, Any], catalog: dict[str, Any], artifacts_dir: Path) -> list[str]:
    by_id = artifact_by_id(catalog)
    reasons: list[str] = []
    used: set[str] = set()
    for candidate in report["candidates"]:
        used.update(str(value) for value in candidate["artifactIds"])
    for artifact_id in sorted(used):
        item = by_id.get(artifact_id)
        if item is None:
            reasons.append(f"benchmarked artifact is absent from catalog: {artifact_id}")
            continue
        if item.get("benchmarkUseStatus") != "approved":
            reasons.append(f"benchmark use is not approved for artifact: {artifact_id}")
        sha = item.get("sha256")
        if not is_sha256(sha):
            reasons.append(f"benchmarked artifact has no SHA-256 pin: {artifact_id}")
            continue
        from .common import sha256_path
        try:
            path = resolve_artifact_path(artifacts_dir, str(item["expectedFilename"]), artifact_id=artifact_id)
            if not path.exists() or sha256_path(path) != sha:
                reasons.append(f"benchmarked local artifact is missing or hash-mismatched: {artifact_id}")
        except (OSError, ValueError):
            reasons.append(f"benchmarked local artifact cannot be safely hashed: {artifact_id}")
    return reasons


def _evidence_tuples(rows: list[Any], *, label: str) -> set[tuple[str, str, str]]:
    values: set[tuple[str, str, str]] = set()
    for index, raw in enumerate(rows):
        row = require_dict(raw, label=f"{label}Evidence[{index}]")
        page_id, block_id, language = row.get("pageId"), row.get("blockId"), row.get("language")
        if not all(isinstance(value, str) and value for value in (page_id, block_id, language)):
            raise BenchmarkGateError(f"{label} evidence requires pageId/blockId/language")
        key = (page_id, block_id, language)
        if key in values:
            raise BenchmarkGateError(f"{label} evidence contains duplicate corpus block keys")
        values.add(key)
    return values


def _check_sfx(report: dict[str, Any], corpus_summary: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    sfx = report["sfxSafety"]
    reasons = []
    for field in EXACT_ZERO_SFX_FIELDS:
        if float(sfx[field]) != 0.0:
            reasons.append(f"SFX release gate requires exact zero: {field}")
    role_policy = require_dict(policy.get("roleSafety"), label="roleSafety")
    required_revision = role_policy.get("productionRevision")
    required_recall = float(role_policy.get("sfxProtectedRecallMin", 1.0))
    if not isinstance(required_revision, str) or not required_revision:
        raise BenchmarkGateError("roleSafety.productionRevision is required")
    translation = require_dict(report.get("translation"), label="translation")
    if translation.get("roleClassifierRevision") != required_revision:
        reasons.append("benchmarked role/SFX classifier revision does not match production release policy")
    recall = _rate(sfx.get("roleClassifierSfxProtectedRecall"), label="sfxSafety.roleClassifierSfxProtectedRecall")
    if recall < required_recall:
        reasons.append("role/SFX protected recall is below the production safety floor")
    evidence = require_dict(sfx.get("evidence"), label="sfxSafety.evidence")
    reported_sfx = _evidence_tuples(require_list(evidence.get("sfxBlocks"), label="sfxSafety.evidence.sfxBlocks"), label="sfx")
    reported_uncertain = _evidence_tuples(require_list(evidence.get("uncertainBlocks"), label="sfxSafety.evidence.uncertainBlocks"), label="uncertain")
    expected_sfx = {(item["pageId"], item["blockId"], item["language"]) for item in corpus_summary.get("groundTruthSfxBlocks", [])}
    expected_uncertain = {(item["pageId"], item["blockId"], item["language"]) for item in corpus_summary.get("groundTruthUncertainBlocks", [])}
    if reported_sfx != expected_sfx:
        reasons.append("SFX raw evidence does not exactly cover corpus ground-truth SFX blocks")
    if reported_uncertain != expected_uncertain:
        reasons.append("uncertain-block raw evidence does not exactly cover corpus ground truth")
    if int(sfx.get("independentGroundTruthPages", 0)) < 10:
        reasons.append("SFX gate requires at least 10 independently annotated pages")
    expected = corpus_summary.get("groundTruthSfxPagesByLanguage", {})
    measured = sfx.get("independentGroundTruthPagesByLanguage", {})
    if isinstance(expected, dict) and isinstance(measured, dict):
        for language, count in expected.items():
            if int(measured.get(language, 0)) < int(count):
                reasons.append(f"SFX benchmark did not exercise every annotated {language} page")
    return reasons


def _check_quality(report: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    q = report["quality"]
    thresholds = require_dict(policy.get("qualityThresholds"), label="qualityThresholds")
    reasons: list[str] = []
    detection = require_dict(q.get("detection"), label="quality.detection")
    if float(detection.get("dialogueRecall", 0)) < float(thresholds["dialogueRecallMin"]):
        reasons.append("dialogue detection recall is below release policy")
    if float(detection.get("precision", 0)) < float(thresholds["detectionPrecisionMin"]):
        reasons.append("detection precision is below release policy")
    if int(detection.get("criticalFalseEraseCount", 0)) != 0:
        reasons.append("critical false erase count must be zero")
    if float(detection.get("artworkFalsePositiveAreaRate", 1)) > float(thresholds["artworkFalsePositiveAreaRateMax"]):
        reasons.append("artwork false-positive area exceeds release policy")
    if float(detection.get("maskOverreachRate", 1)) > float(thresholds["maskOverreachRateMax"]):
        reasons.append("mask overreach exceeds release policy")
    if float(detection.get("maskUndercoverageRate", 1)) > float(thresholds["maskUndercoverageRateMax"]):
        reasons.append("mask under-coverage exceeds release policy")

    detection_by_language = require_dict(q.get("detectionByLanguage"), label="quality.detectionByLanguage")
    recall_min = require_dict(thresholds.get("dialogueRecallMinByLanguage"), label="dialogueRecallMinByLanguage")
    precision_min = require_dict(thresholds.get("detectionPrecisionMinByLanguage"), label="detectionPrecisionMinByLanguage")
    for lang, minimum in recall_min.items():
        metrics = require_dict(detection_by_language.get(lang), label=f"quality.detectionByLanguage.{lang}")
        if float(metrics.get("dialogueRecall", 0)) < float(minimum):
            reasons.append(f"dialogue detection recall is below release policy for {lang}")
        if float(metrics.get("precision", 0)) < float(precision_min[lang]):
            reasons.append(f"detection precision is below release policy for {lang}")
        if int(metrics.get("criticalFalseEraseCount", 0)) != 0:
            reasons.append(f"critical false erase count must be zero for {lang}")

    ocr = require_dict(q.get("ocr"), label="quality.ocr")
    ocr_thresholds = require_dict(thresholds.get("ocrCerMax"), label="qualityThresholds.ocrCerMax")
    sample_mins = require_dict(thresholds.get("ocrSamplesMin"), label="qualityThresholds.ocrSamplesMin")
    for lang, maximum in ocr_thresholds.items():
        metrics = require_dict(ocr.get(lang), label=f"quality.ocr.{lang}")
        if int(metrics.get("samples", 0)) < int(sample_mins[lang]):
            reasons.append(f"OCR benchmark has insufficient samples for {lang}")
        elif float(metrics.get("cer", 1)) > float(maximum):
            reasons.append(f"OCR CER exceeds release policy for {lang}")

    if float(q.get("readingOrderPairwiseAccuracy", 0)) < float(thresholds["readingOrderPairwiseAccuracyMin"]):
        reasons.append("reading-order accuracy is below release policy")
    order_by_language = require_dict(q.get("readingOrderByLanguage"), label="quality.readingOrderByLanguage")
    order_min = require_dict(thresholds.get("readingOrderPairwiseAccuracyMinByLanguage"), label="readingOrderPairwiseAccuracyMinByLanguage")
    order_pages_min = require_dict(thresholds.get("readingOrderPagesMin"), label="readingOrderPagesMin")
    for lang, minimum in order_min.items():
        metrics = require_dict(order_by_language.get(lang), label=f"quality.readingOrderByLanguage.{lang}")
        if int(metrics.get("pages", 0)) < int(order_pages_min[lang]):
            reasons.append(f"reading-order benchmark has insufficient pages for {lang}")
        elif float(metrics.get("pairwiseAccuracy", 0)) < float(minimum):
            reasons.append(f"reading-order accuracy is below release policy for {lang}")
    if int(q.get("arabicRendererGoldensFailed", 1)) != 0 or int(q.get("arabicRendererGoldensRun", 0)) < int(thresholds["arabicRendererGoldensMin"]):
        reasons.append("Arabic renderer golden gate failed or has insufficient coverage")
    return reasons


def _check_human_review(report: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    review = report["humanReview"]
    thresholds = require_dict(policy.get("humanReviewThresholds"), label="humanReviewThresholds")
    reasons: list[str] = []
    if int(review.get("translationPagesReviewed", 0)) < int(thresholds["translationPagesMin"]):
        reasons.append("translation human-review sample is below release policy")
    by_language = require_dict(review.get("translationPagesByLanguage"), label="humanReview.translationPagesByLanguage")
    by_language_min = require_dict(thresholds.get("translationPagesByLanguageMin"), label="translationPagesByLanguageMin")
    for lang, minimum in by_language_min.items():
        if int(by_language.get(lang, 0)) < int(minimum):
            reasons.append(f"translation human-review sample is below release policy for {lang}")
    if int(review.get("inpaintingPagesReviewed", 0)) < int(thresholds["inpaintingPagesMin"]):
        reasons.append("inpainting human-review sample is below release policy")
    if int(review.get("criticalTranslationFailures", 1)) != 0:
        reasons.append("critical translation failures must be zero")
    if int(review.get("criticalInpaintingFailures", 1)) != 0:
        reasons.append("critical inpainting failures must be zero")
    naturalness = float(review.get("arabicNaturalnessMean", 0))
    if naturalness > 5.0 or naturalness < float(thresholds["arabicNaturalnessMeanMin"]):
        reasons.append("Arabic naturalness mean is outside the accepted 1..5 release range")
    return reasons


def _check_performance(report: dict[str, Any], policy: dict[str, Any], corpus_summary: dict[str, Any]) -> list[str]:
    perf = report["performance"]
    thresholds = require_dict(policy.get("performanceGuardrails"), label="performanceGuardrails")
    reasons: list[str] = []
    if report.get("execution") is not None and perf.get("scope") != "local-ml-detector-ocr-role-inpaint-v1":
        reasons.append("production benchmark performance scope is missing or unsupported")
    if int(perf.get("pageSamples", 0)) < int(corpus_summary.get("pageCount", 0)):
        reasons.append("performance benchmark did not cover every corpus page")
    if float(perf.get("peakRamMiB", 1e12)) > float(thresholds["peakRamMiBMax"]):
        reasons.append("peak RAM exceeds release guardrail")
    if float(perf.get("p95PageSeconds", 1e12)) > float(thresholds["p95PageSecondsMax"]):
        reasons.append("p95 page time exceeds release guardrail")
    return reasons


def _selected_artifacts(report: dict[str, Any]) -> list[str]:
    selected_candidate_ids = set(require_dict(report.get("selected"), label="selected").values())
    result: list[str] = []
    for candidate in report["candidates"]:
        if candidate["candidateId"] in selected_candidate_ids:
            for artifact_id in candidate["artifactIds"]:
                if isinstance(artifact_id, str) and artifact_id not in result:
                    result.append(artifact_id)
    font_artifact = require_dict(report.get("renderer"), label="renderer").get("fontArtifactId")
    if isinstance(font_artifact, str) and font_artifact not in result:
        result.append(font_artifact)
    return result
