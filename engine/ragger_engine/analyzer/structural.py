"""Authoritative structural extractor deriving verified facts strictly from Phase 2 models."""

from typing import Union
from ragger_engine.analyzer.models import StructuralFacts
from ragger_engine.ingestion.models import DatasetModel, DocumentModel, IngestionResult, SourceRecord


class StructuralFactExtractor:
    """Extracts authoritative structural facts from Phase 2 ingestion output.
    
    The LLM is NOT permitted to measure these facts, preventing hallucinations.
    """

    @staticmethod
    def extract_facts(
        source: SourceRecord,
        normalized_model: Union[DocumentModel, DatasetModel, dict],
    ) -> StructuralFacts:
        """Extracts immutable structural facts from normalized model."""
        detected_format = source.detected_format
        file_size = source.file_size_bytes
        warnings = list(source.warnings)

        # Handle Dict input if loaded from JSON storage
        model_type = getattr(normalized_model, "model_type", None)
        if isinstance(normalized_model, dict):
            model_type = normalized_model.get("model_type")

        if model_type == "dataset":
            return StructuralFactExtractor._extract_from_dataset(source, normalized_model)
        else:
            return StructuralFactExtractor._extract_from_document(source, normalized_model)

    @staticmethod
    def _extract_from_dataset(
        source: SourceRecord,
        model: Union[DatasetModel, dict],
    ) -> StructuralFacts:
        sheets = model.sheets if isinstance(model, DatasetModel) else model.get("sheets", [])
        total_sheets = len(sheets)
        total_rows = 0
        total_cols = 0
        has_numerical = False
        words_est = 0

        for sheet in sheets:
            s_rows = sheet.total_rows if isinstance(sheet, object) and hasattr(sheet, "total_rows") else sheet.get("total_rows", 0)
            columns = sheet.columns if isinstance(sheet, object) and hasattr(sheet, "columns") else sheet.get("columns", [])
            total_rows += s_rows
            total_cols += len(columns)

            for col in columns:
                inferred = col.inferred_type if isinstance(col, object) and hasattr(col, "inferred_type") else col.get("inferred_type", "")
                if inferred in ("integer", "float", "number"):
                    has_numerical = True

            # Rough word count from columns and row values
            words_est += len(columns) * 2 + min(s_rows, 500) * len(columns)

        return StructuralFacts(
            source_id=source.source_id,
            detected_format=source.detected_format,
            file_size_bytes=source.file_size_bytes,
            heading_depth=0,
            table_count=total_sheets,
            tabular_ratio=1.0,
            page_count=None,
            slide_count=None,
            total_words=words_est,
            total_rows=total_rows,
            total_columns=total_cols,
            has_numerical_columns=has_numerical,
            has_hierarchical_headings=False,
            extraction_warnings=list(source.warnings),
        )

    @staticmethod
    def _extract_from_document(
        source: SourceRecord,
        model: Union[DocumentModel, dict],
    ) -> StructuralFacts:
        blocks = model.blocks if isinstance(model, DocumentModel) else model.get("blocks", [])
        meta = model.metadata if isinstance(model, DocumentModel) else model.get("metadata", {})
        total_words = model.total_words if isinstance(model, DocumentModel) else model.get("total_words", 0)

        total_blocks = len(blocks)
        table_count = 0
        heading_levels = set()

        for b in blocks:
            b_type = b.type if isinstance(b, object) and hasattr(b, "type") else b.get("type")
            b_level = b.level if isinstance(b, object) and hasattr(b, "level") else b.get("level")

            if b_type == "table":
                table_count += 1
            elif b_type == "heading":
                if b_level is not None:
                    heading_levels.add(b_level)
                else:
                    heading_levels.add(1)

        heading_depth = max(heading_levels) if heading_levels else 0
        heading_depth = min(max(heading_depth, 0), 5)
        has_hierarchical = len(heading_levels) >= 2 or heading_depth >= 2

        # Tabular ratio in mixed document
        tabular_ratio = float(table_count / max(1, total_blocks))
        tabular_ratio = min(max(tabular_ratio, 0.0), 1.0)

        page_count = meta.get("total_pages")
        slide_count = meta.get("total_slides")

        return StructuralFacts(
            source_id=source.source_id,
            detected_format=source.detected_format,
            file_size_bytes=source.file_size_bytes,
            heading_depth=heading_depth,
            table_count=table_count,
            tabular_ratio=tabular_ratio,
            page_count=page_count,
            slide_count=slide_count,
            total_words=total_words,
            total_rows=None,
            total_columns=None,
            has_numerical_columns=False,
            has_hierarchical_headings=has_hierarchical,
            extraction_warnings=list(source.warnings),
        )
