/**
 * Frontend Service Layer for Engine and Supervisor Communication.
 * Decouples React components from direct Electron IPC bindings.
 * Supports both Electron IPC and Browser HTTP Bridge.
 */

import { apiRequest } from './apiBridge';
import {
  AuthenticatedHealthResponse,
  RuntimeDiagnosticsResponse,
  SupervisorStatus,
} from '../types/engine';

export class EngineClient {
  private static isElectronAvailable(): boolean {
    return typeof window !== 'undefined' && Boolean(window.ragger?.engine);
  }

  /**
   * Fetches supervisor process telemetry via Electron IPC or browser HTTP bridge.
   */
  public static async getStatus(): Promise<SupervisorStatus> {
    if (this.isElectronAvailable()) {
      const res = await window.ragger!.engine.getStatus();
      if (!res.success) {
        throw new Error(res.error || 'Failed to fetch supervisor status.');
      }
      return res.data!;
    }

    // Browser Mode fallback: probe health endpoint
    try {
      const health = await this.getHealth();
      return {
        is_running: health.status === 'ok',
        pid: health.process_id || 1,
        port: null,
        host: '127.0.0.1',
        authenticated: health.authenticated,
        error: null,
        last_health_check: new Date().toISOString(),
      };
    } catch (err: any) {
      return {
        is_running: false,
        pid: null,
        port: null,
        host: '127.0.0.1',
        authenticated: false,
        error: `Browser mode: Engine not reachable (${err.message})`,
        last_health_check: null,
      };
    }
  }

  /**
   * Fetches authenticated FastAPI health status.
   */
  public static async getHealth(): Promise<AuthenticatedHealthResponse> {
    if (this.isElectronAvailable()) {
      const res = await window.ragger!.engine.getHealth();
      if (!res.success) {
        throw new Error(res.error || 'Failed to fetch engine health.');
      }
      return res.data!;
    }

    return apiRequest<AuthenticatedHealthResponse>('/api/v1/health');
  }

  /**
   * Fetches runtime diagnostics from Python FastAPI.
   */
  public static async getRuntime(): Promise<RuntimeDiagnosticsResponse> {
    if (this.isElectronAvailable()) {
      const res = await window.ragger!.engine.getRuntime();
      if (!res.success) {
        throw new Error(res.error || 'Failed to fetch runtime diagnostics.');
      }
      return res.data!;
    }

    return apiRequest<RuntimeDiagnosticsResponse>('/api/v1/runtime');
  }

  /**
   * Requests Electron supervisor to restart the Python engine.
   */
  public static async restart(): Promise<SupervisorStatus> {
    if (this.isElectronAvailable()) {
      const res = await window.ragger!.engine.restart();
      if (!res.success) {
        throw new Error(res.error || 'Failed to restart engine.');
      }
      return res.data!;
    }

    return this.getStatus();
  }

  /**
   * Subscribes to supervisor state change events.
   */
  public static subscribeStatus(callback: (status: SupervisorStatus) => void): () => void {
    if (!this.isElectronAvailable()) {
      return () => {};
    }
    return window.ragger!.engine.onStatusChange(callback);
  }
}
