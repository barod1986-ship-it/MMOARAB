# دليل الأسلوب والمصطلحات الثابتة

هذا الملف مرجع إلزامي لكل مراجعة وترجمة ومزامنة في مشروع MMOARAB.

## أولوية المراجع

عند وجود تعارض، تكون الأولوية بالترتيب التالي:

1. `glossary/fixed_terms.csv`
2. `glossary/protected_tokens.txt`
3. هذا الدليل `docs/STYLE_GUIDE.md`
4. `glossary/master_glossary.csv`
5. السياق المحلي للملف، بشرط توثيق أي قرار جديد في القاموس

## 1. الاختصارات التي تبقى بالإنجليزية

هذه الاختصارات لا تترجم ولا تعرّب ولا تغيّر حالة أحرفها:

```text
STR   AGI   VIT   INT   DEX   LUK
HP    SP    ATK   MATK  DEF   MDEF
HIT   FLEE  CRIT  ASPD
```

تظل الاختصارات الإنجليزية داخل الجملة العربية:

| إنجليزي | عربي معتمد |
|---|---|
| `Decrease AGI` | `خفض AGI` |
| `Increase AGI` | `زيادة AGI` |
| `Max HP` | `أقصى HP` |
| `ATK +10` | `ATK +10` |

لا تكتب مثلا: القوة بدل `STR`، أو نقاط الحياة بدل `HP`، عندما يكون النص الأصلي يستخدم الاختصار نفسه.

## 2. الوظائف

| إنجليزي | عربي معتمد |
|---|---|
| Novice | مبتدئ |
| High Novice | مبتدئ متقدم |
| Super Novice | مبتدئ خارق |
| Swordsman | سياف |
| Mage | ساحر |
| Wizard | ساحر عظيم |
| High Wizard | ساحر متقدم |
| Acolyte | مريد |
| Priest | كاهن |
| High Priest | كاهن متقدم |
| Monk | راهب |
| Champion | بطل |
| Archer | رامي |
| Hunter | صياد |
| Sniper | قناص |
| Bard | شاعر |
| Clown | مهرج |
| Dancer | راقصة |
| Gypsy | غجرية |
| Merchant | تاجر |
| Blacksmith | حداد |
| Whitesmith | سيد الحدادين |
| Alchemist | خيميائي |
| Creator | مبتكر |
| Thief | لص |
| Rogue | مارق |
| Stalker | متعقب |
| Assassin | مغتال |
| Assassin Cross | سيد المغتالين |
| Knight | فارس |
| Lord Knight | سيد الفرسان |
| Crusader | فارس صليبي |
| Paladin | فارس مقدس |
| Sage | حكيم |
| Professor | أستاذ |
| Soul Linker | رابط الأرواح |
| Gunslinger | رامي مسدسات |
| Ninja | نينجا |
| TaeKwon Kid | فتى التايكون |
| Taekwon Master | سيد التايكون |

## 3. مصطلحات اللعبة العامة

| إنجليزي | عربي معتمد |
|---|---|
| Zeny | زيني |
| Kafra | كافرا |
| Class / Job | الوظيفة |
| Jobs | الوظائف |
| Level | المستوى |
| Base Level | مستوى القاعدة |
| Job Level | مستوى الوظيفة |
| Weight | الوزن |
| Skill | مهارة |
| Item | عنصر |
| Monster | وحش |
| Boss | زعيم |

## 4. أنواع الوحوش

| إنجليزي | عربي معتمد |
|---|---|
| Plant | نباتي |
| Dragon | تنين |
| Undead | غير ميت |
| Demi-Human / Demihuman | شبه بشري |
| Demon | شيطاني |
| Shadow | ظل |
| Angel | ملاك |
| Brute | وحشي |
| Fish | سمكي |
| Insect | حشرة |
| Formless | بلا شكل |

ملاحظة سياقية: `Undead` كنوع وحش يترجم `غير ميت`. في السرد العام يمكن استخدام `الموتى الأحياء` عندما يشير النص إلى جماعة أو كائنات لا إلى تسمية النوع التقنية.

## 5. المهارات والحالات

| إنجليزي | عربي معتمد |
|---|---|
| Turn Undead | طرد الموتى |
| Stun | صعق |
| Blind | عمى |
| Poison | تسمم |
| Frozen | تجمد |
| Divine Protection | الحماية الإلهية |
| Demon Bane | قهر الشياطين |
| Decrease AGI | خفض AGI |
| Increase AGI | زيادة AGI |
| Signum Crucis | علامة الصليب |
| Pneuma | نيوما |
| Ruwach | رواخ |
| Teleport | انتقال |

## 6. تحديث هذا المرجع

- لا تغيّر مصطلحا ثابتا أثناء مرحلة عادية دون توثيق سبب واضح.
- أي تغيير مقترح يحدّث أولا `glossary/fixed_terms.csv` ثم `glossary/master_glossary.csv` والملفات المرتبطة.
- تظل `glossary/protected_tokens.txt` القائمة الآلية للاختصارات الإنجليزية المحمية.
- يجب ذكر أي تعديل على المصطلحات الثابتة بوضوح في Pull Request.
