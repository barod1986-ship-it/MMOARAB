<?php
/**
 * Related Posts Meta Box
 * 
 * @package MMOARAB_Core
 */

if (!defined('ABSPATH')) {
    exit;
}

class MCP_Related_Posts_Meta {
    
    private static $instance = null;
    
    public static function get_instance() {
        if (null === self::$instance) {
            self::$instance = new self();
        }
        return self::$instance;
    }
    
    private function __construct() {
        add_action('add_meta_boxes', [$this, 'add_meta_box']);
        add_action('save_post', [$this, 'save_meta']);
        add_action('admin_enqueue_scripts', [$this, 'enqueue_scripts']);
        add_action('wp_ajax_mcp_search_games', [$this, 'ajax_search_games']);
    }
    
    /**
     * الحصول على IP المستخدم بشكل آمن
     */
    private function get_user_ip() {
        $ip = '';
        
        if (!empty($_SERVER['HTTP_CLIENT_IP'])) {
            $ip = $_SERVER['HTTP_CLIENT_IP'];
        } elseif (!empty($_SERVER['HTTP_X_FORWARDED_FOR'])) {
            $forwarded = $_SERVER['HTTP_X_FORWARDED_FOR'];
            if (is_string($forwarded)) {
                $ip = explode(',', $forwarded)[0];
            }
        } elseif (!empty($_SERVER['REMOTE_ADDR'])) {
            $ip = $_SERVER['REMOTE_ADDR'];
        }
        
        return filter_var($ip, FILTER_VALIDATE_IP) ? $ip : '0.0.0.0';
    }
    
    public function enqueue_scripts($hook) {
        if ('post.php' !== $hook && 'post-new.php' !== $hook) {
            return;
        }
        
        $screen = get_current_screen();
        if ($screen->post_type !== 'post') {
            return;
        }
        
        // تحميل jQuery UI Autocomplete
        wp_enqueue_script('jquery-ui-autocomplete');
        wp_enqueue_style('wp-jquery-ui-dialog');
        
        wp_enqueue_script(
            'mcp-related-posts',
            MCP_PLUGIN_URL . 'assets/js/admin-related-posts.js',
            ['jquery', 'jquery-ui-autocomplete'],
            MCP_VERSION,
            true
        );
        
        wp_localize_script('mcp-related-posts', 'mcpAjax', [
            'ajax_url' => admin_url('admin-ajax.php'),
            'nonce' => wp_create_nonce('mcp_search_games'),
            'selected' => __('Selected:', 'mmoarab-core'),
            'clear' => __('Clear', 'mmoarab-core')
        ]);
    }
    
    public function add_meta_box() {
        add_meta_box(
            'mcp_related_game',
            __('Related Game', 'mmoarab-core'),
            [$this, 'render_meta_box'],
            'post',
            'side',
            'default'
        );
    }
    
    public function render_meta_box($post) {
        wp_nonce_field('mcp_related_game', 'mcp_related_game_nonce');
        
        $game_id = get_post_meta($post->ID, '_mcp_related_game_id', true);
        $game_title = '';
        
        if ($game_id) {
            $game = get_post($game_id);
            if ($game) {
                $game_title = $game->post_title;
            }
        }
        ?>
        
        <div class="mcp-related-game-field">
            <label for="mcp_game_search"><?php _e('Search for a game:', 'mmoarab-core'); ?></label>
            <input type="text" id="mcp_game_search" class="widefat" value="<?php echo esc_attr($game_title); ?>" placeholder="<?php _e('Type game name...', 'mmoarab-core'); ?>">
            <input type="hidden" id="mcp_related_game_id" name="mcp_related_game_id" value="<?php echo esc_attr($game_id); ?>">
            
            <?php if ($game_id && $game_title): ?>
            <p class="mcp-selected-game">
                <?php _e('Selected:', 'mmoarab-core'); ?> <strong><?php echo esc_html($game_title); ?></strong>
                <button type="button" class="button-link-delete" id="mcp-clear-game"><?php _e('Clear', 'mmoarab-core'); ?></button>
            </p>
            <?php endif; ?>
        </div>
        
        <?php
    }
    
    public function save_meta($post_id) {
        if (!isset($_POST['mcp_related_game_nonce']) || !wp_verify_nonce($_POST['mcp_related_game_nonce'], 'mcp_related_game')) {
            return;
        }
        
        if (defined('DOING_AUTOSAVE') && DOING_AUTOSAVE) {
            return;
        }
        
        if (!current_user_can('edit_post', $post_id)) {
            return;
        }
        
        // حذف الـ cache للـ game المرتبط القديم
        $old_game_id = get_post_meta($post_id, '_mcp_related_game_id', true);
        if ($old_game_id && is_numeric($old_game_id)) {
            delete_transient('mcp_related_posts_' . absint($old_game_id));
        }
        
        if (isset($_POST['mcp_related_game_id'])) {
            $game_id = absint($_POST['mcp_related_game_id']);
            if ($game_id > 0) {
                update_post_meta($post_id, '_mcp_related_game_id', $game_id);
                // حذف الـ cache للـ game الجديد
                delete_transient('mcp_related_posts_' . absint($game_id));
            } else {
                delete_post_meta($post_id, '_mcp_related_game_id');
            }
        }
    }
    
    public function ajax_search_games() {
        // التحقق من nonce
        if (!isset($_GET['nonce']) || !wp_verify_nonce($_GET['nonce'], 'mcp_search_games')) {
            wp_send_json([]);
        }
        
        // التحقق من الصلاحيات
        if (!current_user_can('edit_posts')) {
            wp_send_json([]);
        }
        
        // Rate limiting محسّن مع IP detection آمن
        $user_ip = $this->get_user_ip();
        $rate_limit_key = 'mcp_search_rate_' . md5($user_ip . wp_salt());
        
        // استخدام transient بدلاً من scheduled events
        $current_count = (int) get_transient($rate_limit_key);
        
        if ($current_count >= 10) {
            wp_send_json_error(['message' => __('Too many requests. Please wait.', 'mmoarab-core')]);
        }
        
        // زيادة العداد وحفظه لمدة 60 ثانية
        set_transient($rate_limit_key, $current_count + 1, 60);
        
        $search = isset($_GET['term']) ? sanitize_text_field($_GET['term']) : '';
        
        if (strlen($search) < 2) {
            wp_send_json([]);
        }
        
        $args = [
            'post_type' => 'game',
            'post_status' => 'publish',
            's' => $search,
            'posts_per_page' => 10,
        ];
        
        $query = new WP_Query($args);
        $results = [];
        
        if ($query->have_posts()) {
            while ($query->have_posts()) {
                $query->the_post();
                $results[] = [
                    'id' => get_the_ID(),
                    'label' => get_the_title(),
                    'value' => get_the_title(),
                ];
            }
        }
        
        wp_reset_postdata();
        wp_send_json($results);
    }
}
