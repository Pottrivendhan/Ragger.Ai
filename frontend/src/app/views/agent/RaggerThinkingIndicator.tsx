import React from 'react';
import raggerBoxLogo from '../../../assets/ragger.ai_box_logo.png';

interface RaggerThinkingIndicatorProps {
  statusText?: string;
}

export const RaggerThinkingIndicator: React.FC<RaggerThinkingIndicatorProps> = ({
  statusText = 'Thinking...',
}) => {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label="Ragger is thinking"
      id="ragger-thinking-indicator"
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'flex-start',
        animation: 'fadeIn 200ms ease',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          padding: '12px 18px',
          borderRadius: 14,
          background: '#FFFFFF',
          border: '1px solid #E2E8F0',
          boxShadow: '0 2px 8px rgba(15, 23, 42, 0.04)',
        }}
      >
        {/* Animated Ragger R Logo */}
        <div
          style={{
            width: 28,
            height: 28,
            borderRadius: 8,
            background: '#F8FAFC',
            border: '1px solid #E2E8F0',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
            overflow: 'hidden',
          }}
        >
          <img
            src={raggerBoxLogo}
            alt="Ragger R Logo"
            className="ragger-thinking-logo"
            style={{
              width: 18,
              height: 18,
              objectFit: 'contain',
            }}
          />
        </div>

        {/* Thinking Text */}
        <div
          style={{
            fontSize: 13.5,
            fontWeight: 500,
            color: '#475569',
            letterSpacing: '0.01em',
            userSelect: 'none',
          }}
        >
          {statusText}
        </div>
      </div>
    </div>
  );
};
