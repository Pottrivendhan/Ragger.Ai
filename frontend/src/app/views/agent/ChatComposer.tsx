import React, { useRef, useEffect, useState } from 'react';
import { ArrowUp, Plus, Square, X, Pencil } from 'lucide-react';
import { RAGArtifactRecord } from '../../../types/ragLifecycle';
import { KnowledgeAttachPopover } from './KnowledgeAttachPopover';

interface ChatComposerProps {
  inputPrompt: string;
  setInputPrompt: (val: string) => void;
  onSendMessage: (text?: string) => void;
  onStopGeneration?: () => void;
  isGenerating: boolean;
  placeholder?: string;
  availableRags?: RAGArtifactRecord[];
  attachedRagIds?: string[];
  isLoadingRags?: boolean;
  onAttachRag?: (ragId: string) => Promise<void>;
  onDetachRag?: (ragId: string) => Promise<void>;
  onCreateNewRag?: () => void;
  onBrowseLibrary?: () => void;
  editingMessageIndex?: number | null;
  onCancelEdit?: () => void;
}

export const ChatComposer: React.FC<ChatComposerProps> = ({
  inputPrompt,
  setInputPrompt,
  onSendMessage,
  onStopGeneration,
  isGenerating,
  placeholder = 'Ask your RAG assistant anything...',
  availableRags = [],
  attachedRagIds = [],
  isLoadingRags = false,
  onAttachRag,
  onDetachRag,
  onCreateNewRag,
  onBrowseLibrary,
  editingMessageIndex,
  onCancelEdit,
}) => {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [isPopoverOpen, setIsPopoverOpen] = useState(false);

  // Auto-resize textarea height up to 160px
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      const scrollH = textareaRef.current.scrollHeight;
      textareaRef.current.style.height = `${Math.min(Math.max(scrollH, 44), 160)}px`;
    }
  }, [inputPrompt]);

  // Focus textarea when entering edit mode
  useEffect(() => {
    if (editingMessageIndex !== null && editingMessageIndex !== undefined && textareaRef.current) {
      textareaRef.current.focus();
      textareaRef.current.setSelectionRange(textareaRef.current.value.length, textareaRef.current.value.length);
    }
  }, [editingMessageIndex]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Escape') {
      if (editingMessageIndex !== null && editingMessageIndex !== undefined) {
        e.preventDefault();
        onCancelEdit?.();
      }
    } else if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (inputPrompt.trim() && !isGenerating) {
        onSendMessage();
      }
    }
  };

  const canSend = Boolean(inputPrompt.trim()) && !isGenerating;

  return (
    <div
      style={{
        padding: '16px 24px 20px',
        background: '#FFFFFF',
        borderTop: '1px solid rgba(15, 23, 42, 0.06)',
        position: 'relative',
        zIndex: 5,
      }}
    >
      {/* Editing State Banner */}
      {editingMessageIndex !== null && editingMessageIndex !== undefined && (
        <div
          style={{
            maxWidth: 820,
            margin: '0 auto 8px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '6px 12px',
            background: '#EFF6FF',
            border: '1px solid #BFDBFE',
            borderRadius: 8,
            fontSize: 12,
            color: '#1E40AF',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 500 }}>
            <Pencil size={13} color="#2563EB" />
            <span>Editing message</span>
            <span style={{ color: '#60A5FA' }}>•</span>
            <span style={{ color: '#64748B', fontSize: 11 }}>Press Enter to save & resend, Esc to cancel</span>
          </div>
          <button
            type="button"
            onClick={onCancelEdit}
            title="Cancel editing (Esc)"
            aria-label="Cancel editing"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              fontSize: 11,
              fontWeight: 500,
              color: '#475569',
              background: 'transparent',
              border: 'none',
              cursor: 'pointer',
              padding: '2px 6px',
              borderRadius: 4,
            }}
            onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = '#DBEAFE')}
            onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = 'transparent')}
          >
            <X size={12} />
            <span>Cancel</span>
          </button>
        </div>
      )}

      <div
        style={{
          maxWidth: 820,
          margin: '0 auto',
          position: 'relative',
          display: 'flex',
          alignItems: 'flex-end',
          background: '#F8FAFC',
          border: editingMessageIndex !== null && editingMessageIndex !== undefined ? '1px solid #3B82F6' : '1px solid #CBD5E1',
          borderRadius: 16,
          padding: '6px 10px 6px 10px',
          boxShadow: editingMessageIndex !== null && editingMessageIndex !== undefined ? '0 0 0 2px rgba(59, 130, 246, 0.15)' : '0 2px 6px rgba(15, 23, 42, 0.04)',
          transition: 'border-color 150ms ease, box-shadow 150ms ease',
        }}
        className="composer-container"
      >
        {/* Knowledge Attachment Popover */}
        {onAttachRag && (
          <KnowledgeAttachPopover
            isOpen={isPopoverOpen}
            onClose={() => setIsPopoverOpen(false)}
            availableRags={availableRags}
            attachedRagIds={attachedRagIds}
            isLoading={isLoadingRags}
            onAttachRag={onAttachRag}
            onDetachRag={onDetachRag}
            onCreateNewRag={() => {
              setIsPopoverOpen(false);
              onCreateNewRag?.();
            }}
            onBrowseLibrary={() => {
              setIsPopoverOpen(false);
              onBrowseLibrary?.();
            }}
          />
        )}

        {/* Plus Button on the left */}
        {onAttachRag && (
          <button
            type="button"
            onClick={() => setIsPopoverOpen((prev) => !prev)}
            aria-label="Add knowledge"
            title="Add knowledge"
            id="btn-add-knowledge"
            style={{
              width: 32,
              height: 32,
              borderRadius: 8,
              background: isPopoverOpen ? '#EFF6FF' : 'transparent',
              color: isPopoverOpen ? '#2563EB' : '#64748B',
              border: isPopoverOpen ? '1px solid #BFDBFE' : '1px solid transparent',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
              marginBottom: 4,
              marginRight: 6,
              transition: 'all 120ms ease',
            }}
            onMouseEnter={(e) => {
              if (!isPopoverOpen) {
                (e.currentTarget as HTMLElement).style.background = '#F1F5F9';
                (e.currentTarget as HTMLElement).style.color = '#0F172A';
              }
            }}
            onMouseLeave={(e) => {
              if (!isPopoverOpen) {
                (e.currentTarget as HTMLElement).style.background = 'transparent';
                (e.currentTarget as HTMLElement).style.color = '#64748B';
              }
            }}
          >
            <Plus size={18} strokeWidth={2.2} />
          </button>
        )}

        <textarea
          ref={textareaRef}
          value={inputPrompt}
          onChange={(e) => setInputPrompt(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={isGenerating ? 'Generating answer...' : placeholder}
          disabled={isGenerating}
          rows={1}
          style={{
            flex: 1,
            border: 'none',
            outline: 'none',
            fontSize: 14,
            lineHeight: 1.5,
            resize: 'none',
            background: 'transparent',
            color: '#0F172A',
            paddingTop: 8,
            paddingBottom: 8,
            maxHeight: 160,
            overflowY: 'auto',
            fontFamily: 'inherit',
          }}
          id="input-agent-chat"
        />

        {/* Send / Stop Button */}
        {isGenerating ? (
          <button
            type="button"
            onClick={onStopGeneration}
            style={{
              width: 34,
              height: 34,
              borderRadius: '50%',
              background: '#2563EB',
              color: '#FFFFFF',
              border: 'none',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
              marginBottom: 3,
              marginLeft: 8,
              boxShadow: '0 2px 6px rgba(37, 99, 235, 0.3)',
              transition: 'all 150ms ease',
            }}
            id="btn-stop-agent-chat"
            title="Stop generating"
            aria-label="Stop generating"
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLElement).style.background = '#1D4ED8';
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLElement).style.background = '#2563EB';
            }}
          >
            <Square size={13} fill="#FFFFFF" color="#FFFFFF" />
          </button>
        ) : (
          <button
            type="button"
            onClick={() => onSendMessage()}
            disabled={!canSend}
            style={{
              width: 34,
              height: 34,
              borderRadius: 10,
              background: canSend ? '#0F172A' : '#E2E8F0',
              color: '#FFFFFF',
              border: 'none',
              cursor: canSend ? 'pointer' : 'default',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
              marginBottom: 3,
              marginLeft: 8,
              transition: 'all 150ms ease',
            }}
            id="btn-send-agent-chat"
            title="Send message"
            aria-label="Send message"
          >
            <ArrowUp size={16} />
          </button>
        )}
      </div>

      <div
        style={{
          textAlign: 'center',
          marginTop: 8,
          fontSize: 11,
          color: '#94A3B8',
        }}
      >
        Responses are strictly grounded in attached knowledge bases. Press <kbd style={{ padding: '1px 4px', background: '#F1F5F9', borderRadius: 4, border: '1px solid #E2E8F0' }}>Enter</kbd> to send, <kbd style={{ padding: '1px 4px', background: '#F1F5F9', borderRadius: 4, border: '1px solid #E2E8F0' }}>Shift + Enter</kbd> for newline.
      </div>
    </div>
  );
};

