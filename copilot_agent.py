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

conversation_id = None
watermark = None
response_buffer = ""
last_activity_time = time.time()
continue_attempts = 0
MAX_CONTINUE = 20
FINISHED = False
first_response_received = False


OUTPUT_ROOT = r"D:\Projects\GitHub\tpcpp_copilot_agent\test_output"
processing_time_folder = r"D:\Projects\TPCPP\Processing Time"

os.makedirs(processing_time_folder, exist_ok=True)

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
    # Remove line comments starting with //
    text_no_comments = re.sub(r'//.*', '', raw_text)
    # Remove any leading/trailing whitespace
    text_no_comments = text_no_comments.strip()
    # Optional: remove code fences ```json or ``` markers
    text_no_comments = re.sub(r'```json|```', '', text_no_comments)
    return text_no_comments

def save_response(pdf_name):
    global response_buffer

    # Extract case ID from PDF name
    match = re.match(r'([A-Za-z0-9]+-\d+)', pdf_name)
    case_id = match.group(1) if match else pdf_name

    # Create folder based on case ID
    pdf_folder = os.path.join(OUTPUT_ROOT, case_id)
    os.makedirs(pdf_folder, exist_ok=True)

    # Clean the response buffer
    cleaned_json = clean_json_text(response_buffer)

    # Optionally validate JSON before saving
    try:
        json_object = json.loads(cleaned_json)
        # Reformat nicely with indentation
        cleaned_json = json.dumps(json_object, indent=2)
    except json.JSONDecodeError:
        print("Warning: JSON may be incomplete or invalid. Saving raw cleaned text.")

    # Create filename with timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    file_name = f"{case_id}_{timestamp}.json"
    output_path = os.path.join(pdf_folder, file_name)

    # Save the cleaned JSON
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(cleaned_json)

    print(f"\nFull response saved -> {output_path}")

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

os.makedirs(OUTPUT_ROOT, exist_ok=True)

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

    save_response(pdf_name)

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

    print(f"Processing time JSON saved -> {timer_file_path}")