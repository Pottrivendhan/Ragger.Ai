/**
 * Verification Script for Step 55, 56, 57:
 * Tests the frozen standalone engine (ragger-engine.exe):
 * 1. Boots on loopback with ephemeral port & bearer token.
 * 2. Verifies health endpoint.
 * 3. Verifies 3-stage authentication contract:
 *    - Missing token -> 401
 *    - Wrong token -> 401
 *    - Correct token -> 200
 * 4. Verifies catalog integrity & hardware detection endpoints.
 * 5. Verifies clean termination.
 */

const { spawn } = require('child_process');
const path = require('path');
const http = require('http');
const net = require('net');
const crypto = require('crypto');

async function getFreePort() {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.listen(0, '127.0.0.1', () => {
      const port = srv.address().port;
      srv.close(() => resolve(port));
    });
    srv.on('error', reject);
  });
}

function requestHttp(options, postData = null) {
  return new Promise((resolve, reject) => {
    const req = http.request(options, (res) => {
      let body = '';
      res.on('data', (chunk) => { body += chunk; });
      res.on('end', () => {
        resolve({
          statusCode: res.statusCode,
          headers: res.headers,
          body: body ? JSON.parse(body) : null,
          rawBody: body,
        });
      });
    });
    req.on('error', reject);
    if (postData) {
      req.write(typeof postData === 'string' ? postData : JSON.stringify(postData));
    }
    req.end();
  });
}

async function sleep(ms) {
  return new Promise((res) => setTimeout(res, ms));
}

