# --- FIX FOR PYTHON 3.12+ / BCRYPT ISSUES ---
from sqlalchemy.orm.attributes import flag_modified # Critical for updating JSON
import ai_service # Importing your new separate file
import bcrypt
# Patching bcrypt to prevent the "72 bytes" or "attribute error" crash
bcrypt.__about__ = type("about", (object,), {"__version__": bcrypt.__version__})
# --------------------------------------------

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from typing import List

# Ensure you have these files in your folder
from db import SessionLocal, engine 
import models
import schemas

# Create database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Patient Portal API")

# --- CORS SETTINGS (Allows HTML to talk to Backend) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- PASSWORD SECURITY ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

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

# --- AUTH ENDPOINTS ---

@app.post("/users/", response_model=schemas.UserRead)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    # 1. Check if email exists
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # 2. Hash password
    hashed_pwd = get_password_hash(user.password)
    
    # 3. Force Role to PATIENT (Security Rule)
    # Note: To make an Admin/Doctor, you must manually edit the DB for now.
    new_user = models.User(
        email=user.email,
        hashed_password=hashed_pwd,
        role=models.UserRole.PATIENT, 
        is_2fa_enabled=False,
        has_signed_baa=False
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.post("/login", response_model=schemas.UserRead)
def login(user_credentials: schemas.UserLogin, db: Session = Depends(get_db)):
    # 1. Find user
    user = db.query(models.User).filter(models.User.email == user_credentials.email).first()
    
    # 2. Verify Password
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    if not verify_password(user_credentials.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    return user

# --- DATA ENDPOINTS ---

@app.get("/users/", response_model=List[schemas.UserRead])
def read_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    users = db.query(models.User).offset(skip).limit(limit).all()
    return users

@app.post("/users/{user_id}/profile/", response_model=schemas.ProfileRead)
def create_or_update_profile(
    user_id: int, 
    profile: schemas.ProfileCreate, 
    db: Session = Depends(get_db)
):
    # 1. Check if the user exists
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    # 2. Check if a profile ALREADY exists for this user
    db_profile = db.query(models.Profile).filter(models.Profile.user_id == user_id).first()

    if db_profile:
        # --- UPDATE EXISTING ---
        # We loop through the data sent from frontend and update the DB object
        for key, value in profile.dict().items():
            setattr(db_profile, key, value)
    else:
        # --- CREATE NEW ---
        db_profile = models.Profile(**profile.dict(), user_id=user_id)
        db.add(db_profile)
    
    # 3. Save changes
    db.commit()
    db.refresh(db_profile)
    
    return db_profile




#######################
# --- CHAT ENDPOINT ---

@app.post("/chat/")
def chat_with_doctor(request: schemas.ChatRequest, db: Session = Depends(get_db)):
    # 1. Fetch Chat History from DB using session_id
    # We use session_id so a user can have multiple different chat logs over time
    history_record = db.query(models.ChatHistory).filter(
        models.ChatHistory.session_id == request.session_id
    ).first()

    # 2. If no history exists, create a new record
    if not history_record:
        messages = [] # Empty list
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
        # Load existing messages (Make sure it's a list)
        messages = history_record.messages if history_record.messages else []

    # 3. Call the AI Service (The Separate File)
    # We pass the OLD history + the NEW message
    ai_response_text = ai_service.get_ai_response(messages, request.message)

    # 4. Update the Database
    # Append User Message
    messages.append({"sender": "patient", "text": request.message})
    # Append AI Message
    messages.append({"sender": "ai", "text": ai_response_text})

    # 5. Save Changes
    # IMPORTANT: SQLAlchemy doesn't always detect changes inside a JSON list. 
    # We explicitly tell it "this column changed".
    history_record.messages = messages
    flag_modified(history_record, "messages")
    
    db.commit()

    return {"response": ai_response_text}