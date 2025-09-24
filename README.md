# 🎮 MOMARAB CORE 1.0 — README (نسخة شخصية نهائية)

نظام لإدارة وعرض ألعاب MMO بالعربية على ووردبريس. تكامل Blocksy. فلترة Ajax مع بديل GET. تقييم مُحرّر. تصويت زوار. خبر مرتبط واحد. **بدون متجر**. **بدون ملفات اختبار أو بيانات ديمو**. **للاستخدام الشخصي فقط**.

## المحتويات
- [0) ملاحظات تنفيذ سريعة](#0-ملاحظات-تنفيذ-سريعة)
- [1) المتطلبات](#1-المتطلبات)
- [2) التثبيت](#2-التثبيت)
- [3) الكيانات](#3-الكيانات)
- [4) الحقول Meta](#4-الحقول-meta)
- [5) الواجهة](#5-الواجهة)
- [6) التصويت](#6-التصويت)
- [7) REST API](#7-rest-api)
- [8) الكاش](#8-الكاش)
- [9) الأداء](#9-الأداء)
- [10) الترجمة](#10-الترجمة)
- [11) SEO وSchema](#11-seo-وschema)
- [12) الوصول وRTL](#12-الوصول-وrtl)
- [13) الأمان](#13-الأمان)
- [14) الأحجام والصور](#14-الأحجام-والصور)
- [15) القوالب](#15-القوالب)
- [16) الشورتكود والودجات](#16-الشورتكود-والودجات)
- [17) REST وAjax وGET توازي](#17-rest-وajax-وget-توازي)
- [18) Hooks للمطورين](#18-hooks-للمطورين)
- [19) قفل المصطلحات الأساسية](#19-قفل-المصطلحات-الأساسية)
- [20) التوافق](#20-التوافق)
- [21) إلغاء التثبيت](#21-إلغاء-التثبيت)
- [22) شجرة الملفات](#22-شجرة-الملفات)
- [23) اختبار القبول](#23-اختبار-القبول)
- [24) استكشاف الأخطاء](#24-استكشاف-الأخطاء)
- [25) Ajax actions وNonces](#25-ajax-actions-ونonces)
- [26) WP-CLI](#26-wp-cli)
- [27) صلاحيات CPT/TAX](#27-صلاحيات-cpttax)
- [28) معايير الشفرة وإصدار النسخة](#28-معايير-الشفرة-وإصدار-النسخة)
- [29) ملاحظات ترخيص ونطاق](#29-ملاحظات-ترخيص-ونطاق)

---

## 0) ملاحظات تنفيذ سريعة

- **PHP 7.4:** لا typed properties/returns. استخدم `private $prop` بدل `private string $prop`. لا `: void|int|array|float|bool` في توقيعات الدوال.
- **Handles:** `mcp-front`, `mcp-archive-filter`, `mcp-single-media`, `mcp-admin` مع `wp_set_script_translations()` للدومين `momarab-core`.
- **Capability:** اسم موحّد `manage_momarab_core` لكل شاشات الإضافة. تُمنح تلقائيًا لـ Administrator عند التفعيل.
- **Nonces:** `mcp_meta_nonce`, `mcp_settings_nonce`, `mcp_filter_nonce`, `mcp_votes_nonce`. اطبعها دائمًا عبر `wp_nonce_field()` في الشاشات والنماذج.
- **Limit مركزي:** أقصى 24 في REST والشورتكود وAjax والودجات.
- **كاش داخلي:** أرشيف/REST 10د، ودجات 15د، قوائم تصنيفات 60د. تفريغ عند حفظ/حذف/استرجاع لعبة أو مصطلح. Stampede protection.
- **صور:** `mcp-hero 1200×675`, `mcp-card 600×338`, `mcp-thumb 300×169`. Placeholder داخلي. تسجيل عند `after_setup_theme`.
- **YouTube Privacy:** ملصق محلي. التشغيل عند النقر. **قبول نطاق `youtube-nocookie.com` فقط** عند الحفظ.
- **الخطوط/الألوان:** وراثة Blocksy. لا Google Fonts. Typography = System Default.
- **إعادة الكتابة:** `flush_rewrite_rules()` **مرة واحدة** عند التفعيل فقط. لا Runtime.
- **إخفاء الإصدار:** لا تطبع `MCP_VERSION` في الواجهة.
- **فحص مبكر:** حارس متطلبات (PHP ≥ 7.4، WP ≥ 6.x). أوقف سكيما الإضافة إن وُجد Rank Math أو Yoast.
- **REST آمن:** قراءة فقط. `permission_callback => '__return_true'` مع Validate/Sanitize كامل. Allowlist CORS عبر فلتر موثّق.
- **Multisite:** ضمّن `get_current_blog_id()` داخل مفاتيح الكاش مع prefix ثابت `mcp_` لتفادي التعارض.
- **404 متقدمة:** طبّق الفحص عند `template_redirect` بعد تنفيذ الاستعلام لضمان دقة `$max_num_pages`.
- **Ajax nopriv:** سجّل أكشنات عامة لغير المسجلين للتصفية والتصويت.

---

## 1) المتطلبات

- WordPress 6.x
- PHP 7.4 أو 8.x (موصى 8.1+)
- قالب Blocksy مفعّل
- تعطيل Google Fonts في القالب وأي منشئ صفحات
- **لا تُدرج أي ملفات اختبار أو وسائط تجريبية داخل الإضافة**

---

## 2) التثبيت

1) ضع المجلد `momarab-core/` داخل `wp-content/plugins/`.  
2) فعّل الإضافة من لوحة التحكم.  
3) من شاشة الإعدادات اضغط “إنشاء المصطلحات الأساسية”.  
4) احفظ الإعدادات.  
5) تأكد من ظهور أرشيف `/games/`.

