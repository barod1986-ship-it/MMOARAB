import { defineConfig } from 'wxt';

export default defineConfig({
  modules: ['@wxt-dev/module-react'],
  srcDir: 'src',
  manifestVersion: 3,
  manifest: {
    name: '__MSG_appName__',
    description: '__MSG_appDescription__',
    version: '0.10.0',
    default_locale: 'en',
    minimum_chrome_version: '148',
    permissions: ['activeTab', 'scripting', 'storage', 'sidePanel', 'alarms'],
    optional_host_permissions: ['https://*/*', 'http://127.0.0.1/*'],
    action: {
      default_title: '__MSG_actionTitle__'
    },
    side_panel: {
      default_path: 'sidepanel.html'
    },
    options_ui: {
      page: 'options.html',
      open_in_tab: true
    },
    commands: {
      _execute_action: {
        suggested_key: { default: 'Alt+Shift+M' },
        description: '__MSG_commandDescription__'
      }
    },
    // Chrome 148+ opt-in. Keep this as a spread so builds remain compatible even if
    // WXT's upstream ManifestV3 typings lag the newly-added Chrome manifest key.
    ...({ message_serialization: 'structured_clone' } as const)
  }
});
