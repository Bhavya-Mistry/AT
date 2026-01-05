import google.generativeai as genai
import os

# --- CONFIGURATION ---
# ideally, use os.getenv("GEMINI_API_KEY") for security
API_KEY = "AIzaSyCVUM7zcLXSmcAN0zvC0nZAqS-_a5FMI-I" 
genai.configure(api_key=API_KEY)

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

# --- INITIALIZE MODEL ---
# We use 1.5-flash (standard fast model). 2.5 does not exist yet.
model = genai.GenerativeModel(
    model_name="gemini-2.5-flash", 
    system_instruction=SYSTEM_PROMPT
)

def get_ai_response(db_history: list, new_user_message: str) -> str:
    """
    1. Converts Database History -> Gemini History Format
    2. Sends message to AI
    3. Returns AI text response
    """
    
    # Step A: Convert DB JSON format to Gemini format
    # DB Format:     [{ "sender": "patient", "text": "hi" }, { "sender": "ai", "text": "hello" }]
    # Gemini Format: [{ "role": "user", "parts": ["hi"] },   { "role": "model", "parts": ["hello"] }]
    gemini_history = []
    
    for msg in db_history:
        role = "user" if msg.get("sender") == "patient" else "model"
        # We only add valid text messages to history
        if msg.get("text"): 
            gemini_history.append({"role": role, "parts": [msg["text"]]})

    # Step B: Start Chat
    chat = model.start_chat(history=gemini_history)
    
    # Step C: Send Message & Handle Errors
    try:
        response = chat.send_message(new_user_message)
        return response.text
    except Exception as e:
        return f"I'm having trouble connecting right now. Error: {str(e)}"