> لا تُوزّع مع الإضافة أي ملفات اختبار أو بيانات ديمو.

---

## 3) الكيانات

- **CPT:** `game` مع `rewrite slug=games` وأرشيف مفعّل.
- **تصنيفات:**
  - `game_type`, `game_status`, `game_mode`, `game_platform`
  - Slugs إنجليزية ثابتة وأسماء عربية.

**Seed Terms** (إنشاء برمجي فقط):  
- **game_type:** `mmorpg`, `mmo-arpg`, `mmofps`, `moba`, `mmorts`, `survival-mmo`, `sandbox-mmo`, `social-mmo`, `battle-royale`, `racing-mmo`, `sports-mmo`, `space-mmo`, `naval-mmo`, `anime-mmo`  
- **game_status:** `upcoming`, `alpha`, `beta`, `early-access`, `released`  
- **game_mode:** `pve`, `pvp`, `pvpve`, `open-world`, `co-op`  
- **game_platform:** `pc`, `playstation`, `xbox`, `nintendo-switch`, `mobile`, `browser`

زر “إنشاء المصطلحات الأساسية” يضيف البنود ويتخطى المكرر ويمكن قفلها.

---

## 4) الحقول (Meta)

- الأساسية: المطوّر، الناشر، تاريخ الإصدار، الموقع الرسمي (https)، المحرك.
- الوسائط: رابطا YouTube كحد أقصى، ومعرض حتى 6 صور.
- تقييم المُحرّر 1–10 بخطوة 0.5: Story, Gameplay, Graphics, Audio.
- Overall محسوب افتراضيًا: Gameplay 40%، Story 25%، Graphics 20%، Audio 15% (قابلة للتعديل بالفلتر).
- ملاحظة تحريرية ≤ 240 حرفًا.
- روابط اختيارية: Steam, PlayStation, Xbox, Discord.
- **ربط خبر:** اختيار **مقالة واحدة من نوع post** لتظهر كـ “آخر خبر” في صفحة اللعبة.

**قيود التحقق:** https فقط، عدد الصور ≤ 6، القيم ضمن [1,10] بخطوة 0.5، طول الملاحظة ≤ 240.

```php
// حفظ آمن مختصر
$dev  = sanitize_text_field( $_POST['mcp_developer'] ?? '' );
$url  = esc_url_raw( $_POST['mcp_official_site'] ?? '' );
if ( $url && 0 !== strpos( $url, 'https://' ) ) { $url = ''; }
$note = wp_kses_post( wp_strip_all_tags( $_POST['mcp_editor_note'] ?? '', true ) );

function mcp_is_half_step( $v ) { return abs( ($v*2) - round($v*2) ) < 0.0001; }

// قبول youtube-nocookie فقط
function mcp_allow_youtube_nocookie( $url ){
  $u = wp_parse_url( $url );
  return ( $u && isset($u['host']) && preg_match('~(^|\.)youtube-nocookie\.com$~i', $u['host']) ) ? $url : '';
}
```

---

## 5) الواجهة

