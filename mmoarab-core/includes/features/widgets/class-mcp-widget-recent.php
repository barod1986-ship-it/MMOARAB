<?php
/**
 * Recent Games widget.
 *
 * @package Momarab_Core
 */

namespace Momarab_Core;

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Recent Games widget class.
 */
class MCP_Widget_Recent extends \WP_Widget {

	/**
	 * Constructor.
	 */
	public function __construct() {
		parent::__construct(
			'mcp_recent_games',
			__( 'الألعاب الحديثة', 'momarab-core' ),
			array(
				'description' => __( 'عرض أحدث الألعاب المضافة', 'momarab-core' ),
			)
		);
	}

	/**
	 * Widget output.
	 *
	 * @param array $args     Widget arguments.
	 * @param array $instance Widget instance.
	 */
	public function widget( $args, $instance ) {
		$title = ! empty( $instance['title'] ) ? $instance['title'] : __( 'الألعاب الحديثة', 'momarab-core' );
		$number = ! empty( $instance['number'] ) ? absint( $instance['number'] ) : 5;
		$number = min( $number, 50 ); // Enforce max 50.

		// Get cached results.
		$cache_key = 'mcp_widget_recent_' . $number;
		$games = get_transient( $cache_key );

		if ( false === $games ) {
			$games = $this->get_recent_games( $number );
			set_transient( $cache_key, $games, 600 ); // Cache for 10 minutes.
		}

		if ( empty( $games ) ) {
			return;
		}

		echo $args['before_widget'];

		if ( $title ) {
			echo $args['before_title'] . esc_html( apply_filters( 'widget_title', $title ) ) . $args['after_title'];
		}

		echo '<ul class="mcp-recent-games-list">';
		foreach ( $games as $game ) {
			$this->render_game_item( $game );
		}
		echo '</ul>';

		echo $args['after_widget'];
	}

	/**
	 * Widget form.
	 *
	 * @param array $instance Widget instance.
	 */
	public function form( $instance ) {
		$title = ! empty( $instance['title'] ) ? $instance['title'] : __( 'الألعاب الحديثة', 'momarab-core' );
		$number = ! empty( $instance['number'] ) ? absint( $instance['number'] ) : 5;
		?>
		<p>
			<label for="<?php echo esc_attr( $this->get_field_id( 'title' ) ); ?>"><?php esc_html_e( 'العنوان:', 'momarab-core' ); ?></label>
			<input class="widefat" id="<?php echo esc_attr( $this->get_field_id( 'title' ) ); ?>" name="<?php echo esc_attr( $this->get_field_name( 'title' ) ); ?>" type="text" value="<?php echo esc_attr( $title ); ?>" />
		</p>

		<p>
			<label for="<?php echo esc_attr( $this->get_field_id( 'number' ) ); ?>"><?php esc_html_e( 'عدد الألعاب:', 'momarab-core' ); ?></label>
			<input class="tiny-text" id="<?php echo esc_attr( $this->get_field_id( 'number' ) ); ?>" name="<?php echo esc_attr( $this->get_field_name( 'number' ) ); ?>" type="number" step="1" min="1" max="50" value="<?php echo esc_attr( $number ); ?>" size="3" />
		</p>
		<?php
	}

	/**
	 * Update widget instance.
	 *
	 * @param array $new_instance New instance.
	 * @param array $old_instance Old instance.
	 * @return array Updated instance.
	 */
	public function update( $new_instance, $old_instance ) {
		$instance = array();
		$instance['title'] = ! empty( $new_instance['title'] ) ? sanitize_text_field( $new_instance['title'] ) : '';
		$instance['number'] = ! empty( $new_instance['number'] ) ? absint( $new_instance['number'] ) : 5;
		$instance['number'] = min( $instance['number'], 50 ); // Enforce max 50.

		// Clear cache when widget is updated.
		$this->clear_cache();

		return $instance;
	}

	/**
	 * Get recent games.
	 *
	 * @param int $number Number of games to get.
	 * @return array Games data.
	 */
	private function get_recent_games( $number ) {
		$query = new \WP_Query( array(
			'post_type'      => 'games',
			'post_status'    => 'publish',
			'posts_per_page' => $number,
			'orderby'        => 'date',
			'order'          => 'DESC',
		) );

		$games = array();
		if ( $query->have_posts() ) {
			while ( $query->have_posts() ) {
				$query->the_post();
				$post_id = get_the_ID();

				$games[] = array(
					'id'        => $post_id,
					'title'     => get_the_title(),
					'permalink' => get_permalink(),
					'thumbnail' => get_the_post_thumbnail_url( $post_id, 'mcp-thumb' ),
					'date'      => get_the_date(),
					'developer' => get_post_meta( $post_id, 'mcp_developer', true ),
					'rating'    => get_post_meta( $post_id, 'mcp_rating_overall', true ),
				);
			}
			wp_reset_postdata();
		}

		return $games;
	}

	/**
	 * Render individual game item.
	 *
	 * @param array $game Game data.
	 */
	private function render_game_item( $game ) {
		?>
		<li class="mcp-recent-game-item">
			<div class="mcp-game-thumb">
				<?php if ( $game['thumbnail'] ) : ?>
					<a href="<?php echo esc_url( $game['permalink'] ); ?>">
						<img src="<?php echo esc_url( $game['thumbnail'] ); ?>" alt="<?php echo esc_attr( $game['title'] ); ?>" loading="lazy" />
					</a>
				<?php endif; ?>
			</div>

			<div class="mcp-game-info">
				<h4 class="mcp-game-title">
					<a href="<?php echo esc_url( $game['permalink'] ); ?>">
						<?php echo esc_html( $game['title'] ); ?>
					</a>
				</h4>

				<p class="mcp-game-date">
					<?php echo esc_html( $game['date'] ); ?>
				</p>

				<?php if ( $game['developer'] ) : ?>
					<p class="mcp-game-developer"><?php echo esc_html( $game['developer'] ); ?></p>
				<?php endif; ?>

				<?php if ( $game['rating'] ) : ?>
					<div class="mcp-game-rating">
						<span class="mcp-rating-value"><?php echo esc_html( number_format( $game['rating'], 1 ) ); ?></span>
						<span class="mcp-rating-max">/10</span>
					</div>
				<?php endif; ?>
			</div>
		</li>
		<?php
	}

	/**
	 * Clear widget cache.
	 */
	private function clear_cache() {
		global $wpdb;

		$transients = $wpdb->get_results(
			"SELECT option_name FROM {$wpdb->options} WHERE option_name LIKE '_transient_mcp_widget_recent_%'"
		);

		foreach ( $transients as $transient ) {
			$key = str_replace( '_transient_', '', $transient->option_name );
			delete_transient( $key );
		}
	}
}
