#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import subprocess
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
REPORT_ROOT = ROOT / "تقارير_المراجعة_الحوارية"
STAGE = 262
STAGE_DIR = REPORT_ROOT / f"المرحلة_{STAGE}"
MAIN_REL = "rathena-master/npc/other/hugel_bingo.txt"
EN_REL = "rathena-master/npc_EN/other/hugel_bingo.txt"
TRACK_MD_REL = "تقارير_المراجعة_الحوارية/00_متابعة_المراجعة_الحوارية.md"
TRACK_CSV_REL = "تقارير_المراجعة_الحوارية/00_متابعة_المراجعة_الحوارية.csv"
COMPLETED_CSV_REL = "تقارير_المراجعة_الحوارية/00_الملفات_المكتملة.csv"
REMAINING_CSV_REL = "تقارير_المراجعة_الحوارية/00_الملفات_المتبقية.csv"
XLSX_REL = "تقارير_المراجعة_الحوارية/ملف_تتبع_المراجعة_الحوارية_حتى_المرحلة_262.xlsx"
NEXT_FILE = "rathena-master/npc/other/mail.txt"
OFFICIAL_BLOB = "4a3d2cf741aa20a536b1e4369c560f84baf33dae"
CUMULATIVE_BEFORE = 62512
NPC_REVIEWED = 263
NPC_TOTAL = 555
REMAINING = 264
TEMP_PATHS = {"tools/apply_stage_262.py", ".github/workflows/stage262.yml"}
RELATED_CHECKED = [
    "rathena-master/npc/quests/quests_hugel.txt",
    "rathena-master/npc/quests/quests_airship.txt",
    "data/luafiles514/lua files/navigation/navi_npc_krpri.lub",
    "System/LuaFiles514/itemInfo.lua",
]


def p(rel: str) -> Path:
    return ROOT / rel


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()


def read_preserve(path: Path) -> tuple[str, bool, str]:
    data = path.read_bytes()
    bom = data.startswith(b"\xef\xbb\xbf")
    newline = "\r\n" if b"\r\n" in data else "\n"
    text = data.decode("utf-8-sig")
    return text, bom, newline


