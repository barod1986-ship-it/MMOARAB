import { readFile } from 'node:fs/promises';

const path = process.argv[2] ?? '.output/chrome-mv3/manifest.json';
const manifest = JSON.parse(await readFile(path, 'utf8'));
const errors = [];

if (manifest.manifest_version !== 3) errors.push('manifest_version must be 3');
if (Number(manifest.minimum_chrome_version) < 148) errors.push('minimum_chrome_version must be >= 148');
if (manifest.content_scripts?.length) errors.push('Phase 1 must not register static content_scripts');
if (manifest.host_permissions?.length) errors.push('Phase 1 must not request required host_permissions');
for (const permission of ['activeTab', 'scripting', 'storage', 'sidePanel', 'alarms']) {
  if (!manifest.permissions?.includes(permission)) errors.push(`missing permission: ${permission}`);
}
const optional = new Set(manifest.optional_host_permissions ?? []);
if (!optional.has('https://*/*')) errors.push('missing optional https host permission declaration');
if (!optional.has('http://127.0.0.1/*')) errors.push('missing loopback optional host permission declaration');
if (manifest.message_serialization !== 'structured_clone') errors.push('message_serialization must be structured_clone');
if (!manifest.side_panel?.default_path) errors.push('side_panel.default_path is required');

if (errors.length) {
  console.error(errors.map((error) => `- ${error}`).join('\n'));
  process.exitCode = 1;
} else {
  console.log(`Manifest contract OK: ${path}`);
}
