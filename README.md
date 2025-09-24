# 🎮 MOMARAB CORE
## المواصفات التقنية والتنفيذ

> **إضافة ووردبريس متخصصة لإدارة وعرض ألعاب MMO بالعربية**  
> متوافقة مع Blocksy • دعم RTL كامل • فلترة Ajax • شورتكود وودجات • REST API • ربط الأخبار باللعبة • أداء وأمان محسنان

---

## 📋 المتطلبات الأساسية

| المتطلب | الإصدار |
|---------|---------|
| **WordPress** | 6.x+ |
| **PHP** | 7.4+ (مستهدف 8.1+) |
| **القالب** | Blocksy نشط |
| **الخطوط** | لا خطوط خارجية |

#### 🧪 التوافق المختبر
- ✅ **PHP 8.2/8.3**: مختبر ومتوافق مع أحدث إصدارات PHP
- ✅ **WordPress 6.6**: مختبر ومتوافق مع آخر إصدار ووردبريس
- ✅ **الاستقرار**: اختبارات شاملة على بيئات مختلفة

### 🌐 متطلبات التدويل (i18n)

- ✅ **تحميل ملفات الترجمة**: `load_plugin_textdomain( 'momarab-core', false, 'momarab-core/languages' )`
- ✅ **تهريب النصوص**: جميع النصوص تمر عبر `__()` أو `_e()` أو `esc_html__()`
- ✅ **Text Domain**: `momarab-core` في جميع الملفات
- ✅ **Domain Path**: `/languages` لملفات الترجمة
- ✅ **ترجمة JavaScript**: استخدام `wp_set_script_translations()` لتمكين ترجمة strings داخل ملفات JS

#### 🌍 تسمية ملفات اللغات
- ✅ **صيغة الملفات**: `momarab-core-xx_XX.mo/po` (مثال: `momarab-core-ar.mo`)
- ✅ **ملف POT**: `momarab-core.pot` محدث مع كل إصدار
- ✅ **العربية**: `momarab-core-ar.mo` و `momarab-core-ar.po`
- ✅ **توليد ملفات JSON**: `wp i18n make-json` ضمن خطوات الإصدار للـ JavaScript

## 📄 معلومات الترخيص والميتاداتا

| المعلومة | القيمة |
|---------|--------|
| **الترخيص** | GPLv2+ |
| **Text Domain** | `momarab-core` |
| **Domain Path** | `/languages` |
| **Namespace** | `Momarab_Core` |

### 🔧 الثوابت الموحدة

| الثابت | الوصف |
|--------|-------|
| `MCP_VERSION` | إصدار الإضافة |
| `MCP_FILE` | مسار الملف الرئيسي |
| `MCP_DIR` | مجلد الإضافة |
| `MCP_URL` | رابط الإضافة |
| `MCP_ASSETS` | مجلد الأصول |

### 📝 رأس ملف الإضافة الرئيسي

يجب تضمين الحقول التالية في رأس `momarab-core.php`:

**الحقول المطلوبة:**
- Plugin Name, Plugin URI, Description, Version
- Requires at least, Tested up to: 6.6, Requires PHP
- Author, Text Domain, Domain Path
- **Stable tag**: يجب أن يساوي `MCP_VERSION` منطقياً

#### 🔄 التزامن والإصدار (قاعدة إجبارية)
- ✅ **قاعدة ثابتة**: Version (رأس الإضافة) = Stable tag (readme) = MCP_VERSION
- ✅ **عند كل إصدار**: تحديث القيم الثلاث معاً بنفس الرقم
- ✅ **التحقق**: فحص تطابق الإصدارات قبل النشر
- ✅ **Versioning للأصول**: CSS/JS تُحمَّل مع رقم الإصدار لمنع الـ cache الخبيث بعد التحديثات
- ✅ **Verified in release checklist**: تأكيد في قائمة مراجعة الإصدار

### 📝 متطلبات readme.txt

يجب وضع المعلومات التالية في أعلى `readme.txt`:

**الحقول المطلوبة:**
- Contributors, Tags, Requires at least: 6.0
- Tested up to: 6.6, Requires PHP: 7.4
- Stable tag: 1.0.0
- License, License URI, وأقسام Screenshots, FAQ, Changelog

**مثال readme.txt محسّن:**
```
=== MOMARAB CORE ===
Contributors: momarabdev
Donate link: https://momarab.com/donate
Tags: mmo, games, arabic, rtl, blocksy, gaming, reviews
Requires at least: 6.0
Tested up to: 6.6
Requires PHP: 7.4
Stable tag: 1.0.0
License: GPLv2 or later
License URI: https://www.gnu.org/licenses/gpl-2.0.html

== Description ==
إضافة ووردبريس متخصصة لإدارة وعرض ألعاب MMO بالعربية مع دعم RTL كامل وفلترة Ajax

== Installation ==
1. ارفع مجلد الإضافة إلى `/wp-content/plugins/`
2. فعّل الإضافة من لوحة التحكم
3. اذهب إلى "MOMARAB CORE → إعدادات" للتكوين
4. أضف المصطلحات الأساسية من نفس الصفحة

== Screenshots ==
1. screenshot-1.png - صفحة أرشيف الألعاب مع الفلترة والترتيب
2. screenshot-2.png - صفحة لعبة مفردة مع التقييمات والمعرض
3. screenshot-3.png - لوحة تحكم إضافة لعبة جديدة مع الحقول المخصصة

== WordPress.org Assets ==
Banner: assets/banner-1544x500.png
Icon: assets/icon-256x256.png

== Frequently Asked Questions ==
= هل تدعم الإضافة RTL والعربية؟ =
نعم، دعم كامل للغة العربية واتجاه RTL مع ملفات ترجمة مدمجة.

= هل تتوافق مع قوالب أخرى غير Blocksy؟ =
الإضافة مصممة خصيصاً لـ Blocksy لأفضل تكامل، لكن يمكن استخدامها مع قوالب أخرى مع تخصيص إضافي.

= كيف أستخدم الشورتكود؟ =
استخدم `[momarab_games limit="6" order="toprated"]` لعرض الألعاب أو `[momarab_game_filter]` للفلترة.

== Changelog ==
= 1.0.0 - 2025-02-28 =
* الإصدار الأولي
* إدارة ألعاب MMO مع حقول مخصصة
* 4 تصنيفات: النوع، الحالة، أسلوب اللعب، المنصات
* فلترة Ajax مع تحديث URL
* REST API للاستعلامات الخارجية
* دعم RTL كامل وترجمة عربية
* تكامل مع قالب Blocksy
```

