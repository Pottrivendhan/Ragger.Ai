import React, { useState, useEffect, useRef } from 'react';
import {
  Plus,
  Search,
  ArrowRight,
  Bell,
  Database,
  BellOff,
} from 'lucide-react';
import { AuthSession } from '../../services/localAuth';
import { RAGLifecycleClient } from '../../services/ragLifecycleClient';
import { RAGArtifactRecord } from '../../types/ragLifecycle';
import { ProfileMenu } from '../components/ProfileMenu';
import raggerBoxLogo from '../../assets/ragger.ai_box_logo.png';

interface DashboardViewProps {
  session: AuthSession | null;
  onCreateRag: () => void;
  onOpenKnowledgeBase?: (kbId: string) => void;
  onOpenAgent: (kbId?: string) => void;
  onNavigateToSettings?: (section?: 'account' | 'security' | 'storage' | 'about') => void;
  onNavigateToLibrary?: () => void;
  onRequestLogout?: () => void;
}

export const DashboardView: React.FC<DashboardViewProps> = ({
  session,
  onCreateRag,
  onOpenKnowledgeBase,
  onOpenAgent,
  onNavigateToSettings,
  onNavigateToLibrary,
  onRequestLogout,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [rags, setRags] = useState<RAGArtifactRecord[]>([]);
  const [loading, setLoading] = useState(true);

  // Header popover states
  const [isNotificationsOpen, setIsNotificationsOpen] = useState(false);
  const [isProfileMenuOpen, setIsProfileMenuOpen] = useState(false);
  const notificationRef = useRef<HTMLDivElement>(null);
  const profileRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsNotificationsOpen(false);
        setIsProfileMenuOpen(false);
      }
    };

    const handleClickOutside = (e: MouseEvent) => {
      if (notificationRef.current && !notificationRef.current.contains(e.target as Node)) {
        setIsNotificationsOpen(false);
      }
      if (profileRef.current && !profileRef.current.contains(e.target as Node)) {
        setIsProfileMenuOpen(false);
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  useEffect(() => {
    const client = new RAGLifecycleClient();
    client.listRags().then((res) => {
      setRags(res);
    }).catch(() => {
      setRags([]);
    }).finally(() => {
      setLoading(false);
    });
  }, [session?.accountId]);

  const filteredProjects = rags.filter((p) =>
    p.name.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div style={{ padding: '0 0 40px 0', width: '100%' }}>
      {/* Top Bar (Panel 3 Reference) */}
      <div className="top-app-bar">
        <div
          onClick={() => {
            // Stay on home
          }}
          style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, fontWeight: 600, color: '#0F172A', cursor: 'default' }}
        >
          <span>Home</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 14, position: 'relative' }}>
          {/* Notification Bell */}
          <div ref={notificationRef} style={{ position: 'relative' }}>
            <button
              onClick={() => {
                setIsProfileMenuOpen(false);
                setIsNotificationsOpen((prev) => !prev);
              }}
              className="header-action-btn"
              aria-label="Notifications"
              aria-expanded={isNotificationsOpen}
              id="btn-header-notifications"
              title="Notifications"
            >
              <Bell size={18} />
            </button>

            {isNotificationsOpen && (
              <div
                className="header-popover-panel"
                style={{ width: 290, padding: 0 }}
                role="dialog"
                aria-label="Notification center"
                id="panel-notifications"
              >
                <div style={{ padding: '12px 16px', borderBottom: '1px solid #F1F5F9', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: 13, fontWeight: 700, color: '#0F172A' }}>Notifications</span>
                  <span style={{ fontSize: 11, fontWeight: 600, color: '#64748B' }}>0 unread</span>
                </div>
                <div style={{ padding: '28px 20px', textAlign: 'center' }}>
                  <div style={{ width: 40, height: 40, borderRadius: '50%', background: '#F8FAFC', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 10px', color: '#94A3B8' }}>
                    <BellOff size={18} />
                  </div>
                  <div style={{ fontSize: 13, fontWeight: 600, color: '#334155', marginBottom: 2 }}>
                    No notifications
                  </div>
                  <div style={{ fontSize: 11.5, color: '#94A3B8' }}>
                    You are completely up to date.
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* Profile / Avatar Button */}
          <div ref={profileRef} style={{ position: 'relative' }}>
            <button
              onClick={() => {
                setIsNotificationsOpen(false);
                setIsProfileMenuOpen((prev) => !prev);
              }}
              className="header-avatar-btn"
              aria-label="Open account menu"
              aria-expanded={isProfileMenuOpen}
              aria-haspopup="menu"
              id="btn-header-profile"
              title={session?.fullName || 'User Profile'}
            >
              {session?.fullName ? session.fullName[0].toUpperCase() : 'A'}
            </button>

            <ProfileMenu
              isOpen={isProfileMenuOpen}
              onClose={() => setIsProfileMenuOpen(false)}
              session={session}
              onNavigateToSettings={(section) => {
                setIsProfileMenuOpen(false);
                onNavigateToSettings?.(section);
              }}
              onRequestLogout={() => {
                setIsProfileMenuOpen(false);
                onRequestLogout?.();
              }}
              placement="down"
              triggerRef={profileRef}
            />
          </div>
        </div>
      </div>

      {/* Main Page Area */}
      <div style={{ padding: '32px 36px', maxWidth: 1200, margin: '0 auto' }}>
        {/* Header with Title and Create RAG button */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 24 }}>
          <div>
            <h1 style={{ fontSize: 28, fontWeight: 800, color: '#0F172A', letterSpacing: '-0.02em', marginBottom: 4 }}>
              Good morning,
            </h1>
            <p style={{ fontSize: 14, color: '#64748B' }}>
              Turn your data into real conversations.
            </p>
          </div>

          <button onClick={onCreateRag} className="btn-primary" style={{ padding: '10px 22px' }}>
            <Plus size={16} />
            <span>Create RAG</span>
          </button>
        </div>

        {/* Search Bar (Panel 3 Reference) */}
        <div style={{ position: 'relative', marginBottom: 36 }}>
          <Search
            size={16}
            style={{ position: 'absolute', left: 16, top: '50%', transform: 'translateY(-50%)', color: '#94A3B8' }}
          />
          <input
            type="text"
            placeholder="Search projects..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={{
              width: '100%',
              maxWidth: 480,
              padding: '10px 16px 10px 42px',
              borderRadius: 12,
              border: '1px solid rgba(15, 23, 42, 0.08)',
              background: 'rgba(255, 255, 255, 0.9)',
              fontSize: 13,
              outline: 'none',
              boxShadow: '0 2px 8px rgba(15, 23, 42, 0.02)',
            }}
          />
        </div>

        {/* Recent Projects Section */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <h3 style={{ fontSize: 16, fontWeight: 700, color: '#0F172A' }}>
            Recent Projects
          </h3>
          <button
            onClick={onNavigateToLibrary}
            id="btn-recent-projects-view-all"
            style={{ fontSize: 12, fontWeight: 600, color: '#2563EB', background: 'transparent', border: 'none', cursor: 'pointer', padding: '4px 8px', borderRadius: 6 }}
          >
            View all
          </button>
        </div>

        {/* Dynamic Projects Cards Grid / Clean Empty State */}
        {loading ? (
          <div style={{ padding: 32, textAlign: 'center', color: '#64748B' }}>
            Loading projects...
          </div>
        ) : filteredProjects.length === 0 ? (
          <div
            className="glass-card"
            style={{
              padding: '36px 24px',
              textAlign: 'center',
              marginBottom: 40,
              background: '#FFFFFF',
              borderRadius: 16,
              border: '1px dashed #CBD5E1',
            }}
          >
            <Database size={36} color="#94A3B8" style={{ margin: '0 auto 12px' }} />
            <h4 style={{ fontSize: 16, fontWeight: 700, color: '#0F172A', marginBottom: 4 }}>
              {searchQuery ? 'No matching projects' : 'No knowledge bases yet'}
            </h4>
            <p style={{ fontSize: 13, color: '#64748B', maxWidth: 400, margin: '0 auto 16px' }}>
              {searchQuery ? 'Try another search term.' : 'Compile your first RAG to build private local intelligence.'}
            </p>
            {!searchQuery && (
              <button onClick={onCreateRag} className="btn-primary" style={{ padding: '8px 18px', fontSize: 13 }}>
                <Plus size={14} />
                <span>Create your first RAG</span>
              </button>
            )}
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 18, marginBottom: 40 }}>
            {filteredProjects.map((p) => {
              const activeVer = p.versions.find((v) => v.version_id === p.active_version_id) || p.versions[0];
              const chunkCount = activeVer?.chunk_count || 0;
              const vectorStore = activeVer?.vector_store?.toUpperCase() || 'LANCEDB';

              return (
                <div
                  key={p.rag_id}
                  className="glass-card glass-card-interactive"
                  style={{
                    background: '#FFFFFF',
                    borderRadius: 16,
                    padding: 20,
                    display: 'flex',
                    flexDirection: 'column',
                    cursor: 'pointer',
                    border: '1px solid rgba(15, 23, 42, 0.07)',
                  }}
                  onClick={() => {
                    if (onOpenKnowledgeBase) onOpenKnowledgeBase(p.rag_id);
                    else onOpenAgent(p.rag_id);
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
                    <div
                      style={{
                        width: 36,
                        height: 36,
                        borderRadius: 8,
                        background: '#EFF6FF',
                        color: '#2563EB',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: 11,
                        fontWeight: 800,
                      }}
                    >
                      RAG
                    </div>
                    <span
                      style={{
                        fontSize: 11,
                        fontWeight: 700,
                        padding: '2px 8px',
                        borderRadius: 9999,
                        background: p.status === 'active' ? '#ECFDF5' : '#F1F5F9',
                        color: p.status === 'active' ? '#059669' : '#64748B',
                      }}
                    >
                      {activeVer?.version_tag || 'v1.0.0'}
                    </span>
                  </div>

                  <h4 style={{ fontSize: 15, fontWeight: 700, color: '#0F172A', marginBottom: 4 }}>
                    {p.name}
                  </h4>
                  <div style={{ fontSize: 12, color: '#64748B', marginBottom: 16 }}>
                    📦 {vectorStore} · {chunkCount} indexed units
                  </div>

                  <div style={{ marginTop: 'auto', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <span
                      style={{
                        fontSize: 11,
                        fontWeight: 600,
                        padding: '3px 10px',
                        borderRadius: 9999,
                        background: '#F8FAFC',
                        color: '#475569',
                      }}
                    >
                      {p.rag_id}
                    </span>
                    <span style={{ fontSize: 12, fontWeight: 600, color: '#2563EB' }}>
                      Open →
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Bottom Helper Banner (Panel 3 Reference) */}
        <div
          className="glass-card"
          style={{
            background: 'linear-gradient(135deg, rgba(255, 255, 255, 0.95) 0%, rgba(238, 242, 255, 0.7) 100%)',
            border: '1px solid rgba(99, 102, 241, 0.15)',
            borderRadius: 18,
            padding: '24px 28px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 18 }}>
            <img
              src={raggerBoxLogo}
              alt="Ragger AI"
              style={{
                width: 48,
                height: 48,
                borderRadius: 14,
                objectFit: 'contain',
                boxShadow: '0 4px 12px rgba(79, 70, 229, 0.15)',
              }}
            />
            <div>
              <h4 style={{ fontSize: 15, fontWeight: 700, color: '#0F172A', marginBottom: 2 }}>
                Need help choosing the right RAG type?
              </h4>
              <p style={{ fontSize: 13, color: '#64748B' }}>
                Our Analyzer Agent will review your files and recommend the best setup.
              </p>
            </div>
          </div>

          <button onClick={onCreateRag} className="btn-primary" style={{ padding: '10px 20px', flexShrink: 0 }}>
            <span>Upload Files</span>
            <ArrowRight size={15} />
          </button>
        </div>
      </div>
    </div>
  );
};
