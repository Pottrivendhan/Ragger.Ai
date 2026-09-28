"""Ingestion Service orchestrating file intake, detection, registration, parsing, and sampling."""

import time
from pathlib import Path
from typing import Optional, Union

from ragger_engine.ingestion.detector import FileDetector
from ragger_engine.ingestion.exceptions import (
    ExtractionLimitationError,
    ParserError,
    UnsupportedFormatError,
)
from ragger_engine.ingestion.models import (
    AnalysisSample,
    DatasetModel,
    DetectedFileType,
    DocumentModel,
    IngestionMetrics,
    IngestionResult,
    SourceRecord,
)
from ragger_engine.ingestion.normalizer import StructuralNormalizer
from ragger_engine.ingestion.parsers import get_parser_for_format
from ragger_engine.ingestion.registry import SourceRegistry
from ragger_engine.ingestion.sampler import DeterministicSampleGenerator
from ragger_engine.ingestion.security import FileQuotaValidator, PathSecurityValidator


class IngestionService:
    """High-level service orchestrating the deterministic file ingestion pipeline."""

    def __init__(
        self,
        registry: Optional[SourceRegistry] = None,
        storage_dir: Optional[Union[str, Path]] = None,
    ):
        if registry:
            self.registry = registry
        elif storage_dir:
            self.registry = SourceRegistry(storage_dir=storage_dir)
        else:
            self.registry = SourceRegistry()
        self._normalized_models: Dict[str, Union[DocumentModel, DatasetModel]] = {}
        self._samples: Dict[str, AnalysisSample] = {}
        self._file_paths: Dict[str, Path] = {}

    def detect_only(self, file_path: Union[str, Path]) -> DetectedFileType:
        """Runs multi-signal format detection on a file."""
        safe_path = PathSecurityValidator.validate_safe_path(file_path)
        FileQuotaValidator.validate_size(safe_path)
        return FileDetector.detect_file(safe_path)

    def parse_only(self, file_path: Union[str, Path], source_id: Optional[str] = None) -> Union[DocumentModel, DatasetModel]:
        """Detects, registers, parses, and normalizes a file without returning full sample."""
        safe_path = PathSecurityValidator.validate_safe_path(file_path)
        FileQuotaValidator.validate_size(safe_path)

        detected = FileDetector.detect_file(safe_path)
        if detected.format in ("unknown", "empty"):
            raise UnsupportedFormatError(
                f"Cannot parse file of format '{detected.format}': {', '.join(detected.warnings)}",
                detected_format=detected.format,
            )

        source_record = self.registry.register_file(safe_path, detected, custom_id=source_id)
        parser = get_parser_for_format(detected.format)
        raw_model = parser.parse(safe_path, source_record)
        normalized = StructuralNormalizer.normalize(raw_model)
        self.registry.update_status(source_record.source_id, "parsed")
        return normalized

    def ingest(self, file_path: Union[str, Path], custom_source_id: Optional[str] = None) -> IngestionResult:
        """Executes the complete ingestion pipeline:

        Intake -> Detect -> Register -> Route -> Parse -> Normalize -> Sample.
        """
        start_time = time.perf_counter()
        safe_path = PathSecurityValidator.validate_safe_path(file_path)
        file_size = FileQuotaValidator.validate_size(safe_path)

        # 1. Multi-signal detection
        detected = FileDetector.detect_file(safe_path)
        if detected.format in ("unknown", "empty"):
            raise UnsupportedFormatError(
                f"File format '{detected.format}' cannot be ingested. {', '.join(detected.warnings)}",
                detected_format=detected.format,
            )

        # 2. Source registration with raw SHA-256 computation
        source_record = self.registry.register_file(safe_path, detected, custom_id=custom_source_id)

        # 3. Format-specific parsing
        parser = get_parser_for_format(detected.format)
        try:
            raw_model = parser.parse(safe_path, source_record)
        except ExtractionLimitationError as ele:
            self.registry.update_status(source_record.source_id, "failed", warnings=[str(ele)])
            raise
        except Exception as e:
            self.registry.update_status(source_record.source_id, "failed", warnings=[str(e)])
            if not isinstance(e, ParserError):
                raise ParserError(f"Unexpected parser failure: {e}", parser_name=type(parser).__name__)
            raise

        # 4. Structural normalization
        normalized_model = StructuralNormalizer.normalize(raw_model)

        # 5. Deterministic sample generation
        sample = DeterministicSampleGenerator.generate(normalized_model)

        # 6. Mark status as parsed in registry
        self.registry.update_status(source_record.source_id, "parsed", warnings=normalized_model.warnings)

        duration_ms = (time.perf_counter() - start_time) * 1000.0

        # Compute metrics
        blocks_extracted = normalized_model.total_blocks if isinstance(normalized_model, DocumentModel) else None
        rows_extracted = normalized_model.total_rows_across_sheets if isinstance(normalized_model, DatasetModel) else None

        metrics = IngestionMetrics(
            input_size_bytes=file_size,
            duration_ms=round(duration_ms, 2),
            parser_used=type(parser).__name__,
            blocks_extracted=blocks_extracted,
            rows_extracted=rows_extracted,
        )

        self._normalized_models[source_record.source_id] = normalized_model
        self._samples[source_record.source_id] = sample
        self._file_paths[source_record.source_id] = safe_path

        model_type = "document" if isinstance(normalized_model, DocumentModel) else "dataset"

        return IngestionResult(
            source=source_record,
            detected_type=detected,
            model_type=model_type,
            normalized_model=normalized_model,
            sample=sample,
            metrics=metrics,
            warnings=normalized_model.warnings + detected.warnings,
        )

    def get_normalized_model(self, source_id: str) -> Optional[Union[DocumentModel, DatasetModel]]:
        """Retrieves cached normalized model for an ingested source."""
        return self._normalized_models.get(source_id)

    def get_sample(self, source_id: str) -> Optional[AnalysisSample]:
        """Retrieves cached sample for an ingested source."""
        return self._samples.get(source_id)
