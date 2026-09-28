"""
Deterministic Evidence Deduplication Subsystem for Phase 6 Retrieval, Phase 16 Multi-RAG, and Phase 7 Grounded Context Assembly.
Enforces multi-level deduplication without destroying provenance:
- Level 1: Exact chunk identity (same rag_id + build_id + chunk_id)
- Level 2: Exact normalized text (same normalized content within source/version)
- Level 3: Near-duplicate text (high token-overlap / similarity due to PDF boundary overlapping or repeat headers/footers)

Guarantees:
- Deterministic canonical selection (preserves highest-scoring / first representative candidate).
- Provenance preservation (rag_id, build_id, source_id, source_name, chunk_id, page_number).
- Cross-RAG isolation: candidates from distinct RAG IDs are NEVER merged.
"""

import hashlib
import re
from typing import List, TypeVar, Optional, Set
from ragger_engine.retrieval.models import RetrievedChunk

T = TypeVar("T")


def normalize_text_for_dedup(text: str) -> str:
    """
    Normalizes text for deterministic exact & near-duplicate comparison:
    - Lowercase
    - Strip page boundary markers (e.g. '--- Page X End ---')
    - Strip PDF footer/header markers (e.g. '45-10th English_Unit_2.indd 45 28-11-2022 18:19:39' or '45 10th English_Unit_2.indd...')
    - Collapse multiple whitespace and normalize punctuation
    """
    if not text:
        return ""
    # Strip page boundary markers
    cleaned = re.sub(r"--- Page \d+ (?:End|Start) ---", " ", text, flags=re.IGNORECASE)
    # Strip PDF indd and date/time footer artifacts (matches '45-10th English_Unit_2.indd ...' or '10th English_Unit_2.indd ...')
    cleaned = re.sub(
        r"(?:\d+[\s\-]*)?(?:\d+(?:st|nd|rd|th)[\s\-]*)?[a-zA-Z0-9_\s\-]+?\.indd[^\n\r]*",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    # Lowercase & collapse whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
    return cleaned


def compute_text_hash(normalized_text: str) -> str:
    """Computes SHA-256 fingerprint of normalized chunk text."""
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


def compute_jaccard_similarity(tokens_a: Set[str], tokens_b: Set[str]) -> float:
    """Computes Jaccard word set similarity between two token sets."""
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    if union == 0:
        return 0.0
    return float(intersection) / float(union)


def deduplicate_retrieved_chunks(
    chunks: List[RetrievedChunk],
    near_duplicate_threshold: float = 0.85,
) -> List[RetrievedChunk]:
    """
    Deduplicates a list of RetrievedChunk objects in ranking order.
    
    Levels:
    1. Exact chunk_id: If same chunk_id seen, skip.
    2. Exact normalized text hash: If identical normalized text seen in same source, skip.
    3. Near-duplicate overlap: If two chunks from the same source have Jaccard similarity >= near_duplicate_threshold,
       keep the higher-ranked canonical representative.
    
    Preserves provenance and ordering.
    """
    if not chunks:
        return []

    unique_chunks: List[RetrievedChunk] = []
    seen_chunk_ids: Set[str] = set()
    seen_text_hashes: Set[str] = set()
    accepted_token_sets: List[tuple[str, Set[str]]] = []  # (source_id, token_set)

    for chunk in chunks:
        # Level 1: Exact chunk identity
        if chunk.chunk_id in seen_chunk_ids:
            continue

        norm_text = normalize_text_for_dedup(chunk.text)
        if not norm_text:
            continue

        # Level 2: Exact normalized text hash
        text_hash = compute_text_hash(norm_text)
        src_id = (chunk.provenance.source_id if chunk.provenance else "") or "unknown_src"
        composite_hash = f"{src_id}:{text_hash}"
        if composite_hash in seen_text_hashes:
            continue

        # Level 3: Near-duplicate check against accepted chunks from the same source
        words = set(re.findall(r"\b[a-z0-9_]{3,}\b", norm_text))
        is_near_dup = False
        if len(words) >= 15:  # Only evaluate substantial chunks for near-duplication
            for prev_src, prev_words in accepted_token_sets:
                if prev_src == src_id:
                    similarity = compute_jaccard_similarity(words, prev_words)
                    if similarity >= near_duplicate_threshold:
                        is_near_dup = True
                        break

        if is_near_dup:
            continue

        # Accept chunk
        seen_chunk_ids.add(chunk.chunk_id)
        seen_text_hashes.add(composite_hash)
        accepted_token_sets.append((src_id, words))
        unique_chunks.append(chunk)

    return unique_chunks


def deduplicate_multi_rag_candidates(
    candidates: List["MultiRAGCandidate"],
    near_duplicate_threshold: float = 0.85,
) -> List["MultiRAGCandidate"]:
    """
    Deduplicates MultiRAGCandidate objects across multiple RAGs.
    CRITICAL: Never merges candidates across different RAG IDs to avoid provenance bleeding.
    
    Levels:
    1. Composite key: rag_id:build_id:chunk_id
    2. Exact normalized text hash within same (rag_id, source_id)
    3. Near-duplicate overlap within same (rag_id, source_id)
    """
    if not candidates:
        return []

    unique_candidates: List["MultiRAGCandidate"] = []
    seen_composite_keys: Set[str] = set()
    seen_text_hashes: Set[str] = set()
    accepted_token_sets: List[tuple[str, Set[str]]] = []  # (f"{rag_id}:{source_id}", token_set)

    for cand in candidates:
        # Level 1: Exact composite key
        comp_key = getattr(cand, "composite_key", f"{cand.rag_id}:{cand.build_id}:{cand.chunk_id}")
        if comp_key in seen_composite_keys:
            continue

        norm_text = normalize_text_for_dedup(cand.text)
        if not norm_text:
            continue

        # Level 2: Exact normalized text within same RAG source
        text_hash = compute_text_hash(norm_text)
        rag_src_key = f"{cand.rag_id}:{cand.source_id}"
        composite_hash = f"{rag_src_key}:{text_hash}"
        if composite_hash in seen_text_hashes:
            continue

        # Level 3: Near-duplicate check within same RAG source
        words = set(re.findall(r"\b[a-z0-9_]{3,}\b", norm_text))
        is_near_dup = False
        if len(words) >= 15:
            for prev_key, prev_words in accepted_token_sets:
                if prev_key == rag_src_key:
                    sim = compute_jaccard_similarity(words, prev_words)
                    if sim >= near_duplicate_threshold:
                        is_near_dup = True
                        break

        if is_near_dup:
            continue

        seen_composite_keys.add(comp_key)
        seen_text_hashes.add(composite_hash)
        accepted_token_sets.append((rag_src_key, words))
        unique_candidates.append(cand)

    return unique_candidates


def deduplicate_answer_text(answer: str) -> str:
    """
    Cleans generated answers by collapsing duplicate/near-duplicate paragraphs or sentences
    produced when small LLMs get stuck in a repetitive decoding loop.
    Also strips raw PDF indd layout footers/headers if accidentally echoed.
    """
    if not answer or not answer.strip():
        return answer

    # First, strip all indd layout footers/headers across the entire text
    cleaned_answer = re.sub(
        r"(?:\d+[\s\-]*)?(?:\d+(?:st|nd|rd|th)[\s\-]*)?[a-zA-Z0-9_\s\-]+?\.indd[^\n\r]*",
        "",
        answer,
        flags=re.IGNORECASE,
    )

    # Split by double newline (or single newline with indent/blank line) into paragraphs
    raw_paragraphs = [p.strip() for p in re.split(r"\n\s*\n", cleaned_answer) if p.strip()]
    if not raw_paragraphs:
        return ""

    def _split_into_sentences(text: str) -> List[str]:
        """Splits text into sentences while keeping attached citations like [chk_...] intact."""
        # Finds full sentences ending with punctuation and optional citation brackets [chk_...]
        pattern = r"([^.!?]+(?:[.!?]+(?:\s*\[[a-zA-Z0-9_:\s,\.-]+\])?|$))"
        raw_matches = [m.group(0).strip() for m in re.finditer(pattern, text) if m.group(0).strip()]
        result: List[str] = []
        for item in raw_matches:
            # If item is solely a bracketed citation tag, attach to preceding sentence
            if re.match(r"^\[(?:chk_[a-zA-Z0-9_]+|Source:[^\]]+)\]$", item):
                if result:
                    result[-1] = f"{result[-1]} {item}"
                else:
                    result.append(item)
            else:
                result.append(item)
        return result

    # Helper to deduplicate repeating sentences inside a single paragraph
    def _dedupe_sentences(paragraph: str) -> str:
        sentences = _split_into_sentences(paragraph)
        if len(sentences) <= 1:
            return paragraph

        unique_sents: List[str] = []
        seen_sent_hashes: Set[str] = set()
        accepted_sent_tokens: List[Set[str]] = []

        for s in sentences:
            s_clean = s.strip()
            if not s_clean:
                continue
            norm = normalize_text_for_dedup(s_clean)
            if not norm:
                continue
            h = compute_text_hash(norm)
            if h in seen_sent_hashes:
                continue
            words = set(re.findall(r"\b[a-z0-9_]{3,}\b", norm))
            is_dup = False
            if len(words) >= 4:
                for prev_words in accepted_sent_tokens:
                    if compute_jaccard_similarity(words, prev_words) >= 0.70:
                        is_dup = True
                        break
            if not is_dup:
                seen_sent_hashes.add(h)
                accepted_sent_tokens.append(words)
                unique_sents.append(s_clean)

        return " ".join(unique_sents)

    unique_paras: List[str] = []
    seen_hashes: Set[str] = set()
    accepted_token_sets: List[Set[str]] = []
    global_accepted_sentence_tokens: List[Set[str]] = []

    for p in raw_paragraphs:
        # Check if empty after whitespace strip
        if not p:
            continue

        # If p is solely a bracketed citation tag, attach it to the previous unique paragraph
        if re.match(r"^\[(?:chk_[a-zA-Z0-9_]+|Source:[^\]]+)\]$", p.strip()):
            if unique_paras:
                unique_paras[-1] = f"{unique_paras[-1]} {p.strip()}"
            continue

        p_deduped = _dedupe_sentences(p)
        if not p_deduped:
            continue

        # Also filter out sentences that repeat ideas already stated in earlier paragraphs
        sents = _split_into_sentences(p_deduped)
        filtered_sents: List[str] = []
        for s in sents:
            s_clean = s.strip()
            if not s_clean:
                continue

            norm_s = normalize_text_for_dedup(s_clean)
            words_s = set(re.findall(r"\b[a-z0-9_]{3,}\b", norm_s))
            is_cross_para_repeat = False
            if len(words_s) >= 4:
                for prev_words in global_accepted_sentence_tokens:
                    if compute_jaccard_similarity(words_s, prev_words) >= 0.55:
                        is_cross_para_repeat = True
                        break
            if not is_cross_para_repeat:
                global_accepted_sentence_tokens.append(words_s)
                filtered_sents.append(s_clean)

        if not filtered_sents:
            continue

        p_final = " ".join(filtered_sents).strip()
        # Drop incomplete sentence fragments at the very end (e.g. 'The poem describes how')
        if not re.search(r"[.!?]$", p_final) and len(p_final.split()) < 8:
            continue

        norm = normalize_text_for_dedup(p_final)
        if not norm:
            continue

        h = compute_text_hash(norm)
        if h in seen_hashes:
            continue

        words = set(re.findall(r"\b[a-z0-9_]{3,}\b", norm))
        is_repeat = False

        # Near-duplicate check against ALL previously accepted paragraphs
        if len(words) >= 6:
            for prev_words in accepted_token_sets:
                if compute_jaccard_similarity(words, prev_words) >= 0.55:
                    is_repeat = True
                    break

        if not is_repeat:
            seen_hashes.add(h)
            accepted_token_sets.append(words)
            unique_paras.append(p_final)

    # If the last paragraph ends in an unfinished clause/fragment, trim it to the last complete sentence
    if unique_paras:
        last_para = unique_paras[-1]
        if not re.search(r"[.!?\]]$", last_para.strip()):
            last_period = max(last_para.rfind("."), last_para.rfind("!"), last_para.rfind("?"), last_para.rfind("]"))
            if last_period != -1:
                trimmed = last_para[:last_period + 1].strip()
                if trimmed:
                    unique_paras[-1] = trimmed
                else:
                    unique_paras.pop()
            else:
                unique_paras.pop()

    return "\n\n".join(unique_paras)

