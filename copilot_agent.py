import requests
import json
import time
import html
import os
import re
from datetime import datetime
from urllib.parse import quote
from pathlib import Path
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

OUTPUT_ROOT_JSON = r"D:\Projects\GitHub\tpcpp_copilot_agent\test_output\JSON"
OUTPUT_ROOT_SGML = r"D:\Projects\GitHub\tpcpp_copilot_agent\test_output\SGML"
processing_time_folder = r"D:\Projects\TPCPP\Processing Time"

os.makedirs(OUTPUT_ROOT_JSON, exist_ok=True)
os.makedirs(OUTPUT_ROOT_SGML, exist_ok=True)
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
    payload = {"type": "message", "from": {"id": USER_ID}, "text": text}
    if attachment_url:
        payload["attachments"] = [{
            "contentType": "application/pdf",
            "contentUrl": attachment_url,
            "name": "input.pdf"
        }]
    res = requests.post(
        url,
        headers={"Authorization": f"Bearer {SECRET}", "Content-Type": "application/json"},
        json=payload
    )
    res.raise_for_status()

def clean_json_text(raw_text):
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

# ---------------- JSON → SGML functions ----------------
def escape_text(text: str) -> str:
    if not text:
        return ""
    escaped = html.escape(text, quote=False)
    return escaped.encode("ascii", "xmlcharrefreplace").decode()

def compile_json_stream(raw_text: str) -> dict:
    obj = json.loads(raw_text)
    pages = obj.get("pages") or obj.get("document", {}).get("pages", [])
    all_blocks = []
    for page in pages:
        for block in page.get("blocks", []):
            if "lines" in block:
                for line in block["lines"]:
                    spans = [{"text": s["text"]} for s in line.get("spans", []) if s.get("text")]
                    if spans:
                        line["spans"] = spans
            elif "spans" in block and block["spans"]:
                block["lines"] = [{"spans": block["spans"]}]
            if block.get("block_type") == "footnotes":
                block["block_type"] = "paragraph"
            if block.get("spans") or block.get("lines") or block.get("items"):
                all_blocks.append(block)
    print(f"Number of blocks to convert: {len(all_blocks)}")
    return {"blocks": all_blocks}

def convert_table_to_sgml(table_block):
    rows = table_block.get("rows", [])
    if not rows:
        return ""
    output = ["<TABLE>"]
    for row in rows:
        output.append("<ROW>")
        for cell in row.get("cells", []):
            text = escape_text(cell.get("text", ""))
            output.append(f"<CELL>{text}</CELL>")
        output.append("</ROW>")
    output.append("</TABLE>")
    return "\n".join(output)

def render_spans_to_sgml_text(spans):
    parts = []
    for sp in spans or []:
        txt = escape_text(sp.get("text", ""))
        styles = sp.get("styles", [])
        if isinstance(styles, list) and "italic" in [s.lower() for s in styles]:
            parts.append("&lt;EM&gt;" + txt + "&lt;/EM&gt;")
        else:
            parts.append(txt)
    return "".join(parts).strip()

def tag_block(block):
    b_type = block.get("block_type")
    level = block.get("level", 1)
    parts = []

    if b_type == "heading":
        text = render_spans_to_sgml_text(block.get("spans"))
        if text:
            parts.append(f"<BLOCK{level}><TI>{text}</TI>")

    elif b_type == "paragraph":
        lines = block.get("lines", [])
        if lines:
            parts.append("<PARAGRAPH>")
            for line in lines:
                text = render_spans_to_sgml_text(line.get("spans"))
                if text:
                    parts.append(f"<LINE>{text}</LINE>")
            parts.append("</PARAGRAPH>")

    elif b_type == "list":
        for item in block.get("items", []):
            text = escape_text(item.get("text", ""))
            if text:
                parts.append(f"<ITEM><P>{text}</P></ITEM>")

    elif b_type == "address_block":
        parts.append("<ADDRESS>")
        for line in block.get("lines", []):
            text = render_spans_to_sgml_text(line.get("spans"))
            if text:
                parts.append(f"<LINE>{text}</LINE>")
        parts.append("</ADDRESS>")

    elif b_type == "party_block":
        lines = block.get("lines") or ([{"spans": block.get("spans")}] if block.get("spans") else [])
        tag_map = {"label":"LINE","party":"PARTY","party_role":"PARTYROLE","connector":"CONNECTOR","act_under":"ACTUNDER"}
        parts.append("&lt;PARTYBLOCK&gt;")
        for line in lines:
            line_type = (line.get("line_type") or "").lower()
            tag = tag_map.get(line_type, "LINE")
            text_sgml = render_spans_to_sgml_text(line.get("spans"))
            if text_sgml:
                parts.append(f"&lt;{tag}&gt;{text_sgml}&lt;/{tag}&gt;")
        parts.append("&lt;/PARTYBLOCK&gt;")

    elif b_type == "table":
        tbl = convert_table_to_sgml(block)
        if tbl:
            parts.append(tbl)
    else:
        print(f"Warning: unsupported block type {b_type}")

    return "\n".join(parts)

