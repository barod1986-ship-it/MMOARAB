<?php
/**
 * REST API endpoint for games.
 *
 * @package Momarab_Core
 */

namespace Momarab_Core;

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Games REST API endpoint class.
 */
class MCP_REST_Games extends MCP_REST_Controller {

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
			'/games',
			array(
				'methods'             => 'GET',
				'callback'            => array( $this, 'get_games' ),
				'permission_callback' => '__return_true', // Public read access.
				'args'                => $this->get_collection_params(),
			)
		);

		register_rest_route(
			$this->namespace,
			'/games/(?P<id>\d+)',
			array(
				'methods'             => 'GET',
				'callback'            => array( $this, 'get_game' ),
				'permission_callback' => '__return_true', // Public read access.
				'args'                => array(
					'id' => array(
						'description' => __( 'معرف اللعبة', 'momarab-core' ),
						'type'        => 'integer',
						'required'    => true,
					),
				),
			)
		);
	}

	/**
	 * Get games collection.
	 *
	 * @param \WP_REST_Request $request Request object.
	 * @return \WP_REST_Response|\WP_Error Response object or error.
	 */
	public function get_games( $request ) {
		$params = $request->get_params();

		// Validate order parameter.
		if ( ! empty( $params['order'] ) && ! $this->validate_order( $params['order'] ) ) {
			return $this->get_error_response(
				'invalid_param',
				__( 'قيمة order غير صالحة', 'momarab-core' ),
				400
			);
		}

		// Build query arguments.
		$query_args = array(
			'post_type'      => 'games',
			'post_status'    => 'publish',
			'posts_per_page' => $this->sanitize_per_page( $params['per_page'] ?? 12 ),
			'paged'          => max( 1, intval( $params['page'] ?? 1 ) ),
			'tax_query'      => array(),
			'meta_query'     => array(),
		);

		// Add search.
		if ( ! empty( $params['search'] ) ) {
			$query_args['s'] = sanitize_text_field( $params['search'] );
		}

		// Add taxonomy filters.
		$this->add_taxonomy_filters( $query_args, $params );

		// Add ordering.
		$this->add_ordering( $query_args, $params['order'] ?? 'newest' );

		// Execute query.
		$query = new \WP_Query( $query_args );

		if ( is_wp_error( $query ) ) {
			return $this->get_error_response(
				'query_error',
				__( 'خطأ في تنفيذ الاستعلام', 'momarab-core' ),
				500
			);
		}

		// Format results.
		$games = array();
		if ( $query->have_posts() ) {
			while ( $query->have_posts() ) {
				$query->the_post();
				$games[] = $this->format_game_data( $query->post );
			}
			wp_reset_postdata();
		}

		// Build response.
		$response = array(
			'games'      => $games,
			'pagination' => array(
				'current_page' => $query_args['paged'],
				'total_pages'  => $query->max_num_pages,
				'total_posts'  => $query->found_posts,
				'per_page'     => $query_args['posts_per_page'],
			),
		);

		return rest_ensure_response( $response );
	}

	/**
	 * Get single game.
	 *
	 * @param \WP_REST_Request $request Request object.
	 * @return \WP_REST_Response|\WP_Error Response object or error.
	 */
	public function get_game( $request ) {
		$game_id = intval( $request['id'] );
		$post = get_post( $game_id );

		if ( ! $post || 'games' !== $post->post_type || 'publish' !== $post->post_status ) {
			return $this->get_error_response(
				'game_not_found',
				__( 'اللعبة غير موجودة', 'momarab-core' ),
				404
			);
		}

		$game_data = $this->format_game_data( $post );

		// Add additional data for single game.
		$game_data['features'] = $this->get_game_features( $game_id );
		$game_data['media'] = $this->get_game_media( $game_id );
		$game_data['engine'] = get_post_meta( $game_id, 'mcp_engine', true );

		return rest_ensure_response( $game_data );
	}

	/**
	 * Get collection parameters.
	 *
	 * @return array Collection parameters.
	 */
	public function get_collection_params() {
		return array(
			'page' => array(
				'description'       => __( 'رقم الصفحة', 'momarab-core' ),
				'type'              => 'integer',
				'default'           => 1,
				'minimum'           => 1,
				'sanitize_callback' => 'absint',
			),
			'per_page' => array(
				'description'       => __( 'عدد العناصر في الصفحة', 'momarab-core' ),
				'type'              => 'integer',
				'default'           => 12,
				'minimum'           => 1,
				'maximum'           => 50,
				'validate_callback' => array( $this, 'validate_per_page' ),
				'sanitize_callback' => array( $this, 'sanitize_per_page' ),
			),
			'search' => array(
				'description'       => __( 'البحث في العناوين والمحتوى', 'momarab-core' ),
				'type'              => 'string',
				'sanitize_callback' => 'sanitize_text_field',
			),
			'order' => array(
				'description'       => __( 'ترتيب النتائج', 'momarab-core' ),
				'type'              => 'string',
				'default'           => 'newest',
				'enum'              => array( 'newest', 'oldest', 'az', 'za', 'toprated' ),
				'validate_callback' => array( $this, 'validate_order' ),
				'sanitize_callback' => array( $this, 'sanitize_order' ),
			),
			'type' => array(
				'description'       => __( 'فلترة حسب نوع اللعبة', 'momarab-core' ),
				'type'              => 'string',
				'sanitize_callback' => 'sanitize_text_field',
			),
			'status' => array(
				'description'       => __( 'فلترة حسب حالة اللعبة', 'momarab-core' ),
				'type'              => 'string',
				'sanitize_callback' => 'sanitize_text_field',
			),
			'mode' => array(
				'description'       => __( 'فلترة حسب أسلوب اللعب', 'momarab-core' ),
				'type'              => 'string',
				'sanitize_callback' => 'sanitize_text_field',
			),
			'platform' => array(
				'description'       => __( 'فلترة حسب المنصة', 'momarab-core' ),
				'type'              => 'string',
				'sanitize_callback' => 'sanitize_text_field',
			),
		);
	}

	/**
	 * Add taxonomy filters to query.
	 *
	 * @param array $query_args Query arguments.
	 * @param array $params     Request parameters.
	 */
	private function add_taxonomy_filters( &$query_args, $params ) {
		$tax_map = array(
			'type'     => 'game_type',
			'status'   => 'game_status',
			'mode'     => 'game_mode',
			'platform' => 'game_platform',
		);

		foreach ( $tax_map as $param => $taxonomy ) {
			if ( ! empty( $params[ $param ] ) ) {
				$terms = array_map( 'trim', explode( ',', $params[ $param ] ) );
				$terms = array_filter( $terms );

				if ( ! empty( $terms ) ) {
					$query_args['tax_query'][] = array(
						'taxonomy' => $taxonomy,
						'field'    => 'slug',
						'terms'    => $terms,
						'operator' => 'IN',
					);
				}
			}
		}

		// Set relation if multiple taxonomies.
		if ( count( $query_args['tax_query'] ) > 1 ) {
			$query_args['tax_query']['relation'] = 'AND';
		}
	}

	/**
	 * Add ordering to query.
	 *
	 * @param array  $query_args Query arguments.
	 * @param string $order      Order type.
	 */
	private function add_ordering( &$query_args, $order ) {
		switch ( $order ) {
			case 'oldest':
				$query_args['orderby'] = 'date';
				$query_args['order'] = 'ASC';
				break;

			case 'az':
				$query_args['orderby'] = 'title';
				$query_args['order'] = 'ASC';
				break;

			case 'za':
				$query_args['orderby'] = 'title';
				$query_args['order'] = 'DESC';
				break;

			case 'toprated':
				$query_args['meta_key'] = 'mcp_rating_overall';
				$query_args['orderby'] = 'meta_value_num';
				$query_args['order'] = 'DESC';
				$query_args['meta_query'][] = array(
					'key'     => 'mcp_rating_overall',
					'value'   => 0,
					'compare' => '>',
					'type'    => 'NUMERIC',
				);
				break;

			default: // newest
				$query_args['orderby'] = 'date';
				$query_args['order'] = 'DESC';
				break;
		}
	}

	/**
	 * Get game features.
	 *
	 * @param int $post_id Post ID.
	 * @return array Game features.
	 */
	private function get_game_features( $post_id ) {
		$features = array();
		for ( $i = 1; $i <= 4; $i++ ) {
			$feature = get_post_meta( $post_id, 'mcp_feature_' . $i, true );
			if ( $feature ) {
				$features[] = $feature;
			}
		}
		return $features;
	}

	/**
	 * Get game media.
	 *
	 * @param int $post_id Post ID.
	 * @return array Game media.
	 */
	private function get_game_media( $post_id ) {
		$media = array(
			'youtube_videos' => array(),
			'gallery'        => array(),
		);

		// YouTube videos.
		for ( $i = 1; $i <= 2; $i++ ) {
			$youtube_url = get_post_meta( $post_id, 'mcp_trailer_youtube_' . $i, true );
			if ( $youtube_url ) {
				$embed_url = MCP_Templates::get_youtube_embed_url( $youtube_url );
				if ( $embed_url ) {
					$media['youtube_videos'][] = array(
						'original_url' => $youtube_url,
						'embed_url'    => $embed_url,
					);
				}
			}
		}

		// Gallery.
		$gallery_images = MCP_Templates::get_game_gallery( $post_id );
		$media['gallery'] = $gallery_images;

		return $media;
	}
}
