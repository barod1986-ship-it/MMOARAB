# 🎮 MOMARAB CORE - قائمة مراجعة التنفيذ

## 📊 بيانات رأسية
- **الإصدار الجاري**: 1.0.0
- **الفرع**: release/1.0.0  
- **تاريخ الهدف**: 2025-02-28
- **المالك**: @developer
- **المراجع**: @reviewer
- **آخر تحديث**: 2025-09-22

---

## ✅ قائمة المراجعة الشاملة للتنفيذ

> **ملاحظة**: استخدم ✅ للمكتمل، ❌ للفاشل، 🟡 للقيد التنفيذ

### 🔄 1. تزامن الإصدارات

| البند | الحالة | الدليل/PR/Screen |
|-------|--------|------------------|
| **MCP_VERSION** في `momarab-core.php` = `1.0.0` | 🟡 | PR #101 |
| **Version** في رأس الإضافة = `1.0.0` | 🟡 | PR #101 |
| **Stable tag** في `readme.txt` = `1.0.0` | 🟡 | PR #101 |
| **تحقق**: جميع القيم متطابقة تماماً | ❌ | - |

### 🌐 2. i18n مكتمل
- [ ] **POT File**: `languages/momarab-core.pot` محدث ومولد
- [ ] **Arabic Files**: `momarab-core-ar.po` و `momarab-core-ar.mo` موجودان
- [ ] **load_plugin_textdomain()**: مُستدعى في `init` hook
- [ ] **wp_set_script_translations()**: مربوط لكل سكربت له نصوص
- [ ] **Text Domain**: `momarab-core` في جميع `__()` و `_e()`

### 📝 3. رأس الإضافة وreadme.txt
#### رأس الإضافة (`momarab-core.php`)
- [ ] Plugin Name: MOMARAB CORE
- [ ] Plugin URI: [URL]
- [ ] Description: [وصف بالعربية]
- [ ] Version: 1.0.0
- [ ] Requires at least: 6.0
- [ ] Tested up to: 6.6
- [ ] Requires PHP: 7.4
- [ ] Author: [اسم المطور]
- [ ] Text Domain: momarab-core
- [ ] Domain Path: /languages

#### readme.txt
- [ ] Contributors: [username]
- [ ] Tags: mmo, games, arabic, rtl, blocksy
- [ ] Requires at least: 6.0
- [ ] Tested up to: 6.6
- [ ] Requires PHP: 7.4
- [ ] Stable tag: 1.0.0
- [ ] License: GPLv2 or later
- [ ] License URI: https://www.gnu.org/licenses/gpl-2.0.html
- [ ] **Screenshots section**: 3 لقطات شاشة موصوفة
- [ ] **FAQ section**: أسئلة شائعة
- [ ] **Changelog section**: سجل التغييرات

### 🔧 4. التسجيل وPermalinks
- [ ] **CPT Registration**: `register_post_type('games')` على `init`
- [ ] **Taxonomies Registration**: 4 تصنيفات على `init`
- [ ] **show_in_rest**: `true` للـ CPT والتصنيفات
- [ ] **flush_rewrite_rules()**: فقط في `register_activation_hook`
- [ ] **Deactivation**: `flush_rewrite_rules()` في `register_deactivation_hook`

### 📦 5. الأصول مع Versioning
- [ ] **CSS Enqueue**: مع `MCP_VERSION` كـ version parameter
- [ ] **JS Enqueue**: مع `MCP_VERSION` كـ version parameter
- [ ] **Conditional Loading**:
  - [ ] `front.css/js`: عالمي للواجهة
  - [ ] `archive-filter.js`: أرشيف games فقط
  - [ ] `single-media.js`: صفحة game مفردة فقط
  - [ ] `admin.css/js`: شاشات games والإعدادات فقط

### 🛡️ 6. الأمان والتعقيم
#### Nonces
- [ ] **mcp_meta_nonce**: في meta boxes وفحصه عند الحفظ
- [ ] **mcp_settings_nonce**: في صفحة الإعدادات
- [ ] **mcp_filter_nonce**: في Ajax filter

#### التعقيم والتهريب
- [ ] **sanitize_text_field()**: للنصوص البسيطة
- [ ] **esc_url_raw()**: لحقول URL عند الحفظ
- [ ] **wp_kses_post()**: للمحتوى المنسق
- [ ] **esc_html()**: للنصوص في القوالب
- [ ] **esc_attr()**: لخصائص HTML
- [ ] **esc_url()**: للروابط في القوالب

