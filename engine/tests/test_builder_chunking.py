"""
Tests for Phase 5 Chunking Subsystem.
Verifies boundary paragraph, parent-child hierarchical, tabular schema, and section-aware chunkers,
alongside deterministic chunk ID computation and Option B (graph_rag rejection).
"""

import pytest
from ragger_engine.builder.chunking.base import compute_deterministic_chunk_id, estimate_token_count
from ragger_engine.builder.chunking.boundary import BoundaryParagraphChunker
from ragger_engine.builder.chunking.hierarchical import ParentChildHierarchicalChunker
from ragger_engine.builder.chunking.registry import get_chunker_for_strategy
from ragger_engine.builder.chunking.section import SectionAwareChunker
from ragger_engine.builder.chunking.tabular import TabularSchemaChunker
from ragger_engine.builder.exceptions import ArchitectureNotBuildableError
from ragger_engine.builder.models import ChunkType
from ragger_engine.ingestion.models import (
    ColumnSchema,
    DatasetModel,
    DocumentBlock,
    DocumentModel,
    SourceLocation,
    TableSheet,
)
from ragger_engine.recommendation.models import ChunkingConfig, ChunkingStrategyType


def test_estimate_token_count():
    assert estimate_token_count("") == 0
    assert estimate_token_count("Hello world") >= 2
    assert estimate_token_count("A quick brown fox jumps over the lazy dog.") >= 9


def test_deterministic_chunk_id_reproducibility():
    id1 = compute_deterministic_chunk_id("source-12345", "bnd", 0, "Consistent text content")
    id2 = compute_deterministic_chunk_id("source-12345", "bnd", 0, "Consistent text content")
    id3 = compute_deterministic_chunk_id("source-12345", "bnd", 0, "Different text content")

    assert id1 == id2
    assert id1 != id3
    assert id1.startswith("chk_source1_bnd_00000_")


def test_boundary_paragraph_chunker():
    chunker = BoundaryParagraphChunker()
    doc = DocumentModel(
        source_id="src_handbook",
        title="Employee Handbook",
        format="pdf",
        blocks=[
            DocumentBlock(
                block_id="b1",
                type="heading",
                level=1,
                content="Chapter 1: Benefits",
                location=SourceLocation(page_number=1),
            ),
            DocumentBlock(
                block_id="b2",
                type="paragraph",
                content="Our health insurance covers medical, dental, and vision care starting on day one.",
                location=SourceLocation(page_number=1),
            ),
            DocumentBlock(
                block_id="b3",
                type="paragraph",
                content="Employees are eligible for 20 days of paid time off each calendar year.",
                location=SourceLocation(page_number=2),
            ),
        ],
    )
    config = ChunkingConfig(
        strategy=ChunkingStrategyType.BOUNDARY_PARAGRAPH,
        chunk_size=128,
        chunk_overlap=16,
    )
    chunks = chunker.chunk(doc, "src_handbook", "handbook.pdf", config)

    assert len(chunks) >= 1
    for c in chunks:
        assert c.chunk_type == ChunkType.STANDARD_PARAGRAPH
        assert c.source_id == "src_handbook"
        assert c.metadata.source_name == "handbook.pdf"
        assert "Chapter 1: Benefits" in c.metadata.heading_path
        assert c.token_count > 0


def test_parent_child_hierarchical_chunker():
    chunker = ParentChildHierarchicalChunker()
    doc = DocumentModel(
        source_id="src_tech",
        title="Technical Specification",
        format="pdf",
        blocks=[
            DocumentBlock(
                block_id="h1",
                type="heading",
                level=1,
                content="Section 4: Safety Protocols",
                location=SourceLocation(page_number=5),
            ),
            DocumentBlock(
                block_id="p1",
                type="paragraph",
                content="All operators must wear level 3 protective equipment before entering containment.",
                location=SourceLocation(page_number=5),
            ),
            DocumentBlock(
                block_id="p2",
                type="paragraph",
                content="Emergency shutdown triggers when thermal readings exceed 450 degrees Celsius.",
                location=SourceLocation(page_number=6),
            ),
        ],
    )
    config = ChunkingConfig(
        strategy=ChunkingStrategyType.PARENT_CHILD_HIERARCHICAL,
        chunk_size=512,
        child_chunk_size=64,
        parent_chunk_size=256,
    )
    chunks = chunker.chunk(doc, "src_tech", "tech_spec.pdf", config)

    parents = [c for c in chunks if c.chunk_type == ChunkType.PARENT_CHUNK]
    children = [c for c in chunks if c.chunk_type == ChunkType.CHILD_CHUNK]

    assert len(parents) >= 1
    assert len(children) >= 1

    parent_ids = {p.chunk_id for p in parents}
    for ch in children:
        assert ch.metadata.parent_chunk_id in parent_ids
        assert "Section 4: Safety Protocols" in ch.metadata.heading_path


