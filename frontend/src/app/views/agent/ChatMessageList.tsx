import React, { useState } from 'react';
import { Sparkles, RefreshCw, FileText, Pencil } from 'lucide-react';
import { MessageCitation } from '../../../types/chat';
import { AgentCitation, AgentProfile } from '../../../types/agentWorkspace';
import { ChatMessage } from '../../../services/conversationStore';
import raggerBoxLogo from '../../../assets/ragger.ai_box_logo.png';
import { RaggerThinkingIndicator } from './RaggerThinkingIndicator';

interface ChatMessageListProps {
  messages: ChatMessage[];
  isGenerating: boolean;
  currentStreamingText: string;
  activeAgent?: AgentProfile;
  suggestions: string[];
  isLoadingSuggestions: boolean;
  onSelectSuggestion: (suggestion: string) => void;
  onOpenCitation: (citation: MessageCitation) => void;
  onEditQuestion?: (index: number, content: string) => void;
  editingMessageIndex?: number | null;
  messagesEndRef: React.RefObject<HTMLDivElement | null>;
}

export function sanitizeAnswerText(text: string): string {
  if (!text) return '';
  return text
    // Strip [chk_...] and [Source: ...] markers
    .replace(/\[chk_[a-zA-Z0-9_\-]+\]/g, '')
    .replace(/\[Source:[^\]]+\]/g, '')
    // Strip XML attributes that might have leaked e.g. rag="..." version="..."
    .replace(/\b(rag|source|version|page|build|chunk)="[^"]*"/gi, '')
    .replace(/\b(rag|source|version|page|build|chunk)='[^']*'/gi, '')
    .replace(/<[^>]+>/g, '')
    // Clean up excessive whitespace or trailing commas/spaces
    .replace(/[ \t]{2,}/g, ' ')
    .replace(/\s+([,\.!\?])/g, '$1')
    .trim();
}