### 📦 Composer/PSR-4 (اختياري لكن مفيد)

**إعداد PSR-4 Autoloading:**
- ✅ **Namespace**: `Momarab_Core` يشير إلى مجلد `includes/`
- ✅ **تحميل تلقائي**: PSR-4 autoloading للفئات
- ✅ **إدارة التبعيات**: إمكانية إضافة مكتبات خارجية مستقبلاً
- ✅ **معايير الكود**: اتباع معايير PHP الحديثة

---

## 🗂️ هيكل المشروع والوظائف

### 📁 شجرة الملفات

```
momarab-core/
├─ momarab-core.php                 ← نقطة الدخول. تعريف الثوابت والتشغيل.
├─ readme.txt                       ← وصف ووردبريس.
├─ CHANGELOG.md                     ← سجل تغييرات SemVer.
├─ uninstall.php                    ← تنظيف إعدادات عند الحذف.
├─ languages/
│  ├─ momarab-core.pot
│  ├─ ar.mo
│  └─ ar.po
├─ assets/
│  ├─ css/
│  │  ├─ front.css                  ← أنماط عامة للواجهة.
│  │  ├─ front-archive.css          ← أنماط أرشيف الألعاب.
│  │  ├─ front-single.css           ← أنماط صفحة لعبة.
│  │  └─ admin.css                  ← أنماط لوحة التحكم.
│  ├─ js/
│  │  ├─ front.js                   ← تهيئة عامة للواجهة.
│  │  ├─ archive-filter.js          ← فلترة Ajax للأرشيف + تحديث URL.
│  │  ├─ single-media.js            ← تشغيل فيديو ويوتيوب ومعرض الصور.
│  │  └─ admin.js                   ← واجهات الحقول والإعدادات.
│  └─ img/
│     ├─ placeholder-game.jpg
│     └─ icons/
├─ includes/
│  ├─ bootstrap/
│  │  ├─ class-mcp-autoloader.php   ← التحميل التلقائي للفئات.
│  │  └─ class-mcp-init.php         ← ربط الخطافات وفحص المتطلبات.
│  ├─ core/
│  │  ├─ class-mcp-assets.php       ← تحميل الأصول عند الحاجة فقط.
│  │  ├─ class-mcp-templates.php    ← توجيه قوالب single/archive وربط الأجزاء.
│  │  ├─ class-mcp-permalinks.php   ← إدارة rewrite و flush عند التفعيل فقط.
│  │  └─ helpers.php                ← توابع مساعدة (تنسيق/تحقق/صور).
│  ├─ content/
│  │  ├─ class-mcp-cpt.php          ← تسجيل CPT games.
│  │  ├─ class-mcp-taxonomies.php   ← تسجيل التصنيفات الأربع.
│  │  └─ meta/
│  │     ├─ class-mcp-meta-registry.php   ← تعريف مجموعات ومفاتيح الحقول.
│  │     ├─ class-mcp-meta-validation.php ← تحقق 1–10 والروابط والحدود.
│  │     └─ class-mcp-meta-save.php       ← حفظ آمن + nonce + قدرات.
│  ├─ settings/
│  │  ├─ class-mcp-settings.php     ← صفحة الإعدادات وأقسامها.
│  │  ├─ class-mcp-terms-manager.php← زر “إضافة المصطلحات الأساسية” وخيار الأوصاف فقط.
│  │  └─ views/
│  │     ├─ settings-page.php       ← واجهة الإعدادات.
│  │     └─ terms-tools.php         ← واجهة توليد/تحديث المصطلحات.
│  ├─ features/
│  │  ├─ ajax/
│  │  │  └─ class-mcp-ajax-filter.php     ← نقطة Ajax للفلترة وتحديث URL.
│  │  ├─ shortcodes/
│  │  │  ├─ class-mcp-shortcode-games.php       ← [momarab_games]
│  │  │  └─ class-mcp-shortcode-game-filter.php ← [momarab_game_filter]
│  │  ├─ widgets/
│  │  │  ├─ class-mcp-widget-popular.php  ← Popular Games.
│  │  │  └─ class-mcp-widget-recent.php   ← Recent Games.
│  │  ├─ related/
│  │  │  ├─ class-mcp-related-meta.php    ← حقل ربط المقال باللعبة في post.
│  │  │  └─ class-mcp-related-render.php  ← “آخر خبر عن اللعبة” في صفحة اللعبة.
│  │  └─ rest/
│  │     ├─ class-mcp-rest-controller.php ← أساس REST namespace.
│  │     ├─ class-mcp-rest-games.php      ← /momarab/v1/games
│  │     └─ class-mcp-rest-taxonomies.php ← /momarab/v1/taxonomies
│  ├─ security/
│  │  ├─ class-mcp-nonce.php        ← إنشاء/فحص nonces.
│  │  └─ class-mcp-capabilities.php ← فحص manage_options/edit_post/manage_categories.
│  └─ performance/
│     ├─ class-mcp-cache.php        ← كاش قصير للأرشيف والودجات.
│     └─ class-mcp-images.php       ← أحجام صور وتأخير كسول.
├─ templates/
│  ├─ single-games.php              ← عرض لعبة مفردة.
│  ├─ archive-games.php             ← أرشيف الألعاب مع شريط فلترة.
│  └─ parts/
│     ├─ header-card.php            ← رأس بطاقة اللعبة.
│     ├─ game-basics.php            ← مطوّر/ناشر/تاريخ/محرك/مميزات.
│     ├─ game-media.php             ← يوتيوب + معرض حتى 4.
│     ├─ game-ratings.php           ← التقييمات التفصيلية + النهائي.
│     └─ related-news.php           ← خبر واحد مرتبط أو اختفاء.
└─ tests/                           ← اختياري.
   ├─ phpunit.xml.dist
   └─ unit/
      ├─ MetaValidationTest.php
      └─ RestEndpointsTest.php

---
### 🔗 ربط الشجرة بالمهام

| المكون | المسار |
|---------|--------|
| **CPT/Taxonomies** | `includes/content/` |
| **Meta (تعريف/تحقق/حفظ)** | `includes/content/meta/` |
| **الإعدادات + المصطلحات** | `includes/settings/` و `views/` |
| **فلترة Ajax** | `includes/features/ajax/` |
| **الشورتكود** | `includes/features/shortcodes/` |
| **الودجات** | `includes/features/widgets/` |
| **ربط الأخبار** | `includes/features/related/` |
| **REST API** | `includes/features/rest/` |
| **الأمان** | `includes/security/` |
| **الأداء والصور** | `includes/performance/` |
| **القوالب** | `templates/` |
| **الأصول** | `assets/` |

---

## 🎯 مواصفات نوع المحتوى والتصنيفات

### 🎮 نوع المحتوى المخصص (CPT)

| الخاصية | القيمة |
|---------|--------|
| **الاسم** | `games` |
| **الأرشيف** | `/games/` |
| **المفرد** | `/games/{post-name}` |
| **يدعم** | العنوان، المحتوى، الصورة البارزة، المقتطف، الحقول المخصصة |
| **الأيقونة** | `dashicons-games` |
| **has_archive** | `true` |
| **with_front** | `false` |
| **show_in_rest** | `true` |
| **capability_type** | `post` |
| **map_meta_cap** | `true` |

#### 🧩 دعم Gutenberg/Block Editor
- ✅ **المحرر الكتلي**: دعم كامل بفضل `show_in_rest: true`
- ✅ **REST Base**: افتراضياً `games` أو يمكن تخصيصه عبر `rest_base`
- ✅ **الحقول المخصصة**: متاحة في المحرر عبر meta boxes

### 🏷️ التصنيفات الأربعة

| التصنيف | Slug | Rewrite Slug | Hierarchical | show_in_rest |
|---------|------|-------------|--------------|--------------|
| **أنواع الألعاب** | `game_type` | `game_type` | `true` | `true` |
| **حالة اللعبة** | `game_status` | `game_status` | `true` | `true` |
| **أسلوب اللعب** | `game_mode` | `game_mode` | `true` | `true` |
| **المنصات** | `game_platform` | `game_platform` | `true` | `true` |

### 📝 البنود الأساسية

| التصنيف | البنود |
|---------|--------|
| **game_type** | MMORPG, MMOFPS, MOBA, Survival, Sandbox, Action-RPG |
| **game_status** | Upcoming, Alpha, Beta, Early Access, Released |
| **game_mode** | PvE, PvP, Co-op, Open World, Crafting, Raids |
| **game_platform** | PC, PlayStation, Xbox, Nintendo Switch, Mobile |

---

## 🔧 الحقول المخصصة في تحرير اللعبة

### 📋 الحقول الأساسية (Basic)

| الحقل | المفتاح | النوع |
|-------|---------|-------|
| **الموقع الرسمي** | `mcp_official_site` | URL |
| **المطوّر** | `mcp_developer` | نص |
| **الناشر** | `mcp_publisher` | نص |
| **تاريخ الإطلاق** | `mcp_release_date` | تاريخ ISO |

### ⚙️ المحرك (Engine)

| الحقل | المفتاح | النوع | القيم |
|-------|---------|-------|-------|
| **المحرك** | `mcp_engine` | Checkbox List | `unreal_engine`, `unity`, `cryengine`, `frostbite`, `custom` |

### ✨ الميزات (Features)

| الحقل | المفتاح | النوع |
|-------|---------|-------|
| **الميزة 1** | `mcp_feature_1` | نص |
| **الميزة 2** | `mcp_feature_2` | نص |
| **الميزة 3** | `mcp_feature_3` | نص |
| **الميزة 4** | `mcp_feature_4` | نص |

### 🎬 الوسائط (Media)

| الحقل | المفتاح | النوع |
|-------|---------|-------|
| **يوتيوب 1** | `mcp_trailer_youtube_1` | URL يوتيوب |
| **يوتيوب 2** | `mcp_trailer_youtube_2` | URL يوتيوب |
| **معرض الصور** | `mcp_gallery` | IDs (حد أقصى 4) |

### ⭐ التقييمات (Ratings) - مقياس 1-10 + ملاحظة

| التقييم | المفتاح الرقمي | مفتاح الملاحظة |
|---------|---------------|-----------------|
| **القصة** | `mcp_rating_story` | `mcp_rating_story_note` |
| **الجيمبلاي** | `mcp_rating_gameplay` | `mcp_rating_gameplay_note` |
| **الرسومات** | `mcp_rating_graphics` | `mcp_rating_graphics_note` |
| **الصوت** | `mcp_rating_audio` | `mcp_rating_audio_note` |
| **التقييم النهائي** | `mcp_rating_overall` | `mcp_rating_overall_note` |

### ✅ قواعد التحقق والأمان

#### 🔢 التحقق من البيانات
- ✅ **الأرقام**: 1–10 فقط للتقييمات
- ✅ **يوتيوب**: قبول `youtu.be` و `youtube.com/watch?v=` فقط، إخفاء غير ذلك
- ✅ **المعرض**: حد أقصى 4 صور، تجاهل الزائد مع تسجيل ملاحظة في سجل الإدارة
- ✅ **toprated**: ترتيب حسب `meta_key: mcp_rating_overall` و `meta_type: NUMERIC` و `orderby: meta_value_num`
- ✅ **per_page**: الحد الأقصى 50 مفروض خادميًا في REST والشورتكود والـ Ajax حتى لو تم تمرير قيمة أعلى

#### 🛡️ الأمان والصلاحيات
- 🔐 **صلاحيات CPT**: `capability_type => 'post'` و `map_meta_cap => true` للصلاحيات الدقيقة
- 🔐 **الصلاحيات**: `current_user_can('edit_post', $post_id)` عند الحفظ
- 🎫 **Nonce للحقول الميتا**: `mcp_meta_nonce` لحفظ الحقول المخصصة
- 🎫 **Nonce للإعدادات**: `mcp_settings_nonce` لصفحة الإعدادات
- 🎫 **Nonce للفلترة**: `mcp_filter_nonce` لطلبات Ajax
- ✅ **check_ajax_referer**: إجباري قبل أي استعلام Ajax

#### 🧹 قواعد الحفظ والتعقيم
- 🔗 **حقول URL**: استخدام `esc_url_raw()` عند حفظ الحقول من نوع URL
- 📝 **النصوص العادية**: استخدام `sanitize_text_field()` للنصوص البسيطة
- 📄 **المحتوى المنسق**: استخدام `wp_kses_post()` للمحتوى الذي يحتوي على HTML

#### 🛡️ أمان القوالب
- 🔒 **تهريب الإخراج**: استخدام `esc_html()` للنصوص العادية
- 🔒 **تهريب الخصائص**: استخدام `esc_attr()` لخصائص HTML
- 🔒 **تهريب الروابط**: استخدام `esc_url()` للروابط
- 🔒 **تهريب HTML**: استخدام `wp_kses_post()` للمحتوى المنسق
- 🎫 **التحقق من Nonce**: فحص `mcp_meta_nonce` للحقول المخصصة، `mcp_settings_nonce` في صفحة الإعدادات، و `mcp_filter_nonce` في طلبات Ajax

---

## ⚙️ الإعدادات وأدوات المصطلحات

### 🎛️ صفحة الإعدادات

**المسار:** `MOMARAB CORE → إعدادات`

#### 📂 قسم المصطلحات الأساسية

| الخيار | الوصف |
|--------|-------|
| **زر إضافة المصطلحات** | إضافة المصطلحات الأساسية لمرة واحدة |
| **إضافة/تحديث الوصف** | خيار لإضافة أو تحديث أوصاف المصطلحات |
| **تحديث الأوصاف فقط** | خيار لتحديث الأوصاف دون إضافة مصطلحات جديدة |

#### 📰 قسم عرض الأخبار المرتبطة

| الإعداد | القيمة الافتراضية |
|---------|------------------|
| **تمكين/تعطيل** | مُفعل |
| **عنوان القسم** | "آخر خبر عن اللعبة" |
| **حد النتائج** | 1 دائماً |

### 🔑 مفاتيح الإعدادات المحفوظة

| المفتاح | الوصف |
|---------|-------|
| `mcp_settings[seed_terms_descriptions]` | إعدادات أوصاف المصطلحات |
| `mcp_settings[descriptions_update_only]` | تحديث الأوصاف فقط |
| `mcp_settings[related_news_enabled]` | تفعيل الأخبار المرتبطة |
| `mcp_settings[related_news_title]` | عنوان قسم الأخبار |

---

## 🔗 ربط المقالات العادية بالألعاب

### 📝 في تحرير المقال (Post)

| الحقل | المفتاح | النوع |
|-------|---------|-------|
| **اختيار لعبة** | `mcp_related_game_id` | Select2 من games |

### 🎮 في صفحة اللعبة المفردة

#### 📰 قسم الأخبار المرتبطة

| الخاصية | التفاصيل |
|---------|----------|
| **العنوان** | "آخر خبر عن اللعبة" |
| **المحتوى** | آخر 1 مقال مرتبط حسب التاريخ |
| **السلوك** | يختفي إذا لا توجد نتائج |
| **العناصر** | صورة مصغّرة، عنوان، تاريخ، مقتطف، رابط |

---

## 🎨 القوالب والواجهة

### 📄 القوالب الرئيسية

| القالب | المحتوى |
|--------|---------|
| **single-games.php** | العنوان، بيانات أساسية، المحرك، المميزات، الترايلرات، المعرض، التقييمات، الخبر الأخير |
| **archive-games.php** | شبكة بطاقات + شريط فلترة وترتيب |
| **templates/parts/*** | بطاقات وأجزاء منظمة |

#### 🔄 تجاوز القوالب (Template Override)
- ✅ **قابلية التخصيص**: قوالب `templates/` قابلة للنسخ والoverride من القالب الإبن
- ✅ **آلية locate**: استخدام `locate_template()` لضمان قابلية التخصيص
- ✅ **مسار البحث**: قالب إبن أولاً، ثم قوالب الإضافة
- 📁 **مسار override المقترح**: `your-child-theme/momarab-core/single-games.php`

### 🌐 خصائص التصميم

- ✅ **RTL كامل** - دعم كامل للغة العربية
- ✅ **لا خطوط خارجية** - استخدام خطوط النظام
- ✅ **وراثة Blocksy** - للألوان والخطوط والحاويات
- ✅ **بادئة CSS الوحيدة mcp-** - سياسة إجبارية لمنع التعارض

### 📦 تحميل الأصول المشروط

| الملف | السياق |
|-------|---------|
| **front.js/front.css** | عالمي للواجهة |
| **archive-filter.js** | أرشيف games فقط |
| **single-media.js** | صفحة game مفردة فقط |
| **admin.css/admin.js** | شاشات games والإعدادات فقط |

---

## 🔍 فلترة Ajax للأرشيف

### 📥 المدخلات

| المعامل | النوع | الوصف |
|---------|-------|-------|
| **type, status, mode, platform** | ID/slug متعدد | معرفات أو slugs التصنيفات |
| **sort** | string | `newest\|oldest\|az\|za\|toprated` |
| **page** | integer | رقم الصفحة للترقيم |
| **per_page** | integer | عدد العناصر (افتراضي: 12، حد أقصى: 50) |

### 🔒 أمان Ajax

| العنصر | القيمة |
|--------|-------|
| **Nonce Name** | `mcp_filter_nonce` |
| **Action** | `mcp_filter_games` |
| **Capability** | متاح للجميع (قراءة فقط) |

### 📤 المخرجات

- 🎴 **شبكة بطاقات** + ترقيم
- 🔗 **تحديث URL** بـ Query String دون إعادة تحميل

### ⚡ تحسينات الأداء

- 🚀 **WP_Query محسنة** مع Tax/Meta Query
- 💾 **كاش قصير العمر** لنتائج الفلترة (5-10 دقائق)

---

## 📝 الشورتكود والودجات

### 🔖 الشورتكود المتاحة

#### `[momarab_games]`

| المعامل | القيم المتاحة | الوصف |
|---------|---------------|-------|
| **type, status, mode, platform** | IDs/slugs | فلترة حسب التصنيفات |
| **limit** | رقم | عدد الألعاب المعروضة (افتراضي: 12، حد أقصى: 50) |

| **order** | `newest\|oldest\|az\|za\|toprated` | ترتيب النتائج |

**ملاحظة مهمة:** أي قيمة limit أعلى من 50 تُقصّ خادمياً إلى 50 لضمان الأداء.

#### `[momarab_game_filter]`

- 🎛️ **يعرض واجهة الفلترة فقط**
- 🎯 **يستهدف أرشيف games**

### 🧩 الودجات المتاحة

| الودجت | الترتيب | الإعدادات |
|--------|---------|-----------|
| **Popular Games** | حسب `mcp_rating_overall` ثم الأحدث | عدد العناصر |
| **Recent Games** | حسب تاريخ النشر | عدد العناصر |

---

## 🔌 REST API

### 🌐 المعلومات الأساسية

**Namespace:** `momarab/v1`

### 📍 المسارات المتاحة

#### `/games`

| المعامل | النوع | الوصف |
|---------|-------|-------|
| **type, status, mode, platform** | string | فلترة حسب التصنيفات |
| **search** | string | البحث في العناوين والمحتوى |
| **page** | integer | رقم الصفحة |
| **per_page** | integer | عدد العناصر (افتراضي: 12، حد أقصى: 50) |
| **order** | string | ترتيب النتائج |

**ملاحظة:** أي قيمة per_page أعلى من 50 تُقصّ خادمياً إلى 50 تلقائياً.

#### 🔍 توثيق قيود REST والتحقق
- ✅ **كل معامل** له `sanitize_callback` و `validate_callback` محدد
- ✅ **per_page**: حدود 1-50 مع تحقق رقمي
- ✅ **order**: قائمة محددة من القيم المسموحة
  - `newest` - الأحدث أولاً
  - `oldest` - الأقدم أولاً
  - `az` - أبجدي صاعد
  - `za` - أبجدي نازل
  - `toprated` - الأعلى تقييماً
- ✅ **فلاتر التصنيفات**: تحقق من وجود term_id/slug

**المخرجات:** المعرف، العنوان، الرابط، الصورة، الحقول الأساسية، التقييمات، المصطلحات

#### `/taxonomies`

**المخرجات:** قوائم `game_type`, `game_status`, `game_mode`, `game_platform` مع المعرف والاسم والسلاج والوصف

### 🔒 خصائص الأمان والقيود

- 📖 **قراءة فقط** - لا تعديل عبر API، معطل التسجيل/التحديث
- 🌍 **UTF-8** - دعم كامل للعربية
- 🔗 **CORS**: القراءة متاحة افتراضياً ولا تُفتح طرق كتابة
- ⚠️ **CORS للدومينات الخارجية**: لاستهلاك API من دومينات أخرى بالمتصفح، يجب تفعيل ترويسات CORS للقراءة (GET) بشكل صريح
- 🌐 **الدومينات المسموحة**: `https://momarab.com`, `https://api.momarab.com` (لا `*` للأمان)
- ⚡ **حد per_page=50 موحّد**: مفروض خادميًا في REST والشورتكود والـ Ajax دائماً
- 🚫 **لا POST/PUT/DELETE في REST**: قراءة فقط، لا طرق كتابة مفتوحة