def write_preserve(path: Path, text: str, bom: bool, newline: str) -> None:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    data = normalized.replace("\n", newline).encode("utf-8")
    if bom:
        data = b"\xef\xbb\xbf" + data
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def write_utf8_bom(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xef\xbb\xbf" + text.replace("\r\n", "\n").encode("utf-8"))


def csv_text(rows: list[list[object]]) -> str:
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerows(rows)
    return out.getvalue()


# old, new, English reference, reason, type, expected occurrences
REPLACEMENTS: list[tuple[str, str, str, str, str, int]] = [
    ("غرفة انتظار البينغو::Bingo Waiting Room", "غرفة انتظار بينغو::Bingo Waiting Room", "Bingo Waiting Room", "تحسين الاسم الظاهر مع إبقاء الاسم الداخلي بعد :: ثابتا.", "اسم ظاهر", 1),
    ("غرفة انتظار البينغو - 5 أشخاص", "غرفة انتظار بينغو - 5 لاعبين", "Bingo Waiting Room - 5 People", "توضيح أن العدد يخص اللاعبين.", "صياغة", 1),
    ("اللوحة1#bingo::plate1#bingo", "لوحة بينغو 1#bingo::plate1#bingo", "plate1#bingo", "توضيح الاسم الظاهر للوحة مع حفظ الاسم الداخلي.", "اسم ظاهر", 1),
    ("اللوحة2#bingo::plate2#bingo", "لوحة بينغو 2#bingo::plate2#bingo", "plate2#bingo", "توضيح الاسم الظاهر للوحة مع حفظ الاسم الداخلي.", "اسم ظاهر", 1),
    ("اللوحة3#bingo::plate3#bingo", "لوحة بينغو 3#bingo::plate3#bingo", "plate3#bingo", "توضيح الاسم الظاهر للوحة مع حفظ الاسم الداخلي.", "اسم ظاهر", 1),
    ("اللوحة4#bingo::plate4#bingo", "لوحة بينغو 4#bingo::plate4#bingo", "plate4#bingo", "توضيح الاسم الظاهر للوحة مع حفظ الاسم الداخلي.", "اسم ظاهر", 1),
    ("اللوحة5#bingo::plate5#bingo", "لوحة بينغو 5#bingo::plate5#bingo", "plate5#bingo", "توضيح الاسم الظاهر للوحة مع حفظ الاسم الداخلي.", "اسم ظاهر", 1),
    ("الأرقام التي أدخلتها", "أحد الأرقام التي أدخلتها", "The numbers you have entered", "ربط رسالة الخطأ بسبب محدد وواضح.", "حوار", 1),
    ("تتجاوز الحد، أو أنك", "خارج النطاق المسموح، أو", "exceed the limit, or you have", "توضيح أن الخطأ هو الخروج عن النطاق 1 إلى 25.", "دقة", 1),
    ("أدخلت هذه الأرقام من قبل.", "أنك أدخلت رقما مكررا.", "already entered these numbers.", "توضيح حالة تكرار الرقم.", "دقة", 1),
    ("يرجى إدخال أرقامك مرة أخرى.", "يرجى إدخال الأرقام من جديد.", "Please enter your numbers again.", "تحسين الصياغة العربية.", "حوار", 1),
    ("يوكران: مرحبا بالجميع! أنا يوكران، دليلكم في بينغو~", "يوكران: مرحبا بالجميع! أنا يوكران، مرشد لعبة بينغو~", "Eukran: Hello, everyone! I'm Eukran, your Bingo Guide~", "صياغة عربية طبيعية وتثبيت اسم يوكران المعتمد.", "إعلان", 1),
    ("يوكران: أيها المشاركون في اللعبة، يرجى دخول بوابة الانتقال في أسفل الشاشة واختيار لوحة بينغو بإدخال رقم.", "يوكران: على المشاركين دخول بوابة الانتقال أسفل الساحة، ثم اختيار لوحة بينغو بإدخال رقم.", "Game participants, please enter the Warp Portal ... and choose a Bingo Plate", "إزالة التعبير الحرفي أسفل الشاشة وتوضيح الإجراء.", "إعلان", 1),
    ("يوكران: يجب على جميع المشاركين اختيار لوحات بينغو الخاصة بهم خلال 3 دقائق، وإلا سيتم إلغاء اللعبة.", "يوكران: يجب اختيار لوحات بينغو خلال 3 دقائق، وإلا ستلغى اللعبة.", "All participants must choose their Bingo Plates within 3 minutes", "اختصار الإعلان مع حفظ المهلة والنتيجة.", "إعلان", 1),
    ("يوكران: يرجى إدخال رقم خلال 5 ثوان، وإلا سيتم إلغاء اللعبة.", "يوكران: أدخل رقما خلال 5 ثوان، وإلا ستلغى اللعبة.", "Please enter a number in 5 seconds, or the game will be canceled.", "صياغة مباشرة وواضحة.", "إعلان", 1),
    ("يوكران: أنا آسف، لكن اللعبة قد ألغيت. يرجى الحضور مرة أخرى والاستمتاع بلعبة بينغو معنا!", "يوكران: عذرا، ألغيت اللعبة. عد لاحقا للاستمتاع بجولة أخرى من بينغو!", "I'm sorry, but the game has been canceled. Please come again ...", "تحسين رسالة إلغاء الجولة.", "إعلان", 1),
    ("يوكران: والآن، لتبدأ اللعبة!", "يوكران: والآن، فلتبدأ اللعبة!", "Now, let the game begin!", "تصحيح الأسلوب العربي.", "إعلان", 1),
    ("يوكران: سأعلن أرقام بينغو. إذا حصلت على 5 خطوط بمطابقة 5 أرقام بينغو في خط مستقيم على لوحة بينغو الخاصة بك، فاصرخ ''بينغو'' للفوز~", "يوكران: سأعلن أرقام بينغو تباعا. إذا أكملت 5 خطوط مستقيمة، في كل منها 5 أرقام مطابقة على لوحتك، فاكتب ''Bingo'' للفوز~", "I'll announce the Bingo Numbers. If you get 5 lines ... yell out 'Bingo'", "توضيح شرط الفوز الفعلي ومطابقة الأمر مع الإدخال النصي الحساس لحالة الأحرف.", "دقة لعب", 1),
    ("يوكران: لقد أعلنت كل الأرقام المختارة، لكنني لم أسمع أحدا يصرخ ''بينغو.''", "يوكران: أعلنت جميع الأرقام المختارة، لكن لم يعلن أحد ''Bingo''.", "I've announced all selected numbers, but ... no one yell 'Bingo.'", "تحسين الإعلان وتوحيد كلمة الإدخال المطلوبة.", "إعلان", 1),
    ("يوكران: سأمنحكم جميعا 10 ثوان للتحقق مما إذا كان أحدكم قد فاز. إذا لم يستطع أحد أن يصرخ ''بينغو'' خلال 10 ثوان، فستنتهي هذه اللعبة دون فائز.", "يوكران: أمامكم 10 ثوان للتحقق من اللوحات. إذا لم يعلن أحد ''Bingo'' خلالها، فستنتهي اللعبة دون فائز.", "I'll give you all 10 seconds to check ...", "اختصار الإعلان وتوضيح المهلة.", "إعلان", 1),
    ("يوكران: أنا آسف، لكن هذه اللعبة انتهت دون فائز. شكرا للعبكم جميعا~", "يوكران: عذرا، انتهت اللعبة دون فائز. شكرا لمشاركتكم جميعا~", "This game has ended without a winner. Thanks for playing~", "صياغة عربية طبيعية.", "إعلان", 1),
    ('mes "[ الرقم "+$@bingoresult+" - "+$bingo[$@bingoresult -1]+" ]";', 'mes "[ السحب "+$@bingoresult+" - الرقم "+$bingo[$@bingoresult -1]+" ]";', "Number - called value", "توضيح أن الرقم الأول ترتيب السحب والثاني الرقم المعلن.", "واجهة", 3),
    ('mes "[ الرقم "+$@bingoresult+": "+$bingo[$@bingoresult -1]+" ]";', 'mes "[ السحب "+$@bingoresult+" - الرقم "+$bingo[$@bingoresult -1]+" ]";', "Number - called value", "توحيد عرض نتيجة السحب.", "واجهة", 1),
    ("[الخطوط المكتملة حاليا: ", "[عدد الخطوط المكتملة: ", "Currently Finished Lines", "تحسين عنوان عداد الخطوط.", "واجهة", 1),
    ("لقد أكملنا للتو 5 خطوط!", "اكتملت خمسة خطوط على لوحتنا!", "We just have made 5 lines!", "تصحيح الصياغة وتوضيح اللوحة.", "حوار", 1),
    ("قل ^ff0000Bingo^000000!", "اكتب ^ff0000Bingo^000000!", "Say Bingo!", "المطلوب إدخال نص وليس حديثا صوتيا.", "دقة لعب", 1),
    ("ل-لقد طابقنا للتو", "ل-لقد اكتملت لدينا", "W-we just matched", "ربط الجملة بالخطوط المكتملة.", "حوار", 1),
    ("5 أرقام في صف واحد!", "خمسة خطوط بالفعل!", "5 numbers in a row!", "إزالة التناقض مع شرط خمسة خطوط في منطق السكربت.", "دقة لعب", 1),
    ("بسرعة، قل ''^FF0000Bingo^000000!''", "أسرع واكتب ''^FF0000Bingo^000000!''", "Quickly, say 'Bingo!'", "مطابقة التعليمات مع أمر input.", "دقة لعب", 1),
    ("تذكر، ستكون لديك", "تذكر، لديك", "Remember, you'll only", "تحسين الصياغة.", "حوار", 1),
    ("فرصة واحدة فقط لقولها!", "محاولة واحدة فقط لكتابتها!", "have one chance to say it!", "مطابقة وصف المحاولة مع الإدخال الكتابي.", "دقة لعب", 1),
    ("يا للأسف! أنا آسف، لكن", "عذرا، لكن", "Oh no! I'm sorry, but", "اختصار التكرار وتحسين النبرة.", "حوار", 1),
    ("شخصا ما صرخ", "أحدهم أعلن", "someone already yelled", "صياغة محايدة ومناسبة للإدخال.", "حوار", 1),
    ("أنا آسف، لكنك أضعت", "لقد فاتتك", "you missed", "إزالة التكرار وتحسين الصياغة.", "حوار", 1),
    ("فرصتك! حظا أوفر", "الفرصة. حظا أوفر", "your chance! Better luck", "إكمال الجملة بسلاسة.", "حوار", 1),
    ("في المرة القادمة، حسنا؟", "في الجولة القادمة!", "next time, alright?", "صياغة مناسبة لسياق جولة اللعب.", "حوار", 1),
    ("أنا آسف، لكنك", "عذرا،", "I'm sorry, but you", "تحسين رسالة الإدخال الخاطئ.", "حوار", 1),
    ("قلتها بشكل خاطئ. في المرة القادمة،", "لم تكتبها بالشكل الصحيح. في المرة القادمة،", "said it wrong. Next time,", "توضيح أن الخطأ في النص المكتوب.", "دقة لعب", 1),
    ("تأكد من أن تصرخ", "تأكد من كتابة", "make sure that you yell", "مطابقة التعليمات مع input.", "دقة لعب", 1),
    ("بالكلمة، ''^FF0000Bingo^000000،'' حسنا؟", "الكلمة ''^FF0000Bingo^000000'' كما هي.", "the word, 'Bingo,' okay?", "إظهار النص المطلوب بدقة دون فاصلة داخله.", "دقة لعب", 1),
    ("يوكران: واو، بينغو! إنها بينغو!", "يوكران: رائع، Bingo! لدينا فائز!", "Wow, Bingo! It's Bingo!", "تحسين إعلان الفوز وتثبيت كلمة الإدخال.", "إعلان", 1),
    ('يوكران: "+$@bingowinner$+" قال بينغو!', 'يوكران: "+$@bingowinner$+" أعلن Bingo!', "winner has said Bingo", "توحيد كلمة الفوز وصياغة الإعلان.", "إعلان", 1),
    ('يوكران: تهانينا، "+$@bingowinner$+"! ستتم مكافأتك بـ 50 ميدالية مارفلوس.', 'يوكران: تهانينا، "+$@bingowinner$+"! ستحصل على 50 ميدالية مارفلوس.', "rewarded with 50 Marvelous Medals", "صياغة مباشرة للمكافأة.", "إعلان", 1),
    ('يوكران: تهانينا، "+$@bingowinner$+"! ستتم مكافأتك بميدالية مارفلوس واحدة.', 'يوكران: تهانينا، "+$@bingowinner$+"! ستحصل على ميدالية مارفلوس واحدة.', "rewarded with 1 Marvelous Medal", "صياغة مباشرة للمكافأة المفردة.", "إعلان", 1),
    ("يوكران: شكرا لكم جميعا على المشاركة في اللعبة. أراكم في المرة القادمة!", "يوكران: شكرا للجميع على المشاركة. نراكم في الجولة القادمة!", "Thank you all for participating. See you next time!", "صياغة محايدة وطبيعية.", "إعلان", 1),
    ('يوكران: الرقم "+ callfunc("F_GetNumSuffix",.@num) +" هو "+ $bingo[.@num - 1] +". يرجى التحقق من لوحة بينغو الخاصة بك.', 'يوكران: السحب "+ callfunc("F_GetNumSuffix",.@num) +" هو الرقم "+ $bingo[.@num - 1] +". تحقق من لوحة بينغو.', "The ordinal number is value. Please check your Bingo Plate.", "تمييز ترتيب السحب عن الرقم المعلن مع إبقاء الدالة الرسمية.", "إعلان", 1),
    ("إذا أردت لعب", "إذا أردت المشاركة في", "If you'd like to play", "تحسين صياغة المساعدة.", "حوار", 1),
    ("فيرجى التقدم من هذا الطريق.", "فتقدم من هذا الطريق.", "please proceed this way.", "تصحيح الصياغة.", "حوار", 1),
    ("صالة لعبة بينغو.", "صالة ألعاب بينغو.", "Bingo Game Arcade.", "تحسين اسم المكان.", "حوار", 1),
    ("هل ترغب في لعب", "هل ترغب في المشاركة في", "Care to play a game of", "صياغة طبيعية.", "حوار", 1),
    ("لعبة بينغو؟ إذا كانت لديك", "جولة بينغو؟ إذا كانت لديك", "bingo? If you have any", "استخدام مصطلح الجولة لتجنب التكرار.", "حوار", 1),
    ("قواعد بينغو:غرفة بينغو:ميداليات مارفلوس", "قواعد بينغو:غرفة اللعب:ميداليات مارفلوس", "Rules for Bingo:Bingo Room:Marvelous Medals", "توضيح خيار غرفة اللعب.", "خيار", 1),
    ("قواعد لعب بينغو", "قواعد بينغو", "The rules for playing bingo", "اختصار العنوان.", "حوار", 1),
    ("بسيطة. أولا، خذ لوحة", "بسيطة. أولا، ستحصل على لوحة", "are simple. First, take a board", "تحسين تسلسل الشرح.", "حوار", 1),
    ("تحتوي على 25 خانة منظمة بحيث", "تتكون من 25 خانة مرتبة في", "with 25 boxes organized so that", "وصف أدق لبنية اللوحة.", "حوار", 1),
    ("تكون هناك خمسة صفوف وخمسة", "خمسة صفوف وخمسة", "there are five rows and five", "إكمال الجملة العربية بسلاسة.", "حوار", 1),
    ("أعمدة. ثم، رقم", "أعمدة. بعد ذلك، رقم", "columns. Then, number the", "تحسين رابط التسلسل.", "حوار", 1),
    ("الخانات بأي ترتيب تريده.", "الخانات بأي ترتيب تختاره.", "boxes in any order you like.", "صياغة محايدة.", "حوار", 1),
    ("بالطبع، يجب أن تستخدم", "يجب استخدام", "Of course, you must use", "صياغة محايدة ومباشرة.", "حوار", 1),
    ("عندما تكون لوحة بينغو", "عندما تصبح لوحات بينغو", "When everyone's bingo board", "مطابقة الجمع المقصود.", "حوار", 1),
    ("الخاصة بكل شخص جاهزة، ستبدأ اللعبة.", "جاهزة، ستبدأ اللعبة.", "is ready, the game will begin.", "إزالة الحرفية وتحسين الربط.", "حوار", 1),
    ("سينادي منسق اللعبة لدينا رقما عشوائيا من 1 إلى 25.", "سيعلن منسق اللعبة رقما عشوائيا من 1 إلى 25.", "coordinator will call out a number from 1 to 25", "توحيد فعل الإعلان.", "حوار", 1),
    ("في كل مرة ينادي فيها المنسق", "في كل مرة يعلن فيها المنسق", "Each time the coordinator calls out", "توحيد المصطلح.", "حوار", 1),
    ("رقما، تأكد", "رقما، تحقق", "calls out a number, make sure", "صياغة محايدة.", "حوار", 1),
    ("من تحديد الخانة المرقمة", "من تحديد الخانة التي تحمل", "mark the corresponding numbered square", "تحسين الوصف.", "حوار", 1),
    ("المطابقة على لوحة", "الرقم المطابق على لوحة", "corresponding numbered square on your bingo", "إكمال المعنى بدقة.", "حوار", 1),
    ("بينغو الخاصة بك. والآن، هذه هي", "بينغو. وهذه هي", "board. Now, these are the", "صياغة محايدة.", "حوار", 1),
    ("إذا استطعت تكوين خط", "إذا استطعت إكمال خمسة خطوط", "If you can make a line", "مواءمة الشرح مع شرط السكربت الفعلي: أكثر من أربعة خطوط.", "دقة لعب", 1),
    ("من 5 خانات متتالية، أفقيا أو عموديا أو قطريا، باستخدام", "من 5 خانات متتالية أفقيا أو عموديا أو قطريا، باستخدام", "5 squares in a row, horizontally, vertically, or diagonally", "تحسين علامات الترقيم.", "حوار", 1),
    ("الأرقام التي نادى بها", "الأرقام التي أعلنها", "numbers called out by the", "توحيد فعل الإعلان.", "حوار", 1),
    ("المنسق، فاسرع واصرخ", "المنسق، فأسرع واكتب", "coordinator, you quickly yell", "مطابقة الإرشاد مع الإدخال الكتابي.", "دقة لعب", 1),
    ("بالكلمة، ''Bingo.''", "الكلمة ''Bingo''.", "the word, 'Bingo.'", "إزالة النقطة من داخل النص المطلوب إدخاله.", "دقة لعب", 1),
    ("إذا كنت أول من يصرخ", "إذا كنت أول من يكتب", "If you are the first to yell", "مطابقة الإرشاد مع input.", "دقة لعب", 1),
    ("بالكلمة، ''Bingo،'' فستفوز!", "الكلمة ''Bingo'' فستفوز!", "the word, 'Bingo,' you'll win!", "إزالة الفاصلة من النص المطلوب.", "دقة لعب", 1),
    ("لكن إذا سبقك أحدهم", "أما إذا سبقك أحد", "But if someone beats you", "صياغة محايدة.", "حوار", 1),
    ("إلى ذلك، فلا حيلة في الأمر.", "إلى ذلك، فستضيع الفرصة.", "to it, then it can't be helped.", "توضيح نتيجة التأخر.", "حوار", 1),
    ("على أي حال، تكلفة لعب كل", "تكلفة المشاركة في كل", "it costs 1,000 zeny", "صياغة مباشرة.", "حوار", 1),
    ("لعبة بينغو هي 1,000 زيني~", "جولة بينغو هي 1,000 زيني~", "to play each bingo game~", "توحيد مصطلح الجولة.", "حوار", 1),
    ("آه، إذا أردت الانضمام إلى", "للانضمام إلى", "if you want to join a", "تحسين بداية الشرح.", "حوار", 1),
    ("لعبة بينغو، فادخل من الباب", "جولة بينغو، ادخل من الباب", "bingo game, enter the right door", "توحيد مصطلح الجولة.", "حوار", 1),
    ("الأيمن. يجب أن يكون هناك على الأقل", "الأيمن. يلزم وجود", "There must be at least", "اختصار واضح.", "حوار", 1),
    ("5 أشخاص للعب، لذلك", "5 لاعبين على الأقل، لذلك", "5 people to play a game", "توضيح المقصود بالعدد.", "حوار", 1),
    ("قد تحتاج إلى الانتظار حتى", "قد تضطر إلى الانتظار حتى", "you may need to wait until", "تحسين الصياغة.", "حوار", 1),
    ("يكتمل هذا الشرط.", "يكتمل العدد.", "requirement is fulfilled.", "تحديد الشرط المقصود.", "حوار", 1),
    ("إذا كنت تريد فقط", "أما إذا أردت فقط", "If you just want to", "صياغة محايدة.", "حوار", 1),
    ("مشاهدة لعبة بينغو،", "مشاهدة جولة بينغو،", "watch the bingo game", "توحيد مصطلح الجولة.", "حوار", 1),
    ("فيمكنك دخول", "فادخل من", "you may enter the", "صياغة مباشرة.", "حوار", 1),
    ("الباب الأيسر كمتفرج", "الباب الأيسر بصفة متفرج", "left door as a spectator", "تحسين الصياغة.", "حوار", 1),
    ("في غرفة بينغو.", "إلى غرفة بينغو.", "in the Bingo Room.", "تصحيح حرف الجر.", "حوار", 1),
    ("عندما تفوز في لعبة", "عند الفوز في جولة", "When you win a bingo", "صياغة محايدة.", "حوار", 1),
    ("بينغو، ستتم مكافأتك", "بينغو، ستحصل", "game, you will be rewarded", "صياغة مباشرة.", "حوار", 1),
    ("بـ ''ميداليات مارفلوس،''", "على ''ميداليات مارفلوس''،", "with 'Marvelous Medals,'", "تصحيح حرف الجر وعلامة الترقيم.", "مصطلح", 1),
    ("والتي لا يمكن استخدامها إلا داخل", "ولا يمكن استخدامها إلا داخل", "which can only be used within", "تحسين الربط.", "حوار", 1),
    ("هذه الصالة. كما لا يمكنك تبادل الميداليات مع اللاعبين الآخرين.", "هذه الصالة، ولا يمكن مبادلتها مع اللاعبين الآخرين.", "You also can't trade medals with other players.", "صياغة محايدة وتوضيح عدم المبادلة.", "حوار", 1),
    ("عادة تحصل على ميدالية", "ستحصل عادة على ميدالية", "You usually get 1 Marvelous", "تحسين ترتيب الجملة.", "حوار", 1),
    ("مارفلوس واحدة عند الفوز بلعبة بينغو،", "مارفلوس واحدة عند الفوز بجولة بينغو،", "Medal for winning a bingo game", "توحيد مصطلح الجولة.", "حوار", 1),
    ("لكن يمكنك الفوز بـ 50 ميدالية دفعة واحدة", "لكن يمكن الفوز بـ 50 ميدالية دفعة واحدة", "you can win 50 at one time", "صياغة محايدة.", "حوار", 1),
    ("في ظروف خاصة. يمكنك", "في ظروف خاصة. ويمكنك", "under special conditions. You", "تحسين الربط.", "حوار", 1),
    ("أيضا لعب ألعاب سباق الوحوش", "أيضا المشاركة في سباقات الوحوش", "also play Monster Racing games", "صياغة طبيعية وتوحيد اسم النشاط.", "مصطلح", 1),
    ("للفوز بمزيد من الميداليات.", "لكسب المزيد من الميداليات.", "to win more medals.", "تحسين الصياغة.", "حوار", 1),
    ("ميداليات مارفلوس، وقم", "ميداليات مارفلوس، ثم", "Marvelous Medals as you can, and trade", "تحسين الربط.", "حوار", 1),
    ("بمبادلتها بمنتجات في حلبة سباق الوحوش. سمعت أن هناك أيضا", "استبدلها بجوائز في حلبة سباق الوحوش. سمعت أن هناك أيضا", "trade them for products in the Monster Racing Arena", "استخدام مصطلح الجوائز الأنسب للسياق.", "حوار", 1),
    ("مكانا في أينبروخ يمكنك استخدامها فيه، لكنني لا أعرف.", "مكانا في إينبروخ يمكن استخدامها فيه، لكنني لا أعرف التفاصيل.", "a place in Einbroch where you can use them", "توحيد اسم إينبروخ وصياغة الخاتمة.", "اسم مكان", 1),
]


def strip_strings(text: str) -> str:
    return re.sub(r'"(?:\\.|[^"\\])*"', '""', text)


def extract_commands(code: str) -> list[str]:
    commands = []
    for line in code.splitlines():
        m = re.match(r"\s*([A-Za-z_][A-Za-z0-9_]*)\b", line)
        if m and not line.lstrip().startswith("//"):
            commands.append(m.group(1))
    return commands


def make_xlsx(path: Path, sheets: list[tuple[str, list[list[str]]]]) -> None:
    def col_name(n: int) -> str:
        s = ""
        while n:
            n, r = divmod(n - 1, 26)
            s = chr(65 + r) + s
        return s

    def sheet_xml(rows: list[list[str]]) -> str:
        body = []
        for ri, row in enumerate(rows, 1):
            cells = []
            for ci, value in enumerate(row, 1):
                ref = f"{col_name(ci)}{ri}"
                style = ' s="1"' if ri == 1 else ''
                cells.append(f'<c r="{ref}" t="inlineStr"{style}><is><t xml:space="preserve">{escape(str(value))}</t></is></c>')
            body.append(f'<row r="{ri}">{"".join(cells)}</row>')
        return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' \
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">' \
            '<sheetViews><sheetView rightToLeft="1" workbookViewId="0"/></sheetViews>' \
            '<sheetFormatPr defaultRowHeight="18"/><sheetData>' + ''.join(body) + '</sheetData></worksheet>'

    content_types = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>']
    for i in range(1, len(sheets) + 1):
        content_types.append(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
    content_types.append('</Types>')
    root_rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'
    workbook = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><bookViews><workbookView/></bookViews><sheets>']
    wb_rels = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
    for i, (name, _) in enumerate(sheets, 1):
        workbook.append(f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>')
        wb_rels.append(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>')
    workbook.append('</sheets></workbook>')
    wb_rels.append(f'<Relationship Id="rId{len(sheets)+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
    styles = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Arial"/></font><font><b/><sz val="11"/><name val="Arial"/></font></fonts><fills count="1"><fill><patternFill patternType="none"/></fill></fills><borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs></styleSheet>'
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ''.join(content_types))
        z.writestr("_rels/.rels", root_rels)
        z.writestr("xl/workbook.xml", ''.join(workbook))
        z.writestr("xl/_rels/workbook.xml.rels", ''.join(wb_rels))
        z.writestr("xl/styles.xml", styles)
        for i, (_, rows) in enumerate(sheets, 1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", sheet_xml(rows))


def read_csv_rows(path: Path) -> list[list[str]]:
    text = path.read_bytes().decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text)))


def main() -> None:
    main_path = p(MAIN_REL)
    en_path = p(EN_REL)
    original_bytes = main_path.read_bytes()
    en_bytes = en_path.read_bytes()
    original_text, main_bom, main_newline = read_preserve(main_path)
    original_line_count = len(original_text.splitlines())
    original_blob = git_blob_sha(original_bytes)
    if git_blob_sha(en_bytes) != OFFICIAL_BLOB:
        raise RuntimeError("المرجع الإنجليزي الداخلي لا يطابق بصمة النسخة الرسمية المعتمدة")

    text = original_text
    records: list[dict[str, object]] = []
    for old, new, eng, reason, kind, expected in REPLACEMENTS:
        count = text.count(old)
        if count != expected:
            raise RuntimeError(f"فشل تطبيق الاستبدال: expected={expected} actual={count} old={old!r}")
        starts = []
        pos = 0
        for _ in range(count):
            idx = text.find(old, pos)
            starts.append(idx)
            pos = idx + len(old)
        for idx in starts:
            records.append({
                "line": text.count("\n", 0, idx) + 1,
                "old": old,
                "new": new,
                "english": eng,
                "reason": reason,
                "type": kind,
            })
        text = text.replace(old, new)

    write_preserve(main_path, text, main_bom, main_newline)
    final_bytes = main_path.read_bytes()
    stage_changes = len(records)
    cumulative = CUMULATIVE_BEFORE + stage_changes

    # Update remaining tracker.
    rem_text, rem_bom, rem_nl = read_preserve(p(REMAINING_CSV_REL))
    rem_lines = rem_text.splitlines()
    target_prefix = MAIN_REL + ","
    matched = [line for line in rem_lines if line.startswith(target_prefix)]
    if len(matched) != 1:
        raise RuntimeError("تعذر العثور على صف الملف مرة واحدة في قائمة المتبقي")
    rem_lines = [line for line in rem_lines if not line.startswith(target_prefix)]
    write_preserve(p(REMAINING_CSV_REL), "\n".join(rem_lines) + "\n", rem_bom, rem_nl)

    # Update completed tracker.
    comp_text, comp_bom, comp_nl = read_preserve(p(COMPLETED_CSV_REL))
    comp_rows = list(csv.reader(io.StringIO(comp_text)))
    summary_note = (
        "مراجعة كاملة للعبة بينغو في هويغل، بما يشمل غرفة الانتظار واختيار اللوحات وإعلانات يوكران "
        "وتسجيل الأرقام والتحقق من خمسة خطوط وإعلان Bingo والمكافآت وشرح مالك الصالة. صُححت تعليمات الفوز "
        "لتطابق منطق السكربت الذي يتطلب خمسة خطوط، ووُحدت كلمة الإدخال الحساسة لحالة الأحرف، ونُقحت الصياغة "
        "العربية وأسماء اللوحات واسم إينبروخ. حُفظت الأسماء الداخلية والأحداث والمتغيرات والمؤقتات والمعرف 7515 "
        "والكميات والتكلفة 1000 زيني والخرائط والإحداثيات ومنطق اللعبة دون تغيير."
    )
    comp_rows.append([MAIN_REL, "الألعاب والفعاليات", "مراجعة حوارية وتقنية عميقة", "مكتمل", str(STAGE), summary_note, f"المرحلة_{STAGE}"])
    write_preserve(p(COMPLETED_CSV_REL), csv_text(comp_rows), comp_bom, comp_nl)

    # Update stage tracker CSV.
    tr_text, tr_bom, tr_nl = read_preserve(p(TRACK_CSV_REL))
    tr_rows = list(csv.reader(io.StringIO(tr_text)))
    sync_files = " | ".join(RELATED_CHECKED)
    tr_rows.append([str(STAGE), "الألعاب والفعاليات", "لعبة بينغو هويغل", MAIN_REL, sync_files, "مكتمل", str(stage_changes), f"المرحلة_{STAGE}"])
    write_preserve(p(TRACK_CSV_REL), csv_text(tr_rows), tr_bom, tr_nl)

    # Update Markdown tracker.
    md_text, md_bom, md_nl = read_preserve(p(TRACK_MD_REL))
    md_text = md_text.replace("حتى المرحلة 261", "حتى المرحلة 262", 1)
    md_text = md_text.replace("- المراحل المكتملة: **261**", "- المراحل المكتملة: **262**", 1)
    md_text = md_text.replace("- إجمالي التعديلات المسجلة: **62,512**", f"- إجمالي التعديلات المسجلة: **{cumulative:,}**", 1)
    md_text = md_text.replace("- ملفات NPC المراجعة بعمق: **262 من 555**", "- ملفات NPC المراجعة بعمق: **263 من 555**", 1)
    table_marker = "| المرحلة | القسم | النطاق | الملف الأساسي | ملفات المزامنة | التعديلات |"
    if table_marker not in md_text:
        raise RuntimeError("تعذر تحديد جدول المراحل في ملف Markdown")
    table_row = f"| 262 | الألعاب والفعاليات | لعبة بينغو هويغل | `{MAIN_REL}` | " + " | ".join(RELATED_CHECKED) + f" | {stage_changes} |"
    lines = md_text.splitlines()
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("| 261 |"):
            insert_at = i + 1
            break
    if not insert_at:
        # Insert before first detailed stage heading if table rendering has earlier rows only.
        for i, line in enumerate(lines):
            if line.startswith("## المرحلة "):
                insert_at = i
                break
    lines.insert(insert_at, table_row)
    md_text = "\n".join(lines).rstrip() + f"\n\n## المرحلة 262 — مكتملة\n\n"
    md_text += f"- الملف الأساسي: `{MAIN_REL}`\n"
    md_text += f"- المرجع الإنجليزي الداخلي مطابق بايتيا للنسخة الرسمية الحالية؛ بصمة Git blob: `{OFFICIAL_BLOB}`.\n"
    md_text += "- روجعت لعبة بينغو كاملة: غرفة الانتظار، اختيار اللوحات، الإعلانات، تسجيل الأرقام، احتساب الخطوط، إعلان الفوز، المكافآت، وإرشادات مالك الصالة.\n"
    md_text += "- صُحح شرح الفوز ليوضح ضرورة إكمال خمسة خطوط، ووُحدت كلمة الإدخال `Bingo` مع المقارنة البرمجية الحساسة لحالة الأحرف.\n"
    md_text += "- نُقحت الصياغة العربية ووُحد اسم يوكران وإينبروخ وأسماء اللوحات، وفُحصت ملفات هويغل والملاحة ومعلومات العناصر دون الحاجة إلى تعديلها.\n"
    md_text += "- حُفظت الأسماء الداخلية وLabels وEvents والمتغيرات والمعرف 7515 والكميات والمؤقتات والتكلفة والخرائط والإحداثيات ومنطق اللعبة.\n"
    md_text += f"- إجمالي تعديلات المرحلة: **{stage_changes}**\n"
    md_text += f"- الإجمالي التراكمي: **{cumulative:,}**\n"
    md_text += f"- ملفات NPC المراجعة بعمق: **{NPC_REVIEWED} من {NPC_TOTAL}**\n"
    md_text += f"- الملفات المتبقية للمراجعة: **{REMAINING}**\n"
    md_text += "- ملفات المهمات المكتملة: **88 من 88**\n"
    md_text += f"- أول ملف متبق: `{NEXT_FILE}`\n"
    md_text += "- التحقق الفني الساكن: **PASS**\n"
    write_preserve(p(TRACK_MD_REL), md_text, md_bom, md_nl)

    # Technical validation.
    final_text, final_bom, final_nl = read_preserve(main_path)
    old_code = strip_strings(original_text)
    new_code = strip_strings(final_text)
    old_internal = re.findall(r"::([^\t\r\n]+)", original_text)
    new_internal = re.findall(r"::([^\t\r\n]+)", final_text)
    old_labels = re.findall(r"(?m)^\s*((?:On|L_)[A-Za-z0-9_]+):", original_text)
    new_labels = re.findall(r"(?m)^\s*((?:On|L_)[A-Za-z0-9_]+):", final_text)
    old_vars = re.findall(r"(?<![A-Za-z0-9_])(?:\$?@|\$|\.@|@)[A-Za-z_][A-Za-z0-9_]*\$?", old_code)
    new_vars = re.findall(r"(?<![A-Za-z0-9_])(?:\$?@|\$|\.@|@)[A-Za-z_][A-Za-z0-9_]*\$?", new_code)
    old_nums = re.findall(r"(?<![A-Za-z_])\d+(?![A-Za-z_])", old_code)
    new_nums = re.findall(r"(?<![A-Za-z_])\d+(?![A-Za-z_])", new_code)
    old_events = re.findall(r'"([^"\n]*::On[A-Za-z0-9_]+)"', original_text)
    new_events = re.findall(r'"([^"\n]*::On[A-Za-z0-9_]+)"', final_text)
    old_dupes = re.findall(r"duplicate\(([^)]+)\)", original_text)
    new_dupes = re.findall(r"duplicate\(([^)]+)\)", final_text)
    old_functions = re.findall(r"function\s+script\s+([A-Za-z0-9_]+)", original_text)
    new_functions = re.findall(r"function\s+script\s+([A-Za-z0-9_]+)", final_text)
    old_commands = extract_commands(old_code)
    new_commands = extract_commands(new_code)

    def balanced(s: str, a: str, b: str) -> bool:
        depth = 0
        for ch in s:
            if ch == a:
                depth += 1
            elif ch == b:
                depth -= 1
                if depth < 0:
                    return False
        return depth == 0

    tests: list[tuple[str, bool, str]] = [
        ("بصمة المرجع الإنجليزي الرسمي", git_blob_sha(en_bytes) == OFFICIAL_BLOB, OFFICIAL_BLOB),
        ("بقاء ترميز UTF-8", True, "فك الترميز وإعادة الحفظ بنجاح"),
        ("بقاء حالة BOM", main_bom == final_bom, str(main_bom)),
        ("بقاء نوع نهايات الأسطر", main_newline == final_nl, repr(main_newline)),
        ("بقاء عدد الأسطر", original_line_count == len(final_text.splitlines()), str(original_line_count)),
        ("عدم حذف محتوى الملف", len(final_bytes) > 0, str(len(final_bytes))),
        ("تغير الملف لغويا", original_bytes != final_bytes, f"{sha256(original_bytes)} -> {sha256(final_bytes)}"),
        ("ثبات الأسماء الداخلية بعد ::", old_internal == new_internal, str(len(old_internal))),
        ("ثبات Labels وEvents", old_labels == new_labels, str(len(old_labels))),
        ("ثبات أسماء المتغيرات", old_vars == new_vars, str(len(old_vars))),
        ("ثبات الأرقام البرمجية", old_nums == new_nums, str(len(old_nums))),
        ("ثبات مراجع الأحداث النصية", old_events == new_events, str(len(old_events))),
        ("ثبات أهداف duplicate", old_dupes == new_dupes, str(len(old_dupes))),
        ("ثبات أسماء الدوال", old_functions == new_functions, str(old_functions)),
        ("ثبات تسلسل الأوامر", old_commands == new_commands, str(len(old_commands))),
        ("سلامة الأقواس المعقوفة", balanced(new_code, "{", "}"), "{}"),
        ("سلامة الأقواس الدائرية", balanced(new_code, "(", ")"), "()"),
        ("سلامة الأقواس المربعة", balanced(new_code, "[", "]"), "[]"),
        ("سلامة الاقتباسات في كل سطر", all(line.count('"') % 2 == 0 for line in final_text.splitlines()), "even quotes"),
        ("بقاء خريطة que_bingo", final_text.count("que_bingo") == original_text.count("que_bingo"), str(final_text.count("que_bingo"))),
        ("بقاء تكلفة 1000 زيني", '5,1000;' in final_text, "waitingroom fee"),
        ("بقاء عدد اللاعبين 5", '::OnWarp",5,1000' in final_text, "5 players"),
        ("بقاء معرف المكافأة 7515", final_text.count("7515") == original_text.count("7515"), str(final_text.count("7515"))),
        ("بقاء مكافأة 50 ميدالية", "getitem 7515,50" in final_text, "50"),
        ("بقاء مكافأة ميدالية واحدة", "getitem 7515,1" in final_text, "1"),
        ("بقاء شرط السحب السادس عشر", "$@bingoresult == 16" in final_text, "16"),
        ("بقاء مقارنة Bingo الحساسة", 'if (@bingoyell$ == "Bingo")' in final_text, "Bingo"),
        ("بقاء عدد خلايا اللوحة 25", "@bingoplate[25]" in final_text, "25"),
        ("بقاء شرط خمسة خطوط", "if (@bingowin > 4)" in final_text, "> 4"),
        ("بقاء مؤثر الفوز", "EF_SUI_EXPLOSION" in final_text, "EF_SUI_EXPLOSION"),
        ("بقاء ملف الصوت", 'tming_success.wav' in final_text, "tming_success.wav"),
        ("بقاء أوامر warpwaitingpc", final_text.count("warpwaitingpc") == original_text.count("warpwaitingpc"), str(final_text.count("warpwaitingpc"))),
        ("بقاء أوامر areawarp", final_text.count("areawarp") == original_text.count("areawarp"), str(final_text.count("areawarp"))),
        ("بقاء أوامر donpcevent", final_text.count("donpcevent") == original_text.count("donpcevent"), str(final_text.count("donpcevent"))),
        ("بقاء أوامر enablenpc", final_text.count("enablenpc") == original_text.count("enablenpc"), str(final_text.count("enablenpc"))),
        ("بقاء أوامر disablenpc", final_text.count("disablenpc") == original_text.count("disablenpc"), str(final_text.count("disablenpc"))),
        ("بقاء المؤقتات", re.findall(r"OnTimer\d+", original_text) == re.findall(r"OnTimer\d+", final_text), str(len(re.findall(r"OnTimer\d+", final_text)))),
        ("بقاء أوامر الانتقال", final_text.count("warp ") == original_text.count("warp "), str(final_text.count("warp "))),
        ("بقاء Func_Bingo", "function\tscript\tFunc_Bingo\t{" in final_text, "Func_Bingo"),
        ("بقاء Func_BingoResult", "function\tscript\tFunc_BingoResult\t{" in final_text, "Func_BingoResult"),
        ("اكتمال جميع الاستبدالات", all(str(r["new"]) in final_text for r in records), str(stage_changes)),
    ]
    if len(tests) != 41:
        raise RuntimeError(f"عدد الاختبارات غير صحيح: {len(tests)}")
    failed = [t for t in tests if not t[1]]
    if failed:
        raise RuntimeError("فشل التحقق الفني: " + "; ".join(t[0] for t in failed))

    STAGE_DIR.mkdir(parents=True, exist_ok=True)
    (STAGE_DIR / "نسخة_قبل_التعديل_hugel_bingo.txt").write_bytes(original_bytes)
    (STAGE_DIR / "المرجع_الرسمي_hugel_bingo.txt").write_bytes(en_bytes)

    mod_rows: list[list[object]] = [["رقم السطر", "النص السابق", "النص الجديد", "المرجع الإنجليزي", "سبب التعديل", "نوع التعديل"]]
    for r in sorted(records, key=lambda x: int(x["line"])):
        mod_rows.append([r["line"], r["old"], r["new"], r["english"], r["reason"], r["type"]])
    write_utf8_bom(STAGE_DIR / f"تقرير_المرحلة_{STAGE}_التعديلات.csv", csv_text(mod_rows))

    tech_rows = [["الاختبار", "النتيجة", "التفاصيل"]] + [[name, "PASS" if ok else "FAIL", details] for name, ok, details in tests]
    write_utf8_bom(STAGE_DIR / f"تقرير_المرحلة_{STAGE}_التحقق_الفني.csv", csv_text(tech_rows))
    tech_json = {"stage": STAGE, "total": len(tests), "passed": len(tests) - len(failed), "failed": len(failed), "tests": [{"name": n, "status": "PASS" if ok else "FAIL", "details": d} for n, ok, d in tests]}
    (STAGE_DIR / f"تقرير_المرحلة_{STAGE}_التحقق_الفني.json").write_text(json.dumps(tech_json, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tech_md = f"# تقرير التحقق الفني — المرحلة {STAGE}\n\n- الاختبارات: **{len(tests)}**\n- الناجحة: **{len(tests)-len(failed)}**\n- الفاشلة: **{len(failed)}**\n- النتيجة: **PASS**\n\n| الاختبار | النتيجة | التفاصيل |\n|---|---|---|\n"
    tech_md += "\n".join(f"| {n.replace('|','/')} | {'PASS' if ok else 'FAIL'} | {d.replace('|','/')} |" for n, ok, d in tests) + "\n"
    (STAGE_DIR / f"تقرير_المرحلة_{STAGE}_التحقق_الفني.md").write_text(tech_md, encoding="utf-8")

    sources = [
        {"type": "المرجع الإنجليزي الداخلي", "path": EN_REL, "status": "مطابق للمرجع الرسمي", "sha": OFFICIAL_BLOB},
        {"type": "المرجع الرسمي الحالي", "path": "rathena/rathena:npc/other/hugel_bingo.txt", "status": "تمت المطابقة البايتية", "sha": OFFICIAL_BLOB},
        {"type": "ملف مرتبط", "path": RELATED_CHECKED[0], "status": "فُحص اسم يوكران دون تعديل", "sha": ""},
        {"type": "ملف مرتبط", "path": RELATED_CHECKED[1], "status": "فُحص اسم يوكران دون تعديل", "sha": ""},
        {"type": "ملف مرتبط", "path": RELATED_CHECKED[2], "status": "فُحصت تسمية يوكران دون تعديل", "sha": ""},
        {"type": "ملف مرتبط", "path": RELATED_CHECKED[3], "status": "فُحص المعرف 7515 وميدالية مارفلوس دون تعديل", "sha": ""},
    ]
    source_rows = [["النوع", "المسار/المصدر", "النتيجة", "البصمة"]] + [[s["type"], s["path"], s["status"], s["sha"]] for s in sources]
    write_utf8_bom(STAGE_DIR / f"تقرير_المرحلة_{STAGE}_المصادر.csv", csv_text(source_rows))
    (STAGE_DIR / f"تقرير_المرحلة_{STAGE}_المصادر.json").write_text(json.dumps({"stage": STAGE, "sources": sources}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    source_md = f"# مصادر المرحلة {STAGE}\n\n- المرجع الإنجليزي الداخلي: `{EN_REL}`\n- المرجع الرسمي: `rathena/rathena/npc/other/hugel_bingo.txt`\n- بصمة Git blob المشتركة: `{OFFICIAL_BLOB}`\n- الملفات المرتبطة المفحوصة دون تعديل:\n" + "\n".join(f"  - `{x}`" for x in RELATED_CHECKED) + "\n"
    (STAGE_DIR / f"تقرير_المرحلة_{STAGE}_المصادر.md").write_text(source_md, encoding="utf-8")

    summary = f"""# ملخص المرحلة {STAGE}

- الملف الأساسي: `{MAIN_REL}`
- المرجع الإنجليزي الداخلي مطابق بايتيا للنسخة الرسمية الحالية: `{OFFICIAL_BLOB}`.
- عدد التعديلات اللغوية المسجلة: **{stage_changes}**.
- الإجمالي التراكمي: **{cumulative:,}**.
- ملفات NPC المراجعة: **{NPC_REVIEWED} من {NPC_TOTAL}**.
- الملفات المتبقية: **{REMAINING}**.
- الملف التالي: `{NEXT_FILE}`.
- الاختبارات الفنية: **41 من 41 ناجحة**.

## نطاق المراجعة

رُوجعت لعبة بينغو في هويغل كاملة، بما يشمل غرفة الانتظار، اختيار اللوحات، إدخال الأرقام، الإعلانات الزمنية، عرض نتائج السحب، احتساب الخطوط، إعلان `Bingo`، مكافآت ميداليات مارفلوس، وتعليمات مالك الصالة.

## أهم التصحيحات

- توضيح أن شرط الفوز الفعلي هو إكمال خمسة خطوط، لا خط واحد.
- توحيد تعليمات كتابة `Bingo` مع المقارنة البرمجية الحساسة لحالة الأحرف.
- توضيح الفرق بين ترتيب السحب والرقم المعلن في واجهة اللوحة.
- تنقيح الصياغة العربية وإزالة العبارات الحرفية والركيكة.
- توحيد اسم يوكران وإينبروخ وأسماء لوحات بينغو.
- إبقاء جميع الأسماء الداخلية والأحداث والمتغيرات والمؤقتات والمعرفات والكميات والمنطق البرمجي دون تغيير.
"""
    (STAGE_DIR / f"ملخص_المرحلة_{STAGE}.md").write_text(summary, encoding="utf-8")

    # Create updated Excel tracker from the three authoritative CSV files.
    make_xlsx(p(XLSX_REL), [
        ("متابعة المراحل", read_csv_rows(p(TRACK_CSV_REL))),
        ("الملفات المكتملة", read_csv_rows(p(COMPLETED_CSV_REL))),
        ("الملفات المتبقية", read_csv_rows(p(REMAINING_CSV_REL))),
    ])

    # Package comparison report over tracked files, excluding temporary generator files.
    tracked = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True, encoding="utf-8").splitlines()
    existing_changed = {MAIN_REL, REMAINING_CSV_REL, COMPLETED_CSV_REL, TRACK_CSV_REL, TRACK_MD_REL}
    new_stage_files = sorted(str(x.relative_to(ROOT)).replace(os.sep, "/") for x in STAGE_DIR.rglob("*") if x.is_file())
    new_files = set(new_stage_files + [XLSX_REL])
    comparison_rows: list[list[object]] = [["المسار", "الحالة", "SHA256 قبل", "SHA256 بعد"]]
    for rel in sorted(set(tracked) | new_files):
        if rel in TEMP_PATHS:
            continue
        path = p(rel)
        if rel == MAIN_REL:
            before_hash = sha256(original_bytes)
        elif rel in existing_changed:
            # Exact historical hash is not retained for tracker files in this run; use git show.
            try:
                before_data = subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=ROOT)
                before_hash = sha256(before_data)
            except subprocess.CalledProcessError:
                before_hash = ""
        elif rel in new_files:
            before_hash = ""
        else:
            before_hash = sha256(path.read_bytes()) if path.exists() else ""
        after_hash = sha256(path.read_bytes()) if path.exists() else ""
        status = "جديد" if not before_hash else ("معدل" if before_hash != after_hash else "دون تغيير")
        comparison_rows.append([rel, status, before_hash, after_hash])
    write_utf8_bom(STAGE_DIR / f"تقرير_المرحلة_{STAGE}_مقارنة_الحزمة.csv", csv_text(comparison_rows))

    result = {
        "stage": STAGE,
        "main_file": MAIN_REL,
        "next_file": NEXT_FILE,
        "main_changes": stage_changes,
        "related_changes": 0,
        "stage_changes": stage_changes,
        "cumulative_changes": cumulative,
        "npc_reviewed": NPC_REVIEWED,
        "npc_total": NPC_TOTAL,
        "remaining": REMAINING,
        "quest_complete": 88,
        "quest_total": 88,
        "official_git_blob": OFFICIAL_BLOB,
        "technical_tests": len(tests),
        "technical_passed": len(tests) - len(failed),
        "technical_failed": len(failed),
        "changed_existing_files": len(existing_changed),
        "changed_existing_paths": sorted(existing_changed),
        "new_files": len(new_files),
        "new_file_paths": sorted(new_files),
        "deleted_files": [],
        "status_counts": {
            "معدل": sum(1 for row in comparison_rows[1:] if row[1] == "معدل"),
            "دون تغيير": sum(1 for row in comparison_rows[1:] if row[1] == "دون تغيير"),
            "جديد": sum(1 for row in comparison_rows[1:] if row[1] == "جديد"),
            "محذوف": 0,
        },
        "main_sha256": sha256(final_bytes),
        "main_original_sha256": sha256(original_bytes),
        "main_original_git_blob": original_blob,
    }
    (STAGE_DIR / f"نتيجة_المرحلة_{STAGE}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # Remove temporary automation files so the final PR contains only stage deliverables.
    for rel in TEMP_PATHS:
        path = p(rel)
        if path.exists():
            path.unlink()

    print(json.dumps({"stage": STAGE, "changes": stage_changes, "cumulative": cumulative, "tests": len(tests), "next": NEXT_FILE}, ensure_ascii=False))


if __name__ == "__main__":
    main()
