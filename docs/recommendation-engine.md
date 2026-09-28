# Ragger.ai — Analyzer Agent & Recommendation Engine Specification

**Version:** 1.0.0-draft  
**Component:** Intelligence Pipeline (Analyzer Agent + Deterministic Recommendation Engine)  
**Target Environment:** Python Engine / LLM Provider Abstraction

---

## 1. Core Architectural Principle: Observer vs Decision Maker

A common failure in generative AI applications is delegating critical architectural decisions to unconstrained LLM prompts. An LLM instructed to "pick the best RAG architecture and explain why" will produce inconsistent results, hallucinated rationales, and unpredictable configurations.

Ragger.ai enforces an absolute architectural separation:

```text
┌────────────────────────────────────────────────────────┐
│                   ANALYZER AGENT                       │
│                   (The Observer)                       │
│                                                        │
│  - Inspects AnalysisSample & statistical telemetry     │
│  - Identifies content features, density, language      │
│  - Emits STRICT Pydantic-validated JSON observations   │
│  - NEVER decides the final RAG architecture            │
└───────────────────────────┬────────────────────────────┘
                            │ Structured FileAnalysisProfile
┌───────────────────────────▼────────────────────────────┐
│               RECOMMENDATION ENGINE                    │
│               (Deterministic Decider)                  │
│                                                        │
│  - Consumes structured profiles across all files       │
│  - Evaluates registered deterministic rules            │
│  - Computes architecture scores and matching signals   │
│  - Emits PREDEFINED, product-controlled explanations   │
│  - NEVER asks the LLM "Why did you recommend this?"   │
└────────────────────────────────────────────────────────┘
```

---

## 2. Analyzer Agent Specification

### 2.1 Inputs
- `AnalysisSample`: Structured sample from `SampleGenerator` (headings, text slices, table markdown, schema).
- `FileMetadata`: File size, extension, page/row counts, MIME type.
- `StructuralStatistics`: Heading count, table count, null percentage, average paragraph length.

### 2.2 Pydantic Validation Schema (`FileAnalysisProfile`)
The LLM output is validated against strict Pydantic models. Any missing field, invalid enum, or extra text triggers an automated schema repair retry loop (up to 2 retries) before failing gracefully.

```python
class ContentModality(str, Enum):
    NARRATIVE_TEXT = "narrative_text"
    HIERARCHICAL_DOCUMENT = "hierarchical_document"
    TABULAR_DATASET = "tabular_dataset"
    SEMI_STRUCTURED_CODE = "semi_structured_code"
    SLIDE_PRESENTATION = "slide_presentation"
    SCIENTIFIC_RESEARCH = "scientific_research"

class SemanticDensity(str, Enum):
    LOW = "low"          # Conversational, verbose, high redundancy
    MEDIUM = "medium"    # Standard manuals, general documentation
    HIGH = "high"        # Dense academic, legal, or technical documentation

class FileAnalysisProfile(BaseModel):
    source_id: str
    detected_domain: str                  # e.g., "finance", "legal", "engineering", "general"
    primary_modality: ContentModality
    semantic_density: SemanticDensity
    has_hierarchical_headings: bool
    heading_depth_estimate: int          # 0 if flat, 1-5 for deep hierarchies
    has_numerical_aggregations: bool     # True if rows/columns warrant quantitative calculations
    entity_relationship_density: str     # "low", "medium", "high"
    primary_language: str                # ISO code, e.g., "en", "es", "de"
    extraction_quality_score: float      # 0.0 - 1.0 (flags OCR or encoding issues)
    extraction_warnings: List[str] = []
    summary_description: str             # Objective 2-sentence description of contents
```

---

## 3. Cross-Source Knowledge Synthesizer

When a user uploads multiple files, Ragger.ai aggregates individual `FileAnalysisProfile` records into a single **`WorkspaceKnowledgeProfile`**:

- **Homogeneous vs Heterogeneous**: Determines whether sources share identical modalities (e.g., 10 standard PDFs) or mixed modalities (e.g., 4 PDFs + 2 Excel sheets).
- **Modality Distribution**: Calculates percentages of narrative text, hierarchical documents, and tabular data.
- **Cross-Source Entity Overlap**: Detects whether column names or document headings indicate related concepts (e.g., `Employee ID` appearing in both a policy PDF and a payroll CSV).

