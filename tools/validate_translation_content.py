#!/usr/bin/env python3
"""Validate changed MMOARAB translation files without rewriting them.

The checker is intentionally conservative:
- byte-level encoding/BOM/newline changes are errors for existing files;
- internal NPC/script identifiers are compared with the base revision;
- protected English abbreviations are compared with the English counterpart;
- deprecated Arabic aliases are reported as warnings by default.

During the first baseline import, counterpart differences are warnings unless
--strict-counterparts is requested. This keeps the import reviewable while
still producing an audit list for later cleanup.
"""

from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_EXTENSIONS = {".txt", ".lua", ".lub", ".yml", ".yaml", ".conf", ".ini", ".csv"}
PROTECTED_FILE = ROOT / "glossary" / "protected_tokens.txt"
GLOSSARY_FILE = ROOT / "glossary" / "master_glossary.csv"

INTERNAL_REF_RE = re.compile(r"::[A-Za-z0-9_#@]+")
EVENT_LABEL_RE = re.compile(r"(?m)^\s*(On[A-Za-z0-9_]+):")
DUPLICATE_RE = re.compile(r"duplicate\s*\(\s*([^)]*?)\s*\)", re.IGNORECASE)
TOKEN_BOUNDARY = r"(?<![A-Za-z0-9_]){}(?![A-Za-z0-9_])"
ARABIC_RE = re.compile(r"[\u0600-\u06FF]")
QUOTED_STRING_RE = re.compile(r'"(?:\\.|[^"\\])*"')
ANY_INTERNAL_RE = re.compile(r"::([^\s,;{}()]+)")


@dataclass(frozen=True)
class TextInfo:
    encoding: str
    bom: str
    newline: str
    text: str


def run_git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=check, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )


def valid_commit(ref: str | None) -> bool:
    if not ref or set(ref) == {"0"}:
        return False
    return run_git("cat-file", "-e", f"{ref}^{{commit}}", check=False).returncode == 0