#### 📋 قائمة order المسموحة
- `newest` - الأحدث أولاً
- `oldest` - الأقدم أولاً  
- `az` - أبجدي صاعد
- `za` - أبجدي نازل
- `toprated` - الأعلى تقييماً

**خطأ 400**: أي قيمة order غير مدرجة أعلاه ترجع `{"code":"invalid_param"}`

### ⚠️ رموز أخطاء REST API

| رمز الخطأ | الوصف | المثال |
|-----------|--------|--------|
| **400** | معاملات غير صالحة | `{"code":"invalid_param","message":"معامل غير صالح","data":{"status":400}}` |
| **429** | تحديد المعدل (مستقبلاً) | `{"code":"rate_limit","message":"تم تجاوز الحد المسموح","data":{"status":429}}` |
| **500** | خطأ خادم عام | `{"code":"server_error","message":"خطأ في الخادم","data":{"status":500}}` |

#### 📋 بنية استجابة الخطأ الموحدة
```json
{
  "code": "error_code",
  "message": "رسالة الخطأ بالعربية",
  "data": {
    "status": 400,
    "params": ["المعاملات المرفوضة"]
  }
}
```

---

## 🎨 دعم Blocksy

### 🔗 التكامل مع القالب

#### 🎨 سلوك الوراثة المؤكد
- ✅ **وراثة كاملة**: جميع أنماط الإضافة مُسبوقة بـ `mcp-` ولا يوجد CSS reset
- ✅ **الحاويات والألوان والخطوط**: وراثة تلقائية من Blocksy
- 🚫 **عدم تحميل خطوط خارجية**: لا Google Fonts مطلقاً - استخدام خطوط النظام فقط
- 🔧 **مارك-أب بسيط**: يتنسق عبر Blocksy تلقائياً
- 🌐 **احترام RTL**: وإعدادات المظهر العالمية
- 📐 **متغيرات القالب**: احترام متغيرات CSS للألوان والخطوط

