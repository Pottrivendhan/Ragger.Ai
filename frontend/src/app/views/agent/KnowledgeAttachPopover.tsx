import React, { useState, useEffect, useRef } from 'react';
import { Search, Plus, BookOpen, Check, Layers, Loader2, X } from 'lucide-react';
import { RAGArtifactRecord } from '../../../types/ragLifecycle';

interface KnowledgeAttachPopoverProps {
  isOpen: boolean;
  onClose: () => void;
  availableRags: RAGArtifactRecord[];
  attachedRagIds: string[];
  isLoading: boolean;
  onAttachRag: (ragId: string) => Promise<void>;
  onDetachRag?: (ragId: string) => Promise<void>;
  onCreateNewRag: () => void;
  onBrowseLibrary: () => void;
}

export const KnowledgeAttachPopover: React.FC<KnowledgeAttachPopoverProps> = ({
  isOpen,
  onClose,
  availableRags,
  attachedRagIds,
  isLoading,
  onAttachRag,
  onDetachRag,
  onCreateNewRag,
  onBrowseLibrary,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [attachingRagId, setAttachingRagId] = useState<string | null>(null);
  const [detachingRagId, setDetachingRagId] = useState<string | null>(null);
  const [feedbackMessage, setFeedbackMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Focus input on open, clear query
  useEffect(() => {
    if (isOpen) {
      setSearchQuery('');
      setFeedbackMessage(null);
      setTimeout(() => {
        searchInputRef.current?.focus();
      }, 50);
    }
  }, [isOpen]);

  // Click outside to close & Escape key handler
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };

    const handleClickOutside = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        onClose();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  // Filter RAGs by name, display name, description, or rag_id
  const filteredRags = availableRags.filter((r) => {
    const q = searchQuery.toLowerCase().trim();
    if (!q) return true;
    const nameMatch = (r.name || '').toLowerCase().includes(q);
    const descMatch = (r.description || '').toLowerCase().includes(q);
    const idMatch = (r.rag_id || '').toLowerCase().includes(q);
    return nameMatch || descMatch || idMatch;
  });

  const handleSelectRag = async (ragId: string) => {
    if (attachedRagIds.includes(ragId) || attachingRagId) return;

    try {
      setAttachingRagId(ragId);
      await onAttachRag(ragId);
      setFeedbackMessage({ text: 'RAG attached', type: 'success' });
      setTimeout(() => {
        onClose();
      }, 350);
    } catch (err: any) {
      setFeedbackMessage({ text: 'Could not attach knowledge', type: 'error' });
    } finally {
      setAttachingRagId(null);
    }
  };

  return (
    <div
      ref={popoverRef}
      role="dialog"
      aria-label="Add knowledge"
      id="popover-add-knowledge"
      style={{
        position: 'absolute',
        bottom: 'calc(100% + 10px)',
        left: 0,
        width: 320,
        maxWidth: 'calc(100vw - 32px)',
        background: '#FFFFFF',
        borderRadius: 14,
        border: '1px solid #E2E8F0',
        boxShadow: '0 10px 25px -5px rgba(15, 23, 42, 0.12), 0 8px 10px -6px rgba(15, 23, 42, 0.08)',
        zIndex: 50,
        overflow: 'hidden',
        animation: 'fadeIn 150ms cubic-bezier(0.16, 1, 0.3, 1)',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: '12px 14px 10px',
          borderBottom: '1px solid #F1F5F9',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: 13, fontWeight: 700, color: '#0F172A' }}>
          <Layers size={16} color="#2563EB" />
          <span>Add Knowledge</span>
        </div>
        {feedbackMessage && (
          <span
            style={{
              fontSize: 11,
              fontWeight: 600,
              color: feedbackMessage.type === 'success' ? '#059669' : '#DC2626',
            }}
          >
            {feedbackMessage.text}
          </span>
        )}
      </div>

      {/* Search Input */}
      <div style={{ padding: '8px 12px', borderBottom: '1px solid #F1F5F9' }}>
        <div
          style={{
            position: 'relative',
            display: 'flex',
            alignItems: 'center',
          }}
        >
          <Search size={14} color="#94A3B8" style={{ position: 'absolute', left: 10, pointerEvents: 'none' }} />
          <input
            ref={searchInputRef}
            type="text"
            placeholder="Search knowledge..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            id="input-search-knowledge"
            style={{
              width: '100%',
              padding: '6px 10px 6px 32px',
              fontSize: 12.5,
              borderRadius: 8,
              border: '1px solid #E2E8F0',
              background: '#F8FAFC',
              color: '#0F172A',
              outline: 'none',
              transition: 'border-color 150ms ease',
            }}
          />
        </div>
      </div>

      {/* RAG List Scroll Area */}
      <div
        style={{
          maxHeight: 220,
          overflowY: 'auto',
          padding: '6px 8px',
          display: 'flex',
          flexDirection: 'column',
          gap: 2,
        }}
      >
        {isLoading ? (
          <div
            style={{
              padding: '24px 16px',
              textAlign: 'center',
              color: '#64748B',
              fontSize: 12,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 8,
            }}
          >
            <Loader2 size={15} className="spin" color="#2563EB" />
            <span>Loading knowledge...</span>
          </div>
        ) : availableRags.length === 0 ? (
          <div
            style={{
              padding: '20px 14px',
              textAlign: 'center',
              color: '#64748B',
              fontSize: 12,
            }}
          >
            <div style={{ fontWeight: 600, color: '#334155', marginBottom: 4 }}>No knowledge bases available.</div>
            <div>Create a RAG to attach knowledge.</div>
          </div>
        ) : filteredRags.length === 0 ? (
          <div
            style={{
              padding: '20px 14px',
              textAlign: 'center',
              color: '#94A3B8',
              fontSize: 12,
            }}
          >
            No matching knowledge bases.
          </div>
        ) : (
          filteredRags.map((rag) => {
            const isAttached = attachedRagIds.includes(rag.rag_id);
            const isAttaching = attachingRagId === rag.rag_id;
            const activeVersion =
              rag.versions?.find((v) => v.version_id === rag.active_version_id) || rag.versions?.[0];
            const versionTag = activeVersion?.version_tag || 'v1.0.0';

            const isDetaching = detachingRagId === rag.rag_id;

            return (
              <div
                key={rag.rag_id}
                onClick={() => {
                  if (!isAttached && !isAttaching && !isDetaching) {
                    handleSelectRag(rag.rag_id);
                  }
                }}
                id={`rag-option-${rag.rag_id}`}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '8px 10px',
                  borderRadius: 8,
                  border: 'none',
                  background: isAttached ? '#F8FAFC' : 'transparent',
                  color: isAttached ? '#64748B' : '#0F172A',
                  cursor: isAttached ? 'default' : isAttaching || isDetaching ? 'not-allowed' : 'pointer',
                  textAlign: 'left',
                  transition: 'background 120ms ease',
                  width: '100%',
                  userSelect: 'none',
                }}
                onMouseEnter={(e) => {
                  if (!isAttached && !isAttaching && !isDetaching) {
                    (e.currentTarget as HTMLElement).style.background = '#F1F5F9';
                  }
                }}
                onMouseLeave={(e) => {
                  if (!isAttached && !isAttaching && !isDetaching) {
                    (e.currentTarget as HTMLElement).style.background = 'transparent';
                  }
                }}
              >
                <div style={{ display: 'flex', flexDirection: 'column', overflow: 'hidden', flex: 1, marginRight: 8 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <span
                      style={{
                        fontSize: 13,
                        fontWeight: 600,
                        color: isAttached ? '#64748B' : '#0F172A',
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                      }}
                    >
                      {rag.name}
                    </span>
                    <span
                      style={{
                        fontSize: 10,
                        padding: '1px 5px',
                        borderRadius: 4,
                        background: '#E2E8F0',
                        color: '#475569',
                        fontFamily: 'monospace',
                        fontWeight: 500,
                        flexShrink: 0,
                      }}
                    >
                      {versionTag}
                    </span>
                  </div>
                  {rag.description && (
                    <span
                      style={{
                        fontSize: 11,
                        color: '#94A3B8',
                        whiteSpace: 'nowrap',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        marginTop: 2,
                      }}
                    >
                      {rag.description}
                    </span>
                  )}
                </div>

                {isAttaching ? (
                  <Loader2 size={14} className="spin" color="#2563EB" />
                ) : isAttached ? (
                  <div style={{ display: 'inline-flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
                    <span
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: 3,
                        fontSize: 11,
                        color: '#059669',
                        fontWeight: 600,
                      }}
                    >
                      <Check size={13} strokeWidth={2.5} />
                      <span>Attached</span>
                    </span>
                    {onDetachRag && (
                      <button
                        type="button"
                        id={`btn-detach-rag-${rag.rag_id}`}
                        disabled={isDetaching}
                        onClick={async (e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          if (isDetaching) return;
                          try {
                            setDetachingRagId(rag.rag_id);
                            await onDetachRag(rag.rag_id);
                            setFeedbackMessage({ text: 'Attachment removed', type: 'success' });
                          } catch (err) {
                            setFeedbackMessage({ text: 'Could not remove', type: 'error' });
                          } finally {
                            setDetachingRagId(null);
                          }
                        }}
                        title={`Remove ${rag.name} from current agent`}
                        style={{
                          border: 'none',
                          background: isDetaching ? '#F1F5F9' : 'transparent',
                          color: isDetaching ? '#94A3B8' : '#94A3B8',
                          cursor: isDetaching ? 'not-allowed' : 'pointer',
                          padding: 2,
                          borderRadius: 4,
                          display: 'inline-flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          width: 20,
                          height: 20,
                          transition: 'all 120ms ease',
                        }}
                        onMouseEnter={(e) => {
                          if (!isDetaching) {
                            (e.currentTarget as HTMLElement).style.color = '#EF4444';
                            (e.currentTarget as HTMLElement).style.background = '#FEE2E2';
                          }
                        }}
                        onMouseLeave={(e) => {
                          if (!isDetaching) {
                            (e.currentTarget as HTMLElement).style.color = '#94A3B8';
                            (e.currentTarget as HTMLElement).style.background = 'transparent';
                          }
                        }}
                      >
                        {isDetaching ? (
                          <Loader2 size={12} className="spin" color="#EF4444" />
                        ) : (
                          <X size={12} strokeWidth={2.5} />
                        )}
                      </button>
                    )}
                  </div>
                ) : (
                  <span
                    style={{
                      fontSize: 11,
                      color: '#2563EB',
                      fontWeight: 600,
                      flexShrink: 0,
                    }}
                  >
                    + Attach
                  </span>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Footer Navigation Actions */}
      <div
        style={{
          padding: '6px',
          borderTop: '1px solid #F1F5F9',
          background: '#FAFAFA',
          display: 'flex',
          flexDirection: 'column',
          gap: 2,
        }}
      >
        <button
          onClick={() => {
            onClose();
            onCreateNewRag();
          }}
          id="btn-popover-create-new-rag"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '7px 10px',
            fontSize: 12,
            fontWeight: 600,
            color: '#1D4ED8',
            background: 'transparent',
            border: 'none',
            borderRadius: 6,
            cursor: 'pointer',
            textAlign: 'left',
            width: '100%',
            transition: 'background 120ms ease',
          }}
          onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = '#EFF6FF')}
          onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = 'transparent')}
        >
          <Plus size={14} color="#2563EB" />
          <span>Create New RAG</span>
        </button>

        <button
          onClick={() => {
            onClose();
            onBrowseLibrary();
          }}
          id="btn-popover-browse-library"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '7px 10px',
            fontSize: 12,
            fontWeight: 600,
            color: '#475569',
            background: 'transparent',
            border: 'none',
            borderRadius: 6,
            cursor: 'pointer',
            textAlign: 'left',
            width: '100%',
            transition: 'background 120ms ease',
          }}
          onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = '#F1F5F9')}
          onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = 'transparent')}
        >
          <BookOpen size={14} color="#64748B" />
          <span>Browse RAG Library</span>
        </button>
      </div>
    </div>
  );
};
