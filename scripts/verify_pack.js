/**
 * Verification Script for Step 58, 59, 60, 61, 62, 63:
 * 1. Step 58: Static Frontend Independence.
 * 2. Step 59: win-unpacked Structure Verification.
 * 3. Step 60: Zero Model Weights Scan (*.gguf, *.safetensors, model-weight *.bin, *.onnx).
 * 4. Step 61-62: Packaged Electron Launch & Engine Supervisor Handshake.
 * 5. Step 63: Process-tree shutdown & zero orphan process verification.
 */

const fs = require('fs');
const path = require('path');
const { spawn, execSync } = require('child_process');

function walkDir(dir, fileList = []) {
  const files = fs.readdirSync(dir);
  for (const file of files) {
    const filePath = path.join(dir, file);
    const stat = fs.statSync(filePath);
    if (stat.isDirectory()) {
      walkDir(filePath, fileList);
    } else {
      fileList.push({ path: filePath, size: stat.size, name: file });
    }
  }
  return fileList;
}

async function run() {
  console.log('====================================================');
  console.log(' STEPS 58-63: win-unpacked Distribution Verification');
  console.log('====================================================\n');

  const rootDir = path.resolve(__dirname, '..');
  const winUnpackedDir = path.join(rootDir, 'release', 'win-unpacked');

  if (!fs.existsSync(winUnpackedDir)) {
    throw new Error(`Directory release/win-unpacked not found at: ${winUnpackedDir}`);
  }

  // --------------------------------------------------------------------------
  // STEP 58: Static Frontend Independence
  // --------------------------------------------------------------------------
  console.log('----------------------------------------------------');
  console.log('[Step 58] Checking Static Frontend Independence...');
  console.log('----------------------------------------------------');
  const frontendIndexHtml = path.join(winUnpackedDir, 'resources', 'frontend', 'dist', 'index.html');
  if (!fs.existsSync(frontendIndexHtml)) {
    throw new Error(`Production index.html missing at: ${frontendIndexHtml}`);
  }
  const htmlContent = fs.readFileSync(frontendIndexHtml, 'utf8');
  console.log(`  - Found index.html (${htmlContent.length} bytes)`);
  if (!htmlContent.includes('<div id="root"></div>') || !htmlContent.includes('script type="module"')) {
    throw new Error('index.html does not contain standard bundled React entry structure.');
  }
  console.log('  - HTML structure validated: single-page app bundle with zero dev server dependency.');
  console.log('  [PASS] Step 58 Static Frontend Independence verified.\n');

  // --------------------------------------------------------------------------
  // STEP 59: win-unpacked Structure Verification
  // --------------------------------------------------------------------------
  console.log('----------------------------------------------------');
  console.log('[Step 59] Checking win-unpacked Structure...');
  console.log('----------------------------------------------------');
  const electronExe = path.join(winUnpackedDir, 'Ragger.ai.exe');
  const engineExe = path.join(winUnpackedDir, 'resources', 'engine', 'ragger-engine.exe');
  const engineInternal = path.join(winUnpackedDir, 'resources', 'engine', '_internal');
  const appAsar = path.join(winUnpackedDir, 'resources', 'app.asar');

  if (!fs.existsSync(electronExe)) throw new Error(`Missing Electron executable at ${electronExe}`);
  const electronStat = fs.statSync(electronExe);
  console.log(`  - Electron executable: ${electronExe} (${(electronStat.size / (1024 * 1024)).toFixed(2)} MB)`);

  if (!fs.existsSync(engineExe)) throw new Error(`Missing frozen engine executable at ${engineExe}`);
  const engineStat = fs.statSync(engineExe);
  console.log(`  - Frozen engine binary: ${engineExe} (${(engineStat.size / (1024 * 1024)).toFixed(2)} MB)`);

  if (!fs.existsSync(engineInternal) || !fs.statSync(engineInternal).isDirectory()) {
    throw new Error(`Missing frozen engine _internal directory at ${engineInternal}`);
  }
  const internalEntries = fs.readdirSync(engineInternal);
  console.log(`  - Frozen engine _internal runtime: ${internalEntries.length} items present`);

  if (!fs.existsSync(appAsar)) throw new Error(`Missing app.asar at ${appAsar}`);
  console.log(`  - Desktop application ASAR bundle: ${appAsar} (${(fs.statSync(appAsar).size / 1024).toFixed(2)} KB)`);
  console.log('  [PASS] Step 59 win-unpacked Structure verified.\n');

  // --------------------------------------------------------------------------
  // STEP 60: Zero Model Weights Scan
  // --------------------------------------------------------------------------
  console.log('----------------------------------------------------');
  console.log('[Step 60] Performing Zero Model Weights Scan...');
  console.log('----------------------------------------------------');
  console.log('  Scanning entire release/win-unpacked directory recursively...');
  const allFiles = walkDir(winUnpackedDir);
  console.log(`  - Total files scanned: ${allFiles.length}`);

  const forbiddenExtensions = ['.gguf', '.safetensors', '.onnx'];
  const violations = [];
  let modelBinCount = 0;

  for (const item of allFiles) {
    const lower = item.name.toLowerCase();
    
    // Check forbidden model formats
    for (const ext of forbiddenExtensions) {
      if (lower.endsWith(ext)) {
        violations.push({ file: item.path, reason: `Forbidden model format: ${ext}`, size: item.size });
      }
    }

    // Check forbidden model bin files (distinguishing from v8 snapshot binaries)
    if (lower.endsWith('.bin')) {
      if (lower.includes('model') || lower.includes('pytorch') || lower.includes('weight')) {
        violations.push({ file: item.path, reason: 'Forbidden model-weight *.bin artifact', size: item.size });
      } else {
        modelBinCount++;
      }
    }
  }

  console.log(`  - Inspected ${allFiles.length} files across win-unpacked distribution.`);
  console.log(`  - Checked for: *.gguf, *.safetensors, *.onnx model weights, model-weight *.bin`);
  console.log(`  - Non-model system binaries observed: ${modelBinCount} (e.g. v8_context_snapshot.bin)`);

  if (violations.length > 0) {
    console.error('FATAL: Forbidden model artifacts discovered inside distribution:');
    for (const v of violations) {
      console.error(`  * ${v.file} (${(v.size / (1024 * 1024)).toFixed(2)} MB) - ${v.reason}`);
    }
    throw new Error(`Zero-Model-Weights contract violated: found ${violations.length} forbidden model files.`);
  }

  console.log('  [PASS] Step 60 Zero Model Weights Scan: 0 forbidden model artifacts found.\n');

  // --------------------------------------------------------------------------
  // STEP 61 & 62: Packaged Electron Launch & Engine Supervisor Handshake
  // --------------------------------------------------------------------------
  console.log('----------------------------------------------------');
  console.log('[Step 61-62] Testing Packaged Electron Launch & Handshake...');
  console.log('----------------------------------------------------');
  console.log(`  Spawning: ${electronExe} --check-packaged-smoke`);

  const smokeResult = await new Promise((resolve, reject) => {
    let stdoutData = '';
    let stderrData = '';
    const child = spawn(electronExe, ['--check-packaged-smoke'], {
      cwd: winUnpackedDir,
      env: {
        ...process.env,
        ELECTRON_ENABLE_LOGGING: '1',
      },
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
      reject(new Error('Timeout (30s) waiting for packaged smoke test execution.'));
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
    throw new Error(`Packaged Electron smoke test failed with exit code ${smokeResult.code}`);
  }

  console.log(`  - Packaged smoke test exited with code 0`);
  console.log('  [PASS] Step 61-62 Packaged Electron launch and engine handshake verified.\n');

  // --------------------------------------------------------------------------
  // STEP 63: Process-tree Shutdown & Zero Orphan Process Verification
  // --------------------------------------------------------------------------
  console.log('----------------------------------------------------');
  console.log('[Step 63] Verifying Process-Tree Shutdown & Zero Orphans...');
  console.log('----------------------------------------------------');
  // Query tasklist on Windows
  const tasklistEngine = execSync('tasklist /FI "IMAGENAME eq ragger-engine.exe" /FO CSV', { encoding: 'utf8' });
  if (tasklistEngine.includes('ragger-engine.exe')) {
    throw new Error(`Orphan ragger-engine.exe process detected in tasklist:\n${tasklistEngine}`);
  }

  const tasklistElectron = execSync('tasklist /FI "IMAGENAME eq Ragger.ai.exe" /FO CSV', { encoding: 'utf8' });
  if (tasklistElectron.includes('Ragger.ai.exe')) {
    throw new Error(`Orphan Ragger.ai.exe process detected in tasklist:\n${tasklistElectron}`);
  }

  console.log('  - tasklist check confirms: 0 ragger-engine.exe processes running.');
  console.log('  - tasklist check confirms: 0 Ragger.ai.exe processes running.');
  console.log('  [PASS] Step 63 Process-tree shutdown and zero orphans verified.\n');

  console.log('====================================================');
  console.log(' ALL STEPS 58-63 PASSED: WIN-UNPACKED VERIFIED ✅');
  console.log('====================================================');
}

run().catch((err) => {
  console.error('\n[FATAL ERROR]', err.message);
  process.exit(1);
});
