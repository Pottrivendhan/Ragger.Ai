import { MessageCitation } from '../types/chat';
import { AgentCitation } from '../types/agentWorkspace';
import { localAuth } from './localAuth';

export interface ChatMessage {
  id?: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: MessageCitation[];
  agentCitations?: AgentCitation[];
  isOod?: boolean;
  liked?: boolean;
  disliked?: boolean;
  normalizedQuery?: string;
  provider?: string;
  model?: string;
  timestamp?: string;
}

export interface ConversationRecord {
  id: string; // e.g., "chat_1712345678_abcd"
  backendSessionId?: string | null;
  title: string;
  agentId: string;
  ragIds: string[];
  ragNames: string[];
  activeRagId?: string | null;
  createdAt: string; // ISO string
  updatedAt: string; // ISO string
  messages: ChatMessage[];
  version: 1;
}

export type DateCategory = 'Today' | 'Yesterday' | 'Previous 7 Days' | 'Older';

export interface DateGroupedConversations {
  Today: ConversationRecord[];
  Yesterday: ConversationRecord[];
  'Previous 7 Days': ConversationRecord[];
  Older: ConversationRecord[];
}

const LEGACY_STORAGE_KEY = 'ragger.chat.v1';

export class ConversationStore {
  /**
   * Resolves the account-scoped localStorage key: ragger:<account_id>:conversations
   */
  static getStorageKey(accountIdOverride?: string): string {
    const accId = accountIdOverride || localAuth.getSession()?.accountId || 'acc_default';
    return `ragger:${accId}:conversations`;
  }

