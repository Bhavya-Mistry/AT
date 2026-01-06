from google import genai
from google.genai import types

# REPLACE THIS with your actual key
API_KEY = "api key" 

client = genai.Client(api_key=API_KEY)

def transcribe_audio_gemini(audio_path):
    print(f"Uploading {audio_path} to Gemini...")
    
    # 1. Read the audio file
    # Gemini can process mp3, wav, aac, etc. directly.
    
    audio_file = client.files.upload(file=audio_path)

    print("Processing audio... (Listening & Converting)")

    # 2. Send Audio + Prompt to Gemini
    # We ask it to do both tasks: Transcribe AND Transliterate
    prompt = "Listen to this audio. Transcribe exactly what is said in Hindi, but write it using the English alphabet (Hinglish/Roman Script). Example: 'Tum kaise ho?'"
    
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part.from_uri(
                        file_uri=audio_file.uri,
                        mime_type=audio_file.mime_type),
                    types.Part.from_text(text=prompt),
                ]),
        ],
    )
    
    return response.text

# --- Test ---
audio_file = "path"  # Also works with .mp3 and .m4a!

try:
    result = transcribe_audio_gemini(audio_file)
    print("\n---------------------------------")
    print(f"Gemini Output: {result}")
    print("---------------------------------")
except Exception as e:
    print(f"Error: {e}")