🎮 MOMARAB CORE 1.0 — دليل الاستخدام الرسمي (نسخة شخصية)

الغرض: نظام متكامل لإدارة وعرض ألعاب MMO بالعربية على ووردبريس مع تكامل Blocksy، فلترة Ajax، تقييم مُحرّر، تصويت زوار Like/Dislike، وخبر مرتبط واحد.
نطاق الاستخدام: شخصي/خاص. لا نشر عام. لا ملفات اختبار. لا بيانات ديمو. لا خطوط خارجية.

1) المتطلبات

WordPress: 6.x

PHP: 7.4 أو 8.x (موصى 8.1+)

القالب: Blocksy مفعّل

الخطوط: تعطيل Google Fonts في Blocksy وأي منشئ صفحات

2) الهدف

مكتبة ألعاب MMO عربية مع:

أرشيف /games/ بفلترة أفقيّة سريعة.

صفحة لعبة منظمة: Hero → معلومات → وسائط → تقييمات + ملاحظة → خبر واحد → بيانات سكيما.

تقييم مُحرّر 1–10 بخطوة 0.5 مع Overall محسوب.

تصويت Like/Dislike للزوار والمستخدمين.

وراثة كاملة لألوان/خطوط/مسافات Blocksy. لا خطوط خارجية.

3) الكيانات

CPT: game
أرشيف عبر rewrite slug = games.

التصنيفات:
game_type, game_status, game_mode, game_platform

السلاجات: ثابتة بالإنجليزية. الأسماء المعروضة بالعربية.

4) المصطلحات الافتراضية (Seed Terms)

game_type:
mmorpg • mmo-arpg • mmofps • moba • mmorts • survival-mmo • sandbox-mmo • social-mmo • battle-royale • racing-mmo • sports-mmo • space-mmo • naval-mmo • anime-mmo

game_status:
upcoming • alpha • beta • early-access • released

game_mode:
pve • pvp • pvpve • open-world • co-op

game_platform:
pc • playstation • xbox • nintendo-switch • mobile • browser

زر “إنشاء المصطلحات الأساسية” يضيف البنود أعلاه، يتخطّى المكرر، ويمكن قفلها لمنع الحذف العرضي.

5) الحقول (Meta)

أساسية: المطوّر • الناشر • تاريخ الإصدار • الموقع الرسمي (https فقط) • المحرك
وسائط: رابطا YouTube كحد أقصى • معرض حتى 6 صور
تقييم المُحرّر: 1–10 بخطوة 0.5

Story • Gameplay • Graphics • Audio

Overall محسوب افتراضيًا: Gameplay 40% • Story 25% • Graphics 20% • Audio 15%

يمكن تعديل الأوزان من الإعدادات.

ملاحظة تحريرية ≤ 240 حرفًا

روابط اختيارية: Steam • PlayStation • Xbox • Discord

ربط خبر: في المقال العادي حقل لاختيار لعبة واحدة ليظهر “آخر خبر” في صفحة اللعبة.

6) الواجهة
أرشيف الألعاب /games/

شريط فلترة أفقي متعدد الاختيار: النوع/المنصة/الأسلوب.

ترتيب: newest • oldest • az • za • toprated • mostliked.

تحديث URL بالباراميترات وحفظ الحالة عند الرجوع.

Empty state: رسالة ودّية + اقتراح 3 فلاتر شائعة.

يعمل دون قوائم جانبية. يعمل حتى بدون JS عبر GET.

صفحة اللعبة

الترتيب: Hero + عنوان + شارات → معلومات أساسية → وسائط → تقييمات + ملاحظة → خبر مرتبط 1 → سكيما.

إن لا توجد أخبار مرتبطة: يُخفى القسم.

الصورة البارزة مطلوبة. إن غابت يُستخدم بديل داخلي.

7) التصويت (Like/Dislike)

للزوّار والمستخدمين. صوت واحد قابل للتبديل لكل لعبة.

العرض: عدّاد الإعجابات وعدم الإعجاب + نسبة الرضا = likes / (likes + dislikes).

ترتيب إضافي في الأرشيف: mostliked = (likes − dislikes) مع كسر تعادل بالـ ratio.

لا يدخل في السكيما.

مكافحة سبام: 1 فعل/15ث، 30 طلب/دقيقة/IP (و 10/دقيقة داخل wp-admin). لا تخزين IP دائم. زائر عبر كوكي موقّعة، مستخدم عبر user_id.

