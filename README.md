ChatGPT said:
MOMARAB CORE 1.0 — دليل الاستخدام (نسخة شخصية)

ملاحظات مهمة:

استخدام شخصي فقط. مستودع خاص. بلا ملفات اختبار أو بيانات ديمو.

قالب Blocksy مفعّل، وتعطيل Google Fonts دائمًا.

لا خطوط خارجية. لا تتبّع. لا مفاتيح أو خدمات طرف ثالث.

1) معلومات الإضافة

الاسم: MOMARAB CORE

الإصدار: 1.0.0 (SemVer بسيط)

الترخيص: استخدام خاص (Private)

التوافق: WordPress 6.x • PHP 7.4/8.x • Blocksy • Rank Math اختياري

الخصوصية: لا تتبع • لا إرسال بيانات • كوكي محلية للتصويت فقط

الاعتمادات: بلا Webhooks، بلا مفاتيح API، بلا خطوط خارجية

2) الهدف

مكتبة ألعاب MMO عربية مع: فلترة سريعة، صفحة لعبة منظمة، تقييم محرر + ملاحظة، تصويت زوار Like/Dislike، وخبر مرتبط واحد.

وراثة كاملة لألوان وخطوط ومسافات Blocksy.

3) المتطلبات

WordPress 6.x

PHP 7.4 أو 8.x

قالب Blocksy مفعّل

تعطيل Google Fonts في Blocksy وأي منشئ صفحات

4) الكيانات

CPT: game

التصنيفات: النوع، الحالة، أسلوب اللعب، المنصات

السلاجات: إنجليزية ثابتة • الأسماء معروضة بالعربية

5) المصطلحات الافتراضية

game_type: mmorpg • mmo-arpg • mmofps • moba • mmorts • survival-mmo • sandbox-mmo • social-mmo • battle-royale • racing-mmo • sports-mmo • space-mmo • naval-mmo • anime-mmo
game_status: upcoming • alpha • beta • early-access • released
game_mode: pve • pvp • pvpve • open-world • co-op
game_platform: pc • playstation • xbox • nintendo-switch • mobile • browser

زر “إنشاء المصطلحات الأساسية” يضيفها، يتخطى المكرر، ويمكن قفلها لمنع الحذف العرضي.

6) الحقول (Meta)

أساسية: المطوّر، الناشر، تاريخ الإصدار، الموقع الرسمي (https فقط)، المحرك

وسائط: رابطا YouTube كحد أقصى، معرض حتى 6 صور

تقييم المحرر 1–10 بخطوة 0.5: Story • Gameplay • Graphics • Audio

Overall محسوب: Gameplay 40% • Story 25% • Graphics 20% • Audio 15%

ملاحظة تحريرية ≤ 240 حرفًا

روابط اختيارية: Steam • PlayStation • Xbox • Discord

ربط خبر: في المقال العادي حقل لاختيار لعبة واحدة لعرض آخر خبر في صفحة اللعبة

7) أرشيف الألعاب

شريط فلترة أفقي أعلى الشبكة: متعدد لاختيارات النوع/المنصة/الأسلوب + ترتيب بالأحدث/الأقدم/الأعلى تقييمًا/أبجدي

تحديث URL بالباراميترات وحفظ الحالة عند الرجوع

حالة لا نتائج: رسالة ودّية مع اقتراح فلاتر شائعة

بدون قوائم جانبية للفلترة

8) صفحة اللعبة

الترتيب: Hero + عنوان + شارات → معلومات أساسية → وسائط → تقييمات المحرر + الملاحظة → خبر مرتبط واحد → بيانات السكيما

إخفاء قسم الأخبار إذا لا توجد نتائج

صورة بارزة مطلوبة. بديل داخلي عند الغياب

9) التصويت (Like/Dislike)

للزوّار والمستخدمين. صوت واحد لكل لعبة وقابل للتبديل

عرض العدادين ونسبة الرضا = likes / (likes + dislikes)

فرز إضافي في الأرشيف: “الأكثر إعجابًا” = likes − dislikes، كسر تعادل بالـ ratio

لا يدخل في السكيما

مكافحة سبام: 1 فعل/15ث • 30 طلب/دقيقة/IP (10 داخل wp-admin) • لا تخزين IP دائم

10) لوحة التحكم

لوحة رئيسية: KPIs، حالة الكاش (Hits/Misses)، آخر تعديلات، جودة البيانات

