"""
Deterministic Synthetic Probe Generator for Phase 8 Quality Evaluation.
Generates stratified in-domain probes from active build chunks and pairs them with
standardized out-of-domain probes. Fully reproducible with sampling_seed=42.
"""

from collections import defaultdict
import random
import re
from typing import List

from ragger_engine.builder.models import Chunk
from .models import ProbeQueryItem, ProbeType


OOD_PROBES = [
    "What is the average surface temperature of Venus in winter?",
    "Explain the recipe for authentic Neapolitan pizza dough.",
    "What are the rules of curling in the Winter Olympic Games?",
    "Who won the 1982 FIFA World Cup final and what was the score?",
    "How do photosynthesis and cellular respiration interact in deep sea hydrothermal vents?",
    "What is the history and development of origami paper folding in Japan?",
]


def _extract_declarative_fact(text: str) -> str:
    """Extracts a clean, declarative sentence or clause from chunk text."""
    # Split text into candidate sentences
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    candidates = []
    for s in sentences:
        s_clean = re.sub(r"\s+", " ", s).strip()
        # declarative sentence of moderate length, not a question or heading fragment
        if 30 <= len(s_clean) <= 180 and not s_clean.endswith("?") and not s_clean.startswith("#"):
            candidates.append(s_clean)

    if candidates:
        return candidates[0]

    # Fallback to first non-empty line or substring
    lines = [line.strip() for line in text.splitlines() if len(line.strip()) >= 20]
    if lines:
        return lines[0][:140].strip()

    return text[:100].strip()


def generate_evaluation_probes(
    chunks: List[Chunk],
    sample_size: int = 10,
    sampling_seed: int = 42,
) -> List[ProbeQueryItem]:
    """
    Deterministically generates evaluation probes using stratified sampling across build sources.
    - sample_size: Total number of probes (in-domain + out-of-domain).
    - sampling_seed: Random seed for reproducible probe selection.
    """
    if not chunks:
        return []

    sample_size = max(3, min(50, sample_size))
    rng = random.Random(sampling_seed)

    # Determine split: reserve at least 1 or 2 probes for out-of-domain
    if sample_size >= 6:
        n_out = max(1, min(2, sample_size // 5))
    else:
        n_out = 1
    n_in = max(1, sample_size - n_out)

    # 1. Stratify chunks by source_id
    chunks_by_source = defaultdict(list)
    for c in chunks:
        chunks_by_source[c.source_id].append(c)

    # Sort sources and chunks within sources for determinism
    sorted_sources = sorted(chunks_by_source.keys())
    for s_id in sorted_sources:
        chunks_by_source[s_id].sort(key=lambda x: (x.metadata.chunk_index, x.chunk_id))

    # 2. Stratified round-robin selection of in-domain chunks
    selected_chunks: List[Chunk] = []
    source_chunk_ptrs = {s_id: 0 for s_id in sorted_sources}

    # Derive reproducible starting offsets
    source_order = list(sorted_sources)
    rng.shuffle(source_order)

    round_idx = 0
    while len(selected_chunks) < n_in and round_idx < len(chunks):
        source_id = source_order[round_idx % len(source_order)]
        chunks_in_src = chunks_by_source[source_id]
        ptr = source_chunk_ptrs[source_id]

        if ptr < len(chunks_in_src):
            selected_chunks.append(chunks_in_src[ptr])
            source_chunk_ptrs[source_id] = ptr + 1

        round_idx += 1

        # Break if all chunks exhausted
        if all(source_chunk_ptrs[s] >= len(chunks_by_source[s]) for s in sorted_sources):
            break

    # 3. Formulate in-domain probe queries
    probes: List[ProbeQueryItem] = []
    for idx, chunk in enumerate(selected_chunks):
        fact = _extract_declarative_fact(chunk.text)
        src_name = chunk.metadata.source_name
        heading_path = chunk.metadata.heading_path

        if heading_path:
            heading = heading_path[-1]
            query = f"What does the section '{heading}' state regarding: {fact}?"
        else:
            query = f"According to {src_name}, what is reported about: {fact}?"

        probes.append(
            ProbeQueryItem(
                probe_id=f"probe_in_{idx + 1:02d}",
                probe_type=ProbeType.IN_DOMAIN,
                query=query,
                origin_chunk_id=chunk.chunk_id,
                origin_source_id=chunk.source_id,
                origin_source_name=src_name,
                expected_facts=fact,
                expected_disclaimer=False,
            )
        )

    # 4. Formulate standardized out-of-domain probe queries
    for ood_idx in range(n_out):
        ood_query = OOD_PROBES[ood_idx % len(OOD_PROBES)]
        probes.append(
            ProbeQueryItem(
                probe_id=f"probe_out_{ood_idx + 1:02d}",
                probe_type=ProbeType.OUT_OF_DOMAIN,
                query=ood_query,
                origin_chunk_id=None,
                origin_source_id=None,
                origin_source_name=None,
                expected_facts=None,
                expected_disclaimer=True,
            )
        )

    return probes
