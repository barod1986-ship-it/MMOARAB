<?php
/**
 * Capabilities management for MOMARAB CORE plugin.
 *
 * @package Momarab_Core
 */

namespace Momarab_Core;

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Capabilities management class.
 */
class MCP_Capabilities {

	/**
	 * Check if user can manage plugin settings.
	 *
	 * @param int $user_id User ID (optional, defaults to current user).
	 * @return bool True if user can manage settings.
	 */
	public static function can_manage_settings( $user_id = null ) {
		if ( null === $user_id ) {
			return current_user_can( 'manage_options' );
		}

		return user_can( $user_id, 'manage_options' );
	}

	/**
	 * Check if user can manage taxonomy terms.
	 *
	 * @param int $user_id User ID (optional, defaults to current user).
	 * @return bool True if user can manage terms.
	 */
	public static function can_manage_terms( $user_id = null ) {
		if ( null === $user_id ) {
			return current_user_can( 'manage_categories' ) || current_user_can( 'manage_options' );
		}

		return user_can( $user_id, 'manage_categories' ) || user_can( $user_id, 'manage_options' );
	}

	/**
	 * Check if user can edit a specific post.
	 *
	 * @param int $post_id Post ID.
	 * @param int $user_id User ID (optional, defaults to current user).
	 * @return bool True if user can edit post.
	 */
	public static function can_edit_post( $post_id, $user_id = null ) {
		if ( null === $user_id ) {
			return current_user_can( 'edit_post', $post_id );
		}

		return user_can( $user_id, 'edit_post', $post_id );
	}

	/**
	 * Check if user can edit games.
	 *
	 * @param int $user_id User ID (optional, defaults to current user).
	 * @return bool True if user can edit games.
	 */
	public static function can_edit_games( $user_id = null ) {
		if ( null === $user_id ) {
			return current_user_can( 'edit_posts' );
		}

		return user_can( $user_id, 'edit_posts' );
	}

	/**
	 * Check if user can publish games.
	 *
	 * @param int $user_id User ID (optional, defaults to current user).
	 * @return bool True if user can publish games.
	 */
	public static function can_publish_games( $user_id = null ) {
		if ( null === $user_id ) {
			return current_user_can( 'publish_posts' );
		}

		return user_can( $user_id, 'publish_posts' );
	}

	/**
	 * Check if user can delete games.
	 *
	 * @param int $user_id User ID (optional, defaults to current user).
	 * @return bool True if user can delete games.
	 */
	public static function can_delete_games( $user_id = null ) {
		if ( null === $user_id ) {
			return current_user_can( 'delete_posts' );
		}

		return user_can( $user_id, 'delete_posts' );
	}

	/**
	 * Check if user can upload files.
	 *
	 * @param int $user_id User ID (optional, defaults to current user).
	 * @return bool True if user can upload files.
	 */
	public static function can_upload_files( $user_id = null ) {
		if ( null === $user_id ) {
			return current_user_can( 'upload_files' );
		}

		return user_can( $user_id, 'upload_files' );
	}

	/**
	 * Check if current request is from admin area.
	 *
	 * @return bool True if admin request.
	 */
	public static function is_admin_request() {
		return is_admin() && ! wp_doing_ajax();
	}

	/**
	 * Check if current request is Ajax.
	 *
	 * @return bool True if Ajax request.
	 */
	public static function is_ajax_request() {
		return wp_doing_ajax();
	}

	/**
	 * Check if current request is REST API.
	 *
	 * @return bool True if REST API request.
	 */
	public static function is_rest_request() {
		return defined( 'REST_REQUEST' ) && REST_REQUEST;
	}

	/**
	 * Check if current request is from frontend.
	 *
	 * @return bool True if frontend request.
	 */
	public static function is_frontend_request() {
		return ! self::is_admin_request() && ! self::is_ajax_request() && ! self::is_rest_request();
	}

	/**
	 * Get current user capability level.
	 *
	 * @return string User capability level.
	 */
	public static function get_user_capability_level() {
		if ( ! is_user_logged_in() ) {
			return 'guest';
		}

		if ( current_user_can( 'manage_options' ) ) {
			return 'administrator';
		}

		if ( current_user_can( 'edit_others_posts' ) ) {
			return 'editor';
		}

		if ( current_user_can( 'publish_posts' ) ) {
			return 'author';
		}

		if ( current_user_can( 'edit_posts' ) ) {
			return 'contributor';
		}

		return 'subscriber';
	}

	/**
	 * Log capability check for debugging.
	 *
	 * @param string $capability Capability being checked.
	 * @param bool   $result     Check result.
	 * @param int    $user_id    User ID.
	 */
	public static function log_capability_check( $capability, $result, $user_id = null ) {
		if ( defined( 'WP_DEBUG' ) && WP_DEBUG ) {
			// أظهر تنبيه/سجل، لكن لا تُوقف السلوك الوظيفي.
			// Capability check completed silently.
		}
	}

	/**
	 * Check multiple capabilities at once.
	 *
	 * @param array $capabilities Array of capabilities to check.
	 * @param int   $user_id      User ID (optional, defaults to current user).
	 * @param bool  $require_all  Whether all capabilities are required (default: true).
	 * @return bool True if capability requirements are met.
	 */
	public static function check_multiple_capabilities( $capabilities, $user_id = null, $require_all = true ) {
		if ( empty( $capabilities ) ) {
			return false;
		}

		$results = array();
		foreach ( $capabilities as $capability ) {
			if ( null === $user_id ) {
				$results[] = current_user_can( $capability );
			} else {
				$results[] = user_can( $user_id, $capability );
			}
		}

		if ( $require_all ) {
			return ! in_array( false, $results, true );
		}

		return in_array( true, $results, true );
	}
}