**أرشيف `/games/`:**
- فلترة أفقية متعددة: النوع، الحالة، المنصّة، الوضع، والبحث.
- `sort`: `newest|oldest|az|za|toprated|mostliked`.
- Ajax مع تحديث URL وحفظ الحالة. يعمل بدون JS عبر GET بنفس المعايير. Empty state واضحة. عناصر الفلترة تطبع `wp_nonce_field('mcp_filter_nonce')`.

**صفحة اللعبة:**
- Hero + عنوان + شارات التصنيفات.
- معلومات أساسية → وسائط (YouTube Privacy + معرض) → تقييمات + ملاحظة → خبر واحد → Schema.
- صورة بارزة مطلوبة وإلا Placeholder داخلي.

**قوالب قابلة للـ override:**
- استخدم `locate_template( 'momarab-core/parts/...php' )` قبل تضمين `templates/`.

**أمثلة GET بدون JS:**
```
/games/?type=mmorpg&platform=pc&sort=toprated&page=2
/games/?status=released&mode=pve
```

**404 للأرشيف بعد تنفيذ الاستعلام:**
```php
add_action('template_redirect', function(){
  if ( is_post_type_archive('game') && is_main_query() ) {
    global $wp_query;
    $max   = max(1, (int) $wp_query->max_num_pages);
    $paged = max(1, (int) get_query_var('paged'));
    if ($paged > $max) { $wp_query->set_404(); status_header(404); }
  }
});
```

---

## 6) التصويت

- صوت واحد قابل للتبديل لكل لعبة. زائر عبر كوكي موقّعة. مستخدم عبر `user_meta`.
- تخزين موصى به: **جدول مخصص** `wp_mcp_votes(post_id, user_hash, vote, updated_at)` مع فهرس فريد `(post_id,user_hash)`، وتحديث عدّادات في post meta للتجميع.
- عرض `likes`, `dislikes`, و`ratio = likes / (likes+dislikes)`.
- ترتيب `mostliked = (likes - dislikes)` مع كسر تعادل بالـ ratio.
- Rate-limit: 1 فعل/15ث، 30 طلب/دقيقة/IP (و10 داخل wp-admin). لا حفظ IP طويل الأمد.
- توقيع الكوكي بـ `hash_hmac('sha256', $user_id_or_ip, wp_salt('auth'))`.

**إنشاء جدول التصويت + صلاحية + فلاش مرة واحدة:**
```php
register_activation_hook(__FILE__, function(){
  global $wpdb;
  $c = $wpdb->get_charset_collate();
  $t = $wpdb->prefix . 'mcp_votes';
  $sql = "CREATE TABLE IF NOT EXISTS `$t` (
    post_id BIGINT UNSIGNED NOT NULL,
    user_hash VARBINARY(64) NOT NULL,
    vote TINYINT NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uniq (post_id,user_hash),
    KEY post_id (post_id)
  ) $c;";
  require_once ABSPATH.'wp-admin/includes/upgrade.php';
  dbDelta($sql);


});
```

```php
// طبقة Rate-limit موحّدة + تنظيف قفل
class MCP_RateLimit {
  public static function allow( $key, $window = 60, $max = 30 ) {
    $k = 'mcp_rl_' . md5( $key );
    $d = get_transient( $k );
    if ( ! is_array( $d ) ) { $d = ['c'=>0,'t'=>time()]; }
    if ( time() - $d['t'] > $window ) { $d = ['c'=>0,'t'=>time()]; }
    if ( $d['c'] >= $max ) { return false; }
    $d['c']++;
    set_transient( $k, $d, $window );
    return true;
  }
}
```
**Cooldown 15s لكل تصويت (مثال تطبيقي):**
```php
function mcp_vote_cooldown_ok( $user_hash, $post_id ){
  $k = 'mcp_vc_' . md5( $user_hash . '|' . $post_id );
  if ( get_transient( $k ) ) return false; // خلال 15 ثانية
  set_transient( $k, 1, 15 ); // 15 ثانية تبريد
  return true;
}
// داخل أكشن التصويت: تحقّق من MCP_RateLimit::allow(...) ثم mcp_vote_cooldown_ok(...)
```


---

## 7) REST API

- Namespace: `momarab/v1`
- المسارات: `/games`, `/taxonomies`
- المعاملات: `per_page, page, search, type, status, platform, mode, sort`
- حد `per_page`: أقصى 24
- sort: `newest, oldest, az, za, toprated, mostliked`
- قراءة فقط. Sanitize/Validate لكل المعاملات. رسائل عربية موحّدة.

