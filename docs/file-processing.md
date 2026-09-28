# Ragger.ai — File Ingestion, Parsing & Normalization Specification

**Version:** 1.0.0-draft  
**Component:** Ingestion, Parsers, Normalization & Sample Generation  
**Target Environment:** Local Python Engine

---

## 1. Ingestion Pipeline Architecture

```text
RAW FILE INPUT
     │
     ▼
[FileDetector] ──────── 1. Extension Verification
     │                  2. MIME Type Sniffing
     │                  3. Magic Bytes / Header Signature Inspection
     ▼
[Source Registry] ──── Computes SHA-256 Checksum, Detects Duplicates, Assigns UUID
     │
     ▼
[Parser Router] ────── Dispatches to format-specific Parser
     │
     ▼
[Format Parser] ────── Extracts raw elements, structure, and metadata
     │
     ▼
[Normalizer] ───────── Transforms to DocumentModel OR DatasetModel
     │
     ▼
[Sample Generator] ─── Deterministically extracts representative AnalysisSample
```

---

## 2. File Detection Subsystem (`FileDetector`)

Never rely solely on file extensions provided by the operating system or user uploads. Ragger.ai implements a three-layer detection mechanism:

```python
class DetectionResult:
    detected_format: str          # e.g., "pdf", "docx", "csv"
    mime_type: str                # e.g., "application/pdf"
    is_valid: bool
    confidence: float             # 0.0 - 1.0
    error_detail: Optional[str]

class FileDetector:
    @staticmethod
    def detect(file_path: str) -> DetectionResult:
        # Step 1: Inspect file extension
        # Step 2: Read first 2048 bytes (Magic Byte / Signature Inspection)
        # Step 3: Validate encoding and archive integrity
        ...
```

### Signature / Magic Byte Registry:
| Format | Header / Magic Bytes Signature | Secondary Check |
| :--- | :--- | :--- |
| **PDF** | `%PDF-` (`25 50 44 46 2D`) | Verify `%%EOF` marker in trailing 1024 bytes |
| **DOCX** | `PK\x03\x04` (`50 4B 03 04`) | Inspect ZIP manifest for `[Content_Types].xml` and `word/document.xml` |
| **DOC** | `\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1` (Compound File Binary) | Microsoft Word Document signature |
| **PPTX** | `PK\x03\x04` | Inspect ZIP manifest for `ppt/presentation.xml` |
| **XLSX** | `PK\x03\x04` | Inspect ZIP manifest for `xl/workbook.xml` |
| **XLS** | `\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1` | Microsoft Excel Binary signature |
| **EPUB** | `PK\x03\x04` | Verify uncompressed `mimetype` file containing `application/epub+zip` |
| **CSV / TSV**| Plain text with uniform delimiter counts | Python `csv.Sniffer` dialect detection across first 100 lines |
| **JSON** | First non-whitespace byte is `{` or `[` | Streaming `ijson` or standard JSON parse check |
| **XML** | Starts with `<?xml` or root tag `<...>` | Fast XML syntax validator (preventing XXE) |
| **HTML** | Starts with `<!DOCTYPE html` or `<html>` | Trafilatura / HTML5 parser detection |
| **TXT / MD** | Plain text; no binary null bytes (`\x00`) | Encoding detection via `charset-normalizer` |

---

## 3. Format-Specific Parsers

Every parser implements the base `Parser` interface and produces structured components:

```python
class Parser(ABC):
    @abstractmethod
    def parse(self, file_path: str, source_id: str) -> Union[DocumentModel, DatasetModel]:
        """Parses a local file into a normalized internal data model."""
        pass
```

### Specific Parser Implementations:
1. **`PDFParser`**:
   - Engine: `pdfplumber` / `pypdf` with fallback.
   - Extracts page text, fonts, character coordinates, and table bounding boxes.
   - Extracts page-level metadata (dimensions, page numbers, extracted images count).
2. **`DOCXParser`**:
   - Engine: `python-docx`.
   - Traverses document body elements, preserving heading hierarchy (`Heading 1`, `Heading 2`, etc.), paragraphs, bullet lists, and native XML tables.
3. **`DOCParser`**:
   - Engine: `antiword` / headless LibreOffice conversion or pure Python CFBF parser.
4. **`PPTXParser`**:
   - Engine: `python-pptx`.
   - Iterates through slides, slide notes, shape text frames, and slide titles. Preserves slide sequence and speaker context.
