import React, { useEffect, useRef } from 'react';
import {
  User,
  Settings,
  HelpCircle,
  LogOut,
  Sparkles,
  CheckCircle2,
} from 'lucide-react';
import { AuthSession } from '../../services/localAuth';

export interface ProfileMenuProps {
  isOpen: boolean;
  onClose: () => void;
  session: AuthSession | null;
  onNavigateToSettings: (section?: 'account' | 'security' | 'storage' | 'about') => void;
  onRequestLogout: () => void;
  /** Positioning mode: 'up' for bottom-left sidebar, 'down' for top-right header */
  placement?: 'up' | 'down';
  /** Optional ref of the trigger element so clicking trigger toggles cleanly */
  triggerRef?: React.RefObject<HTMLElement>;
}

export const ProfileMenu: React.FC<ProfileMenuProps> = ({
  isOpen,
  onClose,
  session,
  onNavigateToSettings,
  onRequestLogout,
  placement = 'down',
  triggerRef,
}) => {
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
      }
    };

    const handleClickOutside = (e: MouseEvent) => {
      const targetNode = e.target as Node;
      if (
        menuRef.current &&
        !menuRef.current.contains(targetNode) &&
        (!triggerRef?.current || !triggerRef.current.contains(targetNode))
      ) {
        onClose();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen, onClose, triggerRef]);

  if (!isOpen) return null;

  const userInitial = session?.fullName
    ? session.fullName[0].toUpperCase()
    : session?.username
    ? session.username[0].toUpperCase()
    : 'U';

  const userDisplayName = session?.fullName || session?.username || 'Local User';
  const username = session?.username || 'user';

  // Responsive position styles
  const positionStyles: React.CSSProperties =
    placement === 'up'
      ? {
          position: 'absolute',
          bottom: 'calc(100% + 10px)',
          top: 'auto',
          left: 0,
          right: 'auto',
          width: 280,
          maxWidth: 'calc(100vw - 24px)',
        }
      : {
          position: 'absolute',
          top: 'calc(100% + 10px)',
          bottom: 'auto',
          right: 0,
          left: 'auto',
          width: 280,
          maxWidth: 'calc(100vw - 24px)',
        };

  return (
    <div
      ref={menuRef}
      role="menu"
      aria-label="User account menu"
      id="profile-account-menu"
      className="header-popover-panel profile-menu-popover"
      style={{
        ...positionStyles,
        padding: '10px 10px 8px 10px',
        borderRadius: 18,
        background: '#FFFFFF',
        border: '1px solid rgba(15, 23, 42, 0.08)',
        boxShadow:
          '0 20px 45px -8px rgba(15, 23, 42, 0.16), 0 8px 18px -4px rgba(15, 23, 42, 0.08)',
        zIndex: 1000,
        userSelect: 'none',
      }}
    >
      {/* Profile Header (matches img 3) */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          padding: '4px 6px 12px 6px',
          borderBottom: '1px solid #F1F5F9',
          marginBottom: 6,
        }}
      >
        <div
          style={{
            width: 40,
            height: 40,
            borderRadius: '50%',
            background: '#0F172A',
            color: '#FFFFFF',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 15,
            fontWeight: 700,
            flexShrink: 0,
            boxShadow: '0 2px 6px rgba(15, 23, 42, 0.15)',
          }}
        >
          {userInitial}
        </div>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div
            style={{
              fontSize: 14,
              fontWeight: 700,
              color: '#0F172A',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {userDisplayName}
          </div>
          <div
            style={{
              fontSize: 11,
              color: '#64748B',
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              marginTop: 2,
            }}
          >
            <CheckCircle2 size={11} color="#059669" />
            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {username ? `${username}@local` : 'user@local'} · Local Devi...
            </span>
          </div>
        </div>
      </div>

      {/* Menu Actions */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        {/* Personalization (coming soon / offline preference state) */}
        <button
          type="button"
          onClick={() => {
            onClose();
            onNavigateToSettings('about');
          }}
          className="popover-menu-item"
          id="menu-item-personalization"
        >
          <Sparkles size={15} color="#8B5CF6" />
          <span style={{ flex: 1 }}>Personalization</span>
          <span
            style={{
              fontSize: 10,
              fontWeight: 600,
              padding: '2px 6px',
              borderRadius: 4,
              background: '#F5F3FF',
              color: '#7C3AED',
            }}
          >
            Local
          </span>
        </button>

        {/* Profile (opens Settings Profile & Account) */}
        <button
          type="button"
          onClick={() => {
            onClose();
            onNavigateToSettings('account');
          }}
          className="popover-menu-item"
          id="menu-item-profile"
        >
          <User size={15} color="#2563EB" />
          <span>Profile & Account</span>
        </button>

        {/* Settings */}
        <button
          type="button"
          onClick={() => {
            onClose();
            onNavigateToSettings('account');
          }}
          className="popover-menu-item"
          id="menu-item-settings"
        >
          <Settings size={15} color="#64748B" />
          <span>Settings</span>
        </button>

        <div style={{ height: 1, background: '#F1F5F9', margin: '4px 0' }} />

        {/* Help */}
        <button
          type="button"
          onClick={() => {
            onClose();
            onNavigateToSettings('about');
          }}
          className="popover-menu-item"
          id="menu-item-help"
        >
          <HelpCircle size={15} color="#64748B" />
          <span style={{ flex: 1 }}>Help & Docs</span>
          <span style={{ fontSize: 10.5, color: '#94A3B8' }}>v1.1</span>
        </button>

        {/* Log out */}
        <button
          type="button"
          onClick={() => {
            onClose();
            onRequestLogout();
          }}
          className="popover-menu-item danger"
          id="menu-item-logout"
        >
          <LogOut size={15} color="#DC2626" />
          <span>Log out</span>
        </button>
      </div>
    </div>
  );
};
