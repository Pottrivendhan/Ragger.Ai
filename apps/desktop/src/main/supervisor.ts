/**
 * Python Engine Process Supervisor.
 * Manages the lifecycle, health polling, and graceful termination of the Python engine.
 */

import { ChildProcess, spawn, execSync } from 'child_process';
import net from 'net';
import path from 'path';
import fs from 'fs';
import { getOrCreateSessionToken } from './security';
import { SupervisorStatus, AuthenticatedHealthResponse, RuntimeDiagnosticsResponse } from '../shared/types';

function isPackagedApp(): boolean {
  try {
    const electron = require('electron');
    return Boolean(electron.app && electron.app.isPackaged);
  } catch {
    return false;
  }
}

export class PythonProcessSupervisor {
  private childProcess: ChildProcess | null = null;
  private enginePid: number | null = null;
  private port: number | null = null;
  private host: string = '127.0.0.1';
  private token: string | null = null;
  private isRunning: boolean = false;
  private isAuthenticated: boolean = false;
  private lastError: string | null = null;
  private lastHealthCheck: string | null = null;
  private onStateChangeCallback: ((status: SupervisorStatus) => void) | null = null;

  constructor() {}

  public onStateChange(callback: (status: SupervisorStatus) => void) {
    this.onStateChangeCallback = callback;
  }

  private notifyStateChange() {
    if (this.onStateChangeCallback) {
      this.onStateChangeCallback(this.getStatus());
    }
  }

  /**
   * Finds an available ephemeral TCP port bound strictly to loopback (127.0.0.1).
   */
  public async allocateEphemeralPort(): Promise<number> {
    return new Promise((resolve, reject) => {
      const server = net.createServer();
      server.unref();
      server.on('error', (err) => reject(err));
      server.listen(0, this.host, () => {
        const address = server.address();
        if (address && typeof address === 'object') {
          const port = address.port;
          server.close(() => resolve(port));
        } else {
          reject(new Error('Failed to resolve ephemeral port address.'));
        }
      });
    });
  }

  /**
   * Resolves the path to the Python executable.
   * In Development: uses the virtual environment python if present, or system python.
   * In Production: uses the bundled frozen engine executable.
   */
  private resolveEngineExecution(): { cmd: string; args: string[] } {
    if (isPackagedApp()) {
      const prodBinary = path.join(process.resourcesPath, 'engine', 'ragger-engine.exe');
      return { cmd: prodBinary, args: [] };
    }

    // Development path: locate virtual environment
    const rootDir = path.resolve(__dirname, '../../../../');
    const venvPythonWin = path.join(rootDir, 'engine', '.venv', 'Scripts', 'python.exe');
    const venvPythonUnix = path.join(rootDir, 'engine', '.venv', 'bin', 'python');

    let cmd = 'python';
    if (process.platform === 'win32' && fs.existsSync(venvPythonWin)) {
      cmd = venvPythonWin;
    } else if (fs.existsSync(venvPythonUnix)) {
      cmd = venvPythonUnix;
    }

    return {
      cmd,
      args: ['-m', 'ragger_engine.main'],
    };
  }

  /**
   * Starts the Python engine as a supervised child process.
   */
  public async start(): Promise<SupervisorStatus> {
    if (this.isRunning && this.childProcess) {
      return this.getStatus();
    }

    this.token = getOrCreateSessionToken();
    this.port = await this.allocateEphemeralPort();
    this.lastError = null;

    const rootDir = path.resolve(__dirname, '../../../../');
    if (!isPackagedApp()) {
      try {
        const storageDir = path.join(rootDir, 'storage');
        fs.mkdirSync(storageDir, { recursive: true });
        fs.writeFileSync(
          path.join(storageDir, 'dev_session.json'),
          JSON.stringify({ host: this.host, port: this.port, token: this.token, updated_at: new Date().toISOString() }, null, 2),
          'utf8'
        );
      } catch (e) {
        console.warn('[Supervisor] Could not write dev_session.json:', e);
      }
    }

    const { cmd, args } = this.resolveEngineExecution();
    const spawnArgs = [...args, '--host', this.host, '--port', String(this.port)];

    console.log(`[Supervisor] Spawning Python engine: ${cmd} on ${this.host}:${this.port} (Token: [REDACTED])`);

    const env = {
      ...process.env,
      PYTHONUNBUFFERED: '1',
      RAGGER_API_TOKEN: this.token,
    };

    const engineDir = path.join(rootDir, 'engine');

    try {
      const spawnCwd = isPackagedApp() ? path.dirname(cmd) : (fs.existsSync(engineDir) ? engineDir : undefined);
      this.childProcess = spawn(cmd, spawnArgs, {
        cwd: spawnCwd,
        env,
        stdio: ['ignore', 'pipe', 'pipe'],
      });
    } catch (err: any) {
      this.lastError = `Failed to spawn Python process: ${err.message}`;
      console.error(`[Supervisor] Spawn error:`, err);
      this.notifyStateChange();
      throw err;
    }

    const pid = this.childProcess.pid;
    console.log(`[Supervisor] Python process spawned with PID: ${pid}`);

    this.childProcess.stdout?.on('data', (data: Buffer) => {
      const msg = data.toString().trim();
      if (msg) {
        console.log(`[Engine stdout] ${msg}`);
      }
    });

    this.childProcess.stderr?.on('data', (data: Buffer) => {
      const msg = data.toString().trim();
      if (msg) {
        console.error(`[Engine stderr] ${msg}`);
      }
    });

    this.childProcess.on('exit', (code, signal) => {
      console.warn(`[Supervisor] Python engine process ${pid} exited with code ${code}, signal ${signal}`);
      this.isRunning = false;
      this.isAuthenticated = false;
      this.childProcess = null;
      this.lastError = `Engine exited unexpectedly with code ${code} (${signal || 'no signal'})`;
      this.notifyStateChange();
    });

    this.childProcess.on('error', (err) => {
      console.error(`[Supervisor] Process error on PID ${pid}:`, err);
      this.lastError = err.message;
      this.notifyStateChange();
    });

    // Wait for engine readiness via health check polling
    await this.waitForReadiness(15000);

    return this.getStatus();
  }

