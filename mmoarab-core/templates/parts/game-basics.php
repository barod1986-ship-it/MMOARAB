<?php
/**
 * Game basic information template part.
 *
 * @package Momarab_Core
 */

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

$post_id = $args['post_id'] ?? get_the_ID();

// Get engine information.
$engines = get_post_meta( $post_id, 'mcp_engine', true );
if ( ! is_array( $engines ) ) {
	$engines = array();
}

// Get features.
$features = array();
for ( $i = 1; $i <= 4; $i++ ) {
	$feature = get_post_meta( $post_id, 'mcp_feature_' . $i, true );
	if ( $feature ) {
		$features[] = $feature;
	}
}

// Only show section if we have engines or features.
if ( empty( $engines ) && empty( $features ) ) {
	return;
}

?>
<div class="mcp-game-basics">
	
	<?php if ( ! empty( $engines ) ) : ?>
		<div class="mcp-engine-section">
			<h3><?php esc_html_e( 'المحرك', 'momarab-core' ); ?></h3>
			<div class="mcp-engines">
				<?php
				$engine_labels = array(
					'unreal_engine' => __( 'Unreal Engine', 'momarab-core' ),
					'unity'         => __( 'Unity', 'momarab-core' ),
					'cryengine'     => __( 'CryEngine', 'momarab-core' ),
					'frostbite'     => __( 'Frostbite', 'momarab-core' ),
					'custom'        => __( 'محرك مخصص', 'momarab-core' ),
				);

				foreach ( $engines as $engine ) :
					if ( isset( $engine_labels[ $engine ] ) ) :
						?>
						<span class="mcp-engine-tag"><?php echo esc_html( $engine_labels[ $engine ] ); ?></span>
						<?php
					endif;
				endforeach;
				?>
			</div>
		</div>
	<?php endif; ?>

	<?php if ( ! empty( $features ) ) : ?>
		<div class="mcp-features-section">
			<h3><?php esc_html_e( 'الميزات الرئيسية', 'momarab-core' ); ?></h3>
			<ul class="mcp-features-list">
				<?php foreach ( $features as $feature ) : ?>
					<li class="mcp-feature-item">
						<span class="mcp-feature-icon">✓</span>
						<span class="mcp-feature-text"><?php echo esc_html( $feature ); ?></span>
					</li>
				<?php endforeach; ?>
			</ul>
		</div>
	<?php endif; ?>

</div>
