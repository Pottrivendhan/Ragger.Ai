/**
 * Client service for Phase 9 Local AI Model Manager & Hardware Adaptation.
 * Bridges Electron IPC and direct FastAPI HTTP fallback.
 */

import { apiRequest } from './apiBridge';
import {
  CatalogResponse,
  DownloadProgress,
  HardwareCapabilities,
  InstalledInventoryResponse,
  ModelActivationRequest,
  ModelActivationResponse,
  OllamaDaemonStatus,
} from '../types/models';

export class ModelsClient {
  private static isElectron(): boolean {
    return typeof window !== 'undefined' && !!(window as any).ragger?.models;
  }

  /**
   * Fetches hardware capabilities and tier assessment.
   */
  static async getHardware(refresh: boolean = false): Promise<HardwareCapabilities> {
    if (this.isElectron()) {
      const res = await (window as any).ragger.models.getHardware(refresh);
      if (!res.success) {
        throw new Error(res.error || 'Failed to detect hardware capabilities.');
      }
      return res.data;
    }

    return apiRequest<HardwareCapabilities>(`/api/v1/models/hardware?refresh=${refresh}`);
  }

  /**
   * Fetches curated model catalog with host compatibility flags.
   */
  static async getCatalog(): Promise<CatalogResponse> {
    if (this.isElectron()) {
      const res = await (window as any).ragger.models.getCatalog();
      if (!res.success) {
        throw new Error(res.error || 'Failed to fetch model catalog.');
      }
      return res.data;
    }

    return apiRequest<CatalogResponse>('/api/v1/models/catalog');
  }

  /**
   * Fetches installed model inventory.
   */
  static async getInventory(): Promise<InstalledInventoryResponse> {
    if (this.isElectron()) {
      const res = await (window as any).ragger.models.getInventory();
      if (!res.success) {
        throw new Error(res.error || 'Failed to fetch installed models inventory.');
      }
      return res.data;
    }

    return apiRequest<InstalledInventoryResponse>('/api/v1/models/inventory');
  }

  /**
   * Checks Ollama local daemon reachability and installed tags.
   */
  static async getOllamaStatus(): Promise<OllamaDaemonStatus> {
    if (this.isElectron()) {
      const res = await (window as any).ragger.models.getOllamaStatus();
      if (!res.success) {
        throw new Error(res.error || 'Failed to probe Ollama status.');
      }
      return res.data;
    }

    return apiRequest<OllamaDaemonStatus>('/api/v1/models/ollama/status');
  }

  /**
   * Starts download (Direct Range or Ollama pull).
   */
  static async startDownload(modelKey: string): Promise<DownloadProgress> {
    const encoded = encodeURIComponent(modelKey);
    if (this.isElectron()) {
      const res = await (window as any).ragger.models.download(modelKey);
      if (!res.success) {
        throw new Error(res.error || 'Failed to start download.');
      }
      return res.data;
    }

    return apiRequest<DownloadProgress>(`/api/v1/models/download/${encoded}`, {
      method: 'POST',
    });
  }

  /**
   * Polls download or pull progress.
   */
  static async getProgress(modelKey: string): Promise<DownloadProgress> {
    const encoded = encodeURIComponent(modelKey);
    if (this.isElectron()) {
      const res = await (window as any).ragger.models.getProgress(modelKey);
      if (!res.success) {
        throw new Error(res.error || 'Failed to get progress.');
      }
      return res.data;
    }

    return apiRequest<DownloadProgress>(`/api/v1/models/download/progress/${encoded}`);
  }

  /**
   * Pauses an active direct download.
   */
  static async pauseDownload(modelKey: string): Promise<DownloadProgress> {
    const encoded = encodeURIComponent(modelKey);
    if (this.isElectron()) {
      const res = await (window as any).ragger.models.pauseDownload(modelKey);
      if (!res.success) {
        throw new Error(res.error || 'Failed to pause download.');
      }
      return res.data;
    }

    return apiRequest<DownloadProgress>(`/api/v1/models/download/pause/${encoded}`, {
      method: 'POST',
    });
  }

  /**
   * Resumes a paused direct download.
   */
  static async resumeDownload(modelKey: string): Promise<DownloadProgress> {
    const encoded = encodeURIComponent(modelKey);
    if (this.isElectron()) {
      const res = await (window as any).ragger.models.resumeDownload(modelKey);
      if (!res.success) {
        throw new Error(res.error || 'Failed to resume download.');
      }
      return res.data;
    }

    return apiRequest<DownloadProgress>(`/api/v1/models/download/resume/${encoded}`, {
      method: 'POST',
    });
  }

  /**
   * Cancels an active download or pull.
   */
  static async cancelDownload(modelKey: string): Promise<DownloadProgress> {
    const encoded = encodeURIComponent(modelKey);
    if (this.isElectron()) {
      const res = await (window as any).ragger.models.cancelDownload(modelKey);
      if (!res.success) {
        throw new Error(res.error || 'Failed to cancel download.');
      }
      return res.data;
    }

    return apiRequest<DownloadProgress>(`/api/v1/models/download/cancel/${encoded}`, {
      method: 'POST',
    });
  }

  /**
   * Deletes an installed model from local storage.
   */
  static async deleteModel(modelKey: string): Promise<{ success: boolean; model_key: string; message: string }> {
    const encoded = encodeURIComponent(modelKey);
    if (this.isElectron()) {
      const res = await (window as any).ragger.models.deleteModel(modelKey);
      if (!res.success) {
        throw new Error(res.error || 'Failed to delete model.');
      }
      return res.data;
    }

    return apiRequest<{ success: boolean; model_key: string; message: string }>(`/api/v1/models/installed/${encoded}`, {
      method: 'DELETE',
    });
  }

  /**
   * Explicitly activates an installed model into Phase 7 (generation) or Phase 8 (evaluation) runtime configuration.
   */
  static async activateModel(
    modelKey: string,
    targetRole: 'generation' | 'evaluation'
  ): Promise<ModelActivationResponse> {
    const payload: ModelActivationRequest = {
      model_key: modelKey,
      target_role: targetRole,
    };

    if (this.isElectron()) {
      const res = await (window as any).ragger.models.activateModel(payload);
      if (!res.success) {
        throw new Error(res.error || 'Failed to activate model.');
      }
      return res.data;
    }

    const encodedKey = encodeURIComponent(modelKey);
    return apiRequest<ModelActivationResponse>(`/api/v1/models/${encodedKey}/activate`, {
      method: 'POST',
      body: JSON.stringify({ target_role: targetRole }),
    });
  }
}