#### الصلاحيات
- [ ] **edit_post**: للحقول المخصصة
- [ ] **manage_options**: للإعدادات
- [ ] **manage_categories**: لإدارة المصطلحات

### 🔌 7. REST API
#### المعاملات والتحقق
- [ ] **per_page**: sanitize + validate (1-50)
- [ ] **order**: validate ضد قائمة محددة (newest/oldest/az/za/toprated)
- [ ] **search**: sanitize_text_field
- [ ] **taxonomies**: validate term existence
- [ ] **قص per_page**: أي قيمة > 50 تُقص إلى 50

#### CORS
- [ ] **Headers**: Access-Control-Allow-Origin للقراءة
- [ ] **Methods**: GET فقط، لا POST/PUT/DELETE
- [ ] **Domain Restriction**: حسب النطاقات المحددة

### ⚡ 8. الأداء والكاش
#### Transients
- [ ] **Archive Cache**: `mcp_archive_cache_{hash}`
- [ ] **Widget Cache**: `mcp_widget_popular_{limit}`, `mcp_widget_recent_{limit}`
- [ ] **Cache Duration**: 5-10 دقائق

#### تفريغ الكاش
- [ ] **Game Save/Update**: مسح جميع `mcp_*` transients
- [ ] **Post Status Change**: مسح الكاش عند تغيير الحالة
- [ ] **Term Save/Update/Delete**: مسح كاش الأرشيف والودجات
- [ ] **Settings Update**: مسح كاش الأخبار المرتبطة

#### أحجام الصور
- [ ] **mcp-card**: 600×338 مُعرف ومُسجل
- [ ] **mcp-thumb**: 300×170 مُعرف ومُسجل
 
### 🎨 9. القوالب والـ Override
- [ ] **locate_template()**: يعمل للـ override من القالب الإبن
- [ ] **Template Hierarchy**: single-games.php, archive-games.php
- [ ] **Parts**: templates/parts/ منظمة ومُهربة
- [ ] **RTL Support**: CSS يدعم direction: rtl
- [ ] **No External Fonts**: لا Google Fonts أو خطوط خارجية
- [ ] **Blocksy Integration**: وراثة الألوان والخطوط
- [ ] **CSS Prefix**: جميع الفئات مُسبوقة بـ `mcp-`

### 🧪 10. الاختبارات والدخان (Smoke Tests)

#### REST API Tests
- [ ] **Test 1**: `GET /wp-json/momarab/v1/games?per_page=999`
  - **Expected**: يُقص إلى 50 عنصر
- [ ] **Test 2**: `GET /wp-json/momarab/v1/games?order=foo`
  - **Expected**: خطأ 400 "Invalid order parameter"
- [ ] **Test 3**: `GET /wp-json/momarab/v1/games?type=nonexistent`
  - **Expected**: نتائج فارغة أو خطأ

#### Meta Validation Tests
- [ ] **Test 1**: حفظ rating = 15
  - **Expected**: رفض وعدم الحفظ
- [ ] **Test 2**: حفظ rating = 0
  - **Expected**: رفض وعدم الحفظ
- [ ] **Test 3**: حفظ rating = 5
  - **Expected**: حفظ ناجح

#### Ajax Filter Tests
- [ ] **Test 1**: طلب مع nonce صحيح
  - **Expected**: استجابة ناجحة
- [ ] **Test 2**: طلب مع nonce خاطئ
  - **Expected**: خطأ 403
- [ ] **Test 3**: تحديث URL
  - **Expected**: URL يتحدث بدون إعادة تحميل

#### واجهة المستخدم Tests
- [ ] **تباين الألوان**: فحص بأدوات الوصول
- [ ] **تسلسل العناوين**: H1 → H2 → H3 منطقي
- [ ] **تبويب لوحة المفاتيح**: Tab order صحيح
- [ ] **Console Errors**: لا أخطاء JS في الكونسول
- [ ] **Mobile Responsive**: يعمل على الشاشات الصغيرة

### 🌐 11. i18n/JS المتقدم
- [ ] **wp_set_script_translations()**: مفعّل لكل سكربت يُخرج نصوصاً
- [ ] **JSON Files**: ملفات JSON مولّدة (GlotPress/wp i18n make-json)
- [ ] **Script Translation**: `wp_set_script_translations( 'mcp-script', 'momarab-core', MCP_DIR . 'languages' )`

