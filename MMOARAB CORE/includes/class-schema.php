<?php
/**
 * Schema Markup - JSON-LD للـ SEO
 * 
 * @package MMOARAB_Core
 */

if (!defined('ABSPATH')) {
    exit;
}

class MCP_Schema {
    
    private static $instance = null;
    
    public static function get_instance() {
        if (null === self::$instance) {
            self::$instance = new self();
        }
        return self::$instance;
    }
    
    private function __construct() {
        add_action('wp_head', [$this, 'add_schema_markup']);
    }
    
    public function add_schema_markup() {
        if (!is_singular('game')) {
            return;
        }
        
        global $post;
        
        $schema = [
            '@context' => 'https://schema.org',
            '@type' => 'VideoGame',
            'name' => get_the_title(),
            'description' => wp_strip_all_tags(get_the_excerpt()),
            'url' => get_permalink(),
        ];
        
        // الصورة المميزة
        if (has_post_thumbnail()) {
            $schema['image'] = get_the_post_thumbnail_url($post->ID, 'full');
        }
        
        // المطور
        $developer = get_post_meta($post->ID, '_mcp_developer', true);
        if ($developer) {
            $schema['author'] = [
                '@type' => 'Organization',
                'name' => $developer
            ];
        }
        
        // الناشر
        $publisher = get_post_meta($post->ID, '_mcp_publisher', true);
        if ($publisher) {
            $schema['publisher'] = [
                '@type' => 'Organization',
                'name' => $publisher
            ];
        }
        
        // تاريخ الإصدار
        $release_date = get_post_meta($post->ID, '_mcp_release_date', true);
        if ($release_date) {
            $schema['datePublished'] = $release_date;
        }
        
        // التقييم
        $overall = get_post_meta($post->ID, '_mcp_rating_overall', true);
        if ($overall) {
            $schema['aggregateRating'] = [
                '@type' => 'AggregateRating',
                'ratingValue' => floatval($overall),
                'bestRating' => 10,
                'worstRating' => 1,
                'ratingCount' => 1,
                'reviewCount' => 1
            ];
        }
        
        // اللغة
        $schema['inLanguage'] = get_bloginfo('language');
        
        // التصنيف
        $statuses = wp_get_post_terms($post->ID, 'game_status', ['fields' => 'names']);
        if (!is_wp_error($statuses) && !empty($statuses)) {
            $schema['applicationCategory'] = 'Game';
        }
        
        // المنصات
        $platforms = wp_get_post_terms($post->ID, 'game_platform', ['fields' => 'names']);
        if (!is_wp_error($platforms) && !empty($platforms)) {
            $schema['gamePlatform'] = $platforms;
        }
        
        // نوع اللعبة
        $types = wp_get_post_terms($post->ID, 'game_type', ['fields' => 'names']);
        if (!is_wp_error($types) && !empty($types)) {
            $schema['genre'] = $types;
        }
        
        echo '<script type="application/ld+json">' . wp_json_encode($schema, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES) . '</script>' . "\n";
    }
}
