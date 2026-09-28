import React, { useState, useEffect, useRef } from 'react';
import {
  ArrowRight,
  Download,
  AlertCircle,
  RefreshCw,
  Cpu,
  Pause,
  Play,
  X,
  ShieldCheck,
  Check,
  HardDrive,
  AlertTriangle,
} from 'lucide-react';
import { ModelsClient } from '../../services/modelsClient';
import {
  HardwareCapabilities,
  CatalogModelSpec,
  InstalledModelInfo,
  DownloadProgress,
} from '../../types/models';
import raggerBoxLogo from '../../assets/ragger.ai_box_logo.png';
import raggerFullLogo from '../../assets/ragger.ai_full_logo.png';

interface SetupWorkspaceViewProps {
  onComplete: () => void;
  modelsClient?: ModelsClient;
}

type SetupFlowState =
  | 'loading'
  | 'not_installed'
  | 'downloading'
  | 'verifying'
  | 'activating'
  | 'ready'
  | 'error';

function formatBytes(bytes: number): string {
  if (!bytes || bytes <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(i >= 2 ? 1 : 0)} ${units[i]}`;
}

export const SetupWorkspaceView: React.FC<SetupWorkspaceViewProps> = ({
  onComplete,
}) => {
  // Hardware & Catalog states
  const [hardware, setHardware] = useState<HardwareCapabilities | null>(null);
  const [catalog, setCatalog] = useState<CatalogModelSpec[]>([]);
  const [selectedModel, setSelectedModel] = useState<CatalogModelSpec | null>(null);
  const [installedModels, setInstalledModels] = useState<InstalledModelInfo[]>([]);

  // Flow & telemetry states
  const [flowState, setFlowState] = useState<SetupFlowState>('loading');
  const [statusMessage, setStatusMessage] = useState('Detecting hardware and local runtime...');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isPaused, setIsPaused] = useState(false);
  const [progress, setProgress] = useState<DownloadProgress | null>(null);

  // Modal for "Choose another model"
  const [showModelPicker, setShowModelPicker] = useState(false);

  // Polling ref
  const pollIntervalRef = useRef<any>(null);

  const clearPolling = () => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
  };

  useEffect(() => {
    return () => {
      clearPolling();
    };
  }, []);

  const [activeDownloadKey, setActiveDownloadKey] = useState<string | null>(null);
  const [activeDownloadLabel, setActiveDownloadLabel] = useState<string>('');

  // Initial load: Hardware, Catalog, Inventory
  const loadInitialData = async () => {
    setFlowState('loading');
    setErrorMessage(null);
    setStatusMessage('Preparing local workspace...');

    try {
      // 1. Fetch hardware profile (Model Manager single owner)
      const hw = await ModelsClient.getHardware(false).catch(() => null);
      if (hw) {
        setHardware(hw);
      }

      // 2. Fetch inventory of installed models
      const inv = await ModelsClient.getInventory().catch(() => ({ models: [], total_count: 0, total_size_bytes: 0 }));
      const installed = inv.models || [];
      setInstalledModels(installed);

      // 3. Fetch model catalog enriched with deterministic recommendations
      const catRes = await ModelsClient.getCatalog().catch(() => ({ models: [] }));
      const catList: CatalogModelSpec[] = Array.isArray(catRes) ? catRes : catRes.models || [];
      setCatalog(catList);

      // Resolve recommended or already installed generation model
      const generationModels = catList.filter((m) => m.category === 'generation');
      const installedGenModel = generationModels.find((m) =>
        installed.some((inst) => inst.model_key === m.model_key && inst.status === 'ready')
      );

      const recommendedGen =
        generationModels.find((m) => m.recommended) ||
        generationModels.find((m) => m.is_compatible) ||
        generationModels[0] ||
        null;

      const chosenGen = installedGenModel || recommendedGen;
      if (chosenGen) {
        setSelectedModel(chosenGen);
      } else {
        setFlowState('error');
        setErrorMessage('No compatible local AI models found in catalog.');
        return;
      }

      // Check if both embedding model and generation model are ready
      const embeddingSpec = catList.find((m) => m.category === 'embeddings' || m.category === 'embedding');
      const embeddingKey = embeddingSpec?.model_key || 'bge-small-en-v1.5:onnx:default-v1';
      const isEmbReady = installed.some((inst) => inst.model_key === embeddingKey && inst.status === 'ready');
      const isGenReady = installedGenModel !== undefined;

      if (isEmbReady && isGenReady) {
        setFlowState('ready');
        setStatusMessage('Local AI models are installed and ready.');
      } else {
        setFlowState('not_installed');
      }
    } catch (err: any) {
      setFlowState('error');
      setErrorMessage(err.message || 'Local model service is temporarily unavailable.');
    }
  };

  useEffect(() => {
    loadInitialData();
  }, []);

  // Poll progress for a specific model key until completed, failed, or cancelled
  const pollSingleDownload = (modelKey: string, modelLabel: string): Promise<void> => {
    return new Promise((resolve, reject) => {
      clearPolling();
      setActiveDownloadKey(modelKey);
      setActiveDownloadLabel(modelLabel);

      pollIntervalRef.current = setInterval(async () => {
        try {
          const prog = await ModelsClient.getProgress(modelKey);
          setProgress(prog);

          const stateStr = String(prog.state);
          if (stateStr === 'downloading' || stateStr === 'preflight') {
            setIsPaused(false);
            setFlowState('downloading');
          } else if (stateStr === 'paused') {
            setIsPaused(true);
            setFlowState('downloading');
          } else if (stateStr === 'verifying') {
            setFlowState('verifying');
            setStatusMessage(`Verifying ${modelLabel} integrity (SHA-256)...`);
          } else if (stateStr === 'completed') {
            clearPolling();
            resolve();
          } else if (stateStr === 'failed') {
            clearPolling();
            reject(new Error(prog.error_message || `${modelLabel} download failed.`));
          } else if (stateStr === 'cancelled') {
            clearPolling();
            reject(new Error(`${modelLabel} download cancelled.`));
          }
        } catch {
          // Tolerant to transient connection hiccups
        }
      }, 500);
    });
  };

  // Download & Continue Action (Sequentially handles missing embedding and generation models)
  const handleStartDownload = async () => {
    if (!selectedModel) return;

    // Check preflight requirements before initiating download
    if (!hasEnoughStorage()) {
      setErrorMessage(
        `Not enough disk space for model download. Required: ${displayModelStorageRequired()}, Available: ${displayDiskStorageAvailable()}`
      );
      return;
    }

    setErrorMessage(null);
    setFlowState('downloading');
    setIsPaused(false);
    setProgress(null);

    try {
      // Re-fetch current inventory to see what is already installed
      const inv = await ModelsClient.getInventory().catch(() => ({ models: [], total_count: 0, total_size_bytes: 0 }));
      const installed = inv.models || [];
      setInstalledModels(installed);

      const embeddingSpec = catalog.find((m) => m.category === 'embeddings' || m.category === 'embedding');
      const embeddingKey = embeddingSpec?.model_key || 'bge-small-en-v1.5:onnx:default-v1';
      const isEmbReady = installed.some((inst) => inst.model_key === embeddingKey && inst.status === 'ready');
      const isGenReady = installed.some((inst) => inst.model_key === selectedModel.model_key && inst.status === 'ready');

      // 1. Download embedding model if not ready
      if (!isEmbReady) {
        setStatusMessage('Starting embedding model download (BGE Small v1.5)...');
        const initEmbProg = await ModelsClient.startDownload(embeddingKey);
        setProgress(initEmbProg);
        await pollSingleDownload(embeddingKey, 'Embedding model (BGE Small)');

        // Verify embedding model post-download
        setFlowState('verifying');
        setStatusMessage('Verifying embedding model integrity (SHA-256)...');
        await new Promise((r) => setTimeout(r, 600));

        const postEmbInv = await ModelsClient.getInventory();
        setInstalledModels(postEmbInv.models || []);
        const embMatch = postEmbInv.models?.find((m) => m.model_key === embeddingKey);
        if (embMatch && (embMatch.status === 'corrupt' || embMatch.status === 'failed')) {
          throw new Error('Embedding model verification failed: SHA-256 mismatch.');
        }
      }

      // 2. Download generation model if not ready
      if (!isGenReady) {
        setStatusMessage(`Starting ${selectedModel.model_id} download...`);
        const initGenProg = await ModelsClient.startDownload(selectedModel.model_key);
        setProgress(initGenProg);
        await pollSingleDownload(selectedModel.model_key, selectedModel.model_id);

        // Verify generation model post-download
        setFlowState('verifying');
        setStatusMessage(`Verifying ${selectedModel.model_id} integrity (SHA-256)...`);
        await new Promise((r) => setTimeout(r, 600));

        const postGenInv = await ModelsClient.getInventory();
        setInstalledModels(postGenInv.models || []);
        const genMatch = postGenInv.models?.find((m) => m.model_key === selectedModel.model_key);
        if (genMatch && (genMatch.status === 'corrupt' || genMatch.status === 'failed')) {
          throw new Error(`${selectedModel.model_id} verification failed: SHA-256 mismatch.`);
        }
      }

      // 3. Activate generation model
      setFlowState('activating');
      setStatusMessage('Activating local AI model...');
      await ModelsClient.activateModel(selectedModel.model_key, 'generation').catch(() => {});

      const finalInv = await ModelsClient.getInventory().catch(() => ({ models: [] }));
      setInstalledModels(finalInv.models || []);
      setFlowState('ready');
      setStatusMessage('Local AI ready');
    } catch (err: any) {
      clearPolling();
      setFlowState('error');
      setErrorMessage(err.message || 'Failed to download models. Please check your internet connection.');
    } finally {
      setActiveDownloadKey(null);
      setActiveDownloadLabel('');
    }
  };

  // Handle Pause
  const handlePause = async () => {
    const keyToPause = activeDownloadKey || selectedModel?.model_key;
    if (!keyToPause) return;
    try {
      const p = await ModelsClient.pauseDownload(keyToPause);
      setProgress(p);
      setIsPaused(true);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to pause download.');
    }
  };

  // Handle Resume
  const handleResume = async () => {
    const keyToResume = activeDownloadKey || selectedModel?.model_key;
    if (!keyToResume) return;
    try {
      const p = await ModelsClient.resumeDownload(keyToResume);
      setProgress(p);
      setIsPaused(false);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to resume download.');
    }
  };

  // Handle Cancel
  const handleCancel = async () => {
    const keyToCancel = activeDownloadKey || selectedModel?.model_key;
    if (!keyToCancel) return;
    clearPolling();
    try {
      await ModelsClient.cancelDownload(keyToCancel);
    } catch {
      // Ignored
    }
    setFlowState('not_installed');
    setProgress(null);
    setIsPaused(false);
    setActiveDownloadKey(null);
    setActiveDownloadLabel('');
  };

  // Helper values for System RAM
  const getSystemRamTotalMb = (): number => {
    if (hardware?.memory?.total_mb && !isNaN(hardware.memory.total_mb)) {
      return hardware.memory.total_mb;
    }
    if (hardware?.ram_total_mb && !isNaN(hardware.ram_total_mb)) {
      return hardware.ram_total_mb;
    }
    return 0;
  };

  const displayRamTotal = () => {
    const mb = getSystemRamTotalMb();
    if (mb <= 0) return 'Detecting...';
    return `${Math.round(mb / 1024)} GB`;
  };

  const displayModelRamRequired = () => {
    if (!selectedModel) return '~4 GB';
    if (selectedModel.ram_required_mb && selectedModel.ram_required_mb > 0) {
      const gb = (selectedModel.ram_required_mb / 1024).toFixed(1).replace('.0', '');
      return `~${gb} GB`;
    }
    return '~4 GB';
  };

  const hasEnoughRam = (): boolean => {
    const totalMb = getSystemRamTotalMb();
    if (totalMb <= 0) return true; // graceful fallback if detection pending
    const reqMb = selectedModel?.ram_required_mb || 2048;
    return totalMb >= reqMb;
  };

  // Helper values for Disk Storage
  const getDiskAvailableMb = (): number => {
    if (hardware?.storage?.available_mb && !isNaN(hardware.storage.available_mb)) {
      return hardware.storage.available_mb;
    }
    return 0;
  };

  const displayDiskStorageAvailable = () => {
    const mb = getDiskAvailableMb();
    if (mb <= 0) return 'Checking...';
    return `${Math.round(mb / 1024)} GB`;
  };

  // Storage required accounts for missing models (embedding + generation) + safe reserve headroom
  const getStorageRequiredMb = (): number => {
    let totalBytes = 0;

    // Check embedding model
    const embeddingSpec = catalog.find((m) => m.category === 'embeddings' || m.category === 'embedding');
    const embeddingKey = embeddingSpec?.model_key || 'bge-small-en-v1.5:onnx:default-v1';
    const isEmbReady = installedModels.some((inst) => inst.model_key === embeddingKey && inst.status === 'ready');
    if (!isEmbReady) {
      totalBytes += embeddingSpec?.size_bytes || 133093490; // ~127 MB
    }

    // Check generation model
    if (selectedModel) {
      const isGenReady = installedModels.some((inst) => inst.model_key === selectedModel.model_key && inst.status === 'ready');
      if (!isGenReady) {
        totalBytes += selectedModel.size_bytes || 1117320736;
      }
    }

    if (totalBytes === 0) return 0;

    const totalMb = Math.ceil(totalBytes / (1024 * 1024));
    // Include 100 MB buffer for .part download metadata & fsync
    return totalMb + 100;
  };

  const displayModelStorageRequired = () => {
    const mb = getStorageRequiredMb();
    if (mb <= 0) return '0 MB';
    if (mb >= 1024) {
      return `~${(mb / 1024).toFixed(1)} GB`;
    }
    return `~${mb} MB`;
  };

  const hasEnoughStorage = (): boolean => {
    const availMb = getDiskAvailableMb();
    if (availMb <= 0) return true; // Fallback to allowing user attempt if query still pending
    // Real peak preflight disk check: required size + temporary reserve
    const reqMb = getStorageRequiredMb();
    return availMb >= reqMb;
  };

  // VRAM Information
  const displayVramStatus = () => {
    if (hardware?.gpu && hardware.gpu.vram_mb > 0) {
      const vramGb = Math.round(hardware.gpu.vram_mb / 1024);
      return `${vramGb} GB available (Optional for CPU runtime)`;
    }
    return 'Not required for CPU runtime';
  };

  const displayPlatformTier = () => {
    const tier = hardware?.hardware_tier || hardware?.final_tier;
    if (!tier) return 'Detecting...';
    return tier.charAt(0).toUpperCase() + tier.slice(1);
  };

  const displayAvx = () => {
    if (hardware?.cpu?.avx2 !== undefined) {
      return hardware.cpu.avx2 ? 'Enabled' : 'Disabled';
    }
    if (hardware?.supports_avx2 !== undefined) {
      return hardware.supports_avx2 ? 'Enabled' : 'Disabled';
    }
    return 'Detecting...';
  };

  // Overall compatibility determination
  const isCompatible = hasEnoughRam() && hasEnoughStorage();

  return (
    <div
      className="glass-card"
      style={{
        display: 'flex',
        width: '100%',
        maxWidth: 940,
        padding: 0,
        overflow: 'hidden',
        borderRadius: 24,
        border: '1px solid rgba(15, 23, 42, 0.08)',
        boxShadow: '0 20px 60px -12px rgba(15, 23, 42, 0.12)',
        background: '#FFFFFF',
      }}
    >
      {/* Left Column: Stepper matching Onboarding Panel */}
      <div
        style={{
          flex: '1 1 36%',
          background: 'linear-gradient(145deg, #EFF6FF 0%, #EDE9FE 50%, #F1F5F9 100%)',
          padding: '44px 32px',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          borderRight: '1px solid rgba(15, 23, 42, 0.06)',
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 32 }}>
            <img
              src={raggerBoxLogo}
              alt="Ragger Logo"
              style={{ width: 32, height: 32, borderRadius: 8, objectFit: 'contain' }}
            />
            <img
              src={raggerFullLogo}
              alt="Ragger.ai"
              style={{ height: 26, objectFit: 'contain' }}
            />
          </div>

          <h2 style={{ fontSize: 22, fontWeight: 800, color: '#0F172A', letterSpacing: '-0.02em', marginBottom: 8 }}>
            Prepare Your AI Workspace
          </h2>
          <p style={{ fontSize: 13, color: '#64748B', lineHeight: 1.5, marginBottom: 36 }}>
            Run AI models locally. Internet is only required to download your chosen model.
          </p>

          {/* Stepper with Step 1 completed, Step 2 active, Step 3 next */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            {/* Step 1: Create Account (Completed) */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
              <div
                style={{
                  width: 28,
                  height: 28,
                  borderRadius: '50%',
                  background: '#10B981',
                  color: '#FFFFFF',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 12,
                  fontWeight: 700,
                }}
              >
                <Check size={14} strokeWidth={3} />
              </div>
              <div>
                <span style={{ fontSize: 13, fontWeight: 700, color: '#0F172A', display: 'block' }}>
                  Create Account
                </span>
                <span style={{ fontSize: 11, color: '#10B981', fontWeight: 600 }}>Completed</span>
              </div>
            </div>

            {/* Step 2: Setup Workspace (Active) */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
              <div
                style={{
                  width: 28,
                  height: 28,
                  borderRadius: '50%',
                  background: '#0F172A',
                  color: '#FFFFFF',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 12,
                  fontWeight: 700,
                  boxShadow: '0 0 0 3px rgba(15, 23, 42, 0.15)',
                }}
              >
                2
              </div>
              <div>
                <span style={{ fontSize: 13, fontWeight: 700, color: '#0F172A', display: 'block' }}>
                  Setup Workspace
                </span>
                <span style={{ fontSize: 11, color: '#2563EB', fontWeight: 600 }}>
                  {flowState === 'ready' ? 'Ready' : 'In Progress'}
                </span>
              </div>
            </div>

            {/* Step 3: Build Your First RAG (Next) */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
              <div
                style={{
                  width: 28,
                  height: 28,
                  borderRadius: '50%',
                  background: '#E2E8F0',
                  color: '#64748B',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 12,
                  fontWeight: 600,
                }}
              >
                3
              </div>
              <span style={{ fontSize: 13, fontWeight: 500, color: '#64748B' }}>
                Build Your First RAG
              </span>
            </div>
          </div>
        </div>

        <div style={{ fontSize: 11, color: '#64748B', display: 'flex', alignItems: 'center', gap: 6 }}>
          <ShieldCheck size={14} color="#10B981" />
          <span>Local execution · Zero model weights bundled in installer</span>
        </div>
      </div>

      {/* Right Column: Setup Workspace Content */}
      <div
        style={{
          flex: '1 1 64%',
          background: '#FFFFFF',
          padding: '36px 34px',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          minHeight: 560,
        }}
      >
        <div>
          {/* Header */}
          <div style={{ marginBottom: 16 }}>
            <h3 style={{ fontSize: 22, fontWeight: 800, color: '#0F172A', marginBottom: 4 }}>
              Welcome to Ragger.ai
            </h3>
            <p style={{ fontSize: 13, color: '#64748B' }}>
              Let's prepare your private AI workspace. Everything runs locally on this device.
            </p>
          </div>

          {/* HARDWARE & STORAGE PANEL */}
          <div
            style={{
              background: '#F8FAFC',
              borderRadius: 14,
              padding: '14px 16px',
              border: '1px solid #E2E8F0',
              marginBottom: 14,
            }}
          >
            <div
              style={{
                fontSize: 11,
                fontWeight: 700,
                textTransform: 'uppercase',
                letterSpacing: '0.04em',
                color: '#64748B',
                marginBottom: 10,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <Cpu size={13} />
                <span>Hardware & Storage</span>
              </div>
              <span style={{ fontSize: 11, fontWeight: 600, color: '#64748B' }}>
                Tier: <strong style={{ color: '#0F172A' }}>{displayPlatformTier()}</strong> · AVX2:{' '}
                <strong style={{ color: hardware?.cpu?.avx2 || hardware?.supports_avx2 ? '#10B981' : '#64748B' }}>
                  {displayAvx()}
                </strong>
              </span>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
              {/* System RAM */}
              <div style={{ background: '#FFFFFF', padding: '10px 12px', borderRadius: 10, border: '1px solid #E2E8F0' }}>
                <span style={{ fontSize: 11, color: '#64748B', display: 'block', marginBottom: 2 }}>System RAM</span>
                <div style={{ fontSize: 14, fontWeight: 700, color: '#0F172A' }}>
                  {displayRamTotal()}
                </div>
                <div style={{ fontSize: 11, color: hasEnoughRam() ? '#059669' : '#DC2626', marginTop: 2 }}>
                  {displayModelRamRequired()} required
                </div>
              </div>

              {/* Disk Storage */}
              <div style={{ background: '#FFFFFF', padding: '10px 12px', borderRadius: 10, border: '1px solid #E2E8F0' }}>
                <span style={{ fontSize: 11, color: '#64748B', display: 'block', marginBottom: 2 }}>
                  <HardDrive size={11} style={{ display: 'inline', marginRight: 4 }} />
                  Disk Storage
                </span>
                <div style={{ fontSize: 14, fontWeight: 700, color: '#0F172A' }}>
                  {displayDiskStorageAvailable()} free
                </div>
                <div style={{ fontSize: 11, color: hasEnoughStorage() ? '#059669' : '#DC2626', marginTop: 2 }}>
                  {displayModelStorageRequired()} required
                </div>
              </div>

              {/* GPU VRAM */}
              <div style={{ background: '#FFFFFF', padding: '10px 12px', borderRadius: 10, border: '1px solid #E2E8F0' }}>
                <span style={{ fontSize: 11, color: '#64748B', display: 'block', marginBottom: 2 }}>GPU VRAM</span>
                <div style={{ fontSize: 13, fontWeight: 700, color: '#0F172A', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {displayVramStatus()}
                </div>
                <div style={{ fontSize: 11, color: '#64748B', marginTop: 2 }}>
                  CPU inference ready
                </div>
              </div>
            </div>

            {/* Preflight Compatibility Badge */}
            <div style={{ marginTop: 10, display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 12 }}>
              {isCompatible ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#059669', fontWeight: 600 }}>
                  <Check size={14} strokeWidth={2.5} />
                  <span>✓ Compatible with this device</span>
                </div>
              ) : !hasEnoughStorage ? (
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#DC2626', fontWeight: 600 }}>
                  <AlertTriangle size={14} />
                  <span>⚠ Insufficient disk space on model storage volume</span>
                </div>
              ) : (
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#DC2626', fontWeight: 600 }}>
                  <AlertTriangle size={14} />
                  <span>⚠ System memory is below recommended threshold</span>
                </div>
              )}

              <span style={{ fontSize: 11, color: '#94A3B8' }}>
                %LOCALAPPDATA%\RaggerAI\storage\models
              </span>
            </div>
          </div>

          {/* Embedded Model Checklist Bar */}
          {(() => {
            const embeddingSpec = catalog.find((m) => m.category === 'embeddings' || m.category === 'embedding');
            const embeddingKey = embeddingSpec?.model_key || 'bge-small-en-v1.5:onnx:default-v1';
            const isEmbReady = installedModels.some((inst) => inst.model_key === embeddingKey && inst.status === 'ready');
            const isEmbActive = activeDownloadKey === embeddingKey;

            return (
              <div
                style={{
                  background: '#F8FAFC',
                  borderRadius: 12,
                  padding: '9px 14px',
                  border: isEmbActive ? '1px solid #3B82F6' : '1px solid #E2E8F0',
                  marginBottom: 14,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  transition: 'all 200ms ease',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div
                    style={{
                      width: 22,
                      height: 22,
                      borderRadius: '50%',
                      background: isEmbReady ? '#ECFDF5' : isEmbActive ? '#EFF6FF' : '#F1F5F9',
                      color: isEmbReady ? '#059669' : isEmbActive ? '#2563EB' : '#94A3B8',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    {isEmbReady ? (
                      <Check size={13} strokeWidth={2.5} />
                    ) : isEmbActive ? (
                      <RefreshCw size={12} className="spin-animation" />
                    ) : (
                      <Download size={12} />
                    )}
                  </div>
                  <div>
                    <span style={{ fontSize: 12, fontWeight: 700, color: '#0F172A', display: 'block' }}>
                      Embedding Model: BGE Small v1.5
                    </span>
                    <span style={{ fontSize: 11, color: '#64748B' }}>
                      Local ONNX Dense Retrieval Vectorizer · ~127 MB
                    </span>
                  </div>
                </div>
                {isEmbReady ? (
                  <span className="badge-pill badge-pill-green" style={{ padding: '3px 10px', fontSize: 11 }}>
                    Ready
                  </span>
                ) : isEmbActive ? (
                  <span className="badge-pill badge-pill-blue" style={{ padding: '3px 10px', fontSize: 11 }}>
                    Downloading...
                  </span>
                ) : (
                  <span className="badge-pill" style={{ padding: '3px 10px', fontSize: 11, background: '#F1F5F9', color: '#64748B' }}>
                    Pending Setup
                  </span>
                )}
              </div>
            );
          })()}

          {/* Main Card: Recommended Generation Model / Download / Verification Flow */}
          <div
            style={{
              borderRadius: 16,
              border: flowState === 'ready' ? '1.5px solid #10B981' : '1.5px solid #E2E8F0',
              background: flowState === 'ready' ? '#F0FDF4' : '#FFFFFF',
              padding: '18px 20px',
              boxShadow: '0 4px 16px rgba(15, 23, 42, 0.04)',
              marginBottom: 14,
              transition: 'all 200ms ease',
            }}
          >
            {/* Header label */}
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: 8,
              }}
            >
              <span
                style={{
                  fontSize: 11,
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  letterSpacing: '0.04em',
                  color: flowState === 'ready' ? '#059669' : '#4F46E5',
                }}
              >
                {flowState === 'ready'
                  ? '✓ Local AI Ready'
                  : flowState === 'downloading'
                  ? 'Downloading Local AI Model...'
                  : flowState === 'verifying'
                  ? 'Verifying Model Integrity...'
                  : flowState === 'activating'
                  ? 'Activating Model...'
                  : 'Recommended Local AI'}
              </span>

              {flowState === 'not_installed' && (
                <button
                  type="button"
                  onClick={() => setShowModelPicker(true)}
                  style={{
                    fontSize: 12,
                    color: '#2563EB',
                    background: 'none',
                    border: 'none',
                    cursor: 'pointer',
                    fontWeight: 600,
                    padding: '2px 6px',
                  }}
                >
                  Choose another model
                </button>
              )}
            </div>

            {/* Model Name and Metadata */}
            <div style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 17, fontWeight: 800, color: '#0F172A', marginBottom: 2 }}>
                {selectedModel ? selectedModel.model_id : 'Qwen 2.5 1.5B Instruct'}
              </div>
              <div style={{ fontSize: 12, color: '#64748B' }}>
                {selectedModel?.description || 'Lightweight local conversational model'} ·{' '}
                <span style={{ fontWeight: 600, color: '#334155' }}>
                  Download size: ~{selectedModel ? formatBytes(selectedModel.size_bytes) : '1.1 GB'}
                </span>
              </div>
            </div>

            {/* Features checklist when in Not Installed State */}
            {flowState === 'not_installed' && (
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(2, 1fr)',
                  gap: '6px 12px',
                  margin: '10px 0 14px',
                  fontSize: 12,
                  color: '#475569',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Check size={13} color="#10B981" />
                  <span>Runs 100% locally</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Check size={13} color="#10B981" />
                  <span>Suitable for this hardware</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Check size={13} color="#10B981" />
                  <span>Grounded RAG answers</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <Check size={13} color="#10B981" />
                  <span>Zero internet needed after setup</span>
                </div>
              </div>
            )}

            {/* DOWNLOADING STATE: Real Progress Bar and Telemetry */}
            {flowState === 'downloading' && (
              <div style={{ marginTop: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 6 }}>
                  <span style={{ fontWeight: 600, color: '#0F172A' }}>
                    {isPaused
                      ? `Paused: ${activeDownloadLabel || 'model download'}`
                      : `Downloading: ${activeDownloadLabel || 'model weights...'}`}
                  </span>
                  <span style={{ fontWeight: 700, color: '#2563EB' }}>
                    {progress ? `${Math.round(progress.percent)}%` : '0%'}
                  </span>
                </div>

                {/* Progress bar track */}
                <div
                  style={{
                    height: 8,
                    background: '#E2E8F0',
                    borderRadius: 999,
                    overflow: 'hidden',
                    marginBottom: 10,
                  }}
                >
                  <div
                    style={{
                      height: '100%',
                      width: `${progress ? Math.min(100, Math.max(2, progress.percent)) : 2}%`,
                      background: isPaused ? '#94A3B8' : 'linear-gradient(90deg, #3B82F6, #4F46E5)',
                      borderRadius: 999,
                      transition: 'width 200ms ease',
                    }}
                  />
                </div>

                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    fontSize: 11,
                    color: '#64748B',
                  }}
                >
                  <span>
                    {progress
                      ? `${formatBytes(progress.bytes_downloaded)} / ${formatBytes(progress.bytes_total)}`
                      : 'Connecting...'}
                    {progress?.speed_bytes_per_sec && progress.speed_bytes_per_sec > 0
                      ? ` (${formatBytes(progress.speed_bytes_per_sec)}/s)`
                      : ''}
                  </span>

                  <div style={{ display: 'flex', gap: 8 }}>
                    {isPaused ? (
                      <button
                        type="button"
                        onClick={handleResume}
                        className="btn-secondary"
                        style={{ padding: '4px 10px', fontSize: 11 }}
                      >
                        <Play size={11} />
                        <span>Resume</span>
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={handlePause}
                        className="btn-secondary"
                        style={{ padding: '4px 10px', fontSize: 11 }}
                      >
                        <Pause size={11} />
                        <span>Pause</span>
                      </button>
                    )}

                    <button
                      type="button"
                      onClick={handleCancel}
                      className="btn-secondary"
                      style={{ padding: '4px 10px', fontSize: 11, color: '#EF4444' }}
                    >
                      <X size={11} />
                      <span>Cancel</span>
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* VERIFYING / ACTIVATING STATE */}
            {(flowState === 'verifying' || flowState === 'activating') && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  marginTop: 12,
                  padding: '12px 14px',
                  background: '#F8FAFC',
                  borderRadius: 10,
                }}
              >
                <RefreshCw size={18} className="spin-animation" color="#4F46E5" />
                <div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: '#0F172A' }}>
                    {statusMessage}
                  </div>
                  <div style={{ fontSize: 11, color: '#64748B' }}>
                    Validating cryptographic SHA-256 integrity and setting up runtime environment.
                  </div>
                </div>
              </div>
            )}

            {/* READY STATE */}
            {flowState === 'ready' && (
              <div style={{ marginTop: 8, fontSize: 12, color: '#065F46' }}>
                Your selected AI model is installed locally on this device. Everything runs completely
                offline.
              </div>
            )}
          </div>

          {/* Failure message with Retry */}
          {errorMessage && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '10px 14px',
                borderRadius: 12,
                background: '#FEF2F2',
                border: '1px solid #FECACA',
                color: '#DC2626',
                fontSize: 12,
                marginBottom: 12,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <AlertCircle size={16} />
                <span>{errorMessage}</span>
              </div>
              <button
                type="button"
                onClick={handleStartDownload}
                className="btn-secondary"
                style={{ padding: '4px 12px', fontSize: 11, borderColor: '#F87171' }}
              >
                <RefreshCw size={12} />
                <span>Retry</span>
              </button>
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div>
          <div
            style={{
              fontSize: 11,
              color: '#94A3B8',
              textAlign: 'center',
              marginBottom: 12,
            }}
          >
            {flowState === 'ready'
              ? 'Local AI workspace prepared.'
              : 'Internet connection required only during model download.'}
          </div>

          {flowState === 'ready' ? (
            <button
              type="button"
              id="btn-setup-continue"
              onClick={onComplete}
              className="btn-primary"
              style={{ width: '100%', padding: '13px', fontSize: 15 }}
            >
              <span>Continue to Workspace</span>
              <ArrowRight size={16} />
            </button>
          ) : (
            <button
              type="button"
              id="btn-setup-download"
              disabled={
                flowState === 'downloading' ||
                flowState === 'verifying' ||
                flowState === 'activating' ||
                !hasEnoughStorage
              }
              onClick={handleStartDownload}
              className="btn-primary"
              style={{
                width: '100%',
                padding: '13px',
                fontSize: 15,
                opacity: !hasEnoughStorage ? 0.6 : 1,
                cursor: !hasEnoughStorage ? 'not-allowed' : 'pointer',
              }}
            >
              <Download size={16} />
              <span>
                {!hasEnoughStorage ? 'Not enough disk space for this model' : 'Download & Continue'}
              </span>
            </button>
          )}
        </div>
      </div>

      {/* Model Selection Modal ("Choose another model") */}
      {showModelPicker && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15, 23, 42, 0.45)',
            backdropFilter: 'blur(4px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999,
            padding: 20,
          }}
          onClick={() => setShowModelPicker(false)}
        >
          <div
            style={{
              background: '#FFFFFF',
              borderRadius: 20,
              width: '100%',
              maxWidth: 580,
              padding: '28px 30px',
              boxShadow: '0 25px 60px -15px rgba(15, 23, 42, 0.25)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <div>
                <h3 style={{ fontSize: 18, fontWeight: 800, color: '#0F172A', marginBottom: 2 }}>
                  Available Local Models
                </h3>
                <p style={{ fontSize: 12, color: '#64748B' }}>
                  Select a local conversational AI model compatible with your device.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowModelPicker(false)}
                style={{
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  color: '#64748B',
                  padding: 4,
                }}
              >
                <X size={18} />
              </button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, maxHeight: 380, overflowY: 'auto' }}>
              {catalog
                .filter((m) => m.category === 'generation')
                .map((m) => {
                  const isCurrent = selectedModel?.model_key === m.model_key;
                  const isInstalled = installedModels.some(
                    (inst) => inst.model_key === m.model_key && inst.status === 'ready'
                  );

                  return (
                    <div
                      key={m.model_key}
                      onClick={() => {
                        setSelectedModel(m);
                        setShowModelPicker(false);
                        if (isInstalled) {
                          setFlowState('ready');
                        } else {
                          setFlowState('not_installed');
                        }
                      }}
                      style={{
                        padding: '14px 16px',
                        borderRadius: 14,
                        border: isCurrent ? '2px solid #2563EB' : '1px solid #E2E8F0',
                        background: isCurrent ? '#EFF6FF' : '#FFFFFF',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        transition: 'all 120ms ease',
                      }}
                    >
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 2 }}>
                          <span style={{ fontSize: 14, fontWeight: 700, color: '#0F172A' }}>
                            {m.model_id}
                          </span>
                          {m.recommended && (
                            <span className="badge-pill badge-pill-blue" style={{ fontSize: 10, padding: '2px 8px' }}>
                              Recommended
                            </span>
                          )}
                          {isInstalled && (
                            <span className="badge-pill badge-pill-green" style={{ fontSize: 10, padding: '2px 8px' }}>
                              Installed
                            </span>
                          )}
                        </div>
                        <div style={{ fontSize: 12, color: '#64748B' }}>
                          {m.description} · <span style={{ fontWeight: 600 }}>~{formatBytes(m.size_bytes)}</span>
                        </div>
                      </div>

                      <button
                        type="button"
                        className={isCurrent ? 'btn-primary' : 'btn-secondary'}
                        style={{ padding: '6px 14px', fontSize: 12, flexShrink: 0 }}
                      >
                        {isCurrent ? 'Selected' : 'Select'}
                      </button>
                    </div>
                  );
                })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
