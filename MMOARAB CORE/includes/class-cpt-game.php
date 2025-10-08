<?php
/**
 * Custom Post Type - Game
 * 
 * @package MMOARAB_Core
 */

// منع الوصول المباشر
if (!defined('ABSPATH')) {
    exit;
}

/**
 * كلاس تسجيل Custom Post Type للألعاب
 */
class MCP_CPT_Game {
    
    /**
     * نسخة واحدة من الكلاس
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
        add_action('init', [$this, 'register']);
        add_action('pre_get_posts', [$this, 'archive_filters']);
        add_filter('query_vars', [$this, 'add_query_vars']);
    }
    
    /**
     * تسجيل Custom Post Type
     */
    public static function register() {
        $labels = [
            'name'                  => _x('Games', 'Post type general name', 'mmoarab-core'),
            'singular_name'         => _x('Game', 'Post type singular name', 'mmoarab-core'),
            'menu_name'             => _x('Games', 'Admin Menu text', 'mmoarab-core'),
            'name_admin_bar'        => _x('Game', 'Add New on Toolbar', 'mmoarab-core'),
            'add_new'               => __('Add New', 'mmoarab-core'),
            'add_new_item'          => __('Add New Game', 'mmoarab-core'),
            'new_item'              => __('New Game', 'mmoarab-core'),
            'edit_item'             => __('Edit Game', 'mmoarab-core'),
            'view_item'             => __('View Game', 'mmoarab-core'),
            'all_items'             => __('All Games', 'mmoarab-core'),
            'search_items'          => __('Search Games', 'mmoarab-core'),
            'parent_item_colon'     => __('Parent Games:', 'mmoarab-core'),
            'not_found'             => __('No games found.', 'mmoarab-core'),
            'not_found_in_trash'    => __('No games found in Trash.', 'mmoarab-core'),
            'featured_image'        => _x('Game Cover Image', 'Overrides the "Featured Image" phrase', 'mmoarab-core'),
            'set_featured_image'    => _x('Set cover image', 'Overrides the "Set featured image" phrase', 'mmoarab-core'),
            'remove_featured_image' => _x('Remove cover image', 'Overrides the "Remove featured image" phrase', 'mmoarab-core'),
            'use_featured_image'    => _x('Use as cover image', 'Overrides the "Use as featured image" phrase', 'mmoarab-core'),
            'archives'              => _x('Game archives', 'The post type archive label', 'mmoarab-core'),
            'insert_into_item'      => _x('Insert into game', 'Overrides the "Insert into post" phrase', 'mmoarab-core'),
            'uploaded_to_this_item' => _x('Uploaded to this game', 'Overrides the "Uploaded to this post" phrase', 'mmoarab-core'),
            'filter_items_list'     => _x('Filter games list', 'Screen reader text', 'mmoarab-core'),
            'items_list_navigation' => _x('Games list navigation', 'Screen reader text', 'mmoarab-core'),
            'items_list'            => _x('Games list', 'Screen reader text', 'mmoarab-core'),
        ];
        
        $args = [
            'labels'             => $labels,
            'public'             => true,
            'publicly_queryable' => true,
            'show_ui'            => true,
            'show_in_menu'       => true,
            'query_var'          => true,
            'rewrite'            => ['slug' => 'games', 'with_front' => false],
            'capability_type'    => 'post',
            'has_archive'        => true,
            'hierarchical'       => false,
            'menu_position'      => 5,
            'menu_icon'          => 'dashicons-games',
            'supports'           => [
                'title',
                'editor',
                'thumbnail',
                'excerpt',
                'comments',
                'revisions',
                'author'
            ],
            'show_in_rest'       => true, // دعم Gutenberg
            'taxonomies'         => [
                'game_type',
                'game_status',
                'game_mode',
                'game_platform',
                'game_engine'
            ],
        ];
        
        register_post_type('game', $args);
    }
    
    /**
     * إضافة متغيرات الاستعلام المخصصة
     */
    public function add_query_vars($vars) {
        $vars[] = 'search';
        $vars[] = 'game_type';
        $vars[] = 'game_status';
        $vars[] = 'game_platform';
        $vars[] = 'game_mode';
        $vars[] = 'game_engine';
        return $vars;
    }
    
    /**
     * تطبيق الفلاتر على صفحة الأرشيف
     */
    public function archive_filters($query) {
        // تحقق أننا في الأرشيف وليس في الـ admin
        if (!is_admin() && $query->is_main_query() && is_post_type_archive('game')) {
            
            // فلتر حسب التصنيفات
            $tax_query = [];
            
            $taxonomies = ['game_type', 'game_status', 'game_platform', 'game_mode', 'game_engine'];
            
            foreach ($taxonomies as $taxonomy) {
                if (!empty($_GET[$taxonomy])) {
                    // التحقق من أن المصطلح موجود فعلياً
                    $term_slug = sanitize_text_field($_GET[$taxonomy]);
                    if (term_exists($term_slug, $taxonomy)) {
                        $tax_query[] = [
                            'taxonomy' => $taxonomy,
                            'field'    => 'slug',
                            'terms'    => $term_slug,
                        ];
                    }
                }
            }
            
            if (!empty($tax_query)) {
                $tax_query['relation'] = 'AND';
                $query->set('tax_query', $tax_query);
            }
        }
    }
}
