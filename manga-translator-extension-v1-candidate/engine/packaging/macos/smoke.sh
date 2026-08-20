#!/usr/bin/env bash
set -euo pipefail
python3 "$(dirname "$0")/../smoke_engine.py" "${1:?executable path required}"
