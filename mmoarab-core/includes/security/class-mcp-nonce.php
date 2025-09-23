<?php
/**
 * Nonce management for MOMARAB CORE plugin.
 *
 * @package Momarab_Core
 */

namespace Momarab_Core;

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Nonce management class.
 */
class MCP_Nonce {

	/**
	 * Create nonce for meta fields.
	 *
	 * @return string Nonce field HTML.
	 */
	public static function create_meta_nonce() {
		return wp_nonce_field( 'mcp_meta_save', 'mcp_meta_nonce', true, false );
	}

	/**
	 * Verify meta nonce.
	 *
	 * @return bool True if valid.
	 */
	public static function verify_meta_nonce() {
		return isset( $_POST['mcp_meta_nonce'] ) && wp_verify_nonce( $_POST['mcp_meta_nonce'], 'mcp_meta_save' );
	}

	/**
	 * Create nonce for settings.
	 *
	 * @return string Nonce field HTML.
	 */
	public static function create_settings_nonce() {
		return wp_nonce_field( 'mcp_settings_save', 'mcp_settings_nonce', true, false );
	}

	/**
	 * Verify settings nonce.
	 *
	 * @return bool True if valid.
	 */
	public static function verify_settings_nonce() {
		return isset( $_POST['mcp_settings_nonce'] ) && wp_verify_nonce( $_POST['mcp_settings_nonce'], 'mcp_settings_save' );
	}

	/**
	 * Create nonce for Ajax filter.
	 *
	 * @return string Nonce value.
	 */
	public static function create_filter_nonce() {
		return wp_create_nonce( 'mcp_filter_nonce' );
	}

	/**
	 * Verify Ajax filter nonce.
	 *
	 * @param string $nonce Nonce value.
	 * @return bool True if valid.
	 */
	public static function verify_filter_nonce( $nonce ) {
		return wp_verify_nonce( $nonce, 'mcp_filter_nonce' );
	}

	/**
	 * Check Ajax referer for filter.
	 *
	 * @param string $nonce_name Nonce field name.
	 * @return bool True if valid.
	 */
	public static function check_ajax_filter_referer( $nonce_name = 'nonce' ) {
		return check_ajax_referer( 'mcp_filter_nonce', $nonce_name, false );
	}

	/**
	 * Create nonce for Select2 Ajax.
	 *
	 * @return string Nonce value.
	 */
	public static function create_select2_nonce() {
		return wp_create_nonce( 'mcp_select2_nonce' );
	}

	/**
	 * Verify Select2 Ajax nonce.
	 *
	 * @param string $nonce Nonce value.
	 * @return bool True if valid.
	 */
	public static function verify_select2_nonce( $nonce ) {
		return wp_verify_nonce( $nonce, 'mcp_select2_nonce' );
	}

	/**
	 * Check Ajax referer for Select2.
	 *
	 * @param string $nonce_name Nonce field name.
	 * @return bool True if valid.
	 */
	public static function check_ajax_select2_referer( $nonce_name = 'nonce' ) {
		return check_ajax_referer( 'mcp_select2_nonce', $nonce_name, false );
	}

	/**
	 * Get nonce lifetime.
	 *
	 * @return int Nonce lifetime in seconds.
	 */
	public static function get_nonce_lifetime() {
		return apply_filters( 'nonce_life', DAY_IN_SECONDS );
	}

	/**
	 * Generate secure random string.
	 *
	 * @param int $length String length.
	 * @return string Random string.
	 */
	public static function generate_random_string( $length = 32 ) {
		if ( function_exists( 'random_bytes' ) ) {
			return bin2hex( random_bytes( $length / 2 ) );
		}

		// Fallback for older PHP versions.
		return substr( str_shuffle( str_repeat( '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ', ceil( $length / 62 ) ) ), 1, $length );
	}

	/**
	 * Hash sensitive data.
	 *
	 * @param string $data Data to hash.
	 * @return string Hashed data.
	 */
	public static function hash_data( $data ) {
		return wp_hash( $data );
	}

	/**
	 * Verify hashed data.
	 *
	 * @param string $data Original data.
	 * @param string $hash Hashed data.
	 * @return bool True if valid.
	 */
	public static function verify_hash( $data, $hash ) {
		return hash_equals( self::hash_data( $data ), $hash );
	}
}
