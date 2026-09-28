/**
 * Client service for Phase 8 Quality Evaluation & Benchmarking Subsystem.
 * Bridges Electron IPC and direct FastAPI HTTP fallback.
 */

import { apiRequest } from './apiBridge';
import {
  EvaluationConfig,
  EvaluationReport,
  EvaluationReportSummary,
  EvaluationRunProgress,
  EvaluationRunRequest,
  VersionEvaluationComparisonResult,
} from '../types/evaluation';

export class EvaluationClient {
  private static isElectron(): boolean {
    return typeof window !== 'undefined' && !!(window as any).ragger?.evaluation;
  }

  /**
   * Triggers an automated evaluation run.
   */
  static async triggerRun(payload?: EvaluationRunRequest): Promise<{ eval_id: string; status: string }> {
    if (this.isElectron()) {
      const res = await (window as any).ragger.evaluation.run(payload);
      if (!res.success) {
        throw new Error(res.error || 'Failed to initiate evaluation run.');
      }
      return res.data;
    }

    return apiRequest<{ eval_id: string; status: string }>('/api/v1/evaluation/run?workspace_id=default', {
      method: 'POST',
      body: JSON.stringify(payload || {}),
    });
  }

  /**
   * Polls progress telemetry for an evaluation job.
   */
  static async getProgress(evalId: string): Promise<EvaluationRunProgress> {
    if (this.isElectron()) {
      const res = await (window as any).ragger.evaluation.getProgress(evalId);
      if (!res.success) {
        throw new Error(res.error || 'Failed to fetch evaluation progress.');
      }
      return res.data;
    }

    return apiRequest<EvaluationRunProgress>(`/api/v1/evaluation/progress/${evalId}?workspace_id=default`);
  }

  /**
   * Requests cancellation of an evaluation run.
   */
  static async cancel(evalId: string): Promise<{ status: string; eval_id: string }> {
    if (this.isElectron()) {
      const res = await (window as any).ragger.evaluation.cancel(evalId);
      if (!res.success) {
        throw new Error(res.error || 'Failed to cancel evaluation run.');
      }
      return res.data;
    }

    return apiRequest<{ status: string; eval_id: string }>(`/api/v1/evaluation/cancel/${evalId}?workspace_id=default`, {
      method: 'POST',
    });
  }

  /**
   * Fetches persisted evaluation reports summary.
   */
  static async getReports(): Promise<EvaluationReportSummary[]> {
    if (this.isElectron()) {
      const res = await (window as any).ragger.evaluation.getReports();
      if (!res.success) {
        throw new Error(res.error || 'Failed to fetch evaluation reports.');
      }
      return res.data;
    }

    return apiRequest<EvaluationReportSummary[]>('/api/v1/evaluation/reports?workspace_id=default');
  }

  /**
   * Fetches evaluation reports specifically captured for a given RAG version.
   */
  static async getVersionReports(ragId: string, versionId: string): Promise<EvaluationReportSummary[]> {
    return apiRequest<EvaluationReportSummary[]>(
      `/api/v1/rag-artifacts/${encodeURIComponent(ragId)}/versions/${encodeURIComponent(versionId)}/evaluations?workspace_id=default`
    );
  }

  /**
   * Fetches full evaluation report card by ID.
   */
  static async getReport(evalId: string): Promise<EvaluationReport> {
    if (this.isElectron()) {
      const res = await (window as any).ragger.evaluation.getReport(evalId);
      if (!res.success) {
        throw new Error(res.error || 'Failed to fetch evaluation report.');
      }
      return res.data;
    }

    return apiRequest<EvaluationReport>(`/api/v1/evaluation/reports/${evalId}?workspace_id=default`);
  }

  /**
   * Objective numeric comparison between two evaluation reports for the same RAG artifact.
   */
  static async compareVersionEvaluations(
    ragId: string,
    baseEvalId: string,
    targetEvalId: string,
  ): Promise<VersionEvaluationComparisonResult> {
    const params = new URLSearchParams({
      base_eval_id: baseEvalId,
      target_eval_id: targetEvalId,
      workspace_id: 'default',
    });
    return apiRequest<VersionEvaluationComparisonResult>(
      `/api/v1/rag-artifacts/${encodeURIComponent(ragId)}/evaluations/compare?${params.toString()}`
    );
  }

  /**
   * Deletes an evaluation report by ID.
   */
  static async deleteReport(evalId: string): Promise<{ deleted: boolean; eval_id: string }> {
    if (this.isElectron()) {
      const res = await (window as any).ragger.evaluation.deleteReport(evalId);
      if (!res.success) {
        throw new Error(res.error || 'Failed to delete evaluation report.');
      }
      return res.data;
    }

    return apiRequest<{ deleted: boolean; eval_id: string }>(`/api/v1/evaluation/reports/${evalId}?workspace_id=default`, {
      method: 'DELETE',
    });
  }

  /**
   * Gets application-managed evaluation configuration.
   */
  static async getConfig(): Promise<EvaluationConfig> {
    if (this.isElectron()) {
      const res = await (window as any).ragger.evaluation.getConfig();
      if (!res.success) {
        throw new Error(res.error || 'Failed to fetch evaluation config.');
      }
      return res.data;
    }

    return apiRequest<EvaluationConfig>('/api/v1/evaluation/config?workspace_id=default');
  }

  /**
   * Updates application-managed evaluation configuration.
   */
  static async updateConfig(config: EvaluationConfig): Promise<EvaluationConfig> {
    if (this.isElectron()) {
      const res = await (window as any).ragger.evaluation.updateConfig(config);
      if (!res.success) {
        throw new Error(res.error || 'Failed to update evaluation config.');
      }
      return res.data;
    }

    return apiRequest<EvaluationConfig>('/api/v1/evaluation/config?workspace_id=default', {
      method: 'POST',
      body: JSON.stringify(config),
    });
  }
}
