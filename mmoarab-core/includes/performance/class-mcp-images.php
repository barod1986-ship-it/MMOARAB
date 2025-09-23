<?php
/**
 * Image optimization and management for MOMARAB CORE plugin.
 *
 * @package Momarab_Core
 */

namespace Momarab_Core;

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Image management class.
 */
class MCP_Images {

	/**
	 * Constructor.
	 */
	public function __construct() {
		add_action( 'after_setup_theme', array( $this, 'add_image_sizes' ) );
		add_filter( 'wp_get_attachment_image_attributes', array( $this, 'add_lazy_loading' ), 10, 3 );
	}

	/**
	 * Add custom image sizes.
	 */
	public function add_image_sizes() {
		// Game card image size (600x338).
		add_image_size( 'mcp-card', 600, 338, true );

		// Thumbnail size for widgets and related posts (300x170).
		add_image_size( 'mcp-thumb', 300, 170, true );

		// Hero image size for single game pages (1200x675).
		add_image_size( 'mcp-hero', 1200, 675, true );

		// Gallery thumbnail (200x200).
		add_image_size( 'mcp-gallery-thumb', 200, 200, true );
	}

	/**
	 * Add lazy loading attributes to images.
	 *
	 * @param array        $attr       Image attributes.
	 * @param \WP_Post     $attachment Attachment post object.
	 * @param string|array $size       Image size.
	 * @return array Modified attributes.
	 */
	public function add_lazy_loading( $attr, $attachment, $size ) {
		// Only add lazy loading to frontend images.
		if ( is_admin() ) {
			return $attr;
		}

		// Skip if loading attribute already set.
		if ( isset( $attr['loading'] ) ) {
			return $attr;
		}

		// Add lazy loading for our custom sizes.
		$lazy_sizes = array( 'mcp-card', 'mcp-thumb', 'mcp-gallery-thumb' );
		
		if ( in_array( $size, $lazy_sizes, true ) ) {
			$attr['loading'] = 'lazy';
		}

		return $attr;
	}

	/**
	 * Get optimized image URL.
	 *
	 * @param int    $attachment_id Attachment ID.
	 * @param string $size          Image size.
	 * @return string|false Image URL or false if not found.
	 */
	public static function get_optimized_image_url( $attachment_id, $size = 'full' ) {
		$url = wp_get_attachment_image_url( $attachment_id, $size );

		if ( ! $url ) {
			return false;
		}

		// Apply WebP conversion if supported.
		if ( self::supports_webp() ) {
			$url = self::convert_to_webp_url( $url );
		}

		return $url;
	}

	/**
	 * Get responsive image srcset.
	 *
	 * @param int    $attachment_id Attachment ID.
	 * @param string $size          Image size.
	 * @return string Srcset attribute value.
	 */
	public static function get_responsive_srcset( $attachment_id, $size = 'full' ) {
		return wp_get_attachment_image_srcset( $attachment_id, $size );
	}

	/**
	 * Get image sizes attribute.
	 *
	 * @param int    $attachment_id Attachment ID.
	 * @param string $size          Image size.
	 * @return string Sizes attribute value.
	 */
	public static function get_image_sizes( $attachment_id, $size = 'full' ) {
		return wp_get_attachment_image_sizes( $attachment_id, $size );
	}

	/**
	 * Generate placeholder image.
	 *
	 * @param int    $width  Image width.
	 * @param int    $height Image height.
	 * @param string $text   Placeholder text.
	 * @return string Placeholder image URL.
	 */
	public static function get_placeholder_image( $width = 600, $height = 338, $text = '' ) {
		if ( empty( $text ) ) {
			$text = __( 'لا توجد صورة', 'momarab-core' );
		}

		// Use a simple SVG placeholder.
		$svg = '<svg width="' . $width . '" height="' . $height . '" xmlns="http://www.w3.org/2000/svg">';
		$svg .= '<rect width="100%" height="100%" fill="#f0f0f0"/>';
		$svg .= '<text x="50%" y="50%" font-family="Arial, sans-serif" font-size="16" fill="#999" text-anchor="middle" dominant-baseline="middle">' . esc_html( $text ) . '</text>';
		$svg .= '</svg>';

		return 'data:image/svg+xml;base64,' . base64_encode( $svg );
	}

