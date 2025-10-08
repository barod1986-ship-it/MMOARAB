<?php
/**
 * Plugin Name: MMOARAB Core
 * Plugin URI: https://mmoarab.com
 * Description: إضافة WordPress لإدارة وعرض مراجعات ألعاب MMO العربية بشكل احترافي
 * Version: 1.0.1
 * Author: MMOARAB
 * Author URI: https://mmoarab.com
 * Text Domain: mmoarab-core
 * Domain Path: /languages
 * Requires at least: 6.4
 * Requires PHP: 8.0
 * License: GPL v2 or later
 * License URI: https://www.gnu.org/licenses/gpl-2.0.html
 */

// منع الوصول المباشر
if (!defined('ABSPATH')) {
    exit;
}

// تعريف الثوابت
if (!defined('MCP_VERSION')) {
    define('MCP_VERSION', '1.0.1');
}
if (!defined('MCP_PLUGIN_DIR')) {
    define('MCP_PLUGIN_DIR', plugin_dir_path(__FILE__));
}
if (!defined('MCP_PLUGIN_URL')) {
    define('MCP_PLUGIN_URL', plugin_dir_url(__FILE__));
}
if (!defined('MCP_PLUGIN_BASENAME')) {
    define('MCP_PLUGIN_BASENAME', plugin_basename(__FILE__));
}

/**
 * الكلاس الرئيسي للإضافة
 */
class MMOARAB_Core {
    
    /**
     * نسخة واحدة من الكلاس (Singleton)
     */
    private static $instance = null;
    
    /**
     * الحصول على النسخة الوحيدة
     */
    public static function get_instance() {
        if (null === self::$instance) {
            self::$instance = new self();
        }
        return self::$instance;
    }
    
    /**
     * Constructor
     */
    private function __construct() {
        $this->load_dependencies();
        $this->init_hooks();
    }
    
    /**
     * تحميل الملفات المطلوبة
     */
    private function load_dependencies() {
        $required_files = [
            'includes/class-cpt-game.php',
            'includes/class-taxonomies.php',
            'includes/class-game-meta.php',
            'includes/class-related-posts-meta.php',
            'includes/class-admin-page.php',
            'includes/class-seed-terms.php',
            'includes/class-schema.php'
        ];
        
        foreach ($required_files as $file) {
            $filepath = MCP_PLUGIN_DIR . $file;
            if (!file_exists($filepath)) {
                wp_die(
                    sprintf(
                        /* translators: %s: file path */
                        __('Required file is missing: %s', 'mmoarab-core'),
                        $file
                    )
                );
            }
            require_once $filepath;
        }
    }
    
    /**
     * تسجيل الـ Hooks
     */
    private function init_hooks() {
        // تفعيل الإضافة
        register_activation_hook(__FILE__, [$this, 'activate']);
        
        // إلغاء التفعيل
        register_deactivation_hook(__FILE__, [$this, 'deactivate']);
        
        // تحميل الترجمات أولاً
        add_action('plugins_loaded', [$this, 'load_textdomain'], 5);
        
        // تهيئة الإضافة
        add_action('plugins_loaded', [$this, 'init'], 10);
        
        // تسجيل الـ Assets
        add_action('admin_enqueue_scripts', [$this, 'admin_assets']);
        add_action('wp_enqueue_scripts', [$this, 'frontend_assets']);
        
        // تحميل Templates
        add_filter('template_include', [$this, 'load_templates']);
        
        // تسجيل cron callback للـ database indexes
        add_action('mcp_add_indexes_cron', [$this, 'process_database_indexes']);
        
        // تسجيل query vars للفلاتر
        add_filter('query_vars', [$this, 'register_query_vars']);
        
        // تطبيق الفلاتر على الأرشيف (أعلى priority لتجاوز أي تعديلات أخرى)
        add_action('pre_get_posts', [$this, 'apply_archive_filters'], PHP_INT_MAX);
    }
    
    /**
     * تسجيل query vars للفلاتر
     */
    public function register_query_vars($vars) {
        $vars[] = 'game_type';
        $vars[] = 'game_status';
        $vars[] = 'game_platform';
        $vars[] = 'game_mode';
        $vars[] = 'game_engine';
        $vars[] = 'orderby';
        return $vars;
    }
    
