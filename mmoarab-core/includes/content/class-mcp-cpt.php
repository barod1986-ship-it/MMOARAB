<?php
/**
 * Custom Post Type registration for games.
 *
 * @package Momarab_Core
 */

namespace Momarab_Core;

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Games Custom Post Type class.
 */
class MCP_CPT {

	/**
	 * Constructor.
	 */
	public function __construct() {
		$this->register();
	}

	/**
	 * Register games post type.
	 */
	public function register() {
		\register_post_type( 'games', array(
			'labels' => array(
				'name' => \__( 'Games', 'momarab-core' ),
				'singular_name' => \__( 'Game', 'momarab-core' ),
				'menu_name' => \__( 'Games', 'momarab-core' ),
			),
			'public' => true,
			'show_ui' => true,
			'show_in_menu' => true,
			'menu_position' => 5,
			'menu_icon' => 'dashicons-games',
			'has_archive' => true,
			'show_in_rest' => true,
			'rewrite' => array( 'slug' => 'games', 'with_front' => false ),
			'supports' => array( 'title', 'editor', 'thumbnail', 'excerpt', 'custom-fields' ),
			'capability_type' => 'post',
			'map_meta_cap' => true,
			'taxonomies' => array( 'game_type', 'game_status', 'game_mode', 'game_platform' ),
		) );
	}
}

