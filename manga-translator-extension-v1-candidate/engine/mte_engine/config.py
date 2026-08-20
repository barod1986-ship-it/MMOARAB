from __future__ import annotations

import json
import os
import re
import secrets
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from .constants import DEFAULT_HOST, DEFAULT_PORT

_EXTENSION_ORIGIN_RE = re.compile(r"^chrome-extension://[a-p]{32}$")


@dataclass(frozen=True, slots=True)
class EngineSettings:
    data_dir: Path
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    arabic_font_path: Path | None = None
    enable_fixture_profile: bool = False
    production_freeze_path: Path | None = None
    model_artifacts_dir: Path | None = None
    model_distribution_catalog_path: Path | None = None
    external_text_translation_enabled: bool = False
    openai_api_key: str | None = field(default=None, repr=False)

    @classmethod
    def from_env(cls) -> "EngineSettings":
        default_dir = Path.home() / ".manga-translator-engine"
        data_dir = Path(os.environ.get("MTE_ENGINE_DATA_DIR", default_dir)).expanduser().resolve()
        host = os.environ.get("MTE_ENGINE_HOST", DEFAULT_HOST)
        port = int(os.environ.get("MTE_ENGINE_PORT", str(DEFAULT_PORT)))
        if host != DEFAULT_HOST:
            raise RuntimeError("V1 Local Engine must bind only to 127.0.0.1.")
        if port != DEFAULT_PORT:
            raise RuntimeError(f"V1 Local Engine must bind only to fixed port {DEFAULT_PORT}.")
        font_raw = os.environ.get("MTE_ARABIC_FONT_PATH", "").strip()
        font_path = Path(font_raw).expanduser().resolve() if font_raw else None
        enable_fixture = os.environ.get("MTE_ENABLE_FIXTURE_PROFILE", "") == "1"
        freeze_raw = os.environ.get("MTE_PRODUCTION_FREEZE_PATH", "").strip()
        freeze_path = Path(freeze_raw).expanduser().resolve() if freeze_raw else None
        models_raw = os.environ.get("MTE_MODEL_ARTIFACTS_DIR", "").strip()
        model_artifacts_dir = Path(models_raw).expanduser().resolve() if models_raw else (data_dir / "models")
        catalog_raw = os.environ.get("MTE_MODEL_DISTRIBUTION_CATALOG_PATH", "").strip()
        if catalog_raw:
            model_distribution_catalog_path = Path(catalog_raw).expanduser().resolve()
        else:
            model_distribution_catalog_path = (Path(__file__).resolve().parent / "resources" / "model-distribution-v1.json").resolve()
        external_text_translation_enabled = os.environ.get("MTE_ENABLE_EXTERNAL_TEXT_TRANSLATION", "") == "1"
        openai_api_key = os.environ.get("MTE_OPENAI_API_KEY", "").strip() or None
        return cls(
            data_dir=data_dir, host=host, port=port, arabic_font_path=font_path,
            enable_fixture_profile=enable_fixture, production_freeze_path=freeze_path,
            model_artifacts_dir=model_artifacts_dir, model_distribution_catalog_path=model_distribution_catalog_path,
            external_text_translation_enabled=external_text_translation_enabled, openai_api_key=openai_api_key,
        )

    @property
    def expected_host_header(self) -> str:
        return f"{self.host}:{self.port}"


class PairingStore:
    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir / "engine-config.json"
        self._data_dir = data_dir
        self._data_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self._data_dir, 0o700)
        except OSError:
            pass
        self._ensure_config()

    def _ensure_config(self) -> None:
        if self._path.exists():
            return
        token = secrets.token_urlsafe(32)
        self._atomic_write({"schemaVersion": 1, "token": token, "pairedOrigin": None})

    def _load(self) -> dict[str, object]:
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        if raw.get("schemaVersion") != 1 or not isinstance(raw.get("token"), str):
            raise RuntimeError("Engine pairing config is malformed.")
        return raw

    def _atomic_write(self, value: dict[str, object]) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=".engine-config-", suffix=".tmp", dir=self._data_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(value, handle, ensure_ascii=False, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, self._path)
            try:
                os.chmod(self._path, 0o600)
            except OSError:
                pass
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

    @property
    def token(self) -> str:
        return str(self._load()["token"])

    @property
    def paired_origin(self) -> str | None:
        value = self._load().get("pairedOrigin")
        return value if isinstance(value, str) else None

    def pair(self, origin: str) -> None:
        if not is_valid_extension_origin(origin):
            raise ValueError("Only an exact chrome-extension:// origin can be paired.")
        current = self._load()
        existing = current.get("pairedOrigin")
        if isinstance(existing, str) and existing != origin:
            raise PermissionError("Engine is already paired to another extension origin.")
        current["pairedOrigin"] = origin
        self._atomic_write(current)

    def reset_pairing(self, *, rotate_token: bool = True) -> None:
        current = self._load()
        current["pairedOrigin"] = None
        if rotate_token:
            current["token"] = secrets.token_urlsafe(32)
        self._atomic_write(current)


def is_valid_extension_origin(origin: str) -> bool:
    return bool(_EXTENSION_ORIGIN_RE.fullmatch(origin))
