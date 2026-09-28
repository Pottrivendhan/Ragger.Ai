"""
Tests for Query Standardization Semantic Intent Preservation:
Verifies:
TEST 1: Input "young seagull" -> Does NOT contain "Who is"
TEST 2: Input "role play" -> Does NOT become "Who is role play?"
TEST 3: Input "design" -> Does NOT become "Who is design?"
TEST 4: Input "machine learning" -> Does NOT become "Who is machine learning?"
TEST 5: Input "The Grumble Family auther name?" -> Preserves question intent with spelling normalization
TEST 6: Input "who is Dr. Ashok T. Krishnan?" -> Preserves "Who is Dr. Ashok T. Krishnan?"
TEST 7: Input "why was the young seagull afraid to fly?" -> Preserves the "why" intent
TEST 8: Real Class 10 English retrieval test for "young seagull"
TEST 9: OOD behavior test for "what is the capital of france?" fails closed
"""

import pytest
from pathlib import Path
from unittest.mock import AsyncMock

from ragger_engine.generation.query_standardization.service import QueryStandardizationService
from ragger_engine.generation.models import ChatQueryRequest
from ragger_engine.generation.service import GenerationService
from ragger_engine.retrieval.service import RetrievalService
from ragger_engine.retrieval.models import RetrievedChunk, ScoreType
from ragger_engine.generation.providers.testing import TestDeterministicLLMProvider


@pytest.mark.asyncio
async def test_young_seagull_not_converted_to_who_is():
    """TEST 1: Input 'young seagull' must not contain 'Who is'."""
    service = QueryStandardizationService()
    res = await service.standardize("young seagull")
    assert res.success is True
    assert "who is" not in res.normalized_query.lower()
    assert res.normalized_query == "young seagull"


@pytest.mark.asyncio
async def test_role_play_not_converted_to_who_is():
    """TEST 2: Input 'role play' must not become 'Who is role play?'."""
    service = QueryStandardizationService()
    res = await service.standardize("role play")
    assert res.success is True
    assert not res.normalized_query.lower().startswith("who is role play")
    assert res.normalized_query == "role play"


@pytest.mark.asyncio
async def test_design_not_converted_to_who_is():
    """TEST 3: Input 'design' must not become 'Who is design?'."""
    service = QueryStandardizationService()
    res = await service.standardize("design")
    assert res.success is True
    assert not res.normalized_query.lower().startswith("who is design")
    assert res.normalized_query == "design"


@pytest.mark.asyncio
async def test_machine_learning_not_converted_to_who_is():
    """TEST 4: Input 'machine learning' must not become 'Who is machine learning?'."""
    service = QueryStandardizationService()
    res = await service.standardize("machine learning")
    assert res.success is True
    assert not res.normalized_query.lower().startswith("who is machine learning")
    assert res.normalized_query == "machine learning"


@pytest.mark.asyncio
async def test_grumble_family_author_name_preservation():
    """TEST 5: Input 'The Grumble Family auther name?' preserves author question with spelling fix."""
    service = QueryStandardizationService()
    res = await service.standardize("The Grumble Family auther name?")
    assert res.success is True
    assert "author" in res.normalized_query.lower()
    assert "the grumble family" in res.normalized_query.lower()


@pytest.mark.asyncio
async def test_who_is_dr_ashok_t_krishnan_preservation():
    """TEST 6: Input 'who is Dr. Ashok T. Krishnan?' preserves question structure."""
    service = QueryStandardizationService()
    res = await service.standardize("who is Dr. Ashok T. Krishnan?")
    assert res.success is True
    assert res.normalized_query == "Who is Dr. Ashok T. Krishnan?"


@pytest.mark.asyncio
async def test_why_was_the_young_seagull_afraid_preservation():
    """TEST 7: Input 'why was the young seagull afraid to fly?' preserves the 'why' intent."""
    service = QueryStandardizationService()
    res = await service.standardize("why was the young seagull afraid to fly?")
    assert res.success is True
    assert res.normalized_query == "Why was the young seagull afraid to fly?"