```php
register_rest_route('momarab/v1','/games',[
  'methods'  => 'GET',
  'callback' => 'mcp_rest_games',
  'permission_callback' => '__return_true',
  'args' => [
    'per_page'=>[
      'sanitize_callback'=>function($v){ return mcp_clamp_limit( absint($v), 24 ); },
      'validate_callback'=>function($v){ $v=absint($v); return $v>0 && $v<=24; },
    ],
    'page'=>[
      'sanitize_callback'=>function($v){ $v=absint($v); return $v>0 ? $v : 1; },
      'validate_callback'=>function($v){ return absint($v) >= 1; },
    ],
    'search'=>[
      'sanitize_callback'=>function($v){ $v=wp_strip_all_tags((string)$v); return mb_substr($v,0,80); },
      'validate_callback'=>function($v){ return is_string($v) && mb_strlen($v) <= 80; },
    ],
    'type'=>[
      'sanitize_callback'=>function($v){ return array_map('sanitize_key',(array)$v); },
    ],
    'status'=>[
      'sanitize_callback'=>function($v){ return array_map('sanitize_key',(array)$v); },
      'validate_callback'=>function($v){
        $allowed=['upcoming','alpha','beta','early-access','released'];
        foreach((array)$v as $x){ if(!in_array(sanitize_key($x),$allowed,true)) return false; } return true;
      },
    ],
    'platform'=>[
      'sanitize_callback'=>function($v){ return array_map('sanitize_key',(array)$v); },
      'validate_callback'=>function($v){
        $allowed=['pc','playstation','xbox','nintendo-switch','mobile','browser'];
        foreach((array)$v as $x){ if(!in_array(sanitize_key($x),$allowed,true)) return false; } return true;
      },
    ],
    'mode'=>[
      'sanitize_callback'=>function($v){ return array_map('sanitize_key',(array)$v); },
      'validate_callback'=>function($v){
        $allowed=['pve','pvp','pvpve','open-world','co-op'];
        foreach((array)$v as $x){ if(!in_array(sanitize_key($x),$allowed,true)) return false; } return true;
      },
    ],
    'sort'=>[
      'sanitize_callback'=>function($v){ $v=sanitize_key($v); return in_array($v,['newest','oldest','az','za','toprated','mostliked'],true)?$v:'newest'; },
    ],
  ],
]);
```

**Allowlist CORS (اختياري وموثّق مع OPTIONS):**
```php
add_action('rest_api_init', function(){
  add_filter('rest_send_cors_headers', function($value){
    $allowed = apply_filters('mcp_rest_cors_allow', []);
    if (!empty($allowed)) {
      $origin = $_SERVER['HTTP_ORIGIN'] ?? '';
      if (in_array($origin, $allowed, true)) {
        header('Access-Control-Allow-Origin: '.$origin);
        header('Vary: Origin');
        header('Access-Control-Allow-Methods: GET, OPTIONS');
        header('Access-Control-Allow-Headers: Authorization, Content-Type');
      }
    }
    return $value;
  }, 11);
});
```

**استجابة مثال:**
```json
{
  "page": 1,
  "per_page": 12,
  "total": 120,
  "results": [
    { "id": 123, "title": "Game Title", "slug": "game-title",
      "types": ["mmorpg"], "platforms": ["pc"],
      "rating": { "overall": 8.5 } }
  ]
}
```

**قصّ حد مركزي:**
```php
function mcp_clamp_limit( $val, $max = 24 ) {
  $n = (int) $val;
  return ( $n > 0 && $n <= $max ) ? $n : $max;
}
```

---

## 8) الكاش

- يكاشي: نتائج الفلترة، الودجات، قوائم التصنيفات، ردود REST الشائعة.
- TTL: أرشيف/REST 10د، ودجات 15د، تصنيفات 60د.
- تفريغ ذكي عند حفظ/تحديث/حذف/استرجاع لعبة أو مصطلح.
- Stampede protection بقفل خفيف مع تنظيف آمن.

```php
$ns  = 'mcp_' . 'c_' . get_current_blog_id() . '_';
$key = $ns . $segment . '_' . md5( wp_json_encode( $hash_input ) );

$lock_key = $key . '_lock';
if ( get_transient($lock_key) ) { return get_transient($key); }
set_transient($lock_key, 1, 30);
// احذف واحدًا من تنظيفات القفل (إما هنا أو عبر shutdown)
register_shutdown_function(function() use ($lock_key){ delete_transient($lock_key); });

// build cache...
```

