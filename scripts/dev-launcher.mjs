#!/usr/bin/env node
/**
 * Ragger.ai — Single-Command Development Launcher.
 *
 * Orchestration Workflow:
 * 1. Checks environment and validates project structure relative to repo root.
 * 2. Compiles desktop TypeScript if needed.
 * 3. Starts Vite development server (port 5173).
 * 4. Polls Vite TCP port until listening and ready.
 * 5. Launches Electron desktop host.
 *    - Electron supervisor starts & manages the Python FastAPI engine on an ephemeral loopback port.
 *    - Supervisor writes storage/dev_session.json with host, dynamic port, and bearer token.
 *    - Electron window loads http://localhost:5173 (which proxies API requests to the supervised engine).
 * 6. Captures and prefixes stdout/stderr: [FRONTEND], [ELECTRON], [LAUNCHER].
 * 7. Gracefully tears down all child processes on SIGINT/SIGTERM/exit, preventing orphan processes.
 */

import { spawn, execSync, execFileSync } from 'child_process';
import path from 'path';
import net from 'net';
import fs from 'fs';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, '..');

const VITE_PORT = 5173;
const VITE_HOST = '127.0.0.1';
const STARTUP_TIMEOUT_MS = 30000;

// Track active child processes for clean termination
const activeChildren = new Set();
let isShuttingDown = false;

function log(prefix, message) {
  const lines = String(message).split(/\r?\n/);
  for (const line of lines) {
    if (line.trim().length > 0) {
      console.log(`[${prefix}] ${line}`);
    }
  }
}

function errorLog(prefix, message) {
  const lines = String(message).split(/\r?\n/);
  for (const line of lines) {
    if (line.trim().length > 0) {
      console.error(`[${prefix}] ${line}`);
    }
  }
}

/**
 * Checks if a TCP port is open and accepting connections.
 */
function checkPortOpen(port, host = '127.0.0.1', timeoutMs = 1000) {
  return new Promise((resolve) => {
    const socket = new net.Socket();
    let status = false;

    socket.setTimeout(timeoutMs);
    socket.once('connect', () => {
      status = true;
      socket.destroy();
      resolve(true);
    });

    socket.once('timeout', () => {
      socket.destroy();
      resolve(false);
    });

    socket.once('error', () => {
      socket.destroy();
      resolve(false);
    });

    socket.connect(port, host);
  });
}

/**
 * Waits until a TCP port is listening.
 */
async function waitForPort(port, host = '127.0.0.1', timeoutMs = STARTUP_TIMEOUT_MS) {
  const start = Date.now();
  const hosts = [host, 'localhost', '::1'];
  while (Date.now() - start < timeoutMs) {
    for (const h of hosts) {
      const open = await checkPortOpen(port, h, 300);
      if (open) return true;
    }
    await new Promise((r) => setTimeout(r, 400));
  }
  return false;
}

/**
 * Kills a process and all its children safely across platforms.
 */
function terminateProcess(child) {
  if (!child || !child.pid) return;

  try {
    if (process.platform === 'win32') {
      execSync(`taskkill /pid ${child.pid} /T /F`, { stdio: 'ignore' });
    } else {
      child.kill('SIGTERM');
      setTimeout(() => {
        try {
          if (!child.killed) child.kill('SIGKILL');
        } catch {}
      }, 2000);
    }
  } catch {}
}

/**
 * Clean shutdown handler for all spawned child processes.
 */
function shutdown(exitCode = 0) {
  if (isShuttingDown) return;
  isShuttingDown = true;

  log('LAUNCHER', 'Shutting down Ragger.ai development processes...');

  for (const child of activeChildren) {
    terminateProcess(child);
  }
  activeChildren.clear();

  log('LAUNCHER', 'Clean shutdown complete.');
  process.exit(exitCode);
}

// Handle signals and exit events
process.on('SIGINT', () => shutdown(0));
process.on('SIGTERM', () => shutdown(0));
process.on('exit', () => shutdown(0));

/**
 * Ensures apps/desktop is built so Electron can run dist/main/index.js.
 */
function ensureDesktopBuild() {
  log('LAUNCHER', 'Building desktop TypeScript...');
  try {
    execSync('npm run build --workspace=@ragger/desktop', {
      cwd: REPO_ROOT,
      stdio: 'inherit',
      shell: true,
    });
    log('LAUNCHER', 'Desktop build completed.');
  } catch (err) {
    errorLog('LAUNCHER', `Desktop build failed: ${err.message}`);
    throw err;
  }
}

/**
 * Ensures electron binary resolution in apps/desktop workspace.
 */
