from __future__ import annotations

from pathlib import Path


def read_preserved(path: Path) -> tuple[str, bool]:
    raw = path.read_bytes()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    return raw.decode("utf-8-sig" if has_bom else "utf-8"), has_bom


def write_preserved(path: Path, text: str, has_bom: bool) -> None:
    payload = text.encode("utf-8")
    if has_bom:
        payload = b"\xef\xbb\xbf" + payload
    path.write_bytes(payload)


def replace_exact(text: str, old: str, new: str, expected: int = 1) -> str:
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f"Expected {expected} occurrence(s), found {count}: {old}")
    return text.replace(old, new)


def update_izlude() -> None:
    path = Path("rathena-master/npc/cities/izlude.txt")
    text, has_bom = read_preserved(path)

    replacements = [
        ("تعالوا واركبوا الرياح", "تعالوا وأبحروا مع الريح"),
        ("150 زيني فقط للركوب!", "الرحلة مقابل 150 زيني فقط!"),
        ("500 زيني فقط للركوب!", "الرحلة مقابل 500 زيني فقط!"),
        (
            "إزلود هي المدينة التابعة لبرونتيرا، عاصمة مملكة رون-ميدغارتس.",
            "إزلود مدينة تابعة لبرونتيرا، عاصمة مملكة رون-ميدغارتس.",
        ),
        (
            "إزلود مهمة جدا لمملكتنا بسبب وجود جمعية السيافين هنا، وكذلك لأنها مسؤولة عن حماية ساحل رون-ميدغارتس.",
            "تكتسب إزلود أهمية كبيرة لمملكتنا لوجود جمعية السيافين فيها، ولأنها تتولى حماية ساحل رون-ميدغارتس.",
        ),
        ("فلا تتجول فيها بلا حذر.", "فلا تتجول فيها دون حذر."),
        ("ليتحدوا أنفسهم ويختبروا مهاراتهم.", "ليخوضوا التحديات ويختبروا مهاراتهم."),
        ("يمكنك القتال ضد وحوش بمستويات مختلفة.", "يمكنك مواجهة وحوش بمستويات مختلفة."),
        (
            "بعيدا عن أخطار الجبل نفسه، تعيش هناك حشرات شرسة بجنون أيضا. أعني أنها ستهاجمك بلا أي سبب.",
            "إلى جانب أخطار الجبل نفسه، تعيش هناك حشرات شديدة الشراسة، وستهاجمك بلا أي سبب.",
        ),
        (
            "إذا حاولت إلقاء السحر قربه، فسوف ينتبه ويتقدم ببطء ليحطمك. لذلك من الأفضل أن تحذر من غولم.",
            "إذا حاولت إلقاء السحر قربه، فسوف ينتبه ويقترب منك على مهل ليسحقك. لذلك من الأفضل أن تحذر من غولم.",
        ),
        ("ليس إلا خطوة صغيرة نحو كسر ماغنوم.", "ليست إلا خطوة صغيرة نحو كسر ماغنوم."),
        ("كسر ماغنوم لها خاصية النار.", "مهارة كسر ماغنوم ذات خاصية النار."),
        (
            "ألا تظن أن ارتفاع VIT والتدرب على طريقة تنفس فريدة تتيح استعادة HP بسرعة هما من أعظم مزايا السياف؟",
            "ألا تظن أن ارتفاع قيمة VIT والتدرب على طريقة تنفس فريدة تتيح استعادة HP بسرعة هما من أعظم مزايا السياف؟",
        ),
        ("أمر مهم آخر هو دقة إصابتك لخصومك.", "أمر مهم آخر هو دقة إصابتك بخصومك."),
        (
            "وتمثل DEX العامل الحاسم هنا؛ فكلما رفعتها، ضاقت الفجوة بين أدنى ضرر وأقصاه.",
            "وتمثل DEX العامل الحاسم هنا؛ فكلما دربت DEX، ضاقت الفجوة بين أدنى ضرر وأقصاه.",
        ),
        ("نعم، لقد تعبت حتى الموت.", "نعم، لقد أنهكني التعب."),
    ]

    for old, new in replacements:
        text = replace_exact(text, old, new)

    write_preserved(path, text, has_bom)


def update_glossary() -> None:
    path = Path("glossary/master_glossary.csv")
    text, has_bom = read_preserved(path)
    if "\nMagnum Break," in text or text.startswith("Magnum Break,"):
        return

    newline = "\r\n" if "\r\n" in text else "\n"
    anchor = (
        "Magnifier,عدسة مكبرة,itemInfo وسياق تقييم المعدات,6,"
        "تقارير_المراجعة_الحوارية/المرحلة_06/dialogue_stage6_glossary.csv,,approved,"
        "Merged from stage glossaries."
    )
    row = (
        "Magnum Break,كسر ماغنوم,مهارة | الاسم المعتمد في ملفات المهارات وحوار إزلود,1,"
        "rathena-master/npc/cities/izlude.txt,,approved,Confirmed in review cycle 2 stage 1."
    )
    text = replace_exact(text, anchor, anchor + newline + row)
    write_preserved(path, text, has_bom)


if __name__ == "__main__":
    update_izlude()
    update_glossary()
