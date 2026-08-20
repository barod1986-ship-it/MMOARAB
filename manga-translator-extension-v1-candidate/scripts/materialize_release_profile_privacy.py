from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from release_evidence import V1_ENGINE_TARGETS, load_json, validate_controlled_manifest, validate_smoke_observation

DISCLOSURE_VERSION = '2026-08-19.remote-transfer.v1'
LOCAL_DISCLOSURE_VERSION = '2026-08-19.v1'


def main() -> int:
    parser = argparse.ArgumentParser(description='Materialize the V1 release privacy/profile descriptor from exact-byte Engine smoke observations.')
    parser.add_argument('--controlled-manifest', type=Path, required=True)
    parser.add_argument('--engine-observation', type=Path, action='append', default=[])
    parser.add_argument('--output', type=Path, default=Path('store/release/profile-privacy.json'))
    args = parser.parse_args()

    manifest, manifest_sha = validate_controlled_manifest(args.controlled_manifest.resolve())
    observations = []
    for path in args.engine_observation:
        observation = load_json(path.resolve(), f'Engine smoke observation {path}')
        validate_smoke_observation(observation, manifest=manifest, manifest_sha256=manifest_sha)
        if observation.get('kind') != 'engine-artifact':
            raise SystemExit(f'not an Engine smoke observation: {path}')
        observations.append(observation)

    by_target = {str(item['platform']): item for item in observations}
    if set(by_target) != set(V1_ENGINE_TARGETS) or len(observations) != len(V1_ENGINE_TARGETS):
        missing = sorted(set(V1_ENGINE_TARGETS) - set(by_target))
        extra = sorted(set(by_target) - set(V1_ENGINE_TARGETS))
        detail = []
        if missing:
            detail.append('missing ' + ', '.join(missing))
        if extra:
            detail.append('unexpected ' + ', '.join(extra))
        raise SystemExit('profile/privacy materialization requires exactly one Engine observation per V1 target: ' + '; '.join(detail or ['duplicates present']))

    first = by_target[V1_ENGINE_TARGETS[0]]
    privacy = first['privacyDescriptor']
    providers = first['externalProviderNames']
    for target, observation in by_target.items():
        if observation['privacyDescriptor'] != privacy:
            raise SystemExit(f'privacy descriptor differs across Engine targets: {target}')
        if observation['externalProviderNames'] != providers:
            raise SystemExit(f'external provider list differs across Engine targets: {target}')

    remote = any(privacy.values())
    value = {
        'schemaVersion': 2,
        'profileId': 'default-v1',
        'profileFingerprintsByTarget': {
            target: by_target[target]['profileFingerprint'].removeprefix('sha256:') for target in V1_ENGINE_TARGETS
        },
        'privacyDescriptor': privacy,
        'externalProviderNames': providers,
        'localDisclosureVersion': LOCAL_DISCLOSURE_VERSION,
        'remoteTransferDisclosureVersion': DISCLOSURE_VERSION if remote else None,
        'remoteTransferConsentImplemented': remote,
        'materializedFromControlledManifestSha256': manifest_sha,
        'sourceHeadSha': manifest['sourceHeadSha'],
        'notes': 'Materialized only from exact-byte production Engine smoke observations. Per-target profile fingerprints are expected because the fingerprint includes packaged runtime/codec identity; privacy/provider semantics must remain identical across targets.',
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'output': str(args.output), 'manifestSha256': manifest_sha, 'targets': list(V1_ENGINE_TARGETS), 'remote': remote}, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
