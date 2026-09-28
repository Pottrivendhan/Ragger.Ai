/**
 * Client service for interacting with the Analyzer Agent subsystem.
 * Supports both Electron IPC and Browser HTTP Bridge.
 */

import { apiRequest } from './apiBridge';
import {
  AnalyzerProviderInfo,
  FileAnalysisProfile,
  WorkspaceKnowledgeProfile,
} from '../types/analysis';

export class AnalysisClient {
  /**
   * Executes observational analysis on a single ingested file.
   */
  public static async analyzeFile(
    sourceId: string,
    provider?: string
  ): Promise<FileAnalysisProfile> {
    if (window.ragger?.analysis?.analyzeFile) {
      const res = await window.ragger.analysis.analyzeFile(sourceId, provider);
      if (!res.success || !res.data) {
        throw new Error(res.error || `Failed to analyze source '${sourceId}'.`);
      }
      return res.data;
    }

    return apiRequest<FileAnalysisProfile>('/api/v1/analysis/file', {
      method: 'POST',
      body: JSON.stringify({ source_id: sourceId, provider }),
    });
  }

  /**
   * Deterministically synthesizes all analyzed files in a workspace into a WorkspaceKnowledgeProfile.
   * Performs zero LLM calls.
   */
  public static async synthesizeWorkspace(
    workspaceId: string = 'default'
  ): Promise<WorkspaceKnowledgeProfile> {
    if (window.ragger?.analysis?.synthesizeWorkspace) {
      const res = await window.ragger.analysis.synthesizeWorkspace(workspaceId);
      if (!res.success || !res.data) {
        throw new Error(res.error || 'Failed to synthesize workspace.');
      }
      return res.data;
    }

    return apiRequest<WorkspaceKnowledgeProfile>('/api/v1/analysis/workspace', {
      method: 'POST',
      body: JSON.stringify({ workspace_id: workspaceId }),
    });
  }

  /**
   * Retrieves all saved file analysis profiles.
   */
  public static async getProfiles(): Promise<FileAnalysisProfile[]> {
    if (window.ragger?.analysis?.getProfiles) {
      const res = await window.ragger.analysis.getProfiles();
      if (!res.success || !res.data) {
        throw new Error(res.error || 'Failed to retrieve analysis profiles.');
      }
      return res.data;
    }

    return apiRequest<FileAnalysisProfile[]>('/api/v1/analysis/profiles', {
      method: 'GET',
    });
  }

  /**
   * Retrieves current cached workspace knowledge profile.
   */
  public static async getWorkspaceProfile(): Promise<WorkspaceKnowledgeProfile | null> {
    if (window.ragger?.analysis?.getWorkspaceProfile) {
      const res = await window.ragger.analysis.getWorkspaceProfile();
      if (!res.success) {
        throw new Error(res.error || 'Failed to retrieve workspace profile.');
      }
      return res.data ?? null;
    }

    try {
      return await apiRequest<WorkspaceKnowledgeProfile>('/api/v1/analysis/workspace', {
        method: 'GET',
      });
    } catch {
      return null;
    }
  }

  /**
   * Lists available analysis providers.
   */
  public static async listProviders(): Promise<AnalyzerProviderInfo[]> {
    if (window.ragger?.analysis?.listProviders) {
      const res = await window.ragger.analysis.listProviders();
      if (!res.success || !res.data) {
        throw new Error(res.error || 'Failed to retrieve analyzer providers.');
      }
      return res.data;
    }

    return apiRequest<AnalyzerProviderInfo[]>('/api/v1/analysis/providers', {
      method: 'GET',
    });
  }
}
