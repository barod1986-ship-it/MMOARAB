<?php
/**
 * Meta fields validation for games.
 *
 * @package Momarab_Core
 */

namespace Momarab_Core;

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Meta fields validation class.
 */
class MCP_Meta_Validation {

	/**
	 * Validate rating value.
	 *
	 * @param mixed $value The rating value.
	 * @return float|false Valid rating or false.
	 */
	public static function validate_rating( $value ) {
		if ( empty( $value ) ) {
			return false;
		}

		$rating = floatval( $value );

		if ( $rating < 1 || $rating > 10 ) {
			return false;
		}

		return $rating;
	}

	/**
	 * Validate YouTube URL.
	 *
	 * @param string $url The YouTube URL.
	 * @return string|false Valid YouTube URL or false.
	 */
	public static function validate_youtube_url( $url ) {
		if ( empty( $url ) ) {
			return false;
		}

		$url = esc_url_raw( $url );

		// Check if it's a valid YouTube URL.
		if ( strpos( $url, 'youtu.be/' ) !== false || strpos( $url, 'youtube.com/watch' ) !== false ) {
			return $url;
		}

		return false;
	}

	/**
	 * Validate gallery images.
	 *
	 * @param string $raw Raw gallery data.
	 * @return string Validated gallery IDs.
	 */
	public static function validate_gallery( $raw ) {
		$ids = array_map( 'intval', explode( ',', (string) $raw ) );
		$ids = array_filter( $ids );                 // remove 0/false
		$ids = array_values( array_unique( $ids ) ); // unique + reindex
		$ids = array_slice( $ids, 0, 4 );            // max 4
		return implode( ',', $ids );
	}

	/**
	 * Validate engine selection.
	 *
	 * @param array $engines Selected engines.
	 * @return array Valid engines.
	 */
	public static function validate_engines( $engines ) {
		if ( ! is_array( $engines ) ) {
			return array();
		}

		$valid_engines = array( 'unreal_engine', 'unity', 'cryengine', 'frostbite', 'custom' );
		$filtered_engines = array();

		foreach ( $engines as $engine ) {
			if ( in_array( $engine, $valid_engines, true ) ) {
				$filtered_engines[] = $engine;
			}
		}

		return $filtered_engines;
	}

	/**
	 * Validate text field.
	 *
	 * @param string $value The text value.
	 * @return string Sanitized text.
	 */
	public static function validate_text_field( $value ) {
		return sanitize_text_field( $value );
	}

	/**
	 * Validate URL field.
	 *
	 * @param string $url The URL value.
	 * @return string Sanitized URL.
	 */
	public static function validate_url_field( $url ) {
		return esc_url_raw( $url );
	}

	/**
	 * Validate date field.
	 *
	 * @param string $date The date value.
	 * @return string Valid date in Y-m-d format or empty.
	 */
	public static function validate_date_field( $date ) {
		if ( empty( $date ) ) {
			return '';
		}

		$timestamp = strtotime( $date );
		if ( false === $timestamp ) {
			return '';
		}

		return date( 'Y-m-d', $timestamp );
	}

	/**
	 * Validate textarea field.
	 *
	 * @param string $value The textarea value.
	 * @return string Sanitized textarea content.
	 */
	public static function validate_textarea_field( $value ) {
		return wp_kses_post( $value );
	}
}
