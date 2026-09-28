/**
 * Client service for interacting with the Recommendation Engine.
 * Supports both Electron IPC and Browser HTTP Bridge.
 */

import { apiRequest } from './apiBridge';
import {
  ApprovedBuildConfig,
  ArchitectureSpec,
  BuildPrerequisiteValidationResult,
  RecommendationResult,
} from '../types/recommendation';

export class RecommendationClient {
  private static isElectron(): boolean {
    return typeof window !== 'undefined' && !!window.ragger?.recommendation;
  }

  static async evaluateRecommendation(workspaceId: string = 'default'): Promise<RecommendationResult> {
    if (this.isElectron()) {
      const res = await window.ragger!.recommendation!.evaluate(workspaceId);
      if (!res.success) {
        throw new Error(res.error || 'Failed to evaluate recommendation.');
      }
      return res.data;
    }

    return apiRequest<RecommendationResult>('/api/v1/recommendation/evaluate', {
      method: 'POST',
      body: JSON.stringify({ workspace_id: workspaceId }),
    });
  }

  static async getCurrentRecommendation(): Promise<RecommendationResult | null> {
    if (this.isElectron()) {
      const res = await window.ragger!.recommendation!.getCurrent();
      if (!res.success) {
        throw new Error(res.error || 'Failed to fetch current recommendation.');
      }
      return res.data || null;
    }

    try {
      return await apiRequest<RecommendationResult>('/api/v1/recommendation/current', { method: 'GET' });
    } catch {
      return null;
    }
  }

  static async listArchitectures(): Promise<ArchitectureSpec[]> {
    if (this.isElectron()) {
      const res = await window.ragger!.recommendation!.listArchitectures();
      if (!res.success) {
        throw new Error(res.error || 'Failed to list architectures.');
      }
      return res.data || [];
    }

    return apiRequest<ArchitectureSpec[]>('/api/v1/recommendation/architectures', { method: 'GET' });
  }

  static async approveConfiguration(payload: {
    workspace_id: string;
    architecture_id: string;
    source_ids?: string[];
    custom_chunking?: any;
    custom_embedding?: any;
    custom_vector_db?: any;
    custom_retrieval?: any;
    is_revision?: boolean;
  }): Promise<ApprovedBuildConfig> {
    if (this.isElectron()) {
      const res = await window.ragger!.recommendation!.approve(payload);
      if (!res.success) {
        throw new Error(res.error || 'Failed to approve configuration.');
      }
      return res.data;
    }

    return apiRequest<ApprovedBuildConfig>('/api/v1/recommendation/approve', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  static async getApprovedConfig(): Promise<ApprovedBuildConfig | null> {
    if (this.isElectron()) {
      const res = await window.ragger!.recommendation!.getApproved();
      if (!res.success) {
        throw new Error(res.error || 'Failed to fetch approved configuration.');
      }
      return res.data || null;
    }

    try {
      return await apiRequest<ApprovedBuildConfig>('/api/v1/recommendation/approved', { method: 'GET' });
    } catch {
      return null;
    }
  }

  static async validateBuildPrerequisites(): Promise<BuildPrerequisiteValidationResult> {
    if (this.isElectron()) {
      const res = await window.ragger!.recommendation!.validateBuild();
      if (!res.success) {
        return { valid: false, reason: res.error || 'Failed to validate build prerequisites.' } as any;
      }
      return res.data;
    }

    try {
      return await apiRequest<BuildPrerequisiteValidationResult>('/api/v1/recommendation/validate-build', { method: 'GET' });
    } catch (err: any) {
      return { valid: false, reason: err.message || 'Build prerequisites not satisfied.' } as any;
    }
  }
}
