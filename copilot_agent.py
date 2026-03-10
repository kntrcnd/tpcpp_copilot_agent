import requests
import json
import time
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

def json_to_sgml(json_file, pdf_name):
    """Convert Copilot JSON into fully structured SGML dynamically."""
    os.makedirs(OUTPUT_ROOT_1, exist_ok=True)
    
    # Extract PDF ID for filenames
    pdf_id = os.path.splitext(pdf_name)[0]

    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    sgml_lines = []

    # Start PLEADING root
    sgml_lines.append(f'<PLEADING LABEL="Pleading" TYPE="PLEADING" LANG="EN">')

    # Pages
    pages = data.get("document", {}).get("pages", [])
    for page in pages:
        page_num = page.get("page_number", "")
        sgml_lines.append(f"<N>{page_num}</N>")
        sgml_lines.append(f'<GRAPHIC FILENAME="{pdf_id}P{page_num}.PDF"><LINKTEXT>Original Image of this Document (PDF)</LINKTEXT></GRAPHIC>')

        # Metadata fields at page level
        meta_fields = ["docti", "subject", "date", "caseref", "docket", "partyblock", "counselblock"]
        for field in meta_fields:
            value = page.get(field)
            if value:
                if isinstance(value, list):
                    for v in value:
                        sgml_lines.append(convert_meta_field(field, v))
                else:
                    sgml_lines.append(convert_meta_field(field, value))

        # Freeform blocks
        sgml_lines.append("<FREEFORM>")
        blocks = page.get("blocks", [])
        for block in blocks:
            sgml_lines.extend(convert_block(block))
        sgml_lines.append("</FREEFORM>")

    sgml_lines.append("</PLEADING>")

    # Save SGML
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    sgml_file = os.path.join(OUTPUT_ROOT_1, f"{pdf_id}_{timestamp}.sgml")
    with open(sgml_file, "w", encoding="utf-8") as f:
        f.write("\n".join(sgml_lines))
    
    print(f"SGML saved -> {sgml_file}")


def convert_meta_field(field_name, value):
    """Convert metadata to SGML tags dynamically."""
    if field_name.lower() == "docti":
        return f"<DOCTI>{value}</DOCTI>"
    elif field_name.lower() == "subject":
        return f"<SUBJECT>{value}</SUBJECT>"
    elif field_name.lower() == "date":
        ymd = value.get("YYYYMMDD") if isinstance(value, dict) else ""
        label = value.get("LABEL") if isinstance(value, dict) else ""
        text = value.get("text") if isinstance(value, dict) else str(value)
        return f'<DATE YYYYMMDD="{ymd}" LABEL="{label}">{text}</DATE>'
    elif field_name.lower() == "caseref":
        # CASEREF may have multiple subfields
        parts = []
        if isinstance(value, dict):
            soc = value.get("SOC")
            cite = value.get("CITE")
            correlat = value.get("CORRELAT")
            parts.append(f"<SOC>{soc}</SOC>" if soc else "")
            parts.append(f"<CITE>{cite}</CITE>" if cite else "")
            if correlat:
                parts.append("<CORRELAT>")
                c_cite = correlat.get("CITE")
                if c_cite:
                    parts.append(f"<CITE>{c_cite}</CITE>")
                parts.append("</CORRELAT>")
        return f"<CASEREF>{''.join(parts)}</CASEREF>"
    elif field_name.lower() == "docket":
        if isinstance(value, dict):
            label = value.get("LABEL", "")
            text = value.get("text", "")
            return f'<DOCKET LABEL="{label}">{text}</DOCKET>'
        else:
            return f"<DOCKET>{value}</DOCKET>"
    elif field_name.lower() in ["partyblock", "counselblock"]:
        # Simple placeholder, you can extend to parse nested parties/counsel
        return f"<{field_name.upper()}>{json.dumps(value)}</{field_name.upper()}>"
    else:
        return f"<{field_name.upper()}>{value}</{field_name.upper()}>"


def convert_block(block):
    """Recursively convert nested blocks to SGML."""
    lines = []
    b_type = block.get("b_type", "paragraph")
    
    # Get text content
    texts = []
    if "spans" in block:
        texts = [s.get("text", "").strip() for s in block["spans"]]
    elif "text" in block:
        texts = [block["text"].strip()]

    # Determine block level for nested headings
    level = block.get("level_num", 1)
    
    if b_type.lower() == "paragraph":
        for t in texts:
            if t:
                lines.append(f"<P>{t}</P>")
    elif b_type.lower() == "heading":
        for t in texts:
            if t:
                lines.append(f"<BLOCK{level}><TI>{t}</TI>")
                # Handle nested children recursively
                children = block.get("children", [])
                for child in children:
                    lines.extend(convert_block(child))
                lines.append(f"</BLOCK{level}>")
    elif b_type.lower() == "list":
        for t in texts:
            if t:
                lines.append(f"<ITEM><P>{t}</P></ITEM>")
    
    # Recursively handle children if not heading
    if b_type.lower() != "heading":
        for child in block.get("children", []):
            lines.extend(convert_block(child))
    
    return lines

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

    convert_json_to_sgml(output_file, pdf_name)

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