**CRON تنظيف:** كل 6 ساعات. إزالة التسجيل عند التعطيل.
```php
add_filter('cron_schedules', function($s){
  $s['every_six_hours'] = ['interval'=>21600,'display'=>'Every 6 Hours'];
  return $s;
});
register_activation_hook(__FILE__, function(){
  if ( ! wp_next_scheduled('mcp_cache_cleanup') ) {
    wp_schedule_event( time()+300, 'every_six_hours', 'mcp_cache_cleanup' );
  }
});
register_deactivation_hook(__FILE__, function(){
  $ts = wp_next_scheduled('mcp_cache_cleanup');
  if ( $ts ) wp_unschedule_event( $ts, 'mcp_cache_cleanup' );
});
```

**تفريغ الأحداث:**
```
save_post_game, clean_post_cache, deleted_post, trashed_post, untrashed_post,
created_term, edited_term, set_object_terms, delete_term, deleted_term
```

---

## 9) الأداء

- CWV: LCP ≤ 2.5s، CLS ≤ 0.05، INP ≤ 200ms.
- Lazy images + `srcset` + `width/height` ثابتان و`decoding="async"`.
- عدم تحميل YouTube حتى النقر.
- **تحميل الأصول دائمًا** على صفحات `game`، وتكاملات Blocksy اختيارية فقط.
- خارج صفحات `game`: ≤ 20KB CSS و≤ 20KB JS مضغوطين.
- عند غياب Blocksy: **تظل القوالب تعمل**. اجعل شرط Blocksy داخل تكاملات اختيارية فقط.

```php
add_action('wp_enqueue_scripts', function(){
  $is_game = is_singular('game') || is_post_type_archive('game');
  if ( $is_game ) {
    // enqueue + wp_set_script_translations(...)
  }
  if ( function_exists('blocksy_manager') && $is_game ) {
    // تكاملات Blocksy الاختيارية فقط
  }
}, 20);
```

---

## 10) الترجمة

- Text Domain: `momarab-core`
- PHP: `.po/.mo`
- JS: JSON عبر `wp_set_script_translations()` لنفس الـ handles
- لفّ كل نصوص JS بـ `wp.i18n.__('text','momarab-core')`
- أضف `wp-i18n` كـ dependency عند التسجيل.
- تحميل مبكر:
```php
load_plugin_textdomain('momarab-core', false, dirname(plugin_basename(__FILE__)).'/languages');
```

**نصوص دنيا لازمة:** “جاري التحميل…“، “لا نتائج”، “حدث خطأ. يرجى المحاولة لاحقًا.” + سطر سياسة كوكي للتصويت “سيتم تخزين اختيارك محليًا لتحسين التجربة.”

**أوامر:**
```bash
wp i18n make-pot . languages/momarab-core.pot --slug=momarab-core
wp i18n make-json languages --no-purge
```

---

## 11) SEO وSchema

- يطبع: `Game` + `AggregateRating` من تقييم المُحرّر فقط. `VideoObject` عند وجود فيديو.
- أرشيف مفلتر: canonical إلى `/games/` بدون باراميترات. أضف `rel="next/prev"` للصفحات المرقّمة.
- افتراضيًا: `add_filter('mcp_schema_enabled','__return_true')`. إذا Rank Math أو Yoast فعّالان عطّل مبكرًا.

```php
add_action('plugins_loaded', function(){
  if ( defined('RANK_MATH_VERSION') || class_exists('RankMath') || defined('WPSEO_VERSION') ) {
    add_filter('mcp_schema_enabled', '__return_false');
  }
}, 5);
```

---

## 12) الوصول وRTL

- عناصر الفلترة قابلة للتنقل بالكيبورد. `aria-live="polite"` للتحديثات.
- بعد تحديث Ajax انقل التركيز لأول عنصر نتيجة وأعلن في `role="status"`.
- تباين ≥ 4.5:1. RTL كامل.

```js
resultsEl.setAttribute('aria-busy','false');
const first = resultsEl.querySelector('[data-card]');
if (first) first.focus();
```

---

## 13) الأمان

