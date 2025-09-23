<?php
/**
 * Game ratings template part.
 *
 * @package Momarab_Core
 */

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

$post_id = $args['post_id'] ?? get_the_ID();

// Get all ratings.
$rating_types = array(
	'story'    => __( 'القصة', 'momarab-core' ),
	'gameplay' => __( 'الجيمبلاي', 'momarab-core' ),
	'graphics' => __( 'الرسومات', 'momarab-core' ),
	'audio'    => __( 'الصوت', 'momarab-core' ),
	'overall'  => __( 'التقييم النهائي', 'momarab-core' ),
);

$ratings = array();
$has_ratings = false;

foreach ( $rating_types as $type => $label ) {
	$rating_data = Momarab_Core\MCP_Templates::get_game_rating( $post_id, $type );
	$ratings[ $type ] = array(
		'label' => $label,
		'value' => $rating_data['value'],
		'note'  => $rating_data['note'],
	);
	
	if ( $rating_data['value'] > 0 ) {
		$has_ratings = true;
	}
}

// Only show section if we have ratings.
if ( ! $has_ratings ) {
	return;
}

?>
<div class="mcp-game-ratings">
	<h3><?php esc_html_e( 'التقييمات', 'momarab-core' ); ?></h3>

	<div class="mcp-ratings-grid">
		<?php foreach ( $ratings as $type => $rating ) : ?>
			<?php if ( $rating['value'] > 0 ) : ?>
				<div class="mcp-rating-item mcp-rating-<?php echo esc_attr( $type ); ?>">
					<div class="mcp-rating-header">
						<h4 class="mcp-rating-label"><?php echo esc_html( $rating['label'] ); ?></h4>
						<div class="mcp-rating-score">
							<span class="mcp-score-value"><?php echo esc_html( number_format( $rating['value'], 1 ) ); ?></span>
							<span class="mcp-score-max">/10</span>
						</div>
					</div>
					
					<div class="mcp-rating-bar">
						<div class="mcp-rating-fill" style="width: <?php echo esc_attr( ( $rating['value'] / 10 ) * 100 ); ?>%;"></div>
					</div>

					<?php if ( $rating['note'] ) : ?>
						<div class="mcp-rating-note">
							<?php echo wp_kses_post( $rating['note'] ); ?>
						</div>
					<?php endif; ?>
				</div>
			<?php endif; ?>
		<?php endforeach; ?>
	</div>

	<?php if ( $ratings['overall']['value'] > 0 ) : ?>
		<div class="mcp-overall-rating">
			<div class="mcp-overall-circle">
				<div class="mcp-circle-progress" data-rating="<?php echo esc_attr( $ratings['overall']['value'] ); ?>">
					<div class="mcp-circle-inner">
						<span class="mcp-overall-score"><?php echo esc_html( number_format( $ratings['overall']['value'], 1 ) ); ?></span>
						<span class="mcp-overall-max">/10</span>
					</div>
				</div>
			</div>
			<div class="mcp-overall-label">
				<?php echo esc_html( $ratings['overall']['label'] ); ?>
			</div>
		</div>
	<?php endif; ?>

</div>
