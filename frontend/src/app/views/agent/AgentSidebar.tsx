import React, { useState, useRef, useEffect } from 'react';
import {
  Plus,
  Search,
  MessageSquare,
  MoreVertical,
  Edit2,
  Trash2,
  Check,
  X,
  ChevronLeft,
  ChevronRight,
  Bot,
} from 'lucide-react';
import {
  ConversationRecord,
  DateCategory,
  ConversationStore,
} from '../../../services/conversationStore';

interface AgentSidebarProps {
  conversations: ConversationRecord[];
  activeConversationId: string | null;
  onSelectConversation: (id: string) => void;
  onNewChat: () => void;
  onRenameConversation: (id: string, newTitle: string) => void;
  onDeleteConversation: (id: string) => void;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}

export const AgentSidebar: React.FC<AgentSidebarProps> = ({
  conversations,
  activeConversationId,
  onSelectConversation,
  onNewChat,
  onRenameConversation,
  onDeleteConversation,
  isCollapsed = false,
  onToggleCollapse,
}) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [activeMenuId, setActiveMenuId] = useState<string | null>(null);

  const editInputRef = useRef<HTMLInputElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);

  // Close context menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setActiveMenuId(null);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => {
    if (editingId && editInputRef.current) {
      editInputRef.current.focus();
      editInputRef.current.select();
    }
  }, [editingId]);

  const filteredConversations = ConversationStore.search(searchQuery, conversations);
  const grouped = ConversationStore.groupByDate(filteredConversations);

  const handleStartRename = (conv: ConversationRecord, e: React.MouseEvent) => {
    e.stopPropagation();
    setActiveMenuId(null);
    setEditingId(conv.id);
    setEditTitle(conv.title);
  };

  const handleConfirmRename = (id: string) => {
    if (editTitle.trim()) {
      onRenameConversation(id, editTitle.trim());
    }
    setEditingId(null);
  };

  const handleCancelRename = () => {
    setEditingId(null);
  };

  const categories: DateCategory[] = ['Today', 'Yesterday', 'Previous 7 Days', 'Older'];

  if (isCollapsed) {
    return (
      <div
        style={{
          width: 56,
          height: '100%',
          background: '#F8FAFC',
          borderRight: '1px solid #E2E8F0',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          padding: '16px 8px',
          gap: 12,
          transition: 'width 200ms ease',
          zIndex: 10,
        }}
      >
        <button
          onClick={onToggleCollapse}
          title="Expand sidebar"
          style={{
            padding: 8,
            borderRadius: 8,
            border: 'none',
            background: 'transparent',
            color: '#64748B',
            cursor: 'pointer',
          }}
        >
          <ChevronRight size={18} />
        </button>
        <button
          onClick={onNewChat}
          title="New Chat"
          style={{
            width: 40,
            height: 40,
            borderRadius: 10,
            border: '1px solid #CBD5E1',
            background: '#FFFFFF',
            color: '#0F172A',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: 'pointer',
            boxShadow: '0 1px 3px rgba(15,23,42,0.06)',
          }}
        >
          <Plus size={18} />
        </button>
      </div>
    );
  }

  return (
    <aside
      style={{
        width: 280,
        minWidth: 260,
        maxWidth: 320,
        height: '100%',
        background: '#FFFFFF',
        borderRight: '1px solid #E2E8F0',
        display: 'flex',
        flexDirection: 'column',
        boxSizing: 'border-box',
        position: 'relative',
        userSelect: 'none',
      }}
    >
      {/* Sidebar Header & New Chat */}
      <div style={{ padding: '16px 14px 12px', borderBottom: '1px solid #F1F5F9' }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: 12,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div
              style={{
                width: 28,
                height: 28,
                borderRadius: 8,
                background: '#EFF6FF',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <Bot size={16} color="#2563EB" />
            </div>
            <span style={{ fontSize: 13, fontWeight: 700, color: '#0F172A', letterSpacing: '-0.01em' }}>
              Conversations
            </span>
          </div>

          {onToggleCollapse && (
            <button
              onClick={onToggleCollapse}
              title="Collapse sidebar"
              style={{
                padding: 4,
                borderRadius: 6,
                border: 'none',
                background: 'transparent',
                color: '#94A3B8',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <ChevronLeft size={16} />
            </button>
          )}
        </div>

        {/* New Chat Button */}
        <button
          onClick={onNewChat}
          id="btn-new-chat"
          style={{
            width: '100%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 8,
            padding: '9px 14px',
            borderRadius: 10,
            background: '#0F172A',
            color: '#FFFFFF',
            border: 'none',
            fontSize: 13,
            fontWeight: 600,
            cursor: 'pointer',
            transition: 'all 150ms ease',
            boxShadow: '0 2px 6px rgba(15, 23, 42, 0.08)',
          }}
        >
          <Plus size={16} />
          <span>New Chat</span>
        </button>

        {/* Search Conversations Input */}
        <div
          style={{
            position: 'relative',
            marginTop: 10,
            display: 'flex',
            alignItems: 'center',
          }}
        >
          <Search
            size={14}
            color="#94A3B8"
            style={{ position: 'absolute', left: 10, pointerEvents: 'none' }}
          />
          <input
            type="text"
            placeholder="Search conversations..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            id="input-search-conversations"
            style={{
              width: '100%',
              padding: '6px 10px 6px 30px',
              borderRadius: 8,
              border: '1px solid #E2E8F0',
              background: '#F8FAFC',
              fontSize: 12,
              color: '#0F172A',
              outline: 'none',
              transition: 'border-color 150ms ease',
            }}
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              style={{
                position: 'absolute',
                right: 8,
                border: 'none',
                background: 'transparent',
                color: '#94A3B8',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
              }}
            >
              <X size={12} />
            </button>
          )}
        </div>
      </div>

      {/* Grouped Conversations Scroll Area */}
      <div
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: '10px 10px 20px',
          display: 'flex',
          flexDirection: 'column',
          gap: 16,
        }}
      >
        {filteredConversations.length === 0 ? (
          <div
            style={{
              padding: '32px 16px',
              textAlign: 'center',
              color: '#94A3B8',
              fontSize: 12,
            }}
          >
            {searchQuery ? 'No matching conversations' : 'No conversations yet'}
          </div>
        ) : (
          categories.map((category) => {
            const list = grouped[category];
            if (!list || list.length === 0) return null;

            return (
              <div key={category} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                <div
                  style={{
                    fontSize: 11,
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    color: '#94A3B8',
                    letterSpacing: '0.04em',
                    padding: '4px 8px',
                  }}
                >
                  {category}
                </div>

                {list.map((conv) => {
                  const isActive = conv.id === activeConversationId;
                  const isEditing = conv.id === editingId;
                  const hasMenu = conv.id === activeMenuId;

                  // Label preview: RAG or Agent name (no internal build_id)
                  const subLabel =
                    conv.ragNames && conv.ragNames.length > 0
                      ? conv.ragNames[0]
                      : null;

                  return (
                    <div
                      key={conv.id}
                      onClick={() => !isEditing && onSelectConversation(conv.id)}
                      style={{
                        position: 'relative',
                        padding: '8px 10px',
                        borderRadius: 8,
                        background: isActive ? '#F1F5F9' : 'transparent',
                        color: isActive ? '#0F172A' : '#334155',
                        cursor: isEditing ? 'default' : 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: 8,
                        fontSize: 13,
                        fontWeight: isActive ? 600 : 500,
                        transition: 'background 120ms ease',
                      }}
                      className={`conversation-item ${isActive ? 'active' : ''}`}
                    >
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          gap: 8,
                          flex: 1,
                          overflow: 'hidden',
                        }}
                      >
                        <MessageSquare
                          size={14}
                          color={isActive ? '#2563EB' : '#94A3B8'}
                          style={{ flexShrink: 0 }}
                        />

                        {isEditing ? (
                          <div
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              gap: 4,
                              flex: 1,
                            }}
                            onClick={(e) => e.stopPropagation()}
                          >
                            <input
                              ref={editInputRef}
                              value={editTitle}
                              onChange={(e) => setEditTitle(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') handleConfirmRename(conv.id);
                                if (e.key === 'Escape') handleCancelRename();
                              }}
                              style={{
                                width: '100%',
                                padding: '2px 6px',
                                fontSize: 12,
                                border: '1px solid #2563EB',
                                borderRadius: 4,
                                outline: 'none',
                                background: '#FFFFFF',
                              }}
                            />
                            <button
                              onClick={() => handleConfirmRename(conv.id)}
                              style={{
                                border: 'none',
                                background: '#2563EB',
                                color: '#FFFFFF',
                                borderRadius: 4,
                                padding: 3,
                                cursor: 'pointer',
                                display: 'flex',
                              }}
                              title="Save"
                            >
                              <Check size={12} />
                            </button>
                            <button
                              onClick={handleCancelRename}
                              style={{
                                border: 'none',
                                background: '#E2E8F0',
                                color: '#475569',
                                borderRadius: 4,
                                padding: 3,
                                cursor: 'pointer',
                                display: 'flex',
                              }}
                              title="Cancel"
                            >
                              <X size={12} />
                            </button>
                          </div>
                        ) : (
                          <div
                            style={{
                              display: 'flex',
                              flexDirection: 'column',
                              overflow: 'hidden',
                              flex: 1,
                            }}
                          >
                            <span
                              style={{
                                whiteSpace: 'nowrap',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                fontSize: 12.5,
                              }}
                            >
                              {conv.title}
                            </span>
                            {subLabel && (
                              <span
                                style={{
                                  fontSize: 10,
                                  color: '#94A3B8',
                                  whiteSpace: 'nowrap',
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis',
                                }}
                              >
                                {subLabel}
                              </span>
                            )}
                          </div>
                        )}
                      </div>

                      {/* Action Menu (Rename, Delete) */}
                      {!isEditing && (
                        <div style={{ position: 'relative' }}>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setActiveMenuId(hasMenu ? null : conv.id);
                            }}
                            className="conversation-menu-trigger"
                            style={{
                              border: 'none',
                              background: 'transparent',
                              color: '#94A3B8',
                              padding: 4,
                              borderRadius: 4,
                              cursor: 'pointer',
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              opacity: isActive || hasMenu ? 1 : 0.4,
                            }}
                            title="Conversation options"
                          >
                            <MoreVertical size={14} />
                          </button>

                          {hasMenu && (
                            <div
                              ref={menuRef}
                              style={{
                                position: 'absolute',
                                right: 0,
                                top: 24,
                                background: '#FFFFFF',
                                border: '1px solid #E2E8F0',
                                borderRadius: 8,
                                boxShadow: '0 4px 14px rgba(15, 23, 42, 0.1)',
                                padding: '4px',
                                minWidth: 120,
                                zIndex: 100,
                                display: 'flex',
                                flexDirection: 'column',
                                gap: 2,
                              }}
                            >
                              <button
                                onClick={(e) => handleStartRename(conv, e)}
                                style={{
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: 8,
                                  padding: '6px 10px',
                                  fontSize: 12,
                                  color: '#334155',
                                  border: 'none',
                                  background: 'transparent',
                                  borderRadius: 6,
                                  cursor: 'pointer',
                                  textAlign: 'left',
                                  width: '100%',
                                }}
                                onMouseEnter={(e) =>
                                  ((e.currentTarget as HTMLElement).style.background = '#F8FAFC')
                                }
                                onMouseLeave={(e) =>
                                  ((e.currentTarget as HTMLElement).style.background = 'transparent')
                                }
                              >
                                <Edit2 size={13} color="#64748B" />
                                <span>Rename</span>
                              </button>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setActiveMenuId(null);
                                  onDeleteConversation(conv.id);
                                }}
                                style={{
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: 8,
                                  padding: '6px 10px',
                                  fontSize: 12,
                                  color: '#EF4444',
                                  border: 'none',
                                  background: 'transparent',
                                  borderRadius: 6,
                                  cursor: 'pointer',
                                  textAlign: 'left',
                                  width: '100%',
                                }}
                                onMouseEnter={(e) =>
                                  ((e.currentTarget as HTMLElement).style.background = '#FEF2F2')
                                }
                                onMouseLeave={(e) =>
                                  ((e.currentTarget as HTMLElement).style.background = 'transparent')
                                }
                              >
                                <Trash2 size={13} color="#EF4444" />
                                <span>Delete</span>
                              </button>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
};
