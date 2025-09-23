<?php
/**
 * Settings page template.
 *
 * @package Momarab_Core
 */

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

?>
<div class="wrap">
	<h1><?php echo esc_html( get_admin_page_title() ); ?></h1>

	<?php settings_errors(); ?>

	<form method="post" action="options.php">
		<?php
		settings_fields( 'mcp_settings_group' );
		do_settings_sections( 'mcp-settings' );
		?>

		<?php submit_button(); ?>
	</form>

	<?php require __DIR__ . '/terms-tools.php'; // ← ضع أداة المصطلحات خارج الفورم ?>

	<div class="mcp-info-box" style="background: #f9f9f9; border: 1px solid #ddd; padding: 15px; margin-top: 20px;">
		<h3><?php esc_html_e( 'معلومات الإضافة', 'momarab-core' ); ?></h3>
		<p><strong><?php esc_html_e( 'الإصدار:', 'momarab-core' ); ?></strong> <?php echo esc_html( MCP_VERSION ); ?></p>
		<p><strong><?php esc_html_e( 'نوع المحتوى:', 'momarab-core' ); ?></strong> games</p>
		<p><strong><?php esc_html_e( 'التصنيفات:', 'momarab-core' ); ?></strong> game_type, game_status, game_mode, game_platform</p>
		<p><strong><?php esc_html_e( 'الشورتكود المتاحة:', 'momarab-core' ); ?></strong></p>
		<ul style="margin-left: 20px;">
			<li><code>[momarab_games limit="6" order="toprated"]</code></li>
			<li><code>[momarab_game_filter]</code></li>
		</ul>
		<p><strong><?php esc_html_e( 'REST API:', 'momarab-core' ); ?></strong></p>
		<ul style="margin-left: 20px;">
			<li><code>/wp-json/momarab/v1/games</code></li>
			<li><code>/wp-json/momarab/v1/taxonomies</code></li>
		</ul>
	</div>
</div>
