<?php
/**
 * Uninstall script for MOMARAB CORE plugin.
 * 
 * This file is executed when the plugin is deleted from WordPress admin.
 * It cleans up plugin-specific options and transients only.
 * 
 * @package Momarab_Core
 */

// If uninstall not called from WordPress, then exit.
if ( ! defined( 'WP_UNINSTALL_PLUGIN' ) ) {
	exit;
}

/**
 * Clean up plugin data on uninstall.
 * 
 * According to README specifications:
 * - Only deletes mcp_settings and mcp_* transients
 * - Does NOT delete CPT data, taxonomies, or user content
 * - Preserves all game data and user-created content
 */

// Delete plugin settings.
delete_option( 'mcp_settings' );

// Delete all plugin transients.
global $wpdb;

// Get all mcp_* transients.
$transients = $wpdb->get_results(
	"SELECT option_name FROM {$wpdb->options} 
	 WHERE option_name LIKE '_transient_mcp_%' 
	 OR option_name LIKE '_transient_timeout_mcp_%'"
);

// Delete each transient.
foreach ( $transients as $transient ) {
	$key = str_replace( array( '_transient_', '_transient_timeout_' ), '', $transient->option_name );
	delete_transient( $key );
}

// Clear any remaining cache.
if ( function_exists( 'wp_cache_flush' ) ) {
	wp_cache_flush();
}

/**
 * Note: We deliberately DO NOT delete:
 * 
 * 1. Games CPT data - User content should be preserved
 * 2. Taxonomy terms - May be referenced by other content  
 * 3. Meta fields - Part of user's game data
 * 4. Custom image sizes - WordPress handles these
 * 5. User capabilities - WordPress default capabilities used
 * 
 * This ensures that if the plugin is reinstalled, all user data remains intact.
 * Users can manually delete games and terms if they want complete removal.
 */
