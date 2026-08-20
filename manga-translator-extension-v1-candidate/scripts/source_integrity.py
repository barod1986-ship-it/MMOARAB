from __future__ import annotations

import hashlib
from pathlib import Path

MANIFEST = 'SOURCE_SHA256SUMS.txt'
EXCLUDED_DIR_NAMES = {'.git', 'node_modules', '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', '.output', '.offline-check'}
EXCLUDED_PREFIXES = ('release/',)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def source_files(root: Path) -> list[str]:
    files: list[str] = []
    for path in root.rglob('*'):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel == MANIFEST or rel.startswith(EXCLUDED_PREFIXES):
            continue
        if any(part in EXCLUDED_DIR_NAMES for part in path.relative_to(root).parts):
            continue
        files.append(rel)
    return sorted(files)


def render_manifest(root: Path) -> str:
    return ''.join(f'{sha256_file(root / rel)}  {rel}\n' for rel in source_files(root))


def parse_manifest(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for lineno, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if not line:
            continue
        if '  ' not in line:
            raise ValueError(f'{path.name}:{lineno}: invalid checksum line')
        digest, rel = line.split('  ', 1)
        if len(digest) != 64 or any(ch not in '0123456789abcdefABCDEF' for ch in digest):
            raise ValueError(f'{path.name}:{lineno}: invalid SHA-256')
        if not rel or rel.startswith('/') or '\\' in rel or any(part in {'', '.', '..'} for part in Path(rel).parts):
            raise ValueError(f'{path.name}:{lineno}: unsafe path')
        if rel in entries:
            raise ValueError(f'{path.name}:{lineno}: duplicate path {rel}')
        entries[rel] = digest.lower()
    return entries


def verify_source_integrity(root: Path) -> list[str]:
    errors: list[str] = []
    manifest = root / MANIFEST
    if not manifest.is_file():
        return [f'{MANIFEST} is missing']
    try:
        entries = parse_manifest(manifest)
    except (OSError, ValueError) as exc:
        return [str(exc)]

    expected = set(source_files(root))
    actual = set(entries)
    for rel in sorted(expected - actual):
        errors.append(f'untracked source file: {rel}')
    for rel in sorted(actual - expected):
        errors.append(f'checksum entry is stale or excluded: {rel}')
    for rel in sorted(expected & actual):
        path = root / rel
        try:
            digest = sha256_file(path)
        except OSError as exc:
            errors.append(f'cannot hash {rel}: {exc}')
            continue
        if digest != entries[rel]:
            errors.append(f'checksum mismatch: {rel}')
    return errors
