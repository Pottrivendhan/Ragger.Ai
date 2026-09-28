import React, { useEffect, useRef } from 'react';
import { AlertCircle, LogOut } from 'lucide-react';

export interface LogoutConfirmationModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirmLogout: () => void;
  username?: string;
}

export const LogoutConfirmationModal: React.FC<LogoutConfirmationModalProps> = ({
  isOpen,
  onClose,
  onConfirmLogout,
  username = 'user',
}) => {
  const modalRef = useRef<HTMLDivElement>(null);
  const cancelButtonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!isOpen) return;

    // Focus cancel button by default for safety
    cancelButtonRef.current?.focus();

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(15, 23, 42, 0.45)',
        backdropFilter: 'blur(4px)',
        zIndex: 2000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 20,
        animation: 'fadeIn 120ms ease-out',
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="logout-dialog-title"
      aria-describedby="logout-dialog-description"
      id="modal-logout-confirm"
    >
      <div
        ref={modalRef}
        className="glass-card"
        style={{
          background: '#FFFFFF',
          borderRadius: 18,
          border: '1px solid rgba(15, 23, 42, 0.08)',
          boxShadow: '0 25px 50px -12px rgba(15, 23, 42, 0.25)',
          maxWidth: 400,
          width: '100%',
          padding: 24,
          animation: 'pageSlideIn 150ms cubic-bezier(0.16, 1, 0.3, 1)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 16 }}>
          <div
            style={{
              width: 44,
              height: 44,
              borderRadius: 12,
              background: '#FEF2F2',
              color: '#DC2626',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <AlertCircle size={22} />
          </div>
          <div>
            <h3
              id="logout-dialog-title"
              style={{ fontSize: 17, fontWeight: 700, color: '#0F172A', margin: 0 }}
            >
              Sign out?
            </h3>
            <p
              id="logout-dialog-description"
              style={{ fontSize: 13, color: '#64748B', margin: '3px 0 0 0' }}
            >
              Are you sure you want to sign out of Ragger.ai?
            </p>
          </div>
        </div>

        <p style={{ fontSize: 12.5, color: '#64748B', lineHeight: 1.5, marginBottom: 20 }}>
          Your offline knowledge bases, models, and local settings for <strong>{username}</strong> will remain safely saved on your local device.
        </p>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <button
            ref={cancelButtonRef}
            type="button"
            onClick={onClose}
            className="btn-secondary"
            id="btn-logout-cancel"
            style={{ padding: '8px 18px', fontSize: 13 }}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => {
              onClose();
              onConfirmLogout();
            }}
            className="btn-primary"
            id="btn-logout-confirm"
            style={{
              padding: '8px 18px',
              fontSize: 13,
              background: '#DC2626',
              borderColor: '#DC2626',
              color: '#FFFFFF',
              boxShadow: '0 2px 8px rgba(220, 38, 38, 0.25)',
            }}
          >
            <LogOut size={14} />
            <span>Sign out</span>
          </button>
        </div>
      </div>
    </div>
  );
};
