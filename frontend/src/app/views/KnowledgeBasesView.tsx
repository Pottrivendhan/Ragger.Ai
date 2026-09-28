import React, { useEffect, useState } from 'react';
import {
  BookOpen,
  Download,
  Bot,
  FileText,
  ArrowLeft,
  RefreshCw,
  Database,
  Layers,
  CheckCircle2,
  GitBranch,
  RotateCcw,
  GitCompare,
  X,
  Award,
  Play,
  Scale,
  Trash2,
  AlertTriangle,
} from 'lucide-react';
import { RAGLibraryClient } from '../../services/ragLibraryClient';
import { RAGLifecycleClient } from '../../services/ragLifecycleClient';
import { EvaluationClient } from '../../services/evaluationClient';
import { AgentWorkspaceClient } from '../../services/agentWorkspaceClient';
import { ConversationStore } from '../../services/conversationStore';
import { RAGArtifact, RAGArtifactDetail } from '../../types/ragLibrary';
import { RAGArtifactRecord, VersionComparisonResult } from '../../types/ragLifecycle';
import { EvaluationReportSummary, VersionEvaluationComparisonResult } from '../../types/evaluation';
import { AgentProfile } from '../../types/agentWorkspace';

interface KnowledgeBasesViewProps {
  onOpenChat: (kbId: string) => void;
  onExportRagger: (title: string) => void;
  onCreateNew: () => void;
  onBuildNewVersion?: (ragId: string) => void;
}

