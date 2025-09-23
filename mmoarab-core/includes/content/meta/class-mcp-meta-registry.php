<?php
/**
 * Meta fields registry for games.
 *
 * @package Momarab_Core
 */

namespace Momarab_Core;

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Meta fields registry class.
 */
class MCP_Meta_Registry {

	/**
	 * Constructor.
	 */
	public function __construct() {
		add_action( 'add_meta_boxes', array( $this, 'add_meta_boxes' ) );
	}

	/**
	 * Add meta boxes for games.
	 */
	public function add_meta_boxes() {
		add_meta_box(
			'mcp_game_basics',
			__( 'المعلومات الأساسية', 'momarab-core' ),
			array( $this, 'render_basics_meta_box' ),
			'games',
			'normal',
			'high'
		);

		add_meta_box(
			'mcp_game_engine',
			__( 'المحرك', 'momarab-core' ),
			array( $this, 'render_engine_meta_box' ),
			'games',
			'normal',
			'high'
		);

		add_meta_box(
			'mcp_game_features',
			__( 'الميزات', 'momarab-core' ),
			array( $this, 'render_features_meta_box' ),
			'games',
			'normal',
			'high'
		);

		add_meta_box(
			'mcp_game_media',
			__( 'الوسائط', 'momarab-core' ),
			array( $this, 'render_media_meta_box' ),
			'games',
			'normal',
			'high'
		);

		add_meta_box(
			'mcp_game_ratings',
			__( 'التقييمات', 'momarab-core' ),
			array( $this, 'render_ratings_meta_box' ),
			'games',
			'normal',
			'high'
		);

		// Gallery meta box
		add_meta_box(
			'mcp_gallery_box',
			__( 'معرض الصور', 'momarab-core' ),
			array( $this, 'render_gallery_meta_box' ),
			'games',
			'side',
			'default'
		);
	}

	/**
	 * Render basics meta box.
	 *
	 * @param \WP_Post $post The post object.
	 */
	public function render_basics_meta_box( $post ) {
		wp_nonce_field( 'mcp_meta_save', 'mcp_meta_nonce' );

		$official_site = get_post_meta( $post->ID, 'mcp_official_site', true );
		$developer     = get_post_meta( $post->ID, 'mcp_developer', true );
		$publisher     = get_post_meta( $post->ID, 'mcp_publisher', true );
		$release_date  = get_post_meta( $post->ID, 'mcp_release_date', true );

		?>
		<table class="form-table">
			<tr>
				<th scope="row">
					<label for="mcp_official_site"><?php esc_html_e( 'الموقع الرسمي', 'momarab-core' ); ?></label>
				</th>
				<td>
					<input type="url" id="mcp_official_site" name="mcp_official_site" value="<?php echo esc_attr( $official_site ); ?>" class="regular-text" />
				</td>
			</tr>
			<tr>
				<th scope="row">
					<label for="mcp_developer"><?php esc_html_e( 'المطوّر', 'momarab-core' ); ?></label>
				</th>
				<td>
					<input type="text" id="mcp_developer" name="mcp_developer" value="<?php echo esc_attr( $developer ); ?>" class="regular-text" />
				</td>
			</tr>
			<tr>
				<th scope="row">
					<label for="mcp_publisher"><?php esc_html_e( 'الناشر', 'momarab-core' ); ?></label>
				</th>
				<td>
					<input type="text" id="mcp_publisher" name="mcp_publisher" value="<?php echo esc_attr( $publisher ); ?>" class="regular-text" />
				</td>
			</tr>
			<tr>
				<th scope="row">
					<label for="mcp_release_date"><?php esc_html_e( 'تاريخ الإطلاق', 'momarab-core' ); ?></label>
				</th>
				<td>
					<input type="date" id="mcp_release_date" name="mcp_release_date" value="<?php echo esc_attr( $release_date ); ?>" />
				</td>
			</tr>
		</table>
		<?php
	}

