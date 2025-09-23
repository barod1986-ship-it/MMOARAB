<?php
/**
 * Main initialization class for MOMARAB CORE plugin.
 *
 * @package Momarab_Core
 */

namespace Momarab_Core;

// Prevent direct access.
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

/**
 * Main plugin initialization class.
 */
class MCP_Init {

	/**
	 * Single instance of the class.
	 *
	 * @var MCP_Init
	 */
	private static $instance = null;

	/**
	 * Get single instance.
	 *
	 * @return MCP_Init
	 */
	public static function get_instance() {
		if ( null === self::$instance ) {
			self::$instance = new self();
		}
		return self::$instance;
	}

	/**
	 * Constructor.
	 */
	private function __construct() {
		$this->init_hooks();
	}

	/**
	 * Initialize hooks.
	 */
	private function init_hooks() {
		add_action( 'init', array( $this, 'init' ) );
		add_action( 'wp_enqueue_scripts', array( $this, 'enqueue_frontend_assets' ) );
		add_action( 'admin_enqueue_scripts', array( $this, 'enqueue_admin_assets' ) );
		add_action( 'rest_api_init', array( $this, 'init_rest_api' ) );
		add_action( 'widgets_init', array( $this, 'register_widgets' ) );
		add_action( 'admin_menu', array( $this, 'admin_menu' ) );
		add_action( 'admin_init', array( $this, 'admin_init' ) );
	}

	/**
	 * Initialize plugin components.
	 */
	public function init() {
		// Initialize core components.
		new MCP_CPT();
		new MCP_Taxonomies();
		new MCP_Meta_Registry();
		new MCP_Meta_Save();
		new MCP_Permalinks();
		new MCP_Templates();
		new MCP_Terms_Manager();

		// Initialize features.
		new MCP_Ajax_Filter();
		new MCP_Shortcode_Games();
		new MCP_Shortcode_Game_Filter();
		new MCP_Related_Meta();
		new MCP_Related_Render();

		// Initialize security and performance.
		new MCP_Cache();
		new MCP_Images();
	}

	/**
	 * Enqueue frontend assets.
	 */
	public function enqueue_frontend_assets() {
		$assets = new MCP_Assets();
		$assets->enqueue_frontend();
	}

	/**
	 * Enqueue admin assets.
	 */
	public function enqueue_admin_assets() {
		$assets = new MCP_Assets();
		$assets->enqueue_admin();
	}

	/**
	 * Initialize REST API.
	 */
	public function init_rest_api() {
		new MCP_REST_Controller();
		new MCP_REST_Games();
		new MCP_REST_Taxonomies();
	}

	/**
	 * Register widgets.
	 */
	public function register_widgets() {
		register_widget( 'Momarab_Core\MCP_Widget_Popular' );
		register_widget( 'Momarab_Core\MCP_Widget_Recent' );
	}

	/**
	 * Add admin menu.
	 */
	public function admin_menu() {
		$settings = new MCP_Settings();
		$settings->add_menu();
	}

	/**
	 * Initialize admin settings.
	 */
	public function admin_init() {
		$settings = new MCP_Settings();
		$settings->init();
	}

	/**
	 * Plugin activation hook.
	 */
	public static function activate() {
		// Flush rewrite rules on activation.
		flush_rewrite_rules();

		// Create default settings.
		$default_settings = array(
			'related_news_enabled' => true,
			'related_news_title'   => __( 'آخر خبر عن اللعبة', 'momarab-core' ),
		);

		if ( ! get_option( 'mcp_settings' ) ) {
			update_option( 'mcp_settings', $default_settings );
		}
	}

	/**
	 * Plugin deactivation hook.
	 */
	public static function deactivate() {
		// Flush rewrite rules on deactivation.
		flush_rewrite_rules();
	}
}
