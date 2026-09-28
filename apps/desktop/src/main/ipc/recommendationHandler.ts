/**
 * Electron Main IPC Handlers for Recommendation Engine & Approval Lifecycle.
 */

import { ipcMain } from 'electron';
import { PythonProcessSupervisor } from '../supervisor';
import {
  ApprovedBuildConfig,
  ArchitectureSpec,
  BuildPrerequisiteValidationResult,
  IPCResult,
  RecommendationResult,
} from '../../shared/types';

export function registerRecommendationIpcHandlers(supervisor: PythonProcessSupervisor) {
  // Deterministically evaluate recommendation for current workspace
  ipcMain.handle(
    'recommendation:evaluate',
    async (_event, workspaceId: string = 'default'): Promise<IPCResult<RecommendationResult>> => {
      try {
        const data = await supervisor.authenticatedRequest<RecommendationResult>(
          '/api/v1/recommendation/evaluate',
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

  // Retrieve current evaluated recommendation
  ipcMain.handle(
    'recommendation:get-current',
    async (): Promise<IPCResult<RecommendationResult | null>> => {
      try {
        const data = await supervisor.authenticatedRequest<RecommendationResult | null>(
          '/api/v1/recommendation/current'
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );

  // List all available architecture specifications
  ipcMain.handle(
    'recommendation:list-architectures',
    async (): Promise<IPCResult<ArchitectureSpec[]>> => {
      try {
        const data = await supervisor.authenticatedRequest<ArchitectureSpec[]>(
          '/api/v1/recommendation/architectures'
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );

  // Approve and freeze build configuration snapshot
  ipcMain.handle(
    'recommendation:approve',
    async (_event, approvalPayload: any): Promise<IPCResult<ApprovedBuildConfig>> => {
      try {
        const data = await supervisor.authenticatedRequest<ApprovedBuildConfig>(
          '/api/v1/recommendation/approve',
          {
            method: 'POST',
            body: JSON.stringify(approvalPayload),
          }
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );

  // Get current frozen approved configuration snapshot
  ipcMain.handle(
    'recommendation:get-approved',
    async (): Promise<IPCResult<ApprovedBuildConfig | null>> => {
      try {
        const data = await supervisor.authenticatedRequest<ApprovedBuildConfig | null>(
          '/api/v1/recommendation/approved'
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );

  // Validate Phase 5 build contract prerequisites
  ipcMain.handle(
    'recommendation:validate-build',
    async (): Promise<IPCResult<BuildPrerequisiteValidationResult>> => {
      try {
        const data = await supervisor.authenticatedRequest<BuildPrerequisiteValidationResult>(
          '/api/v1/recommendation/validate-build'
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );
}
