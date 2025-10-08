<?php
/**
 * Admin Page - MMOARAB Core Dashboard
 * 
 * @package MMOARAB_Core
 */

if (!defined('ABSPATH')) {
    exit;
}

class MCP_Admin_Page {
    
    private static $instance = null;
    
    public static function get_instance() {
        if (null === self::$instance) {
            self::$instance = new self();
        }
        return self::$instance;
    }
    
    private function __construct() {
        add_action('admin_menu', [$this, 'add_menu_page']);
        add_action('admin_init', [$this, 'redirect_after_activation']);
        add_action('admin_enqueue_scripts', [$this, 'enqueue_scripts']);
    }
    
    public function enqueue_scripts($hook) {
        if ('toplevel_page_mmoarab-core' !== $hook) {
            return;
        }
        
        wp_enqueue_script(
            'mcp-admin',
            MCP_PLUGIN_URL . 'assets/js/admin.js',
            ['jquery'],
            MCP_VERSION,
            true
        );
        
        wp_localize_script('mcp-admin', 'mcpAdmin', [
            'ajax_url' => admin_url('admin-ajax.php'),
            'nonce' => wp_create_nonce('mcp_add_seed_terms')
        ]);
    }
    
    public function add_menu_page() {
        add_menu_page(
            __('MMOARAB Core', 'mmoarab-core'),
            __('MMOARAB Core', 'mmoarab-core'),
            'manage_options',
            'mmoarab-core',
            [$this, 'render_page'],
            'dashicons-games',
            3
        );
    }
    
    public function redirect_after_activation() {
        if (get_transient('mcp_activation_redirect')) {
            delete_transient('mcp_activation_redirect');
            
            // التحقق من activate-multi و الصلاحيات
            // phpcs:ignore WordPress.Security.NonceVerification.Recommended
            if (!isset($_GET['activate-multi']) && current_user_can('manage_options')) {
                wp_safe_redirect(admin_url('admin.php?page=mmoarab-core'));
                exit;
            }
        }
    }
    
    public function render_page() {
        $games_count = wp_count_posts('game');
        $total_games = is_object($games_count) && isset($games_count->publish) ? $games_count->publish : 0;
        $archive_url = get_post_type_archive_link('game');
        ?>
        
        <div class="wrap mcp-admin-page">
            <h1><?php _e('MMOARAB Core - Settings', 'mmoarab-core'); ?></h1>
            
            <div class="mcp-welcome-panel">
                <h2><?php _e('Welcome to MMOARAB Core!', 'mmoarab-core'); ?></h2>
                <p><?php _e('Manage your MMO games reviews professionally.', 'mmoarab-core'); ?></p>
            </div>
            
            <div class="mcp-dashboard-grid">
                
                <!-- Seed Terms Section -->
                <div class="mcp-dashboard-box">
                    <h3><?php _e('Seed Terms', 'mmoarab-core'); ?></h3>
                    <p><?php _e('Add default game terms to get started quickly.', 'mmoarab-core'); ?></p>
                    <button type="button" id="mcp-add-seed-terms" class="button button-primary">
                        <?php _e('Add Default Game Terms', 'mmoarab-core'); ?>
                    </button>
                    <div id="mcp-seed-terms-message"></div>
                </div>
                
                <!-- Plugin Info -->
                <div class="mcp-dashboard-box">
                    <h3><?php _e('Plugin Information', 'mmoarab-core'); ?></h3>
                    <ul>
                        <li><strong><?php _e('Version:', 'mmoarab-core'); ?></strong> <?php echo MCP_VERSION; ?></li>
                        <li><strong><?php _e('Post Type:', 'mmoarab-core'); ?></strong> game</li>
                        <li><strong><?php _e('Archive URL:', 'mmoarab-core'); ?></strong> <a href="<?php echo esc_url($archive_url); ?>" target="_blank"><?php echo esc_html($archive_url); ?></a></li>
                        <li><strong><?php _e('Total Games:', 'mmoarab-core'); ?></strong> <?php echo esc_html($total_games); ?></li>
                    </ul>
                </div>
                
                <!-- Quick Links -->
                <div class="mcp-dashboard-box">
                    <h3><?php _e('Quick Links', 'mmoarab-core'); ?></h3>
                    <p>
                        <a href="<?php echo admin_url('edit.php?post_type=game'); ?>" class="button"><?php _e('View All Games', 'mmoarab-core'); ?></a>
                        <a href="<?php echo admin_url('post-new.php?post_type=game'); ?>" class="button button-primary"><?php _e('Add New Game', 'mmoarab-core'); ?></a>
                        <a href="<?php echo esc_url($archive_url); ?>" class="button" target="_blank"><?php _e('View Archive', 'mmoarab-core'); ?></a>
                    </p>
                </div>
                
                <!-- Documentation -->
                <div class="mcp-dashboard-box">
                    <h3><?php _e('Documentation & Support', 'mmoarab-core'); ?></h3>
                    <ul>
                        <li><a href="<?php echo MCP_PLUGIN_URL; ?>README.md" target="_blank"><?php _e('README', 'mmoarab-core'); ?></a></li>
                        <li><a href="<?php echo MCP_PLUGIN_URL; ?>DESIGN-DOCUMENTATION.md" target="_blank"><?php _e('Design Documentation', 'mmoarab-core'); ?></a></li>
                        <li><strong><?php _e('Support:', 'mmoarab-core'); ?></strong> support@mmoarab.com</li>
                    </ul>
                </div>
                
            </div>
        </div>
        
        <?php
    }
}
