# backend/routers/user.py
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session, joinedload
from typing import List
import shutil
import os
import uuid

import models
import schemas
import drive_service
from db import get_db
from security import get_current_user

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
    db_profile = (
        db.query(models.Profile)
        .filter(models.Profile.user_id == current_user.user_id)
        .first()
    )
    if not db_profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return db_profile


@router.get("/me/profile-pic/")
def get_my_profile_pic(
    db: Session = Depends(get_db),
    current_user: schemas.TokenData = Depends(get_current_user),
):
    """
    Streams the CURRENT USER's own profile picture.
    Always fetches the drive_id from the database — never accepts it as a param.
    This prevents any cross-user photo leakage.
    """
    db_profile = (
        db.query(models.Profile)
        .filter(models.Profile.user_id == current_user.user_id)
        .first()
    )

    if not db_profile or not db_profile.profile_pic_drive_id:
        raise HTTPException(status_code=404, detail="No profile picture set")

    file_stream = drive_service.get_file_stream(db_profile.profile_pic_drive_id)
    if not file_stream:
        raise HTTPException(
            status_code=404, detail="Could not retrieve profile picture from storage"
        )

    return StreamingResponse(
        file_stream,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-cache"},  # Don't cache — always serve fresh
    )


@router.post("/me/profile-pic/")
async def upload_profile_picture(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: schemas.TokenData = Depends(get_current_user),
):
    user_id = current_user.user_id

    if file.content_type not in ["image/jpeg", "image/png", "image/webp"]:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, WEBP allowed")

    file_ext = file.filename.split(".")[-1]
    unique_name = f"profile_pic_{user_id}_{uuid.uuid4().hex[:8]}.{file_ext}"
    temp_path = f"temp_{unique_name}"

    try:
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        drive_data = drive_service.upload_to_drive(
            temp_path, unique_name, file.content_type
        )
        if not drive_data:
            raise HTTPException(
                status_code=500, detail="Failed to upload to Cloud Storage"
            )

        db_profile = (
            db.query(models.Profile).filter(models.Profile.user_id == user_id).first()
        )

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

        # Delete old picture from Drive to save space
        if db_profile.profile_pic_drive_id:
            try:
                drive_service.delete_file_from_drive(db_profile.profile_pic_drive_id)
            except Exception as e:
                print(f"Note: Could not delete old profile picture: {e}")

        db_profile.profile_pic_drive_id = drive_data["file_id"]
        db.commit()

        return {
            "message": "Profile picture updated successfully",
            "profile_pic_drive_id": drive_data["file_id"],
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@router.get("/{user_id}/profile-pic/")
def get_user_profile_pic(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: schemas.TokenData = Depends(get_current_user),
):
    """
    Streams a specific user's profile picture.
    Only the user themselves OR a doctor can access it.
    """
    # Security: only allow access to own pic or doctor accessing a patient's pic
    is_own = current_user.user_id == user_id
    is_doctor = str(current_user.role) in ("doctor", "UserRole.DOCTOR")

    if not is_own and not is_doctor:
        raise HTTPException(status_code=403, detail="Not authorized")

    db_profile = (
        db.query(models.Profile).filter(models.Profile.user_id == user_id).first()
    )

    if not db_profile or not db_profile.profile_pic_drive_id:
        raise HTTPException(status_code=404, detail="No profile picture set")

    file_stream = drive_service.get_file_stream(db_profile.profile_pic_drive_id)
    if not file_stream:
        raise HTTPException(
            status_code=404, detail="Could not retrieve profile picture"
        )

    return StreamingResponse(
        file_stream,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/doctors/")
def get_all_doctors(
    db: Session = Depends(get_db),
    current_user: schemas.TokenData = Depends(get_current_user),
):
    """Returns all doctors with names — used by patients when booking appointments."""
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
            "profile": {"full_name": d.profile.full_name if d.profile else None}
            if d.profile
            else None,
        }
        for d in doctors
    ]
