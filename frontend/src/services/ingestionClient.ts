/**
 * Client service for interacting with the Ingestion subsystem.
 * Supports both Electron IPC and Browser HTTP Bridge.
 */

import { apiRequest } from './apiBridge';
import {
  DetectedFileType,
  IngestionResult,
  SourceRecord,
} from '../types/ingestion';

export class IngestionClient {
  /**
   * Opens the native OS file picker to select a document or dataset.
   */
  public static async openFileDialog(): Promise<string[] | string | null> {
    if (window.ragger?.ingestion?.openFileDialog) {
      const res = await window.ragger.ingestion.openFileDialog();
      if (!res.success) {
        throw new Error(res.error || 'Failed to open file picker.');
      }
      return res.data ?? null;
    }
    // Browser fallback: prompt user for absolute file path
    const path = window.prompt(
      'Enter the absolute path to the document/dataset to ingest (e.g. D:\\D Downloads\\Class_10_English_2024_Edition-www.tntextbooks.in.pdf):'
    );
    return path ? path.trim() : null;
  }

  /**
   * Triggers fast multi-signal format detection on a given file path.
   */
  public static async detectFile(filePath: string): Promise<DetectedFileType> {
    if (window.ragger?.ingestion?.detectFile) {
      const res = await window.ragger.ingestion.detectFile(filePath);
      if (!res.success || !res.data) {
        throw new Error(res.error || 'Detection failed.');
      }
      return res.data;
    }

    return apiRequest<DetectedFileType>('/api/v1/ingestion/detect', {
      method: 'POST',
      body: JSON.stringify({ file_path: filePath }),
    });
  }

  /**
   * Runs the full end-to-end ingestion pipeline:
   * detect -> register -> parse -> normalize -> sample.
   */
  public static async ingestFile(filePath: string, customId?: string): Promise<IngestionResult> {
    if (window.ragger?.ingestion?.ingestFile) {
      const res = await window.ragger.ingestion.ingestFile(filePath, customId);
      if (!res.success || !res.data) {
        throw new Error(res.error || 'Ingestion failed.');
      }
      return res.data;
    }

    return apiRequest<IngestionResult>('/api/v1/ingestion/ingest', {
      method: 'POST',
      body: JSON.stringify({ file_path: filePath, custom_id: customId }),
    });
  }

  /**
   * Uploads a File object from browser input to engine, parses and normalizes it.
   */
  public static async uploadFile(file: File): Promise<IngestionResult> {
    const formData = new FormData();
    formData.append('file', file);
    return apiRequest<IngestionResult>('/api/v1/ingestion/upload', {
      method: 'POST',
      body: formData,
    });
  }

  /**
   * Lists all persistent source records registered in this workspace.
   */
  public static async listSources(): Promise<SourceRecord[]> {
    if (window.ragger?.ingestion?.listSources) {
      const res = await window.ragger.ingestion.listSources();
      if (!res.success || !res.data) {
        throw new Error(res.error || 'Failed to list registered sources.');
      }
      return res.data;
    }

    return apiRequest<SourceRecord[]>('/api/v1/ingestion/sources', {
      method: 'GET',
    });
  }
}
