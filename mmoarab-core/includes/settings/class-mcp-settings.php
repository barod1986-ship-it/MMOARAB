<?php
/**
 * Settings page for MOMARAB CORE plugin.
 *
 * @package Momarab_Core
 */

namespace Momarab_Core;

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Settings class.
 */
class MCP_Settings {

	/**
	 * Settings page slug.
	 *
	 * @var string
	 */
	private $page_slug = 'mcp-settings';

	/**
	 * Add admin menu.
	 */
	public function add_menu() {
		add_menu_page(
			__( 'MOMARAB CORE', 'momarab-core' ),
			__( 'MOMARAB CORE', 'momarab-core' ),
			'manage_options',
			$this->page_slug,
			array( $this, 'render_settings_page' ),
			'dashicons-games',
			30
		);

		add_submenu_page(
			$this->page_slug,
			__( 'الإعدادات', 'momarab-core' ),
			__( 'الإعدادات', 'momarab-core' ),
			'manage_options',
			$this->page_slug,
			array( $this, 'render_settings_page' )
		);
	}

	/**
	 * Initialize settings.
	 */
	public function init() {
		register_setting(
			'mcp_settings_group',
			'mcp_settings',
			array( $this, 'sanitize_settings' )
		);

		add_settings_section(
			'mcp_terms_section',
			__( 'المصطلحات الأساسية', 'momarab-core' ),
			array( $this, 'render_terms_section' ),
			$this->page_slug
		);

		add_settings_section(
			'mcp_related_news_section',
			__( 'عرض الأخبار المرتبطة', 'momarab-core' ),
			array( $this, 'render_related_news_section' ),
			$this->page_slug
		);

		add_settings_field(
			'seed_terms_descriptions',
			__( 'إضافة/تحديث الوصف', 'momarab-core' ),
			array( $this, 'render_seed_terms_field' ),
			$this->page_slug,
			'mcp_terms_section'
		);

		add_settings_field(
			'descriptions_update_only',
			__( 'تحديث الأوصاف فقط', 'momarab-core' ),
			array( $this, 'render_descriptions_update_field' ),
			$this->page_slug,
			'mcp_terms_section'
		);

		add_settings_field(
			'related_news_enabled',
			__( 'تمكين الأخبار المرتبطة', 'momarab-core' ),
			array( $this, 'render_related_news_enabled_field' ),
			$this->page_slug,
			'mcp_related_news_section'
		);

		add_settings_field(
			'related_news_title',
			__( 'عنوان قسم الأخبار', 'momarab-core' ),
			array( $this, 'render_related_news_title_field' ),
			$this->page_slug,
			'mcp_related_news_section'
		);
	}

	/**
	 * Render settings page.
	 */
	public function render_settings_page() {
		if ( ! current_user_can( 'manage_options' ) ) {
			return;
		}

		// Handle terms generation.
		if ( isset( $_POST['generate_terms'] ) && wp_verify_nonce( $_POST['mcp_settings_nonce'], 'mcp_settings_save' ) ) {
			$terms_manager = new MCP_Terms_Manager();
			$terms_manager->generate_default_terms();
			add_settings_error( 'mcp_settings', 'terms_generated', __( 'تم إنشاء المصطلحات الأساسية بنجاح.', 'momarab-core' ), 'success' );
		}

		include MCP_DIR . 'includes/settings/views/settings-page.php';
	}

	/**
	 * Render terms section.
	 */
	public function render_terms_section() {
		echo '<p>' . esc_html__( 'إدارة المصطلحات الأساسية للألعاب.', 'momarab-core' ) . '</p>';
	}

	/**
	 * Render related news section.
	 */
	public function render_related_news_section() {
		echo '<p>' . esc_html__( 'إعدادات عرض الأخبار المرتبطة بالألعاب.', 'momarab-core' ) . '</p>';
	}

	/**
	 * Render seed terms field.
	 */
	public function render_seed_terms_field() {
		$settings = get_option( 'mcp_settings', array() );
		$value = isset( $settings['seed_terms_descriptions'] ) ? $settings['seed_terms_descriptions'] : false;
		?>
		<label>
			<input type="checkbox" name="mcp_settings[seed_terms_descriptions]" value="1" <?php checked( $value ); ?> />
			<?php esc_html_e( 'إضافة أو تحديث أوصاف المصطلحات', 'momarab-core' ); ?>
		</label>
		<?php
	}

	/**
	 * Render descriptions update field.
	 */
	public function render_descriptions_update_field() {
		$settings = get_option( 'mcp_settings', array() );
		$value = isset( $settings['descriptions_update_only'] ) ? $settings['descriptions_update_only'] : false;
		?>
		<label>
			<input type="checkbox" name="mcp_settings[descriptions_update_only]" value="1" <?php checked( $value ); ?> />
			<?php esc_html_e( 'تحديث الأوصاف فقط دون إضافة مصطلحات جديدة', 'momarab-core' ); ?>
		</label>
		<?php
	}

	/**
	 * Render related news enabled field.
	 */
	public function render_related_news_enabled_field() {
		$settings = get_option( 'mcp_settings', array() );
		$value = isset( $settings['related_news_enabled'] ) ? $settings['related_news_enabled'] : true;
		?>
		<label>
			<input type="checkbox" name="mcp_settings[related_news_enabled]" value="1" <?php checked( $value ); ?> />
			<?php esc_html_e( 'عرض الأخبار المرتبطة في صفحة اللعبة', 'momarab-core' ); ?>
		</label>
		<?php
	}

	/**
	 * Render related news title field.
	 */
	public function render_related_news_title_field() {
		$settings = get_option( 'mcp_settings', array() );
		$value = isset( $settings['related_news_title'] ) ? $settings['related_news_title'] : __( 'آخر خبر عن اللعبة', 'momarab-core' );
		?>
		<input type="text" name="mcp_settings[related_news_title]" value="<?php echo esc_attr( $value ); ?>" class="regular-text" />
		<?php
	}

	/**
	 * Sanitize settings.
	 *
	 * @param array $input Raw input data.
	 * @return array Sanitized settings.
	 */
	public function sanitize_settings( $input ) {
		$sanitized = array();

		if ( isset( $input['seed_terms_descriptions'] ) ) {
			$sanitized['seed_terms_descriptions'] = (bool) $input['seed_terms_descriptions'];
		}

		if ( isset( $input['descriptions_update_only'] ) ) {
			$sanitized['descriptions_update_only'] = (bool) $input['descriptions_update_only'];
		}

		if ( isset( $input['related_news_enabled'] ) ) {
			$sanitized['related_news_enabled'] = (bool) $input['related_news_enabled'];
		}

		if ( isset( $input['related_news_title'] ) ) {
			$sanitized['related_news_title'] = sanitize_text_field( $input['related_news_title'] );
		}

		return $sanitized;
	}
}