  /**
   * Polls http://127.0.0.1:<port>/health until it responds with 200,
   * then verifies authenticated /api/v1/health.
   */
  private async waitForReadiness(timeoutMs: number): Promise<void> {
    const startTime = Date.now();
    const probeUrl = `http://${this.host}:${this.port}/health`;
    const authUrl = `http://${this.host}:${this.port}/api/v1/health`;

    console.log(`[Supervisor] Polling for engine readiness at ${probeUrl}...`);

    while (Date.now() - startTime < timeoutMs) {
      if (!this.childProcess || this.childProcess.exitCode !== null) {
        throw new Error(this.lastError || 'Python process terminated prematurely during startup.');
      }

      try {
        const response = await fetch(probeUrl, { method: 'GET' });
        if (response.ok) {
          // Liveness probe succeeded. Now verify authenticated loopback.
          const authResponse = await fetch(authUrl, {
            method: 'GET',
            headers: {
              Authorization: `Bearer ${this.token}`,
            },
          });

          if (authResponse.ok) {
            const authData = (await authResponse.json()) as AuthenticatedHealthResponse;
            this.enginePid = authData.process_id;
            this.isRunning = true;
            this.isAuthenticated = true;
            this.lastError = null;
            this.lastHealthCheck = new Date().toISOString();
            console.log(`[Supervisor] Engine is healthy and authenticated on ${this.host}:${this.port} (Engine PID: ${this.enginePid})`);
            this.notifyStateChange();
            return;
          } else {
            console.warn(`[Supervisor] Liveness passed but auth failed with status: ${authResponse.status}`);
          }
        }
      } catch (err) {
        // Connection refused while server is initializing; continue waiting
      }

      await new Promise((res) => setTimeout(res, 250));
    }

    this.lastError = `Timeout waiting for Python engine to become ready after ${timeoutMs}ms.`;
    this.notifyStateChange();
    throw new Error(this.lastError);
  }

  /**
   * Makes an authenticated HTTP request to the Python engine on behalf of the renderer.
   * This ensures the renderer never has direct access to the secret token.
   */
  public async authenticatedRequest<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    if (!this.isRunning || !this.port) {
      throw new Error('Python engine is not running.');
    }

    const url = `http://${this.host}:${this.port}${endpoint}`;
    const headers = {
      ...(options.headers || {}),
      Authorization: `Bearer ${this.token}`,
      'Content-Type': 'application/json',
    };

    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const errorBody = await response.text();
      throw new Error(`Engine request failed (${response.status}): ${errorBody}`);
    }

    return (await response.json()) as T;
  }

  public async getHealth(): Promise<AuthenticatedHealthResponse> {
    return this.authenticatedRequest<AuthenticatedHealthResponse>('/api/v1/health');
  }

  public async getRuntime(): Promise<RuntimeDiagnosticsResponse> {
    return this.authenticatedRequest<RuntimeDiagnosticsResponse>('/api/v1/runtime');
  }

  /**
   * Returns current supervisor status telemetry.
   */
  public getStatus(): SupervisorStatus {
    return {
      is_running: this.isRunning,
      pid: this.enginePid || this.childProcess?.pid || null,
      port: this.port,
      host: this.host,
      authenticated: this.isAuthenticated,
      error: this.lastError,
      last_health_check: this.lastHealthCheck,
    };
  }

  /**
   * Provides loopback API base URL and session token for direct authenticated HTTP communication.
   */
  public getApiConfig(): { baseUrl: string | null; token: string | null; host: string; port: number | null } {
    return {
      baseUrl: this.port ? `http://${this.host}:${this.port}` : null,
      token: this.token,
      host: this.host,
      port: this.port,
    };
  }

  /**
   * Stops the Python child process gracefully.
   * Uses taskkill on Windows to ensure child processes are terminated, preventing orphans.
   */
  public async stop(): Promise<void> {
    const childPid = this.childProcess?.pid;
    const enginePid = this.enginePid;

    if (!childPid && !enginePid) {
      return;
    }

    console.log(`[Supervisor] Stopping Python processes (Child PID: ${childPid}, Engine PID: ${enginePid})`);

    if (process.platform === 'win32') {
      if (childPid) {
        try {
          execSync(`taskkill /pid ${childPid} /T /F`, { stdio: 'ignore' });
        } catch {}
      }
      if (enginePid && enginePid !== childPid) {
        try {
          execSync(`taskkill /pid ${enginePid} /T /F`, { stdio: 'ignore' });
        } catch {}
      }
    } else {
      if (this.childProcess) {
        this.childProcess.kill('SIGTERM');
        setTimeout(() => {
          if (this.childProcess && !this.childProcess.killed) {
            this.childProcess.kill('SIGKILL');
          }
        }, 2000);
      }
    }

    this.childProcess = null;
    this.enginePid = null;
    this.isRunning = false;
    this.isAuthenticated = false;
    this.port = null;
    this.notifyStateChange();
    console.log(`[Supervisor] Python processes terminated.`);
  }
}
