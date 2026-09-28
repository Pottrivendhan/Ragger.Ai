import { apiRequest } from './apiBridge';
import {
  RAGArtifactRecord,
  CreateRAGRequest,
  UpdateRAGRequest,
  RegisterVersionRequest,
  ExportRAGResponse,
  VersionComparisonResult,
  RAGSuggestionsResponse,
} from '../types/ragLifecycle';

export class RAGLifecycleClient {
  async getSuggestions(ragId: string): Promise<RAGSuggestionsResponse> {
    return apiRequest<RAGSuggestionsResponse>(`/api/v1/rag-artifacts/${encodeURIComponent(ragId)}/suggestions`);
  }

  async listRags(includeArchived: boolean = false): Promise<RAGArtifactRecord[]> {
    return apiRequest<RAGArtifactRecord[]>(`/api/v1/rag-artifacts?include_archived=${includeArchived}`);
  }

  async getRag(ragId: string): Promise<RAGArtifactRecord> {
    return apiRequest<RAGArtifactRecord>(`/api/v1/rag-artifacts/${encodeURIComponent(ragId)}`);
  }

  async createRag(req: CreateRAGRequest): Promise<RAGArtifactRecord> {
    return apiRequest<RAGArtifactRecord>('/api/v1/rag-artifacts', {
      method: 'POST',
      body: JSON.stringify(req),
    });
  }

  async updateRag(ragId: string, req: UpdateRAGRequest): Promise<RAGArtifactRecord> {
    return apiRequest<RAGArtifactRecord>(`/api/v1/rag-artifacts/${encodeURIComponent(ragId)}`, {
      method: 'PATCH',
      body: JSON.stringify(req),
    });
  }

  async registerVersion(ragId: string, req: RegisterVersionRequest): Promise<any> {
    return apiRequest<any>(`/api/v1/rag-artifacts/${encodeURIComponent(ragId)}/versions`, {
      method: 'POST',
      body: JSON.stringify(req),
    });
  }

  async rollbackVersion(ragId: string, targetVersionId: string): Promise<RAGArtifactRecord> {
    return apiRequest<RAGArtifactRecord>(`/api/v1/rag-artifacts/${encodeURIComponent(ragId)}/rollback?target_version_id=${encodeURIComponent(targetVersionId)}`, {
      method: 'POST',
    });
  }

  async compareVersions(ragId: string, baseVersionId: string, targetVersionId: string): Promise<VersionComparisonResult> {
    return apiRequest<VersionComparisonResult>(
      `/api/v1/rag-artifacts/${encodeURIComponent(ragId)}/versions/compare?base_version_id=${encodeURIComponent(baseVersionId)}&target_version_id=${encodeURIComponent(targetVersionId)}`
    );
  }

  async deleteRag(ragId: string, force: boolean = true): Promise<any> {
    return apiRequest<any>(`/api/v1/rag-artifacts/${encodeURIComponent(ragId)}?force=${force}`, {
      method: 'DELETE',
    });
  }

  async exportRagpack(ragId: string, versionId?: string): Promise<ExportRAGResponse> {
    const url = versionId
      ? `/api/v1/rag-artifacts/${encodeURIComponent(ragId)}/export?version_id=${encodeURIComponent(versionId)}`
      : `/api/v1/rag-artifacts/${encodeURIComponent(ragId)}/export`;
    return apiRequest<ExportRAGResponse>(url, { method: 'POST' });
  }

  async importRagpack(file: File): Promise<any> {
    const formData = new FormData();
    formData.append('file', file);
    return apiRequest<any>('/api/v1/rag-artifacts/import', {
      method: 'POST',
      body: formData,
    });
  }
}

