import React, { useState, useRef } from 'react';
import {
  Home,
  FolderKanban,
  BookOpen,
  Bot,
  Cpu,
  Settings,
  MoreVertical,
} from 'lucide-react';
import { AuthSession } from '../../services/localAuth';
import { ProfileMenu } from './ProfileMenu';
import raggerBoxLogo from '../../assets/ragger.ai_box_logo.png';
import raggerFullLogo from '../../assets/ragger.ai_full_logo.png';

export type ActiveNavTab = 'home' | 'studio' | 'kb' | 'agent' | 'models' | 'settings';

interface SidebarProps {
  activeTab: ActiveNavTab;
  onSelectTab: (tab: ActiveNavTab, section?: 'account' | 'security' | 'storage' | 'about') => void;
  session: AuthSession | null;
  onRequestLogout: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  onSelectTab,
  session,
  onRequestLogout,
}) => {
  const [isProfileMenuOpen, setIsProfileMenuOpen] = useState(false);
  const profileButtonRef = useRef<HTMLButtonElement>(null);

  return (
    <aside className="app-sidebar">
      {/* Brand Header with Box Logo + Full Logo */}
      <div className="sidebar-logo" style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <img
          src={raggerBoxLogo}
          alt="Ragger Logo"
          style={{ width: 28, height: 28, borderRadius: 8, objectFit: 'contain' }}
        />
        <img
          src={raggerFullLogo}
          alt="Ragger.ai"
          style={{ height: 24, objectFit: 'contain' }}
        />
      </div>

      {/* Main Navigation (Panel 3 Reference) */}
      <nav className="sidebar-nav">
        <button
          className={`sidebar-link ${activeTab === 'home' ? 'active' : ''}`}
          onClick={() => {
            setIsProfileMenuOpen(false);
            onSelectTab('home');
          }}
          id="nav-home"
        >
          <Home size={17} />
          <span>Home</span>
        </button>

        <button
          className={`sidebar-link ${activeTab === 'studio' ? 'active' : ''}`}
          onClick={() => {
            setIsProfileMenuOpen(false);
            onSelectTab('studio');
          }}
          id="nav-studio"
        >
          <FolderKanban size={17} />
          <span>RAG Projects</span>
        </button>

        <button
          className={`sidebar-link ${activeTab === 'kb' ? 'active' : ''}`}
          onClick={() => {
            setIsProfileMenuOpen(false);
            onSelectTab('kb');
          }}
          id="nav-rag-library"
        >
          <BookOpen size={17} />
          <span>RAG Library</span>
        </button>

        <button
          className={`sidebar-link ${activeTab === 'agent' ? 'active' : ''}`}
          onClick={() => {
            setIsProfileMenuOpen(false);
            onSelectTab('agent');
          }}
          id="nav-agent"
        >
          <Bot size={17} />
          <span>AI Agent</span>
        </button>

        <button
          className={`sidebar-link ${activeTab === 'models' ? 'active' : ''}`}
          onClick={() => {
            setIsProfileMenuOpen(false);
            onSelectTab('models');
          }}
          id="nav-models"
        >
          <Cpu size={17} />
          <span>Model Hub</span>
        </button>

        <button
          className={`sidebar-link ${activeTab === 'settings' ? 'active' : ''}`}
          onClick={() => {
            setIsProfileMenuOpen(false);
            onSelectTab('settings');
          }}
          id="nav-settings"
        >
          <Settings size={17} />
          <span>Settings</span>
        </button>
      </nav>

      {/* Footer Profile & Account Menu Trigger */}
      <div className="sidebar-footer" style={{ position: 'relative' }}>
        <ProfileMenu
          isOpen={isProfileMenuOpen}
          onClose={() => setIsProfileMenuOpen(false)}
          session={session}
          onNavigateToSettings={(section) => {
            setIsProfileMenuOpen(false);
            onSelectTab('settings', section);
          }}
          onRequestLogout={() => {
            setIsProfileMenuOpen(false);
            onRequestLogout();
          }}
          placement="up"
          triggerRef={profileButtonRef}
        />

        <button
          ref={profileButtonRef}
          type="button"
          onClick={() => setIsProfileMenuOpen((prev) => !prev)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              setIsProfileMenuOpen((prev) => !prev);
            }
          }}
          id="btn-sidebar-profile"
          aria-label="Open account menu"
          aria-expanded={isProfileMenuOpen}
          aria-haspopup="menu"
          className={`sidebar-profile-card ${isProfileMenuOpen ? 'active' : ''}`}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
            <div
              style={{
                width: 32,
                height: 32,
                borderRadius: '50%',
                background: '#0F172A',
                color: '#FFFFFF',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 12.5,
                fontWeight: 700,
                flexShrink: 0,
              }}
            >
              {session?.fullName ? session.fullName[0].toUpperCase() : 'A'}
            </div>
            <div style={{ minWidth: 0 }}>
              <div
                style={{
                  fontSize: 13,
                  fontWeight: 700,
                  color: '#0F172A',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {session?.fullName || 'Alex'}
              </div>
              <div style={{ fontSize: 11, color: '#94A3B8' }}>Local Device</div>
            </div>
          </div>

          <div
            style={{
              color: isProfileMenuOpen ? '#0F172A' : '#94A3B8',
              padding: 4,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <MoreVertical size={16} />
          </div>
        </button>
      </div>
    </aside>
  );
};