#### 🎯 سياسة CSS
- ✅ **البادئة الوحيدة**: `mcp-` فقط لجميع الفئات
- ❌ **لا CSS Reset**: عدم تعديل أنماط القالب الأساسية
- ✅ **التوافق**: ضمان عدم التداخل مع أنماط Blocksy

---

## 🛡️ الأمان والحماية

### 🔐 آليات الحماية

- 🎫 **Nonce** لكل عمليات الحفظ/الإعدادات
- 🧹 **تعقيم المدخلات** وتهريب المخرجات
- 🚫 **منع الوصول المباشر** للملفات

### 👥 إدارة الصلاحيات

| العملية | الصلاحية المطلوبة |
|---------|-------------------|
| **إعدادات/مصطلحات** | `manage_options` و/أو `manage_categories` |
| **حفظ الحقول** | `edit_post` |

---

## ⚡ تحسينات الأداء

### 🚀 استراتيجيات التحسين

- 📦 **تحميل الأصول عند الحاجة فقط**
- 🗜️ **دمج وتقليل CSS/JS** لكل سياق
- 🖼️ **صور كسولة** وأحجام WordPress الافتراضية
- 💾 **كاش استعلامات** الأرشيف والودجات (5-10 دقائق)
- 🔄 **إدارة الروابط الدائمة**: `flush_rewrite_rules()` مرة واحدة عند التفعيل فقط، وليس عند كل تحميل، ومعالجة حالة التعطيل أيضاً