def git_object_bytes(spec: str) -> bytes | None:
    result = subprocess.run(
        ["git", "show", spec], cwd=ROOT, check=False,
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    return result.stdout if result.returncode == 0 else None


def is_translation_file(name: str) -> bool:
    normalized = name.replace("\\", "/")
    path = Path(normalized)
    if path.suffix.lower() not in TEXT_EXTENSIONS:
        return False
    if normalized.startswith("rathena-master/npc_EN/"):
        return False
    if normalized.startswith("rathena-master/npc/"):
        return True
    if normalized.startswith("System/"):
        # Arabic files may retain _EN in their historical filenames; _EN_EN is the reference.
        return "_EN_EN." not in path.name
    if normalized.startswith("data/"):
        return not re.search(r"_EN\.[^.]+$", path.name, re.IGNORECASE)
    return False


def selected_files(base: str | None, all_files: bool) -> list[str]:
    if all_files:
        names: set[str] = set()
        for root_name in ("rathena-master/npc", "System", "data"):
            root_path = ROOT / root_name
            if root_path.exists():
                names.update(str(path.relative_to(ROOT)).replace("\\", "/") for path in root_path.rglob("*") if path.is_file())
    elif valid_commit(base):
        names = set(run_git("diff", "--name-only", "--diff-filter=ACMR", f"{base}...HEAD").stdout.splitlines())
        names.update(run_git("diff", "--name-only", "--diff-filter=ACMR").stdout.splitlines())
        names.update(run_git("diff", "--cached", "--name-only", "--diff-filter=ACMR").stdout.splitlines())
        names.update(run_git("ls-files", "--others", "--exclude-standard").stdout.splitlines())
    else:
        names = set(run_git("ls-files").stdout.splitlines())
        names.update(run_git("ls-files", "--others", "--exclude-standard").stdout.splitlines())
    result = []
    for name in names:
        normalized = name.replace("\\", "/")
        if is_translation_file(normalized) and (ROOT / normalized).is_file():
            result.append(normalized)
    return sorted(set(result))


def inspect_bytes(data: bytes) -> TextInfo:
    if data.startswith(b"\xef\xbb\xbf"):
        text = data.decode("utf-8-sig")
        encoding, bom = "utf-8", "utf-8-bom"
    else:
        try:
            text = data.decode("utf-8")
            encoding, bom = "utf-8", "none"
        except UnicodeDecodeError:
            text = data.decode("cp1256")
            encoding, bom = "cp1256", "none"

    crlf = data.count(b"\r\n")
    bare_lf = data.count(b"\n") - crlf
    bare_cr = data.count(b"\r") - crlf
    styles = [("crlf", crlf), ("lf", bare_lf), ("cr", bare_cr)]
    present = [name for name, count in styles if count]
    newline = "mixed" if len(present) > 1 else (present[0] if present else "none")
    return TextInfo(encoding, bom, newline, text)


def counterpart_for(relative: str) -> Path | None:
    source = ROOT / relative
    candidates: list[Path] = []
    if relative.startswith("rathena-master/npc/"):
        candidates.append(ROOT / relative.replace("rathena-master/npc/", "rathena-master/npc_EN/", 1))
    elif relative.startswith("System/"):
        name = source.name
        if "_EN." in name:
            candidates.append(source.with_name(name.replace("_EN.", "_EN_EN.", 1)))
        candidates.append(source.with_name(f"{source.stem}_EN{source.suffix}"))
    elif relative.startswith("data/"):
        candidates.append(source.with_name(f"{source.stem}_EN{source.suffix}"))

    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def load_tokens() -> list[str]:
    if not PROTECTED_FILE.exists():
        return []
    return [line.strip() for line in PROTECTED_FILE.read_text(encoding="utf-8-sig").splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


def load_aliases() -> list[tuple[str, str]]:
    aliases: list[tuple[str, str]] = []
    if not GLOSSARY_FILE.exists():
        return aliases
    with GLOSSARY_FILE.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            canonical = (row.get("canonical_arabic") or "").strip()
            raw = (row.get("arabic_aliases") or "").strip()
            if not canonical or not raw:
                continue
            for alias in re.split(r"\s*(?:/|\||;)\s*", raw):
                alias = alias.strip()
                if len(alias) >= 3 and alias != canonical and ARABIC_RE.search(alias):
                    aliases.append((alias, canonical))
    return aliases


def structural_tokens(text: str) -> dict[str, Counter[str]]:
    return {
        "internal references": Counter(INTERNAL_REF_RE.findall(text)),
        "event labels": Counter(EVENT_LABEL_RE.findall(text)),
        "duplicate targets": Counter(item.strip() for item in DUPLICATE_RE.findall(text)),
    }


def count_token(text: str, token: str) -> int:
    return len(re.findall(TOKEN_BOUNDARY.format(re.escape(token)), text))


def report_issue(message: str, strict: bool, errors: list[str], warnings: list[str]) -> None:
    (errors if strict else warnings).append(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", help="Base commit for changed-file and byte-preservation checks")
    parser.add_argument("--all", action="store_true", help="Audit every tracked translation file")
    parser.add_argument("--strict-aliases", action="store_true")
    parser.add_argument("--strict-counterparts", action="store_true")
    parser.add_argument("--strict-structure", action="store_true")
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []
    tokens = load_tokens()
    aliases = load_aliases()
    files = selected_files(args.base, args.all)
    base_is_valid = valid_commit(args.base)
    base_files = set(
        run_git("ls-tree", "-r", "--name-only", args.base).stdout.splitlines()
    ) if base_is_valid and args.base else set()

    for relative in files:
        path = ROOT / relative
        try:
            current = inspect_bytes(path.read_bytes())
        except UnicodeDecodeError as exc:
            errors.append(f"Unsupported or damaged encoding: {relative}: {exc}")
            continue

        if current.newline == "mixed":
            errors.append(f"Mixed line endings: {relative}")

        if relative.startswith("rathena-master/npc/"):
            for line_no, line in enumerate(current.text.splitlines(), 1):
                code_only = QUOTED_STRING_RE.sub('""', line)
                for match in ANY_INTERNAL_RE.finditer(code_only):
                    if ARABIC_RE.search(match.group(1)):
                        errors.append(
                            f"Arabic internal name after ::: {relative}:{line_no}: {match.group(1)!r}"
                        )

        old_data = git_object_bytes(f"{args.base}:{relative}") if relative in base_files else None
        if old_data is not None:
            try:
                old = inspect_bytes(old_data)
            except UnicodeDecodeError:
                old = None
            if old:
                if (old.encoding, old.bom) != (current.encoding, current.bom):
                    errors.append(
                        f"Encoding/BOM changed: {relative}: "
                        f"{old.encoding}/{old.bom} -> {current.encoding}/{current.bom}"
                    )
                if old.newline != current.newline:
                    errors.append(f"Line endings changed: {relative}: {old.newline} -> {current.newline}")
                before, after = structural_tokens(old.text), structural_tokens(current.text)
                for label in before:
                    if before[label] != after[label]:
                        report_issue(
                            f"Structural {label} changed: {relative}",
                            args.strict_structure, errors, warnings,
                        )

        counterpart = counterpart_for(relative)
        if counterpart:
            try:
                english = inspect_bytes(counterpart.read_bytes()).text
            except UnicodeDecodeError:
                english = ""
            for token in tokens:
                expected, actual = count_token(english, token), count_token(current.text, token)
                if expected and actual < expected:
                    report_issue(
                        f"Protected token mismatch: {relative}: {token} expected>={expected}, found={actual}",
                        (args.strict_counterparts or old_data is not None), errors, warnings,
                    )

        for alias, canonical in aliases:
            if alias in current.text:
                report_issue(
                    f"Glossary alias found; verify context: {relative}: {alias!r} -> {canonical!r}",
                    args.strict_aliases, errors, warnings,
                )

    if errors:
        print("TRANSLATION CONTENT FAILED")
        for item in errors:
            print("ERROR:", item)
        for item in warnings:
            print("WARNING:", item)
        return 1

    print("TRANSLATION CONTENT PASS")
    print(f"Files checked: {len(files)}")
    print(f"Warnings: {len(warnings)}")
    for item in warnings:
        print("WARNING:", item)
    return 0


if __name__ == "__main__":
    sys.exit(main())
