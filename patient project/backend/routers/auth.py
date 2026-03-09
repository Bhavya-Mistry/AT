# backend/routers/auth.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi.security import OAuth2PasswordRequestForm

import models
import schemas
from db import get_db
from security import get_password_hash, verify_password, create_access_token

# Create a router instance
router = APIRouter(
    tags=["Authentication"]  # This organizes your Swagger UI nicely
)


@router.post("/users/", response_model=schemas.UserRead)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
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
