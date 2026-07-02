#!/usr/bin/env python3
from pathlib import Path
import csv
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
errors = []

required = [
    ROOT / "rathena-master",
    ROOT / "System",
    ROOT / "data",
    ROOT / "glossary" / "master_glossary.csv",
    ROOT / "AGENTS.md",
    ROOT / "tracking" / "PROJECT_STATE.json",
]
for path in required:
    if not path.exists():
        errors.append(f"Missing required path: {path.relative_to(ROOT)}")

for path in ROOT.rglob("*"):
    rel = path.relative_to(ROOT).as_posix()
    low = rel.lower()
    if "نسخة_احتياطية_قبل_المرحلة_" in rel or "_before_stage" in low:
        errors.append(f"Manual backup is forbidden: {rel}")
    if path.is_file() and path.suffix.lower() in {".zip", ".7z", ".rar", ".bak", ".backup", ".old"}:
        errors.append(f"Archive or backup is forbidden: {rel}")
    if rel.startswith("تقارير_المراجعة_الحوارية/"):
        errors.append(f"Historical report tree is forbidden: {rel}")

seen = {}
glossary = ROOT / "glossary" / "master_glossary.csv"
if glossary.exists():
    with glossary.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for line, row in enumerate(rows, 2):
        english = (row.get("english") or "").strip()
        arabic = (row.get("canonical_arabic") or "").strip()
        if not english or not arabic:
            errors.append(f"Glossary row {line} is incomplete")
        key = english.casefold()
        if key in seen:
            errors.append(f"Duplicate glossary English term: {english} (rows {seen[key]} and {line})")
        seen[key] = line

state_file = ROOT / "tracking" / "PROJECT_STATE.json"
if state_file.exists():
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
        if state.get("last_completed_stage", 0) < 292:
            errors.append("PROJECT_STATE.json is older than stage 292")
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"Invalid PROJECT_STATE.json: {exc}")

if errors:
    print("VALIDATION FAILED")
    for error in errors:
        print("-", error)
    sys.exit(1)

print("VALIDATION PASS")
print(f"Glossary terms: {len(seen)}")
