<?php
/**
 * Related posts rendering for game single pages.
 *
 * @package Momarab_Core
 */

namespace Momarab_Core;

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Related posts render class.
 */
class MCP_Related_Render {

	/**
	 * Constructor.
	 */
	public function __construct() {
		add_action( 'mcp_single_game_after_content', array( $this, 'render_related_news' ) );
	}

	/**
	 * Render related news section.
	 *
	 * @param int $game_id The game post ID.
	 */
	public function render_related_news( $game_id ) {
		$settings = get_option( 'mcp_settings', array() );
		
		// Check if related news is enabled.
		if ( ! isset( $settings['related_news_enabled'] ) || ! $settings['related_news_enabled'] ) {
			return;
		}

		$related_post = $this->get_related_post( $game_id );

		if ( ! $related_post ) {
			return;
		}

		$title = isset( $settings['related_news_title'] ) ? $settings['related_news_title'] : __( 'آخر خبر عن اللعبة', 'momarab-core' );

		?>
		<div class="mcp-related-news-section">
			<h3 class="mcp-related-news-title"><?php echo esc_html( $title ); ?></h3>
			
			<div class="mcp-related-news-item">
				<?php $this->render_news_item( $related_post ); ?>
			</div>
		</div>
		<?php
	}

	/**
	 * Get the most recent related post for a game.
	 *
	 * @param int $game_id The game post ID.
	 * @return \WP_Post|null Related post or null if none found.
	 */
	private function get_related_post( $game_id ) {
		// Check cache first.
		$cache_key = 'mcp_news_' . $game_id;
		$related_post = get_transient( $cache_key );

		if ( false !== $related_post ) {
			return $related_post;
		}

		$query = new \WP_Query( array(
			'post_type'      => 'post',
			'post_status'    => 'publish',
			'posts_per_page' => 1,
			'orderby'        => 'date',
			'order'          => 'DESC',
			'meta_query'     => array(
				array(
					'key'     => 'mcp_related_game_id',
					'value'   => $game_id,
					'compare' => '=',
				),
			),
		) );

		$related_post = null;
		if ( $query->have_posts() ) {
			$related_post = $query->posts[0];
		}

		// Cache for 10 minutes.
		set_transient( $cache_key, $related_post, 600 );

		return $related_post;
	}

	/**
	 * Render individual news item.
	 *
	 * @param \WP_Post $post The post object.
	 */
	private function render_news_item( $post ) {
		$thumbnail = get_the_post_thumbnail_url( $post->ID, 'mcp-thumb' );
		$excerpt = get_the_excerpt( $post );
		$date = get_the_date( '', $post );
		$author = get_the_author_meta( 'display_name', $post->post_author );

		?>
		<article class="mcp-news-item">
			<?php if ( $thumbnail ) : ?>
				<div class="mcp-news-thumbnail">
					<a href="<?php echo esc_url( get_permalink( $post ) ); ?>">
						<img src="<?php echo esc_url( $thumbnail ); ?>" alt="<?php echo esc_attr( $post->post_title ); ?>" loading="lazy" />
					</a>
				</div>
			<?php endif; ?>

			<div class="mcp-news-content">
				<h4 class="mcp-news-title">
					<a href="<?php echo esc_url( get_permalink( $post ) ); ?>">
						<?php echo esc_html( $post->post_title ); ?>
					</a>
				</h4>

				<div class="mcp-news-meta">
					<span class="mcp-news-date"><?php echo esc_html( $date ); ?></span>
					<?php if ( $author ) : ?>
						<span class="mcp-news-author">
							<?php
							printf(
								/* translators: %s: Author name */
								esc_html__( 'بواسطة %s', 'momarab-core' ),
								esc_html( $author )
							);
							?>
						</span>
					<?php endif; ?>
				</div>

				<?php if ( $excerpt ) : ?>
					<div class="mcp-news-excerpt">
						<?php echo wp_kses_post( $excerpt ); ?>
					</div>
				<?php endif; ?>

				<div class="mcp-news-link">
					<a href="<?php echo esc_url( get_permalink( $post ) ); ?>" class="mcp-read-more">
						<?php esc_html_e( 'اقرأ المزيد', 'momarab-core' ); ?>
					</a>
				</div>
			</div>
		</article>
		<?php
	}

	/**
	 * Get related posts count for a game.
	 *
	 * @param int $game_id The game post ID.
	 * @return int Number of related posts.
	 */
	public static function get_related_posts_count( $game_id ) {
		$query = new \WP_Query( array(
			'post_type'      => 'post',
			'post_status'    => 'publish',
			'posts_per_page' => 100,
			'no_found_rows' => true,
			'update_post_meta_cache' => false,
			'update_post_term_cache' => false,
			'fields'         => 'ids',
			'meta_query'     => array(
				array(
					'key'     => 'mcp_related_game_id',
					'value'   => $game_id,
					'compare' => '=',
				),
			),
		) );

		return $query->found_posts;
	}

	/**
	 * Get all related posts for a game.
	 *
	 * @param int $game_id The game post ID.
	 * @param int $limit   Number of posts to retrieve.
	 * @return array Array of post objects.
	 */
	public static function get_all_related_posts( $game_id, $limit = 10 ) {
		$limit = min( $limit, 50 ); // Enforce max 50.

		$query = new \WP_Query( array(
			'post_type'      => 'post',
			'post_status'    => 'publish',
			'posts_per_page' => $limit,
			'orderby'        => 'date',
			'order'          => 'DESC',
			'meta_query'     => array(
				array(
					'key'     => 'mcp_related_game_id',
					'value'   => $game_id,
					'compare' => '=',
				),
			),
		) );

		return $query->posts;
	}
}
