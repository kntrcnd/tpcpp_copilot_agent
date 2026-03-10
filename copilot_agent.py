import requests
import json
import time
import html
import os
import re
from datetime import datetime
from urllib.parse import quote
from dotenv import load_dotenv

# ---------------- Load environment ----------------
load_dotenv()

SECRET = os.getenv("DIRECTLINE_SECRET")
USER_ID = os.getenv("USER_ID", "api-user")
BASE_URL = "https://directline.botframework.com/v3/directline"

# ---------------- Globals ----------------
conversation_id = None
watermark = None
response_buffer = ""
last_activity_time = time.time()
continue_attempts = 0
MAX_CONTINUE = 20
FINISHED = False
first_response_received = False

OUTPUT_ROOT = r"D:\Projects\GitHub\tpcpp_copilot_agent\test_output\JSON"
OUTPUT_ROOT_1 = r"D:\Projects\GitHub\tpcpp_copilot_agent\test_output\SGML"
processing_time_folder = r"D:\Projects\TPCPP\Processing Time"

os.makedirs(OUTPUT_ROOT, exist_ok=True)
os.makedirs(OUTPUT_ROOT_1, exist_ok=True)
os.makedirs(processing_time_folder, exist_ok=True)

# ---------------- Copilot functions ----------------
def start_conversation():
    global conversation_id
    res = requests.post(
        f"{BASE_URL}/conversations",
        headers={"Authorization": f"Bearer {SECRET}"}
    )
    res.raise_for_status()
    conversation_id = res.json()["conversationId"]
    print("Conversation started:", conversation_id)

def send_message(text, attachment_url=None):
    url = f"{BASE_URL}/conversations/{conversation_id}/activities"
    payload = {
        "type": "message",
        "from": {"id": USER_ID},
        "text": text
    }
    if attachment_url:
        payload["attachments"] = [
            {
                "contentType": "application/pdf",
                "contentUrl": attachment_url,
                "name": "input.pdf"
            }
        ]
    res = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {SECRET}",
            "Content-Type": "application/json"
        },
        json=payload
    )
    res.raise_for_status()

def clean_json_text(raw_text):
    # Remove line comments and code fences
    text_no_comments = re.sub(r'//.*', '', raw_text)
    text_no_comments = re.sub(r'```json|```', '', text_no_comments)
    return text_no_comments.strip()

def is_json_complete(text):
    try:
        json.loads(text)
        return True
    except json.JSONDecodeError:
        return False

def poll_messages():
    global watermark, response_buffer, last_activity_time, FINISHED, first_response_received
    url = f"{BASE_URL}/conversations/{conversation_id}/activities"
    if watermark:
        url += f"?watermark={watermark}"
    res = requests.get(url, headers={"Authorization": f"Bearer {SECRET}"})
    res.raise_for_status()
    data = res.json()
    watermark = data.get("watermark")
    activities = data.get("activities", [])

    for act in activities:
        if act.get("type") != "message":
            continue
        if act.get("from", {}).get("id") == USER_ID:
            continue
        text = act.get("text")
        if not text:
            continue
        if not first_response_received:
            first_response_received = True
            print("\nProcessing first partial JSON...\n")
        response_buffer += text
        last_activity_time = time.time()
        if is_json_complete(response_buffer):
            FINISHED = True

def monitor_continue():
    global continue_attempts, last_activity_time, FINISHED, response_buffer

    idle = time.time() - last_activity_time

    if idle > 10 and not FINISHED:
        buffer_lower = response_buffer.lower()
        truncated = (
            "continues for pages" in buffer_lower
            or "remaining pages" in buffer_lower
            or "same detailed structure" in buffer_lower
        )

        if not is_json_complete(response_buffer) or truncated:
            if continue_attempts < MAX_CONTINUE:
                continue_attempts += 1
                print(f"Sending Continue #{continue_attempts}")
                send_message(
                    "CONTINUE the JSON exactly where it stopped. "
                    "Do not summarize. Do not describe remaining pages. "
                    "Output only valid JSON."
                )
                last_activity_time = time.time()
            else:
                print("Max Continue attempts reached.")
                FINISHED = True
        else:
            FINISHED = True