	/**
	 * Render engine meta box.
	 *
	 * @param \WP_Post $post The post object.
	 */
	public function render_engine_meta_box( $post ) {
		$engine = get_post_meta( $post->ID, 'mcp_engine', true );
		if ( ! is_array( $engine ) ) {
			$engine = array();
		}

		$engines = array(
			'unreal_engine' => __( 'Unreal Engine', 'momarab-core' ),
			'unity'         => __( 'Unity', 'momarab-core' ),
			'cryengine'     => __( 'CryEngine', 'momarab-core' ),
			'frostbite'     => __( 'Frostbite', 'momarab-core' ),
			'custom'        => __( 'محرك مخصص', 'momarab-core' ),
		);

		?>
		<table class="form-table">
			<tr>
				<th scope="row"><?php esc_html_e( 'المحرك', 'momarab-core' ); ?></th>
				<td>
					<?php foreach ( $engines as $key => $label ) : ?>
						<label>
							<input type="checkbox" name="mcp_engine[]" value="<?php echo esc_attr( $key ); ?>" <?php checked( in_array( $key, $engine, true ) ); ?> />
							<?php echo esc_html( $label ); ?>
						</label><br />
					<?php endforeach; ?>
				</td>
			</tr>
		</table>
		<?php
	}

	/**
	 * Render features meta box.
	 *
	 * @param \WP_Post $post The post object.
	 */
	public function render_features_meta_box( $post ) {
		$feature_1 = get_post_meta( $post->ID, 'mcp_feature_1', true );
		$feature_2 = get_post_meta( $post->ID, 'mcp_feature_2', true );
		$feature_3 = get_post_meta( $post->ID, 'mcp_feature_3', true );
		$feature_4 = get_post_meta( $post->ID, 'mcp_feature_4', true );

		?>
		<table class="form-table">
			<tr>
				<th scope="row">
					<label for="mcp_feature_1"><?php esc_html_e( 'الميزة 1', 'momarab-core' ); ?></label>
				</th>
				<td>
					<input type="text" id="mcp_feature_1" name="mcp_feature_1" value="<?php echo esc_attr( $feature_1 ); ?>" class="regular-text" />
				</td>
			</tr>
			<tr>
				<th scope="row">
					<label for="mcp_feature_2"><?php esc_html_e( 'الميزة 2', 'momarab-core' ); ?></label>
				</th>
				<td>
					<input type="text" id="mcp_feature_2" name="mcp_feature_2" value="<?php echo esc_attr( $feature_2 ); ?>" class="regular-text" />
				</td>
			</tr>
			<tr>
				<th scope="row">
					<label for="mcp_feature_3"><?php esc_html_e( 'الميزة 3', 'momarab-core' ); ?></label>
				</th>
				<td>
					<input type="text" id="mcp_feature_3" name="mcp_feature_3" value="<?php echo esc_attr( $feature_3 ); ?>" class="regular-text" />
				</td>
			</tr>
			<tr>
				<th scope="row">
					<label for="mcp_feature_4"><?php esc_html_e( 'الميزة 4', 'momarab-core' ); ?></label>
				</th>
				<td>
					<input type="text" id="mcp_feature_4" name="mcp_feature_4" value="<?php echo esc_attr( $feature_4 ); ?>" class="regular-text" />
				</td>
			</tr>
		</table>
		<?php
	}