function ensureElectronBinary() {
  const rootElectronDist = path.join(REPO_ROOT, 'node_modules', 'electron', 'dist');
  const desktopElectron = path.join(REPO_ROOT, 'apps', 'desktop', 'node_modules', 'electron');
  const desktopElectronDist = path.join(desktopElectron, 'dist');
  const desktopElectronPathTxt = path.join(desktopElectron, 'path.txt');

  if (fs.existsSync(desktopElectron) && !fs.existsSync(desktopElectronPathTxt)) {
    const rootPathTxt = path.join(REPO_ROOT, 'node_modules', 'electron', 'path.txt');
    if (fs.existsSync(rootPathTxt)) {
      try {
        fs.copyFileSync(rootPathTxt, desktopElectronPathTxt);
      } catch {}
    }
  }

  if (fs.existsSync(rootElectronDist) && fs.existsSync(desktopElectron) && !fs.existsSync(desktopElectronDist)) {
    try {
      fs.cpSync(rootElectronDist, desktopElectronDist, { recursive: true });
    } catch {}
  }
}

/**
 * Main launcher entry point.
 */
async function main() {
  log('LAUNCHER', '==================================================');
  log('LAUNCHER', '       Ragger.ai Development Launcher             ');
  log('LAUNCHER', '==================================================');

  // Verify virtualenv exists for Python engine
  const venvPythonWin = path.join(REPO_ROOT, 'engine', '.venv', 'Scripts', 'python.exe');
  const venvPythonUnix = path.join(REPO_ROOT, 'engine', '.venv', 'bin', 'python');
  const venvFound = (process.platform === 'win32' && fs.existsSync(venvPythonWin)) || fs.existsSync(venvPythonUnix);

  if (!venvFound) {
    log('LAUNCHER', 'Notice: Virtual environment in engine/.venv not found; supervisor will fallback to system python.');
  } else {
    log('LAUNCHER', 'Found engine virtual environment.');
  }

  // Ensure desktop build and electron files are ready
  ensureElectronBinary();
  ensureDesktopBuild();

  // 1. Start Vite development server
  log('LAUNCHER', 'Starting Vite frontend server on port 5173...');
  const isWin = process.platform === 'win32';
  const spawnBin = isWin ? 'cmd.exe' : 'npm';
  const frontendArgs = isWin
    ? ['/d', '/s', '/c', 'npm run dev --workspace=@ragger/frontend']
    : ['run', 'dev', '--workspace=@ragger/frontend'];

  const frontendProcess = spawn(spawnBin, frontendArgs, {
    cwd: REPO_ROOT,
    env: { ...process.env },
    stdio: ['ignore', 'pipe', 'pipe'],
    shell: false,
  });

  activeChildren.add(frontendProcess);

  frontendProcess.stdout.on('data', (data) => log('FRONTEND', data));
  frontendProcess.stderr.on('data', (data) => errorLog('FRONTEND', data));

  frontendProcess.on('exit', (code) => {
    if (!isShuttingDown) {
      errorLog('LAUNCHER', `Frontend server exited unexpectedly with code ${code}.`);
      shutdown(code || 1);
    }
  });

  // 2. Wait for Vite server readiness
  log('LAUNCHER', `Waiting for frontend on ${VITE_HOST}:${VITE_PORT}...`);
  const frontendReady = await waitForPort(VITE_PORT, VITE_HOST, STARTUP_TIMEOUT_MS);

  if (!frontendReady) {
    errorLog('LAUNCHER', `Timeout: Frontend failed to listen on port ${VITE_PORT} within ${STARTUP_TIMEOUT_MS / 1000}s.`);
    shutdown(1);
    return;
  }

  log('LAUNCHER', 'Frontend is ready. Launching Electron desktop host...');
  log('LAUNCHER', '(Electron supervisor will automatically start and authenticate Python engine)');

  // 3. Launch Electron Desktop host
  const electronArgs = isWin
    ? ['/d', '/s', '/c', 'npm run start --workspace=@ragger/desktop']
    : ['run', 'start', '--workspace=@ragger/desktop'];

  const electronProcess = spawn(spawnBin, electronArgs, {
    cwd: REPO_ROOT,
    env: {
      ...process.env,
      NODE_ENV: 'development',
      VITE_DEV_SERVER_URL: `http://${VITE_HOST}:${VITE_PORT}`,
    },
    stdio: ['ignore', 'pipe', 'pipe'],
    shell: false,
  });

  activeChildren.add(electronProcess);

  electronProcess.stdout.on('data', (data) => log('ELECTRON', data));
  electronProcess.stderr.on('data', (data) => errorLog('ELECTRON', data));

  electronProcess.on('exit', (code) => {
    log('LAUNCHER', `Electron application closed (exit code: ${code}).`);
    shutdown(code || 0);
  });
}

main().catch((err) => {
  errorLog('LAUNCHER', `Startup error: ${err.message}`);
  shutdown(1);
});
