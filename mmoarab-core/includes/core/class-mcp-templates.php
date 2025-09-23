<?php
/**
 * Template management for MOMARAB CORE plugin.
 *
 * @package Momarab_Core
 */

namespace Momarab_Core;

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Templates management class.
 */
class MCP_Templates {

	/**
	 * Constructor.
	 */
	public function __construct() {
		add_filter( 'template_include', array( $this, 'template_include' ) );
	}

	/**
	 * Include custom templates for games.
	 *
	 * @param string $template The template path.
	 * @return string Modified template path.
	 */
	public function template_include( $template ) {
		// Single game template.
		if ( is_singular( 'games' ) ) {
			$custom_template = $this->locate_template( 'single-games.php' );
			if ( $custom_template ) {
				return $custom_template;
			}
		}

		// Games archive template.
		if ( is_post_type_archive( 'games' ) ) {
			$custom_template = $this->locate_template( 'archive-games.php' );
			if ( $custom_template ) {
				return $custom_template;
			}
		}

		// Game taxonomy templates.
		if ( is_tax( array( 'game_type', 'game_status', 'game_mode', 'game_platform' ) ) ) {
			$custom_template = $this->locate_template( 'archive-games.php' );
			if ( $custom_template ) {
				return $custom_template;
			}
		}

		return $template;
	}

	/**
	 * Locate template file.
	 *
	 * @param string $template_name The template name.
	 * @return string|false Template path or false if not found.
	 */
	private function locate_template( $template_name ) {
		// Check if template exists in theme first.
		$theme_template = locate_template( array(
			'momarab-core/' . $template_name,
			$template_name,
		) );

		if ( $theme_template ) {
			return $theme_template;
		}

		// Check plugin templates directory.
		$plugin_template = MCP_DIR . 'templates/' . $template_name;
		if ( file_exists( $plugin_template ) ) {
			return $plugin_template;
		}

		return false;
	}

	/**
	 * Get template part.
	 *
	 * @param string $slug The template slug.
	 * @param string $name Optional. The template name.
	 * @param array  $args Optional. Arguments to pass to template.
	 */
	public static function get_template_part( $slug, $name = null, $args = array() ) {
		$templates = array();

		if ( $name ) {
			$templates[] = "momarab-core/parts/{$slug}-{$name}.php";
			$templates[] = "parts/{$slug}-{$name}.php";
		}

		$templates[] = "momarab-core/parts/{$slug}.php";
		$templates[] = "parts/{$slug}.php";

		// Try to locate in theme first.
		$located = locate_template( $templates, false, false );

		if ( ! $located ) {
			// Check plugin templates.
			foreach ( $templates as $template ) {
				$plugin_template = MCP_DIR . 'templates/' . str_replace( 'momarab-core/', '', $template );
				if ( file_exists( $plugin_template ) ) {
					$located = $plugin_template;
					break;
				}
			}
		}

		if ( $located ) {
			// Extract args to make them available in template.
			if ( ! empty( $args ) && is_array( $args ) ) {
				extract( $args, EXTR_SKIP );
			}

			include $located;
		}
	}

	/**
	 * Get games query for archive/taxonomy pages.
	 *
	 * @param array $args Additional query arguments.
	 * @return \WP_Query Games query object.
	 */
	public static function get_games_query( $args = array() ) {
		$default_args = array(
			'post_type'      => 'games',
			'post_status'    => 'publish',
			'posts_per_page' => 12,
			'meta_query'     => array(),
			'tax_query'      => array(),
		);

		// Merge with provided args.
		$query_args = wp_parse_args( $args, $default_args );

		// Ensure per_page limit of 50.
		if ( $query_args['posts_per_page'] > 50 ) {
			$query_args['posts_per_page'] = 50;
		}

		return new \WP_Query( $query_args );
	}

	/**
	 * Get game meta value with fallback.
	 *
	 * @param int    $post_id The post ID.
	 * @param string $meta_key The meta key.
	 * @param mixed  $default Default value if meta doesn't exist.
	 * @return mixed Meta value or default.
	 */
	public static function get_game_meta( $post_id, $meta_key, $default = '' ) {
		$value = get_post_meta( $post_id, $meta_key, true );
		return ! empty( $value ) ? $value : $default;
	}

	/**
	 * Get formatted game rating.
	 *
	 * @param int    $post_id The post ID.
	 * @param string $rating_type The rating type (story, gameplay, etc.).
	 * @return array Rating data with value and note.
	 */
	public static function get_game_rating( $post_id, $rating_type ) {
		$value = get_post_meta( $post_id, 'mcp_rating_' . $rating_type, true );
		$note = get_post_meta( $post_id, 'mcp_rating_' . $rating_type . '_note', true );

		return array(
			'value' => $value ? floatval( $value ) : 0,
			'note'  => $note ? $note : '',
		);
	}

	/**
	 * Get YouTube embed URL from video URL.
	 *
	 * @param string $url YouTube video URL.
	 * @return string|false Embed URL or false if invalid.
	 */
	public static function get_youtube_embed_url( $url ) {
		if ( empty( $url ) ) {
			return false;
		}

		// Extract video ID from different YouTube URL formats.
		$video_id = '';

		if ( strpos( $url, 'youtu.be/' ) !== false ) {
			$video_id = substr( $url, strrpos( $url, '/' ) + 1 );
		} elseif ( strpos( $url, 'youtube.com/watch' ) !== false ) {
			parse_str( parse_url( $url, PHP_URL_QUERY ), $params );
			$video_id = isset( $params['v'] ) ? $params['v'] : '';
		}

		if ( $video_id ) {
			// Remove any additional parameters from video ID.
			$video_id = strtok( $video_id, '&?' );
			return 'https://www.youtube.com/embed/' . $video_id;
		}

		return false;
	}

	/**
	 * Get game gallery images.
	 *
	 * @param int $post_id The post ID.
	 * @return array Array of image data.
	 */
	public static function get_game_gallery( $post_id ) {
		$gallery_ids = get_post_meta( $post_id, 'mcp_gallery', true );
		$images = array();

		if ( empty( $gallery_ids ) ) {
			return $images;
		}

		$ids = explode( ',', $gallery_ids );
		$ids = array_slice( $ids, 0, 4 ); // Limit to 4 images.

		foreach ( $ids as $id ) {
			$id = intval( trim( $id ) );
			if ( $id && wp_attachment_is_image( $id ) ) {
				$images[] = array(
					'id'       => $id,
					'url'      => wp_get_attachment_url( $id ),
					'thumb'    => wp_get_attachment_image_url( $id, 'mcp-thumb' ),
					'full'     => wp_get_attachment_image_url( $id, 'full' ),
					'alt'      => get_post_meta( $id, '_wp_attachment_image_alt', true ),
					'caption'  => wp_get_attachment_caption( $id ),
				);
			}
		}

		return $images;
	}
}
