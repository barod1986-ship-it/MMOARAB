from __future__ import annotations

from typing import Any

from .errors import EngineApiError
from .models import RemoteTransferConsentV1

REMOTE_TRANSFER_DISCLOSURE_VERSION = "2026-08-19.remote-transfer.v1"


def verify_remote_transfer_consent(profile: dict[str, Any], proof: RemoteTransferConsentV1 | None) -> None:
    privacy = profile.get("privacy")
    if not isinstance(privacy, dict):
        raise EngineApiError("profile_not_ready", "Engine profile privacy descriptor is unavailable.", 409)
    image = privacy.get("imageLeavesDevice")
    text = privacy.get("ocrTextLeavesDevice")
    visual = privacy.get("visualContextLeavesDevice")
    if not isinstance(image, bool) or (not isinstance(text, bool) and text is not None) or not isinstance(visual, bool):
        raise EngineApiError("profile_not_ready", "Engine profile privacy descriptor is incomplete.", 409)
    if text is None:
        raise EngineApiError("profile_not_ready", "Engine profile has not frozen its OCR-text transfer behavior.", 409)

    providers = profile.get("externalProviders")
    if not isinstance(providers, list) or any(not isinstance(name, str) or not name.strip() for name in providers):
        raise EngineApiError("profile_not_ready", "Engine profile external-provider disclosure is malformed.", 409)
    remote = image or text or visual
    if not remote:
        if providers:
            raise EngineApiError("profile_not_ready", "Local-only Engine profile unexpectedly declares external providers.", 409)
        return
    if not providers:
        raise EngineApiError("profile_not_ready", "Remote-transfer Engine profile does not name its external provider.", 409)
    if proof is None:
        raise EngineApiError(
            "remote_transfer_consent_required",
            "Separate versioned consent is required before this profile may transfer user data externally.",
            409,
        )

    expected_privacy = {
        "imageLeavesDevice": image,
        "ocrTextLeavesDevice": text,
        "visualContextLeavesDevice": visual,
    }
    actual_privacy = proof.privacyDescriptor.model_dump(mode="json")
    if (
        proof.disclosureVersion != REMOTE_TRANSFER_DISCLOSURE_VERSION
        or proof.profileId != profile.get("profileId")
        or proof.profileFingerprint != profile.get("profileFingerprint")
        or actual_privacy != expected_privacy
        or proof.externalProviderNames != providers
    ):
        raise EngineApiError(
            "remote_transfer_consent_required",
            "Remote-transfer consent does not match the current profile, privacy descriptor, provider, and disclosure version.",
            409,
        )
