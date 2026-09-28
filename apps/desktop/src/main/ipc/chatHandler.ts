/**
 * Electron Main IPC Handlers for Phase 7 Grounded Generation & Interactive RAG Chat Subsystem.
 */

import { ipcMain } from 'electron';
import { PythonProcessSupervisor } from '../supervisor';
import {
  IPCResult,
  ChatQueryRequest,
  GenerationResponse,
  ChatSession,
  GenerationConfig,
} from '../../shared/types';

export function registerChatIpcHandlers(supervisor: PythonProcessSupervisor) {
  // Execute synchronous grounded generation
  ipcMain.handle(
    'chat:generate',
    async (event, queryPayload?: ChatQueryRequest): Promise<IPCResult<GenerationResponse>> => {
      try {
        const payload = (queryPayload !== undefined && queryPayload !== null) ? queryPayload : (event as any);
        const data = await supervisor.authenticatedRequest<GenerationResponse>(
          '/api/v1/chat/generate?workspace_id=default',
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

  // Cancel generation in progress
  ipcMain.handle(
    'chat:cancel',
    async (event, sessionIdParam?: string): Promise<IPCResult<{ status: string; session_id: string }>> => {
      try {
        const sessionId = (sessionIdParam !== undefined && sessionIdParam !== null) ? sessionIdParam : (event as any);
        const data = await supervisor.authenticatedRequest<{ status: string; session_id: string }>(
          `/api/v1/chat/cancel/${sessionId}`,
          { method: 'POST' }
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );

  // List chat sessions for current workspace
  ipcMain.handle(
    'chat:get-sessions',
    async (): Promise<IPCResult<ChatSession[]>> => {
      try {
        const data = await supervisor.authenticatedRequest<ChatSession[]>(
          '/api/v1/chat/sessions?workspace_id=default'
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );

  // Get specific session by ID
  ipcMain.handle(
    'chat:get-session',
    async (event, sessionIdParam?: string): Promise<IPCResult<ChatSession>> => {
      try {
        const sessionId = (sessionIdParam !== undefined && sessionIdParam !== null) ? sessionIdParam : (event as any);
        const data = await supervisor.authenticatedRequest<ChatSession>(
          `/api/v1/chat/sessions/${sessionId}?workspace_id=default`
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );

  // Delete specific session
  ipcMain.handle(
    'chat:delete-session',
    async (event, sessionIdParam?: string): Promise<IPCResult<{ deleted: boolean; session_id: string }>> => {
      try {
        const sessionId = (sessionIdParam !== undefined && sessionIdParam !== null) ? sessionIdParam : (event as any);
        const data = await supervisor.authenticatedRequest<{ deleted: boolean; session_id: string }>(
          `/api/v1/chat/sessions/${sessionId}?workspace_id=default`,
          { method: 'DELETE' }
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );

  // Get generation config
  ipcMain.handle(
    'chat:get-config',
    async (): Promise<IPCResult<GenerationConfig>> => {
      try {
        const data = await supervisor.authenticatedRequest<GenerationConfig>(
          '/api/v1/chat/config'
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );

  // Update generation config
  ipcMain.handle(
    'chat:update-config',
    async (event, configPayload?: GenerationConfig): Promise<IPCResult<GenerationConfig>> => {
      try {
        const payload = (configPayload !== undefined && configPayload !== null) ? configPayload : (event as any);
        const data = await supervisor.authenticatedRequest<GenerationConfig>(
          '/api/v1/chat/config',
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
}
