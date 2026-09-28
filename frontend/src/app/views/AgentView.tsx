import React, { useState, useRef, useEffect, useCallback } from 'react';
import { AgentWorkspaceClient } from '../../services/agentWorkspaceClient';
import { RAGLibraryClient } from '../../services/ragLibraryClient';
import { RAGLifecycleClient } from '../../services/ragLifecycleClient';
import { ChatClient } from '../../services/chatClient';
import { MessageCitation } from '../../types/chat';
import { AgentProfile, MultiRAGClientTarget, AgentChatResponse, AgentCitation } from '../../types/agentWorkspace';
import {
  ConversationStore,
  ConversationRecord,
  ChatMessage,
} from '../../services/conversationStore';
import { RAGArtifactRecord } from '../../types/ragLifecycle';
import { AgentSidebar } from './agent/AgentSidebar';
import { AgentHeader } from './agent/AgentHeader';
import { ChatMessageList } from './agent/ChatMessageList';
import { ChatComposer } from './agent/ChatComposer';

interface AgentViewProps {
  chatClient?: ChatClient;
  selectedRagId?: string | null;
  onOpenCitation: (citation: MessageCitation) => void;
  onNavigateToModels?: () => void;
  onNavigateToStudio?: () => void;
  onNavigateToLibrary?: () => void;
}

