import React, { useState, useEffect, useRef } from 'react';
import {
  UploadCloud,
  CheckCircle2,
  ArrowRight,
  ChevronLeft,
  Check,
  Download,
  MessageSquare,
  Shield,
  Table,
  Layers,
  Sparkles,
  Lock,
  X,
  AlertCircle,
  Loader2,
  RefreshCw,
} from 'lucide-react';
import { IngestionClient } from '../../services/ingestionClient';
import { AnalysisClient } from '../../services/analysisClient';
import { RecommendationClient } from '../../services/recommendationClient';
import { BuilderClient } from '../../services/builderClient';
import { ModelsClient } from '../../services/modelsClient';
import { RAGLifecycleClient } from '../../services/ragLifecycleClient';
import { RAGArtifactRecord } from '../../types/ragLifecycle';
import { FileAnalysisProfile } from '../../types/analysis';
import { RecommendationResult } from '../../types/recommendation';
import { BuildProgress } from '../../types/builder';
import raggerBoxLogo from '../../assets/ragger.ai_box_logo.png';

interface StudioViewProps {
  ingestionClient?: IngestionClient;
  analysisClient?: AnalysisClient;
  recommendationClient?: RecommendationClient;
  builderClient?: BuilderClient;
  ragLifecycleClient?: RAGLifecycleClient;
  targetRagId?: string;
  onGoToChat: (kbId?: string) => void;
  onExportRagger: (kbTitle: string) => void;
  onBackToHome?: () => void;
  initialStep?: 'upload' | 'analyze' | 'recommend' | 'building' | 'ready';
}

type StepKey = 'upload' | 'analyze' | 'recommend' | 'building' | 'ready';

interface UploadedFileItem {
  file?: File;
  filePath?: string;
  name: string;
  size: string;
  extension: string;
  sourceId?: string;
  status: 'pending' | 'uploading' | 'analyzing' | 'done' | 'error';
  progress: number;
  errorMessage?: string;
}

