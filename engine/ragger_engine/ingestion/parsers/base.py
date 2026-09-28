"""Abstract base parser interface."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Union

from ragger_engine.ingestion.models import DatasetModel, DocumentModel, SourceRecord


class BaseParser(ABC):
    """Abstract base class implemented by all format-specific parsers."""

    @abstractmethod
    def parse(self, file_path: Path, source: SourceRecord) -> Union[DocumentModel, DatasetModel]:
        """Parses the input file into a normalized DocumentModel or DatasetModel.

        Must preserve structure, source-location coordinates, and never call an LLM.
        """
        pass
