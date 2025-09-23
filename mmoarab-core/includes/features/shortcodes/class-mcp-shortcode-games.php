<?php
/**
 * Games shortcode functionality.
 *
 * @package Momarab_Core
 */

namespace Momarab_Core;

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Games shortcode class.
 */
class MCP_Shortcode_Games {

	/**
	 * Constructor.
	 */
	public function __construct() {
		add_shortcode( 'momarab_games', array( $this, 'render_shortcode' ) );
	}

	/**
	 * Render games shortcode.
	 *
	 * @param array $atts Shortcode attributes.
	 * @return string Shortcode output.
	 */
	public function render_shortcode( $atts ) {
		$atts = shortcode_atts( array(
			'limit'    => 12,
			'order'    => 'newest',
			'type'     => '',
			'status'   => '',
			'mode'     => '',
			'platform' => '',
		), $atts, 'momarab_games' );

		// Sanitize and validate attributes.
		$limit = min( max( 1, intval( $atts['limit'] ) ), 50 ); // Enforce max 50.
		$order = $this->validate_order( $atts['order'] );

		// Build query arguments.
		$query_args = array(
			'post_type'      => 'games',
			'post_status'    => 'publish',
			'posts_per_page' => $limit,
			'tax_query'      => array(),
		);

		// Add taxonomy filters.
		$this->add_taxonomy_filters( $query_args, $atts );

		// Add ordering.
		$this->add_ordering( $query_args, $order );

		// Get cached results or query.
		$cache_key = 'mcp_shortcode_' . md5( serialize( $query_args ) );
		$output = get_transient( $cache_key );

		if ( false === $output ) {
			$query = new \WP_Query( $query_args );
			$output = $this->generate_output( $query, $atts );
			
			// Cache for 10 minutes.
			set_transient( $cache_key, $output, 600 );
		}

		return $output;
	}

	/**
	 * Validate order parameter.
	 *
	 * @param string $order Order parameter.
	 * @return string Valid order.
	 */
	private function validate_order( $order ) {
		$allowed_orders = array( 'newest', 'oldest', 'az', 'za', 'toprated' );
		return in_array( $order, $allowed_orders, true ) ? $order : 'newest';
	}

	/**
	 * Add taxonomy filters to query.
	 *
	 * @param array $query_args Query arguments.
	 * @param array $atts       Shortcode attributes.
	 */
	private function add_taxonomy_filters( &$query_args, $atts ) {
		$tax_map = array(
			'type'     => 'game_type',
			'status'   => 'game_status',
			'mode'     => 'game_mode',
			'platform' => 'game_platform',
		);

		foreach ( $tax_map as $attr => $taxonomy ) {
			if ( ! empty( $atts[ $attr ] ) ) {
				$terms = array_map( 'trim', explode( ',', $atts[ $attr ] ) );
				$terms = array_filter( $terms );

				if ( ! empty( $terms ) ) {
					$query_args['tax_query'][] = array(
						'taxonomy' => $taxonomy,
						'field'    => 'slug',
						'terms'    => $terms,
						'operator' => 'IN',
					);
				}
			}
		}

		// Set relation if multiple taxonomies.
		if ( count( $query_args['tax_query'] ) > 1 ) {
			$query_args['tax_query']['relation'] = 'AND';
		}
	}

	/**
	 * Add ordering to query.
	 *
	 * @param array  $query_args Query arguments.
	 * @param string $order      Order type.
	 */
	private function add_ordering( &$query_args, $order ) {
		switch ( $order ) {
			case 'oldest':
				$query_args['orderby'] = 'date';
				$query_args['order'] = 'ASC';
				break;

			case 'az':
				$query_args['orderby'] = 'title';
				$query_args['order'] = 'ASC';
				break;

			case 'za':
				$query_args['orderby'] = 'title';
				$query_args['order'] = 'DESC';
				break;

			case 'toprated':
				$query_args['meta_key'] = 'mcp_rating_overall';
				$query_args['orderby'] = 'meta_value_num';
				$query_args['order'] = 'DESC';
				$query_args['meta_query'] = array(
					array(
						'key'     => 'mcp_rating_overall',
						'value'   => 0,
						'compare' => '>',
						'type'    => 'NUMERIC',
					),
				);
				break;

			default: // newest
				$query_args['orderby'] = 'date';
				$query_args['order'] = 'DESC';
				break;
		}
	}

