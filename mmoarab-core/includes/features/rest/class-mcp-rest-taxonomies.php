<?php
/**
 * REST API endpoint for taxonomies.
 *
 * @package Momarab_Core
 */

namespace Momarab_Core;

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Taxonomies REST API endpoint class.
 */
class MCP_REST_Taxonomies extends MCP_REST_Controller {

	/**
	 * Constructor.
	 */
	public function __construct() {
		parent::__construct();
		add_action( 'rest_api_init', array( $this, 'register_routes' ) );
	}

	/**
	 * Register REST API routes.
	 */
	public function register_routes() {
		register_rest_route(
			$this->namespace,
			'/taxonomies',
			array(
				'methods'             => 'GET',
				'callback'            => array( $this, 'get_taxonomies' ),
				'permission_callback' => '__return_true', // Public read access.
				'args'                => array(
					'include_empty' => array(
						'description' => __( 'تضمين المصطلحات الفارغة', 'momarab-core' ),
						'type'        => 'boolean',
						'default'     => false,
					),
				),
			)
		);

		register_rest_route(
			$this->namespace,
			'/taxonomies/(?P<taxonomy>[a-zA-Z0-9_-]+)',
			array(
				'methods'             => 'GET',
				'callback'            => array( $this, 'get_taxonomy_terms' ),
				'permission_callback' => '__return_true', // Public read access.
				'args'                => array(
					'taxonomy' => array(
						'description' => __( 'اسم التصنيف', 'momarab-core' ),
						'type'        => 'string',
						'required'    => true,
					),
					'include_empty' => array(
						'description' => __( 'تضمين المصطلحات الفارغة', 'momarab-core' ),
						'type'        => 'boolean',
						'default'     => false,
					),
				),
			)
		);
	}

	/**
	 * Get all game taxonomies.
	 *
	 * @param \WP_REST_Request $request Request object.
	 * @return \WP_REST_Response|\WP_Error Response object or error.
	 */
	public function get_taxonomies( $request ) {
		$include_empty = $request->get_param( 'include_empty' );
		$taxonomies = array( 'game_type', 'game_status', 'game_mode', 'game_platform' );
		$result = array();

		foreach ( $taxonomies as $taxonomy ) {
			$terms = $this->get_terms_data( $taxonomy, $include_empty );
			if ( ! is_wp_error( $terms ) ) {
				$result[ $taxonomy ] = $terms;
			}
		}

		return rest_ensure_response( $result );
	}

	/**
	 * Get terms for a specific taxonomy.
	 *
	 * @param \WP_REST_Request $request Request object.
	 * @return \WP_REST_Response|\WP_Error Response object or error.
	 */
	public function get_taxonomy_terms( $request ) {
		$taxonomy = $request->get_param( 'taxonomy' );
		$include_empty = $request->get_param( 'include_empty' );

		// Validate taxonomy.
		$allowed_taxonomies = array( 'game_type', 'game_status', 'game_mode', 'game_platform' );
		if ( ! in_array( $taxonomy, $allowed_taxonomies, true ) ) {
			return $this->get_error_response(
				'invalid_taxonomy',
				__( 'تصنيف غير صالح', 'momarab-core' ),
				400,
				array( 'taxonomy' => $taxonomy )
			);
		}

		$terms = $this->get_terms_data( $taxonomy, $include_empty );

		if ( is_wp_error( $terms ) ) {
			return $this->get_error_response(
				'terms_error',
				__( 'خطأ في جلب المصطلحات', 'momarab-core' ),
				500
			);
		}

		return rest_ensure_response( array(
			'taxonomy' => $taxonomy,
			'terms'    => $terms,
		) );
	}

	/**
	 * Get terms data for a taxonomy.
	 *
	 * @param string $taxonomy Taxonomy name.
	 * @param bool   $include_empty Include empty terms.
	 * @return array|\WP_Error Terms data or error.
	 */
	private function get_terms_data( $taxonomy, $include_empty = false ) {
		$args = array(
			'taxonomy'   => $taxonomy,
			'hide_empty' => ! $include_empty,
			'orderby'    => 'name',
			'order'      => 'ASC',
		);

		$terms = get_terms( $args );

		if ( is_wp_error( $terms ) ) {
			return $terms;
		}

		$formatted_terms = array();
		foreach ( $terms as $term ) {
			$formatted_terms[] = array(
				'id'          => $term->term_id,
				'name'        => $term->name,
				'slug'        => $term->slug,
				'description' => $term->description,
				'count'       => $term->count,
				'parent'      => $term->parent,
			);
		}

		return $formatted_terms;
	}
}
