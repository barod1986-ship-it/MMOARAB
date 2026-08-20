from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .config import EngineSettings
from .constants import FIXTURE_PROFILE_ID, PROFILE_ID
from .errors import EngineApiError
from .pipeline.detector import ReferenceDetector
from .pipeline.inpaint import ReferenceSolidInpainter
from .pipeline.ocr import ReferenceOcrRouter
from .pipeline.reading_order import HeuristicReadingOrder
from .pipeline.renderer import ArabicRenderer
from .pipeline.roles import ConservativeRoleClassifier
from .pipeline.staged import PipelineArtifact, StagedPipeline
from .pipeline.translator import ReferenceTranslator
from .spool import SpoolStore
from .production_runtime import build_production_pipeline


def process_staged_job(
    source_path: Path,
    spool: SpoolStore,
    settings: EngineSettings,
    *,
    ticket: str,
    job_id: str,
    profile_id: str,
    profile_fingerprint: str,
    source_language: str,
    target_language: str,
    stage_callback=None,
    started_at: float | None = None,
) -> tuple[Path, PipelineArtifact]:
    if profile_id == FIXTURE_PROFILE_ID:
        if not settings.enable_fixture_profile:
            raise EngineApiError("profile_not_ready", "Fixture profile is disabled.", 409)
        if settings.arabic_font_path is None:
            raise EngineApiError("renderer_capability_missing", "Arabic font profile is not configured.", 409)
        renderer = ArabicRenderer(settings.arabic_font_path)
        renderer.self_test()
        pipeline = StagedPipeline(
            detector=ReferenceDetector(),
            reading_order=HeuristicReadingOrder(),
            ocr=ReferenceOcrRouter(),
            roles=ConservativeRoleClassifier(),
            translator=ReferenceTranslator(),
            inpainter=ReferenceSolidInpainter(),
            renderer=renderer,
        )
    elif profile_id == PROFILE_ID:
        pipeline = build_production_pipeline(settings)
    else:
        raise EngineApiError("profile_not_ready", f"Unknown processing profile: {profile_id}.", 409)
    artifact = pipeline.process(
        source_path,
        job_id=job_id,
        profile_fingerprint=profile_fingerprint,
        source_language=source_language,
        target_language=target_language,
        stage_callback=stage_callback,
        started_at=started_at or time.monotonic(),
    )
    suffix = ".webp" if artifact.mime == "image/webp" else ".png"
    path = spool.allocate_result_path(ticket, suffix)
    temp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(artifact.encoded)
        handle.flush()
        os.fsync(handle.fileno())
    temp.replace(path)
    return path, artifact
