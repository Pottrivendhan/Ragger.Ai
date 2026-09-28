import { apiRequest } from './apiBridge';
import { RAGArtifact, RAGArtifactDetail } from '../types/ragLibrary';

export class RAGLibraryClient {
  /**
   * Discovers and lists all compiled RAG knowledge artifacts in the workspace.
   */
  async listArtifacts(): Promise<RAGArtifact[]> {
    return apiRequest<RAGArtifact[]>('/api/v1/rag-library/builds', {
      method: 'GET',
    });
  }

  /**
   * Fetches detailed manifest, configuration, and sample chunks for a build.
   */
  async getArtifactDetail(buildId: string): Promise<RAGArtifactDetail> {
    return apiRequest<RAGArtifactDetail>(`/api/v1/rag-library/builds/${encodeURIComponent(buildId)}`, {
      method: 'GET',
    });
  }
}
