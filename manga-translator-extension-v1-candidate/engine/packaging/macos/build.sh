#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
ARGS=("$ROOT/engine/packaging/build_engine.py")
[[ "${1:-}" == "--release" ]] && ARGS+=(--release)
python3 "${ARGS[@]}"
