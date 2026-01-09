from google import genai
from google.genai import types
import os
import time

from dotenv import load_dotenv
load_dotenv()

API_KEY = os.getenv("gemini_api_key")

client = genai.Client(api_key=API_KEY)

# --- SYSTEM INSTRUCTIONS ---
SYSTEM_PROMPT = """
You are an advanced Medical AI Assistant for a Patient Portal. 
Your goal is to gather information from the patient to prepare a summary for the real doctor.

RULES:
1. Be empathetic, professional, and clear.
2. When a user describes symptoms, ask 1-2 relevant follow-up questions.
3. DO NOT provide a medical diagnosis. Instead, say "This sounds like something the doctor should review."
4. If the user types 'SUMMARIZE', you must stop chatting and output a STRICT JSON summary.
"""

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
            chat_history.append(types.Content(
                role=role,
                parts=[types.Part.from_text(text=msg["text"])]
            ))

    # Step B: Create Chat Session
    chat = client.chats.create(
        model="gemini-2.5-flash",
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.7,
        ),
        history=chat_history
    )
    
    # Step C: Send Message
    try:
        response = chat.send_message(new_user_message)
        return response.text
    except Exception as e:
        return f"I'm having trouble connecting right now. Error: {str(e)}"

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
                            mime_type=upload_result.mime_type
                        ),
                        types.Part.from_text(text=prompt)
                    ]
                )
            ]
        )
        
        return response.text

    except Exception as e:
        print(f"Transcription Error: {e}")
        return f"Error processing audio: {str(e)}"