from pydantic import BaseModel, EmailStr
from typing import Optional, List
from models import UserRole, MedicalStatus

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
    email: EmailStr
    
    # 1. REMOVED default value. Now you MUST type a password.
    password: str 
    
    # 2. REMOVED default. Now you MUST select a role (patient/doctor).
    role: UserRole 
    
    # 3. These can stay False by default, or remove '= False' to force entry
    has_signed_baa: bool = False
    is_2fa_enabled: bool = False

class UserRead(BaseModel):
    id: int
    email: str
    role: UserRole
    has_signed_baa: bool
    is_2fa_enabled: bool
    # Returns the nested profile automatically if it exists
    profile: Optional[ProfileRead] = None

    class Config:
        from_attributes = True

# --- MEDIA & CHAT SCHEMAS ---
class MediaRead(BaseModel):
    id: int
    file_type: str
    drive_file_id: str
    transcript: Optional[str] = None

    class Config:
        from_attributes = True

class ChatHistoryRead(BaseModel):
    session_id: str
    messages: List[dict]

    class Config:
        from_attributes = True