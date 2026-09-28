"""Format parsers registry and factory router."""

from typing import Dict, Type
from ragger_engine.ingestion.parsers.base import BaseParser
from ragger_engine.ingestion.parsers.pdf import PDFParser
from ragger_engine.ingestion.parsers.docx import DOCXParser
from ragger_engine.ingestion.parsers.pptx import PPTXParser
from ragger_engine.ingestion.parsers.txt import TXTParser
from ragger_engine.ingestion.parsers.markdown import MarkdownParser
from ragger_engine.ingestion.parsers.csv_tsv import CSVParser, TSVParser
from ragger_engine.ingestion.parsers.xlsx import XLSXParser
from ragger_engine.ingestion.parsers.xls import XLSParser
from ragger_engine.ingestion.parsers.json_parser import JSONParser
from ragger_engine.ingestion.parsers.xml_parser import XMLParser
from ragger_engine.ingestion.parsers.html_parser import HTMLParser
from ragger_engine.ingestion.parsers.epub_parser import EPUBParser
from ragger_engine.ingestion.parsers.doc import DOCParser

PARSER_REGISTRY: Dict[str, Type[BaseParser]] = {
    "pdf": PDFParser,
    "docx": DOCXParser,
    "pptx": PPTXParser,
    "txt": TXTParser,
    "md": MarkdownParser,
    "csv": CSVParser,
    "tsv": TSVParser,
    "xlsx": XLSXParser,
    "xls": XLSParser,
    "json": JSONParser,
    "xml": XMLParser,
    "html": HTMLParser,
    "epub": EPUBParser,
    "doc": DOCParser,
}


def get_parser_for_format(format_name: str) -> BaseParser:
    """Instantiates the format-specific parser for the requested format."""
    normalized = format_name.lower().strip()
    parser_cls = PARSER_REGISTRY.get(normalized)
    if not parser_cls:
        raise ValueError(f"No parser registered for format: '{format_name}'")
    return parser_cls()