### 🔒 12. توحيد Nonces
- [ ] **Action Names**: ثابتة ومحددة لكل nonce
- [ ] **mcp_meta_nonce**: action = 'mcp_save_meta'
- [ ] **mcp_settings_nonce**: action = 'mcp_save_settings'  
- [ ] **mcp_filter_nonce**: action = 'mcp_ajax_filter'
- [ ] **check_ajax_referer()**: في جميع مسارات Ajax قبل الاستعلامات

### 📏 13. PHPCS وCoding Standards
- [ ] **ruleset.xml**: ملف تكوين WordPress Coding Standards
- [ ] **PHPCS Command**: `phpcs --standard=WordPress`
- [ ] **Code Quality**: جميع الملفات تمر فحص PHPCS
- [ ] **PSR-4 Compliance**: بنية الفئات متوافقة

### 🔄 14. CI/CD وGitHub Actions
- [ ] **Matrix Testing**: PHP 7.4/8.1/8.2/8.3 + WP 6.0/6.6
- [ ] **Lint Check**: فحص syntax errors
- [ ] **PHPCS**: فحص coding standards
- [ ] **PHPUnit**: تشغيل الاختبارات
- [ ] **Workflow File**: `.github/workflows/test.yml`

### 🧪 15. PHPUnit Setup
- [ ] **bootstrap.php**: ملف تهيئة الاختبارات
- [ ] **Test Data**: seed للبيانات الوهمية (CPT/Tax)
- [ ] **REST Tests**: اختبارات endpoints
- [ ] **Meta Tests**: اختبارات validation
- [ ] **Test Coverage**: تغطية شاملة للوظائف الأساسية

### 📦 16. wp_register_script/style المحسن
- [ ] **Dependencies**: jQuery, wp-i18n محددة صحيحاً
- [ ] **Conditional Loading**: `is_post_type_archive('games')` و `is_singular('games')`
- [ ] **Admin Screens**: `get_current_screen()` للتحقق من السياق
- [ ] **Block Editor**: عدم تحميل في المحرر إلا للـ CPT

### ♿ 17. A11y/Ajax المتقدم
- [ ] **Results Region**: `role="status"` أو `aria-live="polite"`
- [ ] **Skip Links**: زر "تخطي للفلاتر" 
- [ ] **Loading States**: مؤشرات تحميل واضحة
- [ ] **Error Messages**: رسائل خطأ مفهومة

### 🛡️ 18. Security Headers (اختياري)
- [ ] **X-Content-Type-Options**: nosniff
- [ ] **Referrer-Policy**: strict-origin-when-cross-origin
- [ ] **Content-Security-Policy**: إن لزم
- [ ] **Implementation**: عبر القالب أو خادم الويب

### 🎨 19. Template Override المحسن
- [ ] **Subfolder Path**: `locate_template(['momarab-core/single-games.php'])`
- [ ] **Fallback System**: مسار احتياطي للقوالب
- [ ] **Theme Compatibility**: لا تعارض مع قوالب أخرى
- [ ] **Override Testing**: اختبار النسخ من القالب الإبن

### 🔄 20. Assets Version Busting
- [ ] **MCP_VERSION**: في جميع `wp_enqueue_*`
- [ ] **Version Change**: يتغير مع كل إصدار
- [ ] **Cache Prevention**: منع الكاش القديم
- [ ] **Development Mode**: version = time() في التطوير

### 🖼️ 21. WordPress.org Assets
- [ ] **Banner**: `assets/banner-1544x500.png`
- [ ] **Icon**: `assets/icon-256x256.png`
- [ ] **Screenshots**: في مجلد assets للمتجر
- [ ] **Asset Guidelines**: متوافق مع معايير WordPress.org

### 🌐 22. CORS المحدود
- [ ] **GET Only**: ترويسات للقراءة فقط
- [ ] **Domain Allowlist**: قائمة محددة (ليس *)
- [ ] **Origin Validation**: فحص المصدر
- [ ] **Security**: لا write methods

### 🖼️ 23. الحالات الحدّية
- [ ] **Missing Featured Image**: عرض `assets/img/placeholder-game.jpg`
- [ ] **Archive Placeholder**: في صفحة الأرشيف
- [ ] **Single Placeholder**: في الصفحة المفردة
- [ ] **Image Fallback**: آلية احتياطية للصور

