"""Domain exception hierarchy for file ingestion, detection, and parsing."""


class IngestionError(Exception):
    """Base exception for all ingestion errors."""

    def __init__(self, message: str, code: str = "INGESTION_ERROR", status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class UnsupportedFormatError(IngestionError):
    """Raised when file format is unrecognized or unsupported."""

    def __init__(self, message: str, detected_format: str = "unknown"):
        super().__init__(message, code="UNSUPPORTED_FILE_TYPE", status_code=415)
        self.detected_format = detected_format


class FileTooLargeError(IngestionError):
    """Raised when file exceeds size quotas."""

    def __init__(self, message: str, size_bytes: int, max_bytes: int):
        super().__init__(message, code="FILE_TOO_LARGE", status_code=413)
        self.size_bytes = size_bytes
        self.max_bytes = max_bytes


class PathTraversalError(IngestionError):
    """Raised when path attempts directory traversal outside root."""

    def __init__(self, message: str = "Path traversal attempted outside allowed root."):
        super().__init__(message, code="PATH_NOT_ALLOWED", status_code=403)


class SecurityLimitExceededError(IngestionError):
    """Raised when archive or document exceeds safe decompression/entity limits."""

    def __init__(self, message: str, code: str = "SECURITY_LIMIT_EXCEEDED"):
        super().__init__(message, code=code, status_code=422)


class ParserError(IngestionError):
    """Raised when a specific parser fails on corrupted or malformed content."""

    def __init__(self, message: str, parser_name: str, code: str = "PARSER_ERROR"):
        super().__init__(message, code=code, status_code=422)
        self.parser_name = parser_name


class ExtractionLimitationError(IngestionError):
    """Raised when legacy or proprietary format cannot be extracted reliably."""

    def __init__(self, message: str, format_name: str):
        super().__init__(message, code="EXTRACTION_LIMITATION", status_code=422)
        self.format_name = format_name
