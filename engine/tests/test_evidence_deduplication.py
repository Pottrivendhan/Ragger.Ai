"""
Regression tests for deterministic evidence deduplication and repetition prevention.
Covers:
TEST 1: Exact chunk identity deduplication
TEST 2: Exact normalized text deduplication
TEST 3: Near-duplicate text collapse
TEST 4: Distinct chunks preservation (no over-deduplication)
TEST 5: Multi-RAG candidate deduplication without cross-RAG bleeding
TEST 6: 'The Grumble Family' regression against simulated & real chunks
TEST 7: Generated answer repetition cleanup
"""

from pathlib import Path
import pytest
from unittest.mock import MagicMock

from ragger_engine.builder.models import ChunkType
from ragger_engine.retrieval.models import RetrievedChunk, ScoreType, CitationProvenance
from ragger_engine.retrieval.deduplication import (
    deduplicate_retrieved_chunks,
    deduplicate_multi_rag_candidates,
    deduplicate_answer_text,
    normalize_text_for_dedup,
    compute_jaccard_similarity,
)
from ragger_engine.multi_rag.models import MultiRAGCandidate


def _make_chunk(chunk_id: str, text: str, score: float = 0.9, page: int = 1, source_id: str = "src_01") -> RetrievedChunk:
    prov = CitationProvenance(
        source_id=source_id,
        source_name="test_doc.pdf",
        source_sha256="sha256_mock",
        chunk_id=chunk_id,
        chunk_type=ChunkType.STANDARD_PARAGRAPH,
        page_number=page,
        token_count=len(text.split()),
    )
    return RetrievedChunk(
        chunk_id=chunk_id,
        text=text,
        score=score,
        score_type=ScoreType.RRF,
        provenance=prov,
        citation=f"[test_doc.pdf, p. {page}]",
    )


def test_level1_exact_chunk_id_deduplication():
    """Identical chunk IDs in candidate set must be collapsed to one."""
    c1 = _make_chunk("chk_01", "The quick brown fox jumps over the lazy dog.", score=0.95)
    c2 = _make_chunk("chk_01", "The quick brown fox jumps over the lazy dog.", score=0.85)
    res = deduplicate_retrieved_chunks([c1, c2])
    assert len(res) == 1
    assert res[0].chunk_id == "chk_01"
    assert res[0].score == 0.95


def test_level2_exact_normalized_text_deduplication():
    """Different chunk IDs with identical normalized text from the same source must collapse to the canonical representative."""
    c1 = _make_chunk("chk_01", "Apple is a fruit.", score=0.92)
    c2 = _make_chunk("chk_02", "--- Page 1 End ---\n\napple is a fruit.\n\n45 unit.indd 45 28-11-2022 18:19:39", score=0.88)
    c3 = _make_chunk("chk_03", "Apples can be red or green.", score=0.80)

    res = deduplicate_retrieved_chunks([c1, c2, c3])
    assert len(res) == 2
    assert res[0].chunk_id == "chk_01"
    assert res[1].chunk_id == "chk_03"


def test_level3_near_duplicate_collapse():
    """Two chunks from the same source with near-identical overlapping content collapse to highest-scoring representative."""
    t1 = (
        "The Grumble Family lives on Complaining Street in the city of Never-Are-Satisfied. "
        "They are known for their constant complaints and growling at the rain and the sun. "
        "Whatever comes, there is always something amiss with their life."
    )
    t2 = (
        "The Grumble Family lives on Complaining Street in the city of Never-Are-Satisfied. "
        "They are known for their constant complaints and growling at the rain and the sun. "
        "Whatever comes, there is always something amiss."
    )
    c1 = _make_chunk("chk_g1", t1, score=0.96)
    c2 = _make_chunk("chk_g2", t2, score=0.89)

    res = deduplicate_retrieved_chunks([c1, c2], near_duplicate_threshold=0.80)
    assert len(res) == 1
    assert res[0].chunk_id == "chk_g1"


def test_distinct_chunks_preserved():
    """Distinct facts from the document must not be falsely merged or discarded."""
    c1 = _make_chunk("chk_01", "The young seagull was alone on his ledge and afraid to fly.", score=0.95)
    c2 = _make_chunk("chk_02", "His mother tore at a piece of fish and flew across to encourage him.", score=0.90)
    c3 = _make_chunk("chk_03", "He screamed with delight as he spread his wings and finally flew.", score=0.85)

    res = deduplicate_retrieved_chunks([c1, c2, c3])
    assert len(res) == 3
    assert [c.chunk_id for c in res] == ["chk_01", "chk_02", "chk_03"]


