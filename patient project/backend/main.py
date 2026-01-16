# --- FIX FOR PYTHON 3.12+ / BCRYPT ISSUES ---
from sqlalchemy.orm.attributes import flag_modified 
import ai_service 
import bcrypt
# Patching bcrypt
bcrypt.__about__ = type("about", (object,), {"__version__": bcrypt.__version__})
# --------------------------------------------
from fastapi.staticfiles import StaticFiles
import drive_service 
import pdf_generation_service
import uuid 
import json
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Form 
import shutil
import os
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, joinedload
from passlib.context import CryptContext
from typing import List
from fastapi.responses import StreamingResponse

from db import SessionLocal, engine 
import models
import schemas

# Create database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Patient Portal API")

# --- CORS SETTINGS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- PASSWORD SECURITY ---
pwd_context = CryptContext(
    schemes=["argon2"],
    deprecated="auto"
)

os.makedirs("uploaded_files", exist_ok=True)
app.mount("/static", StaticFiles(directory="uploaded_files"), name="static")

def get_password_hash(password):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- UTILITY: CLEAN JSON ---
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

# --- AUTH ENDPOINTS ---

@app.post("/users/", response_model=schemas.UserRead)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_pwd = get_password_hash(user.password)
    
    new_user = models.User(
        email=user.email,
        hashed_password=hashed_pwd,
        role=models.UserRole.PATIENT, 
        has_signed_baa=user.has_signed_baa,
        is_policy_accepted=user.is_policy_accepted
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.post("/login", response_model=schemas.UserRead)
def login(user_credentials: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == user_credentials.email).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    if not verify_password(user_credentials.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    return user

@app.post("/users/{user_id}/profile/", response_model=schemas.ProfileRead)
def create_or_update_profile(
    user_id: int, 
    profile: schemas.ProfileCreate, 
    db: Session = Depends(get_db)
):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    db_profile = db.query(models.Profile).filter(models.Profile.user_id == user_id).first()

    if db_profile:
        for key, value in profile.dict().items():
            setattr(db_profile, key, value)
    else:
        db_profile = models.Profile(**profile.dict(), user_id=user_id)
        db.add(db_profile)
    
    db.commit()
    db.refresh(db_profile)
    
    return db_profile

# --- CHAT ENDPOINT ---

@app.post("/chat/")
def chat_with_doctor(request: schemas.ChatRequest, db: Session = Depends(get_db)):
    history_record = db.query(models.ChatHistory).filter(
        models.ChatHistory.session_id == request.session_id
    ).first()

    if not history_record:
        messages = [] 
        new_record = models.ChatHistory(
            patient_id=request.user_id,
            session_id=request.session_id,
            messages=messages
        )
        db.add(new_record)
        db.commit()
        db.refresh(new_record)
        history_record = new_record
    else:
        messages = history_record.messages if history_record.messages else []

    # Call AI
    ai_response_text = ai_service.get_ai_response(messages, request.message)

    messages.append({"sender": "patient", "text": request.message})
    messages.append({"sender": "ai", "text": ai_response_text})

    # Check for Summary (and Priority Score)
    is_summary_request = "SUMMARIZE" in request.message.upper() or "SUMMARY" in request.message.upper()
    
    if is_summary_request:
        summary_json = clean_ai_json(ai_response_text)
        if summary_json:
            history_record.summary = summary_json
            flag_modified(history_record, "summary")

    history_record.messages = messages
    flag_modified(history_record, "messages")
    
    db.commit()

    return {"response": ai_response_text}


# --- DOCTOR DASHBOARD & SMART TRIAGE ---

@app.get("/doctor/patients/{patient_id}/summaries", response_model=List[schemas.ChatHistoryRead])
def get_patient_summaries(patient_id: int, db: Session = Depends(get_db)):
    """
    Fetches chat sessions and SORTS them by priority score (High to Low).
    """
    sessions = db.query(models.ChatHistory).filter(
        models.ChatHistory.patient_id == patient_id
    ).all()

    # Smart Triage Sort: 
    # If summary exists and has 'priority_score', use it. Else default to 0.
    def get_priority(session):
        if session.summary and isinstance(session.summary, dict):
            return session.summary.get('priority_score', 0)
        return 0

    # Sort descending (High priority first)
    sessions.sort(key=get_priority, reverse=True)
    
    return sessions


@app.post("/doctor/prescribe/")
def create_prescription(request: schemas.PrescriptionRequest, db: Session = Depends(get_db)):
    """
    The 'Digital Prescription' Loop:
    1. Generates PDF from summary + notes.
    2. Uploads to 'Drive' (simulated).
    3. Saves to Patient's 'My Files'.
    4. Schedules Follow-up (Simulated via Chat Message).
    """
    # 1. Fetch Chat Data
    history_record = db.query(models.ChatHistory).filter(
        models.ChatHistory.session_id == request.session_id
    ).first()
    
    if not history_record:
        raise HTTPException(status_code=404, detail="Session not found")

    patient = db.query(models.User).filter(models.User.id == history_record.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    patient_name = "Patient"
    if patient.profile:
        patient_name = patient.profile.full_name

    # 2. Generate PDF
    filename = f"Prescription_{request.session_id}_{uuid.uuid4().hex[:6]}.pdf"
    
    # UPDATE THIS FUNCTION CALL:
    file_path = pdf_generation_service.generate_medical_report(
        patient_name=patient_name,
        date_str=datetime.now().strftime("%Y-%m-%d"),
        summary_json=history_record.summary,
        doctor_notes=request.doctor_notes,
        filename=filename,
        follow_up_days=request.follow_up_days  # <--- Pass the new value here
    )
    # 3. Upload to Drive
    drive_data = drive_service.upload_to_drive(file_path, filename, "application/pdf")

    # 4. Save to 'My Files' (MedicalMedia)
    # NOTE: We now construct a LOCAL PROXY LINK instead of using the drive link
    new_media = models.MedicalMedia(
        patient_id=patient.id,
        file_name=f"Rx: {filename}",
        file_type="pdf",
        drive_file_id=drive_data['file_id'], 
        drive_view_link="", # Leave blank for now, or set a placeholder
        transcript=request.doctor_notes
    )
    db.add(new_media)
    db.commit() # Commit to generate the ID
    
    # NOW update the link with the real ID
    new_media.drive_view_link = f"http://127.0.0.1:8000/media/view/{new_media.id}"
    db.commit()

    # 5. Follow-up Scheduler (Injecting Message)
    follow_up_msg = (
        f"*** AUTOMATED SYSTEM MESSAGE ***\n"
        f"Dr. Smith has issued a prescription. It is now available in your 'My Files' tab.\n"
        f"A follow-up check-in has been scheduled for {request.follow_up_days} days from now."
    )
    
    messages = history_record.messages if history_record.messages else []
    messages.append({"sender": "ai", "text": follow_up_msg})
    
    history_record.messages = messages
    flag_modified(history_record, "messages")

    db.commit()
    db.refresh(new_media)

    return {"message": "Prescription generated and sent to patient", "file_url": new_media.drive_view_link}


@app.get("/patients/")
def get_all_patients(db: Session = Depends(get_db)):
    patients = db.query(models.User).options(joinedload(models.User.profile)).filter(
        models.User.role == models.UserRole.PATIENT
    ).all()
    return patients


# --- AUDIO TRANSCRIPTION ENDPOINT ---

@app.post("/transcribe/")
async def transcribe_audio_endpoint(
    file: UploadFile = File(...), 
    user_id: int = Form(...),
    db: Session = Depends(get_db)
):
    file_ext = file.filename.split('.')[-1]
    unique_name = f"audio_{uuid.uuid4()}.{file_ext}"
    temp_path = f"temp_{unique_name}"
    
    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        drive_data = drive_service.upload_to_drive(temp_path, unique_name, file.content_type)
        transcription_text = ai_service.transcribe_audio(temp_path)
        
        if os.path.exists(temp_path):
            os.remove(temp_path)

        new_media = models.MedicalMedia(
        patient_id=user_id,
        file_name="Voice Note - " + unique_name[:8],
        file_type="audio",
        drive_file_id=drive_data['file_id'],
        drive_view_link="", # Placeholder
        transcript=transcription_text
        )
        db.add(new_media)
        db.commit()

        # Update with Proxy Link
        new_media.drive_view_link = f"http://127.0.0.1:8000/media/view/{new_media.id}"
        db.commit()
            
        return {
            "transcript": transcription_text,
            "media_id": new_media.id,
            "file_url": new_media.drive_view_link
        }

    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(status_code=500, detail=str(e))
    
# In main.py

@app.get("/users/{user_id}/media/", response_model=List[schemas.MediaRead])
def get_user_media(user_id: int, db: Session = Depends(get_db)):
    """
    Fetches all medical media for a specific patient.
    Matches the frontend route: /users/{id}/media/
    """
    files = db.query(models.MedicalMedia).filter(
        models.MedicalMedia.patient_id == user_id
    ).order_by(models.MedicalMedia.created_at.desc()).all()
    
    return files

@app.get("/users/{user_id}/chats/", response_model=List[schemas.ChatHistoryRead])
def get_patient_chat_sessions(user_id: int, db: Session = Depends(get_db)):
    """
    Fetches all chat sessions for a specific patient.
    Used to display a 'History' sidebar so they can resume a conversation.
    """
    sessions = db.query(models.ChatHistory).filter(
        models.ChatHistory.patient_id == user_id
    ).order_by(models.ChatHistory.created_at.desc()).all()
    
    return sessions


@app.delete("/media/{media_id}")
def delete_media(media_id: int, db: Session = Depends(get_db)):
    media_item = db.query(models.MedicalMedia).filter(models.MedicalMedia.id == media_id).first()
    
    if not media_item:
        raise HTTPException(status_code=404, detail="File not found")

    # Call Drive Service to delete from Cloud
    if media_item.drive_file_id and media_item.drive_file_id != "local_error":
        drive_service.delete_file_from_drive(media_item.drive_file_id)

    db.delete(media_item)
    db.commit()
    return {"detail": "File deleted successfully"}

@app.get("/media/view/{media_id}")
def view_media_proxy(media_id: int, db: Session = Depends(get_db)):
    """
    Secure Proxy: Fetches file from Google Drive (Server-to-Server)
    and streams it to the client.
    """
    media = db.query(models.MedicalMedia).filter(models.MedicalMedia.id == media_id).first()
    if not media:
        raise HTTPException(status_code=404, detail="File not found")

    # Get the file stream from Drive Service
    file_stream = drive_service.get_file_stream(media.drive_file_id)
    
    if not file_stream:
        raise HTTPException(status_code=500, detail="Could not retrieve file from Cloud")

    # Determine Content-Type
    mime_type = "application/pdf" # Default
    if media.file_type == "audio": mime_type = "audio/webm"
    elif media.file_type == "image": mime_type = "image/jpeg"

    # Return as a stream
    return StreamingResponse(file_stream, media_type=mime_type)


# [main.py] - Add this near the other media endpoints

@app.post("/media/upload/")
async def upload_generic_media(
    file: UploadFile = File(...), 
    user_id: int = Form(...),
    db: Session = Depends(get_db)
):
    """
    Handles generic file uploads (Images, PDFs) from the 'Upload Record' button.
    Uploads to Google Drive and saves reference in DB.
    """
    # 1. Create a temporary file to hold the upload
    file_ext = file.filename.split('.')[-1]
    unique_name = f"upload_{uuid.uuid4()}.{file_ext}"
    temp_path = f"temp_{unique_name}"
    
    try:
        # Save upload to local temp file
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # 2. Upload to Google Drive using our new Service
        # Determine MIME type based on extension
        mime_type = file.content_type
        drive_data = drive_service.upload_to_drive(temp_path, unique_name, mime_type)
        
        # 3. Clean up local temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)

        if not drive_data:
            raise HTTPException(status_code=500, detail="Failed to upload to Cloud Storage")

        # 4. Save to Database
        new_media = models.MedicalMedia(
            patient_id=user_id,
            file_name=file.filename, # Keep original name for display
            file_type="image" if "image" in mime_type else "document",
            drive_file_id=drive_data['file_id'],
            drive_view_link="", # Placeholder
            transcript="User Uploaded Record"
        )
        
        db.add(new_media)
        db.commit()
        db.refresh(new_media)
        
        # 5. Generate Proxy Link
        new_media.drive_view_link = f"http://127.0.0.1:8000/media/view/{new_media.id}"
        db.commit()
            
        return {
            "id": new_media.id,
            "file_url": new_media.drive_view_link,
            "message": "Upload successful"
        }

    except Exception as e:
        # Cleanup on error
        if os.path.exists(temp_path):
            os.remove(temp_path)
        print(f"Upload Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))