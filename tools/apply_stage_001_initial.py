#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IZLUDE = ROOT / "rathena-master/npc/cities/izlude.txt"
GLOSSARY = ROOT / "glossary/master_glossary.csv"

REPLACEMENTS = {
    'mes "إذا أردت يوما زيارة مكان خلف جبل ميولنير، فعليك أن تجهز نفسك للتحدي. أو يمكنك الالتفاف حوله.";':
        'mes "إذا أردت يوما زيارة مكان يقع خلف جبل ميولنير، فعليك الاستعداد لهذا التحدي، أو الالتفاف حول الجبل.";',
    'mes "لا توجد هناك وحوش بورينغ وردية فحسب، بل توجد أيضا دروبس الصحراوية وبوبورينغ الأخضر.";':
        'mes "لا توجد هناك وحوش بورينغ وردية فحسب، بل ستجد أيضا دروبس الصحراوية وبوبورينغ الأخضر.";',
    'mes "أتريد معرفة بعض المعلومات المفيدة؟ حسنا، حسنا، دعني أخبرك! كسر ماغنوم لها خاصية النار.";':
        'mes "أتريد معرفة بعض المعلومات المفيدة؟ حسنا، حسنا، دعني أخبرك! مهارة كسر ماغنوم ذات خاصية النار.";',
    'mes "ليس إلا خطوة صغيرة نحو كسر ماغنوم.";':
        'mes "ليست إلا خطوة صغيرة نحو كسر ماغنوم.";',
    'mes "لذلك لن يكون فعالا جدا ضد الوحوش ذات خاصية الماء، لكنه مثالي ضد الوحوش غير الميتة والوحوش ذات خاصية الأرض!";':
        'mes "لذلك لن يكون فعالا جدا ضد الوحوش ذات خاصية الماء، لكنه مثالي ضد الوحوش غير الميتة وذات خاصية الأرض!";',
}


def decode_preserving(data: bytes) -> tuple[str, str, bytes]:
    bom = b"\xef\xbb\xbf" if data.startswith(b"\xef\xbb\xbf") else b""
    payload = data[len(bom):]
    for encoding in ("utf-8", "cp1256"):
        try:
            return payload.decode(encoding), encoding, bom
        except UnicodeDecodeError:
            continue
    raise RuntimeError("Unsupported text encoding")


def write_preserving(path: Path, text: str, encoding: str, bom: bytes, newline: str) -> None:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if newline == "\r\n":
        normalized = normalized.replace("\n", "\r\n")
    path.write_bytes(bom + normalized.encode(encoding))


def patch_izlude() -> int:
    data = IZLUDE.read_bytes()
    newline = "\r\n" if b"\r\n" in data else "\n"
    text, encoding, bom = decode_preserving(data)
    changes = 0
    for old, new in REPLACEMENTS.items():
        count = text.count(old)
        if count == 0:
            raise RuntimeError(f"Expected Izlude text not found: {old}")
        text = text.replace(old, new)
        changes += count
    write_preserving(IZLUDE, text, encoding, bom, newline)
    return changes


def update_glossary() -> int:
    data = GLOSSARY.read_bytes()
    newline_bytes = b"\r\n" if b"\r\n" in data else b"\n"
    text = data.decode("utf-8-sig")
    if any(line.startswith("Magnum Break,") for line in text.splitlines()):
        return 0
    entry = (
        "Magnum Break,كسر ماغنوم,مهارة | الاسم المعتمد في ملفات المهارات وحوارات إزلود,"
        "1,rathena-master/npc/cities/izlude.txt,,approved,"
        "ثبت في الدورة الثانية بعد التحقق من ملفات المهارات والحزمة."
    ).encode("utf-8")
    if not data.endswith((b"\n", b"\r")):
        data += newline_bytes
    GLOSSARY.write_bytes(data + entry + newline_bytes)
    return 1


def main() -> None:
    dialogue_changes = patch_izlude()
    glossary_changes = update_glossary()
    print(f"Izlude replacements: {dialogue_changes}")
    print(f"Glossary entries: {glossary_changes}")


if __name__ == "__main__":
    main()
