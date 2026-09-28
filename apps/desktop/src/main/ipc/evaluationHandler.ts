/**
 * Electron Main IPC Handlers for Phase 8 Quality Evaluation & Benchmarking Subsystem.
 */

import { ipcMain } from 'electron';
import { PythonProcessSupervisor } from '../supervisor';
import {
  IPCResult,
  EvaluationConfig,
  EvaluationRunRequest,
  EvaluationRunProgress,
  EvaluationReport,
  EvaluationReportSummary,
} from '../../shared/types';

export function registerEvaluationIpcHandlers(supervisor: PythonProcessSupervisor) {
  // Trigger evaluation run
  ipcMain.handle(
    'evaluation:run',
    async (event, reqPayload?: EvaluationRunRequest): Promise<IPCResult<{ eval_id: string; status: string }>> => {
      try {
        const payload = reqPayload !== undefined && reqPayload !== null ? reqPayload : (event as any);
        const data = await supervisor.authenticatedRequest<{ eval_id: string; status: string }>(
          '/api/v1/evaluation/run?workspace_id=default',
          {
            method: 'POST',
            body: JSON.stringify(payload || {}),
          }
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );

  // Poll progress for evaluation run
  ipcMain.handle(
    'evaluation:progress',
    async (event, evalIdParam?: string): Promise<IPCResult<EvaluationRunProgress>> => {
      try {
        const evalId = evalIdParam !== undefined && evalIdParam !== null ? evalIdParam : (event as any);
        const data = await supervisor.authenticatedRequest<EvaluationRunProgress>(
          `/api/v1/evaluation/progress/${evalId}?workspace_id=default`
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );

  // Cancel evaluation run in flight
  ipcMain.handle(
    'evaluation:cancel',
    async (event, evalIdParam?: string): Promise<IPCResult<{ status: string; eval_id: string }>> => {
      try {
        const evalId = evalIdParam !== undefined && evalIdParam !== null ? evalIdParam : (event as any);
        const data = await supervisor.authenticatedRequest<{ status: string; eval_id: string }>(
          `/api/v1/evaluation/cancel/${evalId}?workspace_id=default`,
          { method: 'POST' }
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );

  // List all evaluation reports
  ipcMain.handle(
    'evaluation:get-reports',
    async (): Promise<IPCResult<EvaluationReportSummary[]>> => {
      try {
        const data = await supervisor.authenticatedRequest<EvaluationReportSummary[]>(
          '/api/v1/evaluation/reports?workspace_id=default'
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );

  // Get full report card by ID
  ipcMain.handle(
    'evaluation:get-report',
    async (event, evalIdParam?: string): Promise<IPCResult<EvaluationReport>> => {
      try {
        const evalId = evalIdParam !== undefined && evalIdParam !== null ? evalIdParam : (event as any);
        const data = await supervisor.authenticatedRequest<EvaluationReport>(
          `/api/v1/evaluation/reports/${evalId}?workspace_id=default`
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );

  // Delete evaluation report by ID
  ipcMain.handle(
    'evaluation:delete-report',
    async (event, evalIdParam?: string): Promise<IPCResult<{ deleted: boolean; eval_id: string }>> => {
      try {
        const evalId = evalIdParam !== undefined && evalIdParam !== null ? evalIdParam : (event as any);
        const data = await supervisor.authenticatedRequest<{ deleted: boolean; eval_id: string }>(
          `/api/v1/evaluation/reports/${evalId}?workspace_id=default`,
          { method: 'DELETE' }
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );

  // Get evaluation configuration
  ipcMain.handle(
    'evaluation:get-config',
    async (): Promise<IPCResult<EvaluationConfig>> => {
      try {
        const data = await supervisor.authenticatedRequest<EvaluationConfig>(
          '/api/v1/evaluation/config?workspace_id=default'
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );

  // Update evaluation configuration
  ipcMain.handle(
    'evaluation:update-config',
    async (event, configPayload?: EvaluationConfig): Promise<IPCResult<EvaluationConfig>> => {
      try {
        const config = configPayload !== undefined && configPayload !== null ? configPayload : (event as any);
        const data = await supervisor.authenticatedRequest<EvaluationConfig>(
          '/api/v1/evaluation/config?workspace_id=default',
          {
            method: 'POST',
            body: JSON.stringify(config),
          }
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );
}