---

## 4. Deterministic Recommendation Engine (`RecommendationEngine`)

### 4.1 Rule Interface & Evaluation
The Recommendation Engine evaluates a registry of deterministic rules against the `WorkspaceKnowledgeProfile`:

```python
class RuleEvaluationResult(BaseModel):
    rule_id: str
    matched: bool
    confidence_score: float              # 0.0 to 1.0
    detected_signals: List[str]
    target_architecture: str             # e.g., "knowledge_rag"

class RecommendationRule(ABC):
    @property
    @abstractmethod
    def rule_id(self) -> str:
        pass

    @abstractmethod
    def evaluate(self, profile: WorkspaceKnowledgeProfile) -> RuleEvaluationResult:
        pass
```

### 4.2 Standard Rule Catalog:

1. **`RULE_TABULAR_DOMINANT`**:
   - **Condition**: Tabular datasets account for $\ge 70\%$ of uploaded sources.
   - **Target**: `Structured Data RAG`.
   - **Signals**: High column consistency, numerical fields detected, row counts warrant query engine.
2. **`RULE_HIERARCHICAL_LONGFORM`**:
   - **Condition**: Modality is predominantly `hierarchical_document` with `heading_depth_estimate >= 2` and word count $> 5,000$.
   - **Target**: `Knowledge / Hierarchical RAG`.
   - **Signals**: Multi-level section structure, cross-referencing sub-topics, high semantic density.
3. **`RULE_MIXED_MODALITY`**:
   - **Condition**: Workspace contains at least one narrative document ($> 20\%$) and at least one tabular dataset ($> 20\%$).
   - **Target**: `Hybrid RAG`.
   - **Signals**: Coexistence of unstructured prose and structured tabular records.
4. **`RULE_SCIENTIFIC_RESEARCH`**:
   - **Condition**: Modality classified as `scientific_research` with abstract/methodology sections or citation apparatus.
   - **Target**: `Research-Oriented RAG`.
   - **Signals**: Academic formatting, explicit citations, domain-specific terminology requiring hybrid sparse/dense retrieval.
5. **`RULE_DEFAULT_DOCUMENT`**:
   - **Condition**: Flat prose documents, modest length, absence of complex tables or deep hierarchies.
   - **Target**: `Document RAG`.
   - **Signals**: Standard narrative paragraphs, uniform reading order.

---

## 5. Predefined Explanation Copy Catalog

Explanations shown in the UI are **curated product copy**, mapped directly from matched `rule_id`s. They are completely reproducible and audit-safe.

### Example UI Card Definition:
```json
{
  "architecture_id": "knowledge_rag",
  "title": "Hierarchical Knowledge RAG",
  "recommended_badge": true,
  "confidence_level": "High (94%)",
  "signals": [
    "Deep section hierarchy detected (up to 4 levels)",
    "Long-form multi-topic documents (>18,000 words)",
    "Interconnected policy and procedure definitions"
  ],
  "why_recommended": "Your sources contain structured manuals with nested headings and sections. Standard chunking risks fragmenting related policies; Hierarchical RAG preserves parent-child context to prevent out-of-context retrieval.",
  "strengths": [
    "Maintains structural context across parent sections",
    "High precision for specific operational clauses",
    "Precise breadcrumb citation tracking"
  ],
  "tradeoffs": [
    "Slightly higher index build time due to multi-level chunk generation",
    "Requires parent context re-expansion during retrieval"
  ],
  "alternative_options": ["document_rag", "hybrid_rag"]
}
```

---

## 6. User Review & Approval Workflow

```text
[Analysis Complete]
        │
        ▼
[Recommendation Screen] ── Displays Recommended Architecture, Signals & Why
        │
        ├──► [View Analysis Details] (Inspect per-file modality & stats)
        │
        ├──► [Customize Settings] (Change Chunk Size, Embedding Model, Top-K)
        │
        ▼
[User Explicit Action Required]
   ├── [Approve & Build]
   └── [Switch to Alternative Architecture]
        │
        ▼
[Create ApprovedBuildConfig Snapshot] ── Frozen configuration written to disk
        │
        ▼
[Trigger RAG Builder]
```

**Security & Predictability Invariant**: No background process may begin chunking, embedding, or vector indexing until an `ApprovedBuildConfig` object is written and digitally signed by user interaction.
