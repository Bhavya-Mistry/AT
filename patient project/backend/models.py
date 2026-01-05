from sqlalchemy import Column, Integer, String, ForeignKey, Enum, Boolean, Text, JSON
from sqlalchemy.orm import relationship
from db import Base
import enum
 
# --- ENUMS (Ensures strict data validation) ---
class UserRole(str, enum.Enum):
    PATIENT = "patient"
    DOCTOR = "doctor"
    ADMIN = "admin"
 
class MedicalStatus(str, enum.Enum):
    MILD = "mild"
    CRITICAL = "critical"
    PAST_RECORD = "past_record"
 
# --- USERS TABLE ---
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    # --- NEW COLUMN ---
    hashed_password = Column(String) 
    # ------------------
 
    role = Column(Enum(UserRole), default=UserRole.PATIENT)
    is_2fa_enabled = Column(Boolean, default=False)
    has_signed_baa = Column(Boolean, default=False)
    profile = relationship("Profile", back_populates="owner", uselist=False)
    media = relationship("MedicalMedia", back_populates="patient")
    chat_history = relationship("ChatHistory", back_populates="patient")
     
# --- PROFILES TABLE ---
class Profile(Base):
    __tablename__ = "profiles"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    full_name = Column(String)
    contact_no = Column(String)
    address = Column(Text)
    blood_group = Column(String)
    profile_pic_drive_id = Column(String, nullable=True)
   
    current_status = Column(Enum(MedicalStatus), default=MedicalStatus.MILD)
    owner = relationship("User", back_populates="profile")
 
# --- MEDICAL MEDIA TABLE ---
class MedicalMedia(Base):
    __tablename__ = "medical_media"
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("users.id"))
    file_type = Column(String)  # 'x-ray', 'prescription', 'audio'
    drive_file_id = Column(String)  
    transcript = Column(Text, nullable=True)
   
    patient = relationship("User", back_populates="media")
 
# --- CHAT HISTORY TABLE ---
class ChatHistory(Base):
    __tablename__ = "chat_history"
    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("users.id"))
    session_id = Column(String, index=True) # Added index for faster search
    messages = Column(JSON)
 
    patient = relationship("User", back_populates="chat_history")