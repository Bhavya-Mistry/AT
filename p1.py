'''Patient Management AI Portal 

 

1. Project Overview 

Mission: Portal for patients to interact with doctor/ Medical team remotely. 

Target Audience: Patients 

Core AI Features:  

Audio Transcription 

Adequate Response generation for patient 

Smart query suggestion (for patients) {optional} 

Summary Generation (For doctor) 

Medicine/Medical Test recommendation (for doctor) 

OCR Scanning 

Formatted PDF Generation (text to formatted markdown) 

Flag generation 

2. System Architecture 

This section explains how the components interact. Use a diagram here 	to show the flow from the user's microphone to the final PDF. 

 

Frontend: HTML-CSS / React.js 

Backend: Flask, FastAPI  

LLM: Gemini 

DB: MongoDB 

 

 

 

3. Data Flow: 

User signups via google or email OTP. 

User chats with LLM and inputs the data (editable) in text, voice or image format. 

LLM analyzes the text, asks follow-up questions to the patient, maintains conversational memory and transforms the final conversation into a structured medical summary (Symptoms, History, Risks) and flags the record if critical symptoms are detected. 

The Doctor accesses the Admin Dashboard to see a prioritized list of patients, reviews the AI summary, listens to original audio (if needed), and types the final diagnosis/prescription. 

A pdf report is generated for the patient to download. 

 

3. Data Structure:  

User Metadata (Relational/Structured) 

Profile:  

Profile Pic 

Full Name 

Contact No. 

Address 

Blood Group 

 

Medical Status: 

Current Status: Mild, Critical, Past Record 

Vector & Media Data (Unstructured) 

Conversational: 

AI chat history  

 

Multimedia: Images: 

Images (X-rays, prescriptions) 

Audio provided by user 

4. Python Modules For each task: 

OCR: Paddle OCR/ Tesseract 

Data to PDF: markdown-pdf (not fixed yet) 

Speech to Text: AI4Bharat / Wisper AI 

Login/Sign up: OAuth2 (FastAPI) 

OTP: smtplib 

Google Auth: google-auth-oauthlib 

API Calls: FastAPI 

 

5. Web Pages: 

Login/Sign Up with consent form (Common) 

 

User: 

Home Page (Chat Screen) 

Side Bar (Managing files) {pdf, images, prescriptions received from Doc, User Account} 

 Account/Profile Page 

 

DOC/Admin: 

Admin Dashboard Page (Table of patients, active patient queries & their review sub-section) 

Patient Specific Page (detailed page) 



'''
