<?php
/**
 * Template: Single Game
 * 
 * @package MMOARAB_Core
 */

get_header();
?>

<main id="main" class="site-main">
  <div class="ct-container">
    <div class="ct-row">
      <div class="ct-col-12">

<?php
while (have_posts()) : the_post();
    
    // Get meta data with sanitization
    $developer = sanitize_text_field(get_post_meta(get_the_ID(), '_mcp_developer', true));
    $publisher = sanitize_text_field(get_post_meta(get_the_ID(), '_mcp_publisher', true));
    $release_date = sanitize_text_field(get_post_meta(get_the_ID(), '_mcp_release_date', true));
    $official_site = esc_url_raw(get_post_meta(get_the_ID(), '_mcp_official_site', true));
    $trailer = esc_url_raw(get_post_meta(get_the_ID(), '_mcp_trailer', true));
    $gallery = get_post_meta(get_the_ID(), '_mcp_gallery', true);
    
    // Ratings with validation
    $ratings = [
        'story' => floatval(get_post_meta(get_the_ID(), '_mcp_rating_story', true)),
        'gameplay' => floatval(get_post_meta(get_the_ID(), '_mcp_rating_gameplay', true)),
        'graphics' => floatval(get_post_meta(get_the_ID(), '_mcp_rating_graphics', true)),
        'audio' => floatval(get_post_meta(get_the_ID(), '_mcp_rating_audio', true)),
    ];
    
    $overall = floatval(get_post_meta(get_the_ID(), '_mcp_rating_overall', true));
    
    // Features
    $features = [];
    for ($i = 1; $i <= 4; $i++) {
        $feature = sanitize_text_field(get_post_meta(get_the_ID(), "_mcp_feature_{$i}", true));
        if ($feature) {
            $features[] = $feature;
        }
    }
    
    // Taxonomies
    $types = get_the_terms(get_the_ID(), 'game_type');
    $statuses = get_the_terms(get_the_ID(), 'game_status');
    $modes = get_the_terms(get_the_ID(), 'game_mode');
    $platforms = get_the_terms(get_the_ID(), 'game_platform');
    $engines = get_the_terms(get_the_ID(), 'game_engine');
?>

