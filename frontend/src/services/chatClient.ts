/**
 * Client service for interacting with Phase 7 Grounded Generation & Interactive RAG Chat Subsystem.
 * Supports both Electron IPC bridge and direct HTTP fetch (including SSE streaming).
 */

import { apiRequest, apiStream } from './apiBridge';
import {
  ChatQueryRequest,
  GenerationResponse,
  ChatSession,
  GenerationConfig,
  MessageCitation,
} from '../types/chat';

export class ChatClient {
  private static isElectron(): boolean {
    return typeof window !== 'undefined' && !!window.ragger?.chat;
  }

  /**
   * Executes synchronous grounded generation.
   */
  static async generate(payload: ChatQueryRequest): Promise<GenerationResponse> {
    if (this.isElectron()) {
      const res = await window.ragger!.chat!.generate(payload);
      if (!res.success) {
        throw new Error(res.error || 'Failed to generate answer.');
      }
      return res.data!;
    }

    return apiRequest<GenerationResponse>('/api/v1/chat/generate?workspace_id=default', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  /**
   * Streams generation response using Server-Sent Events (SSE).
   */
  static async stream(
    payload: ChatQueryRequest,
    callbacks: {
      onInit?: (data: { session_id: string; message_id: string }) => void;
      onRetrieval?: (data: { query: string; chunk_count: number }) => void;
      onToken?: (token: string) => void;
      onCitation?: (citation: MessageCitation) => void;
      onDisclaimer?: () => void;
      onComplete?: (data: any) => void;
      onError?: (error: any) => void;
    },
    signal?: AbortSignal
  ): Promise<void> {
    try {
      const res = await apiStream('/api/v1/chat/stream?workspace_id=default', {
        method: 'POST',
        body: JSON.stringify(payload),
        signal,
      });

      if (!res.body) {
        throw new Error('ReadableStream not supported by response');
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        let currentEvent = 'message';
        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.startsWith('event: ')) {
            currentEvent = trimmed.slice(7).trim();
          } else if (trimmed.startsWith('data: ')) {
            const dataStr = trimmed.slice(6);
            if (dataStr === '[DONE]') continue;
            try {
              const data = JSON.parse(dataStr);
              if (currentEvent === 'status') {
                if (data.session_id) {
                  callbacks.onInit?.({ session_id: data.session_id, message_id: data.message_id || '' });
                }
                if (data.state === 'generating') {
                  callbacks.onRetrieval?.({ query: payload.query, chunk_count: data.retrieved_chunk_count || 0 });
                }
              } else if (currentEvent === 'token') {
                callbacks.onToken?.(data.token);
              } else if (currentEvent === 'done') {
                if (data.has_insufficient_evidence) {
                  callbacks.onDisclaimer?.();
                }
                if (data.valid_citations && Array.isArray(data.valid_citations)) {
                  for (const cit of data.valid_citations) {
                    callbacks.onCitation?.({
                      citation_id: cit.chunk_id,
                      source_name: cit.source_name,
                      page_number: cit.page_number,
                      chunk_id: cit.chunk_id,
                      validation_status: 'verified',
                      snippet: cit.citation_text || cit.snippet || '',
                    });
                  }
                }
                callbacks.onComplete?.(data);
              } else if (currentEvent === 'error') {
                callbacks.onError?.(new Error(data.message || 'Stream error'));
              }
            } catch (e) {
              console.warn('Failed to parse SSE event:', dataStr, e);
            }
          }
        }
      }
    } catch (err: any) {
      if (err.name === 'AbortError') {
        console.log('Stream generation aborted by user.');
      } else {
        callbacks.onError?.(err);
        throw err;
      }
    }
  }

  /**
   * Cancels generation in progress.
   */
  static async cancel(sessionId: string): Promise<{ status: string; session_id: string }> {
    if (this.isElectron()) {
      const res = await window.ragger!.chat!.cancel(sessionId);
      if (!res.success) {
        throw new Error(res.error || 'Failed to cancel generation.');
      }
      return res.data!;
    }

    return apiRequest<{ status: string; session_id: string }>(`/api/v1/chat/cancel/${sessionId}`, {
      method: 'POST',
    });
  }

  /**
   * Fetches all chat sessions for the workspace.
   */
  static async getSessions(): Promise<ChatSession[]> {
    if (this.isElectron()) {
      const res = await window.ragger!.chat!.getSessions();
      if (!res.success) {
        throw new Error(res.error || 'Failed to fetch sessions.');
      }
      return res.data!;
    }

    return apiRequest<ChatSession[]>('/api/v1/chat/sessions?workspace_id=default');
  }

  /**
   * Fetches a specific chat session by ID.
   */
  static async getSession(sessionId: string): Promise<ChatSession> {
    if (this.isElectron()) {
      const res = await window.ragger!.chat!.getSession(sessionId);
      if (!res.success) {
        throw new Error(res.error || 'Failed to fetch session.');
      }
      return res.data!;
    }

    return apiRequest<ChatSession>(`/api/v1/chat/sessions/${sessionId}?workspace_id=default`);
  }

  /**
   * Deletes a chat session by ID.
   */
  static async deleteSession(sessionId: string): Promise<{ deleted: boolean; session_id: string }> {
    if (this.isElectron()) {
      const res = await window.ragger!.chat!.deleteSession(sessionId);
      if (!res.success) {
        throw new Error(res.error || 'Failed to delete session.');
      }
      return res.data!;
    }

    return apiRequest<{ deleted: boolean; session_id: string }>(`/api/v1/chat/sessions/${sessionId}?workspace_id=default`, {
      method: 'DELETE',
    });
  }

  /**
   * Fetches generation config.
   */
  static async getConfig(): Promise<GenerationConfig> {
    if (this.isElectron()) {
      const res = await window.ragger!.chat!.getConfig();
      if (!res.success) {
        throw new Error(res.error || 'Failed to fetch generation config.');
      }
      return res.data!;
    }

    return apiRequest<GenerationConfig>('/api/v1/chat/config');
  }

  /**
   * Updates generation config.
   */
  static async updateConfig(config: GenerationConfig): Promise<GenerationConfig> {
    if (this.isElectron()) {
      const res = await window.ragger!.chat!.updateConfig(config);
      if (!res.success) {
        throw new Error(res.error || 'Failed to update config.');
      }
      return res.data!;
    }

    return apiRequest<GenerationConfig>('/api/v1/chat/config', {
      method: 'POST',
      body: JSON.stringify(config),
    });
  }
}
