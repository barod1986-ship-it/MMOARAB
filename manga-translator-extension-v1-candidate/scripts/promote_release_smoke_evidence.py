from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from source_integrity import parse_manifest, sha256_file, verify_source_integrity

ROOT = Path(__file__).resolve().parents[1]
MATERIALIZE = ROOT / 'scripts' / 'materialize_release_profile_privacy.py'
MERGE = ROOT / 'scripts' / 'merge_release_smoke_evidence.py'
ORCHESTRATOR = ROOT / 'scripts' / 'v1_evidence_orchestrator.py'


def run_checked(command: list[str]) -> None:
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    if result.returncode != 0:
        if result.stdout:
            print(result.stdout, file=sys.stderr, end='')
        if result.stderr:
            print(result.stderr, file=sys.stderr, end='')
        raise SystemExit(result.returncode)


def atomic_replace(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, target)


def render_updated_integrity(staged_by_target: dict[Path, Path], source_manifest: Path) -> str:
    entries = parse_manifest(source_manifest)
    for target, staged in staged_by_target.items():
        rel = target.resolve().relative_to(ROOT).as_posix()
        entries[rel] = sha256_file(staged)
    return ''.join(f'{entries[rel]}  {rel}\n' for rel in sorted(entries))


def replace_transactionally(staged_by_target: dict[Path, Path], staged_manifest: Path | None = None, source_manifest: Path | None = None) -> None:
    backup = Path(tempfile.mkdtemp(prefix='mte-release-smoke-backup-'))
    targets = [*staged_by_target.keys()] + ([source_manifest] if source_manifest is not None else [])
    try:
        for target in targets:
            key = hashlib.sha256(str(target.resolve()).encode('utf-8')).hexdigest()
            saved = backup / key
            if target.is_file():
                saved.write_bytes(target.read_bytes())
        replaced: list[Path] = []
        try:
            for target, staged in staged_by_target.items():
                atomic_replace(staged, target)
                replaced.append(target)
            if staged_manifest is not None and source_manifest is not None:
                atomic_replace(staged_manifest, source_manifest)
                replaced.append(source_manifest)
                errors = verify_source_integrity(ROOT)
                if errors:
                    raise RuntimeError('post-promotion source-integrity failed: ' + '; '.join(errors))
        except Exception:
            for target in reversed(replaced):
                key = hashlib.sha256(str(target.resolve()).encode('utf-8')).hexdigest()
                saved = backup / key
                if saved.is_file():
                    target.write_bytes(saved.read_bytes())
                else:
                    target.unlink(missing_ok=True)
            raise
    finally:
        shutil.rmtree(backup, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Transactionally promote exact-byte Engine/browser smoke observations into V1 release evidence state.'
    )
    parser.add_argument('--controlled-manifest', type=Path, required=True)
    parser.add_argument('--engine-observation', type=Path, action='append', default=[])
    parser.add_argument('--browser-observation', type=Path, action='append', default=[])
    parser.add_argument('--profile-privacy', type=Path, default=ROOT / 'store' / 'release' / 'profile-privacy.json')
    parser.add_argument('--records', type=Path, default=ROOT / 'release-control' / 'smoke-records.json')
    parser.add_argument('--release-state', type=Path, default=ROOT / 'release-control' / 'release-state.json')
    parser.add_argument('--orchestration-session', type=Path, required=True, help='browser-smoke-complete V1 orchestration session')
    parser.add_argument('--orchestration-output', type=Path, default=ROOT / 'release-control' / 'v1-orchestration.json')
    parser.add_argument('--dry-run', action='store_true', help='Validate and materialize into temporary files without changing source evidence state.')
    args = parser.parse_args()

    manifest = args.controlled_manifest.resolve()
    engines = [path.resolve() for path in args.engine_observation]
    browsers = [path.resolve() for path in args.browser_observation]
    if len(engines) != 3:
        raise SystemExit('promotion requires exactly three Engine observations (Linux, macOS, Windows)')
    if len(browsers) != 2:
        raise SystemExit('promotion requires exactly two unpacked-browser observations (Chrome 148 and current Stable)')
    for path in [manifest, *engines, *browsers, args.release_state.resolve(), args.orchestration_session.resolve()]:
        if not path.is_file():
            raise SystemExit(f'required promotion input is missing: {path}')

    with tempfile.TemporaryDirectory(prefix='mte-release-smoke-promotion-') as td:
        staging = Path(td)
        staged_privacy = staging / 'profile-privacy.json'
        staged_records = staging / 'smoke-records.json'
        staged_state = staging / 'release-state.json'
        shutil.copyfile(args.release_state.resolve(), staged_state)

        materialize = [
            sys.executable, str(MATERIALIZE),
            '--controlled-manifest', str(manifest),
            '--output', str(staged_privacy),
        ]
        for path in engines:
            materialize += ['--engine-observation', str(path)]
        run_checked(materialize)

        merge = [
            sys.executable, str(MERGE),
            '--controlled-manifest', str(manifest),
            '--profile-privacy', str(staged_privacy),
            '--records', str(staged_records),
            '--release-state', str(staged_state),
        ]
        for path in [*engines, *browsers]:
            merge += ['--observation', str(path)]
        run_checked(merge)

        staged_orchestration = staging / 'v1-orchestration.json'
        run_checked([
            sys.executable, str(ORCHESTRATOR), 'promoted',
            '--session', str(args.orchestration_session.resolve()),
            '--controlled-manifest', str(manifest),
            '--profile-privacy', str(staged_privacy),
            '--smoke-records', str(staged_records),
            '--release-state', str(staged_state),
            '--output', str(staged_orchestration),
        ])

        staged_by_target = {
            args.profile_privacy.resolve(): staged_privacy,
            args.records.resolve(): staged_records,
            args.release_state.resolve(): staged_state,
            args.orchestration_output.resolve(): staged_orchestration,
        }
        source_manifest = ROOT / 'SOURCE_SHA256SUMS.txt'
        staged_source_manifest: Path | None = None
        try:
            for target in staged_by_target:
                target.relative_to(ROOT)
        except ValueError:
            # Custom external paths are supported for isolated validation/tests; they do not mutate source integrity.
            source_manifest_for_commit: Path | None = None
        else:
            staged_source_manifest = staging / 'SOURCE_SHA256SUMS.txt'
            staged_source_manifest.write_text(render_updated_integrity(staged_by_target, source_manifest), encoding='utf-8')
            source_manifest_for_commit = source_manifest

        if args.dry_run:
            print(f'validated release smoke evidence transactionally; staged outputs: {staging}')
            return 0

        # Promote evidence mirrors and, for real source paths, their checksum manifest as one rollback-capable transaction.
        replace_transactionally(staged_by_target, staged_source_manifest, source_manifest_for_commit)

    print('release smoke evidence promoted transactionally: profile/privacy + smoke records + release state + orchestration + source integrity')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
