# backend/routers/user.py
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session, joinedload
from typing import List
import shutil
import os
import uuid

import models
import schemas
import drive_service  # <-- Add this import
from db import get_db
from security import get_current_user

# The prefix "/users" means every route in here automatically starts with /users
router = APIRouter(prefix="/users", tags=["Users & Profiles"])


@router.post("/me/profile/", response_model=schemas.ProfileRead)
def create_or_update_profile(
    profile: schemas.ProfileCreate,
    db: Session = Depends(get_db),
    current_user: schemas.TokenData = Depends(get_current_user),
):
    user_id = current_user.user_id

    db_user = db.query(models.User).filter(models.User.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    db_profile = (
        db.query(models.Profile).filter(models.Profile.user_id == user_id).first()
    )

    if db_profile:
        for key, value in profile.dict().items():
            setattr(db_profile, key, value)
    else:
        db_profile = models.Profile(**profile.dict(), user_id=user_id)
        db.add(db_profile)

    db.commit()
    db.refresh(db_profile)

    return db_profile


@router.get("/me/media/", response_model=List[schemas.MediaRead])
def get_user_media(
    db: Session = Depends(get_db),
    current_user: schemas.TokenData = Depends(get_current_user),
):
    files = (
        db.query(models.MedicalMedia)
        .filter(models.MedicalMedia.patient_id == current_user.user_id)
        .order_by(models.MedicalMedia.created_at.desc())
        .all()
    )
    return files


@router.get("/me/chats/", response_model=List[schemas.ChatHistoryRead])
def get_patient_chat_sessions(
    db: Session = Depends(get_db),
    current_user: schemas.TokenData = Depends(get_current_user),
):
    sessions = (
        db.query(models.ChatHistory)
        .filter(models.ChatHistory.patient_id == current_user.user_id)
        .order_by(models.ChatHistory.created_at.desc())
        .all()
    )
    return sessions


@router.get("/me/profile/", response_model=schemas.ProfileRead)
def get_user_profile(
    db: Session = Depends(get_db),
    current_user: schemas.TokenData = Depends(get_current_user),
):
    """Fetches the current user's profile data."""
    db_profile = (
        db.query(models.Profile)
        .filter(models.Profile.user_id == current_user.user_id)
        .first()
    )

    if not db_profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    return db_profile


@router.post("/me/profile-pic/")
async def upload_profile_picture(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: schemas.TokenData = Depends(get_current_user),
):
    user_id = current_user.user_id

    # 1. Validate file type
    if file.content_type not in ["image/jpeg", "image/png", "image/webp"]:
        raise HTTPException(
            status_code=400, detail="Only image files (JPEG, PNG, WEBP) are allowed"
        )

    # 2. Setup temporary local file
    file_ext = file.filename.split(".")[-1]
    unique_name = f"profile_pic_{user_id}_{uuid.uuid4().hex[:8]}.{file_ext}"
    temp_path = f"temp_{unique_name}"

    try:
        # Save file locally
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 3. Upload to Google Drive
        drive_data = drive_service.upload_to_drive(
            temp_path, unique_name, file.content_type
        )

        if not drive_data:
            raise HTTPException(
                status_code=500, detail="Failed to upload image to Cloud Storage"
            )

        # 4. Fetch the user's profile
        db_profile = (
            db.query(models.Profile).filter(models.Profile.user_id == user_id).first()
        )

        # If the user doesn't have a profile yet, create a blank one
        if not db_profile:
            db_profile = models.Profile(
                user_id=user_id,
                full_name="New User",
                contact_no="",
                address="",
                blood_group="",
                current_status=models.MedicalStatus.MILD,
            )
            db.add(db_profile)
            db.commit()
            db.refresh(db_profile)

        # Optional cleanup: Delete the old profile picture from Drive to save space
        if db_profile.profile_pic_drive_id:
            try:
                drive_service.delete_file_from_drive(db_profile.profile_pic_drive_id)
            except Exception as e:
                print(f"Note: Could not delete old profile picture: {e}")

        # 5. Update the database with the new Drive ID
        db_profile.profile_pic_drive_id = drive_data["file_id"]
        db.commit()

        return {
            "message": "Profile picture updated successfully",
            "profile_pic_drive_id": drive_data["file_id"],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        # 6. Always clean up the local temporary file
        if os.path.exists(temp_path):
            os.remove(temp_path)


@router.get("/doctors/")
def get_all_doctors(
    db: Session = Depends(get_db),
    current_user: schemas.TokenData = Depends(get_current_user),
):
    """Returns all doctors with their profile names — used by patients when booking appointments."""
    doctors = (
        db.query(models.User)
        .filter(models.User.role == models.UserRole.DOCTOR)
        .options(joinedload(models.User.profile))
        .all()
    )
    return [
        {
            "id": d.id,
            "email": d.email,
            "profile": {
                "full_name": d.profile.full_name if d.profile else None,
            }
            if d.profile
            else None,
        }
        for d in doctors
    ]
