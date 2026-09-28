import React, { useState, useRef } from 'react';
import {
  X,
  Download,
  Upload,
  CheckCircle2,
  Package,
  FileCheck,
  AlertCircle,
} from 'lucide-react';
import { RAGLifecycleClient } from '../../services/ragLifecycleClient';

interface ExportImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  kbTitle?: string;
  ragId?: string;
  defaultTab?: 'export' | 'import';
  onImportComplete?: () => void;
}

export const ExportImportModal: React.FC<ExportImportModalProps> = ({
  isOpen,
  onClose,
  kbTitle = 'Class 10 English',
  ragId = 'rag_class10_english',
  defaultTab = 'export',
  onImportComplete,
}) => {
  const [client] = useState(() => new RAGLifecycleClient());
  const [tab, setTab] = useState<'export' | 'import'>(defaultTab);
  const [exporting, setExporting] = useState(false);
  const [exportDone, setExportDone] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const [importing, setImporting] = useState(false);
  const [importDone, setImportDone] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  if (!isOpen) return null;

  const handleExport = async () => {
    setExporting(true);
    setExportError(null);
    try {
      await client.exportRagpack(ragId);
      setExporting(false);
      setExportDone(true);
    } catch (err: any) {
      setExporting(false);
      setExportError(err.message || 'Export failed');
    }
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setImporting(true);
    setImportError(null);
    try {
      await client.importRagpack(file);
      setImporting(false);
      setImportDone(true);
      if (onImportComplete) onImportComplete();
    } catch (err: any) {
      setImporting(false);
      setImportError(err.message || 'Import verification failed');
    }
  };

  return (
    <div className="source-drawer-backdrop" onClick={onClose} style={{ alignItems: 'center', justifyContent: 'center' }}>
      <div
        className="glass-card"
        onClick={(e) => e.stopPropagation()}
        style={{ width: '100%', maxWidth: 520, padding: 32, background: '#FFFFFF' }}
      >
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ width: 36, height: 36, borderRadius: 10, background: 'rgba(79, 70, 229, 0.08)', color: '#4F46E5', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Package size={20} />
            </div>
            <div>
              <h3 style={{ fontSize: 18, fontWeight: 700, color: '#0F172A' }}>
                Portable .ragger Package
              </h3>
              <span style={{ fontSize: 12, color: '#64748B' }}>
                Versioned knowledge base artifact
              </span>
            </div>
          </div>
          <button onClick={onClose} style={{ color: '#94A3B8', padding: 6 }}>
            <X size={20} />
          </button>
        </div>

        {/* Tab Toggle */}
        <div style={{ display: 'flex', background: '#F1F5F9', borderRadius: 10, padding: 3, marginBottom: 24 }}>
          <button
            onClick={() => { setTab('export'); setExportDone(false); }}
            style={{
              flex: 1,
              padding: '8px 12px',
              borderRadius: 8,
              fontSize: 13,
              fontWeight: 600,
              background: tab === 'export' ? '#FFFFFF' : 'transparent',
              color: tab === 'export' ? '#0F172A' : '#64748B',
              boxShadow: tab === 'export' ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
            }}
          >
            Export .ragger
          </button>
          <button
            onClick={() => { setTab('import'); setImportDone(false); }}
            style={{
              flex: 1,
              padding: '8px 12px',
              borderRadius: 8,
              fontSize: 13,
              fontWeight: 600,
              background: tab === 'import' ? '#FFFFFF' : 'transparent',
              color: tab === 'import' ? '#0F172A' : '#64748B',
              boxShadow: tab === 'import' ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
            }}
          >
            Import .ragger
          </button>
        </div>

        {/* Export Tab */}
        {tab === 'export' && (
          <div>
            <div style={{ background: '#F8FAFC', borderRadius: 12, padding: 18, border: '1px solid rgba(15, 23, 42, 0.06)', marginBottom: 20 }}>
              <span style={{ fontSize: 11, fontWeight: 700, color: '#4F46E5', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Selected Knowledge Base
              </span>
              <h4 style={{ fontSize: 16, fontWeight: 700, color: '#0F172A', marginTop: 2, marginBottom: 12 }}>
                {kbTitle}
              </h4>

              <div style={{ fontSize: 13, color: '#475569', display: 'flex', flexDirection: 'column', gap: 6 }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <CheckCircle2 size={14} color="#10B981" />
                  <span>Knowledge index & dense vectors</span>
                </span>
                <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <CheckCircle2 size={14} color="#10B981" />
                  <span>Retrieval configuration & BM25 sparse index</span>
                </span>
                <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <CheckCircle2 size={14} color="#10B981" />
                  <span>Source metadata & page provenance</span>
                </span>
                <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <CheckCircle2 size={14} color="#10B981" />
                  <span>Build manifest & cryptographic seals</span>
                </span>
              </div>
            </div>

            <p style={{ fontSize: 12, color: '#94A3B8', marginBottom: 20 }}>
              Note: Model weights (GGUF/ONNX) remain separate and are not bundled inside the .ragger package.
            </p>

            {exportError && (
              <div style={{ padding: '8px 12px', borderRadius: 8, background: '#FEF2F2', color: '#B91C1C', fontSize: 12, marginBottom: 16, display: 'flex', alignItems: 'center', gap: 6 }}>
                <AlertCircle size={14} />
                <span>{exportError}</span>
              </div>
            )}

            <button
              onClick={handleExport}
              className="btn-primary"
              style={{ width: '100%', padding: '12px' }}
              disabled={exporting || exportDone}
              id="btn-confirm-export-ragger"
            >
              <Download size={16} />
              <span>{exporting ? 'Packaging .ragpack...' : exportDone ? 'Package Exported!' : `Export ${kbTitle}.ragpack`}</span>
            </button>
          </div>
        )}

        {/* Import Tab */}
        {tab === 'import' && (
          <div>
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileChange}
              accept=".ragpack,.zip"
              style={{ display: 'none' }}
            />
            <div
              className="dropzone-area"
              onClick={() => fileInputRef.current?.click()}
              style={{ padding: '32px 16px', marginBottom: 20, cursor: 'pointer' }}
            >
              <Upload size={32} color="#4F46E5" style={{ marginBottom: 12 }} />
              <span style={{ fontSize: 14, fontWeight: 700, color: '#0F172A', display: 'block' }}>
                Drop a .ragpack bundle here
              </span>
              <span style={{ fontSize: 12, color: '#64748B', marginTop: 4 }}>
                Or click to choose a knowledge package file
              </span>
            </div>

            <div style={{ fontSize: 12, color: '#64748B', marginBottom: 20 }}>
              <span style={{ fontWeight: 600, color: '#0F172A', display: 'block', marginBottom: 4 }}>
                Verification protocol:
              </span>
              <span>We will verify manifest integrity, path traversal safety, schema version, and lance indices.</span>
            </div>

            {importError && (
              <div style={{ padding: '8px 12px', borderRadius: 8, background: '#FEF2F2', color: '#B91C1C', fontSize: 12, marginBottom: 16, display: 'flex', alignItems: 'center', gap: 6 }}>
                <AlertCircle size={14} />
                <span>{importError}</span>
              </div>
            )}

            <button
              onClick={() => fileInputRef.current?.click()}
              className="btn-primary"
              style={{ width: '100%', padding: '12px' }}
              disabled={importing || importDone}
              id="btn-choose-ragpack-file"
            >
              <FileCheck size={16} />
              <span>{importing ? 'Verifying Package...' : importDone ? 'Imported Successfully!' : 'Choose .ragpack File'}</span>
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
