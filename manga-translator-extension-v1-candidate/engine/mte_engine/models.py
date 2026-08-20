from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Sha256Prefixed = str


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class TextRolePolicy(StrictModel):
    translatableKinds: list[Literal["dialogue", "narration"]]

    @field_validator("translatableKinds")
    @classmethod
    def validate_translatable_kinds(cls, value: list[str]) -> list[str]:
        if value != ["dialogue", "narration"]:
            raise ValueError("translatableKinds must be exactly [dialogue, narration]")
        return value
    sfxAction: Literal["preserve-original"]
    uncertainAction: Literal["preserve-original"]
    revision: Literal["sfx-preserve-v1"]


class OutputSpec(StrictModel):
    kind: Literal["translated-raster-image"]
    preserveDimensions: Literal[True]


class ProcessingSpecV1(StrictModel):
    schemaVersion: Literal[1]
    sourceLanguage: str
    targetLanguage: Literal["ar"]
    textRolePolicy: TextRolePolicy
    output: OutputSpec
    profileId: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")

    @field_validator("sourceLanguage")
    @classmethod
    def validate_source_language(cls, value: str) -> str:
        if value == "auto":
            return value
        import re
        if not re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*", value):
            raise ValueError("invalid source language token")
        return value


class PrivacyDescriptor(StrictModel):
    imageLeavesDevice: bool
    ocrTextLeavesDevice: bool | None
    visualContextLeavesDevice: bool


class RemoteTransferConsentV1(StrictModel):
    schemaVersion: Literal[1]
    disclosureVersion: Literal["2026-08-19.remote-transfer.v1"]
    profileId: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    profileFingerprint: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    privacyDescriptor: PrivacyDescriptor
    externalProviderNames: list[str] = Field(min_length=1, max_length=8)
    acceptedAt: int = Field(gt=0)

    @field_validator("externalProviderNames")
    @classmethod
    def validate_external_provider_names(cls, value: list[str]) -> list[str]:
        if any(not name.strip() or len(name) > 128 for name in value) or len(set(value)) != len(value):
            raise ValueError("externalProviderNames must contain unique bounded provider names")
        return value


class CreateJobRequest(StrictModel):
    jobId: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")
    idempotencyKey: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    sourceSha256: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    sourceBytes: int = Field(gt=0)
    sourceMime: Literal["image/jpeg", "image/png", "image/webp", "image/avif"]
    processingSpec: ProcessingSpecV1
    expectedProfileFingerprint: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    remoteTransferConsent: RemoteTransferConsentV1 | None = None


class StartJobRequest(StrictModel):
    remoteTransferConsent: RemoteTransferConsentV1 | None = None


class ResultDescriptor(StrictModel):
    mime: Literal["image/webp", "image/png"]
    bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    manifestAvailable: bool


class CreateJobResponse(StrictModel):
    engineTicket: str
    state: str
    profileFingerprint: str
    result: ResultDescriptor | None = None


class Progress(StrictModel):
    completed: int = Field(ge=0)
    total: int = Field(gt=0)


class JobStatus(StrictModel):
    state: Literal[
        "awaiting_source", "queued", "running", "succeeded", "failed",
        "cancel_requested", "cancelled", "interrupted"
    ]
    stage: Literal["decode", "detect", "order", "ocr", "translate", "mask", "inpaint", "typeset", "composite", "encode"] | None = None
    progress: Progress | None = None
    updatedAt: str
    error: dict[str, object] | None = None
    result: ResultDescriptor | None = None


class ProfileDescriptor(StrictModel):
    profileId: str
    profileFingerprint: str
    state: Literal["ready", "needs-download", "unavailable-hardware", "misconfigured-provider", "renderer-missing", "runtime-unavailable"]
    privacy: PrivacyDescriptor
    externalProviders: list[str]


class HardwareDescriptor(StrictModel):
    cpu: bool
    cuda: bool
    rocm: bool
    metal: bool
    vulkan: bool


class CapabilitiesResponse(StrictModel):
    protocolVersion: Literal[1]
    engineVersion: str
    maxSourceBytes: int
    maxResultBytes: int
    supportedOutputKinds: tuple[Literal["translated-raster-image"], ...]
    resultManifestSchemaVersions: tuple[Literal[1], ...]
    supportedSourceLanguages: tuple[str, ...]
    supportedTargetLanguages: tuple[str, ...]
    recommendedDefaults: dict[str, str]
    hardware: HardwareDescriptor
    recommendedConcurrency: int
    profiles: tuple[ProfileDescriptor, ...]
