import { spawnSync } from 'node:child_process';
import { resolve } from 'node:path';

const script = resolve('scripts/verify_controlled_release_ready.py');
const result = spawnSync(process.env.PYTHON || 'python', [script, ...process.argv.slice(2)], {
  cwd: resolve('.'),
  encoding: 'utf8',
  stdio: ['inherit', 'pipe', 'pipe'],
});
if (result.stdout) process.stdout.write(result.stdout);
if (result.stderr) process.stderr.write(result.stderr);
if (result.error) {
  console.error(`controlled release verifier could not start Python: ${result.error.message}`);
  process.exit(2);
}
process.exit(result.status ?? 2);
