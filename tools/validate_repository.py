#!/usr/bin/env python3
from pathlib import Path
import csv
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
errors = []
warnings = []

always_required = [
    ROOT / "AGENTS.md",
    ROOT / "README.md",
    ROOT / "docs" / "AI_WORKFLOW.md",
    ROOT / "docs" / "SYNC_SCOPE.md",
    ROOT / "docs" / "progress" / "PROJECT_STATUS.md",
    ROOT / "glossary" / "master_glossary.csv",
    ROOT / "tracking" / "PROJECT_STATE.json",
]
for path in always_required:
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
    required_columns = {"english", "canonical_arabic", "category_or_context", "arabic_aliases", "source_stages"}
    if rows and not required_columns.issubset(rows[0].keys()):
        errors.append("Glossary columns are incomplete")
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
state = {}
if state_file.exists():
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"Invalid PROJECT_STATE.json: {exc}")

if state:
    if state.get("review_cycle") != 2:
        errors.append("Active review_cycle must be 2")
    if state.get("restart_from_beginning") is not True:
        errors.append("restart_from_beginning must be true")
    last_stage = state.get("last_completed_stage")
    next_stage = state.get("next_stage")
    if not isinstance(last_stage, int) or last_stage < 0:
        errors.append("last_completed_stage must be a non-negative integer")
    if isinstance(last_stage, int) and next_stage != last_stage + 1:
        errors.append("next_stage must equal last_completed_stage + 1")
    next_files = state.get("next_files")
    if not isinstance(next_files, list) or not next_files:
        errors.append("next_files must contain at least one file")
    if state.get("glossary_update_required_every_stage") is not True:
        errors.append("Glossary updates/checks must be mandatory")
    if state.get("cross_file_sync_required") is not True:
        errors.append("Cross-file synchronization must be mandatory")
    if state.get("translation_correction_required") is not True:
        errors.append("Translation correction must be mandatory")

    if state.get("baseline_import_complete"):
        for path in [ROOT / "rathena-master", ROOT / "System", ROOT / "data"]:
            if not path.exists():
                errors.append(f"Baseline marked complete but missing: {path.relative_to(ROOT)}")
    else:
        warnings.append("Clean game baseline has not been imported completely yet")

if errors:
    print("VALIDATION FAILED")
    for error in errors:
        print("-", error)
    sys.exit(1)

print("VALIDATION PASS")
print(f"Glossary terms: {len(seen)}")
for warning in warnings:
    print("WARNING:", warning)