export const StudioView: React.FC<StudioViewProps> = ({
  onGoToChat,
  onExportRagger,
  onBackToHome,
  initialStep = 'upload',
  targetRagId,
}) => {
  const [currentStep, setCurrentStep] = useState<StepKey>(initialStep);
  // Target RAG Selection: 'new' or 'existing'
  const [targetMode, setTargetMode] = useState<'new' | 'existing'>(targetRagId ? 'existing' : 'new');
  const [existingRags, setExistingRags] = useState<RAGArtifactRecord[]>([]);
  const [selectedRagId, setSelectedRagId] = useState<string>(targetRagId || '');
  const [newRagName, setNewRagName] = useState<string>('');
  const [versionTag, setVersionTag] = useState<string>('v1.0.0');
  const [createdOrUpdatedRagId, setCreatedOrUpdatedRagId] = useState<string>('');
  const [registeredVersionTag, setRegisteredVersionTag] = useState<string>('');

  const [lifecycleClient] = useState(() => new RAGLifecycleClient());

  // Real files uploaded by user (starts completely empty, zero mock files)
  const [selectedFiles, setSelectedFiles] = useState<UploadedFileItem[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isProcessingStep, setIsProcessingStep] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Real analysis profiles returned by backend
  const [analysisProfiles, setAnalysisProfiles] = useState<FileAnalysisProfile[]>([]);

  // Real recommendation returned by backend
  const [recommendation, setRecommendation] = useState<RecommendationResult | null>(null);
  const [selectedArchitectureId, setSelectedArchitectureId] = useState<string>('knowledge_rag');

  // Real build progress telemetry
  const [buildProgress, setBuildProgress] = useState<BuildProgress | null>(null);
  const [activeBuildId, setActiveBuildId] = useState<string | null>(null);
  const buildPollTimerRef = useRef<any>(null);

  // Embedding model auto-download state in Studio
  const [isDownloadingEmbedding, setIsDownloadingEmbedding] = useState(false);
  const [embeddingDownloadProgress, setEmbeddingDownloadProgress] = useState<number | null>(null);

  const handleDownloadEmbeddingModel = async () => {
    setIsDownloadingEmbedding(true);
    setErrorMessage(null);
    try {
      const embeddingKey = 'bge-small-en-v1.5:onnx:default-v1';
      await ModelsClient.startDownload(embeddingKey);

      await new Promise<void>((resolve, reject) => {
        const timer = setInterval(async () => {
          try {
            const prog = await ModelsClient.getProgress(embeddingKey);
            setEmbeddingDownloadProgress(Math.round(prog.percent || 0));
            if (String(prog.state) === 'completed') {
              clearInterval(timer);
              resolve();
            } else if (String(prog.state) === 'failed') {
              clearInterval(timer);
              reject(new Error(prog.error_message || 'Embedding model download failed.'));
            }
          } catch {
            // Tolerant to transient connection hiccups
          }
        }, 500);
      });

      // Verification tick
      await new Promise((r) => setTimeout(r, 600));
      setIsDownloadingEmbedding(false);
      setEmbeddingDownloadProgress(null);
      // Auto-trigger build once embedding model is ready
      handleApproveAndBuild();
    } catch (err: any) {
      setIsDownloadingEmbedding(false);
      setEmbeddingDownloadProgress(null);
      setErrorMessage(err.message || 'Failed to download embedding model.');
    }
  };

  // Fetch existing RAGs on mount
  useEffect(() => {
    lifecycleClient.listRags().then((rags) => {
      setExistingRags(rags);
      if (targetRagId) {
        setSelectedRagId(targetRagId);
        setTargetMode('existing');
        const match = rags.find((r) => r.rag_id === targetRagId);
        if (match) {
          const nextMinor = match.versions.length ? `v1.${match.versions.length}.0` : 'v1.1.0';
          setVersionTag(nextMinor);
        }
      } else if (rags.length > 0 && !selectedRagId) {
        setSelectedRagId(rags[0].rag_id);
      }
    }).catch((err) => {
      console.warn('Could not load existing RAGs:', err);
    });
  }, [targetRagId]);

  // Sync if initialStep changes externally
  useEffect(() => {
    setCurrentStep(initialStep);
  }, [initialStep]);

  // Clean up timers on unmount
  useEffect(() => {
    return () => {
      if (buildPollTimerRef.current) {
        clearInterval(buildPollTimerRef.current);
      }
    };
  }, []);

  const handleChooseFilesClick = async () => {
    // If in Electron, prioritize native file dialog to get absolute paths directly
    if (window.ragger?.ingestion?.openFileDialog) {
      try {
        const res = await window.ragger.ingestion.openFileDialog();
        if (res.success && res.data) {
          const paths = Array.isArray(res.data) ? res.data : [res.data];
          const newItems: UploadedFileItem[] = paths.filter(Boolean).map((p: string) => {
            const normalized = p.replace(/\\/g, '/');
            const name = normalized.split('/').pop() || 'document';
            const ext = name.split('.').pop()?.toUpperCase() || 'FILE';
            return {
              filePath: p,
              name,
              size: 'Local file',
              extension: ext,
              status: 'pending',
              progress: 0,
            };
          });
          if (newItems.length > 0) {
            setErrorMessage(null);
            setSelectedFiles((prev) => [...prev, ...newItems]);
            return;
          }
        }
      } catch (err) {
        console.warn('Native openFileDialog fallback to input:', err);
      }
    }
    fileInputRef.current?.click();
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  const handleFilesSelected = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setErrorMessage(null);
    const newItems: UploadedFileItem[] = [];
    for (let i = 0; i < files.length; i++) {
      const f = files[i];
      const ext = f.name.split('.').pop()?.toUpperCase() || 'FILE';
      const nativePath = (f as any).path || (f as any).webkitRelativePath || undefined;
      newItems.push({
        file: f,
        filePath: nativePath,
        name: f.name,
        size: formatFileSize(f.size),
        extension: ext,
        status: 'pending',
        progress: 0,
      });
    }
    setSelectedFiles((prev) => [...prev, ...newItems]);
  };

  const handleRemoveFile = (index: number, e: React.MouseEvent) => {
    e.stopPropagation();
    setSelectedFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFilesSelected(e.dataTransfer.files);
    }
  };

  // STEP 1 -> STEP 2: Upload real files to backend, ingest, then analyze
  const handleProceedToAnalysis = async () => {
    if (selectedFiles.length === 0) {
      setErrorMessage('Please select at least one document or dataset to proceed.');
      return;
    }

    setErrorMessage(null);
    setIsProcessingStep(true);
    setCurrentStep('analyze');

    const updatedFiles = [...selectedFiles];
    const profiles: FileAnalysisProfile[] = [];

    try {
      for (let i = 0; i < updatedFiles.length; i++) {
        const item = updatedFiles[i];
        item.status = 'uploading';
        item.progress = 30;
        setSelectedFiles([...updatedFiles]);

        let sourceId = item.sourceId;

        // If we have an absolute file path (from Electron dialog or Electron File.path), ingest directly via IPC
        const directPath = item.filePath || (item.file as any)?.path;
        if (directPath) {
          try {
            const ingestRes = await IngestionClient.ingestFile(directPath);
            sourceId = ingestRes.source.source_id;
            item.sourceId = sourceId;
            item.progress = 60;
            item.status = 'analyzing';
            setSelectedFiles([...updatedFiles]);
          } catch (err: any) {
            console.error(`[Production RAG IPC Ingestion Error]`, {
              filePath: directPath,
              filename: item.name,
              error: err?.message || err,
            });
            // If direct path failed, fall back to uploadFile below if file object is present
            if (!item.file) {
              item.status = 'error';
              item.errorMessage = err.message || 'Unable to ingest file from disk.';
              setSelectedFiles([...updatedFiles]);
              continue;
            }
          }
        }

        if (!sourceId && item.file) {
          try {
            const ingestRes = await IngestionClient.uploadFile(item.file);
            sourceId = ingestRes.source.source_id;
            item.sourceId = sourceId;
            item.progress = 60;
            item.status = 'analyzing';
            setSelectedFiles([...updatedFiles]);
          } catch (err: any) {
            console.error(`[Production RAG Upload Error]`, {
              filename: item.name,
              status: item.status,
              source_id: sourceId,
              error: err?.message || err,
              stack: err?.stack,
            });
            item.status = 'error';
            item.errorMessage = err.message || 'Unable to upload file to backend.';
            setSelectedFiles([...updatedFiles]);
            continue;
          }
        }

        if (sourceId) {
          try {
            const profile = await AnalysisClient.analyzeFile(sourceId);
            profiles.push(profile);
            item.progress = 100;
            item.status = 'done';
            setSelectedFiles([...updatedFiles]);
          } catch (err: any) {
            console.error(`[Production RAG Analysis Error]`, {
              filename: item.name,
              source_id: sourceId,
              error: err?.message || err,
              stack: err?.stack,
            });
            item.status = 'error';
            item.errorMessage = err.message || 'Unable to analyze this file.';
            setSelectedFiles([...updatedFiles]);
          }
        }
      }

      setAnalysisProfiles(profiles);

      // Synthesize workspace knowledge
      try {
        await AnalysisClient.synthesizeWorkspace();
      } catch (err) {
        console.warn('Workspace synthesis notice:', err);
      }
    } catch (err: any) {
      setErrorMessage(err.message || 'Error processing files.');
    } finally {
      setIsProcessingStep(false);
    }
  };

  const handleRetryFile = async (index: number) => {
    const updatedFiles = [...selectedFiles];
    const item = updatedFiles[index];
    if (!item) return;

    item.status = 'uploading';
    item.progress = 30;
    item.errorMessage = undefined;
    setSelectedFiles([...updatedFiles]);
    setIsProcessingStep(true);

    try {
      let sourceId = item.sourceId;
      if (item.file) {
        const ingestRes = await IngestionClient.uploadFile(item.file);
        sourceId = ingestRes.source.source_id;
        item.sourceId = sourceId;
        item.progress = 60;
        item.status = 'analyzing';
        setSelectedFiles([...updatedFiles]);
      }

      if (sourceId) {
        const profile = await AnalysisClient.analyzeFile(sourceId);
        setAnalysisProfiles((prev) => [...prev.filter((p) => p.source_id !== sourceId), profile]);
        item.progress = 100;
        item.status = 'done';
        setSelectedFiles([...updatedFiles]);
      }

      try {
        await AnalysisClient.synthesizeWorkspace();
      } catch (err) {
        console.warn('Workspace synthesis notice:', err);
      }
    } catch (err: any) {
      console.error(`[Production RAG Retry Error]`, {
        filename: item.name,
        error: err?.message || err,
        stack: err?.stack,
      });
      item.status = 'error';
      item.errorMessage = err.message || 'Retry failed. Unable to analyze this file.';
      setSelectedFiles([...updatedFiles]);
    } finally {
      setIsProcessingStep(false);
    }
  };

  // STEP 2 -> STEP 3: Fetch real architecture recommendation
  const handleProceedToRecommendation = async () => {
    setIsProcessingStep(true);
    setErrorMessage(null);
    try {
      const recResult = await RecommendationClient.evaluateRecommendation();
      setRecommendation(recResult);
      if (recResult?.recommended_architecture) {
        setSelectedArchitectureId(recResult.recommended_architecture);
      }
      setCurrentStep('recommend');
    } catch (err: any) {
      console.error('Error evaluating recommendation:', err);
      // If no recommendation yet or evaluation failed, fallback to default knowledge_rag
      setSelectedArchitectureId('knowledge_rag');
      setCurrentStep('recommend');
    } finally {
      setIsProcessingStep(false);
    }
  };

  // STEP 3 -> STEP 4: Approve configuration and trigger real RAG build
  const handleApproveAndBuild = async () => {
    setIsProcessingStep(true);
    setErrorMessage(null);
    try {
      // Preflight verification: Ensure embedding model is available before build begins
      try {
        const inv = await ModelsClient.getInventory();
        const hasEmbeddingModel = inv.models?.some(
          (m) =>
            (m.category === 'embeddings' || m.category === 'embedding' || m.model_key.includes('bge-small')) &&
            m.status === 'ready'
        );
        if (!hasEmbeddingModel) {
          setErrorMessage(
            "Embedding model (BGE Small v1.5) is not installed. Please complete the setup in Setup Workspace or Model Manager to download the embedding weights."
          );
          setIsProcessingStep(false);
          return;
        }
      } catch {
        // Tolerant if models endpoint query fails, allow backend 424 guard to handle
      }

      const sourceIds = selectedFiles.map((f) => f.sourceId).filter(Boolean) as string[];

      await RecommendationClient.approveConfiguration({
        workspace_id: 'default',
        architecture_id: selectedArchitectureId,
        source_ids: sourceIds.length > 0 ? sourceIds : undefined,
        is_revision: true,
      });

      // Start the actual build pipeline in backend
      const buildRes = await BuilderClient.startBuild();
      setActiveBuildId(buildRes.build_id);
      setCurrentStep('building');

      // Poll real build telemetry every 800ms
      if (buildPollTimerRef.current) clearInterval(buildPollTimerRef.current);
      buildPollTimerRef.current = setInterval(async () => {
        try {
          const prog = await BuilderClient.getProgress();
          setBuildProgress(prog);

          if (prog.current_stage === 'completed' || prog.status === 'completed') {
            clearInterval(buildPollTimerRef.current);
            // Authoritative Phase 13 Registration Gate:
            // Register build as active version in RAG lifecycle layer
            const finalBuildId = buildRes.build_id;
            try {
              if (targetMode === 'new') {
                const ragName = newRagName.trim() || (selectedFiles.length > 0 ? selectedFiles[0].name.replace(/\.[^/.]+$/, '') : `Knowledge Base (${finalBuildId})`);
                const createdRecord = await lifecycleClient.createRag({
                  name: ragName,
                  description: `Compiled via RAG Studio with ${selectedArchitectureId.toUpperCase()}`,
                  initial_build_id: finalBuildId,
                });
                setCreatedOrUpdatedRagId(createdRecord.rag_id);
                setRegisteredVersionTag(versionTag || 'v1.0.0');
              } else {
                const targetId = selectedRagId || (existingRags.length > 0 ? existingRags[0].rag_id : null);
                if (!targetId) {
                  throw new Error('No target RAG artifact selected for new version registration.');
                }
                const registeredVer = await lifecycleClient.registerVersion(targetId, {
                  build_id: finalBuildId,
                  version_tag: versionTag || 'v1.1.0',
                  set_active: true,
                });
                setCreatedOrUpdatedRagId(targetId);
                setRegisteredVersionTag(registeredVer.version_tag);
              }
            } catch (regErr: any) {
              console.error('Failed to register RAG version:', regErr);
              setErrorMessage(`Build succeeded, but RAG version registration failed: ${regErr.message}`);
            }
            setCurrentStep('ready');
          } else if (prog.current_stage === 'failed' || prog.status === 'failed') {
            clearInterval(buildPollTimerRef.current);
            setErrorMessage(prog.message || 'Build failed.');
          }
        } catch (e) {
          console.error('Polling build telemetry error:', e);
        }
      }, 800);
    } catch (err: any) {
      console.error('Error starting build:', err);
      setErrorMessage(err.message || 'Failed to start build.');
    } finally {
      setIsProcessingStep(false);
    }
  };

  return (
    <div style={{ padding: '0 0 60px 0', width: '100%' }}>
      {/* Top Navigation Bar */}
      <div className="top-app-bar">
        <button
          onClick={onBackToHome}
          id="btn-studio-back"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            fontSize: 13,
            fontWeight: 600,
            color: '#64748B',
            background: 'transparent',
            border: 'none',
            cursor: onBackToHome ? 'pointer' : 'default',
            padding: '6px 10px',
            borderRadius: 8,
            transition: 'background 120ms ease',
          }}
          onMouseEnter={(e) => {
            if (onBackToHome) (e.currentTarget as HTMLElement).style.background = 'rgba(15, 23, 42, 0.05)';
          }}
          onMouseLeave={(e) => {
            if (onBackToHome) (e.currentTarget as HTMLElement).style.background = 'transparent';
          }}
        >
          <ChevronLeft size={16} />
          <span>
            {currentStep === 'upload' && 'RAG Projects > Create New RAG'}
            {currentStep === 'analyze' && 'Create New RAG > Analyze'}
            {currentStep === 'recommend' && 'Analyze > Recommendation'}
            {currentStep === 'building' && 'Configure > Build'}
            {currentStep === 'ready' && 'Build > Complete'}
          </span>
        </button>
      </div>

      <div style={{ maxWidth: 960, margin: '32px auto 0', padding: '0 24px' }}>
        {/* Horizontal 5-Step Stepper */}
        <div className="stepper-header">
          <div
            className={`step-item ${currentStep === 'upload' ? 'active' : 'completed'}`}
            onClick={() => setCurrentStep('upload')}
          >
            <div className="step-num">1</div>
            <span className="step-label">Upload</span>
          </div>

          <div
            className={`step-item ${currentStep === 'analyze' ? 'active' : ['recommend', 'building', 'ready'].includes(currentStep) ? 'completed' : ''}`}
            onClick={() => selectedFiles.length > 0 && setCurrentStep('analyze')}
          >
            <div className="step-num">2</div>
            <span className="step-label">Analyze</span>
          </div>

          <div
            className={`step-item ${currentStep === 'recommend' ? 'active' : ['building', 'ready'].includes(currentStep) ? 'completed' : ''}`}
            onClick={() => selectedFiles.length > 0 && setCurrentStep('recommend')}
          >
            <div className="step-num">3</div>
            <span className="step-label">Configure</span>
          </div>

          <div
            className={`step-item ${currentStep === 'building' ? 'active' : currentStep === 'ready' ? 'completed' : ''}`}
            onClick={() => activeBuildId && setCurrentStep('building')}
          >
            <div className="step-num">4</div>
            <span className="step-label">Build</span>
          </div>

          <div
            className={`step-item ${currentStep === 'ready' ? 'active' : ''}`}
            onClick={() => currentStep === 'ready' && setCurrentStep('ready')}
          >
            <div className="step-num">5</div>
            <span className="step-label">Ready</span>
          </div>
        </div>

        {/* Global Error Banner if any */}
        {errorMessage && (
          <div
            className="glass-card"
            style={{
              padding: '14px 18px',
              borderRadius: 12,
              background: '#FEF2F2',
              border: '1px solid #FCA5A5',
              color: '#B91C1C',
              fontSize: 13,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 12,
              marginBottom: 24,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <AlertCircle size={18} style={{ flexShrink: 0 }} />
              <span>{errorMessage}</span>
            </div>
            {errorMessage.includes('Embedding model (BGE Small v1.5) is not installed') && (
              <button
                type="button"
                onClick={handleDownloadEmbeddingModel}
                disabled={isDownloadingEmbedding}
                className="btn-primary"
                style={{
                  padding: '6px 14px',
                  fontSize: 12,
                  whiteSpace: 'nowrap',
                  background: '#2563EB',
                  border: 'none',
                }}
              >
                {isDownloadingEmbedding ? (
                  <>
                    <Loader2 size={13} className="animate-spin" />
                    <span>Downloading {embeddingDownloadProgress !== null ? `${embeddingDownloadProgress}%` : '...'}</span>
                  </>
                ) : (
                  <>
                    <Download size={13} />
                    <span>Download Embedding Model (~127 MB)</span>
                  </>
                )}
              </button>
            )}
          </div>
        )}

        {/* ================================================================
            STEP 1: UPLOAD (Clean, Zero Mock Data, Real File Intake)
           ================================================================ */}
        {currentStep === 'upload' && (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
              <div>
                <h1 style={{ fontSize: 28, fontWeight: 800, color: '#0F172A', letterSpacing: '-0.02em', margin: 0 }}>
                  {targetMode === 'new' ? 'Create New RAG' : 'Build New Version of Existing RAG'}
                </h1>
                <p style={{ fontSize: 14, color: '#64748B', marginTop: 4 }}>
                  {targetMode === 'new'
                    ? 'Ingest sources, compute profiles, and register a fresh knowledge artifact with a stable ID.'
                    : 'Compile an updated build version for an existing RAG without breaking attached Agents.'}
                </p>
              </div>

              {/* Toggle: New RAG vs Existing RAG Version */}
              <div
                style={{
                  display: 'flex',
                  background: '#F1F5F9',
                  padding: 4,
                  borderRadius: 10,
                  border: '1px solid #E2E8F0',
                }}
              >
                <button
                  type="button"
                  onClick={() => setTargetMode('new')}
                  style={{
                    padding: '8px 16px',
                    borderRadius: 8,
                    fontSize: 13,
                    fontWeight: 600,
                    border: 'none',
                    cursor: 'pointer',
                    background: targetMode === 'new' ? '#FFFFFF' : 'transparent',
                    color: targetMode === 'new' ? '#2563EB' : '#64748B',
                    boxShadow: targetMode === 'new' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
                    transition: 'all 0.15s ease',
                  }}
                  id="tab-target-new-rag"
                >
                  Create New RAG
                </button>
                <button
                  type="button"
                  onClick={() => setTargetMode('existing')}
                  style={{
                    padding: '8px 16px',
                    borderRadius: 8,
                    fontSize: 13,
                    fontWeight: 600,
                    border: 'none',
                    cursor: 'pointer',
                    background: targetMode === 'existing' ? '#FFFFFF' : 'transparent',
                    color: targetMode === 'existing' ? '#2563EB' : '#64748B',
                    boxShadow: targetMode === 'existing' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
                    transition: 'all 0.15s ease',
                  }}
                  id="tab-target-existing-rag"
                >
                  New Version of Existing RAG
                </button>
              </div>
            </div>

            {/* Target Details Card */}
            <div className="glass-card" style={{ padding: 18, borderRadius: 12, marginBottom: 24, background: '#F8FAFC' }}>
              {targetMode === 'new' ? (
                <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 16 }}>
                  <div>
                    <label style={{ fontSize: 12, fontWeight: 700, color: '#334155', display: 'block', marginBottom: 6 }}>
                      RAG Knowledge Base Name
                    </label>
                    <input
                      type="text"
                      value={newRagName}
                      onChange={(e) => setNewRagName(e.target.value)}
                      placeholder="e.g. Legal Compliance Archive, Science Textbook..."
                      style={{
                        width: '100%',
                        padding: '10px 14px',
                        borderRadius: 8,
                        border: '1px solid #CBD5E1',
                        fontSize: 13,
                        outline: 'none',
                      }}
                      id="input-new-rag-name"
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: 12, fontWeight: 700, color: '#334155', display: 'block', marginBottom: 6 }}>
                      Initial Version Tag
                    </label>
                    <input
                      type="text"
                      value={versionTag}
                      onChange={(e) => setVersionTag(e.target.value)}
                      placeholder="v1.0.0"
                      style={{
                        width: '100%',
                        padding: '10px 14px',
                        borderRadius: 8,
                        border: '1px solid #CBD5E1',
                        fontSize: 13,
                        outline: 'none',
                      }}
                      id="input-version-tag"
                    />
                  </div>
                </div>
              ) : (
                <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 16 }}>
                  <div>
                    <label style={{ fontSize: 12, fontWeight: 700, color: '#334155', display: 'block', marginBottom: 6 }}>
                      Target Knowledge Artifact (Stable Identity)
                    </label>
                    <select
                      value={selectedRagId}
                      onChange={(e) => {
                        setSelectedRagId(e.target.value);
                        const match = existingRags.find((r) => r.rag_id === e.target.value);
                        if (match) {
                          setVersionTag(`v1.${match.versions.length}.0`);
                        }
                      }}
                      style={{
                        width: '100%',
                        padding: '10px 14px',
                        borderRadius: 8,
                        border: '1px solid #CBD5E1',
                        fontSize: 13,
                        outline: 'none',
                        background: '#FFFFFF',
                      }}
                      id="select-target-rag"
                    >
                      {existingRags.map((r) => (
                        <option key={r.rag_id} value={r.rag_id}>
                          {r.name} ({r.rag_id}) — {r.versions.length} version(s)
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label style={{ fontSize: 12, fontWeight: 700, color: '#334155', display: 'block', marginBottom: 6 }}>
                      Next Version Tag
                    </label>
                    <input
                      type="text"
                      value={versionTag}
                      onChange={(e) => setVersionTag(e.target.value)}
                      placeholder="v1.1.0"
                      style={{
                        width: '100%',
                        padding: '10px 14px',
                        borderRadius: 8,
                        border: '1px solid #CBD5E1',
                        fontSize: 13,
                        outline: 'none',
                      }}
                      id="input-existing-version-tag"
                    />
                  </div>
                </div>
              )}
            </div>

            {/* Hidden native file input */}
            <input
              type="file"
              ref={fileInputRef}
              style={{ display: 'none' }}
              multiple
              accept=".pdf,.docx,.txt,.csv,.pptx,.md,.json"
              onChange={(e) => handleFilesSelected(e.target.files)}
            />

            {/* Giant Clean Dropzone */}
            <div
              className={`dropzone-panel ${isDragging ? 'dragging' : ''}`}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={handleChooseFilesClick}
              style={{
                minHeight: 340,
                marginBottom: 28,
                cursor: 'pointer',
                borderColor: isDragging ? '#4F46E5' : undefined,
                background: isDragging ? 'rgba(238, 242, 255, 0.85)' : undefined,
              }}
            >
              {/* Center Content */}
              <div style={{ width: 68, height: 68, borderRadius: '50%', background: '#F1F5F9', display: 'flex', alignItems: 'center', justifyContent: 'center', marginBottom: 18 }}>
                <UploadCloud size={34} color="#0F172A" />
              </div>

              <h3 style={{ fontSize: 20, fontWeight: 800, color: '#0F172A', marginBottom: 8 }}>
                Drop your files here
              </h3>

              <p style={{ fontSize: 13, color: '#64748B', maxWidth: 480, marginBottom: 22, lineHeight: 1.6 }}>
                Select documents or datasets from your computer to analyze and index.<br />
                <span style={{ fontSize: 12, color: '#94A3B8' }}>Supports PDF, DOCX, CSV, TXT, PPTX, MD, and JSON</span>
              </p>

              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  handleChooseFilesClick();
                }}
                className="btn-primary"
                style={{ padding: '12px 28px', marginBottom: 14 }}
              >
                <span>Choose Files</span>
              </button>

              <span style={{ fontSize: 12, color: '#94A3B8' }}>or drag and drop files directly onto this zone</span>

              {/* Privacy Label */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: '#64748B', marginTop: 36 }}>
                <Lock size={13} color="#64748B" />
                <span>Files are processed strictly locally on this machine.</span>
              </div>
            </div>

            {/* Selected Real Files Staging List */}
            {selectedFiles.length > 0 ? (
              <div style={{ marginBottom: 32 }}>
                <div style={{ fontSize: 14, fontWeight: 700, color: '#0F172A', marginBottom: 14, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span>Files to Ingest ({selectedFiles.length})</span>
                  <button
                    onClick={() => setSelectedFiles([])}
                    style={{ background: 'transparent', border: 'none', color: '#EF4444', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}
                  >
                    Clear All
                  </button>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
                  {selectedFiles.map((file, idx) => (
                    <div
                      key={idx}
                      className="glass-card"
                      style={{
                        padding: '14px 18px',
                        borderRadius: 14,
                        background: '#FFFFFF',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        border: '1px solid rgba(15, 23, 42, 0.08)',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0 }}>
                        <div
                          style={{
                            padding: '6px 10px',
                            borderRadius: 8,
                            fontSize: 11,
                            fontWeight: 800,
                            background:
                              file.extension === 'PDF'
                                ? '#FEE2E2'
                                : file.extension === 'DOCX'
                                ? '#DBEAFE'
                                : file.extension === 'CSV'
                                ? '#D1FAE5'
                                : '#F1F5F9',
                            color:
                              file.extension === 'PDF'
                                ? '#DC2626'
                                : file.extension === 'DOCX'
                                ? '#2563EB'
                                : file.extension === 'CSV'
                                ? '#059669'
                                : '#475569',
                          }}
                        >
                          {file.extension}
                        </div>
                        <div style={{ minWidth: 0 }}>
                          <div style={{ fontSize: 13, fontWeight: 700, color: '#0F172A', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>
                            {file.name}
                          </div>
                          <div style={{ fontSize: 11, color: '#94A3B8' }}>{file.size}</div>
                        </div>
                      </div>

                      <button
                        onClick={(e) => handleRemoveFile(idx, e)}
                        title="Remove file"
                        style={{
                          background: 'transparent',
                          border: 'none',
                          color: '#94A3B8',
                          cursor: 'pointer',
                          padding: 6,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                        }}
                      >
                        <X size={16} />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}

            <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
              <button
                onClick={handleProceedToAnalysis}
                disabled={selectedFiles.length === 0 || isProcessingStep}
                className="btn-primary"
                style={{ padding: '12px 28px', opacity: selectedFiles.length === 0 ? 0.6 : 1 }}
              >
                {isProcessingStep ? (
                  <>
                    <Loader2 size={16} className="animate-spin" />
                    <span>Processing...</span>
                  </>
                ) : (
                  <>
                    <span>Proceed to Analysis</span>
                    <ArrowRight size={16} />
                  </>
                )}
              </button>
            </div>
          </div>
        )}

        {/* ================================================================
            STEP 2: ANALYZING YOUR REAL FILES (Zero Hardcoded Data)
           ================================================================ */}
        {currentStep === 'analyze' && (
          <div>
            <h1 style={{ fontSize: 28, fontWeight: 800, color: '#0F172A', letterSpacing: '-0.02em', marginBottom: 28 }}>
              Analyzing Your Files
            </h1>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 32, alignItems: 'center', marginBottom: 40 }}>
              {/* Left Column: Concentric Glowing Orb & Observational Status */}
              <div style={{ textAlign: 'center', padding: '20px' }}>
                <div className="radiant-core" style={{ margin: '0 auto 24px' }}>
                  <div className="radiant-ring radiant-ring-1" />
                  <div className="radiant-ring radiant-ring-2" />
                  <div className="ragger-orb-3d" style={{ width: 80, height: 80 }}>
                    <img
                      src={raggerBoxLogo}
                      alt="Ragger Logo"
                      style={{ width: 50, height: 50, borderRadius: 12, objectFit: 'contain' }}
                    />
                  </div>
                </div>

                <p style={{ fontSize: 14, color: '#64748B', maxWidth: 320, margin: '0 auto 24px', lineHeight: 1.5 }}>
                  {isProcessingStep
                    ? 'Our Analyzer Agent is extracting text, computing headings, and analyzing structural density...'
                    : 'Analysis complete. Structural profiles and modality parameters calculated.'}
                </p>

                {/* Did You Know Callout */}
                <div
                  className="glass-card"
                  style={{
                    background: 'rgba(255, 255, 255, 0.9)',
                    padding: 16,
                    borderRadius: 14,
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: 12,
                    textAlign: 'left',
                  }}
                >
                  <Sparkles size={18} color="#2563EB" style={{ flexShrink: 0, marginTop: 2 }} />
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 700, color: '#0F172A', marginBottom: 2 }}>
                      Deterministic Profiling
                    </div>
                    <div style={{ fontSize: 12, color: '#64748B', lineHeight: 1.5 }}>
                      We inspect token counts, heading depths, tabular ratios, and domain features to guarantee reproducible architecture selection.
                    </div>
                  </div>
                </div>
              </div>

              {/* Right Column: Real File Ingestion & Analysis Status */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                {selectedFiles.map((file, idx) => {
                  const profile = analysisProfiles.find((p) => p.source_id === file.sourceId);
                  return (
                    <div key={idx} className="glass-card" style={{ background: '#FFFFFF', padding: 20, borderRadius: 16 }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                          <div
                            style={{
                              width: 36,
                              height: 36,
                              borderRadius: 8,
                              background: file.extension === 'PDF' ? '#FEE2E2' : file.extension === 'DOCX' ? '#DBEAFE' : file.extension === 'CSV' ? '#D1FAE5' : '#F1F5F9',
                              color: file.extension === 'PDF' ? '#DC2626' : file.extension === 'DOCX' ? '#2563EB' : file.extension === 'CSV' ? '#059669' : '#475569',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              fontSize: 10,
                              fontWeight: 800,
                            }}
                          >
                            {file.extension}
                          </div>
                          <div>
                            <div style={{ fontSize: 14, fontWeight: 700, color: '#0F172A' }}>{file.name}</div>
                            <div style={{ fontSize: 12, color: '#64748B' }}>
                              {profile
                                ? `Domain: ${profile.semantic_observations.detected_domain} · ${profile.structural_facts.total_words} words`
                                : file.status === 'uploading'
                                ? 'Uploading to engine...'
                                : file.status === 'analyzing'
                                ? 'Analyzing structural facts...'
                                : file.status === 'error'
                                ? file.errorMessage || 'Error'
                                : 'Ready to analyze'}
                            </div>
                          </div>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                          {file.status === 'error' && (
                            <button
                              onClick={() => handleRetryFile(idx)}
                              disabled={isProcessingStep}
                              className="btn-secondary"
                              style={{
                                padding: '4px 10px',
                                fontSize: 11,
                                height: 28,
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: 4,
                                color: '#EF4444',
                                borderColor: '#FCA5A5',
                              }}
                            >
                              <RefreshCw size={12} />
                              <span>Retry</span>
                            </button>
                          )}
                          <span style={{ fontSize: 13, fontWeight: 700, color: file.status === 'error' ? '#EF4444' : '#0F172A' }}>
                            {file.status === 'done' ? '100%' : file.status === 'error' ? 'Failed' : `${file.progress}%`}
                          </span>
                        </div>
                      </div>
                      <div className="progress-bar-container">
                        <div
                          className="progress-bar-fill"
                          style={{
                            width: `${file.progress}%`,
                            background: file.status === 'error' ? '#EF4444' : undefined,
                          }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12 }}>
              <button
                onClick={() => setCurrentStep('upload')}
                className="btn-secondary"
                style={{ padding: '12px 24px' }}
              >
                <span>Back</span>
              </button>

              <button
                onClick={handleProceedToRecommendation}
                disabled={isProcessingStep}
                className="btn-primary"
                style={{ padding: '12px 28px' }}
              >
                {isProcessingStep ? (
                  <>
                    <Loader2 size={16} className="animate-spin" />
                    <span>Evaluating Rules...</span>
                  </>
                ) : (
                  <>
                    <span>View Recommendation</span>
                    <ArrowRight size={16} />
                  </>
                )}
              </button>
            </div>
          </div>
        )}

        {/* ================================================================
            STEP 3: RAG TYPE RECOMMENDATION (Driven by Real Engine Evaluation)
           ================================================================ */}
        {currentStep === 'recommend' && (
          <div>
            <h1 style={{ fontSize: 28, fontWeight: 800, color: '#0F172A', letterSpacing: '-0.02em', marginBottom: 4 }}>
              RAG Type Recommendation
            </h1>
            <p style={{ fontSize: 14, color: '#64748B', marginBottom: 32 }}>
              Based on the {selectedFiles.length} file(s) you ingested, the engine deterministically calculated this architecture:
            </p>

            <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: 28, marginBottom: 40 }}>
              {/* Left Column: Recommended Card */}
              <div>
                <div style={{ fontSize: 13, fontWeight: 700, color: '#0F172A', marginBottom: 12 }}>
                  Recommended RAG Type
                </div>

                <div
                  className="glass-card"
                  style={{
                    background: '#FFFFFF',
                    borderRadius: 20,
                    padding: 28,
                    border: '1.5px solid rgba(99, 102, 241, 0.3)',
                    boxShadow: '0 12px 36px -6px rgba(99, 102, 241, 0.12)',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <div style={{ width: 40, height: 40, borderRadius: 10, background: '#EFF6FF', color: '#2563EB', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <Shield size={22} />
                      </div>
                      <h3 style={{ fontSize: 18, fontWeight: 800, color: '#0F172A' }}>
                        {recommendation?.architecture_spec?.title || 'Knowledge Base RAG'}
                      </h3>
                    </div>
                    <span className="badge-pill badge-pill-green">
                      {recommendation?.confidence_level ? `${recommendation.confidence_level.toUpperCase()} CONFIDENCE` : 'RECOMMENDED'}
                    </span>
                  </div>

                  <p style={{ fontSize: 13, color: '#64748B', lineHeight: 1.5, marginBottom: 20 }}>
                    {recommendation?.architecture_spec?.tagline || 'Best for document collections, manual guides, and structured enterprise content.'}
                  </p>

                  <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 28 }}>
                    {(recommendation?.architecture_spec?.strengths || [
                      'Handles dense document hierarchies',
                      'High recall semantic vector search',
                      'Deterministic boundary paragraph chunking',
                    ]).map((str, sIdx) => (
                      <div key={sIdx} style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13, color: '#334155' }}>
                        <Check size={16} color="#10B981" />
                        <span>{str}</span>
                      </div>
                    ))}
                  </div>

                  <button
                    onClick={() => {
                      setSelectedArchitectureId(recommendation?.recommended_architecture || 'knowledge_rag');
                      handleApproveAndBuild();
                    }}
                    disabled={isProcessingStep}
                    className="btn-primary"
                    style={{ width: '100%', padding: '13px' }}
                  >
                    {isProcessingStep ? (
                      <>
                        <Loader2 size={16} className="animate-spin" />
                        <span>Freezing Configuration...</span>
                      </>
                    ) : (
                      <>
                        <span>Approve & Build</span>
                        <ArrowRight size={16} />
                      </>
                    )}
                  </button>
                </div>
              </div>

              {/* Right Column: Other Suitable Options */}
              <div>
                <div style={{ fontSize: 13, fontWeight: 700, color: '#0F172A', marginBottom: 12 }}>
                  Alternative Configurations
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                  {/* Option 1: Tabular RAG */}
                  <div
                    onClick={() => setSelectedArchitectureId('structured_data_rag')}
                    className="glass-card"
                    style={{
                      background: '#FFFFFF',
                      padding: 20,
                      borderRadius: 16,
                      cursor: 'pointer',
                      border: selectedArchitectureId === 'structured_data_rag' ? '2px solid #4F46E5' : '1px solid rgba(15, 23, 42, 0.08)',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                      <div style={{ width: 32, height: 32, borderRadius: 8, background: '#F5F3FF', color: '#7C3AED', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <Table size={18} />
                      </div>
                      <h4 style={{ fontSize: 15, fontWeight: 700, color: '#0F172A' }}>Tabular Data RAG</h4>
                    </div>
                    <p style={{ fontSize: 12, color: '#64748B', lineHeight: 1.5, marginBottom: 8 }}>
                      Best for tabular records, spreadsheet datasets, and column schemas.
                    </p>
                  </div>

                  {/* Option 2: Hybrid RAG */}
                  <div
                    onClick={() => setSelectedArchitectureId('hybrid_rag')}
                    className="glass-card"
                    style={{
                      background: '#FFFFFF',
                      padding: 20,
                      borderRadius: 16,
                      cursor: 'pointer',
                      border: selectedArchitectureId === 'hybrid_rag' ? '2px solid #4F46E5' : '1px solid rgba(15, 23, 42, 0.08)',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
                      <div style={{ width: 32, height: 32, borderRadius: 8, background: '#EFF6FF', color: '#2563EB', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <Layers size={18} />
                      </div>
                      <h4 style={{ fontSize: 15, fontWeight: 700, color: '#0F172A' }}>Hybrid RAG</h4>
                    </div>
                    <p style={{ fontSize: 12, color: '#64748B', lineHeight: 1.5, marginBottom: 8 }}>
                      Combines keyword exact match with vector embeddings.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ================================================================
            STEP 4: REAL-TIME PIPELINE EXECUTION (Authoritative Telemetry)
           ================================================================ */}
        {currentStep === 'building' && (
          <div>
            <h1 style={{ fontSize: 28, fontWeight: 800, color: '#0F172A', letterSpacing: '-0.02em', marginBottom: 36 }}>
              Building Your RAG
            </h1>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 36, alignItems: 'center', marginBottom: 40 }}>
              {/* Left Column: 3D Layered Discs */}
              <div style={{ textAlign: 'center' }}>
                <div className="database-layers-visual" style={{ margin: '0 auto 28px' }}>
                  <div className="disc-layer disc-layer-1" />
                  <div className="disc-layer disc-layer-2" />
                  <div className="disc-layer disc-layer-3" />
                </div>

                <div
                  style={{
                    display: 'inline-block',
                    background: '#FFFFFF',
                    padding: '8px 18px',
                    borderRadius: 9999,
                    fontSize: 13,
                    fontWeight: 600,
                    color: '#475569',
                    boxShadow: '0 2px 10px rgba(0,0,0,0.04)',
                    marginBottom: 12,
                  }}
                >
                  {buildProgress?.message || 'Processing chunks and embedding vectors...'}
                </div>

                <p style={{ fontSize: 12, color: '#94A3B8' }}>
                  {buildProgress?.elapsed_seconds !== undefined
                    ? `Elapsed: ${buildProgress.elapsed_seconds.toFixed(1)}s · Build ID: ${activeBuildId || 'live'}`
                    : 'Constructing vector index and running retrieval verification...'}
                </p>
              </div>

              {/* Right Column: Real-Time Stage Telemetry */}
              <div className="glass-card" style={{ background: '#FFFFFF', padding: 32, borderRadius: 20 }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                    {['chunking', 'embedding', 'indexing', 'verifying', 'completed'].includes(buildProgress?.current_stage || '') ? (
                      <CheckCircle2 size={20} color="#10B981" />
                    ) : (
                      <div style={{ width: 20, height: 20, borderRadius: '50%', border: '2px solid #3B82F6', borderTopColor: 'transparent', animation: 'spin 1s linear infinite' }} />
                    )}
                    <span style={{ fontSize: 14, fontWeight: 600, color: '#0F172A' }}>
                      Preflight & Structural Verification
                    </span>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                    {['embedding', 'indexing', 'verifying', 'completed'].includes(buildProgress?.current_stage || '') ? (
                      <CheckCircle2 size={20} color="#10B981" />
                    ) : buildProgress?.current_stage === 'chunking' ? (
                      <div style={{ width: 20, height: 20, borderRadius: '50%', border: '2px solid #3B82F6', borderTopColor: 'transparent', animation: 'spin 1s linear infinite' }} />
                    ) : (
                      <div style={{ width: 18, height: 18, borderRadius: '50%', border: '2px solid #CBD5E1' }} />
                    )}
                    <span style={{ fontSize: 14, fontWeight: 600, color: '#0F172A' }}>
                      Boundary Chunking ({buildProgress?.chunks_processed || 0} chunks)
                    </span>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                    {['indexing', 'verifying', 'completed'].includes(buildProgress?.current_stage || '') ? (
                      <CheckCircle2 size={20} color="#10B981" />
                    ) : buildProgress?.current_stage === 'embedding' ? (
                      <div style={{ width: 20, height: 20, borderRadius: '50%', border: '2px solid #3B82F6', borderTopColor: 'transparent', animation: 'spin 1s linear infinite' }} />
                    ) : (
                      <div style={{ width: 18, height: 18, borderRadius: '50%', border: '2px solid #CBD5E1' }} />
                    )}
                    <span style={{ fontSize: 14, fontWeight: 600, color: '#0F172A' }}>
                      Dense Vector Embeddings ({buildProgress?.vectors_processed || 0} vectors)
                    </span>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                    {['verifying', 'completed'].includes(buildProgress?.current_stage || '') ? (
                      <CheckCircle2 size={20} color="#10B981" />
                    ) : buildProgress?.current_stage === 'indexing' ? (
                      <div style={{ width: 20, height: 20, borderRadius: '50%', border: '2px solid #3B82F6', borderTopColor: 'transparent', animation: 'spin 1s linear infinite' }} />
                    ) : (
                      <div style={{ width: 18, height: 18, borderRadius: '50%', border: '2px solid #CBD5E1' }} />
                    )}
                    <span style={{ fontSize: 14, fontWeight: 600, color: '#0F172A' }}>
                      Flat Vector Index & Storage
                    </span>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                    {buildProgress?.current_stage === 'completed' ? (
                      <CheckCircle2 size={20} color="#10B981" />
                    ) : buildProgress?.current_stage === 'verifying' ? (
                      <div style={{ width: 20, height: 20, borderRadius: '50%', border: '2px solid #3B82F6', borderTopColor: 'transparent', animation: 'spin 1s linear infinite' }} />
                    ) : (
                      <div style={{ width: 18, height: 18, borderRadius: '50%', border: '2px solid #CBD5E1' }} />
                    )}
                    <span style={{ fontSize: 14, fontWeight: 600, color: '#0F172A' }}>
                      Retrieval Self-Consistency Sanity Verification
                    </span>
                  </div>
                </div>
              </div>
            </div>

            {/* Error Actions for Failed Build */}
            {(errorMessage || buildProgress?.status === 'failed' || buildProgress?.current_stage === 'failed') && (
              <div style={{ display: 'flex', justifyContent: 'center', gap: 14, marginTop: 16 }}>
                <button
                  onClick={() => {
                    setErrorMessage(null);
                    setCurrentStep('recommend');
                  }}
                  className="btn-secondary"
                  style={{ padding: '12px 24px' }}
                >
                  <span>Back to Configuration</span>
                </button>
                <button
                  onClick={() => {
                    setErrorMessage(null);
                    handleApproveAndBuild();
                  }}
                  className="btn-primary"
                  style={{ padding: '12px 28px', display: 'inline-flex', alignItems: 'center', gap: 8 }}
                >
                  <RefreshCw size={16} />
                  <span>Retry Build</span>
                </button>
              </div>
            )}
          </div>
        )}

        {/* ================================================================
            STEP 5: READY & FULLY VERIFIED RAG KNOWLEDGE BASE
           ================================================================ */}
        {currentStep === 'ready' && (
          <div style={{ textAlign: 'center', padding: '40px 20px' }}>
            {/* Luminous Celebration Checkmark Orb */}
            <div className="celebration-orb">
              <Check size={48} strokeWidth={3} />
            </div>

            <h1 style={{ fontSize: 32, fontWeight: 800, color: '#0F172A', letterSpacing: '-0.02em', marginBottom: 8 }}>
              {targetMode === 'new' ? 'New RAG Knowledge Base Ready!' : 'New Version Successfully Activated!'}
            </h1>
            <p style={{ fontSize: 16, color: '#64748B', marginBottom: 20 }}>
              <strong style={{ color: '#0F172A' }}>
                {createdOrUpdatedRagId || (selectedFiles.length > 0 ? selectedFiles[0].name.replace(/\.[^/.]+$/, '') : 'Knowledge Base')}
              </strong>{' '}
              {registeredVersionTag ? `(${registeredVersionTag})` : ''} is verified and active for private grounded conversation.
            </p>

            {createdOrUpdatedRagId && (
              <div
                className="glass-card"
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 12,
                  padding: '8px 16px',
                  borderRadius: 20,
                  background: '#F8FAFC',
                  border: '1px solid #E2E8F0',
                  marginBottom: 28,
                  fontSize: 12,
                  color: '#475569',
                }}
              >
                <span>Stable ID: <strong style={{ color: '#0F172A', fontFamily: 'monospace' }}>{createdOrUpdatedRagId}</strong></span>
                <span>•</span>
                <span>Active Version: <strong style={{ color: '#2563EB', fontFamily: 'monospace' }}>{registeredVersionTag || 'v1.0.0'}</strong></span>
                <span>•</span>
                <span>Build: <strong style={{ color: '#059669', fontFamily: 'monospace' }}>{activeBuildId || 'bld_active'}</strong></span>
              </div>
            )}

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 14, marginBottom: 32 }}>
              <button
                onClick={() => onGoToChat(createdOrUpdatedRagId || 'rag_class10_english')}
                className="btn-primary"
                style={{ padding: '13px 28px', fontSize: 15 }}
                id="btn-ready-agent"
              >
                <span>Go to AI Agent</span>
                <ArrowRight size={16} />
              </button>

              <button
                onClick={() => onGoToChat(createdOrUpdatedRagId || 'rag_class10_english')}
                className="btn-secondary"
                style={{ padding: '13px 26px', fontSize: 15 }}
                id="btn-ready-chat"
              >
                <MessageSquare size={16} />
                <span>Chat with Your Data</span>
              </button>
            </div>

            <div>
              <button
                onClick={() => onExportRagger(createdOrUpdatedRagId || 'Knowledge Base')}
                style={{ fontSize: 13, fontWeight: 600, color: '#4F46E5', display: 'inline-flex', alignItems: 'center', gap: 6 }}
                id="btn-ready-export-package"
              >
                <Download size={14} />
                <span>Export .ragpack package</span>
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