export const KnowledgeBasesView: React.FC<KnowledgeBasesViewProps> = ({
  onOpenChat,
  onExportRagger,
  onCreateNew,
  onBuildNewVersion,
}) => {
  const [client] = useState(() => new RAGLibraryClient());
  const [lifecycleClient] = useState(() => new RAGLifecycleClient());
  const [agentClient] = useState(() => new AgentWorkspaceClient());
  const [artifacts, setArtifacts] = useState<RAGArtifact[]>([]);
  const [ragRecords, setRagRecords] = useState<RAGArtifactRecord[]>([]);
  const [selectedBuildId, setSelectedBuildId] = useState<string | null>(null);
  const [detail, setDetail] = useState<RAGArtifactDetail | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Version Comparison modal state
  const [comparisonModalOpen, setComparisonModalOpen] = useState<boolean>(false);
  const [comparisonResult, setComparisonResult] = useState<VersionComparisonResult | null>(null);
  const [comparingVersions, setComparingVersions] = useState<boolean>(false);

  // Phase 15: Evaluation Benchmark per Version state
  const [evaluationsByVersion, setEvaluationsByVersion] = useState<Record<string, EvaluationReportSummary[]>>({});
  const [evaluatingVersionId, setEvaluatingVersionId] = useState<string | null>(null);
  const [evalComparisonModalOpen, setEvalComparisonModalOpen] = useState<boolean>(false);
  const [evalComparisonResult, setEvalComparisonResult] = useState<VersionEvaluationComparisonResult | null>(null);
  const [comparingEvals, setComparingEvals] = useState<boolean>(false);

  // Deletion modal & progress state
  const [ragToDelete, setRagToDelete] = useState<{ ragId: string; name: string; referencingAgents?: AgentProfile[] } | null>(null);
  const [deletingRagId, setDeletingRagId] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const fetchArtifacts = async () => {
    setLoading(true);
    setError(null);
    try {
      const [list, rags] = await Promise.all([
        client.listArtifacts(),
        lifecycleClient.listRags().catch(() => []),
      ]);
      // Authoritative Account Isolation:
      // Filter discovered build artifacts so users only see builds associated with their own RAG records
      const ownedBuildIds = new Set<string>();
      rags.forEach((r) => {
        r.versions?.forEach((v) => {
          if (v.build_id) ownedBuildIds.add(v.build_id);
        });
      });
      const filteredArtifacts = list.filter((a) =>
        ownedBuildIds.has(a.build_id) ||
        rags.some((r) => r.rag_id === a.rag_id || r.rag_id === `rag_${a.build_id}`)
      );
      setArtifacts(filteredArtifacts);
      setRagRecords(rags);
    } catch (err: any) {
      setError(err?.message || 'Failed to discover RAG builds.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchArtifacts();
  }, []);

  const fetchVersionEvaluations = async (ragId: string, versionId: string) => {
    try {
      const reports = await EvaluationClient.getVersionReports(ragId, versionId);
      setEvaluationsByVersion((prev) => ({
        ...prev,
        [versionId]: reports,
      }));
    } catch (err: any) {
      console.warn(`Failed to fetch evaluations for version ${versionId}:`, err);
    }
  };

  const handleSelectBuild = async (buildId: string) => {
    setSelectedBuildId(buildId);
    try {
      const data = await client.getArtifactDetail(buildId);
      setDetail(data);

      // Load evaluations for versions of matching RAG
      const matchingRag = ragRecords.find((r) => r.versions.some((v) => v.build_id === buildId));
      if (matchingRag) {
        matchingRag.versions.forEach((v) => {
          fetchVersionEvaluations(matchingRag.rag_id, v.version_id);
        });
      }
    } catch (err: any) {
      console.error('Failed to load build detail:', err);
    }
  };

  const handleTriggerEvaluation = async (ragId: string, versionId: string) => {
    setEvaluatingVersionId(versionId);
    try {
      await EvaluationClient.triggerRun({
        rag_id: ragId,
        version_id: versionId,
        sample_size: 5,
      });
      alert(`Evaluation initiated for version ${versionId}. Benchmark running in background.`);
      // Refresh evaluations list after brief delay
      setTimeout(() => {
        fetchVersionEvaluations(ragId, versionId);
      }, 2000);
    } catch (err: any) {
      alert(`Evaluation failed: ${err.message || 'Unknown error'}`);
    } finally {
      setEvaluatingVersionId(null);
    }
  };

  const handleCompareEvaluations = async (ragId: string, baseEvalId: string, targetEvalId: string) => {
    setComparingEvals(true);
    try {
      const result = await EvaluationClient.compareVersionEvaluations(ragId, baseEvalId, targetEvalId);
      setEvalComparisonResult(result);
      setEvalComparisonModalOpen(true);
    } catch (err: any) {
      alert(`Evaluation comparison failed: ${err.message || 'Unknown error'}`);
    } finally {
      setComparingEvals(false);
    }
  };

  const handleRollback = async (ragId: string, targetVersionId: string) => {
    try {
      await lifecycleClient.rollbackVersion(ragId, targetVersionId);
      await fetchArtifacts();
      if (selectedBuildId) {
        await handleSelectBuild(selectedBuildId);
      }
    } catch (err: any) {
      alert(`Rollback failed: ${err.message}`);
    }
  };

  const handleCompare = async (ragId: string, baseVerId: string, targetVerId: string) => {
    setComparingVersions(true);
    try {
      const result = await lifecycleClient.compareVersions(ragId, baseVerId, targetVerId);
      setComparisonResult(result);
      setComparisonModalOpen(true);
    } catch (err: any) {
      alert(`Comparison failed: ${err.message}`);
    } finally {
      setComparingVersions(false);
    }
  };

  const promptDeleteRag = async (ragId: string, name: string) => {
    setDeleteError(null);
    try {
      const agents = await agentClient.listAgents().catch(() => []);
      const referencing = agents.filter((a) => a.attached_rag_ids && a.attached_rag_ids.includes(ragId));
      setRagToDelete({ ragId, name, referencingAgents: referencing });
    } catch {
      setRagToDelete({ ragId, name, referencingAgents: [] });
    }
  };

  const handleConfirmDelete = async () => {
    if (!ragToDelete) return;
    const { ragId } = ragToDelete;
    setDeletingRagId(ragId);
    setDeleteError(null);
    try {
      await lifecycleClient.deleteRag(ragId, true);
      // Clean up dependent conversations stored in localStorage (ragger.chat.v1)
      ConversationStore.removeConversationsForRag(ragId);
      setRagToDelete(null);
      if (selectedBuildId) {
        setSelectedBuildId(null);
        setDetail(null);
      }
      await fetchArtifacts();
    } catch (err: any) {
      const msg = err.message || 'Failed to delete RAG artifact.';
      setDeleteError(msg);
    } finally {
      setDeletingRagId(null);
    }
  };

  // ----------------------------------------------------
  // Detailed Knowledge Base View
  // ----------------------------------------------------
  if (selectedBuildId && detail) {
    const mainSource = detail.sources[0]?.filename || detail.build_id;
    return (
      <div style={{ padding: '32px 36px', maxWidth: 1280, margin: '0 auto', width: '100%', animation: 'pageSlideIn 300ms cubic-bezier(0.16, 1, 0.3, 1)' }}>
        <div style={{ marginBottom: 24 }}>
          <button
            onClick={() => {
              setSelectedBuildId(null);
              setDetail(null);
            }}
            className="btn-secondary"
            style={{ padding: '6px 12px', fontSize: 13, marginBottom: 16 }}
            id="btn-back-rag-library"
          >
            <ArrowLeft size={14} />
            <span>Back to RAG Library</span>
          </button>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4 }}>
                <h1 className="page-title" style={{ fontSize: 26, margin: 0 }}>
                  {mainSource}
                </h1>
                {detail.is_active && (
                  <span style={{ fontSize: 11, fontWeight: 700, padding: '3px 10px', borderRadius: 9999, background: '#ECFDF5', color: '#059669', display: 'flex', alignItems: 'center', gap: 4 }}>
                    <CheckCircle2 size={12} />
                    Active Retrieval Build
                  </span>
                )}
                <span style={{ fontSize: 11, fontWeight: 600, padding: '3px 8px', borderRadius: 6, background: '#F1F5F9', color: '#475569' }}>
                  {detail.build_id}
                </span>
              </div>
              <p className="page-subtitle">
                Immutable knowledge artifact compiled with {detail.approved_architecture.toUpperCase()} strategy
              </p>
            </div>

            <div style={{ display: 'flex', gap: 12 }}>
              <button
                onClick={() => {
                  const matchingRag = ragRecords.find((r) =>
                    r.versions.some((v) => v.build_id === detail.build_id) ||
                    r.rag_id === detail.rag_id ||
                    r.rag_id === (detail.build_id === 'bld_6f509ca2' ? 'rag_class10_english' : `rag_${detail.build_id}`)
                  );
                  const resolvedRagId = matchingRag?.rag_id || detail.rag_id;
                  onOpenChat(resolvedRagId);
                }}
                className="btn-primary"
                id="btn-details-chat"
              >
                <Bot size={16} />
                <span>Open in AI Agent</span>
              </button>
              <button
                onClick={() => onExportRagger(mainSource)}
                className="btn-secondary"
                id="btn-details-export"
              >
                <Download size={16} />
                <span>Export Package</span>
              </button>
              <button
                onClick={() => {
                  const matchingRag = ragRecords.find((r) =>
                    r.versions.some((v) => v.build_id === detail.build_id) ||
                    r.rag_id === detail.rag_id ||
                    r.rag_id === (detail.build_id === 'bld_6f509ca2' ? 'rag_class10_english' : `rag_${detail.build_id}`)
                  );
                  const resolvedRagId = matchingRag?.rag_id || detail.rag_id;
                  promptDeleteRag(resolvedRagId, mainSource);
                }}
                className="btn-secondary"
                style={{
                  color: '#DC2626',
                  borderColor: '#FECACA',
                  background: '#FEF2F2',
                }}
                id="btn-details-delete"
              >
                <Trash2 size={16} color="#DC2626" />
                <span>Delete</span>
              </button>
            </div>
          </div>
        </div>

        {/* Info Grid */}
        <div className="glass-card" style={{ padding: 24, marginBottom: 24 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 20 }}>
            <div>
              <span style={{ fontSize: 11, color: '#94A3B8', display: 'block', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Architecture
              </span>
              <span style={{ fontSize: 14, fontWeight: 700, color: '#0F172A', marginTop: 4, display: 'block' }}>
                {detail.approved_architecture}
              </span>
            </div>
            <div>
              <span style={{ fontSize: 11, color: '#94A3B8', display: 'block', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Indexed Units
              </span>
              <span style={{ fontSize: 14, fontWeight: 700, color: '#0F172A', marginTop: 4, display: 'block' }}>
                {detail.chunk_count} chunks ({detail.vector_count} vectors)
              </span>
            </div>
            <div>
              <span style={{ fontSize: 11, color: '#94A3B8', display: 'block', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Embedding Model
              </span>
              <span style={{ fontSize: 14, fontWeight: 700, color: '#0F172A', marginTop: 4, display: 'block' }}>
                {detail.embedding_model} ({detail.embedding_dimension}d)
              </span>
            </div>
            <div>
              <span style={{ fontSize: 11, color: '#94A3B8', display: 'block', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Vector Store
              </span>
              <span style={{ fontSize: 14, fontWeight: 700, color: '#0F172A', marginTop: 4, display: 'block' }}>
                {detail.vector_store.toUpperCase()}
              </span>
            </div>
          </div>
        </div>

        {/* Indexed Sources & Sample Chunks */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
          {/* Sources List */}
          <div className="glass-card" style={{ padding: 20 }}>
            <h3 style={{ fontSize: 16, fontWeight: 700, margin: '0 0 16px 0', display: 'flex', alignItems: 'center', gap: 8 }}>
              <FileText size={18} color="#2563EB" />
              <span>Provenance Sources ({detail.sources.length})</span>
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {detail.sources.map((src) => (
                <div
                  key={src.source_id}
                  style={{
                    padding: 12,
                    borderRadius: 8,
                    background: '#F8FAFC',
                    border: '1px solid #E2E8F0',
                  }}
                >
                  <div style={{ fontWeight: 600, fontSize: 13, color: '#0F172A', marginBottom: 4 }}>
                    {src.filename}
                  </div>
                  <div style={{ display: 'flex', gap: 12, fontSize: 11, color: '#64748B' }}>
                    <span>Format: {src.detected_format?.toUpperCase() || 'DOCUMENT'}</span>
                    {src.file_size_bytes && <span>Size: {(src.file_size_bytes / 1024 / 1024).toFixed(2)} MB</span>}
                  </div>
                  {src.sha256_checksum && (
                    <div style={{ fontSize: 10, color: '#94A3B8', marginTop: 4, fontFamily: 'monospace' }}>
                      SHA: {src.sha256_checksum.slice(0, 24)}...
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Sample Chunks Inspection (Read-Only, No LLM) */}
          <div className="glass-card" style={{ padding: 20 }}>
            <h3 style={{ fontSize: 16, fontWeight: 700, margin: '0 0 16px 0', display: 'flex', alignItems: 'center', gap: 8 }}>
              <Layers size={18} color="#059669" />
              <span>Sample Grounding Chunks (Inspection)</span>
            </h3>
            {detail.sample_chunks.length === 0 ? (
              <p style={{ fontSize: 13, color: '#64748B' }}>No sample chunks available in this build.</p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {detail.sample_chunks.map((chk) => (
                  <div
                    key={chk.chunk_id}
                    style={{
                      padding: 12,
                      borderRadius: 8,
                      background: '#F8FAFC',
                      border: '1px solid #E2E8F0',
                      fontSize: 12,
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                      <span style={{ fontWeight: 700, color: '#2563EB', fontFamily: 'monospace' }}>
                        {chk.chunk_id}
                      </span>
                      {chk.page_number && (
                        <span style={{ color: '#64748B', fontWeight: 600 }}>Page {chk.page_number}</span>
                      )}
                    </div>
                    <p style={{ margin: 0, color: '#334155', fontStyle: 'italic', lineHeight: 1.4 }}>
                      "{chk.snippet}"
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Phase 13: Version History, Rollback & Comparison Panel */}
        {(() => {
          // Look up corresponding RAG Artifact Record
          const matchingRag = ragRecords.find((r) =>
            r.versions.some((v) => v.build_id === detail.build_id) ||
            r.rag_id === (detail.build_id === 'bld_6f509ca2' ? 'rag_class10_english' : `rag_${detail.build_id}`)
          );

          if (!matchingRag) return null;

          return (
            <div className="glass-card" style={{ padding: 24, marginTop: 24, marginBottom: 24 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 18 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <GitBranch size={20} color="#2563EB" />
                  <div>
                    <h3 style={{ fontSize: 16, fontWeight: 700, margin: 0, color: '#0F172A' }}>
                      Version History & Lifecycle Management
                    </h3>
                    <span style={{ fontSize: 12, color: '#64748B' }}>
                      Target RAG: <strong style={{ color: '#0F172A', fontFamily: 'monospace' }}>{matchingRag.rag_id}</strong> (Active: {matchingRag.active_version_id || 'none'})
                    </span>
                  </div>
                </div>

                <div style={{ display: 'flex', gap: 10 }}>
                  {onBuildNewVersion && (
                    <button
                      onClick={() => onBuildNewVersion(matchingRag.rag_id)}
                      className="btn-primary"
                      style={{ padding: '7px 14px', fontSize: 12 }}
                      id="btn-build-new-version"
                    >
                      <GitBranch size={13} />
                      <span>Build New Version</span>
                    </button>
                  )}
                  {matchingRag.versions.length >= 2 && (
                    <button
                      onClick={() => {
                        handleCompare(matchingRag.rag_id, matchingRag.versions[0].version_id, matchingRag.versions[matchingRag.versions.length - 1].version_id);
                      }}
                      className="btn-secondary"
                      style={{ padding: '7px 14px', fontSize: 12 }}
                      id="btn-compare-versions"
                      disabled={comparingVersions}
                    >
                      <GitCompare size={13} />
                      <span>Compare Versions</span>
                    </button>
                  )}
                  {(() => {
                    // Check if at least two versions have evaluations
                    const versionsWithEvals = matchingRag.versions.filter((v) => (evaluationsByVersion[v.version_id] || []).length > 0);
                    if (versionsWithEvals.length >= 2) {
                      const baseEval = evaluationsByVersion[versionsWithEvals[0].version_id][0].eval_id;
                      const targetEval = evaluationsByVersion[versionsWithEvals[1].version_id][0].eval_id;
                      return (
                        <button
                          onClick={() => handleCompareEvaluations(matchingRag.rag_id, baseEval, targetEval)}
                          className="btn-secondary"
                          style={{ padding: '7px 14px', fontSize: 12, display: 'inline-flex', alignItems: 'center', gap: 6 }}
                          id="btn-compare-evaluations"
                          disabled={comparingEvals}
                          title="Factual benchmark comparison between version evaluations"
                        >
                          <Scale size={13} color="#2563EB" />
                          <span>Compare Evaluations</span>
                        </button>
                      );
                    }
                    return null;
                  })()}
                </div>
              </div>

              {/* Version Table */}
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                <thead>
                  <tr style={{ textAlign: 'left', borderBottom: '1px solid #E2E8F0', color: '#64748B' }}>
                    <th style={{ padding: '8px 12px' }}>Version Tag</th>
                    <th style={{ padding: '8px 12px' }}>Version ID</th>
                    <th style={{ padding: '8px 12px' }}>Build ID</th>
                    <th style={{ padding: '8px 12px' }}>Chunks</th>
                    <th style={{ padding: '8px 12px' }}>Vectors</th>
                    <th style={{ padding: '8px 12px' }}>Quality Score</th>
                    <th style={{ padding: '8px 12px' }}>Status</th>
                    <th style={{ padding: '8px 12px', textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {matchingRag.versions.map((ver) => {
                    const isActive = ver.version_id === matchingRag.active_version_id;
                    const versionReports = evaluationsByVersion[ver.version_id] || [];
                    const latestReport = versionReports.length > 0 ? versionReports[0] : null;

                    return (
                      <tr key={ver.version_id} style={{ borderBottom: '1px solid #F1F5F9' }}>
                        <td style={{ padding: '10px 12px', fontWeight: 700, color: '#0F172A' }}>
                          {ver.version_tag}
                        </td>
                        <td style={{ padding: '10px 12px', fontFamily: 'monospace', fontSize: 12, color: '#64748B' }}>
                          {ver.version_id}
                        </td>
                        <td style={{ padding: '10px 12px', fontFamily: 'monospace', fontSize: 12, color: '#2563EB' }}>
                          {ver.build_id}
                        </td>
                        <td style={{ padding: '10px 12px', color: '#0F172A' }}>
                          {ver.chunk_count}
                        </td>
                        <td style={{ padding: '10px 12px', color: '#0F172A' }}>
                          {ver.vector_count}
                        </td>
                        <td style={{ padding: '10px 12px' }}>
                          {latestReport ? (
                            <span
                              style={{
                                fontSize: 12,
                                fontWeight: 700,
                                padding: '3px 8px',
                                borderRadius: 6,
                                background: '#EFF6FF',
                                color: '#1D4ED8',
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: 4,
                                border: '1px solid #BFDBFE',
                              }}
                              title={`Evaluation ID: ${latestReport.eval_id} | Completed: ${latestReport.completed_at}`}
                            >
                              <Award size={12} color="#2563EB" />
                              <span>Quality Score: {latestReport.quality_score.toFixed(1)}</span>
                            </span>
                          ) : (
                            <span style={{ fontSize: 11, color: '#94A3B8' }}>Not evaluated</span>
                          )}
                        </td>
                        <td style={{ padding: '10px 12px' }}>
                          {isActive ? (
                            <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 9999, background: '#ECFDF5', color: '#059669', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                              <CheckCircle2 size={11} />
                              Active
                            </span>
                          ) : (
                            <span style={{ fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 9999, background: '#F1F5F9', color: '#64748B' }}>
                              Inactive
                            </span>
                          )}
                        </td>
                        <td style={{ padding: '10px 12px', textAlign: 'right' }}>
                          <div style={{ display: 'inline-flex', gap: 6 }}>
                            <button
                              onClick={() => handleTriggerEvaluation(matchingRag.rag_id, ver.version_id)}
                              className="btn-secondary"
                              style={{ padding: '4px 8px', fontSize: 11, display: 'inline-flex', alignItems: 'center', gap: 4 }}
                              title="Run automated evaluation benchmark on this specific version"
                              disabled={evaluatingVersionId === ver.version_id}
                            >
                              <Play size={10} className={evaluatingVersionId === ver.version_id ? 'animate-spin' : ''} />
                              <span>{evaluatingVersionId === ver.version_id ? 'Evaluating...' : 'Evaluate'}</span>
                            </button>
                            {!isActive && (
                              <button
                                onClick={() => handleRollback(matchingRag.rag_id, ver.version_id)}
                                className="btn-secondary"
                                style={{ padding: '4px 10px', fontSize: 11, display: 'inline-flex', alignItems: 'center', gap: 4 }}
                                title="Roll back active pointer to this version"
                              >
                                <RotateCcw size={11} />
                                <span>Rollback</span>
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          );
        })()}
      </div>
    );
  }

  // ----------------------------------------------------
  // Primary RAG Library Grid View
  // ----------------------------------------------------
  return (
    <div style={{ padding: '32px 36px', maxWidth: 1280, margin: '0 auto', width: '100%', animation: 'pageSlideIn 300ms cubic-bezier(0.16, 1, 0.3, 1)' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 28 }}>
        <div>
          <h1 className="page-title">RAG Knowledge Library</h1>
          <p className="page-subtitle">
            Discovered knowledge builds and vector indexes available for attachment to AI agents
          </p>
        </div>

        <div style={{ display: 'flex', gap: 12 }}>
          <button
            onClick={fetchArtifacts}
            className="btn-secondary"
            style={{ padding: '8px 14px' }}
            disabled={loading}
          >
            <RefreshCw size={15} className={loading ? 'animate-spin' : ''} />
            <span>Scan Builds</span>
          </button>
          <button onClick={onCreateNew} className="btn-primary" id="btn-create-rag">
            <BookOpen size={16} />
            <span>Compile New RAG</span>
          </button>
        </div>
      </div>

      {error && (
        <div style={{ padding: 16, borderRadius: 8, background: '#FEF2F2', border: '1px solid #F87171', color: '#991B1B', marginBottom: 20 }}>
          {error}
        </div>
      )}

      {loading ? (
        <div style={{ padding: 48, textAlign: 'center', color: '#64748B' }}>
          <RefreshCw size={24} className="animate-spin" style={{ margin: '0 auto 12px' }} />
          <p>Discovering compiled RAG builds in workspace...</p>
        </div>
      ) : artifacts.length === 0 ? (
        <div className="glass-card" style={{ padding: 48, textAlign: 'center' }}>
          <Database size={40} color="#94A3B8" style={{ margin: '0 auto 16px' }} />
          <h3 style={{ fontSize: 18, fontWeight: 700, margin: '0 0 8px 0', color: '#0F172A' }}>
            No Knowledge Builds Found
          </h3>
          <p style={{ color: '#64748B', maxWidth: 460, margin: '0 auto 20px', fontSize: 14 }}>
            You haven't compiled any RAG knowledge artifacts yet. Head to RAG Projects to upload documents and build an index.
          </p>
          <button onClick={onCreateNew} className="btn-primary">
            <span>Create First RAG Build</span>
          </button>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: 20 }}>
          {artifacts.map((artifact) => {
            const primaryName = artifact.sources[0]?.filename || artifact.build_id;
            return (
              <div
                key={artifact.build_id}
                className="glass-card"
                style={{
                  padding: 24,
                  display: 'flex',
                  flexDirection: 'column',
                  justifyContent: 'space-between',
                  border: artifact.is_active ? '2px solid #2563EB' : '1px solid #E2E8F0',
                  position: 'relative',
                }}
              >
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
                    <div>
                      <h3 style={{ fontSize: 17, fontWeight: 700, color: '#0F172A', margin: '0 0 4px 0' }}>
                        {primaryName}
                      </h3>
                      <span style={{ fontSize: 11, color: '#64748B', fontFamily: 'monospace' }}>
                        {artifact.build_id}
                      </span>
                    </div>
                    {artifact.is_active && (
                      <span style={{ fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 9999, background: '#EFF6FF', color: '#1D4ED8' }}>
                        Active Default
                      </span>
                    )}
                  </div>

                  <p style={{ fontSize: 13, color: '#475569', margin: '0 0 16px 0' }}>
                    Strategy: <strong style={{ color: '#0F172A' }}>{artifact.approved_architecture}</strong>
                  </p>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, padding: 12, background: '#F8FAFC', borderRadius: 8, marginBottom: 16 }}>
                    <div>
                      <span style={{ fontSize: 10, color: '#94A3B8', textTransform: 'uppercase', display: 'block' }}>
                        Chunks / Vectors
                      </span>
                      <span style={{ fontSize: 13, fontWeight: 700, color: '#0F172A' }}>
                        {artifact.chunk_count} units
                      </span>
                    </div>
                    <div>
                      <span style={{ fontSize: 10, color: '#94A3B8', textTransform: 'uppercase', display: 'block' }}>
                        Embed Model
                      </span>
                      <span style={{ fontSize: 12, fontWeight: 600, color: '#0F172A' }}>
                        {artifact.embedding_model}
                      </span>
                    </div>
                  </div>
                </div>

                <div style={{ display: 'flex', gap: 10, marginTop: 12 }}>
                  <button
                    onClick={() => handleSelectBuild(artifact.build_id)}
                    className="btn-secondary"
                    style={{ flex: 1, padding: '8px 12px', fontSize: 13 }}
                  >
                    <span>Inspect</span>
                  </button>
                  <button
                    onClick={() => {
                      const matchingRag = ragRecords.find((r) =>
                        r.versions.some((v) => v.build_id === artifact.build_id) ||
                        r.rag_id === artifact.rag_id ||
                        r.rag_id === (artifact.build_id === 'bld_6f509ca2' ? 'rag_class10_english' : `rag_${artifact.build_id}`)
                      );
                      const resolvedRagId = matchingRag?.rag_id || artifact.rag_id;
                      onOpenChat(resolvedRagId);
                    }}
                    className="btn-primary"
                    style={{ flex: 1, padding: '8px 12px', fontSize: 13 }}
                  >
                    <Bot size={15} />
                    <span>Chat</span>
                  </button>
                  <button
                    onClick={() => {
                      const matchingRag = ragRecords.find((r) =>
                        r.versions.some((v) => v.build_id === artifact.build_id) ||
                        r.rag_id === artifact.rag_id ||
                        r.rag_id === (artifact.build_id === 'bld_6f509ca2' ? 'rag_class10_english' : `rag_${artifact.build_id}`)
                      );
                      const resolvedRagId = matchingRag?.rag_id || artifact.rag_id;
                      promptDeleteRag(resolvedRagId, primaryName);
                    }}
                    disabled={deletingRagId === (artifact.rag_id || artifact.build_id)}
                    className="btn-secondary"
                    style={{
                      padding: '8px 10px',
                      fontSize: 13,
                      color: '#DC2626',
                      borderColor: '#FECACA',
                      background: '#FEF2F2',
                      cursor: deletingRagId ? 'not-allowed' : 'pointer',
                    }}
                    title="Delete RAG"
                    id={`btn-delete-${artifact.build_id}`}
                  >
                    <Trash2 size={15} color="#DC2626" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
      {/* Phase 13: Descriptive Version Comparison Modal */}
      {comparisonModalOpen && comparisonResult && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15, 23, 42, 0.6)',
            backdropFilter: 'blur(4px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: 20,
          }}
          onClick={() => setComparisonModalOpen(false)}
        >
          <div
            className="glass-card"
            style={{
              background: '#FFFFFF',
              borderRadius: 16,
              maxWidth: 720,
              width: '100%',
              padding: 28,
              maxHeight: '85vh',
              overflowY: 'auto',
              boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <GitCompare size={22} color="#2563EB" />
                <h2 style={{ fontSize: 20, fontWeight: 800, margin: 0, color: '#0F172A' }}>
                  Version Comparison (Objective Deltas)
                </h2>
              </div>
              <button
                onClick={() => setComparisonModalOpen(false)}
                style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#94A3B8' }}
              >
                <X size={20} />
              </button>
            </div>

            <div style={{ fontSize: 13, color: '#64748B', marginBottom: 20 }}>
              Target RAG: <strong style={{ color: '#0F172A', fontFamily: 'monospace' }}>{comparisonResult.rag_id}</strong> &nbsp;|&nbsp;
              Comparing <strong style={{ color: '#2563EB' }}>{comparisonResult.base_version_tag}</strong> ({comparisonResult.base_version_id}) vs <strong style={{ color: '#059669' }}>{comparisonResult.target_version_tag}</strong> ({comparisonResult.target_version_id})
            </div>

            {/* Metrics Delta Table */}
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, marginBottom: 24 }}>
              <thead>
                <tr style={{ textAlign: 'left', borderBottom: '2px solid #E2E8F0', color: '#64748B' }}>
                  <th style={{ padding: '8px 12px' }}>Property</th>
                  <th style={{ padding: '8px 12px' }}>{comparisonResult.base_version_tag} (Base)</th>
                  <th style={{ padding: '8px 12px' }}>{comparisonResult.target_version_tag} (Target)</th>
                  <th style={{ padding: '8px 12px', textAlign: 'right' }}>Factual Delta</th>
                </tr>
              </thead>
              <tbody>
                <tr style={{ borderBottom: '1px solid #F1F5F9' }}>
                  <td style={{ padding: '10px 12px', fontWeight: 600, color: '#334155' }}>Chunks Count</td>
                  <td style={{ padding: '10px 12px' }}>{comparisonResult.base.chunk_count}</td>
                  <td style={{ padding: '10px 12px' }}>{comparisonResult.target.chunk_count}</td>
                  <td style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 700, color: comparisonResult.chunk_count_delta >= 0 ? '#059669' : '#DC2626' }}>
                    {comparisonResult.chunk_count_delta >= 0 ? `+${comparisonResult.chunk_count_delta}` : comparisonResult.chunk_count_delta}
                  </td>
                </tr>
                <tr style={{ borderBottom: '1px solid #F1F5F9' }}>
                  <td style={{ padding: '10px 12px', fontWeight: 600, color: '#334155' }}>Vectors Count</td>
                  <td style={{ padding: '10px 12px' }}>{comparisonResult.base.vector_count}</td>
                  <td style={{ padding: '10px 12px' }}>{comparisonResult.target.vector_count}</td>
                  <td style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 700, color: comparisonResult.vector_count_delta >= 0 ? '#059669' : '#DC2626' }}>
                    {comparisonResult.vector_count_delta >= 0 ? `+${comparisonResult.vector_count_delta}` : comparisonResult.vector_count_delta}
                  </td>
                </tr>
                <tr style={{ borderBottom: '1px solid #F1F5F9' }}>
                  <td style={{ padding: '10px 12px', fontWeight: 600, color: '#334155' }}>Sources Count</td>
                  <td style={{ padding: '10px 12px' }}>{comparisonResult.base.sources_count}</td>
                  <td style={{ padding: '10px 12px' }}>{comparisonResult.target.sources_count}</td>
                  <td style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 700, color: comparisonResult.sources_count_delta >= 0 ? '#059669' : '#DC2626' }}>
                    {comparisonResult.sources_count_delta >= 0 ? `+${comparisonResult.sources_count_delta}` : comparisonResult.sources_count_delta}
                  </td>
                </tr>
                <tr style={{ borderBottom: '1px solid #F1F5F9' }}>
                  <td style={{ padding: '10px 12px', fontWeight: 600, color: '#334155' }}>Embedding Model</td>
                  <td style={{ padding: '10px 12px', fontSize: 12 }}>{comparisonResult.base.embedding_model || 'N/A'}</td>
                  <td style={{ padding: '10px 12px', fontSize: 12 }}>{comparisonResult.target.embedding_model || 'N/A'}</td>
                  <td style={{ padding: '10px 12px', textAlign: 'right', fontSize: 12, color: comparisonResult.embedding_model_changed ? '#D97706' : '#64748B' }}>
                    {comparisonResult.embedding_model_changed ? 'Modified' : 'Unchanged'}
                  </td>
                </tr>
                <tr style={{ borderBottom: '1px solid #F1F5F9' }}>
                  <td style={{ padding: '10px 12px', fontWeight: 600, color: '#334155' }}>Manifest Hash</td>
                  <td style={{ padding: '10px 12px', fontFamily: 'monospace', fontSize: 11 }}>{comparisonResult.base.manifest_hash.slice(0, 16)}...</td>
                  <td style={{ padding: '10px 12px', fontFamily: 'monospace', fontSize: 11 }}>{comparisonResult.target.manifest_hash.slice(0, 16)}...</td>
                  <td style={{ padding: '10px 12px', textAlign: 'right', fontSize: 12, color: comparisonResult.manifest_hash_changed ? '#2563EB' : '#64748B' }}>
                    {comparisonResult.manifest_hash_changed ? 'Changed' : 'Identical'}
                  </td>
                </tr>
              </tbody>
            </table>

            {/* Source Delta Lists */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 14 }}>
              <div style={{ padding: 12, borderRadius: 8, background: '#F8FAFC', border: '1px solid #E2E8F0' }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: '#059669', textTransform: 'uppercase', display: 'block', marginBottom: 6 }}>
                  Added Sources ({comparisonResult.sources_added.length})
                </span>
                {comparisonResult.sources_added.length === 0 ? (
                  <span style={{ fontSize: 12, color: '#94A3B8' }}>None</span>
                ) : (
                  comparisonResult.sources_added.map((s) => (
                    <div key={s} style={{ fontSize: 12, color: '#0F172A', fontFamily: 'monospace' }}>+{s}</div>
                  ))
                )}
              </div>
              <div style={{ padding: 12, borderRadius: 8, background: '#F8FAFC', border: '1px solid #E2E8F0' }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: '#DC2626', textTransform: 'uppercase', display: 'block', marginBottom: 6 }}>
                  Removed Sources ({comparisonResult.sources_removed.length})
                </span>
                {comparisonResult.sources_removed.length === 0 ? (
                  <span style={{ fontSize: 12, color: '#94A3B8' }}>None</span>
                ) : (
                  comparisonResult.sources_removed.map((s) => (
                    <div key={s} style={{ fontSize: 12, color: '#0F172A', fontFamily: 'monospace' }}>-{s}</div>
                  ))
                )}
              </div>
              <div style={{ padding: 12, borderRadius: 8, background: '#F8FAFC', border: '1px solid #E2E8F0' }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: '#475569', textTransform: 'uppercase', display: 'block', marginBottom: 6 }}>
                  Retained Sources ({comparisonResult.sources_retained.length})
                </span>
                {comparisonResult.sources_retained.length === 0 ? (
                  <span style={{ fontSize: 12, color: '#94A3B8' }}>None</span>
                ) : (
                  comparisonResult.sources_retained.map((s) => (
                    <div key={s} style={{ fontSize: 12, color: '#64748B', fontFamily: 'monospace' }}>{s}</div>
                  ))
                )}
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 24 }}>
              <button
                onClick={() => setComparisonModalOpen(false)}
                className="btn-primary"
                style={{ padding: '8px 20px', fontSize: 13 }}
              >
                Close Comparison
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Phase 15: Factual Version Evaluation Comparison Modal */}
      {evalComparisonModalOpen && evalComparisonResult && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15, 23, 42, 0.6)',
            backdropFilter: 'blur(4px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: 20,
          }}
          onClick={() => setEvalComparisonModalOpen(false)}
        >
          <div
            className="glass-card"
            style={{
              background: '#FFFFFF',
              borderRadius: 16,
              maxWidth: 760,
              width: '100%',
              padding: 28,
              maxHeight: '85vh',
              overflowY: 'auto',
              boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <Award size={22} color="#2563EB" />
                <h2 style={{ fontSize: 20, fontWeight: 800, margin: 0, color: '#0F172A' }}>
                  Evaluation Benchmark Comparison (Factual Metrics)
                </h2>
              </div>
              <button
                onClick={() => setEvalComparisonModalOpen(false)}
                style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: '#94A3B8' }}
              >
                <X size={20} />
              </button>
            </div>

            <div style={{ fontSize: 13, color: '#64748B', marginBottom: 20 }}>
              Target RAG: <strong style={{ color: '#0F172A', fontFamily: 'monospace' }}>{evalComparisonResult.rag_id}</strong> &nbsp;|&nbsp;
              Comparing <strong style={{ color: '#2563EB' }}>{evalComparisonResult.base_version_tag || 'Base'}</strong> ({evalComparisonResult.base_build_id}) vs <strong style={{ color: '#059669' }}>{evalComparisonResult.target_version_tag || 'Target'}</strong> ({evalComparisonResult.target_build_id})
            </div>

            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13, marginBottom: 24 }}>
              <thead>
                <tr style={{ textAlign: 'left', borderBottom: '2px solid #E2E8F0', color: '#64748B' }}>
                  <th style={{ padding: '8px 12px' }}>Benchmark Metric</th>
                  <th style={{ padding: '8px 12px' }}>{evalComparisonResult.base_version_tag || 'Base'}</th>
                  <th style={{ padding: '8px 12px' }}>{evalComparisonResult.target_version_tag || 'Target'}</th>
                  <th style={{ padding: '8px 12px', textAlign: 'right' }}>Factual Delta</th>
                </tr>
              </thead>
              <tbody>
                {[
                  { name: 'Quality Score', item: evalComparisonResult.quality_score_delta, isScore: true },
                  { name: 'Hits@1', item: evalComparisonResult.hits_at_1_delta },
                  { name: 'Hits@3', item: evalComparisonResult.hits_at_3_delta },
                  { name: 'Hits@5', item: evalComparisonResult.hits_at_5_delta },
                  { name: 'Mean Reciprocal Rank (MRR)', item: evalComparisonResult.mrr_delta },
                  { name: 'Source Coverage', item: evalComparisonResult.source_coverage_delta },
                  { name: 'Citation Precision', item: evalComparisonResult.citation_precision_delta },
                  { name: 'Faithfulness (Judge)', item: evalComparisonResult.faithfulness_delta },
                  { name: 'Disclaimer Accuracy', item: evalComparisonResult.disclaimer_accuracy_delta },
                ].map(({ name, item, isScore }) => {
                  const baseStr = item.base_value !== null && item.base_value !== undefined ? (isScore ? item.base_value.toFixed(1) : item.base_value.toFixed(3)) : 'N/A';
                  const targetStr = item.target_value !== null && item.target_value !== undefined ? (isScore ? item.target_value.toFixed(1) : item.target_value.toFixed(3)) : 'N/A';
                  const deltaVal = item.delta;
                  const deltaStr = deltaVal !== null && deltaVal !== undefined
                    ? `${deltaVal >= 0 ? '+' : ''}${isScore ? deltaVal.toFixed(1) : deltaVal.toFixed(3)}`
                    : 'N/A';

                  return (
                    <tr key={name} style={{ borderBottom: '1px solid #F1F5F9' }}>
                      <td style={{ padding: '10px 12px', fontWeight: 600, color: '#334155' }}>{name}</td>
                      <td style={{ padding: '10px 12px' }}>{baseStr}</td>
                      <td style={{ padding: '10px 12px' }}>{targetStr}</td>
                      <td style={{ padding: '10px 12px', textAlign: 'right', fontWeight: 700, fontFamily: 'monospace', color: deltaVal !== null && deltaVal !== undefined && deltaVal >= 0 ? '#059669' : '#DC2626' }}>
                        {deltaStr}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>

            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 24 }}>
              <button
                onClick={() => setEvalComparisonModalOpen(false)}
                className="btn-primary"
                style={{ padding: '8px 20px', fontSize: 13 }}
              >
                Close Comparison
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Dialog */}
      {ragToDelete && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15, 23, 42, 0.6)',
            backdropFilter: 'blur(4px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1100,
            padding: 20,
          }}
          onClick={() => {
            if (!deletingRagId) {
              setRagToDelete(null);
              setDeleteError(null);
            }
          }}
        >
          <div
            className="glass-card"
            style={{
              background: '#FFFFFF',
              borderRadius: 16,
              maxWidth: 480,
              width: '100%',
              padding: 28,
              boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1)',
            }}
            onClick={(e) => e.stopPropagation()}
            id="modal-delete-confirmation"
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
              <div
                style={{
                  width: 44,
                  height: 44,
                  borderRadius: 12,
                  background: '#FEE2E2',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                }}
              >
                <AlertTriangle size={24} color="#DC2626" />
              </div>
              <div>
                <h3 style={{ fontSize: 18, fontWeight: 700, margin: 0, color: '#0F172A' }}>
                  Delete RAG Knowledge Base?
                </h3>
                <span style={{ fontSize: 12, color: '#64748B', fontFamily: 'monospace' }}>
                  {ragToDelete.ragId}
                </span>
              </div>
            </div>

            {ragToDelete.referencingAgents && ragToDelete.referencingAgents.length > 0 ? (
              <div style={{ fontSize: 14, color: '#475569', lineHeight: 1.5, margin: '0 0 16px 0' }}>
                <p style={{ margin: '0 0 12px 0' }}>
                  <strong style={{ color: '#0F172A' }}>{ragToDelete.name}</strong> is currently attached to{' '}
                  <strong style={{ color: '#0F172A' }}>{ragToDelete.referencingAgents.length} AI Agent{ragToDelete.referencingAgents.length > 1 ? 's' : ''}</strong>
                  {ragToDelete.referencingAgents.map(a => ` (${a.name})`).join('')}.
                </p>
                <div
                  style={{
                    background: '#F8FAFC',
                    border: '1px solid #E2E8F0',
                    borderRadius: 8,
                    padding: '12px 14px',
                    marginBottom: 12,
                    fontSize: 13,
                    color: '#334155',
                  }}
                >
                  <div style={{ fontWeight: 600, marginBottom: 6, color: '#0F172A' }}>
                    Deleting this RAG will:
                  </div>
                  <ul style={{ margin: 0, paddingLeft: 18, lineHeight: 1.6 }}>
                    <li>Remove it from the attached Agent{ragToDelete.referencingAgents.length > 1 ? 's' : ''}</li>
                    <li>Remove it from your RAG Knowledge Library</li>
                    <li>Delete its associated RAG index and data</li>
                  </ul>
                </div>
                <p style={{ margin: 0, fontSize: 13, color: '#DC2626', fontWeight: 500 }}>
                  This action cannot be undone.
                </p>
              </div>
            ) : (
              <p style={{ fontSize: 14, color: '#475569', lineHeight: 1.5, margin: '0 0 16px 0' }}>
                Are you sure you want to delete <strong style={{ color: '#0F172A' }}>{ragToDelete.name}</strong>?
                This will permanently remove this RAG from your knowledge library.
              </p>
            )}

            {deleteError && (
              <div
                style={{
                  padding: 12,
                  borderRadius: 8,
                  background: '#FEF2F2',
                  border: '1px solid #FCA5A5',
                  color: '#B91C1C',
                  fontSize: 13,
                  lineHeight: 1.4,
                  marginBottom: 16,
                  display: 'flex',
                  alignItems: 'flex-start',
                  gap: 8,
                }}
                id="delete-error-banner"
              >
                <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: 2 }} />
                <div>
                  <div style={{ fontWeight: 600 }}>Error Deleting RAG</div>
                  <div>{deleteError}</div>
                </div>
              </div>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, marginTop: 20 }}>
              <button
                type="button"
                onClick={() => {
                  setRagToDelete(null);
                  setDeleteError(null);
                }}
                disabled={Boolean(deletingRagId)}
                className="btn-secondary"
                style={{ padding: '9px 18px', fontSize: 13 }}
                id="btn-cancel-delete"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirmDelete}
                disabled={Boolean(deletingRagId)}
                className="btn-primary"
                style={{
                  padding: '9px 18px',
                  fontSize: 13,
                  background: '#DC2626',
                  borderColor: '#DC2626',
                  color: '#FFFFFF',
                  opacity: deletingRagId ? 0.7 : 1,
                  cursor: deletingRagId ? 'not-allowed' : 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                }}
                id="btn-confirm-delete"
              >
                {deletingRagId ? (
                  <>
                    <RefreshCw size={14} className="spin" />
                    <span>Deleting...</span>
                  </>
                ) : (
                  <>
                    <Trash2 size={14} />
                    <span>Delete RAG</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
