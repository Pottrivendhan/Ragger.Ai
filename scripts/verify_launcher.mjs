/**
 * Tests for scripts/dev-launcher.mjs and npm scripts configuration.
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, '..');

function assert(condition, message) {
  if (!condition) {
    console.error(`❌ Assertion Failed: ${message}`);
    process.exit(1);
  }
}

console.log('=== [Launcher Test] Verifying Single-Command Launcher Configuration ===');

// 1. Verify launcher script exists
const launcherPath = path.join(REPO_ROOT, 'scripts', 'dev-launcher.mjs');
assert(fs.existsSync(launcherPath), 'scripts/dev-launcher.mjs must exist.');
console.log('✓ scripts/dev-launcher.mjs exists.');

// 2. Verify package.json configuration
const pkgPath = path.join(REPO_ROOT, 'package.json');
const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'));
assert(pkg.scripts && pkg.scripts.dev === 'node scripts/dev-launcher.mjs', 'package.json "dev" script must run "node scripts/dev-launcher.mjs"');
console.log('✓ package.json "dev" script points to dev-launcher.mjs.');

// 3. Verify lower-level scripts preserved
assert(pkg.scripts['dev:frontend'], 'dev:frontend script must be preserved.');
assert(pkg.scripts['dev:desktop'], 'dev:desktop script must be preserved.');
assert(pkg.scripts['test:engine'], 'test:engine script must be preserved.');
assert(pkg.scripts['test:integration'], 'test:integration script must be preserved.');
console.log('✓ Lower-level scripts preserved.');

// 4. Verify no hardcoded paths in dev-launcher.mjs
const launcherContent = fs.readFileSync(launcherPath, 'utf8');
assert(!launcherContent.includes('POTTRIVENDHAN'), 'dev-launcher.mjs must not contain hardcoded user paths.');
assert(launcherContent.includes('REPO_ROOT'), 'dev-launcher.mjs must use repository-relative resolution.');
assert(launcherContent.includes('activeChildren'), 'dev-launcher.mjs must track child processes for clean termination.');
console.log('✓ dev-launcher.mjs uses repository-relative resolution and tracks child processes.');

// 5. Verify electron resolution logic
assert(launcherContent.includes('ensureElectronBinary'), 'dev-launcher.mjs must ensure electron binary resolution.');
assert(launcherContent.includes('ensureDesktopBuild'), 'dev-launcher.mjs must verify desktop build.');
console.log('✓ Launcher readiness and binary safeguards verified.');

console.log('\n✅ All Launcher Tests Passed Successfully.');
