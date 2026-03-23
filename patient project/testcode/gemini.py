import google.generativeai as genai
import os

# --- CONFIGURATION ---
# 1. Setup your API Key
API_KEY = "AIzaSyCVUM7zcLXSmcAN0zvC0nZAqS-_a5FMI-I"  # <--- PASTE KEY HERE
genai.configure(api_key=API_KEY)

# 2. Define the "Brain" (Model Settings)
generation_config = {
    "temperature": 0.7,        # 0.7 = Creative but focused. 0.2 = Very precise/robotic.
    "top_p": 1,
    "top_k": 1,
    "max_output_tokens": 2048,
}

# 3. The "Persona" (Prompt Engineering)
# This is where we tell Gemini exactly how to behave based on your project requirements.
SYSTEM_PROMPT = """
You are an advanced Medical AI Assistant for a Patient Portal. 
Your goal is to gather information from the patient to prepare a summary for the real doctor.

RULES:
1. Be empathetic, professional, and clear.
2. When a user describes symptoms, ask 1-2 relevant follow-up questions (e.g., "How long have you felt this?", "Is the pain sharp or dull?").
3. DO NOT provide a medical diagnosis (e.g., "You have cancer"). Instead, say "This sounds like something the doctor should review."
4. If the user types 'SUMMARIZE', you must stop chatting and output a STRICT JSON summary of the session.

JSON FORMAT for 'SUMMARIZE':
{
  "patient_symptoms": ["List of symptoms"],
  "duration": "Time duration mentioned",
  "severity_flag": "Mild/Critical",
  "suggested_specialist": "General/Cardio/Dermatologist/etc"
}
"""

model = genai.GenerativeModel(
    model_name="gemini-2.5-flash", # Or "gemini-pro"
    generation_config=generation_config,
    system_instruction=SYSTEM_PROMPT
)

def start_medical_chat():
    print("----------------------------------------------------")
    print("👨‍⚕️ AI Medical Assistant (Test Mode)")
    print("----------------------------------------------------")
    print("Type your symptoms. Type 'quit' to exit. Type 'SUMMARIZE' to generate report.")
    print("----------------------------------------------------")

    # Start a chat session (maintains history/memory)
    chat_session = model.start_chat(history=[])

    while True:
        # 1. Get User Input
        user_input = input("\n👤 Patient: ")
        
        if user_input.lower() in ['quit', 'exit']:
            print("Exiting...")
            break

        # 2. Send to Gemini
        try:
            response = chat_session.send_message(user_input)
            
            # 3. Print AI Response
            print(f"🤖 AI Doctor: {response.text}")
            
            # If we just generated a summary, end the chat
            if "patient_symptoms" in response.text and "severity_flag" in response.text:
                print("\n[System] Summary generated. Conversation ended.")
                break
                
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    start_medical_chat()