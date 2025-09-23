<?php
/**
 * Base REST API controller for MOMARAB CORE.
 *
 * @package Momarab_Core
 */

namespace Momarab_Core;

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Base REST API controller class.
 */
class MCP_REST_Controller {

	/**
	 * API namespace.
	 *
	 * @var string
	 */
	protected $namespace = 'momarab/v1';

	/**
	 * Constructor.
	 */
	public function __construct() {
		add_action( 'rest_api_init', array( $this, 'register_cors_headers' ) );
	}

	/**
	 * Register CORS headers for read access.
	 */
	public function register_cors_headers() {
		add_filter( 'rest_pre_serve_request', array( $this, 'add_cors_headers' ), 10, 4 );
	}

	/**
	 * Add CORS headers for allowed domains.
	 *
	 * @param bool             $served  Whether the request has already been served.
	 * @param \WP_HTTP_Response $result   Result to send to the client.
	 * @param \WP_REST_Request  $request  Request used to generate the response.
	 * @param \WP_REST_Server   $server   Server instance.
	 * @return bool
	 */
	public function add_cors_headers( $served, $result, $request, $server ) {
		// Only apply to our API endpoints.
		if ( strpos( $request->get_route(), '/momarab/v1/' ) !== 0 ) {
			return $served;
		}

		// Only allow GET requests from external domains.
		if ( 'GET' !== $request->get_method() ) {
			return $served;
		}

		$allowed_origins = array(
			'https://momarab.com',
			'https://api.momarab.com',
		);

		$origin = $request->get_header( 'origin' );
		
		if ( $origin && in_array( $origin, $allowed_origins, true ) ) {
			header( 'Access-Control-Allow-Origin: ' . $origin );
			header( 'Access-Control-Allow-Methods: GET' );
			header( 'Access-Control-Allow-Headers: Content-Type, Authorization' );
		}

		return $served;
	}

	/**
	 * Get namespace.
	 *
	 * @return string API namespace.
	 */
	public function get_namespace() {
		return $this->namespace;
	}

	/**
	 * Validate order parameter.
	 *
	 * @param string $value Order value.
	 * @return bool True if valid.
	 */
	public function validate_order( $value ) {
		$allowed_orders = array( 'newest', 'oldest', 'az', 'za', 'toprated' );
		return in_array( $value, $allowed_orders, true );
	}

	/**
	 * Sanitize order parameter.
	 *
	 * @param string $value Order value.
	 * @return string Sanitized order.
	 */
	public function sanitize_order( $value ) {
		return $this->validate_order( $value ) ? $value : 'newest';
	}

	/**
	 * Validate per_page parameter.
	 *
	 * @param int $value Per page value.
	 * @return bool True if valid.
	 */
	public function validate_per_page( $value ) {
		$per_page = intval( $value );
		return $per_page >= 1 && $per_page <= 50;
	}

	/**
	 * Sanitize per_page parameter.
	 *
	 * @param int $value Per page value.
	 * @return int Sanitized per page (max 50).
	 */
	public function sanitize_per_page( $value ) {
		$per_page = intval( $value );
		return min( max( 1, $per_page ), 50 );
	}

	/**
	 * Validate taxonomy term.
	 *
	 * @param string $value Term slug or ID.
	 * @param string $taxonomy Taxonomy name.
	 * @return bool True if valid.
	 */
	public function validate_taxonomy_term( $value, $taxonomy ) {
		if ( empty( $value ) ) {
			return true; // Empty is valid (no filter).
		}

		// Check if term exists by slug or ID.
		$term = get_term_by( 'slug', $value, $taxonomy );
		if ( ! $term ) {
			$term = get_term_by( 'id', intval( $value ), $taxonomy );
		}

		return $term && ! is_wp_error( $term );
	}

	/**
	 * Get error response.
	 *
	 * @param string $code Error code.
	 * @param string $message Error message.
	 * @param int    $status HTTP status code.
	 * @param array  $data Additional error data.
	 * @return \WP_Error Error object.
	 */
	public function get_error_response( $code, $message, $status = 400, $data = array() ) {
		return new \WP_Error(
			$code,
			$message,
			array_merge( array( 'status' => $status ), $data )
		);
	}

	/**
	 * Format game data for API response.
	 *
	 * @param \WP_Post $post Game post object.
	 * @return array Formatted game data.
	 */
	protected function format_game_data( $post ) {
		$post_id = $post->ID;

		// Get basic meta.
		$basic_meta = array(
			'official_site' => get_post_meta( $post_id, 'mcp_official_site', true ),
			'developer'     => get_post_meta( $post_id, 'mcp_developer', true ),
			'publisher'     => get_post_meta( $post_id, 'mcp_publisher', true ),
			'release_date'  => get_post_meta( $post_id, 'mcp_release_date', true ),
		);

		// Get ratings.
		$ratings = array();
		$rating_types = array( 'story', 'gameplay', 'graphics', 'audio', 'overall' );
		foreach ( $rating_types as $type ) {
			$value = get_post_meta( $post_id, 'mcp_rating_' . $type, true );
			$note = get_post_meta( $post_id, 'mcp_rating_' . $type . '_note', true );
			
			if ( $value ) {
				$ratings[ $type ] = array(
					'value' => floatval( $value ),
					'note'  => $note ? $note : '',
				);
			}
		}

		// Get taxonomies.
		$taxonomies = array();
		$tax_names = array( 'game_type', 'game_status', 'game_mode', 'game_platform' );
		foreach ( $tax_names as $taxonomy ) {
			$terms = get_the_terms( $post_id, $taxonomy );
			if ( $terms && ! is_wp_error( $terms ) ) {
				$taxonomies[ $taxonomy ] = array_map( function( $term ) {
					return array(
						'id'   => $term->term_id,
						'name' => $term->name,
						'slug' => $term->slug,
					);
				}, $terms );
			}
		}

		return array(
			'id'            => $post_id,
			'title'         => $post->post_title,
			'content'       => apply_filters( 'the_content', $post->post_content ),
			'excerpt'       => get_the_excerpt( $post ),
			'link'          => get_permalink( $post ),
			'date'          => $post->post_date,
			'modified'      => $post->post_modified,
			'featured_image' => get_the_post_thumbnail_url( $post_id, 'full' ),
			'basic_info'    => $basic_meta,
			'ratings'       => $ratings,
			'taxonomies'    => $taxonomies,
		);
	}
}
