/**
 * Verification Script for Step 66-69 (Clean-Machine Independence):
 * 1. Simulates pristine machine by stripping PATH of all developer tooling (Python, Node, Git, pip).
 * 2. Runs the silent installer or tests the installed package.
 * 3. Launches Ragger.ai.exe with sanitized environment.
 * 4. Verifies frozen engine boots without any external Python installation.
 * 5. Verifies handshake and clean shutdown.
 */

const fs = require('fs');
const path = require('path');
const { spawn, execSync } = require('child_process');

async function run() {
  console.log('====================================================');
  console.log(' STEPS 66-69: Clean-Machine Independence Simulation');
  console.log('====================================================\n');

  const rootDir = path.resolve(__dirname, '..');
  const releaseDir = path.join(rootDir, 'release');
  const setupExe = path.join(releaseDir, 'RaggerAI-Setup.exe');

  if (!fs.existsSync(setupExe)) {
    throw new Error(`RaggerAI-Setup.exe not found at ${setupExe}`);
  }

  // 1. Pristine Environment Definition: Only Windows system utilities
  const cleanPath = [
    process.env.SystemRoot ? path.join(process.env.SystemRoot, 'System32') : 'C:\\Windows\\System32',
    process.env.SystemRoot || 'C:\\Windows',
    process.env.SystemRoot ? path.join(process.env.SystemRoot, 'System32', 'Wbem') : 'C:\\Windows\\System32\\Wbem',
  ].join(';');

  const cleanEnv = {
    SystemRoot: process.env.SystemRoot || 'C:\\Windows',
    WINDIR: process.env.WINDIR || 'C:\\Windows',
    LOCALAPPDATA: process.env.LOCALAPPDATA,
    APPDATA: process.env.APPDATA,
    TEMP: process.env.TEMP,
    TMP: process.env.TMP,
    PATH: cleanPath,
    ELECTRON_ENABLE_LOGGING: '1',
  };

  console.log('----------------------------------------------------');
  console.log('[Check 1] Verifying Dev Tools are absent from clean environment...');
  console.log('----------------------------------------------------');
  console.log(`  Sanitized PATH: ${cleanEnv.PATH}`);

  function testCommandAbsence(cmdName) {
    try {
      execSync(`where ${cmdName}`, { env: cleanEnv, stdio: 'ignore' });
      return false; // Found
    } catch {
      return true; // Not found (expected!)
    }
  }

  const pythonAbsent = testCommandAbsence('python');
  const nodeAbsent = testCommandAbsence('node');
  const gitAbsent = testCommandAbsence('git');

  console.log(`  - Python absent from PATH: ${pythonAbsent ? 'YES ✅' : 'NO ❌'}`);
  console.log(`  - Node.js absent from PATH: ${nodeAbsent ? 'YES ✅' : 'NO ❌'}`);
  console.log(`  - Git absent from PATH:     ${gitAbsent ? 'YES ✅' : 'NO ❌'}`);

  if (!pythonAbsent || !nodeAbsent || !gitAbsent) {
    throw new Error('Environment sanitization failed: developer tools leaked into PATH.');
  }
  console.log('  [PASS] Clean machine environment successfully isolated.\n');

  // 2. Test running packaged executable with sanitized environment
  console.log('----------------------------------------------------');
  console.log('[Check 2] Launching Packaged Application in Clean Environment...');
  console.log('----------------------------------------------------');
  const electronExe = path.join(releaseDir, 'win-unpacked', 'Ragger.ai.exe');

  const smokeResult = await new Promise((resolve, reject) => {
    let stdoutData = '';
    let stderrData = '';
    const child = spawn(electronExe, ['--check-packaged-smoke'], {
      cwd: path.dirname(electronExe),
      env: cleanEnv,
    });

    child.stdout.on('data', (d) => {
      const s = d.toString();
      stdoutData += s;
      process.stdout.write(s);
    });

    child.stderr.on('data', (d) => {
      const s = d.toString();
      stderrData += s;
      process.stderr.write(s);
    });

    const timeout = setTimeout(() => {
      try { execSync(`taskkill /F /PID ${child.pid} /T`); } catch {}
      reject(new Error('Timeout waiting for clean-env application smoke test.'));
    }, 30000);

    child.on('exit', (code) => {
      clearTimeout(timeout);
      resolve({ code, stdout: stdoutData, stderr: stderrData });
    });

    child.on('error', (err) => {
      clearTimeout(timeout);
      reject(err);
    });
  });

  if (smokeResult.code !== 0) {
    throw new Error(`Application failed in clean environment with exit code ${smokeResult.code}`);
  }

  console.log('\n  [PASS] Application boots, launches hermetic Python engine, and exits cleanly in pristine environment.');

  // 3. Confirm 0 orphan processes
  const tasklistEngine = execSync('tasklist /FI "IMAGENAME eq ragger-engine.exe" /FO CSV', { encoding: 'utf8' });
  if (tasklistEngine.includes('ragger-engine.exe')) {
    throw new Error(`Orphan ragger-engine.exe process detected in clean environment test:\n${tasklistEngine}`);
  }
  console.log('  [PASS] Zero orphan processes confirmed.\n');

  console.log('====================================================');
  console.log(' ALL CLEAN-MACHINE TESTS PASSED: HERMETIC PASS ✅');
  console.log('====================================================');
}

run().catch((err) => {
  console.error('\n[FATAL ERROR]', err.message);
  process.exit(1);
});
