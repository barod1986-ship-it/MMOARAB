# دليل الأسلوب والمصطلحات الثابتة

هذا الملف مرجع إلزامي لكل مراجعة وترجمة ومزامنة في مشروع MMOARAB.

## أولوية المراجع

1. `glossary/fixed_terms.csv`
2. `glossary/protected_tokens.txt`
3. `docs/STYLE_GUIDE.md`
4. `glossary/master_glossary.csv`
5. السياق المحلي، بشرط توثيق القرار الجديد

## الاختصارات التي تبقى بالإنجليزية

```text
STR   AGI   VIT   INT   DEX   LUK
HP    SP    ATK   MATK  DEF   MDEF
HIT   FLEE  CRIT  ASPD
```

| إنجليزي | عربي معتمد |
|---|---|
| `Decrease AGI` | `خفض AGI` |
| `Increase AGI` | `زيادة AGI` |
| `Max HP` | `أقصى HP` |
| `ATK +10` | `ATK +10` |

لا تستبدل الاختصار بوصف عربي عندما يستخدم النص الأصلي الاختصار نفسه.

## الوظائف

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

## مصطلحات اللعبة العامة

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

## أنواع الوحوش

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

`Undead` كنوع تقني يترجم `غير ميت`. في السرد العام يجوز `الموتى الأحياء` حسب السياق.

## المهارات والحالات

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

## تعديل المصطلحات الثابتة

- لا تغيّر مصطلحًا ثابتًا أثناء مرحلة عادية دون سبب موثق.
- حدّث `fixed_terms.csv` ثم `master_glossary.csv` ثم كل الملفات المرتبطة.
- سجّل التغيير بوضوح في Pull Request.
