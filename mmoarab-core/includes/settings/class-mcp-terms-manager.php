<?php
/**
 * Terms manager for generating default taxonomy terms.
 *
 * @package Momarab_Core
 */

namespace Momarab_Core;

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Terms manager class.
 */
class MCP_Terms_Manager {

	/**
	 * Constructor.
	 */
	public function __construct() {
		add_action( 'admin_post_mcp_seed_terms', array( $this, 'handle_seed_terms' ) );
	}

	/**
	 * Handle seed terms request.
	 */
	public function handle_seed_terms() {
		if ( ! current_user_can( 'manage_categories' ) ) {
			wp_die( esc_html__( 'Unauthorized action.', 'momarab-core' ), 403 );
		}
		check_admin_referer( 'mcp_seed_terms' );
		$this->generate_default_terms();
		wp_redirect( add_query_arg( 'mcp_seeded', '1', wp_get_referer() ?: admin_url( 'admin.php?page=mcp-settings' ) ) );
		exit;
	}

	/**
	 * Generate default terms for all taxonomies.
	 */
	public function generate_default_terms() {
		$this->generate_game_type_terms();
		$this->generate_game_status_terms();
		$this->generate_game_mode_terms();
		$this->generate_game_platform_terms();
	}

	/**
	 * Generate game type terms.
	 */
	private function generate_game_type_terms() {
		$terms = array(
			'mmorpg'      => __( 'MMORPG', 'momarab-core' ),
			'mmo-arpg'    => __( 'MMO ARPG', 'momarab-core' ),
			'mmofps'      => __( 'MMOFPS', 'momarab-core' ),
			'moba'        => __( 'MOBA', 'momarab-core' ),
			'mmorts'      => __( 'MMORTS', 'momarab-core' ),
			'survival-mmo' => __( 'Survival MMO', 'momarab-core' ),
			'sandbox-mmo' => __( 'Sandbox MMO', 'momarab-core' ),
			'social-mmo'  => __( 'Social MMO', 'momarab-core' ),
			'battle-royale' => __( 'Battle Royale', 'momarab-core' ),
			'racing-mmo'  => __( 'Racing MMO', 'momarab-core' ),
			'sports-mmo'  => __( 'Sports MMO', 'momarab-core' ),
			'space-mmo'   => __( 'Space MMO', 'momarab-core' ),
			'naval-mmo'   => __( 'Naval MMO', 'momarab-core' ),
			'anime-mmo'   => __( 'أنمي MMO', 'momarab-core' ),
		);

		$this->create_terms( 'game_type', $terms );
	}

	/**
	 * Generate game status terms.
	 */
	private function generate_game_status_terms() {
		$terms = array(
			'upcoming'      => __( 'قادم', 'momarab-core' ),
			'alpha'         => __( 'ألفا', 'momarab-core' ),
			'beta'          => __( 'بيتا', 'momarab-core' ),
			'early-access'  => __( 'وصول مبكر', 'momarab-core' ),
			'released'      => __( 'صادرة', 'momarab-core' ),
		);

		$this->create_terms( 'game_status', $terms );
	}

	/**
	 * Generate game mode terms.
	 */
	private function generate_game_mode_terms() {
		$terms = array(
			'pve'        => __( 'PvE', 'momarab-core' ),
			'pvp'        => __( 'PvP', 'momarab-core' ),
			'pvpve'      => __( 'PvPvE', 'momarab-core' ),
			'open-world' => __( 'عالم مفتوح', 'momarab-core' ),
			'co-op'      => __( 'تعاوني', 'momarab-core' ),
		);

		$this->create_terms( 'game_mode', $terms );
	}

	/**
	 * Generate game platform terms.
	 */
	private function generate_game_platform_terms() {
		$terms = array(
			'pc'              => __( 'PC', 'momarab-core' ),
			'playstation'     => __( 'PlayStation', 'momarab-core' ),
			'xbox'            => __( 'Xbox', 'momarab-core' ),
			'nintendo-switch' => __( 'Nintendo Switch', 'momarab-core' ),
			'mobile'          => __( 'Mobile', 'momarab-core' ),
			'browser'         => __( 'Browser', 'momarab-core' ),
		);

		$this->create_terms( 'game_platform', $terms );
	}

	/**
	 * Create terms for a taxonomy.
	 *
	 * @param string $taxonomy The taxonomy name.
	 * @param array  $terms    Array of slug => name pairs.
	 */
	private function create_terms( $taxonomy, $terms ) {
		$settings = get_option( 'mcp_settings', array() );
		$update_descriptions = isset( $settings['seed_terms_descriptions'] ) ? $settings['seed_terms_descriptions'] : true;
		$descriptions_only = isset( $settings['descriptions_update_only'] ) ? $settings['descriptions_update_only'] : false;

		foreach ( $terms as $slug => $name ) {
			$existing_term = get_term_by( 'slug', $slug, $taxonomy );

			if ( $existing_term ) {
				// Term exists, update description if needed.
				$description = $this->get_term_description( $taxonomy, $slug );
				if ( $description && $existing_term->description !== $description ) {
					wp_update_term( $existing_term->term_id, $taxonomy, array(
						'description' => $description,
					) );
				}
			} elseif ( ! $descriptions_only ) {
				// Create new term with description.
				$args = array(
					'slug' => $slug,
				);

				$description = $this->get_term_description( $taxonomy, $slug );
				if ( $description ) {
					$args['description'] = $description;
				}

				wp_insert_term( $name, $taxonomy, $args );
			}
		}
	}