### 🔄 24. Regenerate Thumbnails
- [ ] **Size Definition**: بعد تعريف أحجام الصور
- [ ] **Admin Notice**: تنبيه لإعادة توليد المصغّرات
- [ ] **Batch Processing**: معالجة مجمعة للصور القديمة
- [ ] **Progress Indicator**: مؤشر تقدم العملية

### 🧩 25. Block Editor Compatibility
- [ ] **Screen Check**: `get_current_screen()` للتحقق من السياق
- [ ] **CPT Only**: تحميل الأصول للـ CPT فقط في المحرر
- [ ] **Editor Styles**: أنماط مخصصة للمحرر إن لزم
- [ ] **Block Support**: دعم الكتل المخصصة إن وُجدت

---

## 🎯 ملاحظات التنفيذ

### أولويات التنفيذ
1. **عالية**: تزامن الإصدارات، الأمان، REST API
2. **متوسطة**: الأداء، القوالب، i18n
3. **منخفضة**: الاختبارات، التوثيق

### نصائح التطوير
- استخدم `WP_DEBUG` أثناء التطوير
- اختبر على بيئات PHP مختلفة
- استخدم أدوات فحص الوصول
- اختبر مع بيانات حقيقية

---

## 🔧 أوامر التحقق السريعة

### REST API Tests
```bash
# فحص قص per_page (يجب ≤ 50)
curl -sS "https://dev.momarab.local/wp-json/momarab/v1/games?per_page=999" | jq 'length'

# فحص order validation (توقع HTTP 400 و .code = "invalid_param")
curl -sS "https://dev.momarab.local/wp-json/momarab/v1/games?order=invalid" | jq '.code'

# فحص taxonomies endpoint
curl -sS "https://dev.momarab.local/wp-json/momarab/v1/taxonomies" | jq 'keys'
```

> **متطلبات**: تثبيت `jq` على السيرفر/الماك: `brew install jq` أو `apt install jq`

### WP-CLI Tests
```bash
# فحص تسجيل CPT والتصنيفات
wp post type get games --path=/var/www/html
wp taxonomy list | grep -E 'game_(type|status|mode|platform)' --path=/var/www/html

# فحص الإعدادات
wp option get mcp_settings --path=/var/www/html

# فحص الترانزينتات
wp transient list | grep mcp_ --path=/var/www/html
```

> **متطلبات**: تمكين WP-CLI وربط مسار ووردبريس الصحيح

### Performance Tests
```bash
# فحص سرعة الأرشيف (يتطلب curl-format.txt)
curl -w "@curl-format.txt" -o /dev/null -s "https://dev.momarab.local/games/"

# فحص حجم الأصول
ls -lh assets/css/ assets/js/
```

---

## 📊 ماتريكس البيئة

| PHP | WP | النتيجة | الدليل |
|-----|----|---------|---------| 
| 7.4 | 6.0 | 🟡 | PR #102 |
| 8.1 | 6.4 | ❌ | Issue #103 |
| 8.2 | 6.6 | ✅ | PR #104 |
| 8.3 | 6.6 | 🟡 | Testing... |

---

## 🚪 بوابة الإصدار (Release Gate)

**⚠️ بدون هذه البنود، لا دمج للإصدار:**

| المتطلب | الحالة | ملاحظات |
|---------|--------|----------|
| ✅ كل بنود "عالية الأولوية" مكتملة | ❌ | 2/6 مكتمل |
| ✅ اختبارات REST/Meta/Ajax تمر | 🟡 | REST فقط |
| ✅ تزامن الإصدارات + readme.txt | ❌ | قيد المراجعة |
| ✅ أداء < 2s على صفحة الأرشيف | 🟡 | 1.8s حالياً |
| ✅ لا أخطاء PHPCS | ❌ | 12 خطأ |
| ✅ تغطية اختبارات > 80% | ❌ | 45% حالياً |

**الحالة العامة**: 🔴 **غير جاهز للإصدار**

---

## 🔗 ربط سير العمل

**للمطورين**: راجع هذا الملف قبل إنشاء PR وتأكد من اكتمال البنود ذات الأولوية العالية.

**للمراجعين**: استخدم Release Gate كمرجع لقبول أو رفض PRs.
