"""Generates synthetic, structurally valid test fixtures for all 14 formats + security edge cases."""

import csv
import json
import os
import zipfile
from pathlib import Path
from pypdf import PdfWriter
from pypdf.generic import NameObject, create_string_object
import docx
from pptx import Presentation
from pptx.util import Inches, Pt
import openpyxl

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURES_DIR.mkdir(parents=True, exist_ok=True)


def generate_pdf():
    pdf_path = FIXTURES_DIR / "sample.pdf"
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

    writer = PdfWriter()

    def add_page_with_text(paragraphs: list[tuple[str, bool]]):
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject()
        font[NameObject("/Type")] = NameObject("/Font")
        font[NameObject("/Subtype")] = NameObject("/Type1")
        font[NameObject("/BaseFont")] = NameObject("/Helvetica")
        fonts = DictionaryObject()
        fonts[NameObject("/F1")] = font
        resources = DictionaryObject()
        resources[NameObject("/Font")] = fonts
        page[NameObject("/Resources")] = resources

        stream_cmds = []
        y = 720
        for text, is_hd in paragraphs:
            size = 18 if is_hd else 12
            stream_cmds.append(f"BT /F1 {size} Tf 50 {y} Td ({text}) Tj ET")
            y -= 40
        
        stream = DecodedStreamObject()
        stream._data = "\n".join(stream_cmds).encode("latin1")
        page[NameObject("/Contents")] = stream
        return page

    add_page_with_text([
        ("ANNUAL BUSINESS REPORT", True),
        ("This is the executive summary paragraph of the company report.", False),
        ("It contains financial targets and operational guidelines.", False),
    ])

    add_page_with_text([
        ("FINANCIAL PERFORMANCE", True),
        ("Revenue increased by 14 percent across all operational divisions.", False),
    ])

    with open(pdf_path, "wb") as f:
        writer.write(f)
    print(f"Generated {pdf_path}")


def generate_docx():
    docx_path = FIXTURES_DIR / "sample.docx"
    doc = docx.Document()
    doc.add_heading("Company Technical Specification", level=1)
    doc.add_paragraph("This technical document specifies architecture standards.")
    doc.add_heading("Section 1: Microservices", level=2)
    doc.add_paragraph("All services communicate over mutual TLS and authenticated loopback.")
    
    # Add list items
    doc.add_paragraph("High availability", style="List Bullet")
    doc.add_paragraph("Fault tolerance", style="List Bullet")

    # Add table
    table = doc.add_table(rows=3, cols=3)
    headers = ["Service", "Port", "Status"]
    for i, h in enumerate(headers):
        table.rows[0].cells[i].text = h
    data = [["Gateway", "443", "Active"], ["Engine", "8000", "Ready"]]
    for row_idx, r in enumerate(data, start=1):
        for col_idx, val in enumerate(r):
            table.rows[row_idx].cells[col_idx].text = val

    doc.save(str(docx_path))
    print(f"Generated {docx_path}")


def generate_pptx():
    pptx_path = FIXTURES_DIR / "sample.pptx"
    prs = Presentation()

    # Slide 1
    slide_layout = prs.slide_layouts[0]
    slide1 = prs.slides.add_slide(slide_layout)
    slide1.shapes.title.text = "Quarterly Strategic Review"
    slide1.placeholders[1].text = "Presenter: Engineering Team\nFocus: Knowledge Systems"

    # Slide 2 with table and notes
    slide_layout2 = prs.slide_layouts[5] # title only
    slide2 = prs.slides.add_slide(slide_layout2)
    slide2.shapes.title.text = "Infrastructure Milestones"

    # Add table
    shapes = slide2.shapes
    rows, cols = 3, 2
    left, top, width, height = Inches(1.5), Inches(2.0), Inches(6.0), Inches(1.5)
    table_shape = shapes.add_table(rows, cols, left, top, width, height)
    table = table_shape.table
    table.cell(0, 0).text = "Milestone"
    table.cell(0, 1).text = "Status"
    table.cell(1, 0).text = "Ingestion Pipeline"
    table.cell(1, 1).text = "Completed"
    table.cell(2, 0).text = "Vector Store"
    table.cell(2, 1).text = "Planned"

    # Speaker notes
    notes = slide2.notes_slide
    notes.notes_text_frame.text = "Highlight that all milestone targets were achieved within schedule."

    prs.save(str(pptx_path))
    print(f"Generated {pptx_path}")


