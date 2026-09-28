"""Domain models for structural normalization, detection, and sampling."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Detection & Registry Models
# ---------------------------------------------------------------------------

class DetectedFileType(BaseModel):
    """Result emitted by the multi-signal FileDetector."""
    format: str                           # e.g. "pdf", "docx", "xlsx", "csv"
    mime_type: str                        # e.g. "application/pdf"
    confidence: float = 1.0               # 0.0 to 1.0
    detection_method: str                 # "magic_bytes", "container_manifest", "content_sniff", "extension_fallback"
    warnings: List[str] = Field(default_factory=list)


class SourceRecord(BaseModel):
    """Persistent record of an ingested source in the SourceRegistry."""
    source_id: str
    original_filename: str
    detected_format: str
    mime_type: str
    file_size_bytes: int
    sha256_checksum: str                  # Computed strictly over raw input bytes
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = "registered"            # "registered", "parsed", "failed"
    file_path: Optional[str] = None       # Absolute path on local disk
    warnings: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Source Location Tracking (for future citation grounding)
# ---------------------------------------------------------------------------

class SourceLocation(BaseModel):
    """Precise coordinates inside a source document or dataset."""
    page_number: Optional[int] = None     # 1-indexed (PDF, etc.)
    slide_number: Optional[int] = None    # 1-indexed (PPTX)
    sheet_name: Optional[str] = None      # (XLSX, XLS)
    row_index: Optional[int] = None       # 0-indexed row (CSV, XLSX)
    block_index: Optional[int] = None     # 0-indexed structural block
    char_offset: Optional[int] = None     # character position in raw source


# ---------------------------------------------------------------------------
# Document Model (Prose, Slides, Manuals, Articles)
# ---------------------------------------------------------------------------

BlockType = Literal[
    "heading",
    "paragraph",
    "table",
    "list_item",
    "code",
    "quote",
    "page_break",
]


class DocumentBlock(BaseModel):
    """Discrete structural element inside a DocumentModel."""
    block_id: str
    type: BlockType
    content: str
    level: Optional[int] = None           # Heading level (1-6) or list indent level
    location: SourceLocation = Field(default_factory=SourceLocation)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DocumentTable(BaseModel):
    """Table structure preserved in DocumentModel."""
    caption: Optional[str] = None
    headers: List[str] = Field(default_factory=list)
    rows: List[List[str]] = Field(default_factory=list)
    location: SourceLocation = Field(default_factory=SourceLocation)


class DocumentModel(BaseModel):
    """Normalized structural representation for narrative and hierarchical content."""
    model_type: Literal["document"] = "document"
    source_id: str
    title: str
    format: str
    language: str = "en"
    metadata: Dict[str, Any] = Field(default_factory=dict)
    blocks: List[DocumentBlock] = Field(default_factory=list)
    tables: List[DocumentTable] = Field(default_factory=list)
    total_blocks: int = 0
    total_words: int = 0
    warnings: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Dataset Model (Tabular Records, Spreadsheets, Data Matrices)
# ---------------------------------------------------------------------------

class ColumnSchema(BaseModel):
    """Metadata and inferred statistics for a single dataset column."""
    name: str
    inferred_type: str                    # "integer", "float", "string", "datetime", "boolean"
    null_count: int = 0
    distinct_count: int = 0
    sample_values: List[Any] = Field(default_factory=list)
    min_value: Optional[Any] = None
    max_value: Optional[Any] = None
    mean_value: Optional[float] = None


class TableSheet(BaseModel):
    """Individual table or workbook sheet within a DatasetModel."""
    sheet_name: str
    columns: List[ColumnSchema] = Field(default_factory=list)
    rows: List[Dict[str, Any]] = Field(default_factory=list)
    total_rows: int = 0
    total_columns: int = 0
    warnings: List[str] = Field(default_factory=list)


class DatasetModel(BaseModel):
    """Normalized structural representation for structured and tabular content."""
    model_type: Literal["dataset"] = "dataset"
    source_id: str
    title: str
    format: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    sheets: List[TableSheet] = Field(default_factory=list)
    total_sheets: int = 0
    total_rows_across_sheets: int = 0
    warnings: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Sampling & Ingestion Results
# ---------------------------------------------------------------------------

class AnalysisSample(BaseModel):
    """Deterministic, bounded sample prepared for Analyzer Agent."""
    sample_type: Literal["document", "dataset"]
    source_id: str
    token_count_estimate: int
    # Document fields
    heading_outline: List[str] = Field(default_factory=list)
    head_sample: Optional[str] = None
    middle_sample: Optional[str] = None
    tail_sample: Optional[str] = None
    table_samples: List[str] = Field(default_factory=list)
    # Dataset fields
    dataset_schema_summary: List[Dict[str, Any]] = Field(default_factory=list)
    first_rows: List[Dict[str, Any]] = Field(default_factory=list)
    sampled_rows: List[Dict[str, Any]] = Field(default_factory=list)
    last_rows: List[Dict[str, Any]] = Field(default_factory=list)

    @property
    def sample_text(self) -> str:
        parts = []
        if self.heading_outline:
            parts.append("Outline:\n" + "\n".join(self.heading_outline))
        if self.head_sample:
            parts.append("Head:\n" + self.head_sample)
        if self.middle_sample:
            parts.append("Middle:\n" + self.middle_sample)
        if self.tail_sample:
            parts.append("Tail:\n" + self.tail_sample)
        if self.table_samples:
            parts.append("Tables:\n" + "\n".join(self.table_samples))
        return "\n\n".join(parts)

    @property
    def tabular_sample(self) -> Dict[str, Any]:
        return {
            "sheets": self.dataset_schema_summary,
            "first_rows": self.first_rows,
            "sampled_rows": self.sampled_rows,
            "last_rows": self.last_rows,
        }


class IngestionMetrics(BaseModel):
    """Diagnostic processing metrics."""
    input_size_bytes: int
    duration_ms: float
    parser_used: str
    blocks_extracted: Optional[int] = None
    rows_extracted: Optional[int] = None


class IngestionResult(BaseModel):
    """Complete structured result of file intake, parsing, and normalization."""
    source: SourceRecord
    detected_type: DetectedFileType
    model_type: Literal["document", "dataset"]
    normalized_model: Union[DocumentModel, DatasetModel]
    sample: AnalysisSample
    metrics: IngestionMetrics
    warnings: List[str] = Field(default_factory=list)
