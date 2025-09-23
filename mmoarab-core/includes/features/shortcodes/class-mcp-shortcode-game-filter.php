<?php
/**
 * Game filter shortcode functionality.
 *
 * @package Momarab_Core
 */

namespace Momarab_Core;

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Game filter shortcode class.
 */
class MCP_Shortcode_Game_Filter {

	/**
	 * Constructor.
	 */
	public function __construct() {
		add_shortcode( 'momarab_game_filter', array( $this, 'render_shortcode' ) );
	}

	/**
	 * Render game filter shortcode.
	 *
	 * @param array $atts Shortcode attributes.
	 * @return string Shortcode output.
	 */
	public function render_shortcode( $atts ) {
		$atts = shortcode_atts( array(
			'show_sort' => 'yes',
			'show_reset' => 'yes',
		), $atts, 'momarab_game_filter' );

		ob_start();
		?>
		<div class="mcp-filter-form" id="mcp-filter-form">
			<form class="mcp-filter-controls">
				<?php wp_nonce_field( 'mcp_filter_nonce', 'mcp_filter_nonce' ); ?>
				
				<div class="mcp-filter-row">
					<?php $this->render_taxonomy_filter( 'game_type', __( 'نوع اللعبة', 'momarab-core' ) ); ?>
					<?php $this->render_taxonomy_filter( 'game_status', __( 'حالة اللعبة', 'momarab-core' ) ); ?>
				</div>

				<div class="mcp-filter-row">
					<?php $this->render_taxonomy_filter( 'game_mode', __( 'أسلوب اللعب', 'momarab-core' ) ); ?>
					<?php $this->render_taxonomy_filter( 'game_platform', __( 'المنصة', 'momarab-core' ) ); ?>
				</div>

				<?php if ( 'yes' === $atts['show_sort'] ) : ?>
					<div class="mcp-filter-row">
						<div class="mcp-filter-group">
							<label for="mcp-sort"><?php esc_html_e( 'ترتيب حسب', 'momarab-core' ); ?></label>
							<select name="sort" id="mcp-sort" class="mcp-filter-select">
								<option value="newest"><?php esc_html_e( 'الأحدث', 'momarab-core' ); ?></option>
								<option value="oldest"><?php esc_html_e( 'الأقدم', 'momarab-core' ); ?></option>
								<option value="az"><?php esc_html_e( 'أبجدي (أ-ي)', 'momarab-core' ); ?></option>
								<option value="za"><?php esc_html_e( 'أبجدي (ي-أ)', 'momarab-core' ); ?></option>
								<option value="toprated"><?php esc_html_e( 'الأعلى تقييماً', 'momarab-core' ); ?></option>
							</select>
						</div>
					</div>
				<?php endif; ?>

				<div class="mcp-filter-actions">
					<button type="submit" class="mcp-filter-submit">
						<?php esc_html_e( 'تطبيق الفلترة', 'momarab-core' ); ?>
					</button>
					
					<?php if ( 'yes' === $atts['show_reset'] ) : ?>
						<button type="button" class="mcp-filter-reset">
							<?php esc_html_e( 'إعادة تعيين', 'momarab-core' ); ?>
						</button>
					<?php endif; ?>
				</div>
			</form>

			<div class="mcp-filter-results" id="mcp-filter-results">
				<!-- Results will be loaded here via Ajax -->
			</div>

			<div class="mcp-filter-loading" id="mcp-filter-loading" style="display: none;">
				<p><?php esc_html_e( 'جاري التحميل...', 'momarab-core' ); ?></p>
			</div>
		</div>
		<?php

		return ob_get_clean();
	}

	/**
	 * Render taxonomy filter dropdown.
	 *
	 * @param string $taxonomy Taxonomy name.
	 * @param string $label    Filter label.
	 */
	private function render_taxonomy_filter( $taxonomy, $label ) {
		$terms = get_terms( array(
			'taxonomy'   => $taxonomy,
			'hide_empty' => true,
			'orderby'    => 'name',
			'order'      => 'ASC',
		) );

		if ( empty( $terms ) || is_wp_error( $terms ) ) {
			return;
		}

		$filter_name = str_replace( 'game_', '', $taxonomy );
		?>
		<div class="mcp-filter-group">
			<label for="mcp-<?php echo esc_attr( $filter_name ); ?>"><?php echo esc_html( $label ); ?></label>
			<select name="<?php echo esc_attr( $filter_name ); ?>" id="mcp-<?php echo esc_attr( $filter_name ); ?>" class="mcp-filter-select">
				<option value=""><?php esc_html_e( 'الكل', 'momarab-core' ); ?></option>
				<?php foreach ( $terms as $term ) : ?>
					<option value="<?php echo esc_attr( $term->slug ); ?>">
						<?php echo esc_html( $term->name ); ?>
						<?php if ( $term->count > 0 ) : ?>
							(<?php echo esc_html( $term->count ); ?>)
						<?php endif; ?>
					</option>
				<?php endforeach; ?>
			</select>
		</div>
		<?php
	}
}
