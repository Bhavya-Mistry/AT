# backend/routers/auth.py
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordRequestForm

import models
import schemas
from db import get_db
from security import get_password_hash, verify_password, create_access_token

from google.oauth2 import id_token
from google.auth.transport import requests
from dotenv import load_dotenv
import os

import email_service

# Create a router instance
router = APIRouter(
    tags=["Authentication"]  # This organizes your Swagger UI nicely
)
load_dotenv()
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")


@router.post("/users/", response_model=schemas.UserRead)
def create_user(
    user: schemas.UserCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    db_user = db.query(models.User).filter(models.User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_pwd = get_password_hash(user.password)

    new_user = models.User(
        email=user.email,
        hashed_password=hashed_pwd,
        role=models.UserRole.PATIENT,
        has_signed_baa=user.has_signed_baa,  # <--- THIS IS CRITICAL
        is_policy_accepted=user.is_policy_accepted,  # <--- THIS IS CRITICAL
        is_2fa_enabled=False,  # We can default this to False until you build actual 2FA SMS logic
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    patient_name = new_user.email.split("@")[0]
    background_tasks.add_task(
        email_service.send_welcome_email, new_user.email, patient_name
    )
    return new_user


@router.post("/login", response_model=schemas.Token)
def login(
    user_credentials: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = (
        db.query(models.User)
        .filter(models.User.email == user_credentials.username)
        .first()
    )
    if not user or not verify_password(user_credentials.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    access_token = create_access_token(
        data={"user_id": user.id, "email": user.email, "role": user.role}
    )

    return {"access_token": access_token, "token_type": "bearer"}


@router.post("/google", response_model=schemas.Token)
def google_login(
    request: schemas.GoogleAuthRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    try:
        # 1. Verify the token with Google
        idinfo = id_token.verify_oauth2_token(
            request.token, requests.Request(), GOOGLE_CLIENT_ID
        )

        # 2. Extract user info
        email = idinfo.get("email")
        if not email:
            raise HTTPException(
                status_code=400, detail="Google token did not contain an email"
            )

        # 3. Check if user already exists in your DB
        user = db.query(models.User).filter(models.User.email == email).first()

        # 4. If they don't exist, create an account automatically!
        if not user:
            user = models.User(
                email=email,
                hashed_password="",  # No password needed since they use Google
                role=models.UserRole.PATIENT,
                has_signed_baa=True,  # Assuming OAuth implies consent, or handle on frontend
                is_policy_accepted=True,
                is_2fa_enabled=False,
            )
            db.add(user)
            db.commit()
            db.refresh(user)

            # Optional: Auto-create a blank Profile with their Google Name
            google_name = idinfo.get("name", "New User")
            new_profile = models.Profile(
                user_id=user.id,
                full_name=google_name,
                contact_no="",
                address="",
                blood_group="",
                current_status=models.MedicalStatus.MILD,
            )
            db.add(new_profile)
            db.commit()

            background_tasks.add_task(
                email_service.send_welcome_email, user.email, google_name
            )

        # 5. Generate YOUR local JWT token so the rest of the app works normally
        access_token = create_access_token(
            data={"user_id": user.id, "email": user.email, "role": user.role}
        )

        return {"access_token": access_token, "token_type": "bearer"}

    except ValueError:
        # Invalid token
        raise HTTPException(status_code=401, detail="Invalid Google token")
