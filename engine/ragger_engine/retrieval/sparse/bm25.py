"""
Zero-dependency, in-memory Okapi BM25 index.
Constructed at active build cache load time directly from chunks.jsonl tokens.
Read-only and deterministic; zero disk mutation of Phase 5 build artifacts.
"""

from collections import Counter
import math
import re
from typing import Dict, List, Tuple

from ragger_engine.builder.models import Chunk


def tokenize(text: str) -> List[str]:
    """Tokenizes text into lowercase alphanumeric tokens."""
    return re.findall(r"\b\w+\b", text.lower())


class InvertedBM25Index:
    """
    In-memory Okapi BM25 lexical index.
    Derives term frequencies and inverted lists across indexed chunks.
    """

    def __init__(self, chunks: List[Chunk], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.num_docs: int = len(chunks)
        self.doc_ids: List[str] = [c.chunk_id for c in chunks]
        self.doc_lengths: Dict[str, int] = {}
        self.doc_term_freqs: Dict[str, Counter] = {}
        self.doc_freqs: Counter = Counter()

        total_tokens = 0
        for chunk in chunks:
            tokens = tokenize(chunk.text)
            doc_len = len(tokens)
            self.doc_lengths[chunk.chunk_id] = doc_len
            total_tokens += doc_len

            counts = Counter(tokens)
            self.doc_term_freqs[chunk.chunk_id] = counts
            for term in counts.keys():
                self.doc_freqs[term] += 1

        self.avg_doc_len: float = (total_tokens / self.num_docs) if self.num_docs > 0 else 1.0

        # Precompute IDF for all terms
        self.idf: Dict[str, float] = {}
        for term, df in self.doc_freqs.items():
            # Standard Robertson-Spärck Jones formulation with + 1.0 for positive IDFs
            self.idf[term] = math.log((self.num_docs - df + 0.5) / (df + 0.5) + 1.0)

    def score_query(self, query: str) -> List[Tuple[str, float]]:
        """
        Scores all indexed chunks against query tokens using Okapi BM25.
        Returns list of (chunk_id, bm25_score) sorted descending by score.
        """
        query_tokens = tokenize(query)
        if not query_tokens or self.num_docs == 0:
            return []

        # Filter to terms present in corpus
        active_terms = [t for t in query_tokens if t in self.idf]
        if not active_terms:
            return []

        scores: List[Tuple[str, float]] = []
        for doc_id in self.doc_ids:
            tf_counter = self.doc_term_freqs[doc_id]
            doc_len = self.doc_lengths[doc_id]
            score = 0.0

            for term in active_terms:
                tf = tf_counter.get(term, 0)
                if tf > 0:
                    idf_term = self.idf[term]
                    numerator = tf * (self.k1 + 1.0)
                    denominator = tf + self.k1 * (1.0 - self.b + self.b * (doc_len / self.avg_doc_len))
                    score += idf_term * (numerator / denominator)

            if score > 0.0:
                scores.append((doc_id, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores
