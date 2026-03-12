import json
from pathlib import Path
import re
import html

# ------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------

INPUT_PATH = Path(r"D:\Projects\GitHub\tpcpp_copilot_agent\test_output\JSON\2020Ont15279-1-Affidavit of Bruce Arnott\2020Ont15279-1-Affidavit of Bruce Arnott_compiled_2026-03-12_14-07-53.json")
OUTPUT_PATH = Path(r"D:\Projects\GitHub\tpcpp_copilot_agent\test_output\SGML\script\output.sgml")

# ------------------------------------------------------------
# UTILS
# ------------------------------------------------------------

def escape_text(text: str) -> str:
    """Escapes text for SGML-safe output."""
    if not text:
        return ""
    escaped = html.escape(text, quote=False)
    escaped = escaped.encode("ascii", "xmlcharrefreplace").decode()
    return escaped

# ------------------------------------------------------------
# STEP 1 — COMPILE JSON STREAM
# ------------------------------------------------------------

def compile_json_stream(raw_text: str) -> dict:
    obj = json.loads(raw_text)

    # Handle top-level "pages" or nested "document.pages"
    pages = obj.get("pages") or obj.get("document", {}).get("pages", [])

    all_blocks = []

    for page in pages:
        for block in page.get("blocks", []):
            # Flatten lines into spans if missing
            if "lines" in block:
                spans = []
                for line in block["lines"]:
                    line_spans = []
                    for span in line.get("spans", []):
                        if "text" in span and span["text"]:
                            line_spans.append({"text": span["text"]})
                    if line_spans:
                        line["spans"] = line_spans
                # Keep lines intact
            else:
                # If no lines but spans exist, create a dummy line for consistency
                if "spans" in block and block["spans"]:
                    block["lines"] = [{"spans": block["spans"]}]

            # Normalize block type
            if block.get("block_type") in ("footnotes",):
                block["block_type"] = "paragraph"

            if block.get("spans") or block.get("lines") or block.get("items"):
                all_blocks.append(block)

    print(f"Number of blocks to convert: {len(all_blocks)}")
    return {"blocks": all_blocks}

# ------------------------------------------------------------
# STEP 2 — TABLE CONVERSION (KEPT FROM ORIGINAL)
# ------------------------------------------------------------

def convert_table_to_sgml(table_block: dict) -> str:
    """Converts table block into SGMLTBL structure."""
    rows = table_block.get("rows", [])
    if not rows:
        return ""

    max_cols = 0
    for row in rows:
        col_count = sum(cell.get("colspan", 1) for cell in row.get("cells", []))
        max_cols = max(max_cols, col_count)

    header_rows = []
    body_rows = []
    for row in rows:
        cells = row.get("cells", [])
        if any(cell.get("is_header") for cell in cells):
            header_rows.append(row)
        else:
            body_rows.append(row)

    output = ["<P1><TABLE><SGMLTBL>"]

    if header_rows:
        output.append('<TBLHEAD TBLWD="600">')
        output.append('<TBLCDEFS COLSEP="VSINGLE" HALIGN="CENTER" CHARPOS="75%" TOPSEP="HSINGLE">')
        percent = int(100 / max_cols)
        for _ in range(max_cols):
            output.append(f'<TBLCDEF COLWD="{percent}" TBLUNITS="PERCENT">')
        output.append("</TBLCDEFS>")
        output.append('<TBLROWS ROWSEP="HSINGLE" VALIGN="TOP" LEFTSEP="VSINGLE">')

        for row in header_rows:
            output.append("<TBLROW>")
            col_index = 1
            for cell in row.get("cells", []):
                text = escape_text(cell.get("text", ""))
                colspan = cell.get("colspan", 1)
                output.append(
                    f'<TBLCELL COLSTART="{col_index}"'
                    + (f' COLSPAN="{colspan}"' if colspan > 1 else "")
                    + f'>{text}</TBLCELL>'
                )
                col_index += colspan
            output.append("</TBLROW>")

        output.append("</TBLCROWS>")
        output.append("</TBLHEAD>")

    if body_rows:
        output.append('<TBLBODY TBLWD="600">')
        output.append('<TBLCDEFS COLSEP="VSINGLE" HALIGN="LEFT" CHARPOS="75%" TOPSEP="HSINGLE">')
        percent = int(100 / max_cols)
        for _ in range(max_cols):
            output.append(f'<TBLCDEF COLWD="{percent}" TBLUNITS="PERCENT">')
        output.append("</TBLCDEFS>")
        output.append('<TBLROWS ROWSEP="HSINGLE" VALIGN="TOP" LEFTSEP="VSINGLE">')

        for row in body_rows:
            output.append("<TBLROW>")
            col_index = 1
            for cell in row.get("cells", []):
                text = escape_text(cell.get("text", ""))
                colspan = cell.get("colspan", 1)
                output.append(
                    f'<TBLCELL COLSTART="{col_index}"'
                    + (f' COLSPAN="{colspan}"' if colspan > 1 else "")
                    + f'>{text}</TBLCELL>'
                )
                col_index += colspan
            output.append("</TBLROW>")

        output.append("</TBLCROWS>")
        output.append("</TBLBODY>")

    output.append("</SGMLTBL></TABLE></P1>")

    return "\n".join(output)

