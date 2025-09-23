<?php
/**
 * Autoloader for MOMARAB CORE plugin.
 *
 * @package Momarab_Core
 */

namespace Momarab_Core;

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * PSR-4 Autoloader for MOMARAB CORE.
 */
class MCP_Autoloader {

	/**
	 * Register the autoloader.
	 */
	public function register() {
		spl_autoload_register( array( $this, 'autoload' ) );
	}

	/**
	 * Autoload classes.
	 *
	 * @param string $class_name The class name to load.
	 */
	public function autoload( $class_name ) {
		// Check if class belongs to our namespace.
		if ( strpos( $class_name, 'Momarab_Core\\' ) !== 0 ) {
			return;
		}

		// Remove namespace prefix.
		$class_name = str_replace( 'Momarab_Core\\', '', $class_name );

		// Convert class name to file path.
		$file_path = $this->get_file_path( $class_name );

		// Load the file if it exists.
		if ( file_exists( $file_path ) ) {
			require_once $file_path;
		}
	}

	/**
	 * Convert class name to file path.
	 *
	 * @param string $class_name The class name.
	 * @return string The file path.
	 */
	private function get_file_path( $class_name ) {
		// Convert class name to lowercase with hyphens.
		$file_name = 'class-' . strtolower( str_replace( '_', '-', $class_name ) ) . '.php';

		// Map class prefixes to directories.
		$prefix_map = array(
			'MCP_Init'              => 'bootstrap/',
			'MCP_Assets'            => 'core/',
			'MCP_Templates'         => 'core/',
			'MCP_Permalinks'        => 'core/',
			'MCP_CPT'               => 'content/',
			'MCP_Taxonomies'        => 'content/',
			'MCP_Meta_Registry'     => 'content/meta/',
			'MCP_Meta_Validation'   => 'content/meta/',
			'MCP_Meta_Save'         => 'content/meta/',
			'MCP_Settings'          => 'settings/',
			'MCP_Terms_Manager'     => 'settings/',
			'MCP_Ajax_Filter'       => 'features/ajax/',
			'MCP_Shortcode_Games'   => 'features/shortcodes/',
			'MCP_Shortcode_Game_Filter' => 'features/shortcodes/',
			'MCP_Widget_Popular'    => 'features/widgets/',
			'MCP_Widget_Recent'     => 'features/widgets/',
			'MCP_Related_Meta'      => 'features/related/',
			'MCP_Related_Render'    => 'features/related/',
			'MCP_REST_Controller'   => 'features/rest/',
			'MCP_REST_Games'        => 'features/rest/',
			'MCP_REST_Taxonomies'   => 'features/rest/',
			'MCP_Nonce'             => 'security/',
			'MCP_Capabilities'      => 'security/',
			'MCP_Cache'             => 'performance/',
			'MCP_Images'            => 'performance/',
		);

		// Find the appropriate directory.
		$directory = 'includes/';
		foreach ( $prefix_map as $prefix => $dir ) {
			if ( strpos( $class_name, $prefix ) === 0 ) {
				$directory = 'includes/' . $dir;
				break;
			}
		}

		return MCP_DIR . $directory . $file_name;
	}
}
