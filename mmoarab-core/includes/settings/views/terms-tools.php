<?php
/**
 * Terms tools template.
 *
 * @package Momarab_Core
 */

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

?>
<div class="mcp-terms-tools">
	<h2><?php esc_html_e( 'أدوات المصطلحات', 'momarab-core' ); ?></h2>
	
	<?php
	$seeded = isset( $_GET['mcp_seeded'] ) ? sanitize_text_field( wp_unslash( $_GET['mcp_seeded'] ) ) : '';
	if ( '1' === $seeded ) : ?>
		<div class="notice notice-success inline">
			<p><?php esc_html_e( 'تم إنشاء المصطلحات الأساسية بنجاح!', 'momarab-core' ); ?></p>
		</div>
	<?php endif; ?>
	
	<table class="form-table">
		<tr>
			<th scope="row"><?php esc_html_e( 'إنشاء المصطلحات الأساسية', 'momarab-core' ); ?></th>
			<td>
				<form method="post" action="<?php echo esc_url( admin_url( 'admin-post.php' ) ); ?>" style="display: inline;">
					<?php wp_nonce_field( 'mcp_seed_terms' ); ?>
					<input type="hidden" name="action" value="mcp_seed_terms">
					<button type="submit" class="button button-primary">
						<?php echo esc_html__( 'إنشاء المصطلحات الأساسية', 'momarab-core' ); ?>
					</button>
				</form>
				<p class="description">
					<?php esc_html_e( 'إضافة المصطلحات الأساسية لجميع التصنيفات (أنواع الألعاب، الحالة، أسلوب اللعب، المنصات).', 'momarab-core' ); ?>
				</p>
			</td>
		</tr>
	</table>
</div>