8) الكاش الداخلي

يُكاشي: نتائج فلترة الأرشيف • الودجات • قوائم التصنيفات • ردود REST الشائعة.

TTL: أرشيف/REST 10د • ودجات 15د • تصنيفات 60د.

تفريغ ذكي عند نشر/تحديث/حذف لعبة أو مصطلح.

Stampede protection: قفل مؤقت لكل مفتاح + تأخير قصير بعد انتهاء TTL.

مهمة CRON تنظيف كل 6 ساعات.

لا كاش HTML كامل للصفحات (يُترك لـ LiteSpeed).

9) REST API

Namespace: momarab/v1

المسارات:

/games — فلترة/بحث/ترقيم

/taxonomies — قوائم التصنيفات

المعاملات: per_page, page, search, type, status, orderby, order

حد per_page الأقصى: 24 مفروض في REST والشورتكود وAjax.

order المسموح: newest, oldest, az, za, toprated, mostliked

كل المعاملات لها sanitize/validate. رسائل أخطاء عربية موحّدة.

قراءة فقط. CORS قراءة بنطاقات بيضاء عند الحاجة.

GET /wp-json/momarab/v1/games?per_page=12&order=mostliked

10) SEO وSchema

Schema.org: Game + AggregateRating من تقييم المُحرّر فقط. VideoObject عند وجود فيديو.

أرشيف بفلترة: Canonical لنسخة الأرشيف بلا باراميترات.

لا توليد مزدوج عند وجود Rank Math؛ عند التعارض تتوقف سكيما الإضافة تلقائيًا.

rel="prev/next" للترقيم. Breadcrumbs عبر القالب/Rank Math.

11) الوصول وRTL

الفلترة قابلة للتنقّل بالكيبورد بالكامل. عناصر بوسوم ARIA. النتائج بـ aria-live=polite.

تباين ≥ 4.5:1.

دعم RTL كامل للواجهة ولوحة التحكم.

12) الأداء

أهداف CWV: LCP ≤ 2.5s • CLS ≤ 0.05 • INP ≤ 200ms على شبكة 4G متوسطة.

صور lazy + srcset. YouTube Privacy-Enhanced مع Poster محلي وتشغيل عند النقر.

تحميل أصول الإضافة فقط عند الحاجة وفي صفحات game.

13) الأمان

Nonces لكل عمليات الميتا/الإعدادات/Ajax.

صلاحية رئيسية: manage_momarab_core، وإخفاء القوائم لمن لا يملكها.

REST CORS مغلق افتراضيًا. لا كشف رقم الإصدار في الواجهة.

14) الصور والأحجام

Hero: 1200×675

Card: 600×338

Thumb: 300×169

قص/توسيط موحّد. استخدام WebP إن توفر.

15) الترجمة

Text Domain: momarab-core • Domain Path: /languages

PHP: momarab-core-ar.po/.mo

JS: ملفات JSON عبر wp_set_script_translations().

16) التوافق

وراثة Blocksy كاملة (Typography/Palette/Spacing).

لا خطوط خارجية إطلاقًا.

يعمل داخل Elementor Preview دون كسر تخطيط Blocksy.

Sitemap/Breadcrumbs عبر القالب أو Rank Math.

17) الترقية والنسخ الاحتياطي

خيار قاعدة بيانات: mcp_db_version للترحيلات المستقبلية.

حفظ/تصدير إعدادات JSON لاحقًا.

خذ نسخة DB/Uploads قبل أي ترقية.

18) البيانات والسياسة

التعطيل لا يحذف المحتوى.

الحذف النهائي عبر uninstall يحذف إعدادات الإضافة والكاش فقط.

خصوصية: لا تتبع. كوكي محلية للتصويت فقط. لا إرسال خارجي.

19) معايير القبول

تنصيب بلا تحذيرات PHP.

أرشيف /games/ يعمل. شريط الفلترة يحدّث URL ويحفظ الحالة.

صفحة اللعبة كاملة بلا CLS وبلا خطوط خارجية.

REST والودجات ضمن الحدود. الكاش الداخلي فعّال.

مؤشرات CWV والوصول ضمن الأهداف.

إزالة الإضافة تنظّف الإعدادات والكاش دون مسّ المحتوى.

