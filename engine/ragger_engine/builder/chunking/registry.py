"""
Registry and factory for resolving chunker implementations based on approved ChunkingStrategyType.
"""

from ragger_engine.recommendation.models import ChunkingStrategyType
from ..exceptions import ArchitectureNotBuildableError, ChunkingError
from .base import BaseChunker
from .boundary import BoundaryParagraphChunker
from .hierarchical import ParentChildHierarchicalChunker
from .section import SectionAwareChunker
from .tabular import TabularSchemaChunker


def get_chunker_for_strategy(strategy: ChunkingStrategyType) -> BaseChunker:
    """
    Resolves the canonical chunker instance corresponding to the approved chunking strategy.
    Enforces Option B: ENTITY_GRAPH is explicitly rejected as non-buildable in Phase 5.
    """
    if strategy == ChunkingStrategyType.BOUNDARY_PARAGRAPH:
        return BoundaryParagraphChunker()
    elif strategy == ChunkingStrategyType.PARENT_CHILD_HIERARCHICAL:
        return ParentChildHierarchicalChunker()
    elif strategy == ChunkingStrategyType.TABULAR_SCHEMA_SUMMARY:
        return TabularSchemaChunker()
    elif strategy == ChunkingStrategyType.SECTION_AWARE:
        return SectionAwareChunker()
    elif strategy == ChunkingStrategyType.ENTITY_GRAPH:
        raise ArchitectureNotBuildableError(
            "Graph RAG chunking (ENTITY_GRAPH) is designated design-only and is non-buildable in Phase 5."
        )
    else:
        raise ChunkingError(f"Unsupported chunking strategy: {strategy}")