def convert_compiled_to_sgml(compiled_json):
    blocks = compiled_json.get("blocks", [])
    output = []
    for i, block in enumerate(blocks):
        print(f"Processing block {i}: {block.get('block_type')}")
        sgml = tag_block(block)
        if sgml:
            output.append(sgml)
    return "\n".join(output)

def convert_json_to_sgml_strict(json_file, pdf_name, output_root):
    json_file = Path(json_file)
    raw_text = json_file.read_text(encoding="utf-8")
    print("Compiling JSON stream...")
    compiled = compile_json_stream(raw_text)
    print("Converting to SGML...")
    sgml_output = convert_compiled_to_sgml(compiled)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_path = Path(output_root) / f"{pdf_name}_{timestamp}.sgml"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(sgml_output, encoding="utf-8")
    print("SGML written to:", output_path)
    return sgml_output

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

# ---------------- Process PDFs ----------------
for f in pdf_files:
    pdf_name = os.path.splitext(f["name"])[0]
    pdf_url = f"https://raw.githubusercontent.com/{username}/{repo}/{branch}/{folder_path_base}/{quote(f['name'])}"
    print(f"\nProcessing: {pdf_name}")

    # Reset globals
    response_buffer = ""
    FINISHED = False
    continue_attempts = 0
    first_response_received = False
    last_activity_time = time.time()

    start_total_time = datetime.now()
    start_conversation()
    send_message("Extract this PDF into structured JSON. Return ONLY JSON.", pdf_url)

    # Receive JSON stream
    while not FINISHED:
        poll_messages()
        monitor_continue()
        time.sleep(2)

    # ---------------- JSON compilation ----------------
    start_json_time = datetime.now()
    cleaned_json = clean_json_text(response_buffer)
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
    compiled_document = {"document": {"total_pages": 0, "pages": []}}
    for obj in json_objects:
        if isinstance(obj, dict) and "document" in obj:
            pages = obj["document"].get("pages", [])
            compiled_document["document"]["pages"].extend(pages)
    unique_pages = {}
    for page in compiled_document["document"]["pages"]:
        num = page.get("page_number")
        if num not in unique_pages:
            unique_pages[num] = page
    compiled_document["document"]["pages"] = sorted(
        unique_pages.values(), key=lambda x: x.get("page_number", 0)
    )
    compiled_document["document"]["total_pages"] = len(compiled_document["document"]["pages"])
    pdf_folder = os.path.join(OUTPUT_ROOT_JSON, pdf_name)
    os.makedirs(pdf_folder, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    json_file = os.path.join(pdf_folder, f"{pdf_name}_compiled_{timestamp}.json")
    with open(json_file, "w", encoding="utf-8") as f_out:
        json.dump(compiled_document, f_out, indent=2)
    end_json_time = datetime.now()
    json_elapsed = (end_json_time - start_json_time).total_seconds()
    print(f"Compiled JSON saved -> {json_file}")
    print(f"JSON compilation time: {json_elapsed:.2f} seconds")

    # ---------------- SGML conversion ----------------
    start_sgml_time = datetime.now()
    sgml_text = convert_json_to_sgml_strict(json_file, pdf_name, OUTPUT_ROOT_SGML)
    end_sgml_time = datetime.now()
    sgml_elapsed = (end_sgml_time - start_sgml_time).total_seconds()
    print(f"SGML conversion time: {sgml_elapsed:.2f} seconds")

    # ---------------- Total processing time ----------------
    end_total_time = datetime.now()
    total_elapsed = (end_total_time - start_total_time).total_seconds()
    print(f"Total processing time: {total_elapsed:.2f} seconds")

    # ---------------- Save processing time JSON ----------------
    timer_data = {
        "pdf_name": pdf_name,
        "json_compilation_seconds": int(json_elapsed),
        "sgml_conversion_seconds": int(sgml_elapsed),
        "total_seconds": int(total_elapsed),
        "started_at": start_total_time.strftime("%Y-%m-%d %H:%M:%S"),
        "ended_at": end_total_time.strftime("%Y-%m-%d %H:%M:%S")
    }
    timer_file_name = f"{pdf_name}_processing_time_{timestamp}.json"
    timer_file_path = os.path.join(processing_time_folder, timer_file_name)
    with open(timer_file_path, "w", encoding="utf-8") as f_timer:
        json.dump(timer_data, f_timer, indent=2)
    print(f"Processing time JSON saved -> {timer_file_path}")