20) خطوات التشغيل السريع

فعّل Blocksy وأوقف Google Fonts.

فعّل الإضافة.

MOMARAB CORE → إعدادات → إنشاء المصطلحات الأساسية.

أضف لعبة تجريبية: صورة بارزة + حقول + تقييمات + ملاحظة.

أضف مقالًا واربطه باللعبة لاختبار “آخر خبر”.

افتح /games/ وجرب الفلترة وترتيبات toprated/mostliked.

راقب لوحة التحكم: Hits/Misses للكاش + تقرير التصويت.

21) الشورتكود والودجات

الشورتكود

عرض ألعاب:
[momarab_games limit="12" order="toprated"]
[momarab_games type="mmorpg" platform="pc" order="mostliked" limit="8"]
limit يُقصّ خادميًا إلى 24 كحد أقصى.

شريط الفلترة:
[momarab_game_filter]

الودجات

Popular Games: حسب mcp_rating_overall ثم الأحدث.

Recent Games: حسب تاريخ النشر.

إعداد “عدد العناصر” يلتزم بحد أقصى 24.

22) إعداد Blocksy السريع

عطّل Google Fonts.

Typography = System Default.

تأكد من حاويات/مسافات القالب الافتراضية.

فعّل Breadcrumbs إن رغبت. السكيما من Rank Math.