  /**
   * Safely loads all conversations for the active account from localStorage with corruption resilience.
   */
  static loadAll(accountIdOverride?: string): ConversationRecord[] {
    try {
      if (typeof window === 'undefined' || !window.localStorage) {
        return [];
      }
      const key = this.getStorageKey(accountIdOverride);
      let raw = window.localStorage.getItem(key);

      // One-time migration for legacy single-account data to default account
      if (!raw && key === 'ragger:acc_default:conversations') {
        const legacyRaw = window.localStorage.getItem(LEGACY_STORAGE_KEY);
        if (legacyRaw) {
          raw = legacyRaw;
          window.localStorage.setItem(key, legacyRaw);
        }
      }

      if (!raw) {
        return [];
      }
      const parsed = JSON.parse(raw);
      if (!Array.isArray(parsed)) {
        console.warn('[ConversationStore] Invalid data structure in storage. Resetting to empty array.');
        return [];
      }

      // Filter and validate records defensively
      const validated: ConversationRecord[] = [];
      for (const item of parsed) {
        if (item && typeof item === 'object' && typeof item.id === 'string') {
          validated.push({
            id: item.id,
            backendSessionId: item.backendSessionId || null,
            title: item.title || 'New Conversation',
            agentId: item.agentId || 'agt_default',
            ragIds: Array.isArray(item.ragIds) ? item.ragIds : [],
            ragNames: Array.isArray(item.ragNames) ? item.ragNames : [],
            activeRagId: item.activeRagId || null,
            createdAt: item.createdAt || new Date().toISOString(),
            updatedAt: item.updatedAt || new Date().toISOString(),
            messages: Array.isArray(item.messages) ? item.messages : [],
            version: 1,
          });
        }
      }

      // Sort by updatedAt descending
      validated.sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime());
      return validated;
    } catch (err) {
      console.warn('[ConversationStore] Failed to load conversations from localStorage:', err);
      return [];
    }
  }

  /**
   * Saves conversation records with quota defense.
   */
  static saveAll(conversations: ConversationRecord[], accountIdOverride?: string): boolean {
    try {
      if (typeof window === 'undefined' || !window.localStorage) {
        return false;
      }
      const key = this.getStorageKey(accountIdOverride);
      const jsonString = JSON.stringify(conversations);
      window.localStorage.setItem(key, jsonString);
      return true;
    } catch (err: any) {
      console.warn('[ConversationStore] Failed to save conversations to localStorage (quota or disabled):', err);
      return false;
    }
  }

  /**
   * Retrieves a conversation by its ID.
   */
  static get(id: string): ConversationRecord | null {
    const list = this.loadAll();
    return list.find((c) => c.id === id) || null;
  }

  /**
   * Deterministically generates a title from the first user query.
   * Max approx 50 chars, trimmed, no LLM call.
   */
  static generateTitle(firstQuery: string): string {
    if (!firstQuery || !firstQuery.trim()) {
      return 'New Conversation';
    }
    let cleaned = firstQuery.trim().replace(/^["']|["']$/g, '').trim();
    if (cleaned.length > 50) {
      cleaned = cleaned.slice(0, 48).trim() + '...';
    }
    return cleaned || 'New Conversation';
  }

  /**
   * Generates a stable unique conversation ID.
   */
  static generateId(): string {
    const rand = Math.random().toString(36).substring(2, 8);
    return `chat_${Date.now()}_${rand}`;
  }

  /**
   * Creates a new conversation and persists it.
   */
  static create(params: {
    agentId: string;
    ragIds: string[];
    ragNames?: string[];
    activeRagId?: string | null;
    title?: string;
    backendSessionId?: string | null;
  }): ConversationRecord {
    const now = new Date().toISOString();
    const newConv: ConversationRecord = {
      id: this.generateId(),
      backendSessionId: params.backendSessionId || null,
      title: params.title || 'New Conversation',
      agentId: params.agentId,
      ragIds: params.ragIds,
      ragNames: params.ragNames || [],
      activeRagId: params.activeRagId || (params.ragIds.length > 0 ? params.ragIds[0] : null),
      createdAt: now,
      updatedAt: now,
      messages: [],
      version: 1,
    };

    const list = this.loadAll();
    list.unshift(newConv);
    this.saveAll(list);
    return newConv;
  }

  /**
   * Updates an existing conversation (e.g. messages, backendSessionId, title).
   */
  static update(id: string, updates: Partial<Omit<ConversationRecord, 'id' | 'createdAt' | 'version'>>): ConversationRecord | null {
    const list = this.loadAll();
    const idx = list.findIndex((c) => c.id === id);
    if (idx === -1) {
      return null;
    }

    const current = list[idx];
    const updated: ConversationRecord = {
      ...current,
      ...updates,
      updatedAt: new Date().toISOString(),
    };

    list[idx] = updated;
    // Keep list sorted by updatedAt descending
    list.sort((a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime());
    this.saveAll(list);
    return updated;
  }

  /**
   * Renames a conversation.
   */
  static rename(id: string, newTitle: string): ConversationRecord | null {
    const trimmed = newTitle.trim();
    if (!trimmed) return null;
    return this.update(id, { title: trimmed });
  }

  /**
   * Deletes a conversation from storage.
   */
  static remove(id: string): boolean {
    const list = this.loadAll();
    const filtered = list.filter((c) => c.id !== id);
    if (filtered.length === list.length) {
      return false;
    }
    return this.saveAll(filtered);
  }

  /**
   * Scoped cleanup when a RAG artifact is deleted:
   * - If conversation only used the deleted RAG (or activeRagId matches and no other valid ragIds), remove it.
   * - If multi-RAG conversation, remove the deleted ragId from its ragIds list.
   * - If ragIds becomes empty, remove the conversation.
   * Returns true if any conversations were modified or removed.
   */
  static removeConversationsForRag(deletedRagId: string): boolean {
    const list = this.loadAll();
    let modified = false;
    const kept: ConversationRecord[] = [];

    for (const conv of list) {
      const usesRag =
        conv.ragIds.includes(deletedRagId) ||
        conv.activeRagId === deletedRagId;

      if (!usesRag) {
        kept.push(conv);
        continue;
      }

      modified = true;
      // Filter out deleted ragId from attachments
      const remainingRagIds = conv.ragIds.filter((r) => r !== deletedRagId);
      if (remainingRagIds.length === 0) {
        // Conversation has no remaining knowledge context -> remove it
        continue;
      }

      // Multi-RAG conversation: preserve with remaining knowledge bases
      const updatedActiveRagId =
        conv.activeRagId === deletedRagId ? remainingRagIds[0] : conv.activeRagId;

      kept.push({
        ...conv,
        ragIds: remainingRagIds,
        activeRagId: updatedActiveRagId,
        updatedAt: new Date().toISOString(),
      });
    }

    if (modified) {
      this.saveAll(kept);
    }
    return modified;
  }

  /**
   * Clears all conversations for the active account from localStorage.
   */
  static clearAll(accountIdOverride?: string): boolean {
    try {
      if (typeof window !== 'undefined' && window.localStorage) {
        const key = this.getStorageKey(accountIdOverride);
        window.localStorage.removeItem(key);
      }
      return true;
    } catch (err) {
      console.warn('[ConversationStore] Failed to clear local conversations:', err);
      return false;
    }
  }

  /**
   * Local instant search by title or first user query.
   */
  static search(query: string, conversations?: ConversationRecord[]): ConversationRecord[] {
    const list = conversations || this.loadAll();
    const q = query.trim().toLowerCase();
    if (!q) {
      return list;
    }

    return list.filter((conv) => {
      if (conv.title.toLowerCase().includes(q)) return true;
      const firstUserMsg = conv.messages.find((m) => m.role === 'user');
      if (firstUserMsg && firstUserMsg.content.toLowerCase().includes(q)) return true;
      if (conv.ragNames.some((n) => n.toLowerCase().includes(q))) return true;
      return false;
    });
  }

  /**
   * Groups a list of conversations into date buckets: Today, Yesterday, Previous 7 Days, Older.
   */
  static groupByDate(conversations: ConversationRecord[]): DateGroupedConversations {
    const result: DateGroupedConversations = {
      Today: [],
      Yesterday: [],
      'Previous 7 Days': [],
      Older: [],
    };

    const now = new Date();
    const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    const startOfYesterday = startOfToday - 24 * 60 * 60 * 1000;
    const startOf7DaysAgo = startOfToday - 7 * 24 * 60 * 60 * 1000;

    for (const conv of conversations) {
      const convTime = new Date(conv.updatedAt || conv.createdAt).getTime();

      if (convTime >= startOfToday) {
        result.Today.push(conv);
      } else if (convTime >= startOfYesterday) {
        result.Yesterday.push(conv);
      } else if (convTime >= startOf7DaysAgo) {
        result['Previous 7 Days'].push(conv);
      } else {
        result.Older.push(conv);
      }
    }

    return result;
  }
}
