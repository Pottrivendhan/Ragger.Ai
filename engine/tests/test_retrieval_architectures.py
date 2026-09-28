"""
Comprehensive architecture tests for Phase 6 RAG Retrieval Engine.
Verifies the 5 concrete buildable architectures:
1. Document RAG: Dense vector Top-K with cosine similarity
2. Knowledge RAG: Child vector match -> Parent chunk expansion and shared-parent deduplication
3. Structured Data RAG: Deterministic Dual-query routing (Quantitative vs. Semantic)
4. Hybrid RAG: Parallel Dense + Sparse BM25 fused with Reciprocal Rank Fusion (k=60)
5. Research RAG: Section-aware boosting and deterministic lexical_dense reranking
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import pytest

from ragger_engine.builder.models import BuildManifest, Chunk, ChunkMetadata, ChunkType
from ragger_engine.builder.storage.local_flat_store import LocalFlatVectorStore
from ragger_engine.retrieval.models import (
    RetrievalFilter,
    RetrievalQuery,
    ScoreType,
)
from ragger_engine.retrieval.service import RetrievalService


@pytest.fixture(autouse=True)
def allow_test_embeddings(monkeypatch):
    monkeypatch.setenv("RAGGER_ALLOW_TEST_EMBEDDINGS", "1")


def setup_workspace_with_chunks(
    workspace_dir: Path,
    architecture: str,
    chunks: list[Chunk],
    vectors: list[list[float]],
    retrieval_config: dict = None,
    dimension: int = 384,
) -> RetrievalService:
    """Sets up a complete Phase 5 build with given chunks and vectors."""
    build_id = f"bld_{architecture[:4]}_001"
    build_dir = workspace_dir / "builds" / build_id
    index_dir = build_dir / "index"
    index_dir.mkdir(parents=True, exist_ok=True)

    # Persist via LocalFlatVectorStore
    store = LocalFlatVectorStore()
    store.add_chunks(chunks, vectors)
    store.persist(index_dir)

    now = datetime.now(timezone.utc)
    manifest_dict = {
        "manifest_id": f"man_{build_id}",
        "workspace_id": "default",
        "build_id": build_id,
        "config_id": "cfg_test_arch",
        "config_version": 1,
        "config_hash": "c" * 64,
        "source_ids": list({c.source_id for c in chunks}),
        "source_hashes": {c.source_id: "s" * 64 for c in chunks},
        "approved_architecture": architecture,
        "chunking_config": {"strategy": "boundary_paragraph", "chunk_size": 512, "chunk_overlap": 64},
        "embedding_config": {"provider": "test_deterministic", "model_name": "bge-small-en-v1.5", "dimension": dimension},
        "vector_db_config": {"provider": "local_flat_index", "metric": "cosine", "index_type": "auto"},
        "retrieval_config": retrieval_config or {"strategy": "dense_vector_top_k", "top_k": 5, "rerank_enabled": False},
        "chunk_count": len(chunks),
        "vector_count": len(vectors),
        "embedding_dimension": dimension,
        "embedding_model": "bge-small-en-v1.5",
        "vector_store": "local_flat_index",
        "started_at": now,
        "completed_at": now,
        "build_duration_ms": 120.0,
        "status": "completed",
    }
    manifest_dict["manifest_hash"] = BuildManifest.compute_manifest_hash(manifest_dict)
    manifest = BuildManifest(**manifest_dict)

    with open(build_dir / "manifest.json", "w", encoding="utf-8") as f:
        f.write(manifest.model_dump_json(indent=2))

    pointer = {
        "active_build_id": build_id,
        "manifest_id": manifest.manifest_id,
        "manifest_hash": manifest.manifest_hash,
        "activated_at": now.isoformat(),
    }
    with open(workspace_dir / "active_build.json", "w", encoding="utf-8") as f:
        json.dump(pointer, f, indent=2)

    return RetrievalService(workspace_dir=workspace_dir)


def test_document_rag_retrieval(tmp_path):
    """Tests Document RAG: dense vector top-k retrieval and cosine similarity ranking."""
    dim = 384
    # Chunk 1 aligns strongly with query vector
    vec1 = [1.0 / (dim ** 0.5)] * dim
    vec2 = [-1.0 / (dim ** 0.5)] * dim

    chunks = [
        Chunk(
            chunk_id="chk_doc_1",
            source_id="src_policy",
            text="Employee security policy. Passwords must be 12 characters minimum.",
            chunk_type=ChunkType.STANDARD_PARAGRAPH,
            metadata=ChunkMetadata(
                source_id="src_policy",
                source_name="security_policy.pdf",
                chunk_index=0,
                token_count=10,
                page_number=3,
                heading_path=["Security", "Password Requirements"],
            ),
            token_count=10,
        ),
        Chunk(
            chunk_id="chk_doc_2",
            source_id="src_policy",
            text="Cafeteria menu. Lunch is served from 11:30am to 1:30pm daily.",
            chunk_type=ChunkType.STANDARD_PARAGRAPH,
            metadata=ChunkMetadata(
                source_id="src_policy",
                source_name="security_policy.pdf",
                chunk_index=1,
                token_count=11,
                page_number=8,
                heading_path=["Facilities", "Cafeteria"],
            ),
            token_count=11,
        ),
    ]

    from ragger_engine.builder.embeddings.testing import TestDeterministicEmbeddingProvider
    provider = TestDeterministicEmbeddingProvider(dimension=dim)
    vectors = provider.embed_batch([c.text for c in chunks])

    service = setup_workspace_with_chunks(tmp_path, "document_rag", chunks, vectors, dimension=dim)
    res = service.retrieve(RetrievalQuery(query=chunks[0].text, top_k=2))

    assert len(res.results) == 2
    top = res.results[0]
    assert top.chunk_id == "chk_doc_1"
    assert top.score_type == ScoreType.COSINE_SIMILARITY
    assert top.provenance.source_name == "security_policy.pdf"
    assert top.provenance.page_number == 3
    assert "Password Requirements" in top.provenance.heading_path
    assert "[Source: security_policy.pdf, Page: 3, Section: Password Requirements]" in top.citation


def test_knowledge_rag_parent_expansion(tmp_path):
    """
    Tests Knowledge RAG: Child vector match expands to encompassing parent chunk.
    Deduplicates shared parents while accumulating matched child snippets.
    """
    dim = 384

    parent_chunk = Chunk(
        chunk_id="chk_parent_100",
        source_id="src_kb",
        text="Section 4: Enterprise Network Configuration. This section details subnet isolation, firewall rules, and VPC peering connections across availability zones.",
        chunk_type=ChunkType.PARENT_CHUNK,
        metadata=ChunkMetadata(
            source_id="src_kb",
            source_name="network_spec.docx",
            chunk_index=0,
            token_count=25,
            heading_path=["Architecture", "Network Configuration"],
        ),
        token_count=25,
    )

    child1 = Chunk(
        chunk_id="chk_child_1",
        source_id="src_kb",
        text="Subnet isolation ensures DMZ traffic cannot access database tiers directly.",
        chunk_type=ChunkType.CHILD_CHUNK,
        metadata=ChunkMetadata(
            source_id="src_kb",
            source_name="network_spec.docx",
            chunk_index=1,
            token_count=12,
            parent_chunk_id="chk_parent_100",
            heading_path=["Architecture", "Network Configuration", "Subnets"],
        ),
        token_count=12,
    )

    child2 = Chunk(
        chunk_id="chk_child_2",
        source_id="src_kb",
        text="Firewall rules restrict inbound port 22 traffic exclusively to the VPN gateway.",
        chunk_type=ChunkType.CHILD_CHUNK,
        metadata=ChunkMetadata(
            source_id="src_kb",
            source_name="network_spec.docx",
            chunk_index=2,
            token_count=14,
            parent_chunk_id="chk_parent_100",
            heading_path=["Architecture", "Network Configuration", "Firewalls"],
        ),
        token_count=14,
    )

    chunks = [parent_chunk, child1, child2]
    from ragger_engine.builder.embeddings.testing import TestDeterministicEmbeddingProvider
    provider = TestDeterministicEmbeddingProvider(dimension=dim)
    vectors = provider.embed_batch([c.text for c in chunks])

    service = setup_workspace_with_chunks(
        tmp_path,
        "knowledge_rag",
        chunks,
        vectors,
        retrieval_config={"strategy": "parent_expansion", "top_k": 5},
        dimension=dim,
    )

    res = service.retrieve(RetrievalQuery(query=child1.text))

    # Both child matches expand to the single parent chunk
    assert len(res.results) == 1
    result = res.results[0]
    assert result.chunk_id == "chk_parent_100"
    assert result.text == parent_chunk.text
    assert result.score_type == ScoreType.COSINE_SIMILARITY
    # Matched child snippets are aggregated
    assert len(result.matched_child_snippets) >= 1
    assert child1.text in result.matched_child_snippets


def test_structured_data_rag_deterministic_routing(tmp_path):
    """
    Tests Structured Data RAG dual-query routing:
    1. Quantitative query -> structured filter match
    2. Ambiguous / Semantic query -> semantic vector route
    """
    dim = 384
    schema_chunk = Chunk(
        chunk_id="chk_schema_sales",
        source_id="src_sales",
        text="Table: sales. Columns: region (str), revenue (float), year (int), units_sold (int).",
        chunk_type=ChunkType.TABULAR_SCHEMA,
        metadata=ChunkMetadata(
            source_id="src_sales",
            source_name="sales.csv",
            chunk_index=0,
            token_count=15,
            model_type="dataset",
        ),
        token_count=15,
    )

    row_chunk = Chunk(
        chunk_id="chk_row_apac_2024",
        source_id="src_sales",
        text="Row record: Region APAC, revenue 850000, year 2024, units 4200.",
        chunk_type=ChunkType.TABULAR_ROW,
        metadata=ChunkMetadata(
            source_id="src_sales",
            source_name="sales.csv",
            chunk_index=1,
            token_count=12,
            model_type="dataset",
        ),
        token_count=12,
    )

    chunks = [schema_chunk, row_chunk]
    vectors = [[0.1] * dim, [0.2] * dim]

    service = setup_workspace_with_chunks(
        tmp_path,
        "structured_data_rag",
        chunks,
        vectors,
        retrieval_config={"strategy": "dual_query_route", "top_k": 5},
        dimension=dim,
    )

    # 1. Quantitative Query
    quant_res = service.retrieve(RetrievalQuery(query="What was the total revenue in 2024?"))
    assert len(quant_res.results) > 0
    assert quant_res.results[0].score_type == ScoreType.STRUCTURED_MATCH
    assert quant_res.results[0].score > 0.0

    # 2. Ambiguous / Semantic Query (defaults to semantic vector route)
    sem_res = service.retrieve(RetrievalQuery(query="apac enterprise contracts"))
    assert len(sem_res.results) > 0
    assert sem_res.results[0].score_type == ScoreType.COSINE_SIMILARITY


def test_hybrid_rag_reciprocal_rank_fusion(tmp_path):
    """
    Tests Hybrid RAG: Parallel dense and in-memory BM25 lexical search
    fused with Reciprocal Rank Fusion (k=60). Verifies exact keyword boosting.
    """
    dim = 384
    # Document with exact rare acronym 'XYZ_ALPHA_99'
    chk_exact = Chunk(
        chunk_id="chk_exact_code",
        source_id="src_code",
        text="Critical failure code XYZ_ALPHA_99 indicates memory bus parity violation.",
        chunk_type=ChunkType.STANDARD_PARAGRAPH,
        metadata=ChunkMetadata(
            source_id="src_code",
            source_name="error_codes.txt",
            chunk_index=0,
            token_count=12,
        ),
        token_count=12,
    )

    chk_generic = Chunk(
        chunk_id="chk_generic",
        source_id="src_code",
        text="General hardware troubleshooting guide for memory faults and bus warnings.",
        chunk_type=ChunkType.STANDARD_PARAGRAPH,
        metadata=ChunkMetadata(
            source_id="src_code",
            source_name="error_codes.txt",
            chunk_index=1,
            token_count=11,
        ),
        token_count=11,
    )

    chunks = [chk_exact, chk_generic]
    # Invert vectors so generic has higher dense similarity, but exact has high BM25
    vectors = [[-0.5] * dim, [0.8] * dim]

    service = setup_workspace_with_chunks(
        tmp_path,
        "hybrid_rag",
        chunks,
        vectors,
        retrieval_config={"strategy": "hybrid_rrf", "top_k": 5, "rrf_k": 60},
        dimension=dim,
    )

    res = service.retrieve(RetrievalQuery(query="XYZ_ALPHA_99 error"))
    assert len(res.results) > 0
    # Both candidates scored with RRF
    for r in res.results:
        assert r.score_type == ScoreType.RRF
        assert 0.0 < r.score <= 0.05

    # Exact token chunk is ranked first due to BM25 boost
    assert res.results[0].chunk_id == "chk_exact_code"


def test_research_rag_lexical_dense_rerank(tmp_path):
    """
    Tests Research RAG: Section-type boosting and deterministic lexical_dense reranking.
    Abstract section receives 1.25x boost over default sections.
    """
    dim = 384
    abstract_chunk = Chunk(
        chunk_id="chk_abstract",
        source_id="src_paper",
        text="Abstract. Neural retrieval methodologies benchmarks.",
        chunk_type=ChunkType.SECTION_BLOCK,
        metadata=ChunkMetadata(
            source_id="src_paper",
            source_name="paper.pdf",
            chunk_index=0,
            token_count=5,
            heading_path=["Paper Title", "Abstract"],
            extra={"section_type": "abstract"},
        ),
        token_count=5,
    )

    other_chunk = Chunk(
        chunk_id="chk_intro",
        source_id="src_paper",
        text="Introduction. Neural retrieval methodologies benchmarks.",
        chunk_type=ChunkType.SECTION_BLOCK,
        metadata=ChunkMetadata(
            source_id="src_paper",
            source_name="paper.pdf",
            chunk_index=1,
            token_count=5,
            heading_path=["Paper Title", "Introduction"],
            extra={"section_type": "intro"},
        ),
        token_count=5,
    )

    chunks = [abstract_chunk, other_chunk]
    # Equal vector similarities
    vectors = [[0.5] * dim, [0.5] * dim]

    service = setup_workspace_with_chunks(
        tmp_path,
        "research_rag",
        chunks,
        vectors,
        retrieval_config={"strategy": "dense_sparse_rerank", "top_k": 5},
        dimension=dim,
    )

    res = service.retrieve(RetrievalQuery(query="neural retrieval methodologies"))
    assert len(res.results) == 2
    assert res.results[0].score_type == ScoreType.LEXICAL_DENSE
    # Abstract chunk ranks higher due to 1.25x section boost vs 1.05x intro boost
    assert res.results[0].chunk_id == "chk_abstract"
    assert res.results[0].score > res.results[1].score


def test_research_rag_approved_boost_values():
    """
    Directly tests that get_section_boost adheres to the approved contract:
    - Abstract: 1.25
    - Results: 1.20
    - Methodology: 1.15
    - Intro: 1.05
    - Other: 1.00
    """
    from ragger_engine.retrieval.strategies.research import get_section_boost

    def make_chunk(headings: list[str], section_type: str) -> Chunk:
        return Chunk(
            chunk_id="test_chk",
            source_id="src_test",
            text="Test text",
            chunk_type=ChunkType.SECTION_BLOCK,
            metadata=ChunkMetadata(
                source_id="src_test",
                source_name="test.pdf",
                chunk_index=0,
                token_count=2,
                heading_path=headings,
                extra={"section_type": section_type},
            ),
            token_count=2,
        )

    assert get_section_boost(make_chunk(["Abstract"], "abstract")) == 1.25
    assert get_section_boost(make_chunk(["Results and Discussion"], "results")) == 1.20
    assert get_section_boost(make_chunk(["Experimental Methodology"], "methodology")) == 1.15
    assert get_section_boost(make_chunk(["Introduction"], "intro")) == 1.05
    assert get_section_boost(make_chunk(["References"], "appendix")) == 1.00

