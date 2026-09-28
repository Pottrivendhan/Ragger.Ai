/**
 * Electron Main IPC Handlers for Knowledge Analysis & Workspace Synthesis.
 */

import { ipcMain } from 'electron';
import { PythonProcessSupervisor } from '../supervisor';
import {
  AnalyzerProviderInfo,
  FileAnalysisProfile,
  IPCResult,
  WorkspaceKnowledgeProfile,
} from '../../shared/types';

export function registerAnalysisIpcHandlers(supervisor: PythonProcessSupervisor) {
  // Analyze a single file source
  ipcMain.handle(
    'analysis:analyze-file',
    async (_event, sourceId: string, provider?: string): Promise<IPCResult<FileAnalysisProfile>> => {
      try {
        const data = await supervisor.authenticatedRequest<FileAnalysisProfile>(
          '/api/v1/analysis/file',
          {
            method: 'POST',
            body: JSON.stringify({ source_id: sourceId, provider }),
          }
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );

  // Deterministically synthesize workspace profile
  ipcMain.handle(
    'analysis:synthesize-workspace',
    async (_event, workspaceId: string = 'default'): Promise<IPCResult<WorkspaceKnowledgeProfile>> => {
      try {
        const data = await supervisor.authenticatedRequest<WorkspaceKnowledgeProfile>(
          '/api/v1/analysis/workspace',
          {
            method: 'POST',
            body: JSON.stringify({ workspace_id: workspaceId }),
          }
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );

  // List all analyzed file profiles
  ipcMain.handle(
    'analysis:get-profiles',
    async (): Promise<IPCResult<FileAnalysisProfile[]>> => {
      try {
        const data = await supervisor.authenticatedRequest<FileAnalysisProfile[]>(
          '/api/v1/analysis/profiles'
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );

  // Get current workspace profile
  ipcMain.handle(
    'analysis:get-workspace-profile',
    async (): Promise<IPCResult<WorkspaceKnowledgeProfile | null>> => {
      try {
        const data = await supervisor.authenticatedRequest<WorkspaceKnowledgeProfile | null>(
          '/api/v1/analysis/workspace'
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );

  // List available analysis providers
  ipcMain.handle(
    'analysis:list-providers',
    async (): Promise<IPCResult<AnalyzerProviderInfo[]>> => {
      try {
        const data = await supervisor.authenticatedRequest<AnalyzerProviderInfo[]>(
          '/api/v1/analysis/providers'
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );
}