def test_tabular_schema_chunker():
    chunker = TabularSchemaChunker()
    dataset = DatasetModel(
        source_id="src_sales",
        title="Quarterly Sales",
        format="csv",
        sheets=[
            TableSheet(
                sheet_name="Q1_Sales",
                columns=[
                    ColumnSchema(name="Region", inferred_type="string"),
                    ColumnSchema(name="Revenue", inferred_type="float"),
                    ColumnSchema(name="Units", inferred_type="integer"),
                ],
                total_rows=3,
                total_columns=3,
                rows=[
                    {"Region": "North America", "Revenue": 125000.50, "Units": 450},
                    {"Region": "Europe", "Revenue": 98000.00, "Units": 320},
                    {"Region": "Asia Pacific", "Revenue": 154200.75, "Units": 510},
                ],
            )
        ],
    )
    config = ChunkingConfig(
        strategy=ChunkingStrategyType.TABULAR_SCHEMA_SUMMARY,
        chunk_size=128,
        chunk_overlap=0,
    )
    chunks = chunker.chunk(dataset, "src_sales", "sales.csv", config)

    schema_chunks = [c for c in chunks if c.chunk_type == ChunkType.TABULAR_SCHEMA]
    row_chunks = [c for c in chunks if c.chunk_type == ChunkType.TABULAR_ROW]

    assert len(schema_chunks) == 1
    assert len(row_chunks) >= 1

    schema = schema_chunks[0]
    assert "Region (string)" in schema.text
    assert "Revenue (float)" in schema.text
    assert schema.metadata.sheet_name == "Q1_Sales"

    row = row_chunks[0]
    assert "North America" in row.text
    assert "125000.5" in row.text
    assert row.metadata.sheet_name == "Q1_Sales"
    assert "start_row" in row.metadata.extra


def test_section_aware_chunker():
    chunker = SectionAwareChunker()
    doc = DocumentModel(
        source_id="src_paper",
        title="Attention Is All You Need",
        format="pdf",
        blocks=[
            DocumentBlock(block_id="h1", type="heading", level=1, content="Abstract"),
            DocumentBlock(block_id="p1", type="paragraph", content="The dominant sequence transduction models are based on complex recurrent networks."),
            DocumentBlock(block_id="h2", type="heading", level=1, content="1. Introduction"),
            DocumentBlock(block_id="p2", type="paragraph", content="Recurrent neural networks have been firmly established as state of the art."),
            DocumentBlock(block_id="h3", type="heading", level=1, content="3. Model Architecture"),
            DocumentBlock(block_id="p3", type="paragraph", content="Most competitive neural sequence models have an encoder-decoder structure."),
        ],
    )
    config = ChunkingConfig(
        strategy=ChunkingStrategyType.SECTION_AWARE,
        chunk_size=64,
        chunk_overlap=8,
    )
    chunks = chunker.chunk(doc, "src_paper", "transformer.pdf", config)

    assert len(chunks) >= 3
    section_types = [c.metadata.extra.get("section_type") for c in chunks]
    assert "abstract" in section_types
    assert "introduction" in section_types
    assert "methodology" in section_types


def test_chunker_registry_and_option_b_graph_rejection():
    # Valid buildable chunkers resolve properly
    assert isinstance(get_chunker_for_strategy(ChunkingStrategyType.BOUNDARY_PARAGRAPH), BoundaryParagraphChunker)
    assert isinstance(get_chunker_for_strategy(ChunkingStrategyType.PARENT_CHILD_HIERARCHICAL), ParentChildHierarchicalChunker)
    assert isinstance(get_chunker_for_strategy(ChunkingStrategyType.TABULAR_SCHEMA_SUMMARY), TabularSchemaChunker)
    assert isinstance(get_chunker_for_strategy(ChunkingStrategyType.SECTION_AWARE), SectionAwareChunker)

    # Option B: ENTITY_GRAPH is rejected as non-buildable in Phase 5
    with pytest.raises(ArchitectureNotBuildableError) as exc:
        get_chunker_for_strategy(ChunkingStrategyType.ENTITY_GRAPH)
    assert "ENTITY_GRAPH" in str(exc.value)
