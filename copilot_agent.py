import requests
import json
import time
import os
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


def start_conversation():
    global conversation_id

    try:
        res = requests.post(
            f"{BASE_URL}/conversations",
            headers={"Authorization": f"Bearer {SECRET}"}
        )

        res.raise_for_status()

        data = res.json()

        conversation_id = data["conversationId"]

        print("Conversation started:", conversation_id)

    except Exception as e:
        print("Conversation start failed:", e)
        raise


def send_message(text, attachment_url=None):

    try:

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

        requests.post(
            url,
            headers={
                "Authorization": f"Bearer {SECRET}",
                "Content-Type": "application/json"
            },
            json=payload
        )

    except Exception as e:
        print("Send message error:", e)


def save_response():
    global response_buffer

    try:

        with open("copilot_response.txt", "w", encoding="utf-8") as f:
            f.write(response_buffer)

        print("\nFull response saved -> copilot_response.txt")

    except Exception as e:
        print("Save error:", e)


def poll_messages():

    global watermark
    global response_buffer
    global last_activity_time
    global FINISHED

    try:

        url = f"{BASE_URL}/conversations/{conversation_id}/activities"

        if watermark:
            url += f"?watermark={watermark}"

        res = requests.get(
            url,
            headers={"Authorization": f"Bearer {SECRET}"}
        )

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

            print("\n--- Copilot Response ---\n")
            print(text)
            print("\n------------------------\n")

            response_buffer += text + "\n"

            last_activity_time = time.time()

            if "Parsing Completed..." in text:

                print("\nFinal completion message detected.")

                save_response()

                FINISHED = True

                return

    except Exception as e:
        print("Polling error:", e)


def monitor_continue():

    global continue_attempts
    global last_activity_time

    try:

        idle = time.time() - last_activity_time

        if idle > 10 and continue_attempts < MAX_CONTINUE:

            continue_attempts += 1

            print("Sending Continue", continue_attempts)

            send_message("Continue")

            last_activity_time = time.time()

        if continue_attempts >= MAX_CONTINUE:

            print("Max Continue attempts reached")

            save_response()

            exit()

    except Exception as e:
        print("Monitor error:", e)


# ---------------- MAIN ----------------

# GitHub repo info
username = "kntrcnd"
repo = "tpcpp_copilot_agent"
branch = "main"
folder_path = "pdf/test"  # folder inside repo

# Start Copilot conversation
start_conversation()

# Get list of files in GitHub folder dynamically
api_url = f"https://api.github.com/repos/{username}/{repo}/contents/{folder_path}?ref={branch}"
response = requests.get(api_url)
response.raise_for_status()
files = response.json()

# Filter only PDFs and generate raw URLs
pdf_urls = [
    f"https://raw.githubusercontent.com/{username}/{repo}/{branch}/{folder_path}/{quote(f['name'])}"
    for f in files
    if f["name"].lower().endswith(".pdf")
]

if not pdf_urls:
    raise Exception("No PDFs found in GitHub folder.")

print(f"Found {len(pdf_urls)} PDF(s) to process.")

# Loop through each PDF and send to Copilot
for pdf_url in pdf_urls:
    print(f"\nSending PDF: {pdf_url}")

    send_message(
        "Extract this PDF into structured JSON. Return ONLY JSON. End with 'Parsing completed!'",
        pdf_url
    )

    FINISHED = False  # reset for each PDF
    continue_attempts = 0
    last_activity_time = time.time()

    while not FINISHED:
        poll_messages()
        monitor_continue()
        time.sleep(2)