إعدادات: Blocksy-only • حدود الوسائط • الكاش الداخلي (تمكين/مدد/مسح) • REST • Schema • التصويت

إدارة المصطلحات: إنشاء/تدقيق، عرض غير المستخدم والمكرر

تقارير التصويت: أعلى 10 ألعاب تفاعلاً (7/30 يوم) + إعادة ضبط العدادات

11) الكاش الداخلي

يُكاشي: نتائج فلترة الأرشيف • الودجات • قوائم التصنيفات • ردود REST الشائعة

TTL افتراضي: أرشيف/REST 10د • ودجات 15د • تصنيفات 60د

تفريغ ذكي عند نشر/تحديث/حذف لعبة أو مصطلح

أزرار مسح: All / Archive / Widgets / Taxonomies / REST

Stampede protection: قفل مؤقت لكل مفتاح + تأخير قصير عند انتهاء TTL

لا تخزين HTML كامل للصفحات (يُترك لـ LiteSpeed)

12) REST API وحدود الاستخدام

/momarab/v1/games و/taxonomies

معاملات: per_page, page, search, type, status, orderby, order

حد per_page الأقصى: 24

معدل الطلبات: 30 طلب/دقيقة/IP (و10/دقيقة داخل wp-admin)

رسائل أخطاء عربية واضحة

13) SEO وSchema

تفعيل Game وAggregateRating وVideoObject عند وجود فيديو

أرشيف مع فلاتر: Canonical لنسخة الأرشيف بلا باراميترات

لا سكيما مزدوجة مع Rank Math؛ عند التعارض تتوقف سكيما الإضافة

rel="prev/next" للترقيم

Breadcrumbs عبر القالب/Rank Math

14) الوصول وRTL

شريط فلترة قابل للتنقّل بالكيبورد • عناصر بوسوم ARIA • نتائج بـ aria-live=polite

تباين ≥ 4.5:1

دعم RTL كامل في الواجهة ولوحة التحكم

15) الأداء

أهداف CWV: LCP ≤ 2.5s • CLS ≤ 0.05 • INP ≤ 200ms على 4G متوسط

Lazy للصور والفيديو • صور srcset • YouTube وضع الخصوصية مع معاينة قبل التشغيل

تحميل أصول الإضافة عند الحاجة فقط داخل صفحات game

16) الأمان

Nonce لكل عمليات الإدارة وAJAX

capability رئيسي: manage_momarab_core، إخفاء القوائم عمن لا يملكها

REST CORS مغلق افتراضيًا • السماح لقائمة بيضاء عند الحاجة

عدم كشف رقم الإصدار في الواجهة

17) البيانات والسياسة

التعطيل لا يحذف بيانات • الحذف الكامل عند إزالة الإضافة نهائيًا فقط

Multisite: حذف بيانات المدوّنة الحالية فقط

لا جمع بيانات تتبع. سطر خصوصية للتصويت: كوكي محلية فقط

18) الصور والأحجام

Hero 1200×675 • Card 600×338 • Thumb 300×169

سياسة قص/توسيط موحّدة • WebP إن توفّر

19) الترجمة

العربية أساسًا، جاهزية لإضافة الإنجليزية لاحقًا

ترجمة PHP وJS، وملفات JSON لنصوص JS

20) التوافق

وراثة كاملة لـ Blocksy (Typography/Palette/Spacing)

لا خطوط خارجية إطلاقًا

يعمل ضمن Elementor Preview دون كسر تخطيط Blocksy

Sitemap/Breadcrumbs عبر القالب أو Rank Math

21) الترقية والنسخ الاحتياطي

خيار mcp_db_version لإجراءات الترحيل

حفظ/تصدير إعدادات JSON لاحقًا

خذ نسخة DB/Uploads قبل أي ترقية

22) معايير القبول

تنصيب نظيف بلا تحذيرات PHP

شريط فلترة أفقي يحدّث الرابط ويحفظ الحالة

صفحة لعبة كاملة بلا CLS وبلا خطوط خارجية

REST والودجات ضمن الحدود، والكاش الداخلي فعّال

مؤشرات الأداء والوصول ضمن الحدود

إزالة الإضافة تنظّف البيانات دون مخلفات

