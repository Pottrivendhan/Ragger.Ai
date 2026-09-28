import { apiRequest, apiStream } from './apiBridge';
import {
  AgentProfile,
  CreateAgentRequest,
  UpdateAgentRequest,
  AgentChatRequest,
  AgentChatResponse,
  AgentSessionSummary,
  MultiRAGClientTarget,
} from '../types/agentWorkspace';


export class AgentWorkspaceClient {
  /**
   * Lists all configured agents.
   */
  async listAgents(): Promise<AgentProfile[]> {
    return apiRequest<AgentProfile[]>('/api/v1/agents', { method: 'GET' });
  }

  /**
   * Retrieves an agent profile.
   */
  async getAgent(agentId: string): Promise<AgentProfile> {
    return apiRequest<AgentProfile>(`/api/v1/agents/${encodeURIComponent(agentId)}`, { method: 'GET' });
  }

  /**
   * Creates a new agent.
   */
  async createAgent(request: CreateAgentRequest): Promise<AgentProfile> {
    return apiRequest<AgentProfile>('/api/v1/agents', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  /**
   * Updates an existing agent.
   */
  async updateAgent(agentId: string, request: UpdateAgentRequest): Promise<AgentProfile> {
    return apiRequest<AgentProfile>(`/api/v1/agents/${encodeURIComponent(agentId)}`, {
      method: 'PATCH',
      body: JSON.stringify(request),
    });
  }

  /**
   * Deletes an agent profile.
   */
  async deleteAgent(agentId: string): Promise<void> {
    await apiRequest<void>(`/api/v1/agents/${encodeURIComponent(agentId)}`, {
      method: 'DELETE',
    });
  }

  /**
   * Attaches a RAG artifact to an agent.
   */
  async attachRAG(agentId: string, ragId: string): Promise<AgentProfile> {
    return apiRequest<AgentProfile>(`/api/v1/agents/${encodeURIComponent(agentId)}/rag-attachments`, {
      method: 'POST',
      body: JSON.stringify({ rag_id: ragId }),
    });
  }

  /**
   * Detaches a RAG artifact from an agent.
   */
  async detachRAG(agentId: string, ragId: string): Promise<AgentProfile> {
    return apiRequest<AgentProfile>(`/api/v1/agents/${encodeURIComponent(agentId)}/rag-attachments/${encodeURIComponent(ragId)}`, {
      method: 'DELETE',
    });
  }

  /**
   * Lists sessions belonging to this agent.
   */
  async listSessions(agentId: string): Promise<AgentSessionSummary[]> {
    return apiRequest<AgentSessionSummary[]>(`/api/v1/agents/${encodeURIComponent(agentId)}/sessions`, {
      method: 'GET',
    });
  }

  /**
   * Executes grounded chat query against the agent and its attached RAGs.
   */
  async chat(agentId: string, request: AgentChatRequest): Promise<AgentChatResponse> {
    return apiRequest<AgentChatResponse>(`/api/v1/agents/${encodeURIComponent(agentId)}/chat`, {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  /**
   * Streams grounded chat query progressively using Server-Sent Events (SSE).
   */
  async streamChat(
    agentId: string,
    request: AgentChatRequest,
    callbacks: {
      onInit?: (data: { session_id: string; message_id: string }) => void;
      onRetrieval?: (data: { query: string; chunk_count: number }) => void;
      onToken?: (token: string) => void;
      onDone?: (data: AgentChatResponse) => void;
      onError?: (error: any) => void;
    },
    signal?: AbortSignal
  ): Promise<void> {
    try {
      const res = await apiStream(`/api/v1/agents/${encodeURIComponent(agentId)}/chat/stream?workspace_id=default`, {
        method: 'POST',
        body: JSON.stringify(request),
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
                  callbacks.onRetrieval?.({ query: request.query, chunk_count: data.retrieved_chunk_count || 0 });
                }
              } else if (currentEvent === 'token') {
                callbacks.onToken?.(data.token);
              } else if (currentEvent === 'done') {
                callbacks.onDone?.(data as AgentChatResponse);
              } else if (currentEvent === 'error') {
                callbacks.onError?.(new Error(data.message || 'Stream error'));
              }
            } catch (e) {
              console.warn('Failed to parse Agent SSE event:', dataStr, e);
            }
          }
        }
      }
    } catch (err: any) {
      if (err.name === 'AbortError') {
        console.log('Agent stream chat aborted.');
      } else {
        callbacks.onError?.(err);
      }
    }
  }

  /**
   * Retrieves factual resolved targets for an agent (without build_id).
   */
  async getResolvedTargets(agentId: string): Promise<MultiRAGClientTarget[]> {
    return apiRequest<MultiRAGClientTarget[]>(`/api/v1/agents/${encodeURIComponent(agentId)}/resolved-targets`, {
      method: 'GET',
    });
  }
}

