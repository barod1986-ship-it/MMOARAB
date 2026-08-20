from __future__ import annotations

import pytest

from mte_engine.consent import REMOTE_TRANSFER_DISCLOSURE_VERSION, verify_remote_transfer_consent
from mte_engine.errors import EngineApiError
from mte_engine.models import RemoteTransferConsentV1


FINGERPRINT = "sha256:" + "a" * 64


def remote_profile() -> dict[str, object]:
    return {
        "profileId": "default-v1",
        "profileFingerprint": FINGERPRINT,
        "state": "ready",
        "privacy": {"imageLeavesDevice": False, "ocrTextLeavesDevice": True, "visualContextLeavesDevice": False},
        "externalProviders": ["OpenAI"],
    }


def proof() -> RemoteTransferConsentV1:
    return RemoteTransferConsentV1.model_validate({
        "schemaVersion": 1,
        "disclosureVersion": REMOTE_TRANSFER_DISCLOSURE_VERSION,
        "profileId": "default-v1",
        "profileFingerprint": FINGERPRINT,
        "privacyDescriptor": {"imageLeavesDevice": False, "ocrTextLeavesDevice": True, "visualContextLeavesDevice": False},
        "externalProviderNames": ["OpenAI"],
        "acceptedAt": 1_787_181_000_000,
    })


def test_remote_profile_requires_exact_versioned_consent() -> None:
    with pytest.raises(EngineApiError, match="Separate versioned consent") as exc:
        verify_remote_transfer_consent(remote_profile(), None)
    assert exc.value.code == "remote_transfer_consent_required"
    verify_remote_transfer_consent(remote_profile(), proof())


def test_remote_consent_is_bound_to_profile_privacy_and_provider() -> None:
    value = proof().model_copy(update={"profileFingerprint": "sha256:" + "b" * 64})
    with pytest.raises(EngineApiError) as exc:
        verify_remote_transfer_consent(remote_profile(), value)
    assert exc.value.code == "remote_transfer_consent_required"

    value = proof().model_copy(update={"externalProviderNames": ["Other"]})
    with pytest.raises(EngineApiError) as exc:
        verify_remote_transfer_consent(remote_profile(), value)
    assert exc.value.code == "remote_transfer_consent_required"


def test_local_profile_needs_no_remote_consent_but_privacy_must_be_frozen() -> None:
    local = {
        "profileId": "fixture-v1",
        "profileFingerprint": FINGERPRINT,
        "state": "ready",
        "privacy": {"imageLeavesDevice": False, "ocrTextLeavesDevice": False, "visualContextLeavesDevice": False},
        "externalProviders": [],
    }
    verify_remote_transfer_consent(local, None)
    local["privacy"] = {"imageLeavesDevice": False, "ocrTextLeavesDevice": None, "visualContextLeavesDevice": False}
    with pytest.raises(EngineApiError) as exc:
        verify_remote_transfer_consent(local, None)
    assert exc.value.code == "profile_not_ready"
