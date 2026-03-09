# backend/routers/user.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

import models
import schemas
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
