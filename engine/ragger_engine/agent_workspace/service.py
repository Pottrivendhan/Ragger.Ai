"""
Agent Workspace Coordinator Service.
Coordinates agent profiles, RAG attachments, and chat sessions.
Delegates 100% of retrieval, standardization, evidence gating, and generation to the verified GenerationService.
Does NOT re-implement retrieval, embeddings, GGUF generation, or citation validation.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
import uuid

from ragger_engine.agent_workspace.exceptions import (
    AgentNotFoundError,
    NoAttachedRAGError,
    RAGArtifactNotFoundError,
)
from ragger_engine.agent_workspace.models import (
    AgentChatRequest,
    AgentChatResponse,
    AgentCitation,
    AgentProfile,
    CreateAgentRequest,
    UpdateAgentRequest,
)
from typing import TYPE_CHECKING, AsyncGenerator
from ragger_engine.generation.models import ChatQueryRequest, GenerationResponse
from ragger_engine.generation.service import GenerationService
from ragger_engine.rag_library.service import RAGLibraryService

if TYPE_CHECKING:
    from ragger_engine.multi_rag.coordinator import MultiRAGCoordinator

logger = logging.getLogger(__name__)


class AgentWorkspaceService:
    """Supervises Agent lifecycle and coordinates multi-RAG grounded generation."""

    def __init__(
        self,
        workspace_dir: Path,
        rag_library_service: RAGLibraryService,
        generation_service: GenerationService,
        rag_lifecycle_service=None,
        multi_rag_coordinator: Optional["MultiRAGCoordinator"] = None,
    ):
        self.workspace_dir = Path(workspace_dir)
        self.rag_library_service = rag_library_service
        self.generation_service = generation_service
        self._rag_lifecycle_service = rag_lifecycle_service

        # Coordinator for Phase 16 multi-RAG resolution, retrieval and fusion
        if multi_rag_coordinator:
            self.multi_rag_coordinator = multi_rag_coordinator
        elif generation_service and hasattr(generation_service, "retrieval_service"):
            from ragger_engine.multi_rag.coordinator import MultiRAGCoordinator
            self.multi_rag_coordinator = MultiRAGCoordinator(
                retrieval_service=generation_service.retrieval_service,
                rag_lifecycle_service=rag_lifecycle_service,
                rag_library_service=rag_library_service,
            )
        else:
            self.multi_rag_coordinator = None

        # Independent persistence directory for agents and agent sessions
        self.agents_dir = self.workspace_dir / "agents"
        self.agents_dir.mkdir(parents=True, exist_ok=True)
        self.agents_file = self.agents_dir / "agents.json"
        self._ensure_agents_file()

    @property
    def rag_lifecycle_service(self):
        return self._rag_lifecycle_service

    @rag_lifecycle_service.setter
    def rag_lifecycle_service(self, service):
        self._rag_lifecycle_service = service
        if self.multi_rag_coordinator:
            self.multi_rag_coordinator.rag_lifecycle_service = service


    def _ensure_agents_file(self) -> None:
        if not self.agents_file.exists():
            try:
                # Seed default general-purpose assistant agent pointing to stable RAG
                default_rags = []
                if self.rag_lifecycle_service:
                    rags = self.rag_lifecycle_service.list_rags()
                    if rags:
                        default_rags = [rags[0].rag_id]
                if not default_rags:
                    active_build = self.rag_library_service._get_active_build_id()
                    if active_build == "bld_6f509ca2":
                        default_rags = ["rag_class10_english"]
                    elif active_build:
                        default_rags = [f"rag_{active_build}"]

                default_agent = AgentProfile(
                    agent_id="agt_default",
                    name="Default Knowledge Assistant",
                    description="General-purpose grounded knowledge assistant",
                    system_prompt="You are a helpful and rigorously grounded AI Assistant.",
                    attached_rag_ids=default_rags,
                    runtime_ref="local_gguf",
                )
                with open(self.agents_file, "w", encoding="utf-8") as f:
                    json.dump({default_agent.agent_id: default_agent.model_dump(mode="json")}, f, indent=2)
            except Exception as e:
                logger.error("Failed to seed default agents file: %s", e)

    def _load_agents_map(self) -> Dict[str, AgentProfile]:
        if not self.agents_file.exists():
            return {}
        try:
            with open(self.agents_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
            return {k: AgentProfile.model_validate(v) for k, v in raw.items()}
        except Exception as e:
            logger.error("Failed to load agents map: %s", e)
            return {}

    def _save_agents_map(self, agents: Dict[str, AgentProfile]) -> None:
        tmp_file = self.agents_file.with_suffix(".tmp")
        data = {k: v.model_dump(mode="json") for k, v in agents.items()}
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        tmp_file.replace(self.agents_file)

    def list_agents(self, account_id: Optional[str] = None) -> List[AgentProfile]:
        """
        Lists all registered agents filtered by account_id.
        If an account has no agents yet, automatically initializes an empty default agent for that account.
        Defensive lifecycle reconciliation:
        - Filters out dedicated single-RAG agents (excluding default agents) whose attached RAG
          has been deleted or has 0 attached RAGs.
        - Persists cleaned map if stale records were detected and purged.
        """
        agents_map = self._load_agents_map()
        dirty = False

        # Lazily create an empty default agent for accounts with no agents
        if account_id and account_id != "acc_default":
            account_has_agent = any(a.account_id == account_id for a in agents_map.values())
            if not account_has_agent:
                agt_id = f"agt_{account_id}_default"
                new_account_default = AgentProfile(
                    agent_id=agt_id,
                    name="Default Knowledge Assistant",
                    description="General-purpose grounded knowledge assistant",
                    system_prompt="You are a helpful and rigorously grounded AI Assistant.",
                    attached_rag_ids=[],
                    runtime_ref="local_gguf",
                    account_id=account_id,
                )
                agents_map[agt_id] = new_account_default
                dirty = True

        available_rags: Optional[Set[str]] = None

        if self.rag_library_service or self.rag_lifecycle_service:
            available_rags = set()
            if self.rag_library_service:
                for a in self.rag_library_service.list_artifacts():
                    available_rags.add(a.rag_id)
                    available_rags.add(f"rag_{a.build_id}")
            if self.rag_lifecycle_service:
                for r in self.rag_lifecycle_service.list_rags():
                    available_rags.add(r.rag_id)
                    for v in r.versions:
                        available_rags.add(f"rag_{v.build_id}")

        to_delete = []

        for agent_id, agent in agents_map.items():
            if agent_id == "agt_default" or agent_id.endswith("_default"):
                continue

            # Case A: Dedicated agent with 0 attached RAGs
            if len(agent.attached_rag_ids) == 0:
                to_delete.append(agent_id)
                continue

            # Case B: Dedicated single-RAG agent whose RAG no longer exists in library/lifecycle
            if available_rags is not None and len(agent.attached_rag_ids) == 1:
                rag_ref = agent.attached_rag_ids[0]
                if rag_ref not in available_rags:
                    to_delete.append(agent_id)
                    continue

        if to_delete:
            for aid in to_delete:
                del agents_map[aid]
            dirty = True

        if dirty:
            self._save_agents_map(agents_map)

        results = list(agents_map.values())
        if account_id is not None:
            results = [a for a in results if a.account_id == account_id]
        return results

    def get_agent(self, agent_id: str, account_id: Optional[str] = None) -> AgentProfile:
        """Retrieves a single agent profile by ID, validating account ownership if specified."""
        agents_map = self._load_agents_map()
        if agent_id not in agents_map:
            raise AgentNotFoundError(agent_id)
        agent = agents_map[agent_id]
        if account_id is not None and agent.account_id != account_id:
            raise AgentNotFoundError(agent_id)
        return agent

    def create_agent(self, request: CreateAgentRequest, account_id: Optional[str] = None) -> AgentProfile:
        """Creates a new agent after validating all attached RAG references."""
        resolved_account_id = account_id or request.account_id or "acc_default"
        # Validate that any requested RAG attachments exist in RAG Library or RAG Lifecycle for this account
        available_rags = {a.rag_id: a for a in self.rag_library_service.list_artifacts()}
        # Also register build aliases for backward compatibility (e.g. rag_bld_6f509ca2 -> rag_class10_english)
        for a in self.rag_library_service.list_artifacts():
            available_rags[f"rag_{a.build_id}"] = a
        if self.rag_lifecycle_service:
            try:
                rags = self.rag_lifecycle_service.list_rags(account_id=resolved_account_id)
            except TypeError:
                rags = self.rag_lifecycle_service.list_rags()
            for r in rags:
                available_rags[r.rag_id] = r
                for v in r.versions:
                    available_rags[f"rag_{v.build_id}"] = r

        for rag_id in (request.attached_rag_ids or []):
            if rag_id not in available_rags:
                raise RAGArtifactNotFoundError(rag_id)

        now = datetime.now(timezone.utc)
        agent_id = f"agt_{uuid.uuid4().hex[:8]}"
        agent = AgentProfile(
            agent_id=agent_id,
            name=request.name,
            description=request.description or "",
            system_prompt=request.system_prompt,
            grounding_policy=request.grounding_policy or "strict_grounded",
            attached_rag_ids=request.attached_rag_ids or [],
            runtime_ref=request.runtime_ref or "local_gguf",
            account_id=resolved_account_id,
            created_at=now,
            updated_at=now,
        )
        agents_map = self._load_agents_map()
        agents_map[agent_id] = agent
        self._save_agents_map(agents_map)
        return agent

    def update_agent(self, agent_id: str, request: UpdateAgentRequest, account_id: Optional[str] = None) -> AgentProfile:
        """Updates agent metadata or RAG attachments."""
        agents_map = self._load_agents_map()
        if agent_id not in agents_map:
            raise AgentNotFoundError(agent_id)

        agent = agents_map[agent_id]
        if account_id is not None and agent.account_id != account_id:
            raise AgentNotFoundError(agent_id)

        if request.attached_rag_ids is not None:
            available_rags = {a.rag_id: a for a in self.rag_library_service.list_artifacts()}
            for a in self.rag_library_service.list_artifacts():
                available_rags[f"rag_{a.build_id}"] = a
            if self.rag_lifecycle_service:
                try:
                    rags = self.rag_lifecycle_service.list_rags(account_id=agent.account_id)
                except TypeError:
                    rags = self.rag_lifecycle_service.list_rags()
                for r in rags:
                    available_rags[r.rag_id] = r
                    for v in r.versions:
                        available_rags[f"rag_{v.build_id}"] = r
            for rag_id in request.attached_rag_ids:
                if rag_id not in available_rags:
                    raise RAGArtifactNotFoundError(rag_id)
            agent.attached_rag_ids = request.attached_rag_ids

        if request.name is not None:
            agent.name = request.name
        if request.description is not None:
            agent.description = request.description
        if request.system_prompt is not None:
            agent.system_prompt = request.system_prompt
        if request.grounding_policy is not None:
            agent.grounding_policy = request.grounding_policy
        if request.runtime_ref is not None:
            agent.runtime_ref = request.runtime_ref

        agent.updated_at = datetime.now(timezone.utc)
        agents_map[agent_id] = agent
        self._save_agents_map(agents_map)
        return agent

    def delete_agent(self, agent_id: str, account_id: Optional[str] = None) -> None:
        """Deletes an agent profile."""
        agents_map = self._load_agents_map()
        if agent_id not in agents_map:
            raise AgentNotFoundError(agent_id)
        agent = agents_map[agent_id]
        if account_id is not None and agent.account_id != account_id:
            raise AgentNotFoundError(agent_id)
        del agents_map[agent_id]
        self._save_agents_map(agents_map)

    def attach_rag(self, agent_id: str, rag_id: str, account_id: Optional[str] = None) -> AgentProfile:
        """Attaches a RAG artifact reference to an agent."""
        agents_map = self._load_agents_map()
        if agent_id not in agents_map:
            raise AgentNotFoundError(agent_id)

        agent = agents_map[agent_id]
        if account_id is not None and agent.account_id != account_id:
            raise AgentNotFoundError(agent_id)

        available_rags = {a.rag_id: a for a in self.rag_library_service.list_artifacts()}
        for a in self.rag_library_service.list_artifacts():
            available_rags[f"rag_{a.build_id}"] = a
        if self.rag_lifecycle_service:
            try:
                rags = self.rag_lifecycle_service.list_rags(account_id=agent.account_id)
            except TypeError:
                rags = self.rag_lifecycle_service.list_rags()
            for r in rags:
                available_rags[r.rag_id] = r
                for v in r.versions:
                    available_rags[f"rag_{v.build_id}"] = r
        if rag_id not in available_rags:
            raise RAGArtifactNotFoundError(rag_id)

        if rag_id not in agent.attached_rag_ids:
            agent.attached_rag_ids.append(rag_id)
            agent.updated_at = datetime.now(timezone.utc)
            agents_map[agent_id] = agent
            self._save_agents_map(agents_map)
        return agent

    def detach_rag(self, agent_id: str, rag_id: str, account_id: Optional[str] = None) -> AgentProfile:
        """Detaches a RAG artifact reference from an agent."""
        agents_map = self._load_agents_map()
        if agent_id not in agents_map:
            raise AgentNotFoundError(agent_id)

        agent = agents_map[agent_id]
        if account_id is not None and agent.account_id != account_id:
            raise AgentNotFoundError(agent_id)
        if rag_id in agent.attached_rag_ids:
            agent.attached_rag_ids.remove(rag_id)
            agent.updated_at = datetime.now(timezone.utc)
            agents_map[agent_id] = agent
            self._save_agents_map(agents_map)
        return agent

    def get_agents_referencing_rag(self, rag_id: str) -> List[str]:
        """Returns list of agent IDs referencing the specified rag_id."""
        agents_map = self._load_agents_map()
        return [
            agent_id for agent_id, agent in agents_map.items()
            if rag_id in agent.attached_rag_ids
        ]

    def detach_rag_from_all_agents(self, rag_id: str) -> List[str]:
        """
        Atomically unlinks rag_id from all agents, preventing dangling references.
        Controlled cleanup:
        - If a dedicated single-RAG agent (excluding agt_default) loses its only attached RAG,
          the dedicated agent profile is removed entirely so stale assistants do not linger.
        - If an agent has multiple RAGs, only the deleted rag_id is removed; the agent remains valid.
        - If agt_default (the persistent default agent) loses this RAG, it is kept even if 0 RAGs remain.
        """
        agents_map = self._load_agents_map()
        affected = []
        agents_to_delete = []

        for agent_id, agent in agents_map.items():
            if rag_id in agent.attached_rag_ids:
                agent.attached_rag_ids.remove(rag_id)
                agent.updated_at = datetime.now(timezone.utc)
                affected.append(agent_id)

                # Case A: Dedicated single-RAG agent that now has 0 RAGs attached
                # Clean up dedicated assistant, preserving agt_default
                if len(agent.attached_rag_ids) == 0 and agent_id != "agt_default":
                    agents_to_delete.append(agent_id)

        for aid in agents_to_delete:
            del agents_map[aid]

        if affected or agents_to_delete:
            self._save_agents_map(agents_map)
        return affected

    def list_agent_sessions(self, agent_id: str) -> List[Dict]:
        """Lists chat sessions associated with an agent."""
        self.get_agent(agent_id)  # Validate agent existence
        agent_sess_dir = self.agents_dir / agent_id / "sessions"
        if not agent_sess_dir.exists():
            return []
        sessions = []
        for sf in agent_sess_dir.glob("*.json"):
            try:
                with open(sf, "r", encoding="utf-8") as f:
                    s_data = json.load(f)
                sessions.append({
                    "session_id": s_data.get("session_id"),
                    "title": s_data.get("title", "New Conversation"),
                    "message_count": len(s_data.get("messages", [])),
                    "created_at": s_data.get("created_at"),
                    "updated_at": s_data.get("updated_at"),
                })
            except Exception:
                continue
        sessions.sort(key=lambda x: str(x.get("updated_at", "")), reverse=True)
        return sessions

    def create_agent_session(self, agent_id: str, title: Optional[str] = None) -> Dict:
        """Creates a new isolated session for this agent."""
        self.get_agent(agent_id)
        agent_sess_dir = self.agents_dir / agent_id / "sessions"
        agent_sess_dir.mkdir(parents=True, exist_ok=True)

        session_id = f"sess_agt_{uuid.uuid4().hex[:8]}"
        now_str = datetime.now(timezone.utc).isoformat()
        session_data = {
            "session_id": session_id,
            "agent_id": agent_id,
            "title": title or "New Conversation",
            "messages": [],
            "created_at": now_str,
            "updated_at": now_str,
        }
        with open(agent_sess_dir / f"{session_id}.json", "w", encoding="utf-8") as f:
            json.dump(session_data, f, indent=2)
        return session_data

    async def chat(self, agent_id: str, request: AgentChatRequest, workspace_id: str = "default") -> AgentChatResponse:
        """
        Coordinates chat query by dispatching to the verified GenerationService.
        Phase 16: Uses MultiRAGCoordinator to:
        1. Authoritatively resolve all attached RAGs (chain: rag_id -> active_version_id -> RAGVersion -> build_id).
        2. Execute parallel retrieval across all attached builds.
        3. Perform RRF fusion (k=60) and composite deduplication (rag_id:build_id:chunk_id).
        4. Pass unified evidence through the Evidence Gate Adapter and local GGUF.
        5. Enforce composite citation validation (rag_id + build_id + chunk_id) with 0 attribution bleeding.
        """
        agent = self.get_agent(agent_id)
        if not agent.attached_rag_ids:
            raise NoAttachedRAGError(agent_id)

        # If MultiRAGCoordinator is available, use multi-RAG resolution and fusion
        if self.multi_rag_coordinator:
            resolved_targets = self.multi_rag_coordinator.resolve_agent_runtimes(agent)
            
            # Parallel scoped retrieval across all attached knowledge bases
            retrieval_results = await self.multi_rag_coordinator.parallel_retrieve(
                targets=resolved_targets,
                query=request.query,
                top_k_per_rag=request.top_k or 5,
                filters=getattr(request, "filters", None),
            )

            # RRF candidate fusion (k=60) & deduplication - cap to top 4 highest quality candidates
            fused_context = self.multi_rag_coordinator.fuse_and_deduplicate(
                retrieval_results=retrieval_results,
                global_top_k=4,
                rrf_k=60,
            )

            core_request = ChatQueryRequest(
                query=request.query,
                session_id=request.session_id,
                top_k=request.top_k,
                filters=getattr(request, "filters", None),
                temperature=request.temperature,
            )

            gen_resp, raw_citations = await self.generation_service.generate_multi_rag(
                request=core_request,
                workspace_id=workspace_id,
                fused_context=fused_context,
                persist_session=True,
            )

            enriched_citations: List[AgentCitation] = []
            for rc in raw_citations:
                enriched_citations.append(
                    AgentCitation(
                        rag_id=rc["rag_id"],
                        build_id=rc["build_id"],
                        source_id=rc["source_id"],
                        source_name=rc["source_name"],
                        chunk_id=rc["chunk_id"],
                        page_number=rc["page_number"],
                        citation_text=rc["citation_text"],
                        snippet=rc["snippet"],
                    )
                )

            # Persist copy to agent-specific session folder if session_id is active
            try:
                agent_sess_dir = self.agents_dir / agent_id / "sessions"
                agent_sess_dir.mkdir(parents=True, exist_ok=True)
                sess_file = agent_sess_dir / f"{gen_resp.session_id}.json"
                now_str = datetime.now(timezone.utc).isoformat()
                
                sess_data = {"session_id": gen_resp.session_id, "agent_id": agent_id, "messages": []}
                if sess_file.exists():
                    with open(sess_file, "r", encoding="utf-8") as f:
                        sess_data = json.load(f)

                sess_data["updated_at"] = now_str
                sess_data["messages"].append({
                    "role": "user",
                    "content": request.query,
                    "timestamp": now_str,
                })
                sess_data["messages"].append({
                    "role": "assistant",
                    "content": gen_resp.answer,
                    "timestamp": now_str,
                    "citations": [c.model_dump() for c in enriched_citations],
                    "has_insufficient_evidence": gen_resp.has_insufficient_evidence,
                })
                with open(sess_file, "w", encoding="utf-8") as f:
                    json.dump(sess_data, f, indent=2)
            except Exception as e:
                logger.warning("Could not persist agent session file: %s", e)

            return AgentChatResponse(
                agent_id=agent_id,
                session_id=gen_resp.session_id,
                message_id=gen_resp.message_id,
                answer=gen_resp.answer,
                citations=enriched_citations,
                retrieved_chunk_count=gen_resp.retrieved_chunk_count,
                has_insufficient_evidence=gen_resp.has_insufficient_evidence,
                retrieval_latency_ms=gen_resp.retrieval_latency_ms,
                generation_latency_ms=gen_resp.generation_latency_ms,
                original_query=gen_resp.original_query,
                normalized_query=gen_resp.normalized_query,
                generation_provider=gen_resp.generation_provider,
                generation_model=gen_resp.generation_model,
            )

        # Fallback to single primary RAG route if coordinator is not injected
        primary_rag_id = agent.attached_rag_ids[0]
        if self.rag_lifecycle_service:
            try:
                build_id = self.rag_lifecycle_service.resolve_active_build_id(primary_rag_id)
            except Exception:
                build_id = primary_rag_id[4:] if primary_rag_id.startswith("rag_") else primary_rag_id
        else:
            build_id = primary_rag_id[4:] if primary_rag_id.startswith("rag_") else primary_rag_id

        core_request = ChatQueryRequest(
            query=request.query,
            session_id=request.session_id,
            top_k=request.top_k,
            filters=getattr(request, "filters", None),
            temperature=request.temperature,
        )

        gen_resp = await self.generation_service.generate(
            request=core_request,
            workspace_id=workspace_id,
            build_id=build_id,
        )

        enriched_citations = []
        for cite in gen_resp.valid_citations:
            enriched_citations.append(
                AgentCitation(
                    rag_id=primary_rag_id,
                    build_id=build_id,
                    source_id=f"src_{cite.chunk_id.split('_')[2]}" if len(cite.chunk_id.split('_')) > 2 else "src_primary",
                    source_name=cite.source_name,
                    chunk_id=cite.chunk_id,
                    page_number=cite.page_number,
                    citation_text=cite.citation_text,
                    snippet=cite.snippet,
                )
            )

        return AgentChatResponse(
            agent_id=agent_id,
            session_id=gen_resp.session_id,
            message_id=gen_resp.message_id,
            answer=gen_resp.answer,
            citations=enriched_citations,
            retrieved_chunk_count=gen_resp.retrieved_chunk_count,
            has_insufficient_evidence=gen_resp.has_insufficient_evidence,
            retrieval_latency_ms=gen_resp.retrieval_latency_ms,
            generation_latency_ms=gen_resp.generation_latency_ms,
            original_query=gen_resp.original_query,
            normalized_query=gen_resp.normalized_query,
            generation_provider=gen_resp.generation_provider,
            generation_model=gen_resp.generation_model,
        )

    async def stream_chat(
        self, agent_id: str, request: AgentChatRequest, workspace_id: str = "default"
    ) -> AsyncGenerator[dict, None]:
        """
        Streams grounded agent chat progressively over Server-Sent Events (SSE).
        Reuses authoritative stream_multi_rag_generation pipeline.
        Yields status, token, done, error, cancelled events.
        Enriches valid citations with agent and RAG provenance upon completion.
        """
        agent = self.get_agent(agent_id)
        if not agent.attached_rag_ids:
            raise NoAttachedRAGError(agent_id)

        if self.multi_rag_coordinator:
            resolved_targets = self.multi_rag_coordinator.resolve_agent_runtimes(agent)
            
            # Parallel scoped retrieval across all attached knowledge bases
            retrieval_results = await self.multi_rag_coordinator.parallel_retrieve(
                targets=resolved_targets,
                query=request.query,
                top_k_per_rag=request.top_k or 5,
                filters=getattr(request, "filters", None),
            )

            # RRF candidate fusion (k=60) & deduplication - cap to top 4 highest quality candidates
            fused_context = self.multi_rag_coordinator.fuse_and_deduplicate(
                retrieval_results=retrieval_results,
                global_top_k=4,
                rrf_k=60,
            )

            core_request = ChatQueryRequest(
                query=request.query,
                session_id=request.session_id,
                top_k=request.top_k,
                filters=getattr(request, "filters", None),
                temperature=request.temperature,
            )

            async for event in self.generation_service.stream_multi_rag_generation(
                request=core_request,
                workspace_id=workspace_id,
                fused_context=fused_context,
                persist_session=True,
            ):
                ev_name = event.get("event")
                data = event.get("data", {})

                if ev_name == "done":
                    # Enrich citations with AgentCitation model
                    raw_cits = data.get("multi_rag_citations", [])
                    enriched_citations: List[dict] = []
                    for rc in raw_cits:
                        enriched_citations.append(
                            AgentCitation(
                                rag_id=rc["rag_id"],
                                build_id=rc["build_id"],
                                source_id=rc["source_id"],
                                source_name=rc["source_name"],
                                chunk_id=rc["chunk_id"],
                                page_number=rc["page_number"],
                                citation_text=rc["citation_text"],
                                snippet=rc["snippet"],
                            ).model_dump()
                        )
                    data["agent_id"] = agent_id
                    data["citations"] = enriched_citations

                    # Persist copy to agent-specific session folder
                    try:
                        agent_sess_dir = self.agents_dir / agent_id / "sessions"
                        agent_sess_dir.mkdir(parents=True, exist_ok=True)
                        sess_file = agent_sess_dir / f"{data.get('session_id')}.json"
                        now_str = datetime.now(timezone.utc).isoformat()

                        sess_data = {"session_id": data.get("session_id"), "agent_id": agent_id, "messages": []}
                        if sess_file.exists():
                            with open(sess_file, "r", encoding="utf-8") as f:
                                sess_data = json.load(f)

                        sess_data["updated_at"] = now_str
                        sess_data["messages"].append({
                            "role": "user",
                            "content": request.query,
                            "timestamp": now_str,
                        })
                        sess_data["messages"].append({
                            "role": "assistant",
                            "content": data.get("answer", ""),
                            "timestamp": now_str,
                            "citations": enriched_citations,
                            "has_insufficient_evidence": data.get("has_insufficient_evidence", False),
                        })
                        with open(sess_file, "w", encoding="utf-8") as f:
                            json.dump(sess_data, f, indent=2)
                    except Exception as e:
                        logger.warning("Could not persist agent session file in stream: %s", e)

                    yield {"event": "done", "data": data}
                else:
                    yield event
        else:
            # Single RAG fallback
            primary_rag_id = agent.attached_rag_ids[0]
            if self.rag_lifecycle_service:
                try:
                    build_id = self.rag_lifecycle_service.resolve_active_build_id(primary_rag_id)
                except Exception:
                    build_id = primary_rag_id[4:] if primary_rag_id.startswith("rag_") else primary_rag_id
            else:
                build_id = primary_rag_id[4:] if primary_rag_id.startswith("rag_") else primary_rag_id

            core_request = ChatQueryRequest(
                query=request.query,
                session_id=request.session_id,
                top_k=request.top_k,
                filters=getattr(request, "filters", None),
                temperature=request.temperature,
            )

            async for event in self.generation_service.stream_generation(
                request=core_request,
                workspace_id=workspace_id,
                build_id=build_id,
            ):
                ev_name = event.get("event")
                data = event.get("data", {})
                if ev_name == "done":
                    valid_cits = data.get("valid_citations", [])
                    enriched_citations = []
                    for cite in valid_cits:
                        chunk_id = cite.get("chunk_id", "")
                        enriched_citations.append(
                            AgentCitation(
                                rag_id=primary_rag_id,
                                build_id=build_id,
                                source_id=f"src_{chunk_id.split('_')[2]}" if len(chunk_id.split('_')) > 2 else "src_primary",
                                source_name=cite.get("source_name", ""),
                                chunk_id=chunk_id,
                                page_number=cite.get("page_number"),
                                citation_text=cite.get("citation_text", ""),
                                snippet=cite.get("snippet"),
                            ).model_dump()
                        )
                    data["agent_id"] = agent_id
                    data["citations"] = enriched_citations
                    yield {"event": "done", "data": data}
                else:
                    yield event