	/**
	 * Generate shortcode output.
	 *
	 * @param \WP_Query $query Query object.
	 * @param array     $atts  Shortcode attributes.
	 * @return string Generated output.
	 */
	private function generate_output( $query, $atts ) {
		if ( ! $query->have_posts() ) {
			return '<p class="mcp-no-games">' . esc_html__( 'لم يتم العثور على ألعاب.', 'momarab-core' ) . '</p>';
		}

		ob_start();
		?>
		<div class="mcp-games-grid mcp-shortcode-games">
			<?php while ( $query->have_posts() ) : ?>
				<?php $query->the_post(); ?>
				<div class="mcp-game-card">
					<?php $this->render_game_card( get_the_ID() ); ?>
				</div>
			<?php endwhile; ?>
		</div>
		<?php
		wp_reset_postdata();

		return ob_get_clean();
	}

	/**
	 * Render individual game card.
	 *
	 * @param int $post_id Post ID.
	 */
	private function render_game_card( $post_id ) {
		$thumbnail = get_the_post_thumbnail_url( $post_id, 'mcp-card' );
		$rating = get_post_meta( $post_id, 'mcp_rating_overall', true );
		$developer = get_post_meta( $post_id, 'mcp_developer', true );
		$release_date = get_post_meta( $post_id, 'mcp_release_date', true );

		?>
		<div class="mcp-card-image">
			<?php if ( $thumbnail ) : ?>
				<img src="<?php echo esc_url( $thumbnail ); ?>" alt="<?php echo esc_attr( get_the_title() ); ?>" loading="lazy" />
			<?php else : ?>
				<div class="mcp-placeholder-image">
					<span><?php esc_html_e( 'لا توجد صورة', 'momarab-core' ); ?></span>
				</div>
			<?php endif; ?>
			
			<?php if ( $rating ) : ?>
				<div class="mcp-card-rating">
					<span class="mcp-rating-value"><?php echo esc_html( number_format( $rating, 1 ) ); ?></span>
					<span class="mcp-rating-max">/10</span>
				</div>
			<?php endif; ?>
		</div>

		<div class="mcp-card-content">
			<h3 class="mcp-card-title">
				<a href="<?php echo esc_url( get_permalink() ); ?>">
					<?php echo esc_html( get_the_title() ); ?>
				</a>
			</h3>

			<?php if ( $developer ) : ?>
				<p class="mcp-card-developer">
					<strong><?php esc_html_e( 'المطوّر:', 'momarab-core' ); ?></strong>
					<?php echo esc_html( $developer ); ?>
				</p>
			<?php endif; ?>

			<?php if ( $release_date ) : ?>
				<p class="mcp-card-date">
					<strong><?php esc_html_e( 'تاريخ الإطلاق:', 'momarab-core' ); ?></strong>
					<?php echo esc_html( date_i18n( get_option( 'date_format' ), strtotime( $release_date ) ) ); ?>
				</p>
			<?php endif; ?>

			<div class="mcp-card-excerpt">
				<?php echo wp_kses_post( get_the_excerpt() ); ?>
			</div>

			<div class="mcp-card-taxonomies">
				<?php $this->render_card_taxonomies( $post_id ); ?>
			</div>
		</div>
		<?php
	}

	/**
	 * Render card taxonomies.
	 *
	 * @param int $post_id Post ID.
	 */
	private function render_card_taxonomies( $post_id ) {
		$taxonomies = array( 'game_type', 'game_status' );

		foreach ( $taxonomies as $taxonomy ) {
			$terms = get_the_terms( $post_id, $taxonomy );
			if ( $terms && ! is_wp_error( $terms ) ) {
				echo '<div class="mcp-card-tax mcp-card-' . esc_attr( $taxonomy ) . '">';
				foreach ( $terms as $term ) {
					echo '<span class="mcp-tax-tag">' . esc_html( $term->name ) . '</span>';
				}
				echo '</div>';
			}
		}
	}
}
