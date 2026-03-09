import requests
import json
import time
import os
import re
from datetime import datetime
from urllib.parse import quote
from dotenv import load_dotenv

load_dotenv()

SECRET = os.getenv("DIRECTLINE_SECRET")
USER_ID = os.getenv("USER_ID", "api-user")
BASE_URL = "https://directline.botframework.com/v3/directline"
OUTPUT_ROOT = r"D:\Projects\GitHub\tpcpp_copilot_agent\test_output"
processing_time_folder = r"D:\Projects\TPCPP\Processing Time"

conversation_id = None
watermark = None
response_buffer = ""
last_activity_time = time.time()
continue_attempts = 0
MAX_CONTINUE = 20
FINISHED = False
first_response_received = False

os.makedirs(processing_time_folder, exist_ok=True)

# ---------------- Copilot communication functions ----------------

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
    # Remove comments // and code fences ```json ```
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
        truncated = ("continues for pages" in buffer_lower or
                     "remaining pages" in buffer_lower or
                     "same detailed structure" in buffer_lower)
        if not is_json_complete(response_buffer) or truncated:
            if continue_attempts < MAX_CONTINUE:
                continue_attempts += 1
                print(f"Sending Continue #{continue_attempts}")
                send_message("CONTINUE the JSON exactly where it stopped. Do not summarize. Output only JSON.")
                last_activity_time = time.time()
            else:
                print("Max Continue attempts reached.")
                FINISHED = True
        else:
            FINISHED = True

def natural_sort_key(s):
    """
    Splits a string into text and number parts so that 'Page-2' < 'Page-10'.
    """
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', s)]

# ---------------- GitHub recursive PDF fetch ----------------
def get_github_pdfs(user, repo, branch, path):
    pdf_list = []
    api_url = f"https://api.github.com/repos/{user}/{repo}/contents/{path}?ref={branch}"
    response = requests.get(api_url)
    response.raise_for_status()
    items = response.json()
    for item in items:
        if item["type"] == "file" and item["name"].lower().endswith(".pdf"):
            pdf_list.append({"name": item["name"], "path": path})
        elif item["type"] == "dir":
            pdf_list.extend(get_github_pdfs(user, repo, branch, item["path"]))
    return pdf_list

# ---------------- Main pipeline ----------------
username = "kntrcnd"
repo = "tpcpp_copilot_agent"
branch = "main"
folder_path_split = "pdf/split"  # root folder containing split PDF folders

os.makedirs(OUTPUT_ROOT, exist_ok=True)

# Fetch all PDFs recursively
pdf_files = get_github_pdfs(username, repo, branch, folder_path_split)
if not pdf_files:
    raise Exception("No PDFs found in GitHub folder/subfolders.")

# Group PDFs by base folder (assumes all splits are in one folder per base PDF)
from collections import defaultdict
pdf_groups = defaultdict(list)
for f in pdf_files:
    base_folder = f["path"].split("/")[-1]  # use last folder as base
    pdf_groups[base_folder].append(f)

# Process each group (all split pages for one base PDF)
for base_folder, pdf_list in pdf_groups.items():
    print(f"\nProcessing base PDF folder: {base_folder}")
    compiled_json = []

    # ---------------- Start timer ----------------
    current_time = datetime.now()

    # Sort pages naturally
    pdf_list.sort(key=lambda x: natural_sort_key(x["name"]))

    for page_index, f in enumerate(pdf_list, start=1):
        pdf_name = os.path.splitext(f["name"])[0]
        pdf_url = f"https://raw.githubusercontent.com/{username}/{repo}/{branch}/{quote(f['path'])}/{quote(f['name'])}"
        print(f"\nSending PDF {page_index}/{len(pdf_list)}: {pdf_url}")

        response_buffer = ""
        FINISHED = False
        continue_attempts = 0
        last_activity_time = time.time()
        first_response_received = False

        start_conversation()
        send_message("Extract this PDF into structured JSON. Return ONLY JSON.", pdf_url)

        while not FINISHED:
            poll_messages()
            monitor_continue()
            time.sleep(2)

        cleaned_json = clean_json_text(response_buffer)
        try:
            page_json = json.loads(cleaned_json)
        except json.JSONDecodeError:
            print(f"Warning: JSON invalid for {pdf_name}, saving raw cleaned text only.")
            page_json = cleaned_json

        compiled_json.append(page_json)

    # ---------------- End timer ----------------
    # Inside your base PDF processing loop, after you finish processing all pages:
    end_time = datetime.now()
    elapsed_seconds = (end_time - current_time).total_seconds()
    elapsed_minutes = elapsed_seconds / 60

    # --- Print timing info to console ---
    print("\n--- Processing finished ---")
    print(f"Started: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Ended:   {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Elapsed Time: {elapsed_minutes:.2f} minutes ({elapsed_seconds:.0f} seconds)")

    # --- Save timing info to separate JSON file ---
    timer_data = {
        "base_pdf_folder": base_folder,
        "started_at": current_time.strftime('%Y-%m-%d %H:%M:%S'),
        "ended_at": end_time.strftime('%Y-%m-%d %H:%M:%S'),
        "elapsed_minutes": round(elapsed_minutes, 2),
        "elapsed_seconds": int(elapsed_seconds)
    }

    timestamp_str = end_time.strftime("%Y-%m-%d_%H-%M-%S")
    timer_file_name = f"{base_folder}_processing_time_{timestamp_str}.json"
    timer_file_path = os.path.join(processing_time_folder, timer_file_name)

    with open(timer_file_path, "w", encoding="utf-8") as f:
        json.dump(timer_data, f, indent=2)

    print(f"Processing time JSON saved -> {timer_file_path}")

    # Save compiled JSON for this base PDF
    base_output_folder = os.path.join(OUTPUT_ROOT, base_folder)
    os.makedirs(base_output_folder, exist_ok=True)
    timestamp = end_time.strftime("%Y-%m-%d_%H-%M-%S")
    output_file = os.path.join(base_output_folder, f"{base_folder}_compiled_{timestamp}.json")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(compiled_json, f, indent=2)

    print(f"\nCompiled JSON saved -> {output_file}")