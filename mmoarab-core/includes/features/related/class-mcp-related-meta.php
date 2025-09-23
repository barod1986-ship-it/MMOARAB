<?php
/**
 * Related posts meta field for linking posts to games.
 *
 * @package Momarab_Core
 */

namespace Momarab_Core;

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Related posts meta class.
 */
class MCP_Related_Meta {

	/**
	 * Constructor.
	 */
	public function __construct() {
		add_action( 'add_meta_boxes', array( $this, 'add_meta_box' ) );
		add_action( 'save_post', array( $this, 'save_meta' ) );
		add_action( 'wp_ajax_mcp_search_games', array( $this, 'ajax_search_games' ) );
	}

	/**
	 * Add meta box for post type.
	 */
	public function add_meta_box() {
		add_meta_box(
			'mcp_related_game',
			__( 'ربط باللعبة', 'momarab-core' ),
			array( $this, 'render_meta_box' ),
			'post',
			'side',
			'default'
		);
	}

	/**
	 * Render meta box.
	 *
	 * @param \WP_Post $post The post object.
	 */
	public function render_meta_box( $post ) {
		wp_nonce_field( 'mcp_related_meta_save', 'mcp_related_meta_nonce' );

		$related_game_id = get_post_meta( $post->ID, 'mcp_related_game_id', true );
		$game_title = '';

		if ( $related_game_id ) {
			$game_post = get_post( $related_game_id );
			if ( $game_post && 'games' === $game_post->post_type ) {
				$game_title = $game_post->post_title;
			}
		}

		?>
		<div class="mcp-related-game-field">
			<label for="mcp_related_game_select"><?php esc_html_e( 'اختيار لعبة:', 'momarab-core' ); ?></label>
			<select id="mcp_related_game_select" name="mcp_related_game_id" style="width: 100%;">
				<?php if ( $related_game_id && $game_title ) : ?>
					<option value="<?php echo esc_attr( $related_game_id ); ?>" selected="selected">
						<?php echo esc_html( $game_title ); ?>
					</option>
				<?php endif; ?>
			</select>
			<p class="description">
				<?php esc_html_e( 'ربط هذا المقال بلعبة معينة لعرضه في صفحة اللعبة.', 'momarab-core' ); ?>
			</p>
		</div>

		<script type="text/javascript">
		jQuery(document).ready(function($) {
			$('#mcp_related_game_select').select2({
				ajax: {
					url: ajaxurl,
					dataType: 'json',
					delay: 250,
					data: function (params) {
						return {
							q: params.term,
							action: 'mcp_search_games',
							nonce: '<?php echo esc_js( wp_create_nonce( 'mcp_search_games_nonce' ) ); ?>'
						};
					},
					processResults: function (data) {
						return {
							results: data.data || []
						};
					},
					cache: true
				},
				placeholder: '<?php esc_attr_e( 'ابحث عن لعبة...', 'momarab-core' ); ?>',
				allowClear: true,
				minimumInputLength: 2
			});
		});
		</script>
		<?php
	}

	/**
	 * Save meta field.
	 *
	 * @param int $post_id The post ID.
	 */
	public function save_meta( $post_id ) {
		// Check if this is a post.
		if ( 'post' !== get_post_type( $post_id ) ) {
			return;
		}

		// Check nonce.
		if ( ! isset( $_POST['mcp_related_meta_nonce'] ) || ! wp_verify_nonce( $_POST['mcp_related_meta_nonce'], 'mcp_related_meta_save' ) ) {
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

		// Save the related game ID.
		if ( isset( $_POST['mcp_related_game_id'] ) ) {
			$game_id = intval( $_POST['mcp_related_game_id'] );
			
			// Validate that the game exists and is published.
			if ( $game_id > 0 ) {
				$game_post = get_post( $game_id );
				if ( $game_post && 'games' === $game_post->post_type && 'publish' === $game_post->post_status ) {
					update_post_meta( $post_id, 'mcp_related_game_id', $game_id );
				} else {
					delete_post_meta( $post_id, 'mcp_related_game_id' );
				}
			} else {
				delete_post_meta( $post_id, 'mcp_related_game_id' );
			}
		}

		// Clear related news cache.
		$this->clear_related_cache();
	}

	/**
	 * Ajax search for games.
	 */
	public function ajax_search_games() {
		// Check nonce.
		if ( ! check_ajax_referer( 'mcp_search_games_nonce', 'nonce', false ) ) {
			wp_send_json_error( array(
				'message' => __( 'خطأ في التحقق من الأمان.', 'momarab-core' ),
			) );
		}

		$search_term = isset( $_GET['q'] ) ? sanitize_text_field( $_GET['q'] ) : '';

		if ( empty( $search_term ) ) {
			wp_send_json_success( array() );
		}

		$query = new \WP_Query( array(
			'post_type'      => 'games',
			'post_status'    => 'publish',
			'posts_per_page' => 20,
			's'              => $search_term,
			'orderby'        => 'title',
			'order'          => 'ASC',
		) );

		$results = array();
		if ( $query->have_posts() ) {
			while ( $query->have_posts() ) {
				$query->the_post();
				$results[] = array(
					'id'   => get_the_ID(),
					'text' => get_the_title(),
				);
			}
			wp_reset_postdata();
		}

		wp_send_json_success( $results );
	}

	/**
	 * Clear related news cache.
	 */
	private function clear_related_cache() {
		global $wpdb;

		$transients = $wpdb->get_results(
			"SELECT option_name FROM {$wpdb->options} WHERE option_name LIKE '_transient_mcp_news_%'"
		);

		foreach ( $transients as $transient ) {
			$key = str_replace( '_transient_', '', $transient->option_name );
			delete_transient( $key );
		}
	}
}
