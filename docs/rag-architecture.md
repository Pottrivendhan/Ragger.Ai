# Ragger.ai — RAG Architectures & Retrieval Specifications

**Version:** 1.0.0-draft  
**Component:** RAG Architecture Engine  
**Target Environment:** Local-First Desktop / Modular Retrieval Pipelines

---

## 1. The Ragger.ai Architectural Taxonomy

Ragger.ai does not enforce a single "one-size-fits-all" chunk-and-embed pipeline. Real-world knowledge is heterogeneous. Uploading an employee handbook requires fundamentally different retrieval mechanics than querying a 50,000-row sales spreadsheet or an academic research paper.

Ragger.ai defines **6 dedicated Product RAG Architectures**:

```text
                                  INPUT SOURCES
                                        │
                 ┌──────────────────────┼──────────────────────┐
                 ▼                      ▼                      ▼
           Unstructured            Hierarchical            Tabular /
           Narrative Docs          Knowledge Bases         Structured Data
                 │                      │                      │
                 ▼                      ▼                      ▼
          ┌─────────────┐        ┌─────────────┐        ┌─────────────┐
          │1. Document  │        │2. Knowledge │        │3. Structured│
          │     RAG     │        │     RAG     │        │  Data RAG   │
          └─────────────┘        └─────────────┘        └─────────────┘
                 │                      │                      │
                 └──────────────────────┼──────────────────────┘
                                        │
                        ┌───────────────┴───────────────┐
                        ▼                               ▼
                 ┌─────────────┐                 ┌─────────────┐
                 │  4. Hybrid  │                 │ 5. Research │
                 │     RAG     │                 │     RAG     │
                 └─────────────┘                 └─────────────┘
                                        │
                                        ▼ (Advanced / Relational)
                                 ┌─────────────┐
                                 │  6. Graph   │
                                 │Oriented RAG │
                                 └─────────────┘
```

---

## 2. Detailed Architecture Specifications

### 2.1 Architecture 1: Document RAG
- **Target Use Cases**: Standard prose documents, company policies, operational manuals, books, simple reports.
- **Chunking Strategy**: Boundary-aware paragraph chunking with sliding token window (512 tokens with 64 token overlap), sentence-boundary preservation.
- **Metadata Layer**: Source ID, file name, page number, paragraph index, character offset.
- **Retrieval Engine**: Dense vector similarity search (Cosine distance or Inner Product) with Top-K (default K=5).
- **Generation & Citations**: Direct context injection with bracketed citation references `[Source: employee_guide.pdf, Page 12]`.

### 2.2 Architecture 2: Knowledge / Hierarchical RAG
- **Target Use Cases**: Complex corporate documentation, technical software specs, regulatory compliance texts, multi-level manuals.
- **Chunking Strategy**: **Parent-Child Hierarchical Chunking**.
  - Child Chunks (128–256 tokens): Granular content units optimized for precise vector matching.
  - Parent Chunks (512–1024 tokens): Encompassing section or subsection context returned to the LLM upon child match.
- **Metadata Layer**: Heading ancestry tree (e.g., `["Volume 2", "Chapter 4", "Section 4.1.2 - Safety Limits"]`), parent chunk ID, section title, breadcrumb string.
- **Retrieval Engine**: Child vector match $\rightarrow$ Parent expansion $\rightarrow$ Deduplication of shared parent blocks $\rightarrow$ Section-context ranking.
- **Strengths**: Eliminates out-of-context fragment hallucinations; preserves hierarchical document intent.

### 2.3 Architecture 3: Structured Data RAG
- **Target Use Cases**: Tabular datasets (CSV, XLSX, TSV, structured JSON records).
- **Chunking Strategy**: Not raw token chunking. 
  - Schema Profiling: Extract column definitions, data types, distinct values, and statistical bounds.
  - Hybrid Indexing: Row-level record summaries vectorized with schema metadata, combined with an in-memory SQL/DuckDB or Polars engine.
- **Retrieval Engine**: **Dual Query Routing**:
  - Semantic Queries ("Find products relating to gardening"): Vector search over row entity summaries.
  - Quantitative Queries ("What was the total revenue in Q2?"): Text-to-SQL or structured dataframe filter generation against DuckDB, executed with strict read-only constraints.
- **Generation**: Tabular result sets formatted as markdown tables accompanied by analytical commentary.

### 2.4 Architecture 4: Hybrid RAG
- **Target Use Cases**: Multi-file workspaces containing both narrative documents and tabular spreadsheets (e.g., Annual Financial PDF + Detailed Transactions CSV).
- **Retrieval Engine**: **Query Intent Classifier & Reciprocal Rank Fusion (RRF)**:
  1. Incoming user query is analyzed for semantic vs quantitative intent.
  2. Routed simultaneously to the Document/Hierarchical vector retriever and the Structured Data retriever.
  3. Results are fused using RRF:
     $$RRF\_Score(d) = \sum_{r \in R} \frac{1}{k + rank(r, d)}$$
     *(where $k=60$, $r$ is the individual retriever ranking)*.
  4. Top-ranked fused context is passed to the generation model with cross-modal grounding.

