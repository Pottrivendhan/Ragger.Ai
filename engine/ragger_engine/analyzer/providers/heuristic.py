"""Deterministic Heuristic Analyzer Provider.

Provides an offline, fast (< 10ms), 100% reproducible, testable baseline
for structural and semantic observation of content without calling any external LLM.
"""

import re
import time
from typing import List, Set, Tuple
from ragger_engine.analyzer.models import (
    ContentModality,
    EntityRelationshipDensity,
    ProviderTelemetry,
    SemanticDensity,
    SemanticObservations,
    StructuralFacts,
)
from ragger_engine.analyzer.providers.base import BaseAnalyzerProvider
from ragger_engine.ingestion.models import AnalysisSample, SourceRecord


# Keyword dictionaries for domain identification
DOMAIN_KEYWORDS = {
    "finance": {"revenue", "profit", "budget", "quarter", "sales", "fiscal", "tax", "financial", "margin", "cost", "attainment"},
    "legal": {"agreement", "party", "parties", "terms", "liability", "dispute", "clause", "jurisdiction", "regulation", "statute"},
    "technology": {"software", "system", "api", "architecture", "database", "module", "microservices", "code", "server", "python"},
    "healthcare": {"patient", "clinical", "medical", "treatment", "diagnosis", "health", "hospital", "physician"},
    "education": {"course", "student", "curriculum", "lecture", "assignment", "university", "faculty"},
}


