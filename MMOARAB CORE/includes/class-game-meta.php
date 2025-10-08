<?php
/**
 * Game Meta Boxes
 * 
 * @package MMOARAB_Core
 */

// منع الوصول المباشر
if (!defined('ABSPATH')) {
    exit;
}

/**
 * كلاس Meta Boxes للألعاب
 */
class MCP_Game_Meta {
    
    private static $instance = null;
    
    public static function get_instance() {
        if (null === self::$instance) {
            self::$instance = new self();
        }
        return self::$instance;
    }
    
    private function __construct() {
        add_action('add_meta_boxes', [$this, 'add_meta_boxes']);
        add_action('save_post_game', [$this, 'save_meta'], 10, 2);
    }
    
    /**
     * إضافة Meta Boxes
     */
    public function add_meta_boxes() {
        // معلومات اللعبة
        add_meta_box(
            'mcp_game_info',
            __('Game Information', 'mmoarab-core'),
            [$this, 'render_game_info'],
            'game',
            'normal',
            'high'
        );
        
        // المميزات
        add_meta_box(
            'mcp_game_features',
            __('Game Features', 'mmoarab-core'),
            [$this, 'render_game_features'],
            'game',
            'normal',
            'default'
        );
        
        // معرض الصور
        add_meta_box(
            'mcp_game_gallery',
            __('Game Gallery', 'mmoarab-core'),
            [$this, 'render_gallery'],
            'game',
            'normal',
            'default'
        );
        
        // التقييمات
        add_meta_box(
            'mcp_game_ratings',
            __('Game Ratings', 'mmoarab-core'),
            [$this, 'render_ratings'],
            'game',
            'normal',
            'default'
        );
    }
    
    /**
     * عرض حقول معلومات اللعبة
     */
    public function render_game_info($post) {
        wp_nonce_field('mcp_game_meta', 'mcp_game_meta_nonce');
        
        $developer = get_post_meta($post->ID, '_mcp_developer', true);
        $publisher = get_post_meta($post->ID, '_mcp_publisher', true);
        $release_date = get_post_meta($post->ID, '_mcp_release_date', true);
        $official_site = get_post_meta($post->ID, '_mcp_official_site', true);
        $trailer = get_post_meta($post->ID, '_mcp_trailer', true);
        ?>
        
        <div class="mcp-meta-field">
            <label for="mcp_developer"><?php _e('Developer', 'mmoarab-core'); ?></label>
            <input type="text" id="mcp_developer" name="mcp_developer" value="<?php echo esc_attr($developer); ?>" class="widefat">
        </div>
        
        <div class="mcp-meta-field">
            <label for="mcp_publisher"><?php _e('Publisher', 'mmoarab-core'); ?></label>
            <input type="text" id="mcp_publisher" name="mcp_publisher" value="<?php echo esc_attr($publisher); ?>" class="widefat">
        </div>
        
        <div class="mcp-meta-field">
            <label for="mcp_release_date"><?php _e('Release Date', 'mmoarab-core'); ?></label>
            <input type="date" id="mcp_release_date" name="mcp_release_date" value="<?php echo esc_attr($release_date); ?>" class="widefat">
        </div>
        
        <div class="mcp-meta-field">
            <label for="mcp_official_site"><?php _e('Official Website', 'mmoarab-core'); ?></label>
            <input type="url" id="mcp_official_site" name="mcp_official_site" value="<?php echo esc_url($official_site); ?>" class="widefat" placeholder="https://">
        </div>
        
        <div class="mcp-meta-field">
            <label for="mcp_trailer"><?php _e('Trailer URL', 'mmoarab-core'); ?></label>
            <input type="url" id="mcp_trailer" name="mcp_trailer" value="<?php echo esc_url($trailer); ?>" class="widefat" placeholder="https://youtube.com/watch?v=...">
            <p class="description"><?php _e('YouTube, Vimeo, or direct video URL', 'mmoarab-core'); ?></p>
        </div>
        
        <?php
    }
    
