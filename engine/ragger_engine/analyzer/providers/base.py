"""Abstract Base Class for Analyzer Providers."""

from abc import ABC, abstractmethod
from typing import Tuple
from ragger_engine.analyzer.models import ProviderTelemetry, SemanticObservations, StructuralFacts
from ragger_engine.ingestion.models import AnalysisSample, SourceRecord


class BaseAnalyzerProvider(ABC):
    """Abstract interface for Analyzer Providers (Heuristic, Ollama, OpenAI-compatible)."""

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique identifier for this provider, e.g. 'heuristic_offline', 'ollama'."""
        pass

    @abstractmethod
    async def analyze(
        self,
        source: SourceRecord,
        facts: StructuralFacts,
        sample: AnalysisSample,
    ) -> Tuple[SemanticObservations, ProviderTelemetry]:
        """Observes the sample and returns semantic observations along with provider telemetry."""
        pass
