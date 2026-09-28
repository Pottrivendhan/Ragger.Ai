"""CSV and TSV tabular parsers producing normalized DatasetModel."""

import csv
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple
import charset_normalizer

from ragger_engine.ingestion.exceptions import ParserError
from ragger_engine.ingestion.models import (
    ColumnSchema,
    DatasetModel,
    SourceRecord,
    TableSheet,
)
from ragger_engine.ingestion.parsers.base import BaseParser

# Bounded limit for in-memory preview/statistical evaluation
MAX_PREVIEW_ROWS = 50_000


def infer_scalar_type(val: str) -> Tuple[str, Any]:
    """Infers the data type of a string value."""
    val_stripped = val.strip()
    if not val_stripped or val_stripped.lower() in ("null", "none", "na", "n/a", "nan"):
        return "null", None

    # Check boolean
    if val_stripped.lower() in ("true", "false"):
        return "boolean", val_stripped.lower() == "true"

    # Check integer
    try:
        int_val = int(val_stripped)
        return "integer", int_val
    except ValueError:
        pass

    # Check float
    try:
        float_val = float(val_stripped)
        return "float", float_val
    except ValueError:
        pass

    # Check ISO-like datetime
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y"):
        try:
            dt = datetime.strptime(val_stripped, fmt)
            return "datetime", dt.isoformat()
        except ValueError:
            pass

    return "string", val_stripped


class CSVParser(BaseParser):
    """Parses comma-separated and delimiter-separated datasets into DatasetModel."""

    def __init__(self, forced_delimiter: str = None):
        self.forced_delimiter = forced_delimiter

    def parse(self, file_path: Path, source: SourceRecord) -> DatasetModel:
        warnings: List[str] = []

        try:
            with open(file_path, "rb") as f:
                raw_sample = f.read(65536)
        except Exception as e:
            raise ParserError(f"Failed to read CSV/TSV file: {e}", parser_name="CSVParser")

        detected_enc = charset_normalizer.from_bytes(raw_sample).best()
        encoding = detected_enc.encoding if detected_enc else "utf-8"

        # Disambiguate delimiter
        sample_text = raw_sample.decode(encoding, errors="replace")
        delimiter = self.forced_delimiter
        if not delimiter:
            try:
                dialect = csv.Sniffer().sniff(sample_text[:4096])
                delimiter = dialect.delimiter
            except Exception:
                delimiter = "\t" if file_path.suffix.lower() == ".tsv" else ","

        columns_data: Dict[str, List[Any]] = {}
        row_dicts: List[Dict[str, Any]] = []
        headers: List[str] = []
        total_rows = 0

        try:
            with open(file_path, "r", encoding=encoding, errors="replace") as f:
                reader = csv.reader(f, delimiter=delimiter)
                header_row = next(reader, None)
                if not header_row:
                    raise ParserError("File is empty or contains no tabular rows.", parser_name="CSVParser")

                headers = [h.strip() or f"col_{i}" for i, h in enumerate(header_row)]
                columns_data = {h: [] for h in headers}

                for row_idx, row in enumerate(reader):
                    total_rows += 1
                    # Pad row if columns are missing
                    padded_row = row + [""] * (len(headers) - len(row))
                    row_dict = {}

                    for h, val in zip(headers, padded_row):
                        dtype, parsed_val = infer_scalar_type(val)
                        row_dict[h] = parsed_val
                        if row_idx < MAX_PREVIEW_ROWS:
                            columns_data[h].append(parsed_val)

                    if row_idx < 1000:
                        row_dicts.append(row_dict)

        except Exception as e:
            raise ParserError(f"Error parsing delimited text stream: {e}", parser_name="CSVParser")

        # Compute column schemas
        column_schemas: List[ColumnSchema] = []
        for h in headers:
            vals = columns_data[h]
            non_nulls = [v for v in vals if v is not None]
            null_count = len(vals) - len(non_nulls)
            distinct_count = len(set(str(v) for v in non_nulls))
            sample_vals = non_nulls[:5]

            # Incur dominant type
            type_counts = {}
            for v in non_nulls:
                t = type(v).__name__
                type_counts[t] = type_counts.get(t, 0) + 1

            dom_type = "string"
            if type_counts:
                py_type = max(type_counts, key=type_counts.get)
                dom_type = "integer" if py_type == "int" else "float" if py_type == "float" else "boolean" if py_type == "bool" else "string"

            # Numerical stats if applicable
            num_vals = [v for v in non_nulls if isinstance(v, (int, float))]
            min_v = min(num_vals) if num_vals else None
            max_v = max(num_vals) if num_vals else None
            mean_v = sum(num_vals) / len(num_vals) if num_vals else None

            column_schemas.append(
                ColumnSchema(
                    name=h,
                    inferred_type=dom_type,
                    null_count=null_count,
                    distinct_count=distinct_count,
                    sample_values=sample_vals,
                    min_value=min_v,
                    max_value=max_v,
                    mean_value=round(mean_v, 2) if mean_v is not None else None,
                )
            )

        sheet = TableSheet(
            sheet_name=file_path.stem,
            columns=column_schemas,
            rows=row_dicts,
            total_rows=total_rows,
            total_columns=len(headers),
            warnings=warnings,
        )

        return DatasetModel(
            source_id=source.source_id,
            title=file_path.stem,
            format="tsv" if delimiter == "\t" else "csv",
            metadata={"delimiter": delimiter, "encoding": encoding},
            sheets=[sheet],
            total_sheets=1,
            total_rows_across_sheets=total_rows,
            warnings=warnings,
        )


class TSVParser(CSVParser):
    """Specialized TSV parser using tab delimiter."""

    def __init__(self):
        super().__init__(forced_delimiter="\t")