23) شجرة الملفات مع الوصف (للنسخ)
momarab-core/
├─ momarab-core.php                        — نقطة الدخول: ثوابت، autoloader، تفعيل/تعطيل، تشغيل الوحدات
├─ uninstall.php                           — حذف إعدادات وكاش الإضافة فقط عند الإزالة النهائية
├─ README.md                               — هذا الدليل
├─ CHANGELOG.md                            — سجل التغييرات
├─ languages/                              — ترجمات PHP وJS
│  ├─ momarab-core.pot                     — قالب النصوص
│  ├─ momarab-core-ar.po                   — ترجمة عربية قابلة للتحرير
│  ├─ momarab-core-ar.mo                   — الترجمة المجمّعة
│  ├─ mcp-front-ar.json                    — ترجمات JS للواجهة العامة
│  ├─ mcp-archive-filter-ar.json           — ترجمات JS لفلترة الأرشيف
│  └─ mcp-single-media-ar.json             — ترجمات JS لوسائط الصفحة
├─ assets/                                 — أصول الواجهة ولوحة التحكم
│  ├─ css/
│  │  ├─ front.css                         — عام (وراثة Blocksy + RTL)
│  │  ├─ front-archive.css                 — أرشيف + شريط فلترة
│  │  ├─ front-single.css                  — صفحة لعبة (Hero/ratings/media)
│  │  └─ admin.css                         — لوحة التحكم
│  ├─ js/
│  │  ├─ front.js                          — تهيئة عامة + i18n
│  │  ├─ archive-filter.js                 — Ajax فلترة + تحديث URL/حفظ الحالة + fallback GET
│  │  ├─ single-media.js                   — YouTube Privacy + Poster + lazy + Gallery
│  │  └─ admin.js                          — إعدادات + أدوات المصطلحات
│  └─ img/
│     ├─ placeholder-game.jpg              — بديلة عند غياب الصورة
│     └─ icons/                            — أيقونات مساعدة
├─ includes/                               — النواة والمنطق
│  ├─ bootstrap/
│  │  ├─ class-mcp-autoloader.php          — تحميل فئات PSR-4-ish
│  │  └─ class-mcp-init.php                — ربط الهوكات وفحص المتطلبات
│  ├─ core/
│  │  ├─ class-mcp-assets.php              — تحميل أصول مشروط + versioning
│  │  ├─ class-mcp-templates.php           — توجيه قوالب single/archive + locate override
│  │  ├─ class-mcp-permalinks.php          — rewrite /games/ + flush مرة عند التفعيل
│  │  └─ helpers.php                       — أدوات تنسيق/تحقق/صور
│  ├─ content/
│  │  ├─ class-mcp-cpt.php                 — تسجيل CPT `game` (has_archive=true, slug=games)
│  │  ├─ class-mcp-taxonomies.php          — game_type/status/mode/platform
│  │  └─ meta/
│  │     ├─ class-mcp-meta-registry.php    — أساسية/وسائط/تقييمات/روابط + أوزان التقييم
│  │     ├─ class-mcp-meta-validation.php  — تحقق (1–10، https، حدود، يوتيوب)
│  │     └─ class-mcp-meta-save.php        — حفظ آمن + nonce + قدرات
│  ├─ settings/
│  │  ├─ class-mcp-settings.php            — Blocksy-only/Cache/REST/Schema/Votes + تعديل أوزان التقييم
│  │  ├─ class-mcp-terms-manager.php       — إنشاء/تحديث المصطلحات الأساسية
│  │  └─ views/
│  │     ├─ settings-page.php              — واجهة الإعدادات
│  │     └─ terms-tools.php                — أدوات المصطلحات
│  ├─ dashboard/
│  │  ├─ class-mcp-dashboard.php           — KPIs + Hits/Misses + جودة البيانات
│  │  └─ views/
│  │     └─ dashboard.php                  — شاشة لوحة المعلومات
│  ├─ features/
│  │  ├─ ajax/
│  │  │  └─ class-mcp-ajax-filter.php      — فلترة الأرشيف + nonce + rate-limit + كاش
│  │  ├─ votes/
│  │  │  ├─ class-mcp-votes-controller.php — منطق التصويت + سياسات الاستخدام
│  │  │  ├─ class-mcp-votes-storage.php    — totals + حالة المستخدم/الضيف
│  │  │  └─ class-mcp-votes-render.php     — الأزرار + نسبة الرضا + تفريغ كاش موضعي
│  │  ├─ shortcodes/
│  │  │  ├─ class-mcp-shortcode-games.php  — [momarab_games]
│  │  │  └─ class-mcp-shortcode-game-filter.php — [momarab_game_filter]
│  │  ├─ widgets/
│  │  │  ├─ class-mcp-widget-popular.php   — ودجت الألعاب الشائعة
│  │  │  └─ class-mcp-widget-recent.php    — ودجت أحدث الألعاب
│  │  ├─ related/
│  │  │  ├─ class-mcp-related-meta.php     — ربط المقال باللعبة (post → game)
│  │  │  └─ class-mcp-related-render.php   — عرض “آخر خبر” في صفحة اللعبة
│  │  └─ rest/
│  │     ├─ class-mcp-rest-controller.php  — namespace ومعاملات مشتركة
│  │     ├─ class-mcp-rest-games.php       — /momarab/v1/games
│  │     └─ class-mcp-rest-taxonomies.php  — /momarab/v1/taxonomies
│  ├─ security/
│  │  ├─ class-mcp-nonce.php               — nonces (meta/settings/filter)
│  │  └─ class-mcp-capabilities.php        — قدرات وصلاحيات الإدارة
│  └─ performance/
│     ├─ class-mcp-cache.php               — كاش الاستعلامات/الودجات/REST + تفريغ ذكي
│     └─ class-mcp-images.php              — أحجام صور + srcset + WebP + lazy
└─ templates/                              — قابلة للـ override من القالب الابن
   ├─ single-game.php                      — Hero → Basics → Media → Ratings → News → Schema
   ├─ archive-game.php                     — /games/ + شريط فلترة وترتيب
   └─ parts/
      ├─ header-card.php                   — رأس البطاقة/الهيرو وصورة متجاوبة
      ├─ game-basics.php                   — المطوّر/الناشر/التاريخ/المحرك/الروابط
      ├─ game-media.php                    — YouTube Privacy + Poster + معرض حتى 6 صور
      ├─ game-ratings.php                  — تقييمات المُحرّر + الملاحظة
      ├─ votes-bar.php                     — Like/Dislike + العدّاد والنسبة
      └─ related-news.php                  — خبر مرتبط واحد أو إخفاء

24) ملاحظات تنفيذية حاسمة

ثبّت CPT = game ولا تغيّره لاحقًا. الأرشيف يظل عبر rewrite slug = games.

per_page ≤ 24 دائمًا في REST والشورتكود وAjax.

الترتيب mostliked متاح رسميًا ويعتمد (likes − dislikes) مع كسر تعادل بالـratio.

لا خطوط خارجية مطلقًا.

YouTube بوضع Privacy-Enhanced مع Poster محلي وتشغيل عند النقر.

عند التفعيل لأول مرة: ادخل الإعدادات واضغط إنشاء المصطلحات الأساسية ثم حفظ الروابط الدائمة من إعدادات ووردبريس.