5. **`CSVParser` / `TSVParser`**:
   - Engine: `polars` / `pandas`.
   - Automatically detects delimiter, header row, physical types (integer, float, datetime, string), and null representations (`NA`, `N/A`, `null`, empty string).
6. **`XLSXParser` / `XLSParser`**:
   - Engine: `openpyxl` / `xlrd`.
   - Discovers all worksheets. For each sheet, determines data bounds, header rows, merged cells, and formats into tabular structures.
7. **`JSONParser`**:
   - Determines layout: Array of uniform objects (converted to `DatasetModel`) vs deeply nested hierarchical object (converted to `DocumentModel` via flattened key paths).
8. **`XMLParser`**:
   - Engine: `defusedxml` (strictly configured to block XML entity expansion and external DTDs).
   - Maps tag hierarchies into nested sections.
9. **`HTMLParser`**:
   - Engine: `trafilatura` / `beautifulsoup4`.
   - Strips navigational boilerplate, scripts, CSS, and footers. Extracts clean main content, retaining headings and tables.
10. **`EPUBParser`**:
    - Engine: `ebooklib`.
    - Parses spine and TOC manifest, extracting clean chapter text in publication sequence.
11. **`TXTParser` / `MarkdownParser`**:
    - Character set normalization to UTF-8.
    - Markdown parser extracts AST heading blocks, code fences, and lists.

---

## 4. Internal Normalized Data Models

Ragger.ai maintains strict typed models (Pydantic v2) to decouple parsing from chunking and indexing:

### 4.1 Document Model (`DocumentModel`)
Used for prose, manuals, publications, presentations, and hierarchical content.

```python
class TableCell(BaseModel):
    text: str
    is_header: bool = False
    row_span: int = 1
    col_span: int = 1

class DocumentTable(BaseModel):
    caption: Optional[str] = None
    headers: List[str]
    rows: List[List[str]]

class DocumentParagraph(BaseModel):
    text: str
    page_number: Optional[int] = None
    char_offset: int
    is_list_item: bool = False

class DocumentSection(BaseModel):
    section_id: str
    title: str
    level: int                       # 1 for H1, 2 for H2, etc.
    paragraphs: List[DocumentParagraph] = []
    tables: List[DocumentTable] = []
    subsections: List["DocumentSection"] = []

class DocumentModel(BaseModel):
    source_id: str
    filename: str
    format: str
    total_pages: Optional[int] = None
    total_words: int
    metadata: Dict[str, Any]
    sections: List[DocumentSection]
```

### 4.2 Dataset Model (`DatasetModel`)
Used for structured, tabular, and record-oriented data.

```python
class ColumnProfile(BaseModel):
    name: str
    inferred_type: str               # "integer", "float", "string", "datetime", "boolean"
    total_count: int
    null_count: int
    distinct_count: int
    sample_values: List[Any]
    min_value: Optional[Any] = None
    max_value: Optional[Any] = None
    mean_value: Optional[float] = None

class DatasetModel(BaseModel):
    source_id: str
    filename: str
    format: str
    total_rows: int
    total_columns: int
    columns: List[ColumnProfile]
    preview_rows: List[Dict[str, Any]]
    metadata: Dict[str, Any]
```

---

## 5. Representative Sample Generation (`SampleGenerator`)

Sending entire 500-page PDFs or 200,000-row CSVs to an LLM for analysis is slow, expensive, and context-wasteful. Ragger.ai uses **Deterministic Sampling Policies**:

```text
DOCUMENT SAMPLING POLICY (Target: ~4,000 Tokens)
├── Metadata & Table of Contents / Heading Hierarchy
├── Head Sample: First 3 pages or first 5 paragraphs
├── Middle Sample: 2 representative sections from 40%-60% document depth
├── Tail Sample: Concluding section / summary
├── Structural Statistics: Section counts, table counts, word counts
└── Extracted Tables: First 2 parsed tables (formatted as Markdown)

DATASET SAMPLING POLICY (Target: ~3,000 Tokens)
├── Schema Definition: Column names, physical/inferred types
├── Dimension Statistics: Total rows, total columns, file size
├── Head Sample: First 10 rows (formatted as Markdown table)
├── Random Sample: 10 deterministic seeded pseudo-random rows
├── Tail Sample: Last 5 rows
└── Statistical Summary: Null percentages, high-cardinality flags
```

The resulting `AnalysisSample` object is saved to the workspace cache and serves as the single input to the Analyzer Agent.
