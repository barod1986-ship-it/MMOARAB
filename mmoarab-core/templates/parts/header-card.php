<?php
/**
 * Game header card template part.
 *
 * @package Momarab_Core
 */

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

$post_id = $args['post_id'] ?? get_the_ID();
$thumbnail = get_the_post_thumbnail_url( $post_id, 'mcp-hero' );
$overall_rating = get_post_meta( $post_id, 'mcp_rating_overall', true );
$developer = get_post_meta( $post_id, 'mcp_developer', true );
$publisher = get_post_meta( $post_id, 'mcp_publisher', true );
$release_date = get_post_meta( $post_id, 'mcp_release_date', true );
$official_site = get_post_meta( $post_id, 'mcp_official_site', true );

?>
<div class="mcp-header-card">
	
	<div class="mcp-header-image">
		<?php if ( $thumbnail ) : ?>
			<img src="<?php echo esc_url( $thumbnail ); ?>" alt="<?php echo esc_attr( get_the_title( $post_id ) ); ?>" class="mcp-hero-image" />
		<?php else : ?>
			<div class="mcp-placeholder-hero">
				<span><?php esc_html_e( 'لا توجد صورة', 'momarab-core' ); ?></span>
			</div>
		<?php endif; ?>
		
		<?php if ( $overall_rating ) : ?>
			<div class="mcp-header-rating">
				<div class="mcp-rating-circle">
					<span class="mcp-rating-value"><?php echo esc_html( number_format( $overall_rating, 1 ) ); ?></span>
					<span class="mcp-rating-max">/10</span>
				</div>
			</div>
		<?php endif; ?>
	</div>

	<div class="mcp-header-info">
		<h1 class="mcp-game-title"><?php echo esc_html( get_the_title( $post_id ) ); ?></h1>
		
		<div class="mcp-game-meta">
			<?php if ( $developer ) : ?>
				<div class="mcp-meta-item">
					<strong><?php esc_html_e( 'المطوّر:', 'momarab-core' ); ?></strong>
					<span><?php echo esc_html( $developer ); ?></span>
				</div>
			<?php endif; ?>

			<?php if ( $publisher ) : ?>
				<div class="mcp-meta-item">
					<strong><?php esc_html_e( 'الناشر:', 'momarab-core' ); ?></strong>
					<span><?php echo esc_html( $publisher ); ?></span>
				</div>
			<?php endif; ?>

			<?php if ( $release_date ) : ?>
				<div class="mcp-meta-item">
					<strong><?php esc_html_e( 'تاريخ الإطلاق:', 'momarab-core' ); ?></strong>
					<span><?php echo esc_html( date_i18n( get_option( 'date_format' ), strtotime( $release_date ) ) ); ?></span>
				</div>
			<?php endif; ?>

			<?php if ( $official_site ) : ?>
				<div class="mcp-meta-item">
					<a href="<?php echo esc_url( $official_site ); ?>" target="_blank" rel="noopener noreferrer" class="mcp-official-link">
						<?php esc_html_e( 'الموقع الرسمي', 'momarab-core' ); ?>
						<span class="mcp-external-icon">↗</span>
					</a>
				</div>
			<?php endif; ?>
		</div>

		<div class="mcp-game-taxonomies">
			<?php
			$taxonomies = array(
				'game_type'     => __( 'النوع', 'momarab-core' ),
				'game_status'   => __( 'الحالة', 'momarab-core' ),
				'game_mode'     => __( 'أسلوب اللعب', 'momarab-core' ),
				'game_platform' => __( 'المنصات', 'momarab-core' ),
			);

			foreach ( $taxonomies as $taxonomy => $label ) :
				$terms = get_the_terms( $post_id, $taxonomy );
				if ( $terms && ! is_wp_error( $terms ) ) :
					?>
					<div class="mcp-taxonomy-group mcp-<?php echo esc_attr( $taxonomy ); ?>">
						<strong><?php echo esc_html( $label ); ?>:</strong>
						<div class="mcp-terms">
							<?php foreach ( $terms as $term ) : ?>
								<span class="mcp-term-tag"><?php echo esc_html( $term->name ); ?></span>
							<?php endforeach; ?>
						</div>
					</div>
					<?php
				endif;
			endforeach;
			?>
		</div>

		<?php if ( get_the_excerpt( $post_id ) ) : ?>
			<div class="mcp-game-excerpt">
				<?php echo wp_kses_post( get_the_excerpt( $post_id ) ); ?>
			</div>
		<?php endif; ?>
	</div>

</div>