def test_multi_rag_candidate_deduplication_isolation():
    """Candidates from different RAGs must NEVER be merged even if text is similar."""
    cand1 = MultiRAGCandidate(
        rag_id="rag_english",
        rag_name="Class 10 English",
        version_id="v1",
        version_tag="v1.0",
        build_id="bld_01",
        chunk_id="chk_shared",
        source_id="src_doc",
        source_name="guide.pdf",
        page_number=1,
        heading_path=[],
        text="Grammar rules and sentence structures for writing reports.",
        raw_score=0.91,
        retrieval_rank=1,
    )
    cand2 = MultiRAGCandidate(
        rag_id="rag_science",
        rag_name="Class 10 Science",
        version_id="v1",
        version_tag="v1.0",
        build_id="bld_02",
        chunk_id="chk_shared",
        source_id="src_doc",
        source_name="guide.pdf",
        page_number=1,
        heading_path=[],
        text="Grammar rules and sentence structures for writing reports.",
        raw_score=0.88,
        retrieval_rank=1,
    )

    # Cross-RAG isolation: both must remain distinct
    fused = deduplicate_multi_rag_candidates([cand1, cand2])
    assert len(fused) == 2
    assert fused[0].rag_id == "rag_english"
    assert fused[1].rag_id == "rag_science"


def test_deduplicate_answer_text_repetition_loop():
    """Verifies that repetitive decoded loops in generated responses are cleaned to a single coherent answer."""
    repeated_output = (
        "The Grumble Family is a family that lives on Complaining Street in the city of Never-Are-Satisfied. "
        "They are known for their constant complaints.\n\n"
        "The Grumble Family is a family that lives on Complaining Street in the city of Never-Are-Satisfied. "
        "They are known for their constant complaints. 45-10th English_Unit_2.indd 45 28-11-2022 18:19:39\n\n"
        "The Grumble Family is a family that lives on Complaining Street in the city of Never-Are-Satisfied. "
        "They are known for their constant complaints."
    )
    cleaned = deduplicate_answer_text(repeated_output)
    paragraphs = cleaned.split("\n\n")
    assert len(paragraphs) == 1
    assert "Complaining Street" in cleaned
    assert "indd 45" not in cleaned


def test_deduplicate_answer_text_alternating_loop():
    """Verifies that alternating paragraph loops (P1 -> P2 -> P1 -> P2) collapse to only unique paragraphs."""
    p1 = "The Grumble Family is a family that lives on Complaining Street in the city of Never-Are-Satisfied. They are known for their constant complaints."
    p2 = "The poet gives a vivid picture of neighbourhood scenes and encourages readers on how they should mend their ways."
    alternating_text = f"{p1} 45-10th English_Unit_2.indd 45 28-11-2022 18:19:39\n\n{p2} 45-10th English_Unit_2.indd 46 28-11-2022 18:19:39\n\n{p1} 45-10th English_Unit_2.indd 47 28-11-2022 18:19:39\n\n{p2} 45-10th English_Unit_2.indd 48 28-11-2022 18:19:39\n\n{p1}"
    
    cleaned = deduplicate_answer_text(alternating_text)
    paragraphs = cleaned.split("\n\n")
    assert len(paragraphs) == 2
    assert "Complaining Street" in paragraphs[0]
    assert "vivid picture" in paragraphs[1]
    assert "indd" not in cleaned


def test_grumble_family_prompt_grounding_non_repetition():
    """Verifies that the generated prompt includes anti-repetition instructions and single synthesis rule."""
    from ragger_engine.generation.service import GenerationService
    gen_svc = GenerationService(workspace_dir=Path("storage"), retrieval_service=MagicMock())

    c = _make_chunk("chk_grumble_01", "The Grumble Family lives on Complaining Street. 45-10th English_Unit_2.indd 45 28-11-2022 18:19:39", page=51)
    prompt = gen_svc._build_grounded_prompt(
        query="The Grumble Family",
        retrieved_chunks=[c],
        history=[],
    )
    assert "SYNTHESIS & REPETITION RULE" in prompt
    assert "Never repeat the same passage" in prompt
    assert "</grounding_context>" in prompt
    assert "45-10th English_Unit_2.indd" not in prompt
