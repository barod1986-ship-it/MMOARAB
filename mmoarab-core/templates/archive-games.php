<?php
/**
 * Games archive template.
 *
 * @package Momarab_Core
 */

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

get_header(); ?>

<div class="mcp-archive-games-container">
	
	<header class="mcp-archive-header">
		<h1 class="mcp-archive-title">
			<?php
			if ( is_post_type_archive( 'games' ) ) {
				esc_html_e( 'جميع الألعاب', 'momarab-core' );
			} elseif ( is_tax() ) {
				echo esc_html( single_term_title( '', false ) );
			}
			?>
		</h1>
		
		<?php if ( is_tax() && term_description() ) : ?>
			<div class="mcp-archive-description">
				<?php echo wp_kses_post( term_description() ); ?>
			</div>
		<?php endif; ?>
	</header>

	<div class="mcp-filter-section">
		<?php echo do_shortcode( '[momarab_game_filter]' ); ?>
	</div>

	<div class="mcp-games-grid" id="mcp-games-grid">
		<?php if ( have_posts() ) : ?>
			
			<div class="mcp-games-list">
				<?php while ( have_posts() ) : ?>
					<?php the_post(); ?>
					<div class="mcp-game-card">
						<?php
						Momarab_Core\MCP_Templates::get_template_part( 'game-card', null, array( 'post_id' => get_the_ID() ) );
						?>
					</div>
				<?php endwhile; ?>
			</div>

			<div class="mcp-pagination">
				<?php
				the_posts_pagination( array(
					'mid_size'  => 2,
					'prev_text' => __( '&laquo; السابق', 'momarab-core' ),
					'next_text' => __( 'التالي &raquo;', 'momarab-core' ),
				) );
				?>
			</div>

		<?php else : ?>
			
			<div class="mcp-no-games">
				<h2><?php esc_html_e( 'لم يتم العثور على ألعاب', 'momarab-core' ); ?></h2>
				<p><?php esc_html_e( 'لا توجد ألعاب تطابق معايير البحث الحالية.', 'momarab-core' ); ?></p>
			</div>

		<?php endif; ?>
	</div>

</div>

<?php get_footer(); ?>