class DeterministicHeuristicAnalyzer(BaseAnalyzerProvider):
    """Observes samples using deterministic heuristics and structural statistics."""

    @property
    def provider_id(self) -> str:
        return "heuristic_offline"

    async def analyze(
        self,
        source: SourceRecord,
        facts: StructuralFacts,
        sample: AnalysisSample,
    ) -> Tuple[SemanticObservations, ProviderTelemetry]:
        start_time = time.perf_counter()

        # 1. Determine Modalities
        primary_modality, secondary_modalities = self._classify_modalities(facts, sample)

        # 2. Extract text & tokens from sample
        sample_text = self._extract_text_representation(sample)
        tokens = [t.lower() for t in re.findall(r"\b[a-zA-Z]{2,}\b", sample_text)]

        # 3. Detect Domain
        detected_domain = self._detect_domain(tokens, sample)

        # 4. Assess Semantic Density
        semantic_density = self._assess_density(tokens, sample_text)

        # 5. Extract Key Entities / Schema Concepts
        key_entities = self._extract_key_entities(sample, tokens)

        # 6. Assess Entity Relationship Density
        entity_density = self._assess_entity_density(facts, sample, key_entities)

        # 7. Language Detection
        language = self._detect_language(tokens)

        # 8. Extraction Quality Score
        quality_score = 1.0
        if facts.extraction_warnings:
            quality_score = max(0.6, 1.0 - (len(facts.extraction_warnings) * 0.1))

        # 9. Concrete Observed Characteristics
        characteristics = self._build_characteristics(facts, sample, primary_modality, detected_domain)

        # 10. Summary Description (1-2 objective, factual sentences; zero recommendations)
        summary = self._generate_objective_summary(source, facts, primary_modality, detected_domain, key_entities)

        observations = SemanticObservations(
            detected_domain=detected_domain,
            primary_modality=primary_modality,
            secondary_modalities=secondary_modalities,
            semantic_density=semantic_density,
            entity_relationship_density=entity_density,
            key_entities=key_entities[:8],
            primary_language=language,
            extraction_quality_score=round(quality_score, 2),
            observed_characteristics=characteristics,
            summary_description=summary,
        )

        duration = (time.perf_counter() - start_time) * 1000.0

        telemetry = ProviderTelemetry(
            requested_provider="heuristic_offline",
            actual_provider="heuristic_offline",
            fallback_used=False,
            fallback_reason=None,
            model_name="deterministic_heuristic_v1",
            duration_ms=round(duration, 2),
        )

        return observations, telemetry

    def _classify_modalities(
        self, facts: StructuralFacts, sample: AnalysisSample
    ) -> Tuple[ContentModality, List[ContentModality]]:
        secondaries: List[ContentModality] = []

        if facts.tabular_ratio >= 0.7 or sample.sample_type == "dataset":
            primary = ContentModality.TABULAR_DATASET
        elif facts.detected_format == "pptx" or (facts.slide_count and facts.slide_count > 0):
            primary = ContentModality.SLIDE_PRESENTATION
        elif facts.has_hierarchical_headings or facts.heading_depth >= 2:
            primary = ContentModality.HIERARCHICAL_DOCUMENT
            if facts.table_count > 0:
                secondaries.append(ContentModality.TABULAR_DATASET)
        elif facts.detected_format in ("json", "xml") and facts.tabular_ratio < 0.7:
            primary = ContentModality.SEMI_STRUCTURED_CODE
        else:
            # Check for academic markers
            sample_text = (sample.sample_text or "").lower()
            if any(k in sample_text for k in ("abstract", "methodology", "references", "doi:", "bibliography")):
                primary = ContentModality.SCIENTIFIC_RESEARCH
            else:
                primary = ContentModality.NARRATIVE_TEXT

            if facts.table_count > 0:
                secondaries.append(ContentModality.TABULAR_DATASET)

        return primary, secondaries

    def _extract_text_representation(self, sample: AnalysisSample) -> str:
        if sample.sample_text:
            return sample.sample_text
        if sample.tabular_sample and sample.tabular_sample.get("sheets"):
            text_parts = []
            for sheet in sample.tabular_sample["sheets"]:
                text_parts.append(sheet.get("sheet_name", ""))
                for col in sheet.get("columns", []):
                    text_parts.append(col.get("name", ""))
                for rec in sheet.get("sample_records", []):
                    text_parts.extend(str(v) for v in rec.values())
            return " ".join(text_parts)
        return ""

    def _detect_domain(self, tokens: List[str], sample: AnalysisSample) -> str:
        token_set = set(tokens)
        domain_scores = {}
        for domain, kws in DOMAIN_KEYWORDS.items():
            overlap = len(token_set.intersection(kws))
            if overlap > 0:
                domain_scores[domain] = overlap

        if domain_scores:
            return max(domain_scores.items(), key=lambda x: x[1])[0]
        return "general"

    def _assess_density(self, tokens: List[str], text: str) -> SemanticDensity:
        if not tokens:
            return SemanticDensity.MEDIUM
        unique_ratio = len(set(tokens)) / len(tokens)
        avg_word_len = sum(len(t) for t in tokens) / len(tokens)

        if unique_ratio > 0.65 or avg_word_len > 6.5:
            return SemanticDensity.HIGH
        elif unique_ratio < 0.35:
            return SemanticDensity.LOW
        return SemanticDensity.MEDIUM

    def _extract_key_entities(self, sample: AnalysisSample, tokens: List[str]) -> List[str]:
        entities: List[str] = []
        if sample.tabular_sample and sample.tabular_sample.get("sheets"):
            for sheet in sample.tabular_sample["sheets"]:
                entities.append(sheet.get("sheet_name", "Sheet"))
                for col in sheet.get("columns", []):
                    c_name = col.get("name")
                    if c_name and c_name not in entities:
                        entities.append(c_name)
        elif sample.sample_text:
            # Extract capitalized potential entity names
            found = re.findall(r"\b[A-Z][a-zA-Z0-9]{2,}\b", sample.sample_text)
            for word in found:
                if word.lower() not in ("the", "this", "and", "for", "with", "from") and word not in entities:
                    entities.append(word)

        return entities[:10]

    def _assess_entity_density(
        self, facts: StructuralFacts, sample: AnalysisSample, entities: List[str]
    ) -> EntityRelationshipDensity:
        if facts.tabular_ratio >= 0.7:
            if facts.has_numerical_columns and len(entities) >= 4:
                return EntityRelationshipDensity.HIGH
            return EntityRelationshipDensity.MEDIUM
        elif facts.has_hierarchical_headings and len(entities) >= 5:
            return EntityRelationshipDensity.MEDIUM
        return EntityRelationshipDensity.LOW

    def _detect_language(self, tokens: List[str]) -> str:
        token_set = set(tokens[:100])
        if token_set.intersection({"der", "die", "das", "und", "ist"}):
            return "de"
        if token_set.intersection({"el", "la", "los", "las", "es", "en"}):
            return "es"
        if token_set.intersection({"le", "la", "les", "et", "est"}):
            return "fr"
        return "en"

    def _build_characteristics(
        self,
        facts: StructuralFacts,
        sample: AnalysisSample,
        modality: ContentModality,
        domain: str,
    ) -> List[str]:
        chars = []
        if modality == ContentModality.TABULAR_DATASET:
            chars.append(f"Structured dataset with {facts.table_count} table sheet(s) and {facts.total_rows or 'multiple'} rows.")
            if facts.has_numerical_columns:
                chars.append("Contains numerical quantitative attributes suitable for aggregation.")
        elif modality == ContentModality.HIERARCHICAL_DOCUMENT:
            chars.append(f"Hierarchical section structure with heading depth {facts.heading_depth}.")
            chars.append(f"Contains {facts.total_words} words across narrative paragraphs.")
        elif modality == ContentModality.SLIDE_PRESENTATION:
            chars.append(f"Slide deck presentation with {facts.slide_count or 'multiple'} distinct slides.")
        else:
            chars.append(f"Narrative document text with approx {facts.total_words} words.")

        chars.append(f"Content reflects {domain.capitalize()} domain terminology and structure.")
        return chars

    def _generate_objective_summary(
        self,
        source: SourceRecord,
        facts: StructuralFacts,
        modality: ContentModality,
        domain: str,
        entities: List[str],
    ) -> str:
        entity_str = f" such as {', '.join(entities[:3])}" if entities else ""
        if modality == ContentModality.TABULAR_DATASET:
            return f"This {domain} dataset contains structured records and metrics{entity_str}. It is organized into {facts.table_count} sheet(s) with defined column schemas."
        elif modality == ContentModality.HIERARCHICAL_DOCUMENT:
            return f"This {domain} document contains hierarchical sections and headings{entity_str}. It describes operational standards across {facts.page_count or 'multiple'} pages."
        elif modality == ContentModality.SLIDE_PRESENTATION:
            return f"This presentation contains structured slide content concerning {domain} topics{entity_str}. Information is formatted into bullet points and section headers."
        else:
            return f"This document contains narrative text focused on {domain} topics{entity_str}. It presents descriptive information in sequential paragraphs."
