# سير العمل مع GitHub والذكاء الاصطناعي

## نقطة البداية

دورة المراجعة الثانية تبدأ من المرحلة 1:

- `rathena-master/npc/cities/izlude.txt`
- `rathena-master/npc/cities/prontera.txt`

## دورة كل مرحلة

1. حدّث `main` محليًا.
2. أنشئ فرعًا باسم واضح، مثل `ai/cycle-2-stage-001-prontera-izlude`.
3. اقرأ الملفات الإلزامية المذكورة في `AGENTS.md`.
4. قارن الملف العربي بالمرجع الإنجليزي حسب البنية والسياق لا حسب أرقام الأسطر.
5. افحص الأنظمة المرتبطة وفق `docs/SYNC_SCOPE.md`.
6. ابحث في المصادر الرسمية والموثوقة عند الحاجة ووثق النتيجة.
7. حدّث القاموس أو سجل أن تحديثه غير مطلوب.
8. شغّل:

```bash
python tools/validate_repository.py
python tools/validate_terminology_policy.py
python tools/validate_translation_content.py --base origin/main
```

9. راجع `git diff` وخاصة الأوامر والمعرفات والترميز.
10. افتح Pull Request واكمل قالب المراجعة.
11. انتظر نجاح Workflow باسم `Repository QA`.
12. فسّر أي تحذير بنيوي قبل الدمج.
13. ادمج ثم احذف فرع المرحلة.

## الاستيراد الأول

لا تبدأ المرحلة 1 من مستودع لا يحتوي ملفات اللعبة. شغّل `tools/sync_clean_baseline_windows.bat` من هذه الحزمة أولًا، ثم راجع فرع الاستيراد وادمجه.

## تنبيه الترميز

ملفات CP1256 تعدل محليًا بأداة تقرأ وتكتب بالترميز الأصلي. لا تستخدم محرر GitHub على الويب لهذه الملفات.
