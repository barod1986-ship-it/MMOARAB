<?php
/**
 * Single game template.
 *
 * @package Momarab_Core
 */

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

get_header(); ?>

<div class="mcp-single-game-container">
	<?php while ( have_posts() ) : ?>
		<?php the_post(); ?>
		
		<article id="post-<?php the_ID(); ?>" <?php post_class( 'mcp-single-game' ); ?>>
			
			<?php
			// Header card with featured image and basic info.
			Momarab_Core\MCP_Templates::get_template_part( 'header-card', null, array( 'post_id' => get_the_ID() ) );
			?>

			<div class="mcp-game-content">
				
				<?php if ( get_the_content() ) : ?>
					<div class="mcp-game-description">
						<h2><?php esc_html_e( 'وصف اللعبة', 'momarab-core' ); ?></h2>
						<div class="mcp-content">
							<?php the_content(); ?>
						</div>
					</div>
				<?php endif; ?>

				<?php
				// Basic game information.
				Momarab_Core\MCP_Templates::get_template_part( 'game-basics', null, array( 'post_id' => get_the_ID() ) );
				?>

				<?php
				// Media section (YouTube videos and gallery).
				Momarab_Core\MCP_Templates::get_template_part( 'game-media', null, array( 'post_id' => get_the_ID() ) );
				?>

				<?php
				// Ratings section.
				Momarab_Core\MCP_Templates::get_template_part( 'game-ratings', null, array( 'post_id' => get_the_ID() ) );
				?>

				<?php
				// Related news section.
				do_action( 'mcp_single_game_after_content', get_the_ID() );
				?>

			</div>

		</article>

	<?php endwhile; ?>
</div>

<?php get_footer(); ?>