	/**
	 * Check if browser supports WebP.
	 *
	 * @return bool True if WebP is supported.
	 */
	private static function supports_webp() {
		// Check if server supports WebP generation.
		if ( ! function_exists( 'imagewebp' ) ) {
			return false;
		}

		// Check user agent for WebP support.
		$user_agent = $_SERVER['HTTP_USER_AGENT'] ?? '';
		
		// Chrome, Firefox, Edge, Opera support WebP.
		$webp_browsers = array( 'Chrome', 'Firefox', 'Edge', 'Opera' );
		
		foreach ( $webp_browsers as $browser ) {
			if ( strpos( $user_agent, $browser ) !== false ) {
				return true;
			}
		}

		// Check Accept header.
		$accept = $_SERVER['HTTP_ACCEPT'] ?? '';
		return strpos( $accept, 'image/webp' ) !== false;
	}

	/**
	 * Convert image URL to WebP format.
	 *
	 * @param string $url Original image URL.
	 * @return string WebP image URL.
	 */
	private static function convert_to_webp_url( $url ) {
		// This is a placeholder for WebP conversion logic.
		// In a real implementation, you would:
		// 1. Check if WebP version exists
		// 2. Generate WebP version if needed
		// 3. Return WebP URL
		
		return $url; // Return original URL for now.
	}

	/**
	 * Get image metadata.
	 *
	 * @param int $attachment_id Attachment ID.
	 * @return array|false Image metadata or false if not found.
	 */
	public static function get_image_metadata( $attachment_id ) {
		return wp_get_attachment_metadata( $attachment_id );
	}

	/**
	 * Get image alt text.
	 *
	 * @param int $attachment_id Attachment ID.
	 * @return string Alt text.
	 */
	public static function get_image_alt( $attachment_id ) {
		$alt = get_post_meta( $attachment_id, '_wp_attachment_image_alt', true );
		return $alt ? $alt : '';
	}

	/**
	 * Get image caption.
	 *
	 * @param int $attachment_id Attachment ID.
	 * @return string Caption.
	 */
	public static function get_image_caption( $attachment_id ) {
		return wp_get_attachment_caption( $attachment_id );
	}

	/**
	 * Validate image file.
	 *
	 * @param int $attachment_id Attachment ID.
	 * @return bool True if valid image.
	 */
	public static function is_valid_image( $attachment_id ) {
		return wp_attachment_is_image( $attachment_id );
	}

	/**
	 * Get image file size.
	 *
	 * @param int $attachment_id Attachment ID.
	 * @return int|false File size in bytes or false if not found.
	 */
	public static function get_image_file_size( $attachment_id ) {
		$file_path = get_attached_file( $attachment_id );
		
		if ( $file_path && file_exists( $file_path ) ) {
			return filesize( $file_path );
		}

		return false;
	}

	/**
	 * Format file size for display.
	 *
	 * @param int $bytes File size in bytes.
	 * @return string Formatted file size.
	 */
	public static function format_file_size( $bytes ) {
		return size_format( $bytes );
	}

	/**
	 * Get available image sizes.
	 *
	 * @return array Available image sizes.
	 */
	public static function get_available_sizes() {
		global $_wp_additional_image_sizes;

		$sizes = array();

		// Get default WordPress sizes.
		$default_sizes = array( 'thumbnail', 'medium', 'medium_large', 'large', 'full' );
		foreach ( $default_sizes as $size ) {
			$sizes[ $size ] = array(
				'width'  => get_option( $size . '_size_w' ),
				'height' => get_option( $size . '_size_h' ),
				'crop'   => get_option( $size . '_crop' ),
			);
		}

		// Get custom sizes.
		if ( $_wp_additional_image_sizes ) {
			$sizes = array_merge( $sizes, $_wp_additional_image_sizes );
		}

		return $sizes;
	}
}
