<?php
/**
 * Taxonomies registration for games.
 *
 * @package Momarab_Core
 */

namespace Momarab_Core;

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Games Taxonomies class.
 */
class MCP_Taxonomies {

	/**
	 * Constructor.
	 */
	public function __construct() {
		$this->register_taxonomies();
	}

	/**
	 * Register all game taxonomies.
	 */
	public function register_taxonomies() {
		$this->register_game_type();
		$this->register_game_status();
		$this->register_game_mode();
		$this->register_game_platform();
	}

	/**
	 * Register game type taxonomy.
	 */
	private function register_game_type() {
		$labels = array(
			'name'              => _x( 'أنواع الألعاب', 'taxonomy general name', 'momarab-core' ),
			'singular_name'     => _x( 'نوع اللعبة', 'taxonomy singular name', 'momarab-core' ),
			'search_items'      => __( 'البحث في أنواع الألعاب', 'momarab-core' ),
			'all_items'         => __( 'جميع أنواع الألعاب', 'momarab-core' ),
			'parent_item'       => __( 'نوع اللعبة الأب', 'momarab-core' ),
			'parent_item_colon' => __( 'نوع اللعبة الأب:', 'momarab-core' ),
			'edit_item'         => __( 'تحرير نوع اللعبة', 'momarab-core' ),
			'update_item'       => __( 'تحديث نوع اللعبة', 'momarab-core' ),
			'add_new_item'      => __( 'إضافة نوع لعبة جديد', 'momarab-core' ),
			'new_item_name'     => __( 'اسم نوع اللعبة الجديد', 'momarab-core' ),
			'menu_name'         => __( 'أنواع الألعاب', 'momarab-core' ),
		);

		$args = array(
			'hierarchical'      => true,
			'labels'            => $labels,
			'public'            => true,
			'show_ui'           => true,
			'show_in_menu'      => 'edit.php?post_type=games',
			'show_admin_column' => true,
			'rewrite'           => array( 'slug' => 'game_type', 'with_front' => false ),
			'show_in_rest'      => true,
		);

		\register_taxonomy( 'game_type', array( 'games' ), $args );
	}

	/**
	 * Register game status taxonomy.
	 */
	private function register_game_status() {
		$labels = array(
			'name'              => _x( 'حالة اللعبة', 'taxonomy general name', 'momarab-core' ),
			'singular_name'     => _x( 'حالة', 'taxonomy singular name', 'momarab-core' ),
			'search_items'      => __( 'البحث في حالات الألعاب', 'momarab-core' ),
			'all_items'         => __( 'جميع حالات الألعاب', 'momarab-core' ),
			'parent_item'       => __( 'الحالة الأب', 'momarab-core' ),
			'parent_item_colon' => __( 'الحالة الأب:', 'momarab-core' ),
			'edit_item'         => __( 'تحرير الحالة', 'momarab-core' ),
			'update_item'       => __( 'تحديث الحالة', 'momarab-core' ),
			'add_new_item'      => __( 'إضافة حالة جديدة', 'momarab-core' ),
			'new_item_name'     => __( 'اسم الحالة الجديدة', 'momarab-core' ),
			'menu_name'         => __( 'حالة اللعبة', 'momarab-core' ),
		);

		$args = array(
			'hierarchical'      => true,
			'labels'            => $labels,
			'public'            => true,
			'show_ui'           => true,
			'show_in_menu'      => 'edit.php?post_type=games',
			'show_admin_column' => true,
			'rewrite'           => array( 'slug' => 'game_status', 'with_front' => false ),
			'show_in_rest'      => true,
		);

		\register_taxonomy( 'game_status', array( 'games' ), $args );
	}

	/**
	 * Register game mode taxonomy.
	 */
	private function register_game_mode() {
		$labels = array(
			'name'              => _x( 'أسلوب اللعب', 'taxonomy general name', 'momarab-core' ),
			'singular_name'     => _x( 'أسلوب', 'taxonomy singular name', 'momarab-core' ),
			'search_items'      => __( 'البحث في أساليب اللعب', 'momarab-core' ),
			'all_items'         => __( 'جميع أساليب اللعب', 'momarab-core' ),
			'parent_item'       => __( 'الأسلوب الأب', 'momarab-core' ),
			'parent_item_colon' => __( 'الأسلوب الأب:', 'momarab-core' ),
			'edit_item'         => __( 'تحرير الأسلوب', 'momarab-core' ),
			'update_item'       => __( 'تحديث الأسلوب', 'momarab-core' ),
			'add_new_item'      => __( 'إضافة أسلوب جديد', 'momarab-core' ),
			'new_item_name'     => __( 'اسم الأسلوب الجديد', 'momarab-core' ),
			'menu_name'         => __( 'أسلوب اللعب', 'momarab-core' ),
		);

		$args = array(
			'hierarchical'      => true,
			'labels'            => $labels,
			'public'            => true,
			'show_ui'           => true,
			'show_in_menu'      => 'edit.php?post_type=games',
			'show_admin_column' => true,
			'rewrite'           => array( 'slug' => 'game_mode', 'with_front' => false ),
			'show_in_rest'      => true,
		);

		\register_taxonomy( 'game_mode', array( 'games' ), $args );
	}

	/**
	 * Register game platform taxonomy.
	 */
	private function register_game_platform() {
		$labels = array(
			'name'              => _x( 'المنصات', 'taxonomy general name', 'momarab-core' ),
			'singular_name'     => _x( 'منصة', 'taxonomy singular name', 'momarab-core' ),
			'search_items'      => __( 'البحث في المنصات', 'momarab-core' ),
			'all_items'         => __( 'جميع المنصات', 'momarab-core' ),
			'parent_item'       => __( 'المنصة الأب', 'momarab-core' ),
			'parent_item_colon' => __( 'المنصة الأب:', 'momarab-core' ),
			'edit_item'         => __( 'تحرير المنصة', 'momarab-core' ),
			'update_item'       => __( 'تحديث المنصة', 'momarab-core' ),
			'add_new_item'      => __( 'إضافة منصة جديدة', 'momarab-core' ),
			'new_item_name'     => __( 'اسم المنصة الجديدة', 'momarab-core' ),
			'menu_name'         => __( 'المنصات', 'momarab-core' ),
		);

		$args = array(
			'hierarchical'      => true,
			'labels'            => $labels,
			'public'            => true,
			'show_ui'           => true,
			'show_in_menu'      => 'edit.php?post_type=games',
			'show_admin_column' => true,
			'rewrite'           => array( 'slug' => 'game_platform', 'with_front' => false ),
			'show_in_rest'      => true,
		);

		\register_taxonomy( 'game_platform', array( 'games' ), $args );
	}
}
