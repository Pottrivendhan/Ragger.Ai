/**
 * Data contracts and interfaces for Phase 7 Grounded Generation & Interactive RAG Chat Subsystem.
 */

export type CitationValidationStatus = 'verified' | 'unverified' | 'ambiguous';

export type GenerationState = 'idle' | 'generating' | 'completed' | 'cancelled' | 'failed';

export interface MessageCitation {
  citation_id: string;
  chunk_id: string;
  source_name: string;
  page_number?: number | null;
  snippet: string;
  citation_text?: string;
  validation_status: CitationValidationStatus;
}

export interface ChatMessage {
  message_id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
  citations: MessageCitation[];
  state: GenerationState;
  retrieval_query?: string | null;
  retrieved_chunk_count?: number;
  disclaimer_emitted?: boolean;
  error_message?: string | null;
}

export interface ChatSession {
  session_id: string;
  workspace_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: ChatMessage[];
}

export interface GenerationResponse {
  session_id: string;
  message_id: string;
  answer: string;
  citations: MessageCitation[];
  state: 'completed' | 'cancelled' | 'failed';
  retrieval_query: string;
  retrieved_chunk_count: number;
  disclaimer_emitted: boolean;
  duration_ms: number;
}

export interface ChatQueryRequest {
  query: string;
  session_id?: string | null;
  temperature?: number;
  max_tokens?: number;
  top_k?: number;
}

export interface GenerationConfig {
  provider: string;
  model: string;
  context_window: number;
  max_output_tokens: number;
  default_temperature: number;
  system_prompt: string;
  base_url: string;
}
