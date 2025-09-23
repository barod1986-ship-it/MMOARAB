<?php
/**
 * Permalinks management for MOMARAB CORE plugin.
 *
 * @package Momarab_Core
 */

namespace Momarab_Core;

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Permalinks management class.
 */
class MCP_Permalinks {

	/**
	 * Constructor.
	 */
	public function __construct() {
		add_action( 'init', array( $this, 'add_rewrite_rules' ), 20 );
	}

	/**
	 * Add custom rewrite rules.
	 */
	public function add_rewrite_rules() {
		// Games archive pagination.
		add_rewrite_rule(
			'^games/page/([0-9]+)/?$',
			'index.php?post_type=games&paged=$matches[1]',
			'top'
		);

		// Game type taxonomy with pagination.
		add_rewrite_rule(
			'^game_type/([^/]+)/page/([0-9]+)/?$',
			'index.php?game_type=$matches[1]&paged=$matches[2]',
			'top'
		);

		// Game status taxonomy with pagination.
		add_rewrite_rule(
			'^game_status/([^/]+)/page/([0-9]+)/?$',
			'index.php?game_status=$matches[1]&paged=$matches[2]',
			'top'
		);

		// Game mode taxonomy with pagination.
		add_rewrite_rule(
			'^game_mode/([^/]+)/page/([0-9]+)/?$',
			'index.php?game_mode=$matches[1]&paged=$matches[2]',
			'top'
		);

		// Game platform taxonomy with pagination.
		add_rewrite_rule(
			'^game_platform/([^/]+)/page/([0-9]+)/?$',
			'index.php?game_platform=$matches[1]&paged=$matches[2]',
			'top'
		);
	}

	/**
	 * Get games archive URL.
	 *
	 * @return string Games archive URL.
	 */
	public static function get_games_archive_url() {
		return home_url( '/games/' );
	}

	/**
	 * Get game taxonomy URL.
	 *
	 * @param string $taxonomy The taxonomy name.
	 * @param string $term_slug The term slug.
	 * @return string Taxonomy URL.
	 */
	public static function get_taxonomy_url( $taxonomy, $term_slug ) {
		return home_url( '/' . $taxonomy . '/' . $term_slug . '/' );
	}

	/**
	 * Get filtered games URL with query parameters.
	 *
	 * @param array $filters Array of filters.
	 * @return string Filtered URL.
	 */
	public static function get_filtered_url( $filters = array() ) {
		$base_url = self::get_games_archive_url();
		
		if ( empty( $filters ) ) {
			return $base_url;
		}

		$query_args = array();

		// Add taxonomy filters.
		$taxonomies = array( 'type', 'status', 'mode', 'platform' );
		foreach ( $taxonomies as $tax ) {
			if ( ! empty( $filters[ $tax ] ) ) {
				$query_args[ $tax ] = $filters[ $tax ];
			}
		}

		// Add sorting.
		if ( ! empty( $filters['sort'] ) ) {
			$query_args['sort'] = $filters['sort'];
		}

		// Add pagination.
		if ( ! empty( $filters['page'] ) && $filters['page'] > 1 ) {
			$query_args['page'] = $filters['page'];
		}

		return add_query_arg( $query_args, $base_url );
	}

	/**
	 * Parse current filters from URL.
	 *
	 * @return array Current filters.
	 */
	public static function get_current_filters() {
		$filters = array();

		// Get from query vars.
		$taxonomies = array(
			'type'     => 'game_type',
			'status'   => 'game_status',
			'mode'     => 'game_mode',
			'platform' => 'game_platform',
		);

		foreach ( $taxonomies as $param => $taxonomy ) {
			$value = get_query_var( $param );
			if ( $value ) {
				$filters[ $param ] = sanitize_text_field( $value );
			}
		}

		// Get sort parameter.
		$sort = get_query_var( 'sort' );
		if ( $sort ) {
			$filters['sort'] = sanitize_text_field( $sort );
		}

		// Get page parameter.
		$page = get_query_var( 'page' );
		if ( $page ) {
			$filters['page'] = intval( $page );
		}

		return $filters;
	}
}
