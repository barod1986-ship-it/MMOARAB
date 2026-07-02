#!/usr/bin/env python3
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
errors: list[str] = []
warnings: list[str] = []

required = [
    ROOT / "docs" / "STYLE_GUIDE.md",
    ROOT / "glossary" / "fixed_terms.csv",
    ROOT / "glossary" / "protected_tokens.txt",
]
for path in required:
    if not path.exists():
        errors.append(f"Missing required path: {path.relative_to(ROOT)}")

fixed_seen: dict[str, int] = {}
fixed_file = ROOT / "glossary" / "fixed_terms.csv"
if fixed_file.exists():
    with fixed_file.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required_columns = {"english", "canonical_arabic", "category"}
    if rows and not required_columns.issubset(rows[0].keys()):
        errors.append("Fixed terminology columns are incomplete")
    allowed_categories = {"job", "general", "monster_type", "skill_or_status"}
    for line, row in enumerate(rows, 2):
        english = (row.get("english") or "").strip()
        arabic = (row.get("canonical_arabic") or "").strip()
        category = (row.get("category") or "").strip()
        if not english or not arabic or not category:
            errors.append(f"Incomplete fixed term at row {line}")
        if category and category not in allowed_categories:
            errors.append(f"Unknown fixed terminology category at row {line}: {category}")
        key = english.casefold()
        if key in fixed_seen:
            errors.append(f"Duplicate fixed English term: {english} (rows {fixed_seen[key]} and {line})")
        fixed_seen[key] = line
    if len(fixed_seen) < 76:
        errors.append(f"Expected at least 76 approved fixed terms, found {len(fixed_seen)}")


master_file = ROOT / "glossary" / "master_glossary.csv"
if master_file.exists() and fixed_seen:
    fixed_values = {}
    with fixed_file.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            fixed_values[(row.get("english") or "").strip().casefold()] = (row.get("canonical_arabic") or "").strip()
    with master_file.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            english = (row.get("english") or "").strip()
            canonical = (row.get("canonical_arabic") or "").strip()
            context = (row.get("category_or_context") or "").strip()
            fixed_value = fixed_values.get(english.casefold())
            if fixed_value and canonical and canonical != fixed_value:
                warnings.append(
                    f"Fixed/master context difference: {english}: fixed={fixed_value!r}, "
                    f"master={canonical!r}, context={context!r}"
                )

expected_tokens = {
    "STR", "AGI", "VIT", "INT", "DEX", "LUK",
    "HP", "SP", "ATK", "MATK", "DEF", "MDEF",
    "HIT", "FLEE", "CRIT", "ASPD",
}
protected_file = ROOT / "glossary" / "protected_tokens.txt"
tokens: list[str] = []
if protected_file.exists():
    tokens = [
        line.strip()
        for line in protected_file.read_text(encoding="utf-8-sig").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if len(tokens) != len(set(tokens)):
        errors.append("Duplicate protected token")
    if set(tokens) != expected_tokens:
        missing = sorted(expected_tokens - set(tokens))
        extra = sorted(set(tokens) - expected_tokens)
        if missing:
            errors.append("Missing protected tokens: " + ", ".join(missing))
        if extra:
            errors.append("Unexpected protected tokens: " + ", ".join(extra))
    for token in tokens:
        if not re.fullmatch(r"[A-Z]+", token):
            errors.append(f"Invalid protected token format: {token}")

if errors:
    print("TERMINOLOGY POLICY FAILED")
    for error in errors:
        print("ERROR:", error)
    sys.exit(1)

print("TERMINOLOGY POLICY PASS")
print(f"Fixed terms: {len(fixed_seen)}")
print(f"Protected tokens: {len(tokens)}")
for warning in warnings:
    print("WARNING:", warning)