export const ChatMessageList: React.FC<ChatMessageListProps> = ({
  messages,
  isGenerating,
  currentStreamingText,
  activeAgent,
  suggestions,
  isLoadingSuggestions,
  onSelectSuggestion,
  onOpenCitation,
  onEditQuestion,
  editingMessageIndex,
  messagesEndRef,
}) => {
  const [hoveredMessageIndex, setHoveredMessageIndex] = useState<number | null>(null);
  return (
    <div
      style={{
        flex: 1,
        overflowY: 'auto',
        padding: '24px 28px',
        display: 'flex',
        flexDirection: 'column',
        gap: 18,
        maxWidth: 860,
        width: '100%',
        margin: '0 auto',
      }}
    >
      {/* Empty State with Dynamic Suggestions */}
      {messages.length === 0 && !isGenerating && (
        <div
          style={{
            margin: 'auto',
            textAlign: 'center',
            maxWidth: 580,
            padding: 32,
            animation: 'fadeIn 250ms ease',
          }}
        >
          <div
            style={{
              width: 52,
              height: 52,
              borderRadius: 14,
              background: '#FFFFFF',
              boxShadow: '0 4px 14px rgba(15, 23, 42, 0.06)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              margin: '0 auto 16px',
              border: '1px solid rgba(15, 23, 42, 0.08)',
            }}
          >
            <img src={raggerBoxLogo} alt="Ragger" style={{ width: 30, height: 30, objectFit: 'contain' }} />
          </div>

          <h2 style={{ fontSize: 20, fontWeight: 700, color: '#0F172A', marginBottom: 6 }}>
            {activeAgent?.name || 'Default Knowledge Assistant'}
          </h2>
          <p style={{ fontSize: 13.5, color: '#64748B', lineHeight: 1.5, marginBottom: 24 }}>
            {activeAgent?.description || 'Grounded AI assistant for your selected knowledge.'}
          </p>

          {/* If no knowledge attached */}
          {!activeAgent?.attached_rag_ids || activeAgent.attached_rag_ids.length === 0 ? (
            <div
              style={{
                padding: '20px',
                borderRadius: 12,
                background: '#F8FAFC',
                border: '1px dashed #CBD5E1',
                textAlign: 'center',
              }}
            >
              <div style={{ fontSize: 13.5, fontWeight: 600, color: '#334155', marginBottom: 4 }}>
                No knowledge source attached
              </div>
              <div style={{ fontSize: 12.5, color: '#64748B' }}>
                Attach a RAG from the RAG Knowledge Library to start asking questions.
              </div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, textAlign: 'left' }}>
              {isLoadingSuggestions ? (
                <div
                  style={{
                    padding: '16px',
                    borderRadius: 8,
                    background: '#FFFFFF',
                    border: '1px dashed #CBD5E1',
                    fontSize: 13,
                    color: '#64748B',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 8,
                  }}
                >
                  <RefreshCw size={14} className="spin" color="#64748B" />
                  <span>Generating document suggestions...</span>
                </div>
              ) : (
                suggestions.map((sample, idx) => (
                  <button
                    key={idx}
                    onClick={() => onSelectSuggestion(sample)}
                    style={{
                      padding: '10px 16px',
                      borderRadius: 10,
                      background: '#FFFFFF',
                      border: '1px solid #E2E8F0',
                      fontSize: 13,
                      color: '#334155',
                      textAlign: 'left',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      transition: 'all 150ms ease',
                      boxShadow: '0 1px 3px rgba(15,23,42,0.03)',
                    }}
                    className="quick-prompt-btn"
                  >
                    <span>{sample}</span>
                    <Sparkles size={14} color="#94A3B8" />
                  </button>
                ))
              )}
            </div>
          )}
        </div>
      )}

      {/* Message List */}
      {messages.map((msg, index) => {
        const isUser = msg.role === 'user';

        return (
          <div
            key={index}
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: isUser ? 'flex-end' : 'flex-start',
              animation: 'fadeIn 180ms ease',
            }}
          >
            {!isUser && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  marginBottom: 6,
                  userSelect: 'none',
                }}
              >
                <div
                  style={{
                    width: 22,
                    height: 22,
                    borderRadius: 6,
                    background: '#FFFFFF',
                    border: '1px solid #E2E8F0',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    boxShadow: '0 1px 3px rgba(15, 23, 42, 0.04)',
                  }}
                >
                  <img
                    src={raggerBoxLogo}
                    alt="Ragger"
                    style={{ width: 14, height: 14, objectFit: 'contain' }}
                  />
                </div>
                <span
                  style={{
                    fontSize: 12,
                    fontWeight: 600,
                    color: '#475569',
                  }}
                >
                  {activeAgent?.name || 'Ragger.ai Assistant'}
                </span>
              </div>
            )}
            <div
              style={{
                position: 'relative',
                display: 'flex',
                flexDirection: 'column',
                alignItems: isUser ? 'flex-end' : 'flex-start',
                maxWidth: isUser ? '75%' : '90%',
              }}
              onMouseEnter={() => setHoveredMessageIndex(index)}
              onMouseLeave={() => setHoveredMessageIndex(null)}
            >
              <div
                style={{
                  padding: isUser ? '10px 16px' : '14px 18px',
                  borderRadius: isUser ? 18 : 12,
                  background: isUser ? (editingMessageIndex === index ? '#1E293B' : '#0F172A') : '#FFFFFF',
                  color: isUser ? '#FFFFFF' : '#0F172A',
                  boxShadow: isUser ? 'none' : '0 1px 4px rgba(15, 23, 42, 0.04)',
                  border: isUser
                    ? editingMessageIndex === index
                      ? '1px dashed #60A5FA'
                      : 'none'
                    : '1px solid #E2E8F0',
                  fontSize: 14,
                  lineHeight: 1.6,
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  position: 'relative',
                }}
              >
                {isUser ? msg.content : sanitizeAnswerText(msg.content)}

                {/* Citations Badges */}
              {!isUser && msg.citations && msg.citations.length > 0 && (
                <div
                  style={{
                    marginTop: 12,
                    paddingTop: 10,
                    borderTop: '1px solid #F1F5F9',
                    display: 'flex',
                    flexWrap: 'wrap',
                    gap: 6,
                  }}
                >
                  {msg.citations.map((c, cIdx) => {
                    const agentCit: AgentCitation | undefined = msg.agentCitations?.[cIdx];
                    const ragLabel =
                      agentCit?.rag_name || (agentCit?.rag_id ? agentCit.rag_id.replace(/^rag_/, '') : null);

                    return (
                      <button
                        key={cIdx}
                        onClick={() => onOpenCitation(c)}
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 6,
                          fontSize: 11,
                          padding: '3px 8px',
                          borderRadius: 6,
                          background: '#EFF6FF',
                          color: '#1D4ED8',
                          border: '1px solid #BFDBFE',
                          cursor: 'pointer',
                          fontWeight: 600,
                        }}
                      >
                        {ragLabel && (
                          <span
                            style={{
                              fontSize: 9,
                              padding: '1px 4px',
                              borderRadius: 4,
                              background: '#DBEAFE',
                              color: '#1E40AF',
                              textTransform: 'uppercase',
                              letterSpacing: '0.04em',
                            }}
                          >
                            {ragLabel}
                          </span>
                        )}
                        <FileText size={12} />
                        <span>
                          {c.source_name} {c.page_number ? `(p. ${c.page_number})` : ''}
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Edit Action on Hover / Focus for User messages */}
              {isUser && !isGenerating && onEditQuestion && (
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    marginTop: 4,
                    opacity: hoveredMessageIndex === index || editingMessageIndex === index ? 1 : 0,
                    transition: 'opacity 120ms ease',
                    pointerEvents: hoveredMessageIndex === index || editingMessageIndex === index ? 'auto' : 'none',
                  }}
                >
                  <button
                    type="button"
                    onClick={() => onEditQuestion(index, msg.content)}
                    title="Edit message"
                    aria-label="Edit message"
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 4,
                      fontSize: 11,
                      fontWeight: 500,
                      color: '#64748B',
                      background: '#F1F5F9',
                      border: '1px solid #E2E8F0',
                      borderRadius: 6,
                      padding: '2px 8px',
                      cursor: 'pointer',
                      transition: 'all 120ms ease',
                    }}
                    onMouseEnter={(e) => {
                      (e.currentTarget as HTMLElement).style.background = '#E2E8F0';
                      (e.currentTarget as HTMLElement).style.color = '#0F172A';
                    }}
                    onMouseLeave={(e) => {
                      (e.currentTarget as HTMLElement).style.background = '#F1F5F9';
                      (e.currentTarget as HTMLElement).style.color = '#64748B';
                    }}
                  >
                    <Pencil size={11} />
                    <span>Edit</span>
                  </button>
                </div>
              )}
            </div>
          </div>
        );
      })}

      {/* Thinking state when generating before any stream tokens arrived */}
      {isGenerating && !currentStreamingText && (
        <RaggerThinkingIndicator statusText="Ragger is thinking..." />
      )}

      {/* Streaming assistant message when tokens are arriving progressively */}
      {isGenerating && currentStreamingText && (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', animation: 'fadeIn 180ms ease' }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              marginBottom: 6,
              userSelect: 'none',
            }}
          >
            <div
              style={{
                width: 22,
                height: 22,
                borderRadius: 6,
                background: '#FFFFFF',
                border: '1px solid #E2E8F0',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 1px 3px rgba(15, 23, 42, 0.04)',
              }}
            >
              <img
                src={raggerBoxLogo}
                alt="Ragger"
                style={{ width: 14, height: 14, objectFit: 'contain' }}
              />
            </div>
            <span
              style={{
                fontSize: 12,
                fontWeight: 600,
                color: '#475569',
              }}
            >
              {activeAgent?.name || 'Ragger.ai Assistant'}
            </span>
          </div>
          <div
            style={{
              maxWidth: '90%',
              padding: '14px 18px',
              borderRadius: 12,
              background: '#FFFFFF',
              color: '#0F172A',
              border: '1px solid #E2E8F0',
              fontSize: 14,
              lineHeight: 1.6,
              whiteSpace: 'pre-wrap',
              boxShadow: '0 1px 4px rgba(15, 23, 42, 0.04)',
            }}
          >
            {sanitizeAnswerText(currentStreamingText)}
            <span
              className="cursor-blink"
              style={{
                display: 'inline-block',
                width: 6,
                height: 14,
                background: '#2563EB',
                marginLeft: 4,
              }}
            />
          </div>
        </div>
      )}

      <div ref={messagesEndRef as any} />
    </div>
  );
};