def convert_table_to_sgml(table_block: dict) -> str:
    """
    Converts a table block into SGMLTBL structure.
    """
 
    rows = table_block.get("rows", [])
    if not rows:
        return ""
 
    # Determine max column count
    max_cols = 0
    for row in rows:
        col_count = sum(cell.get("colspan", 1) for cell in row.get("cells", []))
        max_cols = max(max_cols, col_count)
 
    # Split header vs body
    header_rows = []
    body_rows = []
 
    for row in rows:
        cells = row.get("cells", [])
        if any(cell.get("is_header") for cell in cells):
            header_rows.append(row)
        else:
            body_rows.append(row)
 
    output = []
    output.append("<P1><TABLE><SGMLTBL>")
 
    # -------------------------
    # HEADER
    # -------------------------
    if header_rows:
        output.append('<TBLHEAD TBLWD="600">')
        output.append('<TBLCDEFS COLSEP="VSINGLE" HALIGN="CENTER" CHARPOS="75%" TOPSEP="HSINGLE">')
 
        # Column definitions (equal width percent)
        percent = int(100 / max_cols)
        for _ in range(max_cols):
            output.append(f'<TBLCDEF COLWD="{percent}" TBLUNITS="PERCENT">')
 
        output.append("</TBLCDEFS>")
        output.append('<TBLROWS ROWSEP="HSINGLE" VALIGN="TOP" LEFTSEP="VSINGLE">')
 
        for row in header_rows:
            output.append("<TBLROW>")
            col_index = 1
            for cell in row.get("cells", []):
                text = cell.get("text", "")
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

def convert_json_to_sgml_strict(json_file, pdf_name):
    with open(json_file, "r", encoding="utf-8") as f:
        compiled_json = json.load(f)

    # ------------------ Helper: tag block ------------------
    def tag_text(block_type: str, text: str, level=None) -> str:
        if not text:
            return ""
        stripped = text.strip()
        if block_type == "heading":
            if level:
                return f"<BLOCK{level}><TI>{stripped}</TI>"
            return f"<TI>{stripped}</TI>"
        elif block_type == "paragraph":
            return f"<P>{stripped}</P>"
        elif block_type == "list":
            return f"<ITEM><P>{stripped}</P></ITEM>"
        elif block_type == "address_block":
            return f"<ADDRESS><LINE>{stripped}</LINE></ADDRESS>"
        elif block_type == "paragraph_lines":
            return f"<PARAGRAPH><LINE>{stripped}</LINE></PARAGRAPH>"
        else:
            return f"<P>{stripped}</P>"

    # ------------------ Build SGML ------------------
    sgml_lines = []

    pages = compiled_json.get("document", {}).get("pages", [])
    for page in pages:
        page_num = page.get("page_number", 0)
        sgml_lines.append(f"<N>{page_num}</N>")
        pdf_filename = f"{pdf_name}P{page_num}.PDF"
        sgml_lines.append(f'<GRAPHIC FILENAME="{pdf_filename}"><LINKTEXT>Original Image of this Document (PDF)</LINKTEXT></GRAPHIC>')
        sgml_lines.append("<FREEFORM>")

        blocks = page.get("blocks", [])
        for block in blocks:
            b_type = block.get("block_type")

            # heading
            if b_type == "heading":
                level = block.get("level", "")
                for span in block.get("spans", []):
                    text = span.get("text", "")
                    sgml_lines.append(tag_text("heading", text, level))

            # paragraph
            elif b_type == "paragraph":
                for span in block.get("spans", []):
                    text = span.get("text", "")
                    sgml_lines.append(tag_text("paragraph", text))

            # list
            elif b_type == "list":
                for item in block.get("items", []):
                    # item may have spans
                    if "spans" in item:
                        for span in item["spans"]:
                            text = span.get("text", "")
                            sgml_lines.append(tag_text("list", text))
                    else:
                        text = item.get("text", "")
                        sgml_lines.append(tag_text("list", text))

            # paragraph with lines / address_block
            elif b_type in ("paragraph_lines", "address_block"):
                for line in block.get("lines", []):
                    text = line.get("text", "")
                    sgml_lines.append(tag_text(b_type, text))

            # table
            elif b_type == "table":
                table_sgml = convert_table_to_sgml(block)
                if table_sgml:
                    sgml_lines.append(table_sgml)

            else:
                print(f"Warning: Unsupported block_type '{b_type}' ignored.")

        sgml_lines.append("</FREEFORM>")

    # ------------------ Save SGML ------------------
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    sgml_file = os.path.join(OUTPUT_ROOT_1, f"{pdf_name}_{timestamp}.sgml")
    os.makedirs(os.path.dirname(sgml_file), exist_ok=True)
    with open(sgml_file, "w", encoding="utf-8") as f:
        f.write("\n".join(sgml_lines))

    print(f"SGML saved -> {sgml_file}")