# ------------------------------------------------------------
# STEP 3 — SGML CONVERSION
# ------------------------------------------------------------

def tag_block(block: dict) -> str:
    """Converts a block dict to SGML according to strict rules."""
    b_type = block.get("block_type")
    level = block.get("level", 1)  # default heading level
    sgml_parts = []

    if b_type == "heading":
        text = " ".join(span.get("text", "") for span in block.get("spans", []))
        if text.strip():
            sgml_parts.append(f"<BLOCK{level}><TI>{escape_text(text.strip())}</TI>")

    elif b_type == "paragraph":
        lines = block.get("lines", [])
        if lines:
            sgml_parts.append("<PARAGRAPH>")
            for line in lines:
                line_text = " ".join(span.get("text", "") for span in line.get("spans", []))
                if line_text.strip():
                    sgml_parts.append(f"<LINE>{escape_text(line_text.strip())}</LINE>")
            sgml_parts.append("</PARAGRAPH>")
        else:
            for span in block.get("spans", []):
                text = span.get("text")
                if text:
                    sgml_parts.append(f"<P>{escape_text(text.strip())}</P>")

    elif b_type == "list":
        items = block.get("items", [])
        for item in items:
            text = item.get("text", "")
            if text.strip():
                sgml_parts.append(f"<ITEM><P>{escape_text(text.strip())}</P></ITEM>")

    elif b_type == "address_block":
        sgml_parts.append("<ADDRESS>")
        lines = block.get("lines", [])
        for line in lines:
            line_text = " ".join(span.get("text", "") for span in line.get("spans", []))
            if line_text.strip():
                sgml_parts.append(f"<LINE>{escape_text(line_text.strip())}</LINE>")
        sgml_parts.append("</ADDRESS>")

    elif b_type == "table":
        table_sgml = convert_table_to_sgml(block)
        if table_sgml:
            sgml_parts.append(table_sgml)

    else:
        print(f"Warning: Unsupported block_type '{b_type}' ignored.")

    return "\n".join(sgml_parts)

def convert_compiled_to_sgml(compiled_json: dict) -> str:
    output_lines = []
    blocks = compiled_json.get("blocks", [])

    if not isinstance(blocks, list):
        raise ValueError("Invalid compiled JSON: 'blocks' must be a list.")

    print(f"Number of blocks to convert: {len(blocks)}")

    for i, block in enumerate(blocks):
        print(f"Processing block {i}: type={block.get('block_type')}, keys={list(block.keys())}")
        sgml_block = tag_block(block)
        if sgml_block:
            output_lines.append(sgml_block)

    return "\n".join(output_lines)

# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------

def main():
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Input file not found: {INPUT_PATH}")

    raw_text = INPUT_PATH.read_text(encoding="utf-8")

    print("Compiling JSON stream...")
    compiled_json = compile_json_stream(raw_text)

    print("Converting to SGML...")
    sgml_output = convert_compiled_to_sgml(compiled_json)

    if not sgml_output.strip():
        raise ValueError("SGML output is empty. Check JSON structure.")

    OUTPUT_PATH.write_text(sgml_output, encoding="utf-8")

    print("SGML conversion completed successfully.")
    print(f"Output written to: {OUTPUT_PATH}")

# ------------------------------------------------------------
# ENTRY
# ------------------------------------------------------------

if __name__ == "__main__":
    main()