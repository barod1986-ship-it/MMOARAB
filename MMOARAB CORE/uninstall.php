<?php
/**
 * Uninstall MMOARAB Core
 * 
 * معالج إلغاء التثبيت - يحذف جميع البيانات عند حذف الإضافة
 * 
 * @package MMOARAB_Core
 */

// إذا لم يتم استدعاء uninstall من WordPress، نخرج
if (!defined('WP_UNINSTALL_PLUGIN')) {
    exit;
}

// حذف جميع الألعاب
$games = get_posts([
    'post_type' => 'game',
    'posts_per_page' => -1,
    'post_status' => 'any',
]);

foreach ($games as $game) {
    wp_delete_post($game->ID, true);
}

// حذف جميع المصطلحات من التصنيفات
$taxonomies = [
    'game_type',
    'game_status',
    'game_mode',
    'game_platform',
    'game_engine',
];

foreach ($taxonomies as $taxonomy) {
    $terms = get_terms([
        'taxonomy' => $taxonomy,
        'hide_empty' => false,
    ]);
    
    if (!is_wp_error($terms)) {
        foreach ($terms as $term) {
            wp_delete_term($term->term_id, $taxonomy);
        }
    }
}

// حذف Options (إذا كانت موجودة)
delete_option('mcp_version');
delete_option('mcp_settings');

// حذف Transients
delete_transient('mcp_activation_redirect');

// إلغاء جميع scheduled events
wp_clear_scheduled_hook('mcp_add_indexes_cron');

// حذف rate limiting transients (البحث عن جميع mcp_search_rate_*)
global $wpdb;
$wpdb->query("DELETE FROM {$wpdb->options} WHERE option_name LIKE '_transient_mcp_search_rate_%' OR option_name LIKE '_transient_timeout_mcp_search_rate_%'");

// حذف related posts cache transients
$wpdb->query("DELETE FROM {$wpdb->options} WHERE option_name LIKE '_transient_mcp_related_posts_%' OR option_name LIKE '_transient_timeout_mcp_related_posts_%'");

// Flush rewrite rules
flush_rewrite_rules();

// تنظيف Meta data من المقالات العادية
$wpdb->query($wpdb->prepare(
    "DELETE FROM {$wpdb->postmeta} WHERE meta_key LIKE %s",
    $wpdb->esc_like('_mcp_') . '%'
));

// حذف database indexes (MySQL 5.6+ compatible)
$index_exists = $wpdb->get_results("SHOW INDEX FROM {$wpdb->postmeta} WHERE Key_name = 'mcp_related_game_idx'");
if (!empty($index_exists)) {
    $wpdb->query("ALTER TABLE {$wpdb->postmeta} DROP INDEX mcp_related_game_idx");
}

$rating_index_exists = $wpdb->get_results("SHOW INDEX FROM {$wpdb->postmeta} WHERE Key_name = 'mcp_rating_overall_idx'");
if (!empty($rating_index_exists)) {
    $wpdb->query("ALTER TABLE {$wpdb->postmeta} DROP INDEX mcp_rating_overall_idx");
}
