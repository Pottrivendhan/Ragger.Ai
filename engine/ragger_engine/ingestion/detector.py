"""Multi-signal deterministic file detector.

Combines magic byte inspection, container structure analysis, MIME sniffing,
and content structure without relying solely on file extensions or LLMs.
"""

import csv
import json
import mimetypes
import os
import zipfile
from pathlib import Path
from typing import Optional, Union

from ragger_engine.ingestion.models import DetectedFileType


# Standard MIME mappings for target formats
FORMAT_MIME_MAP = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc": "application/msword",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "epub": "application/epub+zip",
    "csv": "text/csv",
    "tsv": "text/tab-separated-values",
    "json": "application/json",
    "xml": "application/xml",
    "html": "text/html",
    "md": "text/markdown",
    "txt": "text/plain",
}


class FileDetector:
    """Deterministic, multi-signal file format detector."""

    @classmethod
    def detect_file(cls, file_path: Union[str, Path]) -> DetectedFileType:
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            return DetectedFileType(
                format="unknown",
                mime_type="application/octet-stream",
                confidence=0.0,
                detection_method="error",
                warnings=[f"File does not exist or is not readable: {path}"],
            )

        file_size = path.stat().st_size
        if file_size == 0:
            return DetectedFileType(
                format="empty",
                mime_type="inode/x-empty",
                confidence=1.0,
                detection_method="size_check",
                warnings=["File is 0 bytes (empty)."],
            )

        # Read the first 4096 bytes for header signature inspection
        try:
            with open(path, "rb") as f:
                header = f.read(4096)
        except Exception as e:
            return DetectedFileType(
                format="unknown",
                mime_type="application/octet-stream",
                confidence=0.0,
                detection_method="read_error",
                warnings=[f"Failed to read file bytes: {e}"],
            )

        ext = path.suffix.lower().lstrip(".")

        # Signal 1: PDF Magic Bytes (%PDF-)
        if header.startswith(b"%PDF-"):
            return DetectedFileType(
                format="pdf",
                mime_type=FORMAT_MIME_MAP["pdf"],
                confidence=1.0,
                detection_method="magic_bytes",
                warnings=[] if ext == "pdf" else [f"Extension '.{ext}' does not match detected PDF format."],
            )

        # Signal 2: Zip Container inspection (DOCX, PPTX, XLSX, EPUB)
        if header.startswith(b"PK\x03\x04"):
            zip_type = cls._inspect_zip_container(path, ext)
            if zip_type:
                return zip_type

        # Signal 3: Microsoft Compound File Binary (Legacy DOC, XLS)
        if header.startswith(b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"):
            cfbf_type = cls._inspect_cfbf_container(header, ext)
            if cfbf_type:
                return cfbf_type

        # Signal 4: XML Header or DOCTYPE
        stripped_head = header.lstrip(b"\xef\xbb\xbf \t\r\n")  # Strip UTF-8 BOM and whitespace
        if stripped_head.startswith(b"<?xml") or (stripped_head.startswith(b"<") and b">" in stripped_head[:200]):
            xml_or_html = cls._inspect_xml_or_html(stripped_head, ext)
            if xml_or_html:
                return xml_or_html

        # Signal 5: HTML without leading XML declaration (<!DOCTYPE html or <html>)
        lower_head = stripped_head[:500].lower()
        if b"<!doctype html" in lower_head or b"<html" in lower_head:
            return DetectedFileType(
                format="html",
                mime_type=FORMAT_MIME_MAP["html"],
                confidence=0.95,
                detection_method="html_tags",
                warnings=[] if ext in ("html", "htm") else [f"Extension '.{ext}' does not match detected HTML format."],
            )

        # Signal 6: JSON Structure ({ or [)
        if stripped_head.startswith((b"{", b"[")):
            json_type = cls._inspect_json_candidate(path, ext)
            if json_type:
                return json_type

        # Signal 7: Textual content (CSV, TSV, Markdown, TXT)
        text_type = cls._inspect_text_candidate(path, header, ext)
        if text_type:
            return text_type

        # Fallback: Unknown binary format
        return DetectedFileType(
            format="unknown",
            mime_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
            confidence=0.1,
            detection_method="unknown",
            warnings=[f"Unrecognized binary structure or unsupported format with extension '.{ext}'."],
        )

    @classmethod
    def _inspect_zip_container(cls, path: Path, ext: str) -> Optional[DetectedFileType]:
        """Inspects internal zip manifests to disambiguate Office XML formats and EPUBs."""
        try:
            with zipfile.ZipFile(path, "r") as zf:
                names = set(zf.namelist())

                # Check for EPUB
                if "mimetype" in names or "META-INF/container.xml" in names:
                    try:
                        mimetype_bytes = zf.read("mimetype").decode("utf-8", errors="ignore").strip()
                        if "application/epub+zip" in mimetype_bytes:
                            return DetectedFileType(
                                format="epub",
                                mime_type=FORMAT_MIME_MAP["epub"],
                                confidence=1.0,
                                detection_method="container_manifest",
                                warnings=[] if ext == "epub" else [f"Extension '.{ext}' does not match detected EPUB."],
                            )
                    except Exception:
                        pass
                    if "META-INF/container.xml" in names:
                        return DetectedFileType(
                            format="epub",
                            mime_type=FORMAT_MIME_MAP["epub"],
                            confidence=0.9,
                            detection_method="container_manifest",
                            warnings=[] if ext == "epub" else [f"Extension '.{ext}' does not match detected EPUB."],
                        )

                # Check for Office Open XML
                if "[Content_Types].xml" in names:
                    if any(n.startswith("word/") for n in names):
                        return DetectedFileType(
                            format="docx",
                            mime_type=FORMAT_MIME_MAP["docx"],
                            confidence=1.0,
                            detection_method="container_manifest",
                            warnings=[] if ext == "docx" else [f"Extension '.{ext}' does not match detected DOCX."],
                        )
                    if any(n.startswith("xl/") for n in names):
                        return DetectedFileType(
                            format="xlsx",
                            mime_type=FORMAT_MIME_MAP["xlsx"],
                            confidence=1.0,
                            detection_method="container_manifest",
                            warnings=[] if ext == "xlsx" else [f"Extension '.{ext}' does not match detected XLSX."],
                        )
                    if any(n.startswith("ppt/") for n in names):
                        return DetectedFileType(
                            format="pptx",
                            mime_type=FORMAT_MIME_MAP["pptx"],
                            confidence=1.0,
                            detection_method="container_manifest",
                            warnings=[] if ext == "pptx" else [f"Extension '.{ext}' does not match detected PPTX."],
                        )
        except Exception as e:
            return DetectedFileType(
                format="unknown",
                mime_type="application/zip",
                confidence=0.4,
                detection_method="corrupted_zip",
                warnings=[f"File has zip header but manifest could not be read: {e}"],
            )
        return None

    @classmethod
    def _inspect_cfbf_container(cls, header: bytes, ext: str) -> Optional[DetectedFileType]:
        """Disambiguates legacy Microsoft CFBF (DOC vs XLS)."""
        if ext == "xls":
            return DetectedFileType(
                format="xls",
                mime_type=FORMAT_MIME_MAP["xls"],
                confidence=0.9,
                detection_method="magic_bytes_and_ext",
                warnings=[],
            )
        if ext == "doc":
            return DetectedFileType(
                format="doc",
                mime_type=FORMAT_MIME_MAP["doc"],
                confidence=0.9,
                detection_method="magic_bytes_and_ext",
                warnings=[],
            )
        # CFBF container with non-standard extension
        return DetectedFileType(
            format="doc" if b"WordDocument" in header else "xls",
            mime_type=FORMAT_MIME_MAP["doc"] if b"WordDocument" in header else FORMAT_MIME_MAP["xls"],
            confidence=0.7,
            detection_method="cfbf_signature",
            warnings=[f"Compound binary format detected with non-matching extension '.{ext}'."],
        )

    @classmethod
    def _inspect_xml_or_html(cls, stripped_head: bytes, ext: str) -> Optional[DetectedFileType]:
        """Disambiguates XML documents from XHTML / HTML."""
        lower = stripped_head.lower()
        if b"<html" in lower or b"<!doctype html" in lower:
            return DetectedFileType(
                format="html",
                mime_type=FORMAT_MIME_MAP["html"],
                confidence=0.9,
                detection_method="html_tags",
                warnings=[] if ext in ("html", "htm") else [f"Extension '.{ext}' does not match detected HTML."],
            )
        return DetectedFileType(
            format="xml",
            mime_type=FORMAT_MIME_MAP["xml"],
            confidence=0.95,
            detection_method="xml_declaration",
            warnings=[] if ext == "xml" else [f"Extension '.{ext}' does not match detected XML."],
        )

    @classmethod
    def _inspect_json_candidate(cls, path: Path, ext: str) -> Optional[DetectedFileType]:
        """Validates JSON by reading a small chunk or parsing structure."""
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                snippet = f.read(10000).strip()
                # Check for closed object/array or complete parse on small files
                if path.stat().st_size < 100000:
                    json.loads(snippet)
                    return DetectedFileType(
                        format="json",
                        mime_type=FORMAT_MIME_MAP["json"],
                        confidence=1.0,
                        detection_method="json_parse",
                        warnings=[] if ext == "json" else [f"Extension '.{ext}' does not match detected JSON."],
                    )
                else:
                    # Larger file with valid json opening
                    if snippet.startswith(("{", "[")):
                        return DetectedFileType(
                            format="json",
                            mime_type=FORMAT_MIME_MAP["json"],
                            confidence=0.85,
                            detection_method="json_sniff",
                            warnings=[] if ext == "json" else [f"Extension '.{ext}' does not match detected JSON."],
                        )
        except Exception:
            pass
        return None

    @classmethod
    def _inspect_text_candidate(cls, path: Path, header: bytes, ext: str) -> Optional[DetectedFileType]:
        """Disambiguates text-based formats: CSV, TSV, Markdown, TXT."""
        # Check for binary null bytes
        if b"\x00" in header:
            return None

        # Read first few text lines
        try:
            text_sample = header.decode("utf-8", errors="replace")
        except Exception:
            return None

        lines = [line.strip() for line in text_sample.splitlines() if line.strip()][:20]
        if not lines:
            return None

        # 1. Check for TSV (tab delimited)
        if ext == "tsv" or any("\t" in line for line in lines[:5]):
            tab_counts = [line.count("\t") for line in lines[:5]]
            if len(tab_counts) > 1 and tab_counts[0] > 0 and all(c == tab_counts[0] for c in tab_counts):
                return DetectedFileType(
                    format="tsv",
                    mime_type=FORMAT_MIME_MAP["tsv"],
                    confidence=0.95,
                    detection_method="delimiter_sniff",
                    warnings=[] if ext == "tsv" else [f"Extension '.{ext}' does not match detected TSV format."],
                )

        # 2. Check for CSV (comma or semicolon delimited with uniform column counts)
        if ext in ("csv", "txt") or any("," in line or ";" in line for line in lines[:5]):
            for delimiter in (",", ";"):
                counts = [line.count(delimiter) for line in lines[:5]]
                if len(counts) > 1 and counts[0] > 0 and all(c == counts[0] for c in counts):
                    return DetectedFileType(
                        format="csv",
                        mime_type=FORMAT_MIME_MAP["csv"],
                        confidence=0.95,
                        detection_method="delimiter_sniff",
                        warnings=[] if ext == "csv" else [f"Extension '.{ext}' does not match detected CSV format."],
                    )

        # 3. Check for Markdown (headings with #, markdown tables |, bullet lists, code blocks)
        md_signals = sum(
            1 for line in lines
            if line.startswith(("#", "- ", "* ", "> ", "```")) or ("|" in line and "-|-" in line)
        )
        if ext in ("md", "markdown") or md_signals >= 2:
            return DetectedFileType(
                format="md",
                mime_type=FORMAT_MIME_MAP["md"],
                confidence=0.9 if ext in ("md", "markdown") else 0.8,
                detection_method="markdown_syntax",
                warnings=[] if ext in ("md", "markdown") else [f"Extension '.{ext}' does not match detected Markdown."],
            )

        # 4. Plain Text fallback
        return DetectedFileType(
            format="txt",
            mime_type=FORMAT_MIME_MAP["txt"],
            confidence=0.85 if ext == "txt" else 0.7,
            detection_method="text_encoding",
            warnings=[] if ext == "txt" else [f"File detected as plain text with extension '.{ext}'."],
        )
