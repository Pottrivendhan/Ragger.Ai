"""
Curated Product Copy & Technical Defaults Catalog for Ragger.ai RAG Architectures.
100% deterministic, audit-safe, reproducible product copy (Zero LLM prompts).
"""

from typing import Dict, List
from .models import (
    ArchitectureSpec,
    ChunkingConfig,
    ChunkingStrategyType,
    EmbeddingConfig,
    RagArchitectureId,
    RetrievalConfig,
    RetrievalStrategy,
    VectorDbConfig,
)

ARCHITECTURE_CATALOG: Dict[RagArchitectureId, ArchitectureSpec] = {
    RagArchitectureId.DOCUMENT_RAG: ArchitectureSpec(
        architecture_id=RagArchitectureId.DOCUMENT_RAG,
        title="Document RAG",
        tagline="Standard sliding-window dense retrieval for prose manuals, books, and policy documents.",
        why_recommended=(
            "Your files consist primarily of uniform narrative documents without deep nesting or major tabular data. "
            "Standard boundary-aware paragraph chunking provides optimal retrieval precision with fast indexing."
        ),
        strengths=[
            "Fastest indexing and embedding throughput",
            "Low computational and memory overhead",
            "Precise paragraph-level citation tracking",
            "Broad compatibility with general-purpose embedding models",
        ],
        tradeoffs=[
            "Cannot capture complex parent-child section relationships",
            "Sub-optimal for quantitative calculations or multi-column data",
        ],
        alternative_options=[
            RagArchitectureId.KNOWLEDGE_RAG,
            RagArchitectureId.HYBRID_RAG,
        ],
        default_chunking=ChunkingConfig(
            strategy=ChunkingStrategyType.BOUNDARY_PARAGRAPH,
            chunk_size=512,
            chunk_overlap=64,
        ),
        default_embedding=EmbeddingConfig(
            provider="local_onnx",
            model_name="bge-small-en-v1.5",
            dimension=384,
        ),
        default_vector_db=VectorDbConfig(
            provider="lancedb",
            metric="cosine",
            index_type="auto",
        ),
        default_retrieval=RetrievalConfig(
            strategy=RetrievalStrategy.DENSE_VECTOR_TOP_K,
            top_k=5,
            rerank_enabled=False,
        ),
    ),
    RagArchitectureId.KNOWLEDGE_RAG: ArchitectureSpec(
        architecture_id=RagArchitectureId.KNOWLEDGE_RAG,
        title="Hierarchical Knowledge RAG",
        tagline="Preserves multi-level section context and prevents out-of-context retrieval hallucinations.",
        why_recommended=(
            "Your sources contain structured documentation with nested headings and sections. "
            "Hierarchical RAG preserves parent-child context during vector search to prevent fragmented retrieval."
        ),
        strengths=[
            "Maintains structural context across parent and child sections",
            "High precision for specific operational clauses and subsections",
            "Eliminates out-of-context fragment ambiguity with section breadcrumbs",
            "Automatic parent context deduplication during prompt synthesis",
        ],
        tradeoffs=[
            "Higher index build time due to multi-tier chunk generation",
            "Requires parent context expansion at retrieval time",
        ],
        alternative_options=[
            RagArchitectureId.DOCUMENT_RAG,
            RagArchitectureId.HYBRID_RAG,
        ],
        default_chunking=ChunkingConfig(
            strategy=ChunkingStrategyType.PARENT_CHILD_HIERARCHICAL,
            chunk_size=512,
            chunk_overlap=64,
            child_chunk_size=192,
            parent_chunk_size=768,
        ),
        default_embedding=EmbeddingConfig(
            provider="local_onnx",
            model_name="bge-small-en-v1.5",
            dimension=384,
        ),
        default_vector_db=VectorDbConfig(
            provider="lancedb",
            metric="cosine",
            index_type="auto",
        ),
        default_retrieval=RetrievalConfig(
            strategy=RetrievalStrategy.PARENT_EXPANSION,
            top_k=5,
            rerank_enabled=False,
        ),
    ),
    RagArchitectureId.STRUCTURED_DATA_RAG: ArchitectureSpec(
        architecture_id=RagArchitectureId.STRUCTURED_DATA_RAG,
        title="Structured Data RAG",
        tagline="Dual semantic search and quantitative SQL/filter execution over tabular datasets.",
        why_recommended=(
            "Your workspace is dominated by structured datasets. Text embeddings alone cannot perform "
            "reliable aggregation or calculations; Structured Data RAG uses schema profiling and query routing "
            "for exact quantitative answers."
        ),
        strengths=[
            "Exact numerical calculation and aggregation without LLM math errors",
            "Full column schema, typed definitions, and statistical bounds preservation",
            "Markdown table result formatting with structured analytical context",
            "Dual routing between semantic concepts and analytical queries",
        ],
        tradeoffs=[
            "Requires structured schemas with uniform column definitions",
            "Higher initial schema profiling and column typing overhead",
        ],
        alternative_options=[
            RagArchitectureId.HYBRID_RAG,
            RagArchitectureId.DOCUMENT_RAG,
        ],
        default_chunking=ChunkingConfig(
            strategy=ChunkingStrategyType.TABULAR_SCHEMA_SUMMARY,
            chunk_size=512,
            chunk_overlap=0,
        ),
        default_embedding=EmbeddingConfig(
            provider="local_onnx",
            model_name="bge-small-en-v1.5",
            dimension=384,
        ),
        default_vector_db=VectorDbConfig(
            provider="lancedb",
            metric="cosine",
            index_type="auto",
        ),
        default_retrieval=RetrievalConfig(
            strategy=RetrievalStrategy.DUAL_QUERY_ROUTE,
            top_k=5,
            rerank_enabled=False,
        ),
    ),
    RagArchitectureId.HYBRID_RAG: ArchitectureSpec(
        architecture_id=RagArchitectureId.HYBRID_RAG,
        title="Hybrid Multi-Modal RAG",
        tagline="Reciprocal Rank Fusion (RRF) combining unstructured narrative documents and structured tabular data.",
        why_recommended=(
            "Your workspace combines unstructured narrative documents with structured tabular datasets. "
            "Hybrid RAG concurrently queries vector and structured retrievers, fusing them via Reciprocal Rank Fusion."
        ),
        strengths=[
            "Cross-modal grounding across text, manuals, and numerical tables",
            "Reciprocal Rank Fusion (k=60) prevents retrieval bias toward either modality",
            "Handles both broad conceptual questions and specific metric inquiries",
            "Unified prompt assembly with cross-source references",
        ],
        tradeoffs=[
            "Dual-retriever latency overhead across vector and structured pipelines",
            "Requires query routing coordination to classify incoming intent",
        ],
        alternative_options=[
            RagArchitectureId.KNOWLEDGE_RAG,
            RagArchitectureId.STRUCTURED_DATA_RAG,
            RagArchitectureId.DOCUMENT_RAG,
        ],
        default_chunking=ChunkingConfig(
            strategy=ChunkingStrategyType.BOUNDARY_PARAGRAPH,
            chunk_size=512,
            chunk_overlap=64,
        ),
        default_embedding=EmbeddingConfig(
            provider="local_onnx",
            model_name="bge-small-en-v1.5",
            dimension=384,
        ),
        default_vector_db=VectorDbConfig(
            provider="lancedb",
            metric="cosine",
            index_type="auto",
        ),
        default_retrieval=RetrievalConfig(
            strategy=RetrievalStrategy.HYBRID_RRF,
            top_k=5,
            rerank_enabled=False,
            rrf_k=60,
        ),
    ),
    RagArchitectureId.RESEARCH_RAG: ArchitectureSpec(
        architecture_id=RagArchitectureId.RESEARCH_RAG,
        title="Research-Oriented RAG",
        tagline="Section-aware chunking with hybrid dense + sparse BM25 and cross-encoder reranking.",
        why_recommended=(
            "Your files contain dense technical or academic content. Sparse keyword matching captures "
            "precise terminology and identifiers, while a cross-encoder reranker ensures maximum relevance."
        ),
        strengths=[
            "Catches exact technical terms, formulas, and identifiers via BM25 sparse search",
            "Local cross-encoder reranking maximizes Top-3 precision (Hits@3)",
            "Section-aware boundaries (Abstract, Methods, Results, Discussion)",
            "Robust against vocabulary mismatch in complex domain terminology",
        ],
        tradeoffs=[
            "Cross-encoder reranking adds 20-50ms per query",
            "Higher memory footprint for concurrent dense and sparse indexes",
        ],
        alternative_options=[
            RagArchitectureId.KNOWLEDGE_RAG,
            RagArchitectureId.DOCUMENT_RAG,
        ],
        default_chunking=ChunkingConfig(
            strategy=ChunkingStrategyType.SECTION_AWARE,
            chunk_size=512,
            chunk_overlap=64,
        ),
        default_embedding=EmbeddingConfig(
            provider="local_onnx",
            model_name="bge-small-en-v1.5",
            dimension=384,
        ),
        default_vector_db=VectorDbConfig(
            provider="lancedb",
            metric="cosine",
            index_type="auto",
        ),
        default_retrieval=RetrievalConfig(
            strategy=RetrievalStrategy.DENSE_SPARSE_RERANK,
            top_k=5,
            rerank_enabled=True,
        ),
    ),
    RagArchitectureId.GRAPH_RAG: ArchitectureSpec(
        architecture_id=RagArchitectureId.GRAPH_RAG,
        title="Graph-Oriented RAG",
        tagline="Local property graph traversal for dense entity networks and cross-document relationship discovery.",
        why_recommended=(
            "Designed for multi-entity dossiers, investigations, and dense relationship mapping across disparate documents. "
            "(Advanced Alternative Option)."
        ),
        strengths=[
            "Discovers non-obvious multi-hop connections across documents",
            "Extracts and connects entity relationship clusters",
            "Provides graph neighborhood context expansion",
        ],
        tradeoffs=[
            "Substantially higher index build time due to entity extraction",
            "Experimental graph traversal overhead on local hardware",
        ],
        alternative_options=[
            RagArchitectureId.KNOWLEDGE_RAG,
            RagArchitectureId.HYBRID_RAG,
        ],
        default_chunking=ChunkingConfig(
            strategy=ChunkingStrategyType.ENTITY_GRAPH,
            chunk_size=512,
            chunk_overlap=64,
        ),
        default_embedding=EmbeddingConfig(
            provider="local_onnx",
            model_name="bge-small-en-v1.5",
            dimension=384,
        ),
        default_vector_db=VectorDbConfig(
            provider="lancedb",
            metric="cosine",
            index_type="auto",
        ),
        default_retrieval=RetrievalConfig(
            strategy=RetrievalStrategy.GRAPH_TRAVERSAL,
            top_k=5,
            rerank_enabled=False,
        ),
    ),
}


def get_architecture_spec(architecture_id: RagArchitectureId) -> ArchitectureSpec:
    """Retrieve the architecture specification from the catalog."""
    if architecture_id not in ARCHITECTURE_CATALOG:
        raise KeyError(f"Unknown architecture_id: {architecture_id}")
    return ARCHITECTURE_CATALOG[architecture_id]


def list_architecture_specs() -> List[ArchitectureSpec]:
    """List all supported architecture specifications."""
    return list(ARCHITECTURE_CATALOG.values())
