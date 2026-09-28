export type GroundingPolicy = 'strict_grounded' | 'conversational_strict';

export interface AgentProfile {
  agent_id: string;
  name: string;
  description: string;
  system_prompt?: string | null;
  grounding_policy: GroundingPolicy;
  attached_rag_ids: string[];
  runtime_ref?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateAgentRequest {
  name: string;
  description?: string;
  system_prompt?: string | null;
  grounding_policy?: GroundingPolicy;
  attached_rag_ids?: string[];
  runtime_ref?: string | null;
}

export interface UpdateAgentRequest {
  name?: string;
  description?: string;
  system_prompt?: string | null;
  grounding_policy?: GroundingPolicy;
  attached_rag_ids?: string[];
  runtime_ref?: string | null;
}

export interface MultiRAGClientTarget {
  rag_id: string;
  rag_name: string;
  version_id: string;
  version_tag: string;
}

export interface AgentCitation {
  rag_id: string;
  rag_name?: string;
  build_id?: string;
  source_id: string;
  source_name: string;
  chunk_id: string;
  page_number?: number | null;
  citation_text: string;
  snippet?: string | null;
}


export interface AgentChatRequest {
  query: string;
  session_id?: string | null;
  top_k?: number | null;
  temperature?: number | null;
}

export interface AgentChatResponse {
  agent_id: string;
  session_id: string;
  message_id: string;
  answer: string;
  citations: AgentCitation[];
  retrieved_chunk_count: number;
  has_insufficient_evidence: boolean;
  retrieval_latency_ms: number;
  generation_latency_ms: number;
  original_query?: string | null;
  normalized_query?: string | null;
  generation_provider?: string | null;
  generation_model?: string | null;
}

export interface AgentSessionSummary {
  session_id: string;
  title: string;
  message_count: number;
  created_at: string;
  updated_at: string;
}