    /**
     * عرض حقول المميزات
     */
    public function render_game_features($post) {
        for ($i = 1; $i <= 4; $i++) {
            $feature = get_post_meta($post->ID, "_mcp_feature_{$i}", true);
            ?>
            <div class="mcp-meta-field">
                <label for="mcp_feature_<?php echo esc_attr($i); ?>"><?php printf(__('Feature %d', 'mmoarab-core'), $i); ?></label>
                <input type="text" id="mcp_feature_<?php echo esc_attr($i); ?>" name="mcp_feature_<?php echo esc_attr($i); ?>" value="<?php echo esc_attr($feature); ?>" class="widefat">
            </div>
            <?php
        }
    }
    
    /**
     * عرض معرض الصور
     */
    public function render_gallery($post) {
        $gallery = get_post_meta($post->ID, '_mcp_gallery', true);
        
        // التحقق من نوع البيانات - يجب أن تكون string
        if (!is_string($gallery)) {
            $gallery = '';
        }
        
        // تحويل إلى array وتنظيف
        $gallery_ids = !empty($gallery) ? array_filter(array_map('absint', explode(',', $gallery))) : [];
        ?>
        
        <div id="mcp-gallery-container">
            <div id="mcp-gallery-images">
                <?php foreach ($gallery_ids as $image_id): 
                    // التحقق من أن الـ ID رقم صحيح وموجب
                    if (!$image_id || !is_numeric($image_id)) {
                        continue;
                    }
                    
                    $image = wp_get_attachment_image_src($image_id, 'thumbnail');
                    if ($image):
                ?>
                <div class="mcp-gallery-image" data-id="<?php echo esc_attr($image_id); ?>">
                    <img src="<?php echo esc_url($image[0]); ?>" alt="">
                    <button type="button" class="mcp-remove-image">×</button>
                </div>
                <?php 
                    endif;
                endforeach; ?>
            </div>
            <button type="button" id="mcp-add-gallery-images" class="button"><?php _e('Add Images', 'mmoarab-core'); ?></button>
            <input type="hidden" id="mcp_gallery" name="mcp_gallery" value="<?php echo esc_attr($gallery); ?>">
            <p class="description"><?php _e('Click and drag to reorder images', 'mmoarab-core'); ?></p>
        </div>
        
        <?php
    }
    
    /**
     * عرض حقول التقييمات
     */
    public function render_ratings($post) {
        $ratings = [
            'story' => __('Story', 'mmoarab-core'),
            'gameplay' => __('Gameplay', 'mmoarab-core'),
            'graphics' => __('Graphics', 'mmoarab-core'),
            'audio' => __('Audio', 'mmoarab-core'),
        ];
        
        foreach ($ratings as $key => $label) {
            $rating = get_post_meta($post->ID, "_mcp_rating_{$key}", true);
            $notes = get_post_meta($post->ID, "_mcp_rating_{$key}_notes", true);
            ?>
            
            <div class="mcp-rating-field">
                <label><strong><?php echo esc_html($label); ?></strong></label>
                <input type="number" name="mcp_rating_<?php echo esc_attr($key); ?>" value="<?php echo esc_attr($rating); ?>" min="1" max="10" step="0.1" class="mcp-rating-input small-text" placeholder="1-10">
                <textarea name="mcp_rating_<?php echo esc_attr($key); ?>_notes" rows="2" class="widefat" placeholder="<?php _e('Notes (optional)', 'mmoarab-core'); ?>"><?php echo esc_textarea($notes); ?></textarea>
            </div>
            
            <?php
        }
        
        $overall = get_post_meta($post->ID, '_mcp_rating_overall', true);
        ?>
        
        <div class="mcp-rating-overall">
            <label><strong><?php _e('Final Rating', 'mmoarab-core'); ?></strong></label>
            <input type="number" id="mcp_rating_overall" name="mcp_rating_overall" value="<?php echo esc_attr($overall); ?>" min="1" max="10" step="0.1" class="small-text" readonly>
            <p class="description"><?php _e('Calculated automatically', 'mmoarab-core'); ?></p>
        </div>
        
        <?php
    }
    
