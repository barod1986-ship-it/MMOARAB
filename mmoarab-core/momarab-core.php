<?php
/**
 * Plugin Name: MOMARAB CORE
 * Plugin URI: https://momarab.com/plugins/momarab-core
 * Description: إضافة ووردبريس متخصصة لإدارة وعرض ألعاب MMO بالعربية مع دعم RTL كامل وفلترة Ajax
 * Version: 1.0.0
 * Requires at least: 6.0
 * Tested up to: 6.6
 * Requires PHP: 7.4
 * Author: MOMARAB Development Team
 * Author URI: https://momarab.com
 * License: GPLv2 or later
 * License URI: https://www.gnu.org/licenses/gpl-2.0.html
 * Text Domain: momarab-core
 * Domain Path: /languages
 * Network: false
 *
 * @package Momarab_Core
 */

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

// Define plugin constants.
define( 'MCP_VERSION', '1.0.0' );
define( 'MCP_FILE', __FILE__ );
define( 'MCP_DIR', plugin_dir_path( __FILE__ ) );
define( 'MCP_URL', plugin_dir_url( __FILE__ ) );
define( 'MCP_ASSETS', MCP_URL . 'assets/' );

// Check minimum requirements.
if ( version_compare( PHP_VERSION, '7.4', '<' ) ) {
	add_action( 'admin_notices', 'mcp_php_version_notice' );
	return;
}

if ( version_compare( get_bloginfo( 'version' ), '6.0', '<' ) ) {
	add_action( 'admin_notices', 'mcp_wp_version_notice' );
	return;
}

/**
 * Display PHP version notice.
 */
function mcp_php_version_notice() {
	?>
	<div class="notice notice-error">
		<p>
			<?php
			printf(
				/* translators: %s: Required PHP version */
				esc_html__( 'MOMARAB CORE requires PHP version %s or higher. Please update PHP.', 'momarab-core' ),
				'7.4'
			);
			?>
		</p>
	</div>
	<?php
}

/**
 * Display WordPress version notice.
 */
function mcp_wp_version_notice() {
	?>
	<div class="notice notice-error">
		<p>
			<?php
			printf(
				/* translators: %s: Required WordPress version */
				esc_html__( 'MOMARAB CORE requires WordPress version %s or higher. Please update WordPress.', 'momarab-core' ),
				'6.0'
			);
			?>
		</p>
	</div>
	<?php
}

// Load autoloader.
require_once MCP_DIR . 'includes/bootstrap/class-mcp-autoloader.php';

// Initialize autoloader.
$autoloader = new Momarab_Core\MCP_Autoloader();
$autoloader->register();

// Initialize plugin.
require_once MCP_DIR . 'includes/bootstrap/class-mcp-init.php';

// Start the plugin.
add_action( 'plugins_loaded', array( 'Momarab_Core\MCP_Init', 'get_instance' ) );

// Load text domain.
add_action( 'init', 'mcp_load_textdomain' );

/**
 * Load plugin text domain.
 */
function mcp_load_textdomain() {
	load_plugin_textdomain( 'momarab-core', false, 'momarab-core/languages' );
}

// Activation hook.
register_activation_hook( __FILE__, array( 'Momarab_Core\MCP_Init', 'activate' ) );

// Deactivation hook.
register_deactivation_hook( __FILE__, array( 'Momarab_Core\MCP_Init', 'deactivate' ) );