### 🖼️ أحجام الصور المخصصة

| الحجم | الاستخدام | الأبعاد المقترحة |
|-------|----------|------------------|
| **mcp-card** | بطاقات الألعاب | 600×338 بكسل |
| **mcp-thumb** | صور مصغرة | 300×170 بكسل |

**ملاحظة مهمة:** أحجام الصور تُنشأ عند الرفع، وقد يلزم استخدام Regenerate Thumbnails للصور القديمة.

### 💾 مفاتيح الترانزينت (Transient Keys)

- `mcp_archive_cache_{hash}` - كاش الأرشيف
- `mcp_widget_popular_{limit}` - كاش الألعاب الشائعة
- `mcp_widget_recent_{limit}` - كاش الألعاب الحديثة

**مدة الكاش الافتراضية**: 10 دقائق (600 ثانية)

### 🔄 سياسة إبطال الكاش

**سيناريوهات التفريغ الأربعة:**

| السيناريو | الترانزينتات المحذوفة | المشغل |
|-----------|---------------------|---------|
| **حفظ لعبة** | جميع `mcp_*` | `save_post` hook |
| **تحديث حالة** | `mcp_archive_*`, `mcp_widget_*` | `transition_post_status` |
| **مصطلح** | `mcp_archive_*`, `mcp_widget_*` | `created/edited/deleted_term` |
| **إعدادات** | `mcp_news_*`, `mcp_widget_*` | `update_option` |

