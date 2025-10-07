<?php
/**
 * Seed Terms - المصطلحات الجاهزة
 * 
 * @package MMOARAB_Core
 */

if (!defined('ABSPATH')) {
    exit;
}

class MCP_Seed_Terms {
    
    private static $instance = null;
    
    public static function get_instance() {
        if (null === self::$instance) {
            self::$instance = new self();
        }
        return self::$instance;
    }
    
    private function __construct() {
        add_action('wp_ajax_mcp_add_seed_terms', [$this, 'ajax_add_seed_terms']);
    }
    
    public function ajax_add_seed_terms() {
        check_ajax_referer('mcp_add_seed_terms', 'nonce');
        
        if (!current_user_can('manage_options')) {
            wp_send_json_error(['message' => __('Permission denied.', 'mmoarab-core')]);
        }
        
        $added = $this->add_all_terms();
        
        wp_send_json_success([
            'message' => sprintf(__('Successfully added %d terms!', 'mmoarab-core'), $added),
            'count' => $added
        ]);
    }
    
    public function add_all_terms() {
        $added_count = 0;
        $errors = [];
        
        // Game Types
        $game_types = [
            'MMORPG' => 'mmorpg',
            'MMO-ARPG' => 'mmo-arpg',
            'MMOFPS' => 'mmofps',
            'MOBA' => 'moba',
            'MMORTS' => 'mmorts',
            'Survival MMO' => 'survival-mmo',
            'Sandbox MMO' => 'sandbox-mmo',
            'Social MMO' => 'social-mmo',
            'Battle Royale' => 'royale',
            'Racing MMO' => 'racing-mmo',
            'Sports MMO' => 'sports-mmo',
            'Space MMO' => 'space-mmo',
            'Naval MMO' => 'naval-mmo',
            'Anime MMO' => 'anime-mmo',
        ];
        
        foreach ($game_types as $name => $slug) {
            if (!term_exists($slug, 'game_type')) {
                $result = wp_insert_term($name, 'game_type', ['slug' => $slug]);
                if (!is_wp_error($result)) {
                    $added_count++;
                } else {
                    $errors[] = $name . ': ' . $result->get_error_message();
                }
            }
        }
        
        // Game Status
        $game_status = [
            'Upcoming' => 'upcoming',
            'Alpha' => 'alpha',
            'Beta' => 'beta',
            'Early Access' => 'early-access',
            'Released' => 'released',
        ];
        
        foreach ($game_status as $name => $slug) {
            if (!term_exists($slug, 'game_status')) {
                $result = wp_insert_term($name, 'game_status', ['slug' => $slug]);
                if (!is_wp_error($result)) {
                    $added_count++;
                } else {
                    $errors[] = $name . ': ' . $result->get_error_message();
                }
            }
        }
        
        // Game Modes
        $game_modes = [
            'PvE' => 'pve',
            'PvP' => 'pvp',
            'PvPvE' => 'pvpve',
            'Open World' => 'open-world',
            'Co-op' => 'co-op',
        ];
        
        foreach ($game_modes as $name => $slug) {
            if (!term_exists($slug, 'game_mode')) {
                $result = wp_insert_term($name, 'game_mode', ['slug' => $slug]);
                if (!is_wp_error($result)) {
                    $added_count++;
                } else {
                    $errors[] = $name . ': ' . $result->get_error_message();
                }
            }
        }
        
        // Platforms
        $platforms = [
            'PC' => 'pc',
            'PlayStation' => 'playstation',
            'Xbox' => 'xbox',
            'Nintendo Switch' => 'nintendo-switch',
            'Mobile' => 'mobile',
            'Browser' => 'browser',
        ];
        
        foreach ($platforms as $name => $slug) {
            if (!term_exists($slug, 'game_platform')) {
                $result = wp_insert_term($name, 'game_platform', ['slug' => $slug]);
                if (!is_wp_error($result)) {
                    $added_count++;
                } else {
                    $errors[] = $name . ': ' . $result->get_error_message();
                }
            }
        }
        
        // Game Engines
        $engines = [
            'Unreal Engine 5' => 'unreal-engine-5',
            'Unreal Engine 4' => 'unreal-engine-4',
            'Unity' => 'unity',
            'CryEngine' => 'cryengine',
            'Custom Engine' => 'custom-engine',
            'Godot' => 'godot',
            'Frostbite' => 'frostbite',
            'REDengine' => 'redengine',
            'Source Engine' => 'source-engine',
            'Lumberyard' => 'lumberyard',
            'Creation Engine' => 'creation-engine',
        ];
        
        foreach ($engines as $name => $slug) {
            if (!term_exists($slug, 'game_engine')) {
                $result = wp_insert_term($name, 'game_engine', ['slug' => $slug]);
                if (!is_wp_error($result)) {
                    $added_count++;
                } else {
                    $errors[] = $name . ': ' . $result->get_error_message();
                }
            }
        }
        
        // تسجيل الأخطاء إذا وجدت (مع sanitization)
        if (!empty($errors)) {
            $sanitized_errors = array_map('esc_html', $errors);
            error_log('MCP Seed Terms Errors: ' . implode(', ', $sanitized_errors));
        }
        
        return $added_count;
    }
}
