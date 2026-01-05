# --- FIX FOR PYTHON 3.12+ / BCRYPT ISSUES ---
import bcrypt
# This line "patches" the library to prevent the crash you saw earlier
bcrypt.__about__ = type("about", (object,), {"__version__": bcrypt.__version__})
# --------------------------------------------

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware  # <--- Added CORS for safety
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from typing import List

# Import your database connection logic
from db import SessionLocal, engine 

import models
import schemas

# 1. Create tables (just in case reset_db wasn't run, though reset_db is better)
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Patient Portal API")

# --- ENABLE CORS (Allows your HTML file to talk to the backend) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Setup Password Hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password):
    return pwd_context.hash(password)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- USER ENDPOINTS ---

@app.post("/users/", response_model=schemas.UserRead)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    # Check if user already exists
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Hash the password
    hashed_pwd = get_password_hash(user.password)
    
    # Create new user
    new_user = models.User(
        email=user.email,
        hashed_password=hashed_pwd,
        role=user.role,
        is_2fa_enabled=user.is_2fa_enabled,
        has_signed_baa=user.has_signed_baa
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.get("/users/", response_model=List[schemas.UserRead])
def read_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    users = db.query(models.User).offset(skip).limit(limit).all()
    return users

# --- PROFILE ENDPOINTS ---

@app.post("/users/{user_id}/profile/", response_model=schemas.ProfileRead)
def create_profile_for_user(
    user_id: int, 
    profile: schemas.ProfileCreate, 
    db: Session = Depends(get_db)
):
    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
        
    new_profile = models.Profile(**profile.dict(), user_id=user_id)
    
    db.add(new_profile)
    db.commit()
    db.refresh(new_profile)
    return new_profile