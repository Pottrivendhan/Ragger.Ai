import React, { useState } from 'react';
import {
  Download,
  CheckCircle2,
  Info,
  ChevronLeft,
} from 'lucide-react';
import { ModelsClient } from '../../services/modelsClient';

interface ModelHubViewProps {
  modelsClient?: ModelsClient;
  onBackToHome?: () => void;
}

export const ModelHubView: React.FC<ModelHubViewProps> = ({ onBackToHome }) => {
  const [downloadingKey, setDownloadingKey] = useState<string | null>(null);
  const [installedKeys, setInstalledKeys] = useState<string[]>(['bge-small']);

  const models = [
    {
      key: 'phi-3-mini',
      name: 'Phi-3 Mini (3.8B)',
      tagline: 'Lightweight · Fast · Recommended',
      size: '2.1 GB',
    },
    {
      key: 'llama-3.2-3b',
      name: 'Llama 3.2 (3B)',
      tagline: 'General purpose',
      size: '2.0 GB',
    },
    {
      key: 'mistral-7b',
      name: 'Mistral 7B Instruct',
      tagline: 'High quality responses',
      size: '4.1 GB',
    },
    {
      key: 'bge-small',
      name: 'BGE Small v1.5 (384-dim)',
      tagline: 'High-speed local dense vector encoder',
      size: '133 MB',
    },
  ];

  const handleDownload = (key: string) => {
    setDownloadingKey(key);
    setTimeout(() => {
      setDownloadingKey(null);
      setInstalledKeys((prev) => [...prev, key]);
    }, 1500);
  };

  return (
    <div style={{ padding: '0 0 60px 0', width: '100%' }}>
      {/* Top Bar */}
      <div className="top-app-bar">
        <button
          onClick={onBackToHome}
          id="btn-models-back"
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
          <span>Model Hub</span>
        </button>
      </div>

      <div style={{ maxWidth: 880, margin: '32px auto 0', padding: '0 24px' }}>
        {/* Header (Panel 10 Reference) */}
        <div style={{ marginBottom: 32 }}>
          <h1 style={{ fontSize: 28, fontWeight: 800, color: '#0F172A', letterSpacing: '-0.02em', marginBottom: 4 }}>
            Local Models
          </h1>
          <p style={{ fontSize: 14, color: '#64748B' }}>
            Download and use models locally. No internet required.
          </p>
        </div>

        {/* Models List (Panel 10 Reference) */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginBottom: 36 }}>
          {models.map((m) => {
            const isInstalled = installedKeys.includes(m.key);
            const isDownloading = downloadingKey === m.key;

            return (
              <div
                key={m.key}
                className="glass-card"
                style={{
                  background: '#FFFFFF',
                  padding: '20px 24px',
                  borderRadius: 16,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  border: '1px solid rgba(15, 23, 42, 0.07)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                  <div
                    style={{
                      width: 40,
                      height: 40,
                      borderRadius: 10,
                      background: isInstalled ? '#ECFDF5' : '#F1F5F9',
                      color: isInstalled ? '#059669' : '#475569',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    {isInstalled ? <CheckCircle2 size={20} /> : <Download size={20} />}
                  </div>

                  <div>
                    <h3 style={{ fontSize: 15, fontWeight: 700, color: '#0F172A', marginBottom: 2 }}>
                      {m.name}
                    </h3>
                    <div style={{ fontSize: 12, color: '#64748B' }}>
                      {m.tagline} · <span style={{ color: '#94A3B8' }}>{m.size}</span>
                    </div>
                  </div>
                </div>

                <div>
                  {isInstalled ? (
                    <span className="badge-pill badge-pill-green" style={{ padding: '6px 14px' }}>
                      Active
                    </span>
                  ) : (
                    <button
                      onClick={() => handleDownload(m.key)}
                      disabled={isDownloading}
                      className="btn-secondary"
                      style={{ padding: '8px 18px', fontSize: 13 }}
                    >
                      <Download size={14} />
                      <span>{isDownloading ? 'Downloading...' : 'Download'}</span>
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Tip Banner (Panel 10 Reference) */}
        <div
          className="glass-card"
          style={{
            background: 'rgba(239, 246, 255, 0.8)',
            border: '1px solid rgba(59, 130, 246, 0.15)',
            borderRadius: 16,
            padding: '20px 24px',
            display: 'flex',
            alignItems: 'flex-start',
            gap: 14,
          }}
        >
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: '50%',
              background: '#DBEAFE',
              color: '#2563EB',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
              marginTop: 2,
            }}
          >
            <Info size={18} />
          </div>

          <div>
            <h4 style={{ fontSize: 14, fontWeight: 700, color: '#1E3A8A', marginBottom: 2 }}>
              No models bundled in setup
            </h4>
            <p style={{ fontSize: 12, color: '#3B82F6', lineHeight: 1.5 }}>
              Models are downloaded separately to give you flexibility and keep the installer lightweight.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
