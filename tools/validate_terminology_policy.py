#!/usr/bin/env python3
from pathlib import Path
import csv
import sys

ROOT = Path(__file__).resolve().parents[1]
errors = []

required = [
    ROOT / "docs" / "STYLE_GUIDE.md",
    ROOT / "glossary" / "fixed_terms.csv",
    ROOT / "glossary" / "protected_tokens.txt",
]
for path in required:
    if not path.exists():
        errors.append(f"Missing required path: {path.relative_to(ROOT)}")

fixed_seen = {}
fixed_file = ROOT / "glossary" / "fixed_terms.csv"
if fixed_file.exists():
    with fixed_file.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for line, row in enumerate(rows, 2):
        english = (row.get("english") or "").strip()
        arabic = (row.get("canonical_arabic") or "").strip()
        category = (row.get("category") or "").strip()
        if not english or not arabic or not category:
            errors.append(f"Incomplete fixed term at row {line}")
        key = english.casefold()
        if key in fixed_seen:
            errors.append(f"Duplicate fixed term: {english}")
        fixed_seen[key] = line
    if len(fixed_seen) != 76:
        errors.append(f"Expected 76 fixed terms, found {len(fixed_seen)}")

expected_tokens = {
    "STR", "AGI", "VIT", "INT", "DEX", "LUK",
    "HP", "SP", "ATK", "MATK", "DEF", "MDEF",
    "HIT", "FLEE", "CRIT", "ASPD",
}
protected_file = ROOT / "glossary" / "protected_tokens.txt"
tokens = []
if protected_file.exists():
    tokens = [line.strip() for line in protected_file.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    if set(tokens) != expected_tokens:
        errors.append("Protected token list does not match the approved set")
    if len(tokens) != len(set(tokens)):
        errors.append("Duplicate protected token")

if errors:
    print("TERMINOLOGY POLICY FAILED")
    for error in errors:
        print("-", error)
    sys.exit(1)

print("TERMINOLOGY POLICY PASS")
print(f"Fixed terms: {len(fixed_seen)}")
print(f"Protected tokens: {len(tokens)}")
