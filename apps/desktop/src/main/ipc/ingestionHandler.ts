/**
 * Electron Main IPC Handlers for File Ingestion & Parsing.
 */

import { dialog, ipcMain } from 'electron';
import { PythonProcessSupervisor } from '../supervisor';
import { DetectedFileType, IngestionResult, IPCResult, SourceRecord } from '../../shared/types';

export function registerIngestionIpcHandlers(supervisor: PythonProcessSupervisor) {
  // File dialog to pick local documents/datasets
  ipcMain.handle('dialog:open-file', async (): Promise<IPCResult<string[] | string | null>> => {
    try {
      const result = await dialog.showOpenDialog({
        properties: ['openFile', 'multiSelections'],
        filters: [
          {
            name: 'Supported Documents & Datasets',
            extensions: [
              'pdf', 'docx', 'doc', 'pptx', 'xlsx', 'xls', 'csv', 'tsv',
              'txt', 'md', 'json', 'xml', 'html', 'epub',
            ],
          },
          { name: 'All Files', extensions: ['*'] },
        ],
      });

      if (result.canceled || result.filePaths.length === 0) {
        return { success: true, data: null };
      }

      return { success: true, data: result.filePaths };
    } catch (err: any) {
      return { success: false, error: err.message };
    }
  });

  // Fast format detection endpoint proxy
  ipcMain.handle(
    'ingestion:detect',
    async (_event, filePath: string): Promise<IPCResult<DetectedFileType>> => {
      try {
        const data = await supervisor.authenticatedRequest<DetectedFileType>(
          '/api/v1/ingestion/detect',
          {
            method: 'POST',
            body: JSON.stringify({ file_path: filePath }),
          }
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );

  // Full ingestion & normalization pipeline endpoint proxy
  ipcMain.handle(
    'ingestion:ingest',
    async (_event, filePath: string, customId?: string): Promise<IPCResult<IngestionResult>> => {
      try {
        const data = await supervisor.authenticatedRequest<IngestionResult>(
          '/api/v1/ingestion/ingest',
          {
            method: 'POST',
            body: JSON.stringify({ file_path: filePath, custom_id: customId }),
          }
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );

  // Source registry retrieval proxy
  ipcMain.handle(
    'ingestion:list-sources',
    async (): Promise<IPCResult<SourceRecord[]>> => {
      try {
        const data = await supervisor.authenticatedRequest<SourceRecord[]>(
          '/api/v1/ingestion/sources'
        );
        return { success: true, data };
      } catch (err: any) {
        return { success: false, error: err.message };
      }
    }
  );
}
