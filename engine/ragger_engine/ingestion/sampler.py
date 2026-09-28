"""Deterministic Sample Generator.

Produces bounded, representative AnalysisSample objects for the Analyzer Agent
without invoking any LLMs, strictly adhering to token budgets and determinism.
"""

import random
from typing import List, Union
from ragger_engine.ingestion.models import (
    AnalysisSample,
    DatasetModel,
    DocumentModel,
)

# Approximate token caps
MAX_DOCUMENT_SAMPLE_TOKENS = 4000
MAX_DATASET_SAMPLE_TOKENS = 3000


def estimate_tokens(text: str) -> int:
    """Fast, deterministic word-to-token estimator (~1.3 tokens per whitespace-delimited word)."""
    if not text:
        return 0
    words = len(text.split())
    return int(words * 1.33)


class DeterministicSampleGenerator:
    """Extracts bounded, reproducible samples for future Analyzer Agent inspection."""

    @classmethod
    def generate_document_sample(cls, doc: DocumentModel) -> AnalysisSample:
        # 1. Heading Outline
        headings = [
            f"{'#' * (b.level or 2)} {b.content}"
            for b in doc.blocks
            if b.type == "heading"
        ]

        # 2. Content blocks excluding page breaks
        content_blocks = [b for b in doc.blocks if b.type != "page_break"]
        total_content_blocks = len(content_blocks)

        head_blocks: List[str] = []
        middle_blocks: List[str] = []
        tail_blocks: List[str] = []

        if total_content_blocks <= 6:
            # Small document: head takes all
            head_blocks = [b.content for b in content_blocks]
        else:
            # Head: first 3 content blocks
            head_blocks = [b.content for b in content_blocks[:3]]

            # Middle: 2 blocks centered at 50% depth
            mid_idx = total_content_blocks // 2
            middle_blocks = [b.content for b in content_blocks[max(0, mid_idx - 1): min(total_content_blocks, mid_idx + 1)]]

            # Tail: last 2 content blocks
            tail_blocks = [b.content for b in content_blocks[-2:]]

        # 3. Table samples (first 2 tables)
        table_samples = [b.content for b in doc.blocks if b.type == "table"][:2]

        head_text = "\n\n".join(head_blocks) if head_blocks else None
        middle_text = "\n\n".join(middle_blocks) if middle_blocks else None
        tail_text = "\n\n".join(tail_blocks) if tail_blocks else None

        # Calculate token estimate
        combined_text = "\n".join(
            headings
            + (head_blocks or [])
            + (middle_blocks or [])
            + (tail_blocks or [])
            + table_samples
        )
        token_count = estimate_tokens(combined_text)

        # Enforce budget cap
        if token_count > MAX_DOCUMENT_SAMPLE_TOKENS:
            # Trim middle and tail if necessary
            middle_text = middle_text[:1500] if middle_text else None
            tail_text = tail_text[:1000] if tail_text else None
            token_count = estimate_tokens(
                "\n".join(headings + [head_text or "", middle_text or "", tail_text or ""])
            )

        return AnalysisSample(
            sample_type="document",
            source_id=doc.source_id,
            token_count_estimate=token_count,
            heading_outline=headings[:50],
            head_sample=head_text,
            middle_sample=middle_text,
            tail_sample=tail_text,
            table_samples=table_samples,
        )

    @classmethod
    def generate_dataset_sample(cls, dataset: DatasetModel, deterministic_seed: int = 42) -> AnalysisSample:
        schema_summary = []
        all_first_rows = []
        all_sampled_rows = []
        all_last_rows = []

        for sheet in dataset.sheets:
            sheet_schema = {
                "sheet_name": sheet.sheet_name,
                "total_rows": sheet.total_rows,
                "total_columns": sheet.total_columns,
                "columns": [
                    {
                        "name": col.name,
                        "type": col.inferred_type,
                        "null_count": col.null_count,
                        "distinct_count": col.distinct_count,
                        "sample_values": col.sample_values,
                        "min": col.min_value,
                        "max": col.max_value,
                        "mean": col.mean_value,
                    }
                    for col in sheet.columns
                ],
            }
            schema_summary.append(sheet_schema)

            rows = sheet.rows
            if not rows:
                continue

            # First 10 rows
            first_10 = rows[:10]
            all_first_rows.extend(first_10)

            # Deterministic pseudo-random 10 rows using fixed seed
            rng = random.Random(deterministic_seed)
            if len(rows) > 15:
                # Sample middle slice
                candidate_pool = rows[10:-5] if len(rows) > 20 else rows
                sample_count = min(10, len(candidate_pool))
                sampled_10 = rng.sample(candidate_pool, sample_count)
                all_sampled_rows.extend(sampled_10)

            # Last 5 rows
            last_5 = rows[-5:] if len(rows) > 10 else []
            all_last_rows.extend(last_5)

        # Estimate tokens
        text_repr = str(schema_summary) + str(all_first_rows) + str(all_sampled_rows)
        token_count = estimate_tokens(text_repr)

        return AnalysisSample(
            sample_type="dataset",
            source_id=dataset.source_id,
            token_count_estimate=min(token_count, MAX_DATASET_SAMPLE_TOKENS),
            dataset_schema_summary=schema_summary,
            first_rows=all_first_rows[:15],
            sampled_rows=all_sampled_rows[:15],
            last_rows=all_last_rows[:10],
        )

    @classmethod
    def generate(cls, model: Union[DocumentModel, DatasetModel], deterministic_seed: int = 42) -> AnalysisSample:
        if isinstance(model, DocumentModel):
            return cls.generate_document_sample(model)
        elif isinstance(model, DatasetModel):
            return cls.generate_dataset_sample(model, deterministic_seed=deterministic_seed)
        raise ValueError(f"Unsupported model type for sample generation: {type(model)}")
