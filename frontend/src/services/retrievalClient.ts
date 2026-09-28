/**
 * Client service for interacting with the Phase 6 RAG Retrieval Engine Subsystem.
 * Supports both Electron IPC bridge and universal browser HTTP bridge.
 */

import { apiRequest } from './apiBridge';
import {
  RetrievalQuery,
  RetrievalResponse,
  RetrievalStatus,
} from '../types/retrieval';

export class RetrievalClient {
  private static isElectron(): boolean {
    return typeof window !== 'undefined' && !!window.ragger?.retrieval;
  }

  /**
   * Executes a grounded retrieval query against the active index.
   */
  static async query(payload: RetrievalQuery): Promise<RetrievalResponse> {
    if (this.isElectron()) {
      const res = await window.ragger!.retrieval!.query(payload);
      if (!res.success) {
        throw new Error(res.error || 'Failed to execute retrieval query.');
      }
      return res.data!;
    }

    return apiRequest<RetrievalResponse>('/api/v1/retrieval/query', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  /**
   * Fetches active build retrieval status and diagnostic readiness.
   */
  static async getStatus(): Promise<RetrievalStatus> {
    if (this.isElectron()) {
      const res = await window.ragger!.retrieval!.getStatus();
      if (!res.success) {
        throw new Error(res.error || 'Failed to fetch retrieval status.');
      }
      return res.data!;
    }

    return apiRequest<RetrievalStatus>('/api/v1/retrieval/status', { method: 'GET' });
  }

  /**
   * Forces single-flight cache reload of the active build.
   */
  static async reload(): Promise<{ status: string; build_id: string; manifest_id: string }> {
    if (this.isElectron()) {
      const res = await window.ragger!.retrieval!.reload();
      if (!res.success) {
        throw new Error(res.error || 'Failed to reload retrieval cache.');
      }
      return res.data!;
    }

    return apiRequest<{ status: string; build_id: string; manifest_id: string }>(
      '/api/v1/retrieval/reload',
      { method: 'POST' }
    );
  }
}