	/**
	 * Get term description.
	 *
	 * @param string $taxonomy The taxonomy name.
	 * @param string $slug     The term slug.
	 * @return string The term description.
	 */
	private function get_term_description( $taxonomy, $slug ) {
		$descriptions = array(
			'game_type' => array(
				'mmorpg'      => __( 'عالم ضخم، تقدم طويل، مهام وغارات، ونقابات', 'momarab-core' ),
				'mmo-arpg'    => __( 'قتال أكشن سريع مع لوت وفئات أونلاين واسعة', 'momarab-core' ),
				'mmofps'      => __( 'تصويب منظور أول بمواجهات جماعية وخوادم كبيرة', 'momarab-core' ),
				'moba'        => __( 'فرق على خريطة ثابتة، أبطال بقدرات، وتدمير الهدف الأساسي', 'momarab-core' ),
				'mmorts'      => __( 'إستراتيجية فورية جماعية، بناء قواعد وحروب واسعة', 'momarab-core' ),
				'survival-mmo' => __( 'نجاة جماعية، جمع موارد وصناعة وبقاء مفتوح', 'momarab-core' ),
				'sandbox-mmo' => __( 'حرية عالية، اقتصاد وبناء، محتوى يصنعه اللاعب', 'momarab-core' ),
				'social-mmo'  => __( 'تفاعل اجتماعي، فعاليات، تخصيص شخصيات ومساحات لقاء', 'momarab-core' ),
				'battle-royale' => __( 'سقوط جماعي، دائرة تضيق، آخر من يبقى يفوز', 'momarab-core' ),
				'racing-mmo'  => __( 'سباقات مستمرة، تقدم سيارات وأطوار متعددة', 'momarab-core' ),
				'sports-mmo'  => __( 'بطولات رياضية جماعية موسمية واقتصاد لاعبين', 'momarab-core' ),
				'space-mmo'   => __( 'مجرة مفتوحة، قتال فضائي، تجارة، واستكشاف', 'momarab-core' ),
				'naval-mmo'   => __( 'معارك بحرية، ترقيات سفن، وتكتيكات أساطيل', 'momarab-core' ),
				'anime-mmo'   => __( 'أسلوب بصري وشخصيات وأنظمة بطابع الأنمي', 'momarab-core' ),
			),
			'game_status' => array(
				'upcoming'     => __( 'أُعلن عنها ولم تصدر بعد', 'momarab-core' ),
				'alpha'        => __( 'نسخة مبكرة جدًا للاختبار المحدود', 'momarab-core' ),
				'beta'         => __( 'اختبار أوسع بميزات شبه مكتملة', 'momarab-core' ),
				'early-access' => __( 'متاحة أثناء التطوير للتجربة المدفوعة', 'momarab-core' ),
				'released'     => __( 'إصدار كامل متاح رسميًا', 'momarab-core' ),
			),
			'game_mode' => array(
				'pve'        => __( 'محتوى ضد البيئة مثل مهام، دنجنز، ورؤساء', 'momarab-core' ),
				'pvp'        => __( 'قتال لاعب ضد لاعب بأنماط مرتبة أو مفتوحة', 'momarab-core' ),
				'pvpve'      => __( 'مزيج قتال لاعبين مع تهديدات بيئية مشتركة', 'momarab-core' ),
				'open-world' => __( 'خريطة واسعة متصلة واستكشاف حر', 'momarab-core' ),
				'co-op'      => __( 'تقدم ومهام تُنجز ضمن فريق', 'momarab-core' ),
			),
			'game_platform' => array(
				'pc'              => __( 'أنظمة ويندوز/لينكس/ماك', 'momarab-core' ),
				'playstation'     => __( 'أجهزة بلايستيشن', 'momarab-core' ),
				'xbox'            => __( 'أجهزة إكس بوكس', 'momarab-core' ),
				'nintendo-switch' => __( 'نسخة سويتش محسّنة للمحمول', 'momarab-core' ),
				'mobile'          => __( 'هواتف وأجهزة لوحية iOS/Android', 'momarab-core' ),
				'browser'         => __( 'يعمل عبر المتصفح بتقنيات WebGL/HTML5 دون تثبيت', 'momarab-core' ),
			),
		);

		if ( isset( $descriptions[ $taxonomy ][ $slug ] ) ) {
			return $descriptions[ $taxonomy ][ $slug ];
		}

		return '';
	}
}
