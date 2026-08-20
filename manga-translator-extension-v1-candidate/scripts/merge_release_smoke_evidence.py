from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from release_evidence import V1_ENGINE_TARGETS, load_json, validate_controlled_manifest, validate_smoke_observation


def browser_major(value: str) -> int:
    return int(value.split('.', 1)[0])


def main() -> int:
    parser = argparse.ArgumentParser(description='Merge exact-byte smoke observations and mirror their truth into release-state.json.')
    parser.add_argument('--controlled-manifest', type=Path, required=True)
    parser.add_argument('--observation', type=Path, action='append', default=[])
    parser.add_argument('--records', type=Path, default=Path('release-control/smoke-records.json'))
    parser.add_argument('--release-state', type=Path, default=Path('release-control/release-state.json'))
    parser.add_argument('--profile-privacy', type=Path, default=Path('store/release/profile-privacy.json'))
    args = parser.parse_args()

    manifest, manifest_sha = validate_controlled_manifest(args.controlled_manifest.resolve())
    state = load_json(args.release_state.resolve(), 'release state')
    privacy = load_json(args.profile_privacy.resolve(), 'production profile privacy descriptor')
    if privacy.get('schemaVersion') != 2 or privacy.get('materializedFromControlledManifestSha256') != manifest_sha:
        raise SystemExit('profile/privacy descriptor is not materialized from this controlled manifest')
    fingerprints = privacy.get('profileFingerprintsByTarget')
    if not isinstance(fingerprints, dict) or set(fingerprints) != set(V1_ENGINE_TARGETS):
        raise SystemExit('profile/privacy descriptor does not contain the exact V1 target fingerprint set')

    observations = []
    ids = set()
    for path in args.observation:
        item = load_json(path.resolve(), f'smoke observation {path}')
        validate_smoke_observation(item, manifest=manifest, manifest_sha256=manifest_sha)
        rid = item['id']
        if rid in ids:
            raise SystemExit(f'duplicate smoke observation id: {rid}')
        ids.add(rid)
        if item['kind'] == 'engine-artifact':
            expected = 'sha256:' + fingerprints[item['platform']]
            if item.get('profileFingerprint') != expected:
                raise SystemExit(f'Engine smoke fingerprint does not match materialized profile for {item["platform"]}')
            if item.get('privacyDescriptor') != privacy.get('privacyDescriptor'):
                raise SystemExit(f'Engine smoke privacy descriptor drift for {item["platform"]}')
            if item.get('externalProviderNames') != privacy.get('externalProviderNames'):
                raise SystemExit(f'Engine smoke provider drift for {item["platform"]}')
        observations.append(item)

    engines = {item['platform'] for item in observations if item['kind'] == 'engine-artifact'}
    if engines != set(V1_ENGINE_TARGETS):
        raise SystemExit('V1 smoke evidence must contain all three Engine targets')
    audit = state.get('audit') if isinstance(state.get('audit'), dict) else {}
    baseline = audit.get('chromeBaselineMajor')
    stable = audit.get('currentStableMajorAtAudit')
    browser_records = [item for item in observations if item['kind'] == 'unpacked-extension']
    if not any(browser_major(item['browserVersion']) == baseline for item in browser_records):
        raise SystemExit(f'Chrome {baseline} exact-byte smoke observation is missing')
    if not any(browser_major(item['browserVersion']) == stable for item in browser_records):
        raise SystemExit(f'Chrome {stable} exact-byte smoke observation is missing')

    records_value = {
        'schemaVersion': 2,
        'controlledManifestSha256': manifest_sha,
        'sourceHeadSha': manifest['sourceHeadSha'],
        'records': sorted(observations, key=lambda x: x['id']),
    }
    args.records.parent.mkdir(parents=True, exist_ok=True)
    args.records.write_text(json.dumps(records_value, indent=2) + '\n', encoding='utf-8')

    state['releaseClass'] = manifest['releaseClass']
    artifacts = state.setdefault('artifacts', {})
    manifest_path = args.controlled_manifest.resolve()
    try:
        rel = manifest_path.relative_to(args.release_state.resolve().parents[1])
        artifacts['controlledManifest'] = rel.as_posix()
    except ValueError:
        artifacts['controlledManifest'] = f'release/controlled/{manifest["releaseId"]}/controlled-release.json'
    artifacts['extensionSha256'] = manifest['extension']['sha256'].removeprefix('sha256:')
    artifacts['engineTargets'] = sorted(V1_ENGINE_TARGETS)
    smoke = state.setdefault('smoke', {})
    smoke['freshUnpackedChrome148Passed'] = any(browser_major(item['browserVersion']) == 148 for item in browser_records)
    smoke['freshUnpackedCurrentStablePassed'] = any(browser_major(item['browserVersion']) == stable for item in browser_records)
    smoke['freshEngineArtifactPassedTargets'] = sorted(engines)
    flags = state.setdefault('v1Blockers', {})
    flags['phase7NativeSupportReady'] = True
    flags['chrome148RealBrowserGate'] = smoke['freshUnpackedChrome148Passed']
    flags['currentStableRealBrowserGate'] = smoke['freshUnpackedCurrentStablePassed']
    args.release_state.write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'records': len(observations), 'manifestSha256': manifest_sha, 'engineTargets': sorted(engines), 'browserMajors': sorted({browser_major(item['browserVersion']) for item in browser_records})}, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
