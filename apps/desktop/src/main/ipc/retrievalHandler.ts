/**
 * Electron Main IPC Handlers for Phase 6 RAG Retrieval Engine Subsystem.
 */

import { ipcMain } from 'electron';
import { PythonProcessSupervisor } from '../supervisor';
import {
  IPCResult,
  RetrievalQuery,
  RetrievalResponse,
  RetrievalStatus,
} from '../../shared/types';

export function registerRetrievalIpcHandlers(supervisor: PythonProcessSupervisor) {
  // Execute grounded retrieval query
  ipcMain.handle(
    'retrieval:query',
    async (event, queryPayload?: RetrievalQuery): Promise<IPCResult<RetrievalResponse>> => {
      try {
        // Handle direct testing invocation where event is omitted
        const payload = (queryPayload !== undefined && queryPayload !== null) ? queryPayload : (event as any);
        const data = await supervisor.authenticatedRequest<RetrievalResponse>(
          '/api/v1/retrieval/query',
          {
            method: 'POST',
            body: JSON.stringify(payload),
          }
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );

  // Retrieve active build status and diagnostic metadata
  ipcMain.handle(
    'retrieval:get-status',
    async (): Promise<IPCResult<RetrievalStatus>> => {
      try {
        const data = await supervisor.authenticatedRequest<RetrievalStatus>(
          '/api/v1/retrieval/status'
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );

  // Force single-flight reload of active build cache (zero args)
  ipcMain.handle(
    'retrieval:reload',
    async (): Promise<IPCResult<{ status: string; build_id: string; manifest_id: string }>> => {
      try {
        const data = await supervisor.authenticatedRequest<{
          status: string;
          build_id: string;
          manifest_id: string;
        }>('/api/v1/retrieval/reload', {
          method: 'POST',
        });
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );
}
