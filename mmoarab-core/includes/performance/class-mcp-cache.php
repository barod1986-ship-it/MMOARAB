<?php
/**
 * Cache management for MOMARAB CORE plugin.
 *
 * @package Momarab_Core
 */

namespace Momarab_Core;

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Cache management class.
 */
class MCP_Cache {

	/**
	 * Default cache duration in seconds (10 minutes).
	 */
	const DEFAULT_CACHE_DURATION = 600;

	/**
	 * Constructor.
	 */
	public function __construct() {
		add_action( 'save_post', array( $this, 'clear_game_cache' ) );
		add_action( 'transition_post_status', array( $this, 'clear_archive_cache' ), 10, 3 );
		add_action( 'created_term', array( $this, 'clear_taxonomy_cache' ), 10, 3 );
		add_action( 'edited_term', array( $this, 'clear_taxonomy_cache' ), 10, 3 );
		add_action( 'deleted_term', array( $this, 'clear_taxonomy_cache' ), 10, 3 );
		add_action( 'update_option_mcp_settings', array( $this, 'clear_settings_cache' ) );
	}

	/**
	 * Get cached data.
	 *
	 * @param string $key Cache key.
	 * @return mixed Cached data or false if not found.
	 */
	public static function get( $key ) {
		return get_transient( self::get_cache_key( $key ) );
	}

	/**
	 * Set cached data.
	 *
	 * @param string $key      Cache key.
	 * @param mixed  $data     Data to cache.
	 * @param int    $duration Cache duration in seconds.
	 * @return bool True on success.
	 */
	public static function set( $key, $data, $duration = null ) {
		if ( null === $duration ) {
			$duration = self::DEFAULT_CACHE_DURATION;
		}

		return set_transient( self::get_cache_key( $key ), $data, $duration );
	}

	/**
	 * Delete cached data.
	 *
	 * @param string $key Cache key.
	 * @return bool True on success.
	 */
	public static function delete( $key ) {
		return delete_transient( self::get_cache_key( $key ) );
	}

	/**
	 * Clear all plugin cache.
	 */
	public static function clear_all() {
		global $wpdb;

		$transients = $wpdb->get_results(
			"SELECT option_name FROM {$wpdb->options} WHERE option_name LIKE '_transient_mcp_%'"
		);

		foreach ( $transients as $transient ) {
			$key = str_replace( '_transient_', '', $transient->option_name );
			delete_transient( $key );
		}
	}

	/**
	 * Clear game-related cache on save.
	 *
	 * @param int $post_id Post ID.
	 */
	public function clear_game_cache( $post_id ) {
		if ( 'games' !== get_post_type( $post_id ) ) {
			return;
		}

		// Clear all mcp_* transients.
		self::clear_all();
	}

	/**
	 * Clear archive cache on post status change.
	 *
	 * @param string   $new_status New post status.
	 * @param string   $old_status Old post status.
	 * @param \WP_Post $post       Post object.
	 */
	public function clear_archive_cache( $new_status, $old_status, $post ) {
		if ( 'games' !== $post->post_type ) {
			return;
		}

		// Clear archive and widget caches.
		$this->clear_cache_by_pattern( 'mcp_archive_*' );
		$this->clear_cache_by_pattern( 'mcp_widget_*' );
	}

	/**
	 * Clear taxonomy cache on term changes.
	 *
	 * @param int    $term_id  Term ID.
	 * @param int    $tt_id    Term taxonomy ID.
	 * @param string $taxonomy Taxonomy name.
	 */
	public function clear_taxonomy_cache( $term_id, $tt_id, $taxonomy ) {
		$game_taxonomies = array( 'game_type', 'game_status', 'game_mode', 'game_platform' );

		if ( ! in_array( $taxonomy, $game_taxonomies, true ) ) {
			return;
		}

		// Clear archive and widget caches.
		$this->clear_cache_by_pattern( 'mcp_archive_*' );
		$this->clear_cache_by_pattern( 'mcp_widget_*' );
	}

	/**
	 * Clear settings-related cache.
	 */
	public function clear_settings_cache() {
		$this->clear_cache_by_pattern( 'mcp_news_*' );
		$this->clear_cache_by_pattern( 'mcp_widget_*' );
	}

	/**
	 * Clear cache by pattern.
	 *
	 * @param string $pattern Cache key pattern.
	 */
	private function clear_cache_by_pattern( $pattern ) {
		global $wpdb;

		$like_pattern = str_replace( '*', '%', $pattern );
		$transients = $wpdb->get_results(
			$wpdb->prepare(
				"SELECT option_name FROM {$wpdb->options} WHERE option_name LIKE %s",
				'_transient_' . $like_pattern
			)
		);

		foreach ( $transients as $transient ) {
			$key = str_replace( '_transient_', '', $transient->option_name );
			delete_transient( $key );
		}
	}

	/**
	 * Get cache key with prefix.
	 *
	 * @param string $key Original key.
	 * @return string Prefixed cache key.
	 */
	private static function get_cache_key( $key ) {
		return 'mcp_' . $key;
	}

	/**
	 * Get cache statistics.
	 *
	 * @return array Cache statistics.
	 */
	public static function get_cache_stats() {
		global $wpdb;

		$transients = $wpdb->get_results(
			"SELECT option_name, option_value FROM {$wpdb->options} WHERE option_name LIKE '_transient_mcp_%'"
		);

		$stats = array(
			'total_keys' => count( $transients ),
			'total_size' => 0,
			'keys_by_type' => array(),
		);

		foreach ( $transients as $transient ) {
			$key = str_replace( '_transient_mcp_', '', $transient->option_name );
			$size = strlen( $transient->option_value );
			$stats['total_size'] += $size;

			// Categorize by key type.
			if ( strpos( $key, 'archive_' ) === 0 ) {
				$type = 'archive';
			} elseif ( strpos( $key, 'widget_' ) === 0 ) {
				$type = 'widget';
			} elseif ( strpos( $key, 'news_' ) === 0 ) {
				$type = 'news';
			} elseif ( strpos( $key, 'shortcode_' ) === 0 ) {
				$type = 'shortcode';
			} else {
				$type = 'other';
			}

			if ( ! isset( $stats['keys_by_type'][ $type ] ) ) {
				$stats['keys_by_type'][ $type ] = array( 'count' => 0, 'size' => 0 );
			}

			$stats['keys_by_type'][ $type ]['count']++;
			$stats['keys_by_type'][ $type ]['size'] += $size;
		}

		return $stats;
	}

	/**
	 * Check if caching is enabled.
	 *
	 * @return bool True if caching is enabled.
	 */
	public static function is_caching_enabled() {
		return apply_filters( 'mcp_enable_caching', true );
	}

	/**
	 * Get cache duration for a specific type.
	 *
	 * @param string $type Cache type.
	 * @return int Cache duration in seconds.
	 */
	public static function get_cache_duration( $type = 'default' ) {
		$durations = array(
			'archive'   => 600,  // 10 minutes.
			'widget'    => 600,  // 10 minutes.
			'news'      => 600,  // 10 minutes.
			'shortcode' => 600,  // 10 minutes.
			'default'   => self::DEFAULT_CACHE_DURATION,
		);

		$duration = isset( $durations[ $type ] ) ? $durations[ $type ] : $durations['default'];

		return apply_filters( 'mcp_cache_duration', $duration, $type );
	}
}