---

## 🗑️ الإعدادات والحذف

### 📋 لوحة الإدارة

#### 🔍 Select2 - الترخيص والتحميل
- ✅ **الترخيص**: Select2 مرخَّص MIT ويُحمَّل فقط في شاشات المقال
- ✅ **التحميل المشروط**: يُحمل فقط في شاشات post مع الاعتماد على jQuery
- ✅ **السياق**: حقل `mcp_related_game_id` داخل شاشات تحرير المقالات فقط
- ⚙️ **تحميل مشروط** للأصول حسب السياق

#### ♿ متطلبات إمكانية الوصول
- 🏷️ **aria-label**: إضافة تسميات وصفية للأزرار والعناصر التفاعلية
- 📑 **عناوين الأقسام**: استخدام عناوين H2, H3 بشكل هرمي صحيح
- 🏷️ **عناوين القوالب**: H1 في المفرد/أرشيف بترتيب منطقي
- 🎨 **تباين الألوان**: ضمان تباين كافٍ بين النص والخلفية
- ⌨️ **ترتيب التبويب**: ترتيب تبويب منطقي في واجهة الفلترة
- 🎯 **التركيز البصري**: مؤشرات واضحة للعناصر المركز عليها
- 📱 **الاستجابة**: دعم كامل للشاشات المختلفة

### 🗂️ ما يحذفه uninstall.php

#### ✅ يتم حذفه صراحة
- `delete_option('mcp_settings')` - إعدادات الإضافة فقط
- ترانزينتات الإضافة: جميع المفاتيح التي تبدأ بـ `mcp_*`
  - `mcp_archive_cache_*`
  - `mcp_widget_popular_*`
  - `mcp_widget_recent_*`