- تحقق Nonces في كل POST/Ajax: `check_admin_referer` و`check_ajax_referer`.
- قدرات: كل الشاشات تتطلب `manage_momarab_core`.
- REST CORS مغلق افتراضيًا. Allowlist اختياري عبر فلتر الإضافة.
- لا حفظ IP طويل الأمد. كوكي التصويت موقّعة.
- لا طباعة الإصدار في الواجهة.
- **سلامة الإخراج:** استخدم `esc_html`, `esc_attr`, `esc_url`, `wp_kses_post` قبل الطباعة في القوالب.

```php
register_activation_hook( __FILE__, function(){
  if ( $role = get_role('administrator') ) { $role->add_cap('manage_momarab_core'); }
  flush_rewrite_rules();
});
/* No flush on deactivation to avoid runtime rewrites. */
```

---

## 14) الأحجام والصور

- `mcp-hero 1200x675`
- `mcp-card 600x338`
- `mcp-thumb 300x169`
- WebP إن توفر. قص مركزي. Placeholder مع `srcset` لتفادي CLS.

```php
add_action('after_setup_theme', function(){
  add_image_size('mcp-hero', 1200, 675, true);
  add_image_size('mcp-card', 600, 338, true);
  add_image_size('mcp-thumb', 300, 169, true);
});
```

> تشغيل موصى به بعد التفعيل: **Regenerate Thumbnails**.

---

## 15) القوالب

- `templates/single-game.php`, `archive-game.php`, و`templates/parts/*`
- قبل تضمين أي جزء استخدم `locate_template()` للسماح للثيم بالاستبدال.

---

## 16) الشورتكود والودجات

**شورتكود:**
```
[momarab_games limit="12" sort="toprated"]
[momarab_games type="mmorpg" platform="pc" sort="mostliked" limit="8"]
```
`limit` يُقصّ إلى 24.

**ودجات:**
- Popular: حسب التقييم ثم الأحدث
- Recent: حسب التاريخ
- الحد 24

**شريط فلترة:**
```
[momarab_game_filter]
```

---

## 17) REST وAjax وGET توازي

- نفس معايير الفلترة تُستخدم في: WP_Query للأرشيف، REST، Ajax، والشورتكود.
- الترتيب `mostliked` يحسب `likes - dislikes` مع كسر التعادل بالـ ratio.
- قصّ `paged` داخل `[1, max_pages]`، وإن تجاوزت الطلبات الحد ارجع 404.

```php
// فلتر مركزي لمعطيات الاستعلام
apply_filters( 'mcp_games_query_args', $args );
```

---

## 18) Hooks للمطورين

- `mcp_ratings_weights` تعديل أوزان التقييم
- `mcp_games_query_args` فلترة باراميترات الاستعلام
- `mcp_votes_user_can` التحكم بمن يحق له التصويت
- `mcp_assets_should_enqueue` التحكم بتحميل الأصول
- `mcp_cache_ttl` تعديل TTL لأنواع الكاش
- `mcp_sort_mostliked_tiebreaker` كسر التعادل
- `mcp_votes_ratelimit_window`, `mcp_votes_ratelimit_max` تخصيص سياسات الحد
- `mcp_cache_key` لتعديل مفاتيح التخزين المؤقت

```php
add_filter('mcp_ratings_weights', function($w){
  return ['gameplay'=>0.4,'story'=>0.25,'graphics'=>0.2,'audio'=>0.15];
});
```

---

## 19) قفل المصطلحات الأساسية

منع حذف أو تغيير slug للمصطلحات المقفلة.

```php
function mcp_locked_terms(){
  return ['mmorpg','mmo-arpg','mmofps','moba','mmorts','survival-mmo','sandbox-mmo','social-mmo','battle-royale','racing-mmo','sports-mmo','space-mmo','naval-mmo','anime-mmo'];
}

add_filter('pre_delete_term', function($allow, $term, $tt_id, $tax){
  $slug = is_object($term) ? $term->slug : get_term_field('slug', $term, $tax);
  if ( in_array($slug, mcp_locked_terms(), true) ) {
    return new WP_Error('mcp_locked_term', __('This term is locked and cannot be deleted.','momarab-core'));
  }
  return $allow;
}, 10, 4);

add_filter('wp_update_term_data', function($data, $term_id, $taxonomy){
  $t = get_term($term_id, $taxonomy);
  if ($t && in_array($t->slug, mcp_locked_terms(), true)) {
    $data['slug'] = $t->slug; // قفل الـ slug فقط
  }
  return $data;
}, 10, 3);
```

