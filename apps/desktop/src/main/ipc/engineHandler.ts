/**
 * Electron Main IPC Handlers for Engine Communication.
 */

import { ipcMain } from 'electron';
import { PythonProcessSupervisor } from '../supervisor';
import { IPCResult } from '../../shared/types';

export function registerEngineIpcHandlers(supervisor: PythonProcessSupervisor) {
  ipcMain.handle('engine:get-status', async (): Promise<IPCResult<any>> => {
    try {
      const status = supervisor.getStatus();
      return { success: true, data: status };
    } catch (err: any) {
      return { success: false, error: err.message };
    }
  });

  ipcMain.handle('engine:get-health', async (): Promise<IPCResult<any>> => {
    try {
      const health = await supervisor.getHealth();
      return { success: true, data: health };
    } catch (err: any) {
      return { success: false, error: err.message };
    }
  });

  ipcMain.handle('engine:get-runtime', async (): Promise<IPCResult<any>> => {
    try {
      const runtime = await supervisor.getRuntime();
      return { success: true, data: runtime };
    } catch (err: any) {
      return { success: false, error: err.message };
    }
  });

  ipcMain.handle('engine:restart', async (): Promise<IPCResult<any>> => {
    try {
      console.log('[IPC] Manual restart of Python engine requested.');
      await supervisor.stop();
      const status = await supervisor.start();
      return { success: true, data: status };
    } catch (err: any) {
      return { success: false, error: err.message };
    }
  });

  ipcMain.handle('engine:get-api-config', async (): Promise<IPCResult<{ baseUrl: string | null; token: string | null; host: string; port: number | null }>> => {
    try {
      const config = supervisor.getApiConfig();
      return { success: true, data: config };
    } catch (err: any) {
      return { success: false, error: err.message };
    }
  });
}
