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
You are an advanced Medical AI Triage Assistant. 
Your goal is to gather information from the patient to prepare a highly structured clinical summary for the doctor.

RULES:
1. Be empathetic, professional, and concise.
2. Ask relevant follow-up questions to clarify symptoms and gather maximum data as possible for doctor.
3. DO NOT provide a medical diagnosis or prescribe treatments.
4. CONVERSATION LANGUAGE: You MUST respond in the EXACT SAME language the user is speaking but write it using the English alphabet (Hinglish/Roman Script). Example: 'Tum kaise ho?' 'Tame kem cho?' 
   - If the user types in Hindi (Roman or Devanagari script), reply in Hindi.
   - If they type in Gujarati, Spanish, etc., reply in that same language.
   - Match their tone naturally to make them comfortable.
5. If the user types 'SUMMARIZE' or asks for a summary, output a STRICT JSON summary in ENGLISH language ONLY.

IMPORTANT JSON RULES (FOR DOCTOR REVIEW):
- NO MATTER WHAT LANGUAGE THE CHAT WAS IN, THE FINAL JSON OUTPUT MUST BE IN PROFESSIONAL MEDICAL ENGLISH. 
- The JSON must be FLAT (no nested objects or arrays, use strings).
- You MUST include a 'priority_score' (integer 1-10, where 10 is a life-threatening emergency).
- You MUST strictly use ONLY these specific keys, filling missing data with "None" or "Not reported":
  {
    "chief_complaint": "Main reason for visit (concise)",
    "symptoms": "Detailed list of current symptoms",
    "duration": "How long the symptoms have been present",
    "severity": "Pain scale or intensity (e.g., 7/10)",
    "aggravating_factors": "What makes it worse",
    "alleviating_factors": "What makes it better",
    "medications": "Current medications",
    "allergies": "Known allergies",
    "past_medical_history": "Previous or chronic conditions",
    "vital_signs_mentioned": "Any user-reported metrics (e.g., fever of 102F, BP 140/90)",
    "red_flags": "List any alarming symptoms (e.g., chest pain, loss of consciousness) or state 'None identified'",
    "patient_language": "The language the patient used in this chat (e.g., Hindi (Roman), English)",
    "recommended_action": "Short triage recommendation (e.g., Routine review, Urgent evaluation, ER advised)",
    "priority_score": 1,
    "summary_note": "A 1-2 sentence clinical summary for the physician"
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
    Uploads audio to Gemini and returns the transcription.
    """
    try:
        print(f"Uploading {file_path} to Gemini...")

        # 1. EXPLICITLY TELL GEMINI IT IS AN AUDIO FILE to prevent the 500 Crash
        upload_config = None
        if file_path.endswith(".webm"):
            upload_config = types.UploadFileConfig(mime_type="audio/webm")

        # Upload the file with the config
        upload_result = client.files.upload(file=file_path, config=upload_config)

        # 2. Wait for processing (Audio takes a few seconds)
        while upload_result.state.name == "PROCESSING":
            print("Processing audio...")
            time.sleep(1)
            # Refresh file status
            upload_result = client.files.get(name=upload_result.name)

        if upload_result.state.name == "FAILED":
            return "Audio processing failed by Gemini."

        print("Audio ready. Generating transcript...")

        # 3. Generate Content
        prompt = """
        You are a highly accurate medical transcription AI. 
        Listen to the provided audio. 
        
        1. Transcribe the spoken text accurately. 
        2. If the user is speaking in a regional language (like Hindi, Gujarati, or Spanish), write it using the English alphabet (Hinglish/Roman Script). Example: 'Tum kaise ho?' 'Tame kem cho?' 
        3. If the user is speaking English, just transcribe exactly what they said.
        4. Fix any obvious medical spelling errors, but do not change the underlying meaning of the patient's symptoms.
        5. Output ONLY the final transcribed/translated text. Do not include markdown formatting, introductory conversational text, or quotes.
        """

        # The new SDK allows us to pass the File object directly into the contents array!
        response = client.models.generate_content(
            model="gemini-2.5-flash", contents=[upload_result, prompt]
        )

        return response.text

    except Exception as e:
        print(f"Transcription Error: {e}")
        return f"Error processing audio: {str(e)}"


def clean_ai_json(text_response: str):
    """
    Removes markdown code blocks (```json ... ```) if Gemini adds them.
    Returns a Python Dict or None if parsing fails.
    """
    clean_text = text_response.strip()
    if clean_text.startswith("```json"):
        clean_text = clean_text[7:]
    if clean_text.startswith("```"):
        clean_text = clean_text[3:]
    if clean_text.endswith("```"):
        clean_text = clean_text[:-3]

    try:
        return json.loads(clean_text)
    except json.JSONDecodeError:
        return None