---

## 20) التوافق

- يعمل داخل Elementor Preview.
- خرائط الموقع وBreadcrumbs عبر القالب أو Rank Math.
- لا خطوط خارجية. وراثة Blocksy كاملة.
- إن لم يكن Blocksy نشطًا: عطّل التكاملات الخاصة به فقط، واستمر بالقوالب والأصول الأساسية.

---

## 21) إلغاء التثبيت

- الإزالة عبر `uninstall.php` تحذف الإعدادات والكاش فقط.
- لا تُحذف ألعاب `game` ولا المصطلحات.
- لا تُنشئ الإضافة أي ملفات اختبار أو وسائط ديمو عند التثبيت.

**uninstall.php مثال (تصحيح LIKE):**
```php
if ( ! defined( 'WP_UNINSTALL_PLUGIN' ) ) exit;
delete_option('mcp_options');
global $wpdb;
$like = $wpdb->esc_like('mcp_c_') . '%';
$wpdb->query( $wpdb->prepare(
  "DELETE FROM {$wpdb->options} WHERE option_name LIKE %s", $like
));
```

---

## 22) شجرة الملفات

```
momarab-core/
├─ momarab-core.php
├─ uninstall.php
├─ README.md
├─ CHANGELOG.md
├─ languages/
├─ assets/
│  ├─ css/ (front.css, front-archive.css, front-single.css, admin.css)
│  ├─ js/  (front.js, archive-filter.js, single-media.js, admin.js)
│  └─ img/ (placeholder-game.jpg)
├─ includes/
│  ├─ bootstrap/ (class-mcp-autoloader.php, class-mcp-init.php)
│  ├─ core/      (class-mcp-assets.php, class-mcp-templates.php, class-mcp-permalinks.php, helpers.php)
│  ├─ content/   (class-mcp-cpt.php, class-mcp-taxonomies.php, meta/*)
│  ├─ settings/  (class-mcp-settings.php, class-mcp-terms-manager.php, views/*)
│  ├─ dashboard/ (class-mcp-dashboard.php, views/dashboard.php)
│  ├─ features/
│  │  ├─ ajax/class-mcp-ajax-filter.php
│  │  ├─ votes/* (controller, storage, render)
│  │  ├─ shortcodes/* ([momarab_games], [momarab_game_filter])
│  │  ├─ widgets/* (popular, recent)
│  │  ├─ related/* (meta+render)
│  │  └─ rest/*   (controller, games, taxonomies)
│  ├─ security/   (class-mcp-nonce.php, class-mcp-capabilities.php)
│  └─ performance/(class-mcp-cache.php, class-mcp-images.php)
└─ templates/
   ├─ single-game.php
   ├─ archive-game.php
   └─ parts/ (header-card.php, game-basics.php, game-media.php, game-ratings.php, votes-bar.php, related-news.php)
```

---

## 23) اختبار القبول

1) التفعيل بلا تحذيرات PHP 7.4.  
2) زر المصطلحات يملأ seed دون تكرار.  
3) إضافة لعبة كاملة الحقول وصورة بارزة. Overall صحيح.  
4) `/games/` يعمل. الفلترة تحفظ الحالة وتحدّث URL. بدون JS تعمل عبر GET.  
5) التصويت يبدّل الصوت ويحدّث العدّادات مع Rate-limit وتوقيع كوكي.  
6) REST يرجع نتائج ضمن الحد وكاش 10د. CORS مغلق افتراضيًا.  
7) لا خطوط خارجية. وراثة Blocksy. CLS ≤ 0.05.  
8) تجاوز `paged` يُرجع 404 صحيحة.  
9) تعطيل الإضافة لا يحذف المحتوى. `uninstall` يحذف الإعدادات والكاش فقط.  
10) REST عند معاملات غير صالحة يعيد **400** برسالة عربية موحّدة.  
11) **لا يتم تثبيت أي ملفات اختبار أو وسائط ديمو ضمن الإضافة.**

---

## 24) استكشاف الأخطاء

