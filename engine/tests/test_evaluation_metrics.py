"""
Unit tests for Phase 8 evaluation metrics and RAG Quality Score calculations.
Verifies pure deterministic formulas, percentile latencies, and dynamic weight normalization.
"""

import pytest
from ragger_engine.evaluation.metrics import (
    aggregate_deterministic_metrics,
    aggregate_judge_metrics,
    calculate_percentiles,
    calculate_rag_quality_score,
)
from ragger_engine.evaluation.models import (
    BuildSnapshot,
    DeterministicMetrics,
    JudgeEvaluatedMetrics,
    ProbeEvaluationResult,
    ProbeType,
)


def test_percentile_latencies():
    values = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
    p50, p95 = calculate_percentiles(values)
    assert p50 == 55.0
    assert p95 > 90.0

    # Empty list edge case
    p50_empty, p95_empty = calculate_percentiles([])
    assert p50_empty == 0.0
    assert p95_empty == 0.0


def test_aggregate_deterministic_metrics():
    snapshot = BuildSnapshot(
        build_id="bld_01",
        manifest_id="mnf_01",
        manifest_hash="hash_01",
        approved_architecture="hybrid_rag",
        source_ids=["src_01", "src_02"],
        source_sha256={"src_01": "h1", "src_02": "h2"},
        chunk_count=10,
        vector_count=10,
    )

    chunk_source_map = {
        "chk_01": "src_01",
        "chk_02": "src_02",
        "chk_03": "src_01",
    }

    probe_results = [
        ProbeEvaluationResult(
            probe_id="p1",
            probe_type=ProbeType.IN_DOMAIN,
            query="q1",
            retrieved_chunk_ids=["chk_01", "chk_02"],
            origin_chunk_rank=1,
            hit_at_1=True,
            hit_at_3=True,
            hit_at_5=True,
            reciprocal_rank=1.0,
            retrieval_latency_ms=12.0,
            verified_citations=2,
            unverified_citations=0,
        ),
        ProbeEvaluationResult(
            probe_id="p2",
            probe_type=ProbeType.IN_DOMAIN,
            query="q2",
            retrieved_chunk_ids=["chk_03", "chk_02"],
            origin_chunk_rank=2,
            hit_at_1=False,
            hit_at_3=True,
            hit_at_5=True,
            reciprocal_rank=0.5,
            retrieval_latency_ms=18.0,
            verified_citations=1,
            unverified_citations=1,
        ),
    ]

    metrics = aggregate_deterministic_metrics(probe_results, snapshot, chunk_source_map)
    assert metrics.hits_at_1 == 0.5
    assert metrics.hits_at_3 == 1.0
    assert metrics.hits_at_5 == 1.0
    assert metrics.mrr == 0.75  # (1.0 + 0.5) / 2
    assert metrics.source_coverage == 1.0  # both src_01 and src_02 retrieved
    assert metrics.citation_precision == 0.75  # 3 verified / 4 total citations


def test_rag_quality_score_all_available():
    det = DeterministicMetrics(
        hits_at_1=1.0,
        hits_at_3=1.0,
        hits_at_5=1.0,
        mrr=1.0,
        source_coverage=1.0,
        citation_precision=1.0,
        retrieval_latency_p50_ms=10.0,
        retrieval_latency_p95_ms=20.0,
    )
    judge = JudgeEvaluatedMetrics(
        faithfulness=1.0,
        claims_total=10,
        claims_supported=10,
        claims_unsupported=0,
        disclaimer_accuracy=1.0,
        generation_latency_p50_ms=100.0,
        generation_latency_p95_ms=200.0,
    )

    score, weights = calculate_rag_quality_score(det, judge)
    assert score == 100.0
    assert weights["retrieval"] == 0.35
    assert weights["faithfulness"] == 0.35
    assert weights["citation"] == 0.15
    assert weights["disclaimer"] == 0.15


def test_rag_quality_score_dynamic_normalization_missing_citation():
    """
    Contract test: When citation precision is null, effective weights must be:
    retrieval = 0.35 / 0.85
    faithfulness = 0.35 / 0.85
    disclaimer = 0.15 / 0.85
    citation = 0.0
    No zero substitution.
    """
    det = DeterministicMetrics(
        hits_at_1=1.0,
        hits_at_3=1.0,
        hits_at_5=1.0,
        mrr=1.0,
        source_coverage=1.0,
        citation_precision=None,  # 0 citations emitted
        retrieval_latency_p50_ms=10.0,
        retrieval_latency_p95_ms=20.0,
    )
    judge = JudgeEvaluatedMetrics(
        faithfulness=1.0,
        claims_total=5,
        claims_supported=5,
        claims_unsupported=0,
        disclaimer_accuracy=1.0,
        generation_latency_p50_ms=100.0,
        generation_latency_p95_ms=200.0,
    )

    score, weights = calculate_rag_quality_score(det, judge)
    assert score == 100.0
    assert weights["citation"] == 0.0
    assert weights["retrieval"] == round(0.35 / 0.85, 4)
    assert weights["faithfulness"] == round(0.35 / 0.85, 4)
    assert weights["disclaimer"] == round(0.15 / 0.85, 4)
    assert round(weights["retrieval"] + weights["faithfulness"] + weights["disclaimer"], 2) == 1.0


def test_rag_quality_score_dynamic_normalization_missing_faithfulness_and_citation():
    """
    When both faithfulness and citation are null:
    sum = 0.35 + 0.15 = 0.50
    retrieval = 0.35 / 0.50 = 0.70
    disclaimer = 0.15 / 0.50 = 0.30
    """
    det = DeterministicMetrics(
        hits_at_1=1.0,
        hits_at_3=1.0,
        hits_at_5=1.0,
        mrr=1.0,
        source_coverage=1.0,
        citation_precision=None,
        retrieval_latency_p50_ms=10.0,
        retrieval_latency_p95_ms=20.0,
    )
    judge = JudgeEvaluatedMetrics(
        faithfulness=None,  # 0 claims
        claims_total=0,
        claims_supported=0,
        claims_unsupported=0,
        disclaimer_accuracy=1.0,
        generation_latency_p50_ms=100.0,
        generation_latency_p95_ms=200.0,
    )

    score, weights = calculate_rag_quality_score(det, judge)
    assert score == 100.0
    assert weights["citation"] == 0.0
    assert weights["faithfulness"] == 0.0
    assert weights["retrieval"] == 0.70
    assert weights["disclaimer"] == 0.30
