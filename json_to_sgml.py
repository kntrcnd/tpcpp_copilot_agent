import json
from pathlib import Path
import re
import html

# ------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------

INPUT_PATH = Path(r"D:\Projects\GitHub\tpcpp_copilot_agent\test_output\JSON\2024NS318-17-Letterhead Factum\2024NS318-17-Letterhead Factum_compiled_2026-03-09_19-34-07.json")
OUTPUT_PATH = Path(r"D:\Projects\GitHub\tpcpp_copilot_agent\test_output\SGML\script\output.sgml")

# ------------------------------------------------------------
# STEP 1 — COMPILE CONCATENATED JSON OBJECTS
# ------------------------------------------------------------

def compile_json_stream(raw_text: str) -> dict:
    """Compiles concatenated JSON objects and flattens all blocks into a single list."""
    decoder = json.JSONDecoder()
    idx = 0
    length = len(raw_text)
    all_blocks = []

    while idx < length:
        while idx < length and raw_text[idx].isspace():
            idx += 1
        if idx >= length:
            break

        obj, next_idx = decoder.raw_decode(raw_text, idx)
        idx = next_idx

        pages = obj.get("pages", [])
        if not isinstance(pages, list):
            raise ValueError("Invalid structure: 'pages' must be a list.")

        for page in pages:
            blocks = page.get("blocks", [])
            if not isinstance(blocks, list):
                raise ValueError("Invalid structure: 'blocks' must be a list.")

            # Normalize blocks to always have "spans"
            for block in blocks:
                if "text" in block and "spans" not in block:
                    block["spans"] = [{"text": block["text"]}]
                if block.get("block_type") == "list" and "items" not in block:
                    # fallback: treat spans as list items
                    items = []
                    for span in block.get("spans", []):
                        if "text" in span:
                            items.append({"text": span["text"]})
                    block["items"] = items
                all_blocks.append(block)

    return {"blocks": all_blocks}

# ------------------------------------------------------------
# TAGGING RULES
# ------------------------------------------------------------

def tag_text(block_type: str, text: str) -> str:
    """Maps block_type to SGML tag. Detects 4-digit year headings."""
    if not text:
        return ""
    stripped = text.strip()

    if block_type == "heading":
        if re.fullmatch(r"\d{4}", stripped):
            return f"<DATE>{stripped}</DATE>"
        return f"<TI>{stripped}</TI>"

    if block_type == "paragraph":
        return f"<P>{stripped}</P>"

    if block_type == "list":
        return f"<ITEM><P>{stripped}</P></ITEM>"

    return ""

def escape_text(text: str) -> str:
    """Escapes text for SGML-safe output."""
    if not text:
        return ""
    escaped = html.escape(text, quote=False)
    escaped = escaped.encode("ascii", "xmlcharrefreplace").decode()
    return escaped

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

        output.append("</TBLROWS>")
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
# STEP 2 — CONVERT TO SGML
# ------------------------------------------------------------

def convert_compiled_to_sgml(compiled_json: dict) -> str:
    output_lines = []
    blocks = compiled_json.get("blocks", [])

    print(f"Number of blocks to convert: {len(blocks)}")

    if not isinstance(blocks, list):
        raise ValueError("Invalid compiled JSON: 'blocks' must be a list.")

    for i, block in enumerate(blocks):
        block_type = block.get("block_type")
        print(f"Processing block {i}: type={block_type}, keys={list(block.keys())}")

        if not block_type:
            continue

        if block_type in ("paragraph", "heading"):
            spans = block.get("spans", [])
            for span in spans:
                text = span.get("text") or span.get("Text")
                if text:
                    tagged = tag_text(block_type, text)
                    if tagged:
                        output_lines.append(tagged)

        elif block_type == "list":
            items = block.get("items", [])
            for item in items:
                text = item.get("text")
                if text:
                    tagged = tag_text("list", text)
                    if tagged:
                        output_lines.append(tagged)

        elif block_type == "table":
            table_sgml = convert_table_to_sgml(block)
            if table_sgml:
                output_lines.append(table_sgml)

        else:
            print(f"Warning: Unsupported block_type '{block_type}' ignored.")
            continue

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