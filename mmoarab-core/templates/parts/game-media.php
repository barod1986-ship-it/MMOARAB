<?php
/**
 * Game media template part (YouTube videos and gallery).
 *
 * @package Momarab_Core
 */

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

$post_id = $args['post_id'] ?? get_the_ID();

// Get YouTube videos.
$youtube_videos = array();
for ( $i = 1; $i <= 2; $i++ ) {
	$youtube_url = get_post_meta( $post_id, 'mcp_trailer_youtube_' . $i, true );
	if ( $youtube_url ) {
		$embed_url = Momarab_Core\MCP_Templates::get_youtube_embed_url( $youtube_url );
		if ( $embed_url ) {
			$youtube_videos[] = array(
				'original' => $youtube_url,
				'embed'    => $embed_url,
			);
		}
	}
}

// Get gallery images.
$gallery_images = Momarab_Core\MCP_Templates::get_game_gallery( $post_id );

// Only show section if we have media.
if ( empty( $youtube_videos ) && empty( $gallery_images ) ) {
	return;
}

?>
<div class="mcp-game-media">
	<h3><?php esc_html_e( 'الوسائط', 'momarab-core' ); ?></h3>

	<?php if ( ! empty( $youtube_videos ) ) : ?>
		<div class="mcp-youtube-section">
			<h4><?php esc_html_e( 'مقاطع الفيديو', 'momarab-core' ); ?></h4>
			<div class="mcp-youtube-videos">
				<?php foreach ( $youtube_videos as $index => $video ) : ?>
					<div class="mcp-youtube-video" data-video-index="<?php echo esc_attr( $index ); ?>">
						<div class="mcp-video-wrapper">
							<iframe 
								src="<?php echo esc_url( $video['embed'] ); ?>" 
								title="<?php esc_attr_e( 'فيديو اللعبة', 'momarab-core' ); ?>"
								frameborder="0" 
								allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" 
								allowfullscreen
								loading="lazy">
							</iframe>
						</div>
					</div>
				<?php endforeach; ?>
			</div>
		</div>
	<?php endif; ?>

	<?php if ( ! empty( $gallery_images ) ) : ?>
		<div class="mcp-gallery-section">
			<h4><?php esc_html_e( 'معرض الصور', 'momarab-core' ); ?></h4>
			<div class="mcp-image-gallery">
				<?php foreach ( $gallery_images as $index => $image ) : ?>
					<div class="mcp-gallery-item" data-image-index="<?php echo esc_attr( $index ); ?>">
						<a href="<?php echo esc_url( $image['full'] ); ?>" class="mcp-gallery-link" data-lightbox="game-gallery">
							<img 
								src="<?php echo esc_url( $image['thumb'] ); ?>" 
								alt="<?php echo esc_attr( $image['alt'] ); ?>" 
								loading="lazy"
								class="mcp-gallery-thumb"
							/>
							<div class="mcp-gallery-overlay">
								<span class="mcp-zoom-icon">🔍</span>
							</div>
						</a>
						<?php if ( $image['caption'] ) : ?>
							<div class="mcp-gallery-caption">
								<?php echo esc_html( $image['caption'] ); ?>
							</div>
						<?php endif; ?>
					</div>
				<?php endforeach; ?>
			</div>
		</div>
	<?php endif; ?>

</div>
