# الحارس الآلي وجودة الترجمة

## الأدوات

- `validate_repository.py`: بنية المستودع والحالة والقاموس ومنع النسخ الاحتياطية وملفات Excel داخل Git.
- `validate_terminology_policy.py`: المصطلحات الثابتة والاختصارات المحمية.
- `validate_translation_content.py`: محتوى ملفات الترجمة المتغيرة.
- `.github/workflows/qa.yml`: يشغّل الأدوات تلقائيًا على كل Pull Request وكل push إلى `main`.

## أخطاء تمنع الدمج

- ترميز غير مدعوم أو ملف تالف.
- خلط نهايات الأسطر داخل الملف.
- تغير الترميز أو BOM أو نمط نهاية السطر عن النسخة السابقة.
- اسم داخلي عربي بعد `::` خارج النصوص الحوارية.
- فقد اختصار محمي في ملف موجود سابقا يجري تعديله، مقارنة بالمرجع الإنجليزي.
- فشل بنية القاموس أو الحالة.
- وجود ZIP أو backup أو XLS/XLSX داخل المستودع.
- نقص ملفات الأساس مع إعلان `baseline_import_complete: true`.

## تحذيرات تحتاج مراجعة بشرية

- تغير مجموعة المراجع الداخلية أو event labels أو أهداف `duplicate()`.
- ظهور صيغة مسجلة في `arabic_aliases` وتحتاج تحققًا سياقيًا؛ بعض الألياس مسموح حسب السياق.

التغير البنيوي قد يكون إصلاحًا رسميًا مقصودًا، لذلك يظهر تحذيرًا افتراضيًا. استخدم `--strict-structure` لجعله خطأً أثناء تدقيق خاص، واشرح أي تغير في Pull Request.

## أوامر محلية

```bash
python tools/validate_repository.py
python tools/validate_terminology_policy.py
python tools/validate_translation_content.py --base origin/main
```

لتدقيق الأساس كاملًا وإظهار قائمة النواقص الحالية كتحذيرات:

```bash
python tools/validate_translation_content.py --all
```

بعد معالجة جميع تحذيرات الاختصارات في دورة المراجعة يمكن تشغيل `--strict-counterparts` كتدقيق مانع.