    /**
     * تطبيق الفلاتر على أرشيف الألعاب
     */
    public function apply_archive_filters($query) {
        // فقط في الواجهة الأمامية وللاستعلام الرئيسي
        if (is_admin() || !$query->is_main_query()) {
            return;
        }
        
        // التأكد من أننا في أرشيف الألعاب أو taxonomy للألعاب
        $is_game_archive = is_post_type_archive('game');
        $is_game_taxonomy = is_tax(['game_type', 'game_platform', 'game_status', 'game_mode', 'game_engine']);
        
        // التأكد من أن post_type هو game (مهم للفلاتر)
        $is_game_search = !empty($_GET['s']) && (
            !empty($_GET['game_type']) || 
            !empty($_GET['game_status']) || 
            !empty($_GET['game_platform']) || 
            !empty($_GET['game_mode']) || 
            !empty($_GET['game_engine'])
        );
        
        if (!$is_game_archive && !$is_game_taxonomy && !$is_game_search) {
            return;
        }
        
        // إجبار post_type على game عند استخدام الفلاتر
        if ($is_game_search) {
            $query->set('post_type', 'game');
        }
        
        // تعديل عدد الألعاب المعروضة
        $query->set('posts_per_page', 12);
        
        // تطبيق فلاتر التصنيفات
        $tax_query = [];
        $taxonomies = ['game_type', 'game_status', 'game_platform', 'game_mode', 'game_engine'];
        
        foreach ($taxonomies as $taxonomy) {
            $term = get_query_var($taxonomy);
            if (!empty($term)) {
                $tax_query[] = [
                    'taxonomy' => $taxonomy,
                    'field'    => 'slug',
                    'terms'    => sanitize_text_field($term),
                ];
            }
        }
        
        if (!empty($tax_query)) {
            $tax_query['relation'] = 'AND';
            $query->set('tax_query', $tax_query);
        }
        
        // تطبيق الترتيب
        $orderby = get_query_var('orderby');
        if (!empty($orderby)) {
            switch ($orderby) {
                case 'rating':
                    $query->set('meta_key', '_mcp_rating_overall');
                    $query->set('orderby', 'meta_value_num');
                    $query->set('order', 'DESC');
                    break;
                    
                case 'title':
                    $query->set('orderby', 'title');
                    $query->set('order', 'ASC');
                    break;
                    
                case 'popular':
                    $query->set('meta_key', '_mcp_views_count');
                    $query->set('orderby', 'meta_value_num');
                    $query->set('order', 'DESC');
                    break;
                    
                default:
                    // الترتيب الافتراضي: الأحدث أولاً
                    $query->set('orderby', 'date');
                    $query->set('order', 'DESC');
                    break;
            }
        } else {
            // الترتيب الافتراضي إذا لم يحدد المستخدم شيء
            $query->set('orderby', 'date');
            $query->set('order', 'DESC');
        }
    }
    
    /**
     * تفعيل الإضافة
     */
    public function activate() {
        // تسجيل CPT والـ Taxonomies
        MCP_CPT_Game::register();
        MCP_Taxonomies::register();
        
        // Flush rewrite rules
        flush_rewrite_rules();
        
        // إضافة database indexes للأداء
        $this->add_database_indexes();
        
        // حفظ وقت التفعيل للـ redirect
        set_transient('mcp_activation_redirect', true, 30);
    }
    
    /**
     * إضافة database indexes لتحسين الأداء
     */
    private function add_database_indexes() {
        // تأجيل إلى background باستخدام cron
        if (!wp_next_scheduled('mcp_add_indexes_cron')) {
            wp_schedule_single_event(time() + 10, 'mcp_add_indexes_cron');
        }
    }
    