	/**
	 * Render media meta box.
	 *
	 * @param \WP_Post $post The post object.
	 */
	public function render_media_meta_box( $post ) {
		$youtube_1 = get_post_meta( $post->ID, 'mcp_trailer_youtube_1', true );
		$youtube_2 = get_post_meta( $post->ID, 'mcp_trailer_youtube_2', true );

		?>
		<table class="form-table">
			<tr>
				<th scope="row">
					<label for="mcp_trailer_youtube_1"><?php esc_html_e( 'يوتيوب 1', 'momarab-core' ); ?></label>
				</th>
				<td>
					<input type="url" id="mcp_trailer_youtube_1" name="mcp_trailer_youtube_1" value="<?php echo esc_attr( $youtube_1 ); ?>" class="regular-text" />
					<p class="description"><?php esc_html_e( 'رابط يوتيوب (youtu.be أو youtube.com/watch)', 'momarab-core' ); ?></p>
				</td>
			</tr>
			<tr>
				<th scope="row">
					<label for="mcp_trailer_youtube_2"><?php esc_html_e( 'يوتيوب 2', 'momarab-core' ); ?></label>
				</th>
				<td>
					<input type="url" id="mcp_trailer_youtube_2" name="mcp_trailer_youtube_2" value="<?php echo esc_attr( $youtube_2 ); ?>" class="regular-text" />
					<p class="description"><?php esc_html_e( 'رابط يوتيوب (youtu.be أو youtube.com/watch)', 'momarab-core' ); ?></p>
				</td>
			</tr>
		</table>
		<?php
	}

	/**
	 * Render ratings meta box.
	 *
	 * @param \WP_Post $post The post object.
	 */
	public function render_ratings_meta_box( $post ) {
		$ratings = array(
			'story'    => __( 'القصة', 'momarab-core' ),
			'gameplay' => __( 'الجيمبلاي', 'momarab-core' ),
			'graphics' => __( 'الرسومات', 'momarab-core' ),
			'audio'    => __( 'الصوت', 'momarab-core' ),
			'overall'  => __( 'التقييم النهائي', 'momarab-core' ),
		);

		?>
		<table class="form-table">
			<?php foreach ( $ratings as $key => $label ) : ?>
				<?php
				$rating_value = get_post_meta( $post->ID, 'mcp_rating_' . $key, true );
				$rating_note  = get_post_meta( $post->ID, 'mcp_rating_' . $key . '_note', true );
				?>
				<tr>
					<th scope="row">
						<label for="mcp_rating_<?php echo esc_attr( $key ); ?>"><?php echo esc_html( $label ); ?></label>
					</th>
					<td>
						<input type="number" id="mcp_rating_<?php echo esc_attr( $key ); ?>" name="mcp_rating_<?php echo esc_attr( $key ); ?>" value="<?php echo esc_attr( $rating_value ); ?>" min="1" max="10" step="0.1" style="width: 80px;" />
						<span>/10</span>
						<br />
						<textarea name="mcp_rating_<?php echo esc_attr( $key ); ?>_note" placeholder="<?php esc_attr_e( 'ملاحظة (اختيارية)', 'momarab-core' ); ?>" rows="2" style="width: 100%; margin-top: 5px;"><?php echo esc_textarea( $rating_note ); ?></textarea>
					</td>
				</tr>
			<?php endforeach; ?>
		</table>
		<?php
	}

	/**
	 * Render gallery meta box.
	 *
	 * @param \WP_Post $post The post object.
	 */
	public function render_gallery_meta_box( $post ) {
		wp_nonce_field( 'mcp_meta_gallery', 'mcp_meta_nonce_gallery' );
		$ids = (string) get_post_meta( $post->ID, 'mcp_gallery', true );
		$ids = is_string( $ids ) ? $ids : '';
		?>
		<p>
			<button type="button" class="button mcp-gallery-select"><?php esc_html_e('اختر الصور','momarab-core'); ?></button>
			<button type="button" class="button mcp-gallery-clear"><?php esc_html_e('مسح','momarab-core'); ?></button>
		</p>
		<input type="hidden" id="mcp_gallery" name="mcp_gallery" value="<?php echo esc_attr( $ids ); ?>">
		<ul class="mcp-gallery-preview">
			<?php foreach ( array_filter( array_map( 'intval', explode( ',', $ids ) ) ) as $id ) : ?>
				<li data-id="<?php echo esc_attr( $id ); ?>">
					<?php echo wp_get_attachment_image( $id, 'thumbnail' ); ?>
				</li>
			<?php endforeach; ?>
		</ul>
		<?php
	}
}