    /**
     * حفظ البيانات
     */
    public function save_meta($post_id, $post) {
        // التحقق من nonce
        if (!isset($_POST['mcp_game_meta_nonce']) || !wp_verify_nonce($_POST['mcp_game_meta_nonce'], 'mcp_game_meta')) {
            return;
        }
        
        // التحقق من الصلاحيات
        if (!current_user_can('edit_post', $post_id)) {
            return;
        }
        
        // منع الحفظ التلقائي
        if (defined('DOING_AUTOSAVE') && DOING_AUTOSAVE) {
            return;
        }
        
        // حفظ معلومات اللعبة
        $text_fields = ['developer', 'publisher', 'release_date'];
        foreach ($text_fields as $field) {
            if (isset($_POST["mcp_{$field}"])) {
                update_post_meta($post_id, "_mcp_{$field}", sanitize_text_field($_POST["mcp_{$field}"]));
            }
        }
        
        // حفظ URLs بشكل آمن
        if (isset($_POST['mcp_official_site'])) {
            update_post_meta($post_id, '_mcp_official_site', esc_url_raw($_POST['mcp_official_site']));
        }
        if (isset($_POST['mcp_trailer'])) {
            update_post_meta($post_id, '_mcp_trailer', esc_url_raw($_POST['mcp_trailer']));
        }
        
        // حفظ المميزات
        for ($i = 1; $i <= 4; $i++) {
            if (isset($_POST["mcp_feature_{$i}"])) {
                update_post_meta($post_id, "_mcp_feature_{$i}", sanitize_text_field($_POST["mcp_feature_{$i}"]));
            }
        }
        
        // حفظ المعرض - validation صحيح للـ IDs
        if (isset($_POST['mcp_gallery']) && !empty($_POST['mcp_gallery'])) {
            // تحويل الـ string إلى array من الـ IDs
            $gallery_raw = explode(',', $_POST['mcp_gallery']);
            
            // تنظيف كل ID: absint فقط للأرقام الصحيحة
            $gallery_ids = array_filter(array_map('absint', $gallery_raw));
            
            // حفظ فقط إذا كان هناك IDs صالحة
            if (!empty($gallery_ids)) {
                update_post_meta($post_id, '_mcp_gallery', implode(',', $gallery_ids));
            } else {
                delete_post_meta($post_id, '_mcp_gallery');
            }
        } else {
            // حذف الـ gallery إذا كان فارغاً
            delete_post_meta($post_id, '_mcp_gallery');
        }
        
        // حفظ التقييمات مع validation محسّن
        $rating_types = ['story', 'gameplay', 'graphics', 'audio'];
        $total = 0;
        $count = 0;
        
        foreach ($rating_types as $type) {
            if (isset($_POST["mcp_rating_{$type}"]) && $_POST["mcp_rating_{$type}"] !== '') {
                $rating = floatval($_POST["mcp_rating_{$type}"]);
                
                // Server-side validation صارم
                if ($rating >= 1 && $rating <= 10 && is_numeric($_POST["mcp_rating_{$type}"])) {
                    // تقريب لرقم عشري واحد
                    $rating = round($rating, 1);
                    
                    // التأكد من أن القيمة في النطاق الصحيح بعد التقريب
                    if ($rating >= 1 && $rating <= 10) {
                        update_post_meta($post_id, "_mcp_rating_{$type}", $rating);
                        $total += $rating;
                        $count++;
                    }
                } else {
                    // حذف التقييم إذا كان غير صالح
                    delete_post_meta($post_id, "_mcp_rating_{$type}");
                }
            }
            
            if (isset($_POST["mcp_rating_{$type}_notes"])) {
                update_post_meta($post_id, "_mcp_rating_{$type}_notes", wp_kses_post($_POST["mcp_rating_{$type}_notes"]));
            }
        }
        
        // حساب Overall Rating
        if ($count > 0) {
            $overall = round($total / $count, 1);
            update_post_meta($post_id, '_mcp_rating_overall', $overall);
        } else {
            // حذف التقييم الإجمالي إذا لم يكن هناك تقييمات
            delete_post_meta($post_id, '_mcp_rating_overall');
        }
    }
}