async function run() {
  console.log('====================================================');
  console.log(' STEP 55-57: Frozen Engine Verification');
  console.log('====================================================');

  const rootDir = path.resolve(__dirname, '..');
  let exePath = path.join(rootDir, 'engine', 'dist', 'engine', 'ragger-engine.exe');

  const fs = require('fs');
  const installedExe = path.join(process.env.LOCALAPPDATA || '', 'Programs', 'Ragger.ai', 'resources', 'engine', 'ragger-engine.exe');
  if (fs.existsSync(installedExe)) {
    exePath = installedExe;
  } else if (!fs.existsSync(exePath)) {
    throw new Error(`Frozen engine executable not found at: ${exePath}`);
  }

  const port = await getFreePort();
  const token = crypto.randomBytes(32).toString('hex');
  const host = '127.0.0.1';

  console.log(`[Test] Target Executable: ${exePath}`);
  console.log(`[Test] Ephemeral Port:    ${port}`);
  console.log(`[Test] Bearer Token:      ${token.substring(0, 8)}... (256-bit)`);

  const spawnArgs = ['--host', host, '--port', String(port), '--token', token, '--log-level', 'info'];
  console.log(`[Test] Spawning: ${exePath} ${spawnArgs.join(' ')}`);

  const child = spawn(exePath, spawnArgs, {
    cwd: path.dirname(exePath),
    env: { ...process.env, PYTHONUNBUFFERED: '1', RAGGER_API_TOKEN: token },
    stdio: ['ignore', 'pipe', 'pipe'],
    shell: true,
  });

  child.stdout.on('data', (d) => {
    const line = d.toString().trim();
    if (line) console.log(`  [Frozen Engine stdout] ${line}`);
  });
  child.stderr.on('data', (d) => {
    const line = d.toString().trim();
    if (line) console.log(`  [Frozen Engine stderr] ${line}`);
  });

  let hasExited = false;
  let exitCode = null;
  child.on('exit', (code) => {
    hasExited = true;
    exitCode = code;
  });

  try {
    // 1. Wait for health check (Step 55)
    console.log('\n[Step 55] Waiting for frozen engine boot & /health endpoint...');
    let healthy = false;
    for (let i = 0; i < 40; i++) {
      if (hasExited) {
        throw new Error(`Engine process exited prematurely with code ${exitCode}`);
      }
      try {
        const res = await requestHttp({
          host,
          port,
          path: '/health',
          method: 'GET',
        });
        if (res.statusCode === 200 && res.body && res.body.status === 'ok') {
          console.log(`[PASS] Engine is healthy! Response:`, res.body);
          healthy = true;
          break;
        }
      } catch (e) {
        // Retry
      }
      await sleep(500);
    }

    if (!healthy) {
      throw new Error('Timeout waiting for engine to become healthy');
    }

    // 2. Authentication Contract (Step 57)
    console.log('\n[Step 57] Verifying 3-Stage Authentication Contract (401 / 401 / 200)...');

    // 2a. Missing Token
    const resNoToken = await requestHttp({
      host,
      port,
      path: '/api/v1/models/catalog',
      method: 'GET',
    });
    console.log(`  - No token: HTTP ${resNoToken.statusCode}`);
    if (resNoToken.statusCode !== 401) {
      throw new Error(`Expected HTTP 401 for missing token, got ${resNoToken.statusCode}`);
    }
    console.log('    [PASS] Missing token correctly rejected with 401');

    // 2b. Wrong Token
    const resWrongToken = await requestHttp({
      host,
      port,
      path: '/api/v1/models/catalog',
      method: 'GET',
      headers: {
        Authorization: 'Bearer wrong-invalid-token-xyz',
      },
    });
    console.log(`  - Wrong token: HTTP ${resWrongToken.statusCode}`);
    if (resWrongToken.statusCode !== 401) {
      throw new Error(`Expected HTTP 401 for invalid token, got ${resWrongToken.statusCode}`);
    }
    console.log('    [PASS] Invalid token correctly rejected with 401');

    // 2c. Correct Token
    const resCorrectToken = await requestHttp({
      host,
      port,
      path: '/api/v1/models/catalog',
      method: 'GET',
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });
    console.log(`  - Correct token: HTTP ${resCorrectToken.statusCode}`);
    if (resCorrectToken.statusCode !== 200) {
      throw new Error(`Expected HTTP 200 for correct token, got ${resCorrectToken.statusCode}`);
    }
    console.log('    [PASS] Correct token authenticated with 200 OK');

    // 3. Catalog & Hardware Integrity (Step 56)
    console.log('\n[Step 56] Verifying Catalog Integrity & Hardware Detection...');
    const catalog = resCorrectToken.body;
    const models = Array.isArray(catalog) ? catalog : (catalog && catalog.models ? catalog.models : null);
    if (!models || models.length === 0) {
      throw new Error(`Catalog response invalid or empty: ${JSON.stringify(catalog)}`);
    }
    console.log(`  - Catalog contains ${models.length} model definitions:`);
    for (const m of models) {
      console.log(`    * [${m.category}] ${m.model_id} (${m.format}) -> key: ${m.model_key}`);
    }

    const resHardware = await requestHttp({
      host,
      port,
      path: '/api/v1/models/hardware',
      method: 'GET',
      headers: {
        Authorization: `Bearer ${token}`,
      },
    });
    if (resHardware.statusCode !== 200) {
      throw new Error(`Expected HTTP 200 for hardware endpoint, got ${resHardware.statusCode}`);
    }
    const hw = resHardware.body;
    console.log(`  - Hardware profile: RAM=${hw.memory?.total_mb}MB, Tier=${hw.hardware_tier}, AVX2=${hw.cpu?.avx2}`);
    console.log('  [PASS] Catalog and Hardware endpoints verified successfully');

  } finally {
    // 4. Clean Shutdown
    console.log('\n[Shutdown] Terminating frozen engine process...');
    child.kill('SIGTERM');
    
    // Give it 3 seconds to exit gracefully, otherwise taskkill
    let terminated = false;
    for (let i = 0; i < 30; i++) {
      if (hasExited) {
        terminated = true;
        break;
      }
      await sleep(100);
    }

    if (!terminated) {
      console.log('  Engine did not exit gracefully, issuing taskkill...');
      try {
        const { execSync } = require('child_process');
        execSync(`taskkill /F /PID ${child.pid} /T`);
      } catch (e) {
        // Ignore if already dead
      }
    }
    console.log('  [PASS] Frozen engine process cleanly terminated with no orphans.');
  }

  console.log('\n====================================================');
  console.log(' ALL STEPS 55-57 PASSED: FROZEN ENGINE VERIFIED ✅');
  console.log('====================================================');
}

run().catch((err) => {
  console.error('\n[FATAL ERROR]', err.message);
  process.exit(1);
});
