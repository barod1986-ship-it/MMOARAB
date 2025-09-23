<?php
/**
 * Meta fields save functionality for games.
 *
 * @package Momarab_Core
 */

namespace Momarab_Core;

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Meta fields save class.
 */
class MCP_Meta_Save {

	/**
	 * Constructor.
	 */
	public function __construct() {
		add_action( 'save_post', array( $this, 'save_meta_fields' ) );
		add_action( 'save_post_games', array( $this, 'save_gallery_meta' ) );
	}

	/**
	 * Save meta fields for games.
	 *
	 * @param int $post_id The post ID.
	 */
	public function save_meta_fields( $post_id ) {
		// Check if this is a games post.
		if ( 'games' !== get_post_type( $post_id ) ) {
			return;
		}

		// Check nonce.
		$nonce = isset( $_POST['mcp_meta_nonce'] ) ? sanitize_text_field( wp_unslash( $_POST['mcp_meta_nonce'] ) ) : '';
		if ( ! $nonce || ! wp_verify_nonce( $nonce, 'mcp_meta_save' ) ) {
			return;
		}

		// Check user capabilities.
		if ( ! current_user_can( 'edit_post', $post_id ) ) {
			return;
		}

		// Check if this is an autosave.
		if ( defined( 'DOING_AUTOSAVE' ) && DOING_AUTOSAVE ) {
			return;
		}

		// Save basic fields.
		$this->save_basic_fields( $post_id );

		// Save engine fields.
		$this->save_engine_fields( $post_id );

		// Save feature fields.
		$this->save_feature_fields( $post_id );

		// Save media fields.
		$this->save_media_fields( $post_id );

		// Save rating fields.
		$this->save_rating_fields( $post_id );

		// Clear cache after saving.
		$this->clear_cache();
	}

	/**
	 * Save basic fields.
	 *
	 * @param int $post_id The post ID.
	 */
	private function save_basic_fields( $post_id ) {
		$basic_fields = array(
			'mcp_official_site' => 'validate_url_field',
			'mcp_developer'     => 'validate_text_field',
			'mcp_publisher'     => 'validate_text_field',
			'mcp_release_date'  => 'validate_date_field',
		);

		foreach ( $basic_fields as $field => $validator ) {
			if ( isset( $_POST[ $field ] ) ) {
				$value = MCP_Meta_Validation::$validator( wp_unslash( $_POST[ $field ] ) );
				update_post_meta( $post_id, $field, $value );
			}
		}
	}

	/**
	 * Save engine fields.
	 *
	 * @param int $post_id The post ID.
	 */
	private function save_engine_fields( $post_id ) {
		if ( isset( $_POST['mcp_engine'] ) ) {
			$engines = MCP_Meta_Validation::validate_engines( $_POST['mcp_engine'] );
			update_post_meta( $post_id, 'mcp_engine', $engines );
		} else {
			delete_post_meta( $post_id, 'mcp_engine' );
		}
	}

	/**
	 * Save feature fields.
	 *
	 * @param int $post_id The post ID.
	 */
	private function save_feature_fields( $post_id ) {
		$feature_fields = array(
			'mcp_feature_1',
			'mcp_feature_2',
			'mcp_feature_3',
			'mcp_feature_4',
		);

		foreach ( $feature_fields as $field ) {
			if ( isset( $_POST[ $field ] ) ) {
				$value = MCP_Meta_Validation::validate_text_field( $_POST[ $field ] );
				update_post_meta( $post_id, $field, $value );
			}
		}
	}

	/**
	 * Save media fields.
	 *
	 * @param int $post_id The post ID.
	 */
	private function save_media_fields( $post_id ) {
		// Save YouTube URLs.
		$youtube_fields = array( 'mcp_trailer_youtube_1', 'mcp_trailer_youtube_2' );
		foreach ( $youtube_fields as $field ) {
			if ( isset( $_POST[ $field ] ) ) {
				$url = MCP_Meta_Validation::validate_youtube_url( $_POST[ $field ] );
				if ( $url ) {
					update_post_meta( $post_id, $field, $url );
				} else {
					delete_post_meta( $post_id, $field );
				}
			}
		}
	}

	/**
	 * Save rating fields.
	 *
	 * @param int $post_id The post ID.
	 */
	private function save_rating_fields( $post_id ) {
		$rating_types = array( 'story', 'gameplay', 'graphics', 'audio', 'overall' );

		foreach ( $rating_types as $type ) {
			// Save rating value.
			$rating_field = 'mcp_rating_' . $type;
			if ( isset( $_POST[ $rating_field ] ) ) {
				$rating = MCP_Meta_Validation::validate_rating( $_POST[ $rating_field ] );
				if ( false !== $rating ) {
					update_post_meta( $post_id, $rating_field, $rating );
				} else {
					delete_post_meta( $post_id, $rating_field );
				}
			}

			// Save rating note.
			$note_field = 'mcp_rating_' . $type . '_note';
			if ( isset( $_POST[ $note_field ] ) ) {
				$note = MCP_Meta_Validation::validate_textarea_field( $_POST[ $note_field ] );
				update_post_meta( $post_id, $note_field, $note );
			}
		}
	}

	/**
	 * Clear cache after saving.
	 */
	private function clear_cache() {
		// Clear all mcp_* transients.
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
	 * Save gallery meta with secure validation and 4 image limit.
	 *
	 * @param int $post_id The post ID.
	 */
	public function save_gallery_meta( $post_id ) {
		if ( ! isset( $_POST['mcp_meta_nonce_gallery'] ) || ! wp_verify_nonce( $_POST['mcp_meta_nonce_gallery'], 'mcp_meta_gallery' ) ) {
			return;
		}
		if ( defined( 'DOING_AUTOSAVE' ) && DOING_AUTOSAVE ) {
			return;
		}
		if ( ! current_user_can( 'edit_post', $post_id ) ) {
			return;
		}

		$raw  = isset( $_POST['mcp_gallery'] ) ? (string) $_POST['mcp_gallery'] : '';
		$keep = array_slice( array_unique( array_filter( array_map( 'intval', explode( ',', $raw ) ) ) ), 0, 4 );

		if ( empty( $keep ) ) {
			delete_post_meta( $post_id, 'mcp_gallery' );
		} else {
			update_post_meta( $post_id, 'mcp_gallery', implode( ',', $keep ) );
		}
	}
}