export const AgentView: React.FC<AgentViewProps> = ({
  selectedRagId,
  onOpenCitation,
  onNavigateToStudio,
  onNavigateToLibrary,
}) => {
  const [agentClient] = useState(() => new AgentWorkspaceClient());
  const [libraryClient] = useState(() => new RAGLibraryClient());
  const [lifecycleClient] = useState(() => new RAGLifecycleClient());

  // Conversation history state (local-first)
  const [conversations, setConversations] = useState<ConversationRecord[]>(() =>
    ConversationStore.loadAll()
  );
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);

  // Agent profiles & attachments
  const [agents, setAgents] = useState<AgentProfile[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState<string>('agt_default');
  const [resolvedTargets, setResolvedTargets] = useState<MultiRAGClientTarget[]>([]);

  // Available RAGs in library for popover attachment
  const [availableRags, setAvailableRags] = useState<RAGArtifactRecord[]>([]);
  const [isLoadingRags, setIsLoadingRags] = useState(false);

  // Document-aware suggestions state
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [isLoadingSuggestions, setIsLoadingSuggestions] = useState(false);

  // Active chat & streaming state
  const [inputPrompt, setInputPrompt] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [currentStreamingText, setCurrentStreamingText] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [editingMessageIndex, setEditingMessageIndex] = useState<number | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Active agent reference
  const activeAgent = agents.find((a) => a.agent_id === selectedAgentId) || agents[0];

  // Helper to refresh local conversation list
  const refreshConversations = useCallback(() => {
    const list = ConversationStore.loadAll();
    setConversations(list);
    return list;
  }, []);

  // 1. Initial Load: Sync agents and route selectedRagId if coming from RAG Library
  useEffect(() => {
    let isMounted = true;

    const syncAgentSelection = async () => {
      try {
        const agentList = await agentClient.listAgents().catch(() => []);
        if (!isMounted) return;
        setAgents(agentList);

        // Filter out any stale agents defensively in case backend had not cleaned them yet
        const validAgents = agentList.filter((a) => {
          if (a.agent_id === 'agt_default') return true;
          return a.attached_rag_ids && a.attached_rag_ids.length > 0;
        });

        if (selectedRagId) {
          // Look for an existing agent profile dedicated exclusively to this RAG artifact
          let targetAgent = validAgents.find(
            (a) => a.attached_rag_ids.length === 1 && a.attached_rag_ids[0] === selectedRagId
          );

          let friendlyName = selectedRagId;
          try {
            const artifacts = await libraryClient.listArtifacts().catch(() => []);
            const matchingArt = artifacts.find(
              (art) => art.rag_id === selectedRagId || `rag_${art.build_id}` === selectedRagId
            );
            if (matchingArt && matchingArt.sources && matchingArt.sources[0]?.filename) {
              friendlyName = matchingArt.sources[0].filename;
            }
          } catch (e) {
            // fallback to selectedRagId
          }

          if (!targetAgent) {
            // Create a dedicated single-RAG assistant agent profile
            targetAgent = await agentClient.createAgent({
              name: `${friendlyName} Assistant`,
              description: `Dedicated AI assistant scoped exclusively to ${friendlyName}`,
              system_prompt: 'You are a helpful and rigorously grounded AI Assistant.',
              grounding_policy: 'strict_grounded',
              attached_rag_ids: [selectedRagId],
            });
            if (isMounted) {
              setAgents((prev) => [...prev, targetAgent!]);
            }
          }

          if (isMounted && targetAgent) {
            setSelectedAgentId(targetAgent.agent_id);

            // Check if there is an active conversation for this specific agent or create one
            const currentList = ConversationStore.loadAll();
            const existingForRag = currentList.find(
              (c) =>
                c.activeRagId === selectedRagId ||
                (c.ragIds.length === 1 && c.ragIds[0] === selectedRagId)
            );

            if (existingForRag) {
              setActiveConversationId(existingForRag.id);
              setMessages(existingForRag.messages);
            } else {
              // Create a fresh conversation dedicated to this RAG
              const newConv = ConversationStore.create({
                agentId: targetAgent.agent_id,
                ragIds: [selectedRagId],
                ragNames: [friendlyName],
                activeRagId: selectedRagId,
                title: `${friendlyName} Chat`,
              });
              refreshConversations();
              setActiveConversationId(newConv.id);
              setMessages([]);
            }
          }
        } else {
          // Direct navigation: default to first valid agent or restore most recent conversation
          const currentList = ConversationStore.loadAll();
          if (currentList.length > 0) {
            const mostRecent = currentList[0];
            setActiveConversationId(mostRecent.id);
            setMessages(mostRecent.messages);
            if (mostRecent.agentId && validAgents.some((a) => a.agent_id === mostRecent.agentId)) {
              setSelectedAgentId(mostRecent.agentId);
            } else {
              const defaultAgent = validAgents.find((a) => a.agent_id.endsWith('_default') || a.agent_id === 'agt_default');
              setSelectedAgentId(defaultAgent ? defaultAgent.agent_id : (validAgents[0]?.agent_id || ''));
            }
          } else {
            const defaultAgent = validAgents.find((a) => a.agent_id.endsWith('_default') || a.agent_id === 'agt_default');
            if (defaultAgent) {
              setSelectedAgentId(defaultAgent.agent_id);
            } else if (validAgents.length > 0) {
              setSelectedAgentId(validAgents[0].agent_id);
            }
            setMessages([]);
          }
        }
      } catch (err) {
        console.warn('Could not sync agents in AgentView:', err);
      }
    };

    syncAgentSelection();
    return () => {
      isMounted = false;
    };
  }, [selectedRagId]);

  // 2. Fetch factual resolved targets for currently selected agent (WITHOUT client build_id)
  useEffect(() => {
    let isMounted = true;
    const fetchTargets = async () => {
      if (!selectedAgentId) return;
      try {
        const targets = await agentClient.getResolvedTargets(selectedAgentId).catch(() => []);
        if (isMounted) {
          setResolvedTargets(targets);
        }
      } catch (err) {
        if (isMounted) setResolvedTargets([]);
      }
    };
    fetchTargets();
    return () => {
      isMounted = false;
    };
  }, [selectedAgentId]);

  // 2b. Fetch available RAGs from RAG Library/Lifecycle client
  const refreshAvailableRags = useCallback(async () => {
    setIsLoadingRags(true);
    try {
      const records = await lifecycleClient.listRags(false).catch(() => []);
      setAvailableRags(records);
    } catch (err) {
      console.warn('Could not load RAGs for knowledge attachment:', err);
    } finally {
      setIsLoadingRags(false);
    }
  }, [lifecycleClient]);

  useEffect(() => {
    refreshAvailableRags();
  }, [refreshAvailableRags]);

  // Handler to attach a RAG to currently selected agent
  const handleAttachRag = async (ragId: string) => {
    if (!selectedAgentId) return;
    try {
      const updatedAgent = await agentClient.attachRAG(selectedAgentId, ragId);
      // Update local agent in state
      setAgents((prev) =>
        prev.map((a) => (a.agent_id === updatedAgent.agent_id ? updatedAgent : a))
      );

      // Refresh resolved targets without build_id
      const targets = await agentClient.getResolvedTargets(selectedAgentId).catch(() => []);
      setResolvedTargets(targets);

      // Refresh dynamic suggestions for the updated attachment set
      if (targets.length > 0) {
        setIsLoadingSuggestions(true);
        try {
          const resp = await lifecycleClient.getSuggestions(ragId);
          if (resp && resp.suggestions && resp.suggestions.length > 0) {
            setSuggestions(resp.suggestions);
          }
        } catch (e) {
          // ignore
        } finally {
          setIsLoadingSuggestions(false);
        }
      }

      // If active conversation, update its ragIds and ragNames
      if (activeConversationId) {
        const currentConv = ConversationStore.get(activeConversationId);
        if (currentConv) {
          const updatedRagIds = Array.from(new Set([...currentConv.ragIds, ragId]));
          const targetNames = targets.map((t) => t.rag_name);
          ConversationStore.update(activeConversationId, {
            ragIds: updatedRagIds,
            ragNames: targetNames.length > 0 ? targetNames : updatedRagIds,
          });
          refreshConversations();
        }
      }
    } catch (err) {
      console.error('Failed to attach RAG:', err);
      throw err;
    }
  };

  // Handler to detach a RAG from currently selected agent
  const handleDetachRag = async (ragId: string) => {
    if (!selectedAgentId) return;
    try {
      const updatedAgent = await agentClient.detachRAG(selectedAgentId, ragId);
      setAgents((prev) =>
        prev.map((a) => (a.agent_id === updatedAgent.agent_id ? updatedAgent : a))
      );

      // Refresh resolved targets
      const targets = await agentClient.getResolvedTargets(selectedAgentId).catch(() => []);
      setResolvedTargets(targets);

      // Refresh suggestions for the remaining RAGs if any
      const remainingRagId = updatedAgent.attached_rag_ids?.[0];
      if (remainingRagId) {
        setIsLoadingSuggestions(true);
        try {
          const resp = await lifecycleClient.getSuggestions(remainingRagId);
          if (resp && resp.suggestions && resp.suggestions.length > 0) {
            setSuggestions(resp.suggestions);
          }
        } catch (e) {
          // ignore
        } finally {
          setIsLoadingSuggestions(false);
        }
      } else {
        setSuggestions([
          'Summarize this document.',
          'Explain the main topic.',
          'What are the important concepts?',
          'Give an overview.',
        ]);
      }

      // If active conversation, update its ragIds
      if (activeConversationId) {
        const currentConv = ConversationStore.get(activeConversationId);
        if (currentConv) {
          const updatedRagIds = currentConv.ragIds.filter((id) => id !== ragId);
          const targetNames = targets.map((t) => t.rag_name);
          ConversationStore.update(activeConversationId, {
            ragIds: updatedRagIds,
            ragNames: targetNames.length > 0 ? targetNames : updatedRagIds,
            activeRagId: updatedRagIds[0] || null,
          });
          refreshConversations();
        }
      }
    } catch (err) {
      console.error('Failed to detach RAG:', err);
    }
  };

  // 3. Fetch document-aware suggestions for currently active agent's attached RAG
  useEffect(() => {
    let isMounted = true;
    const fetchSuggestions = async () => {
      const active = agents.find((a) => a.agent_id === selectedAgentId);
      const targetRagId = active?.attached_rag_ids?.[0] || selectedRagId;

      if (!targetRagId) {
        setSuggestions([
          'Summarize this document.',
          'Explain the main topic.',
          'What are the important concepts?',
          'Give an overview.',
        ]);
        return;
      }

      setIsLoadingSuggestions(true);
      try {
        const resp = await lifecycleClient.getSuggestions(targetRagId);
        if (isMounted) {
          if (resp && resp.suggestions && resp.suggestions.length > 0) {
            const cleaned = resp.suggestions.map((s: string) => {
              let trimmed = s.trim();
              if (
                (trimmed.startsWith('"') && trimmed.endsWith('"')) ||
                (trimmed.startsWith("'") && trimmed.endsWith("'"))
              ) {
                trimmed = trimmed.slice(1, -1).trim();
              }
              if (trimmed.includes("' '") || trimmed.includes("''")) {
                trimmed = trimmed.replace(/' '/g, ' ').replace(/''/g, '');
              }
              return trimmed;
            });
            setSuggestions(cleaned);
          } else {
            setSuggestions([
              'Summarize this document.',
              'Explain the main topic.',
              'What are the important concepts?',
              'Give an overview.',
            ]);
          }
        }
      } catch (err) {
        if (isMounted) {
          setSuggestions([
            'Summarize this document.',
            'Explain the main topic.',
            'What are the important concepts?',
            'Give an overview.',
          ]);
        }
      } finally {
        if (isMounted) {
          setIsLoadingSuggestions(false);
        }
      }
    };

    fetchSuggestions();
    return () => {
      isMounted = false;
    };
  }, [selectedAgentId, agents, selectedRagId]);

  // Auto-scroll when messages or streaming text changes
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, currentStreamingText]);

  // Handle conversation selection from sidebar
  const handleSelectConversation = (convId: string) => {
    if (convId === activeConversationId) return;

    const conv = ConversationStore.get(convId);
    if (!conv) return;

    setActiveConversationId(conv.id);
    setMessages(conv.messages);

    // Restore associated agent context and RAG context
    if (conv.agentId && agents.some((a) => a.agent_id === conv.agentId)) {
      setSelectedAgentId(conv.agentId);
    }
  };

  // Handle New Chat
  const handleNewChat = () => {
    const currentAgent = activeAgent;
    const ragIds = currentAgent?.attached_rag_ids || [];
    const ragNames = resolvedTargets.map((rt) => rt.rag_name);

    const newConv = ConversationStore.create({
      agentId: selectedAgentId,
      ragIds,
      ragNames: ragNames.length > 0 ? ragNames : ragIds,
      activeRagId: ragIds[0] || null,
      title: 'New Conversation',
    });

    refreshConversations();
    setActiveConversationId(newConv.id);
    setMessages([]);
    setInputPrompt('');
  };

  // Handle Rename Conversation
  const handleRenameConversation = (id: string, newTitle: string) => {
    ConversationStore.rename(id, newTitle);
    refreshConversations();
  };

  // Handle Delete Conversation
  const handleDeleteConversation = (id: string) => {
    ConversationStore.remove(id);
    const updated = refreshConversations();

    if (id === activeConversationId) {
      if (updated.length > 0) {
        const next = updated[0];
        setActiveConversationId(next.id);
        setMessages(next.messages);
        if (next.agentId) setSelectedAgentId(next.agentId);
      } else {
        // Fallback to empty state
        setActiveConversationId(null);
        setMessages([]);
      }
    }
  };

  // Handle Clear Chat
  const handleClearChat = () => {
    if (!activeConversationId) {
      setMessages([]);
      return;
    }
    setMessages([]);
    ConversationStore.update(activeConversationId, { messages: [] });
    refreshConversations();
  };

  // Handle Edit question: populate composer and set editing index
  const handleEditQuestion = (index: number, content: string) => {
    if (isGenerating) return;
    setEditingMessageIndex(index);
    setInputPrompt(content);
  };

  // Handle Cancel Edit: clear composer and reset editing index
  const handleCancelEdit = () => {
    setEditingMessageIndex(null);
    setInputPrompt('');
  };

  // Handle Stop Generation: abort active request and preserve partial response
  const handleStopGeneration = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setIsGenerating(false);
  };

  // Cleanup abort controller on unmount
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
        abortControllerRef.current = null;
      }
    };
  }, []);

  // Send message implementation with deterministic title generation and backend session mapping
  const handleSendMessage = async (promptToSend?: string) => {
    const query = (promptToSend !== undefined ? promptToSend : inputPrompt).trim();
    if (!query || isGenerating) return;

    // Capture whether this is an edit submission
    const isEdit = editingMessageIndex !== null;
    const editIdx = editingMessageIndex;

    setInputPrompt('');
    setEditingMessageIndex(null);
    setIsGenerating(true);
    setCurrentStreamingText('');

    // Initialize fresh AbortController for this request
    const abortCtrl = new AbortController();
    abortControllerRef.current = abortCtrl;

    // Ensure we have an active conversation record
    let currentConvId = activeConversationId;
    let currentConv = currentConvId ? ConversationStore.get(currentConvId) : null;

    if (!currentConv) {
      const ragIds = activeAgent?.attached_rag_ids || [];
      const ragNames = resolvedTargets.map((rt) => rt.rag_name);
      currentConv = ConversationStore.create({
        agentId: selectedAgentId,
        ragIds,
        ragNames: ragNames.length > 0 ? ragNames : ragIds,
        activeRagId: ragIds[0] || null,
        title: ConversationStore.generateTitle(query),
      });
      currentConvId = currentConv.id;
      setActiveConversationId(currentConvId);
      refreshConversations();
    } else if (currentConv.messages.length === 0 && currentConv.title === 'New Conversation') {
      // First user message: update title deterministically
      const generatedTitle = ConversationStore.generateTitle(query);
      ConversationStore.rename(currentConvId!, generatedTitle);
      refreshConversations();
    }

    const newUserMsg: ChatMessage = {
      role: 'user',
      content: query,
      timestamp: new Date().toISOString(),
    };

    // If editing, truncate conversation at edit point to prevent old answers or duplicate messages
    let baseMessages = messages;
    if (isEdit && editIdx !== null && editIdx >= 0 && editIdx < messages.length) {
      baseMessages = messages.slice(0, editIdx);
    }

    const updatedMessagesWithUser = [...baseMessages, newUserMsg];
    setMessages(updatedMessagesWithUser);

    // Guard: No knowledge source attached
    if (!activeAgent || !activeAgent.attached_rag_ids || activeAgent.attached_rag_ids.length === 0) {
      abortControllerRef.current = null;
      const noRagMsg: ChatMessage = {
        role: 'assistant',
        content:
          'No knowledge source is attached to this Agent. Please attach a RAG from the RAG Knowledge Library before submitting queries.',
        citations: [],
        isOod: true,
        timestamp: new Date().toISOString(),
      };
      const finalMsgs = [...updatedMessagesWithUser, noRagMsg];
      setMessages(finalMsgs);
      setIsGenerating(false);

      if (currentConvId) {
        ConversationStore.update(currentConvId, { messages: finalMsgs });
        refreshConversations();
      }
      return;
    }

    try {
      if (activeAgent && activeAgent.agent_id) {
        // Dispatch to verified Agent Workspace streaming chat route (Phase 11B / 16)
        let accumulated = '';
        await agentClient.streamChat(
          activeAgent.agent_id,
          {
            query,
            session_id: currentConv?.backendSessionId || undefined,
          },
          {
            onToken: (token: string) => {
              accumulated += token;
              setCurrentStreamingText(accumulated);
            },
            onDone: (resp: AgentChatResponse) => {
              abortControllerRef.current = null;
              setIsGenerating(false);
              setCurrentStreamingText('');

              // Convert AgentCitation to MessageCitation
              const messageCitations: MessageCitation[] = (resp.citations || []).map((c: AgentCitation, i: number) => ({
                citation_id: `cit_${c.chunk_id}_${i}`,
                chunk_id: c.chunk_id,
                source_name: c.source_name,
                page_number: c.page_number || undefined,
                citation_text: c.citation_text,
                snippet: c.snippet || c.citation_text,
                validation_status: 'verified',
              }));

              const assistantMsg: ChatMessage = {
                role: 'assistant',
                content: resp.answer || accumulated,
                citations: messageCitations,
                agentCitations: resp.citations,
                isOod: resp.has_insufficient_evidence,
                normalizedQuery: resp.normalized_query || undefined,
                provider: resp.generation_provider || undefined,
                model: resp.generation_model || undefined,
                timestamp: new Date().toISOString(),
              };

              const finalMsgs = [...updatedMessagesWithUser, assistantMsg];
              setMessages(finalMsgs);

              // Persist to conversation store with updated backendSessionId
              if (currentConvId) {
                ConversationStore.update(currentConvId, {
                  messages: finalMsgs,
                  backendSessionId: resp.session_id || currentConv?.backendSessionId,
                });
                refreshConversations();
              }
            },
            onError: (streamErr: any) => {
              abortControllerRef.current = null;
              setIsGenerating(false);
              setCurrentStreamingText('');

              // If generation was aborted by user clicking Stop, preserve partial answer with stopped indicator
              if (streamErr?.name === 'AbortError' || String(streamErr).includes('AbortError')) {
                if (accumulated.trim()) {
                  const stoppedMsg: ChatMessage = {
                    role: 'assistant',
                    content: `${accumulated.trim()} [Generation stopped]`,
                    timestamp: new Date().toISOString(),
                  };
                  const finalMsgs = [...updatedMessagesWithUser, stoppedMsg];
                  setMessages(finalMsgs);
                  if (currentConvId) {
                    ConversationStore.update(currentConvId, { messages: finalMsgs });
                    refreshConversations();
                  }
                }
                return;
              }

              const errStr = String(streamErr?.message || streamErr || '');
              let content = `Generation failed: ${streamErr?.message || 'local engine error'}.`;

              if (errStr.includes('424') || errStr.includes('MODEL_NOT_AVAILABLE')) {
                content = `Your local AI generation model is not active. Open Model Manager to download and activate a local LLM.`;
              } else if (errStr.includes('Failed to fetch') || errStr.includes('Engine may be initializing')) {
                content = `Ragger.ai engine is starting or unreachable. Please wait a moment and retry.`;
              } else if (errStr.includes('NO_ATTACHED_RAG') || errStr.includes('No attached knowledge')) {
                content = `I couldn't find enough evidence because no knowledge base is attached to this Agent.`;
              } else if (errStr.includes('RAG_ARTIFACT_NOT_FOUND') || errStr.includes('RAG_VERSION_NOT_FOUND')) {
                content = `The knowledge base attached to this agent is no longer available or was recompiled. Please re-attach an active RAG in the Knowledge settings.`;
              } else if (errStr.includes('INSUFFICIENT_EVIDENCE')) {
                content = `I couldn't find enough evidence in the attached knowledge base to answer your question.`;
              }

              const errMsg: ChatMessage = {
                role: 'assistant',
                content,
                timestamp: new Date().toISOString(),
              };
              const finalMsgs = [...updatedMessagesWithUser, errMsg];
              setMessages(finalMsgs);

              if (currentConvId) {
                ConversationStore.update(currentConvId, { messages: finalMsgs });
                refreshConversations();
              }
            },
          },
          abortCtrl.signal
        );
      } else {
        // Fallback directly to verified stream if no agent profile
        let accumulated = '';
        const collectedCitations: MessageCitation[] = [];
        let isInsufficient = false;

        await ChatClient.stream(
          { query },
          {
            onToken: (token: string) => {
              accumulated += token;
              setCurrentStreamingText(accumulated);
            },
            onCitation: (citation: MessageCitation) => {
              collectedCitations.push(citation);
            },
            onDisclaimer: () => {
              isInsufficient = true;
            },
            onComplete: (doneResp: any) => {
              abortControllerRef.current = null;
              setIsGenerating(false);
              setCurrentStreamingText('');
              const isOod = Boolean(doneResp?.has_insufficient_evidence || isInsufficient);
              const cits = isOod ? [] : doneResp?.valid_citations || collectedCitations;

              const assistantMsg: ChatMessage = {
                role: 'assistant',
                content: doneResp?.answer || accumulated,
                citations: cits,
                isOod,
                normalizedQuery: doneResp?.normalized_query,
                provider: doneResp?.generation_provider,
                model: doneResp?.generation_model,
                timestamp: new Date().toISOString(),
              };

              const finalMsgs = [...updatedMessagesWithUser, assistantMsg];
              setMessages(finalMsgs);

              if (currentConvId) {
                ConversationStore.update(currentConvId, { messages: finalMsgs });
                refreshConversations();
              }
            },
            onError: (err: any) => {
              abortControllerRef.current = null;
              setIsGenerating(false);
              setCurrentStreamingText('');

              if (err?.name === 'AbortError' || String(err).includes('AbortError')) {
                if (accumulated.trim()) {
                  const stoppedMsg: ChatMessage = {
                    role: 'assistant',
                    content: `${accumulated.trim()} [Generation stopped]`,
                    timestamp: new Date().toISOString(),
                  };
                  const finalMsgs = [...updatedMessagesWithUser, stoppedMsg];
                  setMessages(finalMsgs);
                  if (currentConvId) {
                    ConversationStore.update(currentConvId, { messages: finalMsgs });
                    refreshConversations();
                  }
                }
                return;
              }

              const errStr = String(err?.message || err || '');
              let content = `Generation failed: ${err?.message || 'local engine error'}.`;
              if (errStr.includes('424') || errStr.includes('MODEL_NOT_AVAILABLE')) {
                content = `Your local AI generation model is not active. Open Model Manager to activate a local LLM.`;
              } else if (errStr.includes('Failed to fetch') || errStr.includes('Engine may be initializing')) {
                content = `Ragger.ai engine is starting or unreachable. Please wait a moment and retry.`;
              } else if (errStr.includes('INSUFFICIENT_EVIDENCE')) {
                content = `I couldn't find enough evidence in the attached knowledge base to answer your question.`;
              }
              const errMsg: ChatMessage = {
                role: 'assistant',
                content,
                timestamp: new Date().toISOString(),
              };
              const finalMsgs = [...updatedMessagesWithUser, errMsg];
              setMessages(finalMsgs);

              if (currentConvId) {
                ConversationStore.update(currentConvId, { messages: finalMsgs });
                refreshConversations();
              }
            },
          },
          abortCtrl.signal
        );
      }
    } catch (err: any) {
      abortControllerRef.current = null;
      setIsGenerating(false);
      setCurrentStreamingText('');

      if (err?.name === 'AbortError' || String(err).includes('AbortError')) {
        return;
      }

      const errStr = String(err?.message || err || '');
      let content = `Unable to generate answer: ${err?.message || 'local engine error'}.`;

      if (errStr.includes('424') || errStr.includes('MODEL_NOT_AVAILABLE')) {
        content = `Your local AI generation model is not active. Please visit Model Manager to activate a local LLM.`;
      } else if (errStr.includes('Failed to fetch') || errStr.includes('Engine may be initializing')) {
        content = `Ragger.ai engine is starting or unreachable. Please wait a moment and retry.`;
      } else if (errStr.includes('NO_ATTACHED_RAG') || errStr.includes('No attached knowledge')) {
        content = `I couldn't find enough evidence because no knowledge base is attached to this Agent.`;
      } else if (errStr.includes('RAG_ARTIFACT_NOT_FOUND') || errStr.includes('RAG_VERSION_NOT_FOUND')) {
        content = `The knowledge base attached to this agent is no longer available or was recompiled. Please re-attach an active RAG in the Knowledge settings.`;
      } else if (errStr.includes('INSUFFICIENT_EVIDENCE')) {
        content = `I couldn't find enough evidence in the attached knowledge base to answer your question.`;
      }

      const errMsg: ChatMessage = {
        role: 'assistant',
        content,
        timestamp: new Date().toISOString(),
      };
      const finalMsgs = [...updatedMessagesWithUser, errMsg];
      setMessages(finalMsgs);

      if (currentConvId) {
        ConversationStore.update(currentConvId, { messages: finalMsgs });
        refreshConversations();
      }
    }
  };

  return (
    <div
      style={{
        display: 'flex',
        flex: 1,
        height: '100%',
        background: '#F8FAFC',
        overflow: 'hidden',
      }}
    >
      {/* 1. Left Conversation Sidebar */}
      <AgentSidebar
        conversations={conversations}
        activeConversationId={activeConversationId}
        onSelectConversation={handleSelectConversation}
        onNewChat={handleNewChat}
        onRenameConversation={handleRenameConversation}
        onDeleteConversation={handleDeleteConversation}
        isCollapsed={isSidebarCollapsed}
        onToggleCollapse={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
      />

      {/* 2. Main Central Workspace */}
      <div
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          height: '100%',
          overflow: 'hidden',
          position: 'relative',
        }}
      >
        <AgentHeader
          agents={agents}
          selectedAgentId={selectedAgentId}
          onSelectAgentId={(id) => {
            setSelectedAgentId(id);
            // If in active conversation, associate it with this agent
            if (activeConversationId) {
              ConversationStore.update(activeConversationId, { agentId: id });
              refreshConversations();
            }
          }}
          activeAgent={activeAgent}
          hasMessages={messages.length > 0}
          onClearChat={handleClearChat}
        />

        <ChatMessageList
          messages={messages}
          isGenerating={isGenerating}
          currentStreamingText={currentStreamingText}
          activeAgent={activeAgent}
          suggestions={suggestions}
          isLoadingSuggestions={isLoadingSuggestions}
          onSelectSuggestion={(sug) => handleSendMessage(sug)}
          onOpenCitation={onOpenCitation}
          onEditQuestion={handleEditQuestion}
          editingMessageIndex={editingMessageIndex}
          messagesEndRef={messagesEndRef}
        />

        <ChatComposer
          inputPrompt={inputPrompt}
          setInputPrompt={setInputPrompt}
          onSendMessage={handleSendMessage}
          onStopGeneration={handleStopGeneration}
          isGenerating={isGenerating}
          placeholder={`Ask ${activeAgent?.name || 'your RAG assistant'} anything...`}
          availableRags={availableRags}
          attachedRagIds={activeAgent?.attached_rag_ids || []}
          isLoadingRags={isLoadingRags}
          onAttachRag={handleAttachRag}
          onDetachRag={handleDetachRag}
          onCreateNewRag={() => onNavigateToStudio?.()}
          onBrowseLibrary={() => onNavigateToLibrary?.()}
          editingMessageIndex={editingMessageIndex}
          onCancelEdit={handleCancelEdit}
        />
      </div>
    </div>
  );
};
