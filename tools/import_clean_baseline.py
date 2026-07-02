#!/usr/bin/env python3
"""Safely import the clean MMOARAB baseline into a review branch.

The script runs from the extracted clean package. It clones the current main
branch into a separate work directory, copies the authoritative snapshot,
runs all validators, commits the result, and optionally pushes the branch.
It never writes directly to main and never commits the ZIP archive itself.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPO = "https://github.com/barod1986-ship-it/MMOARAB.git"
DEFAULT_BRANCH = "setup/cycle-2-clean-baseline"

AUTHORITATIVE_DIRECTORIES = ["rathena-master", "System", "data"]
MERGE_DIRECTORIES = [".github", "docs", "glossary", "tools", "tracking"]
OBSOLETE_PATHS = [
    "docs/progress/LAST_STAGE_292.md",
    "docs/progress/completed_files.csv",
    "docs/progress/remaining_files.csv",
    "docs/progress/excluded_files.csv",
]
COPY_FILES = [
    ".gitattributes",
    ".gitignore",
    "AGENTS.md",
    "README.md",
    "official_msg_boards.txt",
]
ESSENTIAL_SOURCE_FILES = [
    "rathena-master/npc/cities/izlude.txt",
    "rathena-master/npc/cities/prontera.txt",
    "rathena-master/npc_EN/cities/izlude.txt",
    "rathena-master/npc_EN/cities/prontera.txt",
    "System/LuaFiles514/itemInfo.lua",
    "data/luafiles514/lua files/navigation/navi_npc_krpri.lub",
]


def run(command: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(command), flush=True)
    return subprocess.run(
        command,
        cwd=cwd,
        check=check,
        text=True,
        stdout=None,
        stderr=None,
    )


def capture(command: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout.strip()


def verify_source() -> None:
    missing = [relative for relative in ESSENTIAL_SOURCE_FILES if not (SOURCE_ROOT / relative).is_file()]
    if missing:
        raise RuntimeError("The extracted package is incomplete. Missing: " + ", ".join(missing))

    source_files = sum(
        1
        for root_name in ("rathena-master", "System", "data")
        for path in (SOURCE_ROOT / root_name).rglob("*")
        if path.is_file()
    )
    if source_files < 1800:
        raise RuntimeError(f"Expected a full baseline, but only {source_files} game/source files were found")
    print(f"Verified clean package: {source_files} game/source files", flush=True)


def choose_branch(repo_url: str, requested: str) -> str:
    result = subprocess.run(
        ["git", "ls-remote", "--heads", repo_url, f"refs/heads/{requested}"],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode == 0 and result.stdout.strip():
        suffix = datetime.now().strftime("%Y%m%d-%H%M%S")
        selected = f"{requested}-{suffix}"
        print(f"Remote branch already exists; using {selected}")
        return selected
    return requested


def copy_snapshot(destination: Path) -> None:
    ignore = shutil.ignore_patterns(".git", "__pycache__", "*.pyc", "*.pyo", "*.zip", "*.7z", "*.rar")

    for name in AUTHORITATIVE_DIRECTORIES:
        source = SOURCE_ROOT / name
        target = destination / name
        if not source.exists():
            raise RuntimeError(f"Required source directory is missing: {name}")
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target, copy_function=shutil.copy2, ignore=ignore)

    for name in MERGE_DIRECTORIES:
        source = SOURCE_ROOT / name
        target = destination / name
        if not source.exists():
            raise RuntimeError(f"Required source directory is missing: {name}")
        shutil.copytree(source, target, dirs_exist_ok=True, copy_function=shutil.copy2, ignore=ignore)

    for relative in OBSOLETE_PATHS:
        target = destination / relative
        if target.is_file() or target.is_symlink():
            target.unlink()
        elif target.is_dir():
            shutil.rmtree(target)

    for name in COPY_FILES:
        source = SOURCE_ROOT / name
        target = destination / name
        if not source.exists():
            raise RuntimeError(f"Required source file is missing: {name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def ensure_state_complete(destination: Path) -> None:
    state_path = destination / "tracking" / "PROJECT_STATE.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["baseline_import_complete"] = True
    state["updated_at"] = datetime.now().date().isoformat()
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def configure_git(workdir: Path) -> None:
    run(["git", "config", "core.autocrlf", "false"], cwd=workdir)
    run(["git", "config", "core.safecrlf", "false"], cwd=workdir)

    name = subprocess.run(
        ["git", "config", "user.name"], cwd=workdir, check=False,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    ).stdout.strip()
    email = subprocess.run(
        ["git", "config", "user.email"], cwd=workdir, check=False,
        text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    ).stdout.strip()
    if not name:
        run(["git", "config", "user.name", "barod1986-ship-it"], cwd=workdir)
    if not email:
        run(["git", "config", "user.email", "barod1986@gmail.com"], cwd=workdir)


def validate(workdir: Path) -> None:
    python = sys.executable
    run([python, "tools/validate_repository.py"], cwd=workdir)
    run([python, "tools/validate_terminology_policy.py"], cwd=workdir)
    run([python, "tools/validate_translation_content.py", "--all"], cwd=workdir)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-url", default=DEFAULT_REPO)
    parser.add_argument("--branch", default=DEFAULT_BRANCH)
    parser.add_argument("--workdir", type=Path, help="Empty directory to use instead of a generated temporary directory")
    parser.add_argument("--no-push", action="store_true", help="Create and validate the commit without pushing")
    args = parser.parse_args()

    try:
        verify_source()
        if shutil.which("git") is None:
            raise RuntimeError("Git is not installed or is not available in PATH")

        branch = choose_branch(args.repo_url, args.branch)
        if args.workdir:
            workdir = args.workdir.resolve()
            if workdir.exists() and any(workdir.iterdir()):
                raise RuntimeError(f"Work directory is not empty: {workdir}")
            workdir.mkdir(parents=True, exist_ok=True)
        else:
            workdir = Path(tempfile.mkdtemp(prefix="MMOARAB_baseline_"))

        print(f"Work directory: {workdir}", flush=True)
        run(["git", "clone", "--branch", "main", "--single-branch", args.repo_url, str(workdir)])
        configure_git(workdir)
        run(["git", "checkout", "-b", branch], cwd=workdir)

        copy_snapshot(workdir)
        ensure_state_complete(workdir)
        run(["git", "add", "-A"], cwd=workdir)
        validate(workdir)
        run([
            "git", "diff", "--cached", "--check", "--",
            ".github", "docs", "glossary", "tools", "tracking",
            "README.md", "AGENTS.md", ".gitignore", ".gitattributes",
        ], cwd=workdir)

        status = capture(["git", "status", "--short"], cwd=workdir)
        if not status:
            print("No changes were found; nothing to commit.")
            return 0

        status_lines = status.splitlines()
        print(f"Files prepared for commit: {len(status_lines)}", flush=True)
        for line in status_lines[:60]:
            print(line)
        if len(status_lines) > 60:
            print(f"... and {len(status_lines) - 60} more files")
        run(["git", "commit", "--quiet", "-m", "chore: import cycle 2 clean baseline and QA"], cwd=workdir)

        if args.no_push:
            print("Commit created locally; push was skipped because --no-push was used.")
        else:
            run(["git", "push", "-u", "origin", branch], cwd=workdir)
            print("\nBranch uploaded successfully.")
            print(f"Open: https://github.com/barod1986-ship-it/MMOARAB/compare/main...{branch}?expand=1")

        print(f"Local worktree retained at: {workdir}")
        return 0
    except (RuntimeError, subprocess.CalledProcessError, OSError, json.JSONDecodeError) as exc:
        print(f"IMPORT FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