#### ❌ لا يتم حذفه نهائيًا
- بيانات الـ CPT (games) - تبقى محفوظة
- المصطلحات والتصنيفات - تبقى محفوظة
- الحقول المخصصة للمحتوى - تبقى محفوظة
- أي بيانات محتوى أنشأها المستخدم

---

## ⚠️ الحالات الحدّية

### 🔧 معالجة الحالات الاستثنائية

| الحالة | المعالجة |
|--------|----------|
| **لا صورة بارزة** | عرض عنصر نائب |
| **روابط يوتيوب غير صالحة** | إخفاء الفيديو (قبول `youtu.be` و `youtube.com/watch?v=` فقط) |
| **أكثر من 4 صور في المعرض** | تجاهل الزائد + تسجيل ملاحظة في سجل الإدارة |
| **لا تقييمات** | إخفاء "الأعلى تقييماً" |
| **لا خبر مرتبط** | إخفاء القسم |

---

## 🏷️ Slugs والأسماء النهائية

### 📝 المعرفات الأساسية

| النوع | القيم |
|-------|-------|
| **CPT** | `games` |
| **التصنيفات** | `game_type`, `game_status`, `game_mode`, `game_platform` |

### 🔑 مفاتيح الحقول المخصصة

#### الحقول الأساسية
- `mcp_official_site`, `mcp_developer`, `mcp_publisher`, `mcp_release_date`

#### المحرك
- `mcp_engine` بقيم: `unreal_engine|unity|cryengine|frostbite|custom`

#### الميزات
- `mcp_feature_1`, `mcp_feature_2`, `mcp_feature_3`, `mcp_feature_4`

#### الوسائط
- `mcp_trailer_youtube_1`, `mcp_trailer_youtube_2`
- `mcp_gallery`

#### التقييمات
- `mcp_rating_story`, `mcp_rating_story_note`
- `mcp_rating_gameplay`, `mcp_rating_gameplay_note`
- `mcp_rating_graphics`, `mcp_rating_graphics_note`
- `mcp_rating_audio`, `mcp_rating_audio_note`
- `mcp_rating_overall`, `mcp_rating_overall_note`

#### المقالات المرتبطة
- `mcp_related_game_id`

---

## 🔗 الهوكات الرئيسية

### 🎯 نقاط الربط الأساسية

| الوظيفة | الهوك |
|---------|-------|
| **التسجيل** | `init` |
| **الأصول** | `wp_enqueue_scripts`, `admin_enqueue_scripts` |
| **Ajax** | `wp_ajax_mcp_filter_games`, `wp_ajax_nopriv_mcp_filter_games` |
| **القوالب** | `template_include` أو فلاتر ملائمة |
| **الإعدادات** | `admin_menu`, `admin_init` |
| **REST API** | `rest_api_init` |

---

## 🚀 سير التنفيذ المقترح

### 📋 خطة التطوير المرحلية

1. **🔧 Bootstrap** - autoloader + init + فحص PHP وWP
2. **🔗 Permalinks** - تسجيل CPT/Tax + flush عند التفعيل فقط
3. **📝 Meta** - registry ثم validation ثم save
4. **⚙️ Settings/Terms** - صفحة إعدادات + زر توليد المصطلحات وخيارات الوصف
5. **🎨 Templates** - single/archive + parts
6. **📦 Assets** - ربط تحميل مشروط حسب السياق
7. **🔍 Ajax Filter** - استعلامات + تحديث URL
8. **📝 Shortcodes & Widgets** - تنفيذ الشورتكود والودجات
9. **🔗 Related Posts** - حقل المقال + عرض الخبر في صفحة اللعبة
10. **🔌 REST API** - المسارات games وtaxonomies
11. **⚡ Performance** - cache/images
12. **🛡️ Security** - nonces + capabilities
13. **🧪 Tests** - وحدات أساسية للتحقق من التحقق وREST
14. **📚 Documentation** - CHANGELOG وreadme.txt

#### 🧪 حالات اختبار مختارة
- ✅ **REST حواف**: per_page>50 (يجب أن يُقصّ إلى 50)
- ✅ **slug غير موجود**: فلتر تصنيف بslug غير صالح (يجب إرجاع خطأ)
- ✅ **حفظ ميتا غير صالح**: rating خارج 1–10 (يجب رفضه وعدم الحفظ)

---

## 📋 سياسة الإصدارات

### 🏷️ نظام SemVer

**التنسيق:** `MAJOR.MINOR.PATCH`

### 📝 التوثيق

- 📖 **توثيق كل تغيير** في `CHANGELOG.md`
- ✅ **"Tested up to"** محدث حسب نسخة ووردبريس

---

## 🔒 الخصوصية وحماية البيانات

### 📋 سياسة البيانات الشخصية

- ✅ **لا تجمع الإضافة بيانات شخصية**: تخزّن فقط ميتاداتا للألعاب داخل قاعدة بيانات ووردبريس
- ✅ **البيانات المحفوظة**: معلومات الألعاب، التقييمات، والإعدادات فقط
- ✅ **لا تتبع خارجي**: لا إرسال بيانات لخوادم خارجية
- ✅ **متوافق مع GDPR**: لا معالجة للبيانات الشخصية للمستخدمين

---

## 📥 التثبيت والإعداد