<div class="mcp-single-game">
    
    <!-- Game Header -->
    <header class="mcp-game-header">
        <?php if (has_post_thumbnail()) : ?>
            <div class="mcp-game-thumbnail">
                <?php the_post_thumbnail('large', ['loading' => 'eager']); ?>
            </div>
        <?php endif; ?>
    </header>
    
    <!-- Quick Info Bar -->
    <div class="mcp-quick-info-bar">
        <div class="mcp-quick-info-content">
            <h1 class="mcp-game-title"><?php the_title(); ?></h1>
            
            <?php if ($overall && $overall > 0) : 
                $fill_percentage = ($overall / 10) * 100;
            ?>
                <div class="mcp-quick-rating">
                    <div class="mcp-rating-star-wrapper">
                        <svg class="mcp-star-svg" viewBox="0 0 100 100" width="45" height="45">
                            <defs>
                                <linearGradient id="starGradient" x1="0%" y1="0%" x2="100%" y2="0%">
                                    <stop offset="<?php echo esc_attr($fill_percentage); ?>%" style="stop-color:#FFD700;stop-opacity:1" />
                                    <stop offset="<?php echo esc_attr($fill_percentage); ?>%" style="stop-color:#555;stop-opacity:1" />
                                </linearGradient>
                            </defs>
                            <path d="M50,10 L61,40 L92,40 L67,58 L78,88 L50,70 L22,88 L33,58 L8,40 L39,40 Z" 
                                  fill="url(#starGradient)" 
                                  stroke="#FFD700" 
                                  stroke-width="2"/>
                        </svg>
                    </div>
                    <div class="mcp-rating-text">
                        <span class="mcp-rating-value"><?php echo esc_html(number_format($overall, 1)); ?></span>
                        <span class="mcp-rating-max">/10</span>
                    </div>
                </div>
            <?php endif; ?>
            
            <?php if ($official_site) : ?>
                <a href="<?php echo esc_url($official_site); ?>" class="mcp-quick-website" target="_blank" rel="noopener noreferrer">
                    <span class="mcp-website-icon">&#127760;</span>
                    <span><?php _e('Official Website', 'mmoarab-core'); ?></span>
                </a>
            <?php endif; ?>
        </div>
    </div>
    
    <!-- Game Information -->
    <?php if ($developer || $publisher || $release_date || $official_site || $types || $statuses || $modes || $platforms || $engines) : ?>
        <section class="mcp-game-section">
            <h2><?php _e('Game Information', 'mmoarab-core'); ?></h2>
            
            <div class="mcp-game-info-grid">
                
                <?php if ($developer) : ?>
                    <div class="mcp-info-item">
                        <div class="mcp-info-item-label">
                            <span class="emoji">&#128104;&#8205;&#128187;</span>
                            <?php _e('Developer', 'mmoarab-core'); ?>
                        </div>
                        <div class="mcp-info-item-value"><?php echo esc_html($developer); ?></div>
                    </div>
                <?php endif; ?>
                
                <?php if ($publisher) : ?>
                    <div class="mcp-info-item">
                        <div class="mcp-info-item-label">
                            <span class="emoji">&#127970;</span>
                            <?php _e('Publisher', 'mmoarab-core'); ?>
                        </div>
                        <div class="mcp-info-item-value"><?php echo esc_html($publisher); ?></div>
                    </div>
                <?php endif; ?>
                
                <?php if ($release_date) : 
                    $formatted_date = '';
                    $timestamp = strtotime($release_date);
                    if ($timestamp !== false) {
                        $formatted_date = date_i18n(get_option('date_format'), $timestamp);
                    } else {
                        $formatted_date = esc_html($release_date);
                    }
                ?>
                    <div class="mcp-info-item">
                        <div class="mcp-info-item-label">
                            <span class="emoji">&#128197;</span>
                            <?php _e('Release Date', 'mmoarab-core'); ?>
                        </div>
                        <div class="mcp-info-item-value"><?php echo $formatted_date; ?></div>
                    </div>
                <?php endif; ?>
                
                <?php if ($types && !is_wp_error($types)) : ?>
                    <div class="mcp-info-item">
                        <div class="mcp-info-item-label">
                            <span class="emoji">&#127918;</span>
                            <?php _e('Game Type', 'mmoarab-core'); ?>
                        </div>
                        <div class="mcp-info-item-value">
                            <?php echo esc_html(implode(', ', wp_list_pluck($types, 'name'))); ?>
                        </div>
                    </div>
                <?php endif; ?>
                
                <?php if ($statuses && !is_wp_error($statuses)) : ?>
                    <div class="mcp-info-item">
                        <div class="mcp-info-item-label">
                            <span class="emoji">&#9989;</span>
                            <?php _e('Status', 'mmoarab-core'); ?>
                        </div>
                        <div class="mcp-info-item-value">
                            <?php echo esc_html(implode(', ', wp_list_pluck($statuses, 'name'))); ?>
                        </div>
                    </div>
                <?php endif; ?>
                
                <?php if ($modes && !is_wp_error($modes)) : ?>
                    <div class="mcp-info-item">
                        <div class="mcp-info-item-label">
                            <span class="emoji">&#128377;&#65039;</span>
                            <?php _e('Game Mode', 'mmoarab-core'); ?>
                        </div>
                        <div class="mcp-info-item-value">
                            <?php echo esc_html(implode(', ', wp_list_pluck($modes, 'name'))); ?>
                        </div>
                    </div>
                <?php endif; ?>
                
                <?php if ($platforms && !is_wp_error($platforms)) : ?>
                    <div class="mcp-info-item">
                        <div class="mcp-info-item-label">
                            <span class="emoji">&#128187;</span>
                            <?php _e('Platforms', 'mmoarab-core'); ?>
                        </div>
                        <div class="mcp-info-item-value">
                            <?php echo esc_html(implode(', ', wp_list_pluck($platforms, 'name'))); ?>
                        </div>
                    </div>
                <?php endif; ?>
                
                <?php if ($engines && !is_wp_error($engines)) : ?>
                    <div class="mcp-info-item">
                        <div class="mcp-info-item-label">
                            <span class="emoji">&#9881;&#65039;</span>
                            <?php _e('Game Engine', 'mmoarab-core'); ?>
                        </div>
                        <div class="mcp-info-item-value">
                            <?php echo esc_html(implode(', ', wp_list_pluck($engines, 'name'))); ?>
                        </div>
                    </div>
                <?php endif; ?>
                
            </div>
        </section>
    <?php endif; ?>
    
    <!-- Features -->
    <?php if (!empty($features)) : ?>
        <section class="mcp-game-section">
            <h2><?php _e('Game Features', 'mmoarab-core'); ?></h2>
            <ul class="mcp-game-features-list">
                <?php foreach ($features as $feature) : ?>
                    <li><?php echo esc_html($feature); ?></li>
                <?php endforeach; ?>
            </ul>
        </section>
    <?php endif; ?>
    
    <!-- About Game Container -->
    <?php if (get_the_content()) : ?>
        <div class="mcp-media-container">
            <section class="mcp-game-section">
                <h2><?php _e('About the Game', 'mmoarab-core'); ?></h2>
                <div class="mcp-game-content">
                    <?php the_content(); ?>
                </div>
            </section>
        </div>
    <?php endif; ?>
    
    <!-- Ratings -->
    <?php if (array_filter($ratings) || $overall) : ?>
        <section class="mcp-game-section">
            <h2><?php _e('Ratings', 'mmoarab-core'); ?></h2>
            
            <div class="mcp-ratings-grid">
                
                <?php 
                $rating_labels = [
                    'story' => ['label' => __('Story', 'mmoarab-core'), 'icon' => '&#128214;'],
                    'gameplay' => ['label' => __('Gameplay', 'mmoarab-core'), 'icon' => '&#127918;'],
                    'graphics' => ['label' => __('Graphics', 'mmoarab-core'), 'icon' => '&#127912;'],
                    'audio' => ['label' => __('Audio', 'mmoarab-core'), 'icon' => '&#127925;'],
                ];
                
                foreach ($rating_labels as $key => $data) :
                    if (!empty($ratings[$key]) && $ratings[$key] > 0) :
                        $notes = sanitize_textarea_field(get_post_meta(get_the_ID(), "_mcp_rating_{$key}_notes", true));
                ?>
                    <div class="mcp-rating-item">
                        <div class="mcp-rating-header">
                            <span class="mcp-rating-label">
                                <span class="mcp-rating-icon"><?php echo $data['icon']; ?></span>
                                <?php echo esc_html($data['label']); ?>
                            </span>
                            <span class="mcp-rating-value"><?php echo esc_html($ratings[$key]); ?>/10</span>
                        </div>
                        <div class="mcp-rating-bar">
                            <div class="mcp-rating-fill" style="width: <?php echo esc_attr($ratings[$key] * 10); ?>%"></div>
                        </div>
                        <?php if ($notes) : ?>
                            <p class="mcp-rating-notes"><?php echo esc_html($notes); ?></p>
                        <?php endif; ?>
                    </div>
                <?php 
                    endif;
                endforeach; 
                ?>
                
            </div>
            
            <?php if ($overall && $overall > 0) : 
                $stars = floor($overall);
                $half = ($overall - $stars) >= 0.5 ? 1 : 0;
                $empty = 10 - $stars - $half;
            ?>
                <div class="mcp-overall-rating">
                    <div class="mcp-overall-label"><?php _e('Final Rating', 'mmoarab-core'); ?></div>
                    <div class="mcp-overall-value"><?php echo esc_html(number_format($overall, 1)); ?><span class="mcp-rating-out-of">/10</span></div>
                    <div class="mcp-overall-stars">
                        <?php 
                        $stars_html = array();
                        for ($i = 0; $i < $stars; $i++) {
                            $stars_html[] = '<span class="mcp-star full">&#9733;</span>';
                        }
                        if ($half) {
                            $stars_html[] = '<span class="mcp-star half">&#9733;</span>';
                        }
                        for ($i = 0; $i < $empty; $i++) {
                            $stars_html[] = '<span class="mcp-star">&#9733;</span>';
                        }
                        echo implode('', $stars_html);
                        ?>
                    </div>
                </div>
            <?php endif; ?>
            
        </section>
    <?php endif; ?>
    
    <!-- Trailer Container -->
    <?php if ($trailer) : ?>
        <div class="mcp-media-container">
            <section class="mcp-game-section">
                <h2><?php _e('Trailer', 'mmoarab-core'); ?></h2>
                
                <?php 
                // Convert YouTube URL to embed
                $embed_url = '';
                $video_id = '';
                
                if (preg_match('/(?:youtube\.com\/(?:[^\/]+\/.+\/|(?:v|e(?:mbed)?)\/|.*[?&]v=)|youtu\.be\/)([^"&?\/\s]{11})/i', $trailer, $match) && isset($match[1])) {
                    $video_id = $match[1];
                }
                
                if ($video_id) {
                    $embed_url = 'https://www.youtube.com/embed/' . esc_attr($video_id);
                }
                
                if ($embed_url) : ?>
                    <div class="mcp-game-trailer">
                        <iframe src="<?php echo esc_url($embed_url); ?>" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>
                    </div>
                <?php else : ?>
                    <a href="<?php echo esc_url($trailer); ?>" class="mcp-trailer-button" target="_blank" rel="noopener noreferrer">
                        <?php _e('Watch Trailer', 'mmoarab-core'); ?>
                    </a>
                <?php endif; ?>
            </section>
        </div>
    <?php endif; ?>
    
    <!-- Gallery Container -->
    <?php if ($gallery && is_string($gallery)) : 
        $gallery_ids = array_filter(array_map('absint', explode(',', $gallery)));
        if (!empty($gallery_ids)) :
    ?>
        <div class="mcp-media-container">
            <section class="mcp-game-section">
                <h2><?php _e('Gallery', 'mmoarab-core'); ?></h2>
                
                <div class="mcp-game-gallery-grid">
                    <?php 
                    $gallery_images = array();
                    foreach ($gallery_ids as $image_id) : 
                        if (!$image_id || !is_numeric($image_id)) {
                            continue;
                        }
                        
                        // Verify attachment exists
                        if (get_post_type($image_id) !== 'attachment') {
                            continue;
                        }
                        
                        $image = wp_get_attachment_image_src($image_id, 'medium');
                        $full_image = wp_get_attachment_image_src($image_id, 'full');
                        
                        if ($image && $full_image) :
                            $image_alt = get_post_meta($image_id, '_wp_attachment_image_alt', true);
                            $gallery_images[] = esc_url($full_image[0]);
                    ?>
                        <div class="mcp-gallery-item" data-index="<?php echo count($gallery_images) - 1; ?>">
                            <img src="<?php echo esc_url($image[0]); ?>" 
                                 data-full="<?php echo esc_url($full_image[0]); ?>" 
                                 alt="<?php echo esc_attr($image_alt ? $image_alt : get_the_title()); ?>"
                                 loading="lazy">
                        </div>
                    <?php 
                        endif;
                    endforeach; ?>
                </div>
                
                <!-- Lightbox -->
                <div class="mcp-lightbox">
                    <button class="mcp-lightbox-close" aria-label="<?php esc_attr_e('Close', 'mmoarab-core'); ?>">&times;</button>
                    <button class="mcp-lightbox-prev" aria-label="<?php esc_attr_e('Previous', 'mmoarab-core'); ?>">&#8249;</button>
                    <div class="mcp-lightbox-content">
                        <img src="" alt="" class="mcp-lightbox-image">
                    </div>
                    <button class="mcp-lightbox-next" aria-label="<?php esc_attr_e('Next', 'mmoarab-core'); ?>">&#8250;</button>
                </div>
                
                <script>
                (function() {
                    const galleryItems = document.querySelectorAll('.mcp-gallery-item');
                    const lightbox = document.querySelector('.mcp-lightbox');
                    const lightboxImg = document.querySelector('.mcp-lightbox-image');
                    const closeBtn = document.querySelector('.mcp-lightbox-close');
                    const prevBtn = document.querySelector('.mcp-lightbox-prev');
                    const nextBtn = document.querySelector('.mcp-lightbox-next');
                    
                    if (!lightbox || !lightboxImg) return;
                    
                    const images = <?php echo json_encode($gallery_images); ?>;
                    let currentIndex = 0;
                    
                    function openLightbox(index) {
                        currentIndex = index;
                        lightboxImg.src = images[currentIndex];
                        lightbox.classList.add('active');
                        document.body.style.overflow = 'hidden';
                    }
                    
                    function closeLightbox() {
                        lightbox.classList.remove('active');
                        document.body.style.overflow = '';
                    }
                    
                    function showNext() {
                        currentIndex = (currentIndex + 1) % images.length;
                        lightboxImg.src = images[currentIndex];
                    }
                    
                    function showPrev() {
                        currentIndex = (currentIndex - 1 + images.length) % images.length;
                        lightboxImg.src = images[currentIndex];
                    }
                    
                    galleryItems.forEach((item, index) => {
                        item.addEventListener('click', () => openLightbox(index));
                    });
                    
                    if (closeBtn) closeBtn.addEventListener('click', closeLightbox);
                    if (nextBtn) nextBtn.addEventListener('click', showNext);
                    if (prevBtn) prevBtn.addEventListener('click', showPrev);
                    
                    lightbox.addEventListener('click', (e) => {
                        if (e.target === lightbox) closeLightbox();
                    });
                    
                    document.addEventListener('keydown', (e) => {
                        if (!lightbox.classList.contains('active')) return;
                        if (e.key === 'Escape') closeLightbox();
                        if (e.key === 'ArrowRight') showNext();
                        if (e.key === 'ArrowLeft') showPrev();
                    });
                })();
                </script>
            </section>
        </div>
    <?php 
        endif;
    endif; ?>
    
    <!-- Related Posts Container -->
    <?php
    $cache_key = 'mcp_related_posts_' . get_the_ID();
    $related_posts_ids = get_transient($cache_key);
    
    if (false === $related_posts_ids) {
        $related_posts = new WP_Query([
            'post_type' => 'post',
            'posts_per_page' => 3,
            'fields' => 'ids',
            'post_status' => 'publish',
            'ignore_sticky_posts' => true,
            'no_found_rows' => true,
            'meta_query' => [
                [
                    'key' => '_mcp_related_game_id',
                    'value' => get_the_ID(),
                    'compare' => '='
                ]
            ]
        ]);
        
        $related_posts_ids = $related_posts->posts;
        set_transient($cache_key, $related_posts_ids, HOUR_IN_SECONDS);
        wp_reset_postdata();
    }
    
    if (!empty($related_posts_ids)) :
        $related_posts = new WP_Query([
            'post_type' => 'post',
            'post__in' => $related_posts_ids,
            'orderby' => 'post__in',
            'posts_per_page' => 3,
            'post_status' => 'publish',
            'no_found_rows' => true
        ]);
    
    if ($related_posts->have_posts()) :
    ?>
        <div class="mcp-media-container">
            <section class="mcp-game-section">
                <h2><?php _e('Latest Game News', 'mmoarab-core'); ?></h2>
                
                <div class="mcp-related-posts-grid">
                    <?php while ($related_posts->have_posts()) : $related_posts->the_post(); ?>
                        <article class="mcp-related-post-card">
                            <div class="mcp-related-post-thumbnail">
                                <a href="<?php the_permalink(); ?>">
                                    <?php if (has_post_thumbnail()) : ?>
                                        <?php the_post_thumbnail('medium', ['loading' => 'lazy']); ?>
                                    <?php else : ?>
                                        <div class="mcp-no-thumbnail">
                                            <span>&#128240;</span>
                                        </div>
                                    <?php endif; ?>
                                </a>
                            </div>
                        
                        <div class="mcp-related-post-content">
                            <h3 class="mcp-related-post-title">
                                <a href="<?php the_permalink(); ?>"><?php the_title(); ?></a>
                            </h3>
                            <div class="mcp-related-post-date">
                                <?php echo esc_html(get_the_date()); ?>
                            </div>
                            <div class="mcp-related-post-excerpt">
                                <?php echo esc_html(wp_trim_words(get_the_excerpt(), 15)); ?>
                            </div>
                        </div>
                    </article>
                <?php endwhile; wp_reset_postdata(); ?>
            </div>
        </section>
        </div>
    <?php 
        endif;
    endif; ?>
    
    <!-- Comments -->
    <?php if (comments_open() || get_comments_number()) : ?>
        <section class="mcp-game-section mcp-comments-section">
            <?php comments_template(); ?>
        </section>
    <?php endif; ?>
    
</div>

<?php
endwhile;
?>

      </div>
    </div>
  </div>
</main>

<?php
get_footer();