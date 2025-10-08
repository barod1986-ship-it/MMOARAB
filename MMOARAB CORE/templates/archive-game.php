<?php
/**
 * Template: Archive Games (Optimized)
 * @package MMOAR_Core
 */

get_header();
?>

<main id="main" class="site-main mcp-archive-games">
  <div class="ct-container">
    <div class="ct-row">
      <div class="ct-col-12">

        <!-- Archive Header -->
        <div class="mcp-archive-header">
          <h1><?php _e('Games', 'mmoarab-core'); ?></h1>
          <p class="mcp-archive-count">
            <?php
            global $wp_query;
            printf(
              _n('Found %s game', 'Found %s games', $wp_query->found_posts, 'mmoarab-core'),
              number_format_i18n($wp_query->found_posts)
            );
            ?>
          </p>
        </div>

        <!-- Filters -->
        <div class="mcp-filters-container">
          <form class="mcp-filters-form" method="get">
            <div class="mcp-filter-field">
              <input type="text" name="s" placeholder="<?php esc_attr_e('Search games...', 'mmoarab-core'); ?>" value="<?php echo esc_attr(get_search_query()); ?>">
            </div>

            <div class="mcp-filter-field">
              <select name="game_type">
                <option value=""><?php _e('All Types', 'mmoarab-core'); ?></option>
                <?php
                $types = get_terms(['taxonomy' => 'game_type', 'hide_empty' => true]);
                $selected_type = get_query_var('game_type');
                if (!is_wp_error($types) && !empty($types)) {
                  foreach ($types as $type) {
                    printf(
                      '<option value="%s"%s>%s</option>',
                      esc_attr($type->slug),
                      selected($selected_type, $type->slug, false),
                      esc_html($type->name)
                    );
                  }
                }
                ?>
              </select>
            </div>

            <div class="mcp-filter-field">
              <select name="game_status">
                <option value=""><?php _e('All Status', 'mmoarab-core'); ?></option>
                <?php
                $statuses = get_terms(['taxonomy' => 'game_status', 'hide_empty' => true]);
                $selected_status = get_query_var('game_status');
                if (!is_wp_error($statuses) && !empty($statuses)) {
                  foreach ($statuses as $status) {
                    printf(
                      '<option value="%s"%s>%s</option>',
                      esc_attr($status->slug),
                      selected($selected_status, $status->slug, false),
                      esc_html($status->name)
                    );
                  }
                }
                ?>
              </select>
            </div>

            <div class="mcp-filter-field">
              <select name="game_platform">
                <option value=""><?php _e('All Platforms', 'mmoarab-core'); ?></option>
                <?php
                $platforms = get_terms(['taxonomy' => 'game_platform', 'hide_empty' => true]);
                $selected_platform = get_query_var('game_platform');
                if (!is_wp_error($platforms) && !empty($platforms)) {
                  foreach ($platforms as $platform) {
                    printf(
                      '<option value="%s"%s>%s</option>',
                      esc_attr($platform->slug),
                      selected($selected_platform, $platform->slug, false),
                      esc_html($platform->name)
                    );
                  }
                }
                ?>
              </select>
            </div>

            <div class="mcp-filter-field">
              <select name="game_mode">
                <option value=""><?php _e('All Modes', 'mmoarab-core'); ?></option>
                <?php
                $modes = get_terms(['taxonomy' => 'game_mode', 'hide_empty' => true]);
                $selected_mode = get_query_var('game_mode');
                if (!is_wp_error($modes) && !empty($modes)) {
                  foreach ($modes as $mode) {
                    printf(
                      '<option value="%s"%s>%s</option>',
                      esc_attr($mode->slug),
                      selected($selected_mode, $mode->slug, false),
                      esc_html($mode->name)
                    );
                  }
                }
                ?>
              </select>
            </div>

            <div class="mcp-filter-field">
              <select name="game_engine">
                <option value=""><?php _e('All Engines', 'mmoarab-core'); ?></option>
                <?php
                $engines = get_terms(['taxonomy' => 'game_engine', 'hide_empty' => true]);
                $selected_engine = get_query_var('game_engine');
                if (!is_wp_error($engines) && !empty($engines)) {
                  foreach ($engines as $engine) {
                    printf(
                      '<option value="%s"%s>%s</option>',
                      esc_attr($engine->slug),
                      selected($selected_engine, $engine->slug, false),
                      esc_html($engine->name)
                    );
                  }
                }
                ?>
              </select>
            </div>

            <div class="mcp-filter-buttons">
              <button type="submit" class="mcp-filter-submit"><?php _e('Filter', 'mmoarab-core'); ?></button>
              <a href="<?php echo esc_url(get_post_type_archive_link('game')); ?>" class="mcp-filter-reset"><?php _e('Reset', 'mmoarab-core'); ?></a>
            </div>
          </form>
        </div>

        <?php if (have_posts()) : ?>
          <!-- Games Grid -->
          <div class="mcp-games-grid">
            <?php while (have_posts()) : the_post();
              $overall = get_post_meta(get_the_ID(), '_mcp_rating_overall', true);
              $types = get_the_terms(get_the_ID(), 'game_type');
            ?>
              <article class="mcp-game-card">
                <div class="mcp-game-card-image">
                  <a href="<?php the_permalink(); ?>">
                    <?php if (has_post_thumbnail()) : ?>
                      <?php 
                      // استخدام حجم صورة أصغر (medium بدلاً من large)
                      the_post_thumbnail('medium', [
                        'loading' => 'lazy',
                        'decoding' => 'async',
                        'fetchpriority' => 'low'
                      ]); 
                      ?>
                    <?php else : ?>
                      <div class="mcp-no-thumbnail" style="background: linear-gradient(135deg, #2d2d2d 0%, #1a1a1a 100%); min-height: 200px; display: flex; align-items: center; justify-content: center; font-size: 3em;">🎮</div>
                    <?php endif; ?>
                  </a>
                  <?php if ($overall) : ?>
                    <div class="mcp-game-rating-badge"><?php echo esc_html($overall); ?>/10 ⭐</div>
                  <?php endif; ?>
                </div>

                <div class="mcp-game-card-content">
                  <h3 class="mcp-game-card-title"><a href="<?php the_permalink(); ?>"><?php the_title(); ?></a></h3>
                  <?php if ($types && !is_wp_error($types)) : ?>
                    <div class="mcp-game-card-tags">
                      <?php foreach ($types as $type) : ?>
                        <a href="<?php echo esc_url(add_query_arg('game_type', $type->slug, get_post_type_archive_link('game'))); ?>" class="mcp-game-tag"><?php echo esc_html($type->name); ?></a>
                      <?php endforeach; ?>
                    </div>
                  <?php endif; ?>
                </div>
              </article>
            <?php endwhile; ?>
          </div>

          <!-- Pagination (Blocksy-compatible) -->
          <div class="mcp-archive-pagination">
            <?php
            the_posts_pagination([
              'mid_size'  => 1,
              'prev_text' => __('Previous', 'mmoarab-core'),
              'next_text' => __('Next', 'mmoarab-core'),
            ]);
            ?>
          </div>

        <?php else : ?>
          <!-- No Results -->
          <div class="mcp-no-results">
            <h2><?php _e('No games found', 'mmoarab-core'); ?></h2>
            <p><?php _e('Try adjusting your filters or search terms.', 'mmoarab-core'); ?></p>
          </div>
        <?php endif; ?>

      </div>
    </div>
  </div>
</main>

<?php get_footer(); ?>