- **Typed properties/returns:** أزل كل الأنواع في جميع الملفات.  
- **قصّ الحد:** استخدم `mcp_clamp_limit()` في REST وAjax والشورتكود والودجات.  
- **أصول صفحات game:** حمّل الأصول دائمًا على صفحات `game`. اجعل تكامل Blocksy اختياريًا.  
- **ازدواج Schema:** أوقف مبكرًا قبل الطباعة عند وجود Rank Math/Yoast.  
- **كاش لا يُفرّغ:** اربط التفريغ مع:
  ```
  save_post_game, clean_post_cache, deleted_post, trashed_post, untrashed_post,
  created_term, edited_term, set_object_terms, delete_term, deleted_term
  ```
- **CORS:** افتح Allowlist فقط عند الحاجة عبر فلتر الإضافة.
- **404 خارج النطاق:** تأكد من تنفيذ فحص 404 في `template_redirect` بعد الاستعلام.

---

## 25) Ajax actions وNonces

| Action              | Nonce               | Capability             | Rate-limit        |
|---------------------|---------------------|------------------------|-------------------|
| `mcp_filter_games`  | `mcp_filter_nonce`  | `read`                 | 30/دقيقة/IP       |
| `mcp_toggle_vote`   | `mcp_votes_nonce`   | `read`                 | 30/دقيقة/IP       |
| `mcp_seed_terms`    | `mcp_settings_nonce`| `manage_momarab_core`  | 10/دقيقة/IP       |
| `mcp_clear_cache`   | `mcp_settings_nonce`| `manage_momarab_core`  | 10/دقيقة/IP       |

**تسجيل nopriv للأكشنات العامة والتحقق من nonce الافتراضي `_wpnonce`:**
```php
add_action('wp_ajax_mcp_filter_games','mcp_filter_games');
add_action('wp_ajax_nopriv_mcp_filter_games','mcp_filter_games');
add_action('wp_ajax_mcp_toggle_vote','mcp_toggle_vote');
add_action('wp_ajax_nopriv_mcp_toggle_vote','mcp_toggle_vote');

// مثال تحقق
check_ajax_referer('mcp_filter_nonce','_wpnonce');
```

---

## 26) WP-CLI (اختياري)

سجّل الأمر ثم الأوامر:

```php
if ( defined('WP_CLI') && WP_CLI ) {
  WP_CLI::add_command('momarab', 'MCP_CLI_Commands');
}
```

```
wp momarab seed-terms   # يضيف المصطلحات الأساسية بأمان
wp momarab cache flush  # يفرّغ كاش الإضافة
```

- خرج مختصر: `Done.` أو رسالة خطأ صريحة مثل: `Error: terms already seeded.`

---

## 27) صلاحيات CPT/TAX (تنفيذ نموذجي)

```php
register_post_type('game', [
  'map_meta_cap' => true,
  'capability_type' => ['game','games'],
  'capabilities' => [
    'edit_post'          => 'manage_momarab_core',
    'read_post'          => 'read',
    'delete_post'        => 'manage_momarab_core',
    'edit_posts'         => 'manage_momarab_core',
    'edit_others_posts'  => 'manage_momarab_core',
    'publish_posts'      => 'manage_momarab_core',
    'read_private_posts' => 'read',
    'delete_posts'       => 'manage_momarab_core',
  ],
  // بقية args…
]);

$tax_caps = [
  'manage_terms'=>'manage_momarab_core',
  'edit_terms'=>'manage_momarab_core',
  'delete_terms'=>'manage_momarab_core',
  'assign_terms'=>'manage_momarab_core',
];

// مثال كامل لتسجيل تصنيف مع صلاحيات مخصصة
register_taxonomy('game_type', ['game'], [
  'hierarchical' => true,
  'capabilities' => $tax_caps,
  // بقية args…
]);
```

---

## 28) معايير الشفرة وإصدار النسخة

- تشدد PHPCS: `WordPress-Core`, `WordPress-Docs`.  
- لا تُضمّن أدوات اختبار. لا ملفات ديمو. لا لقطات شاشة.  
- Prefixed ثابت `mcp_` للدوال و`MCP_` للأصناف.  
- لا دوال أو متغيّرات Global غير مُدارة.  
- **إصدار:** ثبّت `MCP_VERSION` في رأس الإضافة، اتبع **SemVer**، وراجع `CHANGELOG.md`. لا تطبع النسخة في الواجهة.
- أضف `phpcs.xml` محليًا واعتَمد قواعد WordPress.

---

## 29) ملاحظات ترخيص ونطاق

الاستخدام شخصي/خاص. لا نشر عام. **لا ملفات اختبار أو بيانات ديمو**. لا خطوط أو اتصالات خارجية. لا متجر.

انتهى.
