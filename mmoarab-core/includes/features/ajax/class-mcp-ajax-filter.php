<?php
/**
 * Ajax filter functionality for games archive.
 *
 * @package Momarab_Core
 */

namespace Momarab_Core;

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Ajax filter class.
 */
class MCP_Ajax_Filter {

	/**
	 * Constructor.
	 */
	public function __construct() {
		add_action( 'wp_ajax_mcp_filter_games', array( $this, 'filter_games' ) );
		add_action( 'wp_ajax_nopriv_mcp_filter_games', array( $this, 'filter_games' ) );
	}

	/**
	 * Handle Ajax filter request.
	 */
	public function filter_games() {
		// Check nonce.
		if ( ! check_ajax_referer( 'mcp_filter_nonce', 'nonce', false ) ) {
			wp_send_json_error( array(
				'message' => __( 'خطأ في التحقق من الأمان.', 'momarab-core' ),
			) );
		}

		// Get and sanitize parameters.
		$raw = wp_unslash( $_POST );
		$filters = array(
			'search'  => isset( $raw['search'] ) ? sanitize_text_field( $raw['search'] ) : '',
			'tax'     => isset( $raw['tax'] ) ? array_map( 'sanitize_text_field', (array) $raw['tax'] ) : array(),
			'meta'    => isset( $raw['meta'] ) ? array_map( 'sanitize_text_field', (array) $raw['meta'] ) : array(),
			'order'   => isset( $raw['order'] ) ? sanitize_text_field( $raw['order'] ) : '',
			'orderby' => isset( $raw['orderby'] ) ? sanitize_text_field( $raw['orderby'] ) : '',
		);

		// Build query arguments.
		$query_args = $this->build_query_args( $filters );

		// Get cached results or query database.
		$cache_key = 'mcp_archive_cache_' . md5( serialize( $query_args ) );
		$results = get_transient( $cache_key );

		if ( false === $results ) {
			$query = new \WP_Query( $query_args );
			$results = $this->format_results( $query, $filters );
			
			// Cache for 10 minutes.
			set_transient( $cache_key, $results, 600 );
		}

		wp_send_json_success( $results );
	}

	/**
	 * Sanitize filter parameters.
	 *
	 * @param array $post_data POST data.
	 * @return array Sanitized filters.
	 */
	private function sanitize_filters( $post_data ) {
		$filters = array();

		// Taxonomy filters.
		$taxonomies = array( 'type', 'status', 'mode', 'platform' );
		foreach ( $taxonomies as $tax ) {
			if ( ! empty( $post_data[ $tax ] ) ) {
				if ( is_array( $post_data[ $tax ] ) ) {
					$filters[ $tax ] = array_map( 'sanitize_text_field', $post_data[ $tax ] );
				} else {
					$filters[ $tax ] = sanitize_text_field( $post_data[ $tax ] );
				}
			}
		}

		// Sort parameter.
		$allowed_sorts = array( 'newest', 'oldest', 'az', 'za', 'toprated' );
		$sort = isset( $post_data['sort'] ) ? sanitize_text_field( $post_data['sort'] ) : 'newest';
		$filters['sort'] = in_array( $sort, $allowed_sorts, true ) ? $sort : 'newest';

		// Pagination.
		$filters['page'] = isset( $post_data['page'] ) ? max( 1, intval( $post_data['page'] ) ) : 1;

		// Per page (max 50).
		$per_page = isset( $post_data['per_page'] ) ? intval( $post_data['per_page'] ) : 12;
		$filters['per_page'] = min( max( 1, $per_page ), 50 );

		return $filters;
	}

	/**
	 * Build WP_Query arguments from filters.
	 *
	 * @param array $filters Sanitized filters.
	 * @return array Query arguments.
	 */
	private function build_query_args( $filters ) {
		$args = array(
			'post_type'      => 'games',
			'post_status'    => 'publish',
			'posts_per_page' => $filters['per_page'],
			'paged'          => $filters['page'],
			'tax_query'      => array(),
			'meta_query'     => array(),
		);

		// Add taxonomy queries.
		$tax_map = array(
			'type'     => 'game_type',
			'status'   => 'game_status',
			'mode'     => 'game_mode',
			'platform' => 'game_platform',
		);

		foreach ( $tax_map as $filter_key => $taxonomy ) {
			if ( ! empty( $filters[ $filter_key ] ) ) {
				$terms = is_array( $filters[ $filter_key ] ) ? $filters[ $filter_key ] : array( $filters[ $filter_key ] );
				
				$args['tax_query'][] = array(
					'taxonomy' => $taxonomy,
					'field'    => 'slug',
					'terms'    => $terms,
					'operator' => 'IN',
				);
			}
		}

		// Add sorting.
		switch ( $filters['sort'] ) {
			case 'oldest':
				$args['orderby'] = 'date';
				$args['order'] = 'ASC';
				break;

			case 'az':
				$args['orderby'] = 'title';
				$args['order'] = 'ASC';
				break;

			case 'za':
				$args['orderby'] = 'title';
				$args['order'] = 'DESC';
				break;

			case 'toprated':
				$args['meta_key'] = 'mcp_rating_overall';
				$args['orderby'] = 'meta_value_num';
				$args['order'] = 'DESC';
				$args['meta_query'][] = array(
					'key'     => 'mcp_rating_overall',
					'value'   => 0,
					'compare' => '>',
					'type'    => 'NUMERIC',
				);
				break;

			default: // newest
				$args['orderby'] = 'date';
				$args['order'] = 'DESC';
				break;
		}

		// Ensure tax_query relation.
		if ( count( $args['tax_query'] ) > 1 ) {
			$args['tax_query']['relation'] = 'AND';
		}

		return $args;
	}

	/**
	 * Format query results for Ajax response.
	 *
	 * @param \WP_Query $query The query object.
	 * @param array     $filters Current filters.
	 * @return array Formatted results.
	 */
	private function format_results( $query, $filters ) {
		$games = array();

		if ( $query->have_posts() ) {
			while ( $query->have_posts() ) {
				$query->the_post();
				$post_id = get_the_ID();

				$games[] = array(
					'id'            => $post_id,
					'title'         => get_the_title(),
					'excerpt'       => get_the_excerpt(),
					'permalink'     => get_permalink(),
					'thumbnail'     => get_the_post_thumbnail_url( $post_id, 'mcp-card' ),
					'rating'        => get_post_meta( $post_id, 'mcp_rating_overall', true ),
					'developer'     => get_post_meta( $post_id, 'mcp_developer', true ),
					'release_date'  => get_post_meta( $post_id, 'mcp_release_date', true ),
					'taxonomies'    => $this->get_post_taxonomies( $post_id ),
				);
			}
			wp_reset_postdata();
		}

		// Build pagination data.
		$pagination = array(
			'current_page' => $filters['page'],
			'total_pages'  => $query->max_num_pages,
			'total_posts'  => $query->found_posts,
			'per_page'     => $filters['per_page'],
		);

		return array(
			'games'      => $games,
			'pagination' => $pagination,
			'filters'    => $filters,
		);
	}

	/**
	 * Get post taxonomies data.
	 *
	 * @param int $post_id Post ID.
	 * @return array Taxonomies data.
	 */
	private function get_post_taxonomies( $post_id ) {
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

		return $taxonomies;
	}
}
