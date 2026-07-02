#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = ROOT / "تقارير_المراجعة_الحوارية"
STAGE_DIR = REPORT_ROOT / "المرحلة_262"
RESULT = STAGE_DIR / "نتيجة_المرحلة_262.json"
COMPARISON = STAGE_DIR / "تقرير_المرحلة_262_مقارنة_الحزمة.csv"
XLSX_REL = "تقارير_المراجعة_الحوارية/ملف_تتبع_المراجعة_الحوارية_حتى_المرحلة_262.xlsx"
TEMP = {
    ".github/workflows/stage262.yml",
    "tools/apply_stage_262.py",
    "tools/fix_stage262_reports.py",
}
MODIFIED = {
    "rathena-master/npc/other/hugel_bingo.txt",
    "تقارير_المراجعة_الحوارية/00_الملفات_المتبقية.csv",
    "تقارير_المراجعة_الحوارية/00_الملفات_المكتملة.csv",
    "تقارير_المراجعة_الحوارية/00_متابعة_المراجعة_الحوارية.csv",
    "تقارير_المراجعة_الحوارية/00_متابعة_المراجعة_الحوارية.md",
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_show(rel: str) -> bytes:
    return subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=ROOT)


def csv_text(rows: list[list[object]]) -> bytes:
    out = io.StringIO(newline="")
    csv.writer(out, lineterminator="\n").writerows(rows)
    return b"\xef\xbb\xbf" + out.getvalue().encode("utf-8")


def main() -> None:
    tracked_raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    baseline = [x.decode("utf-8") for x in tracked_raw.split(b"\0") if x]
    baseline = sorted(x for x in baseline if x not in TEMP)

    stage_files = sorted(
        str(path.relative_to(ROOT)).replace(os.sep, "/")
        for path in STAGE_DIR.rglob("*")
        if path.is_file()
    )
    new_files = sorted(set(stage_files + [XLSX_REL]))

    result = json.loads(RESULT.read_text(encoding="utf-8"))
    result["changed_existing_files"] = len(MODIFIED)
    result["changed_existing_paths"] = sorted(MODIFIED)
    result["new_files"] = len(new_files)
    result["new_file_paths"] = new_files
    result["deleted_files"] = []
    result["status_counts"] = {
        "معدل": len(MODIFIED),
        "دون تغيير": len(baseline) - len(MODIFIED),
        "جديد": len(new_files),
        "محذوف": 0,
    }
    RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    rows: list[list[object]] = [["المسار", "الحالة", "SHA256 قبل", "SHA256 بعد"]]
    for rel in baseline:
        path = ROOT / rel
        before = sha256(git_show(rel))
        after = sha256(path.read_bytes()) if path.exists() else ""
        status = "معدل" if rel in MODIFIED else "دون تغيير"
        if status == "دون تغيير" and before != after:
            raise RuntimeError(f"ملف غير متوقع تغير أثناء المرحلة: {rel}")
        if status == "معدل" and before == after:
            raise RuntimeError(f"ملف متوقع تعديله لم يتغير: {rel}")
        rows.append([rel, status, before, after])

    for rel in new_files:
        path = ROOT / rel
        if rel.endswith("تقرير_المرحلة_262_مقارنة_الحزمة.csv"):
            after = "SELF"
        else:
            after = sha256(path.read_bytes())
        rows.append([rel, "جديد", "", after])

    COMPARISON.write_bytes(csv_text(rows))

    me = ROOT / "tools/fix_stage262_reports.py"
    if me.exists():
        me.unlink()

    print(json.dumps({
        "modified": len(MODIFIED),
        "unchanged": len(baseline) - len(MODIFIED),
        "new": len(new_files),
        "rows": len(rows) - 1,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
