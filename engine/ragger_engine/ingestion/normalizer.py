"""Structural Normalization layer for DocumentModel and DatasetModel."""

import re
from typing import Union
from ragger_engine.ingestion.models import DatasetModel, DocumentModel


class StructuralNormalizer:
    """Normalizes whitespace and artifacts while strictly preserving structural semantics."""

    @staticmethod
    def normalize_text(text: str) -> str:
        """Standardizes line breaks, eliminates excessive internal whitespace, and trims."""
        if not text:
            return ""
        # Normalize CRLF to LF
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        # Collapse 3+ consecutive newlines to 2
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        # Normalize non-breaking spaces
        normalized = normalized.replace("\xa0", " ")
        # Collapse multiple horizontal spaces/tabs within lines
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in normalized.split("\n")]
        return "\n".join(lines).strip()

    @classmethod
    def normalize_document(cls, doc: DocumentModel) -> DocumentModel:
        """Normalizes blocks and tables in DocumentModel."""
        normalized_blocks = []
        total_words = 0

        for block in doc.blocks:
            clean_content = cls.normalize_text(block.content)
            if not clean_content:
                continue

            words = clean_content.split()
            total_words += len(words)

            block.content = clean_content
            if "word_count" in block.metadata:
                block.metadata["word_count"] = len(words)

            normalized_blocks.append(block)

        doc.blocks = normalized_blocks
        doc.total_blocks = len(normalized_blocks)
        doc.total_words = total_words
        return doc

    @classmethod
    def normalize_dataset(cls, dataset: DatasetModel) -> DatasetModel:
        """Normalizes column names and row string cells in DatasetModel."""
        for sheet in dataset.sheets:
            # Strip column whitespace
            for col in sheet.columns:
                col.name = col.name.strip()

            # Normalize string values in preview rows
            for row in sheet.rows:
                for k, v in row.items():
                    if isinstance(v, str):
                        row[k] = v.strip()

        return dataset

    @classmethod
    def normalize(cls, model: Union[DocumentModel, DatasetModel]) -> Union[DocumentModel, DatasetModel]:
        """Dispatches normalization based on model type."""
        if isinstance(model, DocumentModel):
            return cls.normalize_document(model)
        elif isinstance(model, DatasetModel):
            return cls.normalize_dataset(model)
        return model