momarab-core/
├─ momarab-core.php
├─ uninstall.php
├─ README.md
├─ CHANGELOG.md
├─ languages/
│  ├─ momarab-core.pot
│  ├─ momarab-core-ar.po
│  ├─ momarab-core-ar.mo
│  ├─ mcp-front-ar.json
│  ├─ mcp-archive-filter-ar.json
│  └─ mcp-single-media-ar.json
├─ assets/
│  ├─ css/
│  │  ├─ front.css
│  │  ├─ front-archive.css
│  │  ├─ front-single.css
│  │  └─ admin.css
│  ├─ js/
│  │  ├─ front.js
│  │  ├─ archive-filter.js
│  │  ├─ single-media.js
│  │  └─ admin.js
│  └─ img/
│     ├─ placeholder-game.jpg
│     └─ icons/
├─ includes/
│  ├─ bootstrap/
│  │  ├─ class-mcp-autoloader.php
│  │  └─ class-mcp-init.php
│  ├─ core/
│  │  ├─ class-mcp-assets.php
│  │  ├─ class-mcp-templates.php
│  │  ├─ class-mcp-permalinks.php
│  │  └─ helpers.php
│  ├─ content/
│  │  ├─ class-mcp-cpt.php
│  │  ├─ class-mcp-taxonomies.php
│  │  └─ meta/
│  │     ├─ class-mcp-meta-registry.php         # حقول اللعبة + ملاحظة المحرر
│  │     ├─ class-mcp-meta-validation.php
│  │     └─ class-mcp-meta-save.php
│  ├─ settings/
│  │  ├─ class-mcp-settings.php                 # Blocksy-only, REST, Schema, Cache, Voting
│  │  ├─ class-mcp-terms-manager.php            # زر إنشاء المصطلحات
│  │  └─ views/
│  │     ├─ settings-page.php
│  │     └─ terms-tools.php
│  ├─ dashboard/
│  │  ├─ class-mcp-dashboard.php                # KPIs + حالة الكاش + جودة البيانات
│  │  └─ views/
│  │     └─ dashboard.php
│  ├─ features/
│  │  ├─ ajax/
│  │  │  └─ class-mcp-ajax-filter.php           # فلترة الأرشيف
│  │  ├─ votes/                                 # تصويت Like/Dislike
│  │  │  ├─ class-mcp-votes-controller.php      # منطق التصويت + معدل الطلبات
│  │  │  ├─ class-mcp-votes-storage.php         # totals + حالة المستخدم
│  │  │  └─ class-mcp-votes-render.php          # واجهة الزرين ونسبة الرضا
│  │  ├─ shortcodes/
│  │  │  ├─ class-mcp-shortcode-games.php
│  │  │  └─ class-mcp-shortcode-game-filter.php
│  │  ├─ widgets/
│  │  │  ├─ class-mcp-widget-popular.php
│  │  │  └─ class-mcp-widget-recent.php
│  │  ├─ related/
│  │  │  ├─ class-mcp-related-meta.php          # ربط المقال باللعبة
│  │  │  └─ class-mcp-related-render.php        # عرض “آخر خبر”
│  │  └─ rest/
│  │     ├─ class-mcp-rest-controller.php
│  │     ├─ class-mcp-rest-games.php
│  │     └─ class-mcp-rest-taxonomies.php
│  ├─ security/
│  │  ├─ class-mcp-nonce.php
│  │  └─ class-mcp-capabilities.php
│  └─ performance/
│     ├─ class-mcp-cache.php                    # كاش الاستعلامات والودجات وREST
│     └─ class-mcp-images.php                   # WebP/srcset/Lazy
└─ templates/
   ├─ single-games.php
   ├─ archive-games.php
   └─ parts/
      ├─ header-card.php
      ├─ game-basics.php
      ├─ game-media.php
      ├─ game-ratings.php                       # تقييم المحرر + الملاحظة
      ├─ votes-bar.php                          # أزرار Like/Dislike + النسبة
      └─ related-news.php


24) إجراءات التشغيل السريع

فعّل Blocksy + أوقف Google Fonts

فعّل الإضافة

لوحة التحكم → إنشاء المصطلحات الأساسية

أضف لعبة تجريبية (صورة بارزة + تقييم محرر + ملاحظة)

اربط مقالًا واحدًا باللعبة لاختبار الخبر المرتبط

اختبر الأرشيف والفلترة وترتيب “الأعلى تقييمًا” و“الأكثر إعجابًا”

راقب الكاش والـ Hits/Misses، ثم Lighthouse وأداء CWV

25) سياسة “لا ملفات اختبار”

لا مجلد tests/، لا E2E، لا عينات بيانات، لا Fixtures

الاختبار يتم يدويًا على موقعك التجريبي وفق اختبار القبول السريع