### 2.5 Architecture 5: Research-Oriented RAG
- **Target Use Cases**: Academic papers, technical whitepapers, patents, scientific journals.
- **Chunking Strategy**: Section-type aware chunking (Abstract, Introduction, Related Work, Methodology, Experiments, Results, Discussion, References).
- **Metadata Layer**: Author list, publication year, DOI/identifier, section classification, citation references.
- **Retrieval Engine**: **Hybrid Dense + Sparse with Cross-Encoder Reranking**:
  1. Dense vector search (bi-encoder).
  2. Sparse keyword search (BM25 or SPLADE) for precise terminology, author names, and numerical parameters.
  3. Top 30 candidate chunks are reranked using a local cross-encoder model (e.g., `bge-reranker-small` or `FlashRank`).
  4. Top 5 reranked chunks passed to context builder.

### 2.6 Architecture 6: Graph-Oriented RAG (Design Phase)
- **Target Use Cases**: Deep entity networks, investigative files, intelligence analysis, multi-party contracts with dense cross-references.
- **Mechanism**: Entity and relationship extraction from normalized documents, creating a local property graph (NetworkX / SQLite Graph).
- **Retrieval**: Hybrid traversal: vector search locates seed entities, followed by 1-hop or 2-hop graph neighborhood expansion to surface non-obvious entity relationships.

---

## 3. Core Engine Abstractions & Interfaces

All RAG components are defined as strict abstract interfaces in Python to guarantee modularity and zero vendor lock-in.

```python
# ragger_engine/chunking/base.py
from abc import ABC, abstractmethod
from typing import List
from ragger_engine.normalization.models import DocumentModel, Chunk

class ChunkingStrategy(ABC):
    @abstractmethod
    def chunk(self, document: DocumentModel, config: dict) -> List[Chunk]:
        """Splits a normalized document into discrete searchable chunks."""
        pass

# ragger_engine/embeddings/base.py
class EmbeddingProvider(ABC):
    @abstractmethod
    async def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Generates dense vector embeddings for input text strings."""
        pass

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Returns embedding vector dimension (e.g., 384, 768, 1536)."""
        pass

# ragger_engine/storage/base.py
class VectorStore(ABC):
    @abstractmethod
    async def initialize(self, path: str, dimension: int):
        pass

    @abstractmethod
    async def upsert_chunks(self, chunks: List[Chunk], embeddings: List[List[float]]):
        pass

    @abstractmethod
    async def search(self, query_vector: List[float], top_k: int, filters: dict = None) -> List[RetrievalResult]:
        pass

# ragger_engine/retrieval/base.py
class Retriever(ABC):
    @abstractmethod
    async def retrieve(self, query: str, top_k: int) -> List[RetrievalResult]:
        pass

# ragger_engine/generation/base.py
class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str, system_prompt: str, temperature: float = 0.2) -> str:
        pass

    @abstractmethod
    async def generate_stream(self, prompt: str, system_prompt: str):
        pass
```

---

## 4. Grounded Context Construction & Citations

To prevent hallucinations, Ragger.ai enforces strict **grounded context assembly**:

```text
SYSTEM PROMPT:
You are an expert technical assistant answering questions based strictly on the provided context.
If the provided context does not contain sufficient evidence to answer the question, state clearly:
"Based on the provided sources, there is insufficient information to answer this question."
Do not speculate or extrapolate beyond the explicit facts in the context.
Every factual statement must cite its source using the format [Source: <filename>, Section: <sec>, Page: <p>].

CONTEXT:
---
[Source: q3_financials.pdf | Page: 4 | Section: 2.1 Cash Flow]
Operating cash flows for the third quarter were $42.1M, representing an 8% year-over-year increase.
---
[Source: annual_strategy.docx | Section: Growth Targets]
Target operating margins are projected to stabilize between 22% and 24% by year-end.
---

QUESTION:
{user_query}
```

---

## 5. Automated RAG Quality Evaluation

After build completion, the workspace executes an **Automated Health & Quality Evaluation**:

1. **Synthetic Question Generation**: Using the configured LLM, 5–10 representative factual questions are synthesized from distinct chunk clusters.
2. **Retrieval Verification**:
   - Executes queries against the newly created vector index.
   - Verifies whether the generating chunk appears in the Top-3 retrieval results (Hits@3).
3. **Faithfulness & Grounding Verification**:
   - Generates answers and scores whether claims made in the answer can be directly attributed to the retrieved context.
4. **Health Report Card**:
   - Metric 1: Retrieval Precision / Recall Heuristic.
   - Metric 2: Source Coverage (percentage of sources represented in retrieval).
   - Metric 3: Chunk Density & Distribution Balance.
