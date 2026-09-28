import React from 'react';
import { Bot, RotateCcw } from 'lucide-react';
import { AgentProfile } from '../../../types/agentWorkspace';

interface AgentHeaderProps {
  agents: AgentProfile[];
  selectedAgentId: string;
  onSelectAgentId: (id: string) => void;
  activeAgent?: AgentProfile;
  hasMessages: boolean;
  onClearChat: () => void;
}

export const AgentHeader: React.FC<AgentHeaderProps> = ({
  agents,
  selectedAgentId,
  onSelectAgentId,
  activeAgent,
  hasMessages,
  onClearChat,
}) => {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', borderBottom: '1px solid rgba(15, 23, 42, 0.06)' }}>
      {/* Top Main Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 24px',
          background: '#FFFFFF',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, fontWeight: 700, color: '#0F172A' }}>
            <Bot size={18} color="#2563EB" />
            <span>AI Agent Workspace</span>
          </div>

          {/* Agent Selector Dropdown */}
          {agents.length > 0 && (
            <select
              value={selectedAgentId}
              onChange={(e) => onSelectAgentId(e.target.value)}
              style={{
                fontSize: 12,
                fontWeight: 600,
                padding: '4px 10px',
                borderRadius: 6,
                border: '1px solid #CBD5E1',
                background: '#F8FAFC',
                color: '#0F172A',
                cursor: 'pointer',
                outline: 'none',
              }}
              id="select-agent-profile"
            >
              {agents
                .map((agt) => (
                  <option key={agt.agent_id} value={agt.agent_id}>
                    {agt.name} ({(agt.attached_rag_ids || []).length} RAG attached)
                  </option>
                ))}
            </select>
          )}

          {activeAgent && (
            <span
              style={{
                fontSize: 11,
                padding: '2px 8px',
                borderRadius: 9999,
                background: '#EFF6FF',
                color: '#1D4ED8',
                fontWeight: 600,
              }}
            >
              Runtime: {activeAgent.runtime_ref || 'local_gguf'}
            </span>
          )}

          {activeAgent && activeAgent.attached_rag_ids && activeAgent.attached_rag_ids.length > 0 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginLeft: 4 }}>
              {activeAgent.attached_rag_ids.map((rid) => (
                <span
                  key={rid}
                  style={{
                    fontSize: 11,
                    padding: '2px 8px',
                    borderRadius: 6,
                    background: '#F1F5F9',
                    color: '#334155',
                    border: '1px solid #E2E8F0',
                    fontWeight: 500,
                  }}
                  title={rid}
                >
                  📚 {rid.replace(/^rag_/, '')}
                </span>
              ))}
            </div>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {hasMessages && (
            <button
              onClick={onClearChat}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                padding: '6px 12px',
                fontSize: 12,
                borderRadius: 8,
                border: '1px solid #E2E8F0',
                background: '#FFFFFF',
                color: '#475569',
                cursor: 'pointer',
                fontWeight: 500,
                transition: 'all 120ms ease',
              }}
              onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = '#F8FAFC')}
              onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = '#FFFFFF')}
              id="btn-clear-chat"
            >
              <RotateCcw size={13} />
              <span>Clear Chat</span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
