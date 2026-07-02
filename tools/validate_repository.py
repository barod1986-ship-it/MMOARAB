#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
errors: list[str] = []
warnings: list[str] = []

REQUIRED_PATHS = [
    "AGENTS.md",
    "README.md",
    ".github/pull_request_template.md",
    ".github/workflows/qa.yml",
    "docs/AI_WORKFLOW.md",
    "docs/STYLE_GUIDE.md",
    "docs/ONLINE_SOURCE_POLICY.md",
    "docs/SYNC_SCOPE.md",
    "docs/QA_AUTOMATION.md",
    "docs/progress/PROJECT_STATUS.md",
    "glossary/fixed_terms.csv",
    "glossary/master_glossary.csv",
    "glossary/protected_tokens.txt",
    "tools/validate_repository.py",
    "tools/validate_terminology_policy.py",
    "tools/validate_translation_content.py",
    "tracking/PROJECT_STATE.json",
]

for relative in REQUIRED_PATHS:
    if not (ROOT / relative).exists():
        errors.append(f"Missing required path: {relative}")

FORBIDDEN_SUFFIXES = {".zip", ".7z", ".rar", ".bak", ".backup", ".old", ".xlsx", ".xls"}
for path in ROOT.rglob("*"):
    relative_path = path.relative_to(ROOT)
    if any(part in {".git", ".venv", "venv", "__pycache__"} for part in relative_path.parts):
        continue
    if not path.is_file():
        continue
    relative = relative_path.as_posix()
    lowered = relative.lower()
    if "نسخة_احتياطية_قبل_المرحلة_" in relative or "_before_stage" in lowered:
        errors.append(f"Manual backup is forbidden: {relative}")
    if path.suffix.lower() in FORBIDDEN_SUFFIXES and not path.name.startswith("~$"):
        errors.append(f"Archive, backup, or spreadsheet is forbidden in Git: {relative}")
    if relative.startswith("تقارير_المراجعة_الحوارية/"):
        errors.append(f"Historical report tree is forbidden: {relative}")

# The same English term may legitimately have different translations in different contexts.
# It must remain unique inside the same context.
seen: dict[tuple[str, str], int] = {}
glossary = ROOT / "glossary" / "master_glossary.csv"
if glossary.exists():
    with glossary.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required_columns = {
        "english", "canonical_arabic", "category_or_context", "arabic_aliases", "source_stages"
    }
    if rows and not required_columns.issubset(rows[0].keys()):
        errors.append("Glossary columns are incomplete")
    for line, row in enumerate(rows, 2):
        english = (row.get("english") or "").strip()
        arabic = (row.get("canonical_arabic") or "").strip()
        context = (row.get("category_or_context") or "").strip()
        if not english or not arabic:
            errors.append(f"Glossary row {line} is incomplete")
        key = (english.casefold(), context.casefold())
        if key in seen:
            errors.append(
                f"Duplicate glossary term in the same context: {english!r} / {context!r} "
                f"(rows {seen[key]} and {line})"
            )
        seen[key] = line

state_path = ROOT / "tracking" / "PROJECT_STATE.json"
state: dict = {}
if state_path.exists():
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
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
    elif next_stage != last_stage + 1:
        errors.append("next_stage must equal last_completed_stage + 1")

    next_files = state.get("next_files")
    if not isinstance(next_files, list) or not next_files:
        errors.append("next_files must contain at least one file")

    mandatory_flags = [
        "glossary_update_required_every_stage",
        "fixed_terms_required",
        "protected_tokens_required",
        "style_guide_required",
        "online_research_required_when_needed",
        "primary_sources_first",
        "source_citations_required",
        "pre_renewal_source_check_required",
        "cross_file_sync_required",
        "translation_correction_required",
        "ci_required",
        "content_validation_required",
    ]
    for key in mandatory_flags:
        if state.get(key) is not True:
            errors.append(f"Required project flag must be true: {key}")

    if state.get("baseline_import_complete"):
        essential = [
            "rathena-master/npc/cities/izlude.txt",
            "rathena-master/npc/cities/prontera.txt",
            "rathena-master/npc_EN/cities/izlude.txt",
            "rathena-master/npc_EN/cities/prontera.txt",
            "System/LuaFiles514/itemInfo.lua",
            "data/luafiles514/lua files/navigation/navi_npc_krpri.lub",
        ]
        for relative in essential:
            if not (ROOT / relative).is_file():
                errors.append(f"Baseline marked complete but missing: {relative}")

        game_roots = [ROOT / "rathena-master", ROOT / "System", ROOT / "data"]
        game_files = sum(1 for base in game_roots if base.exists() for path in base.rglob("*") if path.is_file())
        if game_files < 1800:
            errors.append(f"Baseline marked complete but only {game_files} game/source files were found")
    else:
        warnings.append("Clean game baseline has not been imported completely yet")

if errors:
    print("VALIDATION FAILED")
    for error in errors:
        print("ERROR:", error)
    for warning in warnings:
        print("WARNING:", warning)
    sys.exit(1)

print("VALIDATION PASS")
print(f"Glossary term/context pairs: {len(seen)}")
for warning in warnings:
    print("WARNING:", warning)
