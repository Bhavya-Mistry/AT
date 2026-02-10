from google import genai
from google.genai import types
import os
import time
import json

from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("gemini_api_key")

client = genai.Client(api_key=API_KEY)

# --- SYSTEM INSTRUCTIONS ---
# Updated to include Priority Score for Triage
# [ai_service.py]

SYSTEM_PROMPT = """
You are an advanced Medical AI Assistant. 
Your goal is to gather information from the patient to prepare a summary for the doctor.

RULES:
1. Be empathetic and professional.
2. Ask 1-2 relevant follow-up questions to clarify symptoms.
3. DO NOT provide a medical diagnosis.
4. If the user types 'SUMMARIZE', output a STRICT JSON summary.

IMPORTANT JSON RULES:
- The JSON must be FLAT (no nested objects).
- You MUST include a 'priority_score' (integer 1-10).
- You MUST strictly use ONLY these specific keys, filling missing data with "N/A":
  {
    "chief_complaint": "Main reason for visit",
    "symptoms": "List of symptoms",
    "duration": "How long they have had it",
    "severity": "Pain scale or intensity",
    "aggravating_factors": "What makes it worse",
    "alleviating_factors": "What makes it better",
    "medications": "Current meds",
    "allergies": "Known allergies",
    "past_medical_history": "Previous conditions",
    "priority_score": 1,
    "summary_note": "Brief AI conclusion"
  }
"""


def analyze_medical_image(file_path: str) -> str:
    # Upload file using your existing client
    upload = client.files.upload(file=file_path)

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part.from_uri(
                        file_uri=upload.uri, mime_type=upload.mime_type
                    ),
                    types.Part.from_text(
                        text="Extract the text from this medical report/prescription. Summarize key findings."
                    ),
                ],
            )
        ],
    )
    return response.text


def get_ai_response(db_history: list, new_user_message: str) -> str:
    """
    1. Converts Database History -> New SDK History Format
    2. Sends message to AI
    3. Returns AI text response
    """

    # Step A: Convert DB History to New SDK Format
    # The new SDK uses 'role' and 'parts' inside a Content object
    chat_history = []

    for msg in db_history:
        role = "user" if msg.get("sender") == "patient" else "model"
        if msg.get("text"):
            chat_history.append(
                types.Content(role=role, parts=[types.Part.from_text(text=msg["text"])])
            )

    # Step B: Create Chat Session
    chat = client.chats.create(
        model="gemini-2.5-flash",
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.7,
        ),
        history=chat_history,
    )

    # Step C: Send Message
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = chat.send_message(new_user_message)
            return response.text
        except Exception as e:
            # Check if it's a 503 error (Overloaded)
            if "503" in str(e) or "overloaded" in str(e).lower():
                if attempt < max_retries - 1:
                    time.sleep(2)  # Wait 2 seconds before trying again
                    continue
            return f"Error: System is currently busy. Please try again in a moment. ({str(e)})"


def transcribe_audio(file_path: str) -> str:
    """
    Uploads audio to Gemini (New SDK) and returns the transcription.
    """
    try:
        print(f"Uploading {file_path} to Gemini...")

        # 1. Upload the file using the new Client
        upload_result = client.files.upload(file=file_path)

        # 2. Wait for processing
        while upload_result.state.name == "PROCESSING":
            print("Processing audio...")
            time.sleep(1)
            # Refresh file status
            upload_result = client.files.get(name=upload_result.name)

        if upload_result.state.name == "FAILED":
            return "Audio processing failed by Gemini."

        print("Audio ready. Generating transcript...")

        # 3. Generate Content (Using Audio + Prompt)
        prompt = "Listen to this audio. Transcribe exactly what is said in Hindi, but write it using the English alphabet (Hinglish/Roman Script). Example: 'Tum kaise ho?'"

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_uri(
                            file_uri=upload_result.uri,
                            mime_type=upload_result.mime_type,
                        ),
                        types.Part.from_text(text=prompt),
                    ],
                )
            ],
        )

        return response.text

    except Exception as e:
        print(f"Transcription Error: {e}")
        return f"Error processing audio: {str(e)}"