    /**
     * معالجة database indexes في الخلفية
     */
    public function process_database_indexes() {
        global $wpdb;
        
        // زيادة timeout
        @set_time_limit(300);
        
        // Index 1: Related Posts
        $index_exists = $wpdb->get_results(
            $wpdb->prepare(
                "SHOW INDEX FROM {$wpdb->postmeta} WHERE Key_name = %s",
                'mcp_related_game_idx'
            )
        );
        
        if (empty($index_exists)) {
            $result = $wpdb->query("
                ALTER TABLE {$wpdb->postmeta} 
                ADD INDEX mcp_related_game_idx (meta_key(191), meta_value(20))
            ");
            
            if ($result === false) {
                error_log('MCP: Failed to add database index - ' . sanitize_text_field($wpdb->last_error));
            }
        }
        
        // Index 2: Rating Overall
        $rating_index_exists = $wpdb->get_results(
            $wpdb->prepare(
                "SHOW INDEX FROM {$wpdb->postmeta} WHERE Key_name = %s",
                'mcp_rating_overall_idx'
            )
        );
        
        if (empty($rating_index_exists)) {
            $result = $wpdb->query("
                ALTER TABLE {$wpdb->postmeta} 
                ADD INDEX mcp_rating_overall_idx (meta_key(191), meta_value(10))
            ");
            
            if ($result === false) {
                error_log('MCP: Failed to add rating index - ' . sanitize_text_field($wpdb->last_error));
            }
        }
    }
    
    /**
     * إلغاء تفعيل الإضافة
     */
    public function deactivate() {
        // إلغاء جميع scheduled events
        wp_clear_scheduled_hook('mcp_add_indexes_cron');
        
        // Flush rewrite rules
        flush_rewrite_rules();
    }
    
    /**
     * تهيئة الإضافة
     */
    public function init() {
        // تسجيل CPT
        MCP_CPT_Game::get_instance();
        
        // تسجيل Taxonomies
        MCP_Taxonomies::get_instance();
        
        // تسجيل Meta Boxes
        MCP_Game_Meta::get_instance();
        
        // Related Posts Meta
        MCP_Related_Posts_Meta::get_instance();
        
        // Admin Page
        MCP_Admin_Page::get_instance();
        
        // Seed Terms
        MCP_Seed_Terms::get_instance();
        
        // Schema Markup
        MCP_Schema::get_instance();
    }
    
    /**
     * تحميل ملفات الترجمة
     */
    public function load_textdomain() {
        load_plugin_textdomain(
            'mmoarab-core',
            false,
            dirname(MCP_PLUGIN_BASENAME) . '/languages'
        );
    }
    
    /**
     * تحميل Assets للوحة التحكم
     */
    public function admin_assets($hook) {
        global $post_type;
        
        // تحميل فقط في صفحات الألعاب
        if ('game' !== $post_type && 'toplevel_page_mmoarab-core' !== $hook) {
            return;
        }
        
        // Admin CSS
        wp_enqueue_style(
            'mcp-admin',
            MCP_PLUGIN_URL . 'assets/css/admin.css',
            [],
            MCP_VERSION
        );
        
        // Admin JS - Gallery & Overall Rating
        wp_enqueue_script(
            'mcp-admin',
            MCP_PLUGIN_URL . 'assets/js/admin.js',
            ['jquery', 'jquery-ui-sortable'],
            MCP_VERSION,
            true
        );
        
        // ترجمة النصوص في JavaScript
        wp_localize_script('mcp-admin', 'mcpI18n', [
            'selectGalleryImages' => __('Select Gallery Images', 'mmoarab-core'),
            'addToGallery' => __('Add to Gallery', 'mmoarab-core'),
            'galleryImageAlt' => __('Gallery Image', 'mmoarab-core'),
            'addingTerms' => __('Adding...', 'mmoarab-core'),
            'addDefaultTerms' => __('Add Default Game Terms', 'mmoarab-core'),
            'errorOccurred' => __('An error occurred. Please try again.', 'mmoarab-core')
        ]);
        
        // Related Posts Autocomplete
        if (('game' === $post_type || 'post' === $post_type) && current_user_can('edit_posts')) {
            wp_enqueue_script(
                'mcp-admin-related',
                MCP_PLUGIN_URL . 'assets/js/admin-related-posts.js',
                ['jquery', 'jquery-ui-autocomplete'],
                MCP_VERSION,
                true
            );
            
            wp_localize_script('mcp-admin-related', 'mcpAjax', [
                'ajax_url' => admin_url('admin-ajax.php'),
                'nonce' => wp_create_nonce('mcp_search_games')
            ]);
        }
        
        // Media Uploader
        wp_enqueue_media();
    }
    
    /**
     * تحميل Assets للواجهة الأمامية
     */
    public function frontend_assets() {
        // Single Game CSS
        if (is_singular('game')) {
            wp_enqueue_style(
                'mcp-single-game',
                MCP_PLUGIN_URL . 'assets/css/single-game.css',
                [],
                MCP_VERSION
            );
            
            // Lightbox JS
            wp_enqueue_script(
                'mcp-lightbox',
                MCP_PLUGIN_URL . 'assets/js/lightbox.js',
                ['jquery'],
                MCP_VERSION,
                true
            );
        }
        
        // Archive CSS
        if (is_post_type_archive('game') || is_tax(['game_type', 'game_platform', 'game_status', 'game_mode', 'game_engine'])) {
            wp_enqueue_style(
                'mcp-archive-game',
                MCP_PLUGIN_URL . 'assets/css/archive-game.css',
                [],
                MCP_VERSION
            );
        }
    }
    
    /**
     * تحميل Templates المخصصة
     */
    public function load_templates($template) {
        // Single Game Template
        if (is_singular('game')) {
            $custom_template = MCP_PLUGIN_DIR . 'templates/single-game.php';
            
            // السماح للثيم بتجاوز التمبلت
            $theme_template = locate_template(['mmoarab-core/single-game.php']);
            if ($theme_template) {
                return $theme_template;
            }
            
            if (file_exists($custom_template)) {
                return $custom_template;
            }
        }
        
        // Archive Template
        if (is_post_type_archive('game') || is_tax(['game_type', 'game_platform', 'game_status', 'game_mode', 'game_engine'])) {
            $custom_template = MCP_PLUGIN_DIR . 'templates/archive-game.php';
            
            // السماح للثيم بتجاوز التمبلت
            $theme_template = locate_template(['mmoarab-core/archive-game.php']);
            if ($theme_template) {
                return $theme_template;
            }
            
            if (file_exists($custom_template)) {
                return $custom_template;
            }
        }
        
        return $template;
    }
}

/**
 * تشغيل الإضافة
 */
function mmoarab_core() {
    return MMOARAB_Core::get_instance();
}

// بدء التشغيل
mmoarab_core();