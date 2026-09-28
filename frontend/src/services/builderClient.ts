/**
 * Client service for interacting with the RAG Builder Subsystem.
 * Supports both Electron IPC bridge and universal browser HTTP bridge.
 */

import { apiRequest } from './apiBridge';
import { BuildManifest, BuildProgress } from '../types/builder';

export class BuilderClient {
  private static isElectron(): boolean {
    return typeof window !== 'undefined' && !!window.ragger?.builder;
  }

  /**
   * Triggers the knowledge base build pipeline.
   */
  static async startBuild(): Promise<{ status: string; build_id: string }> {
    if (this.isElectron()) {
      const res = await window.ragger!.builder!.start();
      if (!res.success) {
        throw new Error(res.error || 'Failed to start build.');
      }
      return res.data!;
    }

    return apiRequest<{ status: string; build_id: string }>('/api/v1/builder/start', {
      method: 'POST',
    });
  }

  /**
   * Fetches authoritative real-time build telemetry.
   */
  static async getProgress(): Promise<BuildProgress> {
    if (this.isElectron()) {
      const res = await window.ragger!.builder!.getProgress();
      if (!res.success) {
        throw new Error(res.error || 'Failed to fetch build progress.');
      }
      return res.data!;
    }

    return apiRequest<BuildProgress>('/api/v1/builder/progress', { method: 'GET' });
  }

  /**
   * Fetches the active verified BuildManifest.
   */
  static async getActiveManifest(): Promise<BuildManifest | null> {
    if (this.isElectron()) {
      const res = await window.ragger!.builder!.getManifest();
      if (!res.success) {
        return null;
      }
      return res.data || null;
    }

    try {
      return await apiRequest<BuildManifest>('/api/v1/builder/manifest', { method: 'GET' });
    } catch {
      return null;
    }
  }

  /**
   * Requests graceful cancellation of the active build.
   */
  static async cancelBuild(buildId: string): Promise<{ status: string; build_id: string }> {
    if (this.isElectron()) {
      const res = await window.ragger!.builder!.cancel(buildId);
      if (!res.success) {
        throw new Error(res.error || 'Failed to cancel build.');
      }
      return res.data!;
    }

    return apiRequest<{ status: string; build_id: string }>('/api/v1/builder/cancel', {
      method: 'POST',
      body: JSON.stringify({ build_id: buildId }),
    });
  }
}
