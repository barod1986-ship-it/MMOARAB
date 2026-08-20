from __future__ import annotations

import json
from pathlib import Path
import sys

ENGINE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE_ROOT))

from mte_engine.benchmark.corpus_sources import load_source_registry, source_registry_digest


def main() -> int:
    registry = load_source_registry()
    sources = registry["sources"]
    active = [sid for sid, item in sources.items() if item.get("commercialQualificationAllowed") is True and item.get("v1Qualification") != "supplemental-only"]
    blocked = [sid for sid, item in sources.items() if item.get("commercialQualificationAllowed") is not True]
    supplemental = [sid for sid, item in sources.items() if item.get("v1Qualification") == "supplemental-only"]
    payload = {
        "registryRevision": registry["registryRevision"],
        "registrySha256": source_registry_digest(registry),
        "productionEligibleSourceIds": sorted(active),
        "blockedSourceIds": sorted(blocked),
        "supplementalOnlySourceIds": sorted(supplemental),
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