@pytest.mark.asyncio
async def test_llm_validation_rejects_hallucinated_who_is():
    """Verifies that if an LLM incorrectly outputs 'Who is young seagull?', validator rejects it and falls back safely."""
    mock_provider = AsyncMock()
    mock_provider.generate.return_value = "Who is young seagull?"
    mock_provider.provider_name = "test_provider"
    mock_provider.model_name = "test_model"

    service = QueryStandardizationService(provider=mock_provider)
    res = await service.standardize("young seagull")
    # Validator must reject "Who is young seagull?" and fall back to deterministic standardization
    assert res.normalized_query == "young seagull"
    assert "who is" not in res.normalized_query.lower()


def test_real_class10_english_young_seagull_retrieval(tmp_path: Path, monkeypatch):
    """
    TEST 8: Input 'young seagull' run through GenerationService against simulated Class 10 English chunks.
    Verifies normalized query != 'Who is young seagull?' and retrieved evidence yields grounded answer.
    """
    monkeypatch.setenv("RAGGER_ALLOW_TEST_EMBEDDINGS", "1")
    monkeypatch.setenv("RAGGER_ALLOW_TEST_LLM", "1")

    # Mock retrieval service returning young seagull chunk
    from ragger_engine.retrieval.models import CitationProvenance
    from ragger_engine.builder.models import ChunkType

    class MockRetrieval:
        def retrieve(self, query, build_id=None):
            from unittest.mock import MagicMock
            res = MagicMock()
            prov = CitationProvenance(
                source_id="src_01",
                source_name="10th_English.pdf",
                source_sha256="hash123",
                chunk_id="chk_seagull_01",
                chunk_type=ChunkType.STANDARD_PARAGRAPH,
                page_number=1,
                token_count=25,
            )
            res.results = [
                RetrievedChunk(
                    chunk_id="chk_seagull_01",
                    text="The young seagull was alone on his ledge. His two brothers and his sister had already flown away the day before.",
                    score=0.92,
                    score_type=ScoreType.RRF,
                    provenance=prov,
                    citation="[10th_English.pdf, p. 1]",
                )
            ]
            return res

    gen_service = GenerationService(
        workspace_dir=tmp_path,
        retrieval_service=MockRetrieval(),
        provider_override=TestDeterministicLLMProvider(),
    )

    import asyncio
    req = ChatQueryRequest(query="young seagull")
    resp = asyncio.run(gen_service.generate(req, workspace_id="default"))

    assert resp.normalized_query != "Who is young seagull?"
    assert resp.normalized_query == "young seagull"
    assert resp.has_insufficient_evidence is False
    assert "young seagull" in resp.answer.lower()
    assert len(resp.valid_citations) > 0


def test_out_of_domain_france_capital_fails_closed(tmp_path: Path, monkeypatch):
    """
    TEST 9: 'what is the capital of france?' must still fail closed when no evidence is found in the RAG.
    Ensures Evidence Gate remains strictly intact.
    """
    monkeypatch.setenv("RAGGER_ALLOW_TEST_EMBEDDINGS", "1")
    monkeypatch.setenv("RAGGER_ALLOW_TEST_LLM", "1")

    from ragger_engine.retrieval.models import CitationProvenance
    from ragger_engine.builder.models import ChunkType

    class MockRetrieval:
        def retrieve(self, query, build_id=None):
            from unittest.mock import MagicMock
            res = MagicMock()
            prov = CitationProvenance(
                source_id="src_01",
                source_name="10th_English.pdf",
                source_sha256="hash123",
                chunk_id="chk_seagull_01",
                chunk_type=ChunkType.STANDARD_PARAGRAPH,
                page_number=1,
                token_count=10,
            )
            # Return chunks that have zero mentions of France
            res.results = [
                RetrievedChunk(
                    chunk_id="chk_seagull_01",
                    text="The young seagull was alone on his ledge.",
                    score=0.10,
                    score_type=ScoreType.RRF,
                    provenance=prov,
                    citation="[10th_English.pdf, p. 1]",
                )
            ]
            return res

    gen_service = GenerationService(
        workspace_dir=tmp_path,
        retrieval_service=MockRetrieval(),
        provider_override=TestDeterministicLLMProvider(),
    )

    import asyncio
    req = ChatQueryRequest(query="what is the capital of france?")
    resp = asyncio.run(gen_service.generate(req, workspace_id="default"))

    assert resp.has_insufficient_evidence is True
    assert "couldn't find information" in resp.answer.lower() or "could not find information" in resp.answer.lower()
