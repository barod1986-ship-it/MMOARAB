from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
DISCLOSURE_VERSION = "2026-08-19.remote-transfer.v1"


def _text(root: Path, relative: str, blockers: list[str]) -> str:
    path = root / relative
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        blockers.append(f"remote-transfer consent source is missing/unreadable: {relative}: {exc}")
        return ""


def _require(text: str, needles: Iterable[str], label: str, blockers: list[str]) -> None:
    missing = [needle for needle in needles if needle not in text]
    if missing:
        blockers.append(f"{label} is incomplete; missing contract marker(s): {', '.join(missing)}")


def verify_remote_transfer_consent_contract(root: Path, blockers: list[str] | None = None) -> bool:
    """Verify that remote OCR-text consent is implemented at both UI and Engine boundaries.

    This is deliberately source-contract verification, not a claim that a production profile is
    frozen or that a public release is ready. It prevents release metadata from asserting that a
    remote-transfer consent gate exists when the executable source no longer contains it.
    """
    local: list[str] = []
    target = blockers if blockers is not None else local
    before = len(target)

    consent_ts = _text(root, "src/ui/remote-transfer-consent.ts", target)
    gateway_ts = _text(root, "src/engine/local-processing-gateway.ts", target)
    types_ts = _text(root, "src/engine/types.ts", target)
    background_ts = _text(root, "src/messaging/background-handlers.ts", target)
    protocol_ts = _text(root, "src/messaging/protocol.ts", target)
    sidepanel_tsx = _text(root, "src/entrypoints/sidepanel/main.tsx", target)
    coordinator_ts = _text(root, "src/pipeline/coordinator.ts", target)
    engine_consent = _text(root, "engine/mte_engine/consent.py", target)
    engine_models = _text(root, "engine/mte_engine/models.py", target)
    engine_app = _text(root, "engine/mte_engine/app.py", target)
    engine_profile = _text(root, "engine/mte_engine/profile.py", target)
    engine_tests = _text(root, "engine/tests/test_remote_transfer_consent.py", target)

    _require(consent_ts, [
        f"REMOTE_TRANSFER_DISCLOSURE_VERSION = '{DISCLOSURE_VERSION}'",
        "profileFingerprint",
        "privacyDescriptor",
        "externalProviderNames",
        "remoteTransferConsentMatches",
        "profile.externalProviders.length > 0",
    ], "versioned UI consent binding", target)
    _require(types_ts, ["RemoteTransferConsentProof", "externalProviders: string[]"], "Engine protocol consent types", target)
    _require(gateway_ts, [
        "#consentProofForProfile",
        "const remoteTransferConsent = await this.#consentProofForProfile(input.processingSpec.profileId, input.expectedProfileFingerprint)",
        "const remoteTransferConsent = await this.#consentProofForProfile(input.profileId, input.expectedProfileFingerprint)",
        "body: JSON.stringify(remoteTransferConsent ? { remoteTransferConsent } : {})",
        "REMOTE_TRANSFER_CONSENT_REQUIRED",
        "getCapabilities({ force: true })",
    ], "extension create/start enforcement", target)
    _require(protocol_ts, ["ui:accept-remote-transfer-disclosure", "RemoteTransferConsentState"], "trusted UI consent protocol", target)
    _require(background_ts, [
        "onMessage('ui:accept-remote-transfer-disclosure'",
        "privacyConsent.isAccepted()",
        "requiresRemoteTransferConsent(profile)",
        "remoteTransferConsent.accept(profile)",
        "getCapabilities({ force: true })",
    ], "background consent acceptance gate", target)
    _require(sidepanel_tsx, [
        "snapshot?.remoteTransferConsentRequired",
        "!snapshot.remoteTransferConsentAccepted",
        "acceptRemoteTransferDisclosure",
        "remotePrivacyDisclosureBinding",
        "remotePrivacyConsentButton",
    ], "separate remote-transfer disclosure UI", target)
    _require(coordinator_ts, [
        "this.#gateway.startJob(ticket, {",
        "expectedProfileFingerprint: current.engineProfileFingerprint",
    ], "resume/start profile-bound consent handoff", target)

    _require(engine_consent, [
        f'REMOTE_TRANSFER_DISCLOSURE_VERSION = "{DISCLOSURE_VERSION}"',
        "def verify_remote_transfer_consent",
        '"remote_transfer_consent_required"',
        'proof.profileFingerprint != profile.get("profileFingerprint")',
        "actual_privacy != expected_privacy",
        "proof.externalProviderNames != providers",
    ], "Engine consent verifier", target)
    _require(engine_models, [
        "class RemoteTransferConsentV1",
        f'Literal["{DISCLOSURE_VERSION}"]',
        "remoteTransferConsent: RemoteTransferConsentV1 | None = None",
        "externalProviders: list[str]",
    ], "Engine consent request schema", target)
    _require(engine_app, [
        "verify_remote_transfer_consent(descriptor, body.remoteTransferConsent)",
        "verify_remote_transfer_consent(descriptor, body.remoteTransferConsent if body is not None else None)",
        '@app.post("/v1/jobs/{ticket}/start")',
    ], "Engine create/start enforcement", target)
    _require(engine_profile, [
        'return ["OpenAI"] if supported and text_leaves else []',
        '"externalProviders": _production_external_providers(settings)',
        '"externalProviders": []',
    ], "profile/provider disclosure", target)
    _require(engine_tests, [
        "test_remote_profile_requires_exact_versioned_consent",
        "test_remote_consent_is_bound_to_profile_privacy_and_provider",
        "test_local_profile_needs_no_remote_consent_but_privacy_must_be_frozen",
        "ocrTextLeavesDevice\": None",
    ], "Engine consent regressions", target)

    return len(target) == before


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the fail-closed remote OCR-text transfer consent source contract.")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    blockers: list[str] = []
    ok = verify_remote_transfer_consent_contract(args.root.resolve(), blockers)
    if not ok:
        print(f"Remote-transfer consent contract blocked ({len(blockers)}):", file=sys.stderr)
        for blocker in blockers:
            print(f"- {blocker}", file=sys.stderr)
        return 2
    print("Remote-transfer consent contract: 12/12 source boundaries verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
