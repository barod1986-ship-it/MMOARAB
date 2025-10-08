<?php
/**
 * Taxonomies للألعاب
 * 
 * @package MMOARAB_Core
 */

// منع الوصول المباشر
if (!defined('ABSPATH')) {
    exit;
}

/**
 * كلاس تسجيل التصنيفات
 */
class MCP_Taxonomies {
    
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
    }
    
    /**
     * تسجيل جميع التصنيفات
     */
    public static function register() {
        self::register_game_type();
        self::register_game_status();
        self::register_game_mode();
        self::register_game_platform();
        self::register_game_engine();
    }
    
    /**
     * تسجيل تصنيف: نوع اللعبة
     */
    private static function register_game_type() {
        $labels = [
            'name'              => _x('Game Types', 'taxonomy general name', 'mmoarab-core'),
            'singular_name'     => _x('Game Type', 'taxonomy singular name', 'mmoarab-core'),
            'search_items'      => __('Search Game Types', 'mmoarab-core'),
            'all_items'         => __('All Game Types', 'mmoarab-core'),
            'parent_item'       => __('Parent Game Type', 'mmoarab-core'),
            'parent_item_colon' => __('Parent Game Type:', 'mmoarab-core'),
            'edit_item'         => __('Edit Game Type', 'mmoarab-core'),
            'update_item'       => __('Update Game Type', 'mmoarab-core'),
            'add_new_item'      => __('Add New Game Type', 'mmoarab-core'),
            'new_item_name'     => __('New Game Type Name', 'mmoarab-core'),
            'menu_name'         => __('Game Types', 'mmoarab-core'),
        ];
        
        $args = [
            'hierarchical'      => true,
            'labels'            => $labels,
            'show_ui'           => true,
            'show_admin_column' => true,
            'query_var'         => true,
            'rewrite'           => ['slug' => 'game-type'],
            'show_in_rest'      => true,
        ];
        
        register_taxonomy('game_type', ['game'], $args);
    }
    
    /**
     * تسجيل تصنيف: حالة اللعبة
     */
    private static function register_game_status() {
        $labels = [
            'name'              => _x('Game Status', 'taxonomy general name', 'mmoarab-core'),
            'singular_name'     => _x('Status', 'taxonomy singular name', 'mmoarab-core'),
            'search_items'      => __('Search Status', 'mmoarab-core'),
            'all_items'         => __('All Status', 'mmoarab-core'),
            'parent_item'       => __('Parent Status', 'mmoarab-core'),
            'parent_item_colon' => __('Parent Status:', 'mmoarab-core'),
            'edit_item'         => __('Edit Status', 'mmoarab-core'),
            'update_item'       => __('Update Status', 'mmoarab-core'),
            'add_new_item'      => __('Add New Status', 'mmoarab-core'),
            'new_item_name'     => __('New Status Name', 'mmoarab-core'),
            'menu_name'         => __('Status', 'mmoarab-core'),
        ];
        
        $args = [
            'hierarchical'      => true,
            'labels'            => $labels,
            'show_ui'           => true,
            'show_admin_column' => true,
            'query_var'         => true,
            'rewrite'           => ['slug' => 'game-status'],
            'show_in_rest'      => true,
        ];
        
        register_taxonomy('game_status', ['game'], $args);
    }
    
    /**
     * تسجيل تصنيف: نمط اللعب
     */
    private static function register_game_mode() {
        $labels = [
            'name'              => _x('Game Modes', 'taxonomy general name', 'mmoarab-core'),
            'singular_name'     => _x('Game Mode', 'taxonomy singular name', 'mmoarab-core'),
            'search_items'      => __('Search Game Modes', 'mmoarab-core'),
            'all_items'         => __('All Game Modes', 'mmoarab-core'),
            'parent_item'       => __('Parent Game Mode', 'mmoarab-core'),
            'parent_item_colon' => __('Parent Game Mode:', 'mmoarab-core'),
            'edit_item'         => __('Edit Game Mode', 'mmoarab-core'),
            'update_item'       => __('Update Game Mode', 'mmoarab-core'),
            'add_new_item'      => __('Add New Game Mode', 'mmoarab-core'),
            'new_item_name'     => __('New Game Mode Name', 'mmoarab-core'),
            'menu_name'         => __('Game Modes', 'mmoarab-core'),
        ];
        
        $args = [
            'hierarchical'      => true,
            'labels'            => $labels,
            'show_ui'           => true,
            'show_admin_column' => true,
            'query_var'         => true,
            'rewrite'           => ['slug' => 'game-mode'],
            'show_in_rest'      => true,
        ];
        
        register_taxonomy('game_mode', ['game'], $args);
    }
    
    /**
     * تسجيل تصنيف: المنصات
     */
    private static function register_game_platform() {
        $labels = [
            'name'              => _x('Platforms', 'taxonomy general name', 'mmoarab-core'),
            'singular_name'     => _x('Platform', 'taxonomy singular name', 'mmoarab-core'),
            'search_items'      => __('Search Platforms', 'mmoarab-core'),
            'all_items'         => __('All Platforms', 'mmoarab-core'),
            'parent_item'       => __('Parent Platform', 'mmoarab-core'),
            'parent_item_colon' => __('Parent Platform:', 'mmoarab-core'),
            'edit_item'         => __('Edit Platform', 'mmoarab-core'),
            'update_item'       => __('Update Platform', 'mmoarab-core'),
            'add_new_item'      => __('Add New Platform', 'mmoarab-core'),
            'new_item_name'     => __('New Platform Name', 'mmoarab-core'),
            'menu_name'         => __('Platforms', 'mmoarab-core'),
        ];
        
        $args = [
            'hierarchical'      => true,
            'labels'            => $labels,
            'show_ui'           => true,
            'show_admin_column' => true,
            'query_var'         => true,
            'rewrite'           => ['slug' => 'platform'],
            'show_in_rest'      => true,
        ];
        
        register_taxonomy('game_platform', ['game'], $args);
    }
    
    /**
     * تسجيل تصنيف: محرك اللعبة
     */
    private static function register_game_engine() {
        $labels = [
            'name'              => _x('Game Engines', 'taxonomy general name', 'mmoarab-core'),
            'singular_name'     => _x('Game Engine', 'taxonomy singular name', 'mmoarab-core'),
            'search_items'      => __('Search Game Engines', 'mmoarab-core'),
            'all_items'         => __('All Game Engines', 'mmoarab-core'),
            'parent_item'       => __('Parent Game Engine', 'mmoarab-core'),
            'parent_item_colon' => __('Parent Game Engine:', 'mmoarab-core'),
            'edit_item'         => __('Edit Game Engine', 'mmoarab-core'),
            'update_item'       => __('Update Game Engine', 'mmoarab-core'),
            'add_new_item'      => __('Add New Game Engine', 'mmoarab-core'),
            'new_item_name'     => __('New Game Engine Name', 'mmoarab-core'),
            'menu_name'         => __('Game Engines', 'mmoarab-core'),
        ];
        
        $args = [
            'hierarchical'      => true,
            'labels'            => $labels,
            'show_ui'           => true,
            'show_admin_column' => true,
            'query_var'         => true,
            'rewrite'           => ['slug' => 'game-engine'],
            'show_in_rest'      => true,
        ];
        
        register_taxonomy('game_engine', ['game'], $args);
    }
}
