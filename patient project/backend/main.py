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

# from passlib.context import CryptContext
from typing import List
from fastapi.responses import StreamingResponse

from db import SessionLocal, engine, get_db
import models
import schemas


from fastapi.security import OAuth2PasswordRequestForm
from security import create_access_token

from security import get_current_user

from routers import auth, chat, user, doctor, media, appointment

# Create database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Patient Portal API")

app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(user.router)
app.include_router(doctor.router)
app.include_router(media.router)
app.include_router(appointment.router)

# --- CORS SETTINGS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- PASSWORD SECURITY ---


os.makedirs("uploaded_files", exist_ok=True)
app.mount("/static", StaticFiles(directory="uploaded_files"), name="static")
