<?php
/**
 * Assets management for MOMARAB CORE plugin.
 *
 * @package Momarab_Core
 */

namespace Momarab_Core;

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Assets management class.
 */
class MCP_Assets {

	/**
	 * Enqueue frontend assets.
	 */
	public function enqueue_frontend() {
		// Global frontend styles and scripts.
		wp_enqueue_style(
			'mcp-front',
			MCP_ASSETS . 'css/front.css',
			array(),
			MCP_VERSION
		);

		wp_enqueue_script(
			'mcp-front',
			MCP_ASSETS . 'js/front.js',
			array( 'jquery' ),
			MCP_VERSION,
			true
		);

		// Archive-specific assets.
		if ( is_post_type_archive( 'games' ) || is_tax( array( 'game_type', 'game_status', 'game_mode', 'game_platform' ) ) ) {
			wp_enqueue_style(
				'mcp-archive',
				MCP_ASSETS . 'css/front-archive.css',
				array( 'mcp-front' ),
				MCP_VERSION
			);

			wp_enqueue_script(
				'mcp-archive-filter',
				MCP_ASSETS . 'js/archive-filter.js',
				array( 'jquery', 'mcp-front' ),
				MCP_VERSION,
				true
			);

			// Localize script for Ajax.
			wp_localize_script(
				'mcp-archive-filter',
				'mcpAjax',
				array(
					'ajaxurl' => admin_url( 'admin-ajax.php' ),
					'nonce'   => wp_create_nonce( 'mcp_filter_nonce' ),
					'strings' => array(
						'loading'   => __( 'جاري التحميل...', 'momarab-core' ),
						'no_results' => __( 'لم يتم العثور على نتائج.', 'momarab-core' ),
						'error'     => __( 'حدث خطأ. يرجى المحاولة مرة أخرى.', 'momarab-core' ),
					),
				)
			);
		}

		// Single game assets.
		if ( is_singular( 'games' ) ) {
			wp_enqueue_style(
				'mcp-single',
				MCP_ASSETS . 'css/front-single.css',
				array( 'mcp-front' ),
				MCP_VERSION
			);

			wp_enqueue_script(
				'mcp-single-media',
				MCP_ASSETS . 'js/single-media.js',
				array( 'jquery', 'mcp-front' ),
				MCP_VERSION,
				true
			);
		}

		// Set script translations for JavaScript.
		wp_set_script_translations( 'mcp-front', 'momarab-core', MCP_DIR . 'languages' );
		if ( wp_script_is( 'mcp-archive-filter', 'enqueued' ) ) {
			wp_set_script_translations( 'mcp-archive-filter', 'momarab-core', MCP_DIR . 'languages' );
		}
		if ( wp_script_is( 'mcp-single-media', 'enqueued' ) ) {
			wp_set_script_translations( 'mcp-single-media', 'momarab-core', MCP_DIR . 'languages' );
		}
	}

	/**
	 * Enqueue admin assets.
	 */
	public function enqueue_admin() {
		if ( ! function_exists( 'get_current_screen' ) ) { 
			return; 
		}
		$screen = get_current_screen();
		
		// Enqueue for games post type.
		if ( $screen && $screen->post_type === 'games' ) {
			wp_enqueue_media();

			wp_enqueue_script(
				'mcp-admin',
				MCP_ASSETS . 'js/admin.js',
				array( 'jquery' ),
				MCP_VERSION,
				true
			);
			wp_localize_script( 'mcp-admin', 'MCP_GALLERY', array( 'max' => 4 ) );
		}

		// Enqueue Select2 for post screens (for related games feature).
		if ( $screen && in_array( $screen->base, array( 'post', 'edit' ) ) ) {
			// Use WordPress bundled Select2 (available since WP 4.2).
			wp_enqueue_script( 'select2' );
			wp_enqueue_style( 'select2' );
			
			wp_enqueue_script(
				'mcp-select2-init',
				MCP_ASSETS . 'js/select2-init.js',
				array( 'jquery', 'select2' ),
				MCP_VERSION,
				true
			);
		}
	}
}
