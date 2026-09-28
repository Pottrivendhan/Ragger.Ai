/**
 * Electron Main IPC Handlers for Phase 5 RAG Builder Subsystem.
 */

import { ipcMain } from 'electron';
import { PythonProcessSupervisor } from '../supervisor';
import {
  BuildManifest,
  BuildProgress,
  IPCResult,
} from '../../shared/types';

export function registerBuilderIpcHandlers(supervisor: PythonProcessSupervisor) {
  // Start knowledge base construction
  ipcMain.handle(
    'builder:start',
    async (): Promise<IPCResult<{ status: string; build_id: string }>> => {
      try {
        const data = await supervisor.authenticatedRequest<{ status: string; build_id: string }>(
          '/api/v1/builder/start',
          { method: 'POST' }
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );

  // Poll authoritative progress state
  ipcMain.handle(
    'builder:get-progress',
    async (): Promise<IPCResult<BuildProgress>> => {
      try {
        const data = await supervisor.authenticatedRequest<BuildProgress>(
          '/api/v1/builder/progress'
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );

  // Retrieve active verified BuildManifest
  ipcMain.handle(
    'builder:get-manifest',
    async (): Promise<IPCResult<BuildManifest | null>> => {
      try {
        const data = await supervisor.authenticatedRequest<BuildManifest>(
          '/api/v1/builder/manifest'
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );

  // Request graceful build cancellation
  ipcMain.handle(
    'builder:cancel',
    async (_event, buildId: string): Promise<IPCResult<{ status: string; build_id: string }>> => {
      try {
        const data = await supervisor.authenticatedRequest<{ status: string; build_id: string }>(
          '/api/v1/builder/cancel',
          {
            method: 'POST',
            body: JSON.stringify({ build_id: buildId }),
          }
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );
}