def generate_xlsx():
    xlsx_path = FIXTURES_DIR / "sample.xlsx"
    wb = openpyxl.Workbook()

    # Sheet 1: Sales
    ws1 = wb.active
    ws1.title = "Sales"
    ws1.append(["Transaction_ID", "Product", "Revenue", "Units"])
    ws1.append([1001, "Server Rack", 2450.50, 2])
    ws1.append([1002, "Switch L3", 890.00, 4])
    ws1.append([1003, "Patch Panel", 120.75, 10])

    # Sheet 2: Regions
    ws2 = wb.create_sheet(title="Regions")
    ws2.append(["Region_Code", "Region_Name", "Manager", "Active"])
    ws2.append(["NA-EAST", "North America East", "Alice Smith", True])
    ws2.append(["EU-CENTRAL", "Europe Central", "Bob Jones", True])

    wb.save(str(xlsx_path))
    print(f"Generated {xlsx_path}")


def generate_csv_and_tsv():
    csv_path = FIXTURES_DIR / "sample.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "customer", "amount", "category", "created_date"])
        writer.writerow([1, "Acme Corp", 1540.25, "Enterprise", "2026-01-15"])
        writer.writerow([2, "Globex Inc", 450.00, "Mid-Market", "2026-02-20"])
        writer.writerow([3, "Initech", 89.99, "Startup", "2026-03-05"])
    print(f"Generated {csv_path}")

    tsv_path = FIXTURES_DIR / "sample.tsv"
    with open(tsv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["gene_id", "symbol", "expression_level", "chromosome"])
        writer.writerow(["ENSG0001", "BRCA1", 12.45, "chr17"])
        writer.writerow(["ENSG0002", "TP53", 45.12, "chr17"])
        writer.writerow(["ENSG0003", "EGFR", 8.32, "chr7"])
    print(f"Generated {tsv_path}")


def generate_txt_and_md():
    txt_path = FIXTURES_DIR / "sample.txt"
    txt_content = (
        "SYSTEM OPERATIONAL POLICY\n\n"
        "This policy governs data handling across all production repositories.\n"
        "Employees must follow data classification guidelines.\n\n"
        "SECURITY PROCEDURES\n\n"
        "All credentials must be stored in approved secret managers.\n"
        "Access tokens must be refreshed every 30 days.\n"
    )
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(txt_content)
    print(f"Generated {txt_path}")

    md_path = FIXTURES_DIR / "sample.md"
    md_content = """# Ragger.ai Engineering Guide

This document outlines architecture and coding principles.

## Core Directives

1. Maintain modular boundaries.
2. Deterministic execution over prompt chaos.

### Architecture Table

| Tier | Technology | Purpose |
| --- | --- | --- |
| Frontend | React + Vite | User Interface |
| Desktop | Electron | Process Host |
| Engine | Python FastAPI | Processing |

> "Always test real systems against real edge cases."

```python
def example():
    return "Hello Ragger"
```
"""
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"Generated {md_path}")


def generate_json_and_xml():
    json_path = FIXTURES_DIR / "sample.json"
    records = [
        {"id": 1, "name": "Athena", "role": "Architect", "level": "Principal", "salary": 185000},
        {"id": 2, "name": "Boreas", "role": "Engineer", "level": "Senior", "salary": 145000},
        {"id": 3, "name": "Clio", "role": "Researcher", "level": "Staff", "salary": 165000},
    ]
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2)
    print(f"Generated {json_path}")

    xml_path = FIXTURES_DIR / "sample.xml"
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<inventory>
    <item>
        <id>SKU-101</id>
        <name>Sensor Node</name>
        <qty>50</qty>
        <price>89.50</price>
    </item>
    <item>
        <id>SKU-102</id>
        <name>Gateway Unit</name>
        <qty>20</qty>
        <price>299.00</price>
    </item>
</inventory>
"""
    with open(xml_path, "w", encoding="utf-8") as f:
        f.write(xml_content)
    print(f"Generated {xml_path}")


def generate_html():
    html_path = FIXTURES_DIR / "sample.html"
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Company Knowledge Portal</title>
</head>
<body>
    <header><nav><a href="#">Home</a> <a href="#">Login</a></nav></header>
    <h1>Knowledge Engineering Overview</h1>
    <p>Welcome to the central portal for research and engineering documentation.</p>
    <h2>Department Directives</h2>
    <p>All departments must maintain up-to-date knowledge repositories.</p>
    <table>
        <tr><th>Department</th><th>Lead</th></tr>
        <tr><td>AI Systems</td><td>Dr. Alan</td></tr>
        <tr><td>Platform Core</td><td>Sarah T.</td></tr>
    </table>
    <footer><p>Copyright 2026 Ragger.ai Inc.</p></footer>
</body>
</html>
"""
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Generated {html_path}")


