from pydantic import BaseModel, EmailStr
from typing import Optional, List, Dict, Any
from models import UserRole, MedicalStatus
from datetime import datetime

# --- PROFILE SCHEMAS ---
class ProfileBase(BaseModel):
    full_name: str
    contact_no: str
    address: str
    blood_group: str
    current_status: MedicalStatus
    profile_pic_drive_id: Optional[str] = None

class ProfileCreate(ProfileBase):
    pass

class ProfileRead(ProfileBase):
    id: int
    user_id: int

    class Config:
        from_attributes = True

# --- USER SCHEMAS ---
class UserCreate(BaseModel):
    email: str
    password: str
    is_policy_accepted: bool = False
    has_signed_baa: bool = False

class UserRead(BaseModel):
    id: int
    email: str
    role: UserRole
    profile: Optional[ProfileRead] = None

    class Config:
        from_attributes = True

class UserLogin(BaseModel):
    email: EmailStr
    password: str

# --- MEDIA & CHAT SCHEMAS ---
class MediaRead(BaseModel):
    id: int
    file_name: str
    file_type: str
    drive_view_link: Optional[str] = None
    transcript: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class ChatHistoryRead(BaseModel):
    session_id: str
    messages: List[dict]
    summary: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- CHAT INPUT ---
class ChatRequest(BaseModel):
    user_id: int
    session_id: str
    message: str

# --- DOCTOR PRESCRIPTION INPUT (NEW) ---
class PrescriptionRequest(BaseModel):
    session_id: str
    doctor_notes: str
    follow_up_days: int = 3 # Default to 3 days