"""Ingestion subsystem package."""

from ragger_engine.ingestion.detector import FileDetector
from ragger_engine.ingestion.models import (
    AnalysisSample,
    DatasetModel,
    DetectedFileType,
    DocumentBlock,
    DocumentModel,
    DocumentTable,
    IngestionMetrics,
    IngestionResult,
    SourceLocation,
    SourceRecord,
    TableSheet,
)
from ragger_engine.ingestion.normalizer import StructuralNormalizer
from ragger_engine.ingestion.registry import SourceRegistry
from ragger_engine.ingestion.sampler import DeterministicSampleGenerator
from ragger_engine.ingestion.service import IngestionService

__all__ = [
    "FileDetector",
    "SourceRegistry",
    "StructuralNormalizer",
    "DeterministicSampleGenerator",
    "IngestionService",
    "DetectedFileType",
    "SourceRecord",
    "SourceLocation",
    "DocumentBlock",
    "DocumentTable",
    "DocumentModel",
    "DatasetModel",
    "TableSheet",
    "AnalysisSample",
    "IngestionMetrics",
    "IngestionResult",
]