### ⚡ التثبيت السريع
1. **تحميل**: احصل على آخر إصدار من [GitHub Releases](https://github.com/momarabdev/momarab-core/releases)
2. **الرفع**: ارفع مجلد `momarab-core` إلى `/wp-content/plugins/`
3. **التفعيل**: فعّل الإضافة من لوحة تحكم ووردبريس
4. **الإعداد**: اذهب إلى **MOMARAB CORE → إعدادات** وأضف المصطلحات الأساسية

### 🔄 التحديث
- **تلقائي**: عبر لوحة تحكم ووردبريس (عند النشر في المتجر)
- **يدوي**: استبدل مجلد الإضافة بالإصدار الجديد مع الحفاظ على الإعدادات

### 🗑️ إزالة التثبيت
1. **إلغاء التفعيل**: من لوحة الإضافات
2. **الحذف**: احذف الإضافة (سيتم حذف الإعدادات تلقائياً)
3. **التنظيف**: البيانات والصور تبقى محفوظة في قاعدة البيانات

---

## 🚀 الاستخدام السريع

### 📝 الشورتكود

#### عرض الألعاب
```php
// عرض أفضل 6 ألعاب
[momarab_games limit="6" order="toprated"]

// عرض ألعاب من نوع معين
[momarab_games type="mmorpg" limit="8"]

// عرض الأحدث مع فلترة متعددة
[momarab_games order="newest" status="released" platform="pc"]
```

#### واجهة الفلترة
```php
// فلترة Ajax للأرشيف
[momarab_game_filter]
```

### 🔌 REST API

#### الحصول على قائمة الألعاب
```bash
# الطلب
GET /wp-json/momarab/v1/games?per_page=10&order=toprated

# الاستجابة
{
  "games": [
    {
      "id": 123,
      "title": "لعبة رائعة",
      "link": "https://site.com/games/great-game/",
      "featured_image": "https://site.com/wp-content/uploads/game.jpg",
      "ratings": {
        "overall": 8.5,
        "graphics": 9,
        "gameplay": 8
      },
      "taxonomies": {
        "game_type": ["mmorpg"],
        "game_status": ["released"]
      }
    }
  ],
  "total": 50,
  "pages": 5
}
```

#### الحصول على التصنيفات
```bash
# الطلب
GET /wp-json/momarab/v1/taxonomies

# الاستجابة
{
  "game_type": [
    {"id": 1, "name": "MMORPG", "slug": "mmorpg"},
    {"id": 2, "name": "Battle Royale", "slug": "battle-royale"}
  ],
  "game_status": [
    {"id": 3, "name": "مُصدر", "slug": "released"},
    {"id": 4, "name": "قريباً", "slug": "coming-soon"}
  ]
}
```

---

## 🤝 الدعم والمساهمة

### 🐛 الإبلاغ عن المشاكل
- **GitHub Issues**: [إنشاء مشكلة جديدة](https://github.com/momarabdev/momarab-core/issues/new)
- **الدعم**: [منتدى الدعم](https://momarab.com/support)
- **التوثيق**: [دليل المستخدم الكامل](https://docs.momarab.com)

### 💡 المساهمة
1. **Fork** المستودع
2. إنشاء **فرع جديد** للميزة: `git checkout -b feature/amazing-feature`
3. **Commit** التغييرات: `git commit -m 'Add amazing feature'`
4. **Push** للفرع: `git push origin feature/amazing-feature`
5. إنشاء **Pull Request**

### 📋 إرشادات المساهمة
- اتبع [WordPress Coding Standards](https://developer.wordpress.org/coding-standards/)
- راجع [قائمة مراجعة التنفيذ](./IMPLEMENTATION_CHECKLIST.md) قبل إرسال PR
- اكتب اختبارات للميزات الجديدة
- حدّث التوثيق عند الحاجة

---

## 📜 الترخيص

هذا المشروع مرخص تحت **GPLv2 أو أحدث** - راجع ملف [LICENSE](./LICENSE) للتفاصيل.

```
Copyright (C) 2025 MOMARAB Development Team

This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.
```

---

## 🛠️ التطوير

### للمطورين
- **قائمة مراجعة التنفيذ**: [IMPLEMENTATION_CHECKLIST.md](./IMPLEMENTATION_CHECKLIST.md)
- **معايير الكود**: راجع `phpcs.xml` للمعايير المطلوبة (testVersion 7.4–8.3)
- **الاختبارات**: تشغيل `composer test` للاختبارات الكاملة
- **CI/CD**: GitHub Actions يختبر تلقائياً على PHP 7.4-8.3 و WP 6.0-6.6

### 🚪 بوابة الإصدار (Release Gate)

**⚠️ متطلبات إجبارية قبل النشر:**

- ✅ **Sync الإصدارات مكتمل**: Version = Stable tag = MCP_VERSION
- ✅ **i18n كامل**: POT/PO/MO + JSON files للـ JavaScript
- ✅ **REST tests تمر**: per_page cap + order validation
- ✅ **PHPCS بلا أخطاء**: WordPress Coding Standards
- ✅ **أداء أرشيف < 2s**: قياس سرعة التحميل
- ✅ **تغطية ≥ 80%**: PHPUnit test coverage

### 🔧 أوامر التحقق السريعة (Smoke Commands)

```bash
# فحص per_page cap
curl -sS "https://dev.momarab.local/wp-json/momarab/v1/games?per_page=999" | jq 'length'

# فحص order validation  
curl -sS "https://dev.momarab.local/wp-json/momarab/v1/games?order=invalid" | jq '.code'

# فحص CPT registration
wp post type get games --path=/var/www/html

# فحص PHPCS
phpcs --standard=WordPress --extensions=php .

# فحص أداء الأرشيف
curl -w "@curl-format.txt" -o /dev/null -s "https://dev.momarab.local/games/"
```

---

<div align="center">

### 🎮 **MOMARAB CORE**
**إضافة ووردبريس متخصصة لألعاب MMO العربية**

*صُنع بـ ❤️ للمجتمع العربي*

[![GitHub](https://img.shields.io/badge/GitHub-momarabdev/momarab--core-blue?logo=github)](https://github.com/momarabdev/momarab-core)
[![License](https://img.shields.io/badge/License-GPLv2+-green)](./LICENSE)
[![WordPress](https://img.shields.io/badge/WordPress-6.0+-blue?logo=wordpress)](https://wordpress.org)
[![PHP](https://img.shields.io/badge/PHP-7.4+-purple?logo=php)](https://php.net)

</div>