def generate_epub():
    epub_path = FIXTURES_DIR / "sample.epub"
    with zipfile.ZipFile(epub_path, "w") as zf:
        # 1. mimetype (must be first, uncompressed)
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)

        # 2. META-INF/container.xml
        container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
    <rootfiles>
        <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
    </rootfiles>
</container>
"""
        zf.writestr("META-INF/container.xml", container_xml)

        # 3. OEBPS/content.opf
        content_opf = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="pub-id">
    <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
        <dc:title>Principles of Knowledge Engineering</dc:title>
        <dc:creator>Ragger Engineering</dc:creator>
    </metadata>
    <manifest>
        <item id="chapter1" href="chapter1.xhtml" media-type="application/xhtml+xml"/>
        <item id="chapter2" href="chapter2.xhtml" media-type="application/xhtml+xml"/>
    </manifest>
    <spine>
        <itemref idref="chapter1"/>
        <itemref idref="chapter2"/>
    </spine>
</package>
"""
        zf.writestr("OEBPS/content.opf", content_opf)

        # 4. Chapters
        ch1 = """<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Chapter 1</title></head>
<body>
    <h1>Chapter 1: The Foundations of Knowledge</h1>
    <p>Knowledge engineering is the process of translating unstructured information into structured intelligence.</p>
</body>
</html>
"""
        ch2 = """<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml">
<head><title>Chapter 2</title></head>
<body>
    <h1>Chapter 2: Structural Preservation</h1>
    <p>Preserving headings and tables is critical for high-fidelity retrieval.</p>
</body>
</html>
"""
        zf.writestr("OEBPS/chapter1.xhtml", ch1)
        zf.writestr("OEBPS/chapter2.xhtml", ch2)

    print(f"Generated {epub_path}")


def generate_doc():
    doc_path = FIXTURES_DIR / "sample.doc"
    # CFBF header: \xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1 followed by text runs in WordDocument format
    cfbf_header = b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1" + (b"\x00" * 504)
    # Add identifiable UTF-16LE text stream
    text = "Legacy Word Document Title\r\nThis is a legacy company policy document from Word 97-2003 era.\r\nAll employees must read this clause.\r\n"
    stream_content = text.encode("utf-16le")
    doc_bytes = cfbf_header + b"WordDocument\x00\x00" + (b"\x00" * 100) + stream_content + (b"\x00" * 200)

    with open(doc_path, "wb") as f:
        f.write(doc_bytes)
    print(f"Generated {doc_path}")


def generate_xls():
    xls_path = FIXTURES_DIR / "sample.xls"
    # Generate legacy XLS using openpyxl or copy if possible, or build basic BIFF8 stream
    # Note: openpyxl writes xlsx. For testing xlrd, we can generate a simple BIFF8 or use a synthetic CFBF with Workbook stream
    cfbf_header = b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1" + (b"\x00" * 504)
    workbook_stream = b"Workbook\x00\x00" + b"\x09\x08\x10\x00\x00\x06\x05\x00" + (b"\x00" * 500)
    with open(xls_path, "wb") as f:
        f.write(cfbf_header + workbook_stream)
    print(f"Generated {xls_path}")


def generate_edge_cases():
    # 1. Empty file
    with open(FIXTURES_DIR / "empty.txt", "w") as f:
        pass

    # 2. Corrupted PDF
    with open(FIXTURES_DIR / "corrupted.pdf", "wb") as f:
        f.write(b"%PDF-1.4 corrupted garbage binary bytes without EOF markers")

    # 3. XXE Attack Payload
    xxe_content = """<?xml version="1.0" encoding="ISO-8859-1"?>
<!DOCTYPE foo [
  <!ELEMENT foo ANY >
  <!ENTITY xxe SYSTEM "file:///etc/passwd" >]>
<foo>&xxe;</foo>
"""
    with open(FIXTURES_DIR / "xxe_attack.xml", "w") as f:
        f.write(xxe_content)

    print("Generated security edge case fixtures.")


def main():
    generate_pdf()
    generate_docx()
    generate_pptx()
    generate_xlsx()
    generate_csv_and_tsv()
    generate_txt_and_md()
    generate_json_and_xml()
    generate_html()
    generate_epub()
    generate_doc()
    generate_xls()
    generate_edge_cases()
    print("All fixtures generated successfully!")


if __name__ == "__main__":
    main()
