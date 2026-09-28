/**
 * Electron Main IPC Handlers for Phase 9 Local AI Model Manager Subsystem.
 */

import { ipcMain } from 'electron';
import { PythonProcessSupervisor } from '../supervisor';
import {
  IPCResult,
  HardwareCapabilities,
  CatalogResponse,
  InstalledInventoryResponse,
  OllamaDaemonStatus,
  DownloadProgress,
  ModelActivationRequest,
  ModelActivationResponse,
} from '../../shared/types';

export function registerModelsIpcHandlers(supervisor: PythonProcessSupervisor) {
  // Get hardware detection results
  ipcMain.handle(
    'models:get-hardware',
    async (_event, refresh?: boolean): Promise<IPCResult<HardwareCapabilities>> => {
      try {
        const url = `/api/v1/models/hardware?refresh=${Boolean(refresh)}`;
        const data = await supervisor.authenticatedRequest<HardwareCapabilities>(url);
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );

  // Get curated catalog with compatibility checks
  ipcMain.handle(
    'models:get-catalog',
    async (): Promise<IPCResult<CatalogResponse>> => {
      try {
        const data = await supervisor.authenticatedRequest<CatalogResponse>('/api/v1/models/catalog');
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );

  // Get installed model inventory
  ipcMain.handle(
    'models:get-inventory',
    async (): Promise<IPCResult<InstalledInventoryResponse>> => {
      try {
        const data = await supervisor.authenticatedRequest<InstalledInventoryResponse>('/api/v1/models/inventory');
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );

  // Get Ollama daemon status
  ipcMain.handle(
    'models:get-ollama-status',
    async (): Promise<IPCResult<OllamaDaemonStatus>> => {
      try {
        const data = await supervisor.authenticatedRequest<OllamaDaemonStatus>('/api/v1/models/ollama/status');
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );

  // Start model download / pull
  ipcMain.handle(
    'models:download',
    async (event, modelKeyParam?: string): Promise<IPCResult<DownloadProgress>> => {
      try {
        const modelKey = modelKeyParam !== undefined && modelKeyParam !== null ? modelKeyParam : (event as any);
        const encodedKey = encodeURIComponent(modelKey);
        const data = await supervisor.authenticatedRequest<DownloadProgress>(
          `/api/v1/models/download/${encodedKey}`,
          { method: 'POST' }
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );

  // Poll download progress
  ipcMain.handle(
    'models:download-progress',
    async (event, modelKeyParam?: string): Promise<IPCResult<DownloadProgress>> => {
      try {
        const modelKey = modelKeyParam !== undefined && modelKeyParam !== null ? modelKeyParam : (event as any);
        const encodedKey = encodeURIComponent(modelKey);
        const data = await supervisor.authenticatedRequest<DownloadProgress>(
          `/api/v1/models/download/progress/${encodedKey}`
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );

  // Pause active download
  ipcMain.handle(
    'models:pause-download',
    async (event, modelKeyParam?: string): Promise<IPCResult<DownloadProgress>> => {
      try {
        const modelKey = modelKeyParam !== undefined && modelKeyParam !== null ? modelKeyParam : (event as any);
        const encodedKey = encodeURIComponent(modelKey);
        const data = await supervisor.authenticatedRequest<DownloadProgress>(
          `/api/v1/models/download/pause/${encodedKey}`,
          { method: 'POST' }
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );

  // Resume paused download
  ipcMain.handle(
    'models:resume-download',
    async (event, modelKeyParam?: string): Promise<IPCResult<DownloadProgress>> => {
      try {
        const modelKey = modelKeyParam !== undefined && modelKeyParam !== null ? modelKeyParam : (event as any);
        const encodedKey = encodeURIComponent(modelKey);
        const data = await supervisor.authenticatedRequest<DownloadProgress>(
          `/api/v1/models/download/resume/${encodedKey}`,
          { method: 'POST' }
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );

  // Cancel download
  ipcMain.handle(
    'models:cancel-download',
    async (event, modelKeyParam?: string): Promise<IPCResult<DownloadProgress>> => {
      try {
        const modelKey = modelKeyParam !== undefined && modelKeyParam !== null ? modelKeyParam : (event as any);
        const encodedKey = encodeURIComponent(modelKey);
        const data = await supervisor.authenticatedRequest<DownloadProgress>(
          `/api/v1/models/download/cancel/${encodedKey}`,
          { method: 'POST' }
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );

  // Delete installed model
  ipcMain.handle(
    'models:delete',
    async (event, modelKeyParam?: string): Promise<IPCResult<{ success: boolean; model_key: string; message: string }>> => {
      try {
        const modelKey = modelKeyParam !== undefined && modelKeyParam !== null ? modelKeyParam : (event as any);
        const encodedKey = encodeURIComponent(modelKey);
        const data = await supervisor.authenticatedRequest<{ success: boolean; model_key: string; message: string }>(
          `/api/v1/models/installed/${encodedKey}`,
          { method: 'DELETE' }
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );

  // Activate model into generation or evaluation config
  ipcMain.handle(
    'models:activate',
    async (event, payloadParam?: ModelActivationRequest): Promise<IPCResult<ModelActivationResponse>> => {
      try {
        const payload = payloadParam !== undefined && payloadParam !== null ? payloadParam : (event as any);
        const encodedKey = encodeURIComponent(payload.model_key);
        const data = await supervisor.authenticatedRequest<ModelActivationResponse>(
          `/api/v1/models/${encodedKey}/activate`,
          {
            method: 'POST',
            body: JSON.stringify({
              target_role: payload.target_role,
              workspace_id: payload.workspace_id || 'default',
            }),
          }
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );
}
