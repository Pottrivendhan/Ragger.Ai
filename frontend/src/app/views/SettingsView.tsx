import React, { useState } from 'react';
import {
  Shield,
  Key,
  HardDrive,
  Info,
  CheckCircle2,
  FolderOpen,
  User,
  Copy,
  Check,
} from 'lucide-react';
import { AuthSession, generateRecoveryCode } from '../../services/localAuth';

interface SettingsViewProps {
  session: AuthSession | null;
  initialSection?: 'account' | 'security' | 'storage' | 'about';
}

export const SettingsView: React.FC<SettingsViewProps> = ({ session, initialSection = 'account' }) => {
  const [activeSection, setActiveSection] = useState<'account' | 'security' | 'storage' | 'about'>(initialSection);
  const [newRecoveryCode, setNewRecoveryCode] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const handleGenerateNewRecovery = () => {
    const code = generateRecoveryCode();
    setNewRecoveryCode(code);
    alert('New recovery code generated. Please copy and save it safely offline.');
  };

  const handleCopyCode = () => {
    if (newRecoveryCode) {
      navigator.clipboard.writeText(newRecoveryCode);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div style={{ padding: '32px 36px', maxWidth: 840, margin: '0 auto', width: '100%', animation: 'pageSlideIn 300ms cubic-bezier(0.16, 1, 0.3, 1)' }}>
      <div className="page-header" style={{ marginBottom: 24 }}>
        <div>
          <h1 className="page-title">Settings</h1>
          <p className="page-subtitle">
            Manage your local account, offline security, storage footprint, and system preferences.
          </p>
        </div>
      </div>

      {/* Settings Navigation Bar */}
      <div style={{ display: 'flex', gap: 8, background: '#FFFFFF', padding: 4, borderRadius: 12, border: '1px solid rgba(15, 23, 42, 0.08)', marginBottom: 28 }}>
        {[
          { id: 'account', label: 'Account', icon: User },
          { id: 'security', label: 'Security & Recovery', icon: Shield },
          { id: 'storage', label: 'Storage', icon: HardDrive },
          { id: 'about', label: 'About', icon: Info },
        ].map((s) => {
          const Icon = s.icon;
          const isActive = activeSection === s.id;
          return (
            <button
              key={s.id}
              onClick={() => setActiveSection(s.id as any)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '8px 16px',
                borderRadius: 8,
                fontSize: 13,
                fontWeight: isActive ? 600 : 500,
                background: isActive ? '#F1F5F9' : 'transparent',
                color: isActive ? '#0F172A' : '#64748B',
              }}
            >
              <Icon size={16} color={isActive ? '#4F46E5' : '#94A3B8'} />
              <span>{s.label}</span>
            </button>
          );
        })}
      </div>

      {/* ---------------------------------------------------- */}
      {/* Account Section */}
      {/* ---------------------------------------------------- */}
      {activeSection === 'account' && (
        <div className="glass-card" style={{ padding: 28 }}>
          <h3 style={{ fontSize: 18, fontWeight: 700, color: '#0F172A', marginBottom: 20 }}>
            Local Profile
          </h3>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <div>
              <span style={{ fontSize: 12, color: '#94A3B8', display: 'block' }}>Account ID</span>
              <span style={{ fontSize: 13, fontWeight: 700, color: '#2563EB', fontFamily: 'monospace' }}>
                {session?.accountId || 'acc_default'}
              </span>
            </div>

            <div>
              <span style={{ fontSize: 12, color: '#94A3B8', display: 'block' }}>Full Name</span>
              <span style={{ fontSize: 15, fontWeight: 600, color: '#0F172A' }}>
                {session?.fullName || 'Local User'}
              </span>
            </div>

            <div>
              <span style={{ fontSize: 12, color: '#94A3B8', display: 'block' }}>Username</span>
              <span style={{ fontSize: 15, fontWeight: 600, color: '#0F172A' }}>
                {session?.username || 'user'}
              </span>
            </div>

            <div>
              <span style={{ fontSize: 12, color: '#94A3B8', display: 'block' }}>Account Type</span>
              <span style={{ fontSize: 14, color: '#10B981', fontWeight: 600, display: 'flex', alignItems: 'center', gap: 6, marginTop: 2 }}>
                <CheckCircle2 size={16} />
                100% Offline Local Account (Zero Cloud Dependency)
              </span>
            </div>
          </div>
        </div>
      )}

      {/* ---------------------------------------------------- */}
      {/* Security Section */}
      {/* ---------------------------------------------------- */}
      {activeSection === 'security' && (
        <div className="glass-card" style={{ padding: 28 }}>
          <h3 style={{ fontSize: 18, fontWeight: 700, color: '#0F172A', marginBottom: 6 }}>
            Security & Offline Password Recovery
          </h3>
          <p style={{ fontSize: 13, color: '#64748B', marginBottom: 24 }}>
            Because Ragger.ai is completely local, your recovery code is the only mechanism to reset your password without losing account access.
          </p>

          <div style={{ background: '#F8FAFC', padding: 20, borderRadius: 12, border: '1px solid rgba(15, 23, 42, 0.06)', marginBottom: 20 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div>
                <span style={{ fontSize: 14, fontWeight: 600, color: '#0F172A', display: 'block' }}>
                  Offline Recovery Code
                </span>
                <span style={{ fontSize: 12, color: '#64748B' }}>
                  Cryptographically verified salted hash stored locally
                </span>
              </div>
              <button onClick={handleGenerateNewRecovery} className="btn-secondary" style={{ fontSize: 13 }}>
                <Key size={14} />
                <span>Generate New Code</span>
              </button>
            </div>

            {newRecoveryCode && (
              <div style={{ marginTop: 16, paddingTop: 16, borderTop: '1px solid rgba(15, 23, 42, 0.08)' }}>
                <span style={{ fontSize: 12, fontWeight: 600, color: '#4F46E5', display: 'block', marginBottom: 6 }}>
                  New Offline Recovery Code (Save Safely):
                </span>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div className="recovery-code-display" style={{ margin: 0, flex: 1, padding: '10px 14px', fontSize: 15 }}>
                    {newRecoveryCode}
                  </div>
                  <button onClick={handleCopyCode} className="btn-secondary" style={{ padding: '10px 14px' }}>
                    {copied ? <Check size={16} /> : <Copy size={16} />}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ---------------------------------------------------- */}
      {/* Storage Section */}
      {/* ---------------------------------------------------- */}
      {activeSection === 'storage' && (
        <div className="glass-card" style={{ padding: 28 }}>
          <h3 style={{ fontSize: 18, fontWeight: 700, color: '#0F172A', marginBottom: 6 }}>
            Storage Footprint
          </h3>
          <p style={{ fontSize: 13, color: '#64748B', marginBottom: 24 }}>
            Overview of local disk space consumed by knowledge bases, dense vector stores, and models.
          </p>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16, marginBottom: 24 }}>
            <div style={{ background: '#F8FAFC', padding: 16, borderRadius: 12, border: '1px solid rgba(15, 23, 42, 0.06)' }}>
              <span style={{ fontSize: 11, color: '#94A3B8', display: 'block' }}>Knowledge Bases</span>
              <span style={{ fontSize: 18, fontWeight: 700, color: '#0F172A' }}>2.93 MB</span>
              <span style={{ fontSize: 11, color: '#64748B', display: 'block', marginTop: 2 }}>1,907 vectors</span>
            </div>

            <div style={{ background: '#F8FAFC', padding: 16, borderRadius: 12, border: '1px solid rgba(15, 23, 42, 0.06)' }}>
              <span style={{ fontSize: 11, color: '#94A3B8', display: 'block' }}>Model Weights</span>
              <span style={{ fontSize: 18, fontWeight: 700, color: '#0F172A' }}>133.1 MB</span>
              <span style={{ fontSize: 11, color: '#64748B', display: 'block', marginTop: 2 }}>BGE Small ONNX</span>
            </div>

            <div style={{ background: '#F8FAFC', padding: 16, borderRadius: 12, border: '1px solid rgba(15, 23, 42, 0.06)' }}>
              <span style={{ fontSize: 11, color: '#94A3B8', display: 'block' }}>Total Footprint</span>
              <span style={{ fontSize: 18, fontWeight: 700, color: '#4F46E5' }}>136.03 MB</span>
              <span style={{ fontSize: 11, color: '#64748B', display: 'block', marginTop: 2 }}>Compact local cache</span>
            </div>
          </div>

          <div style={{ paddingTop: 16, borderTop: '1px solid rgba(15, 23, 42, 0.07)' }}>
            <button
              onClick={() => alert('Storage directory is located in your local application directory: storage/')}
              className="btn-secondary"
              style={{ fontSize: 13 }}
            >
              <FolderOpen size={16} />
              <span>Open Storage Location</span>
            </button>
          </div>
        </div>
      )}

      {/* ---------------------------------------------------- */}
      {/* About Section */}
      {/* ---------------------------------------------------- */}
      {activeSection === 'about' && (
        <div className="glass-card" style={{ padding: 28 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 16 }}>
            <div className="brand-orb-icon" style={{ width: 44, height: 44, fontSize: 20 }}>R</div>
            <div>
              <h3 style={{ fontSize: 20, fontWeight: 800, color: '#0F172A' }}>Ragger.ai</h3>
              <span style={{ fontSize: 12, color: '#64748B' }}>Version 1.1 Commercial Local Release</span>
            </div>
          </div>

          <p style={{ fontSize: 14, color: '#475569', lineHeight: 1.6, marginBottom: 20 }}>
            Ragger.ai is a commercial-grade local-first RAG and AI knowledge platform. It enables organizations, researchers, and individuals to create portable knowledge artifacts (.ragger) from raw files, verify architecture recommendations, and run grounded conversational agents on consumer hardware with zero cloud telemetry.
          </p>

          <div style={{ fontSize: 12, color: '#94A3B8', paddingTop: 16, borderTop: '1px solid rgba(15, 23, 42, 0.07)' }}>
            <span>© 2026 Ragger.ai. All rights reserved. Zero telemetry invariant enforced.</span>
          </div>
        </div>
      )}
    </div>
  );
};
