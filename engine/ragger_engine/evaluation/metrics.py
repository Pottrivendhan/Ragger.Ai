"""
Deterministic and Judge-Evaluated Metrics Engine for Phase 8 Quality Evaluation.
Implements the frozen RAG Quality Score formula with exact dynamic re-normalization
when Faithfulness or Citation Precision is null (never substituting zero).
"""

from typing import Dict, List, Optional, Tuple
import numpy as np

from .models import (
    BuildSnapshot,
    DeterministicMetrics,
    JudgeEvaluatedMetrics,
    ProbeEvaluationResult,
    ProbeType,
)


def calculate_percentiles(values: List[float]) -> Tuple[float, float]:
    """Calculates p50 (median) and p95 latency percentiles in milliseconds."""
    if not values:
        return 0.0, 0.0
    arr = np.array(values, dtype=float)
    p50 = float(np.percentile(arr, 50))
    p95 = float(np.percentile(arr, 95))
    return round(p50, 2), round(p95, 2)


def aggregate_deterministic_metrics(
    probe_results: List[ProbeEvaluationResult],
    snapshot: BuildSnapshot,
    chunk_source_map: Dict[str, str],
) -> DeterministicMetrics:
    """
    Computes deterministic retrieval and citation metrics across evaluated probes.
    """
    in_probes = [p for p in probe_results if p.probe_type == ProbeType.IN_DOMAIN]
    n_in = len(in_probes)

    if n_in == 0:
        hits_at_1 = 0.0
        hits_at_3 = 0.0
        hits_at_5 = 0.0
        mrr = 0.0
        source_coverage = 1.0 if not snapshot.source_ids else 0.0
    else:
        hits_at_1 = sum(1.0 for p in in_probes if p.hit_at_1) / n_in
        hits_at_3 = sum(1.0 for p in in_probes if p.hit_at_3) / n_in
        hits_at_5 = sum(1.0 for p in in_probes if p.hit_at_5) / n_in
        mrr = sum(p.reciprocal_rank for p in in_probes) / n_in

        # Source coverage tied strictly to build snapshot
        retrieved_sources = set()
        for p in in_probes:
            for cid in p.retrieved_chunk_ids:
                s_id = chunk_source_map.get(cid)
                if s_id:
                    retrieved_sources.add(s_id)

        denom = max(1, len(snapshot.source_ids))
        valid_covered = retrieved_sources.intersection(set(snapshot.source_ids))
        source_coverage = min(1.0, max(0.0, len(valid_covered) / denom))

    # Citation precision across all probes
    total_verified = sum(p.verified_citations for p in probe_results)
    total_unverified = sum(p.unverified_citations for p in probe_results)
    total_citations = total_verified + total_unverified

    if total_citations == 0:
        citation_precision = None
    else:
        citation_precision = round(total_verified / total_citations, 4)

    # Retrieval latencies
    retrieval_latencies = [p.retrieval_latency_ms for p in probe_results if p.retrieval_latency_ms > 0]
    p50_ret, p95_ret = calculate_percentiles(retrieval_latencies)

    return DeterministicMetrics(
        hits_at_1=round(hits_at_1, 4),
        hits_at_3=round(hits_at_3, 4),
        hits_at_5=round(hits_at_5, 4),
        mrr=round(mrr, 4),
        source_coverage=round(source_coverage, 4),
        citation_precision=citation_precision,
        retrieval_latency_p50_ms=p50_ret,
        retrieval_latency_p95_ms=p95_ret,
    )


def aggregate_judge_metrics(
    probe_results: List[ProbeEvaluationResult],
) -> JudgeEvaluatedMetrics:
    """
    Aggregates claim entailment, disclaimer accuracy, and generation latencies.
    """
    total_claims = sum(p.total_claims for p in probe_results)
    supported_claims = sum(p.supported_claims for p in probe_results)
    unsupported_claims = sum(p.unsupported_claims for p in probe_results)

    if total_claims == 0:
        faithfulness = None
    else:
        faithfulness = round(supported_claims / total_claims, 4)

    # Disclaimer accuracy on out-of-domain probes
    ood_probes = [p for p in probe_results if p.probe_type == ProbeType.OUT_OF_DOMAIN]
    if not ood_probes:
        disclaimer_accuracy = 1.0
    else:
        correct_disclaimers = sum(1.0 for p in ood_probes if p.correct_disclaimer is True)
        disclaimer_accuracy = round(correct_disclaimers / len(ood_probes), 4)

    # Generation latencies
    gen_latencies = [p.generation_latency_ms for p in probe_results if p.generation_latency_ms > 0]
    p50_gen, p95_gen = calculate_percentiles(gen_latencies)

    return JudgeEvaluatedMetrics(
        faithfulness=faithfulness,
        claims_total=total_claims,
        claims_supported=supported_claims,
        claims_unsupported=unsupported_claims,
        disclaimer_accuracy=disclaimer_accuracy,
        generation_latency_p50_ms=p50_gen,
        generation_latency_p95_ms=p95_gen,
    )


def calculate_rag_quality_score(
    deterministic_metrics: DeterministicMetrics,
    judge_metrics: JudgeEvaluatedMetrics,
) -> Tuple[float, Dict[str, float]]:
    """
    Calculates the frozen Composite RAG Quality Score (0.0 to 100.0) with dynamic weight
    normalization when Faithfulness or Citation Precision is null.

    Base weights:
      retrieval: 0.35
      faithfulness: 0.35
      citation: 0.15
      disclaimer: 0.15

    Retrieval component score:
      S_ret = 0.40 * mrr + 0.40 * hits_at_3 + 0.20 * source_coverage
    """
    # 1. Retrieval component score
    s_ret = (
        0.40 * deterministic_metrics.mrr
        + 0.40 * deterministic_metrics.hits_at_3
        + 0.20 * deterministic_metrics.source_coverage
    )
    s_ret = max(0.0, min(1.0, s_ret))

    s_disc = max(0.0, min(1.0, judge_metrics.disclaimer_accuracy))

    # 2. Build available metrics and base weights
    base_weights = {
        "retrieval": 0.35,
        "faithfulness": 0.35,
        "citation": 0.15,
        "disclaimer": 0.15,
    }

    available_metrics: Dict[str, float] = {
        "retrieval": s_ret,
        "disclaimer": s_disc,
    }

    if judge_metrics.faithfulness is not None:
        available_metrics["faithfulness"] = max(0.0, min(1.0, judge_metrics.faithfulness))

    if deterministic_metrics.citation_precision is not None:
        available_metrics["citation"] = max(0.0, min(1.0, deterministic_metrics.citation_precision))

    # 3. Dynamic normalization over available base weights
    sum_available_base = sum(base_weights[m] for m in available_metrics)

    weights_used: Dict[str, float] = {}
    for metric_name in ["retrieval", "faithfulness", "citation", "disclaimer"]:
        if metric_name in available_metrics:
            normalized_weight = base_weights[metric_name] / sum_available_base
            weights_used[metric_name] = round(normalized_weight, 4)
        else:
            weights_used[metric_name] = 0.0

    # 4. Weighted composite calculation
    composite_raw = sum(
        weights_used[m] * available_metrics[m]
        for m in available_metrics
    )

    quality_score = round(max(0.0, min(100.0, composite_raw * 100.0)), 2)

    return quality_score, weights_used
