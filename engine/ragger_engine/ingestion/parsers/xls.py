"""Legacy XLS format parser using xlrd into DatasetModel."""

from pathlib import Path
from typing import Any, Dict, List
import xlrd

from ragger_engine.ingestion.exceptions import ParserError
from ragger_engine.ingestion.models import (
    ColumnSchema,
    DatasetModel,
    SourceRecord,
    TableSheet,
)
from ragger_engine.ingestion.parsers.base import BaseParser


class XLSParser(BaseParser):
    """Parses legacy Excel XLS workbooks preserving sheets into DatasetModel."""

    def parse(self, file_path: Path, source: SourceRecord) -> DatasetModel:
        try:
            wb = xlrd.open_workbook(str(file_path))
        except Exception as e:
            raise ParserError(f"Failed to read legacy XLS workbook: {e}", parser_name="XLSParser")

        sheets: List[TableSheet] = []
        warnings: List[str] = []
        total_rows_all = 0

        for sheet_idx in range(wb.nsheets):
            ws = wb.sheet_by_index(sheet_idx)
            sheet_name = ws.name
            num_rows = ws.nrows
            num_cols = ws.ncols

            if num_rows == 0:
                sheets.append(
                    TableSheet(
                        sheet_name=sheet_name,
                        columns=[],
                        rows=[],
                        total_rows=0,
                        total_columns=0,
                        warnings=["Worksheet has 0 rows."],
                    )
                )
                continue

            # Header row
            headers = [
                str(ws.cell_value(0, col)).strip() or f"col_{col}"
                for col in range(num_cols)
            ]
            columns_data: Dict[str, List[Any]] = {h: [] for h in headers}
            sheet_rows: List[Dict[str, Any]] = []

            for row_idx in range(1, num_rows):
                row_dict = {}
                for col_idx, h in enumerate(headers):
                    val = ws.cell_value(row_idx, col_idx)
                    row_dict[h] = val
                    if row_idx <= 20_000:
                        columns_data[h].append(val)
                if row_idx <= 1000:
                    sheet_rows.append(row_dict)

            actual_data_rows = max(num_rows - 1, 0)
            total_rows_all += actual_data_rows

            col_schemas: List[ColumnSchema] = []
            for h in headers:
                vals = columns_data[h]
                non_nulls = [v for v in vals if v != "" and v is not None]
                null_count = len(vals) - len(non_nulls)
                distinct_count = len(set(str(v) for v in non_nulls))

                dom_type = "string"
                num_vals = [v for v in non_nulls if isinstance(v, (int, float))]
                if len(num_vals) == len(non_nulls) and non_nulls:
                    dom_type = "float"

                col_schemas.append(
                    ColumnSchema(
                        name=h,
                        inferred_type=dom_type,
                        null_count=null_count,
                        distinct_count=distinct_count,
                        sample_values=non_nulls[:5],
                        min_value=min(num_vals) if num_vals else None,
                        max_value=max(num_vals) if num_vals else None,
                        mean_value=round(sum(num_vals) / len(num_vals), 2) if num_vals else None,
                    )
                )

            sheets.append(
                TableSheet(
                    sheet_name=sheet_name,
                    columns=col_schemas,
                    rows=sheet_rows,
                    total_rows=actual_data_rows,
                    total_columns=num_cols,
                )
            )

        return DatasetModel(
            source_id=source.source_id,
            title=file_path.stem,
            format="xls",
            metadata={"sheet_count": len(sheets)},
            sheets=sheets,
            total_sheets=len(sheets),
            total_rows_across_sheets=total_rows_all,
            warnings=warnings,
        )