# ---------------- GitHub PDF fetch ----------------
username = "kntrcnd"
repo = "tpcpp_copilot_agent"
branch = "main"
folder_path_base = "pdf/base"

api_url = f"https://api.github.com/repos/{username}/{repo}/contents/{folder_path_base}?ref={branch}"
response = requests.get(api_url)
response.raise_for_status()
files = response.json()
pdf_files = [f for f in files if f["name"].lower().endswith(".pdf")]

if not pdf_files:
    raise Exception("No PDFs found in GitHub folder.")
print(f"Found {len(pdf_files)} PDF(s) to process.")

# ---------------- Process each base PDF ----------------
for f in pdf_files:
    pdf_name = os.path.splitext(f["name"])[0]
    pdf_url = f"https://raw.githubusercontent.com/{username}/{repo}/{branch}/{folder_path_base}/{quote(f['name'])}"
    print(f"\nSending PDF: {pdf_url}")

    # ---------------- Start timer ----------------
    current_time = datetime.now()

    response_buffer = ""
    FINISHED = False
    continue_attempts = 0
    last_activity_time = time.time()
    first_response_received = False

    start_conversation()
    send_message(
        "Extract this PDF into structured JSON. Return ONLY JSON.",
        pdf_url
    )

    while not FINISHED:
        poll_messages()
        monitor_continue()
        time.sleep(2)

    # ---------------- Clean and compile JSON ----------------
    cleaned_json = clean_json_text(response_buffer)

    # Extract all JSON objects from the response
    json_objects = []
    decoder = json.JSONDecoder()
    idx = 0

    while idx < len(cleaned_json):
        try:
            obj, end = decoder.raw_decode(cleaned_json[idx:])
            json_objects.append(obj)
            idx += end
        except json.JSONDecodeError:
            idx += 1

    if not json_objects:
        raise Exception("No valid JSON objects found in Copilot response.")

    # Compile into one document
    compiled_document = {
        "document": {
            "total_pages": 0,
            "pages": []
        }
    }

    for obj in json_objects:
        if isinstance(obj, dict) and "document" in obj:
            pages = obj["document"].get("pages", [])
            compiled_document["document"]["pages"].extend(pages)

    # Remove duplicate pages (Copilot sometimes repeats them)
    unique_pages = {}
    for page in compiled_document["document"]["pages"]:
        num = page.get("page_number")
        if num not in unique_pages:
            unique_pages[num] = page

    compiled_document["document"]["pages"] = sorted(
        unique_pages.values(),
        key=lambda x: x.get("page_number", 0)
    )

    compiled_document["document"]["total_pages"] = len(compiled_document["document"]["pages"])

    # ---------------- Save compiled JSON ----------------
    pdf_folder = os.path.join(OUTPUT_ROOT, pdf_name)
    os.makedirs(pdf_folder, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_file = os.path.join(pdf_folder, f"{pdf_name}_compiled_{timestamp}.json")
    with open(output_file, "w", encoding="utf-8") as f_out:
        json.dump(compiled_document, f_out, indent=2)

    print(f"\nCompiled JSON saved -> {output_file}")

    convert_json_to_sgml_strict(output_file, pdf_name)

    # ---------------- End timer ----------------
    end_time = datetime.now()
    elapsed_seconds = (end_time - current_time).total_seconds()
    elapsed_minutes = elapsed_seconds / 60

    # --- Print timing info to console ---
    print("\n--- Processing finished ---")
    print(f"Started: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Ended:   {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Elapsed Time: {elapsed_minutes:.2f} minutes ({elapsed_seconds:.0f} seconds)")

    # --- Save processing time JSON ---
    timer_data = {
        "pdf_name": pdf_name,
        "started_at": current_time.strftime('%Y-%m-%d %H:%M:%S'),
        "ended_at": end_time.strftime('%Y-%m-%d %H:%M:%S'),
        "elapsed_minutes": round(elapsed_minutes, 2),
        "elapsed_seconds": int(elapsed_seconds)
    }

    timestamp_str = end_time.strftime("%Y-%m-%d_%H-%M-%S")
    timer_file_name = f"{pdf_name}_processing_time_{timestamp_str}.json"
    timer_file_path = os.path.join(processing_time_folder, timer_file_name)

    with open(timer_file_path, "w", encoding="utf-8") as f_timer:
        json.dump(timer_data, f_timer, indent=2)

    print(f"Processing time JSON saved...")