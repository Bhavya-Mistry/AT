# backend/security.py
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
import os
from dotenv import load_dotenv
from fastapi.security import OAuth2PasswordBearer
from fastapi import Depends, HTTPException, status
import schemas
from passlib.context import CryptContext
from models import UserRole

load_dotenv()

# We will read this from your .env file later, but this is your secret key used to sign tokens.
# NEVER share this key.
SECRET_KEY = os.getenv("SECRET_KEY", "super_secret_temporary_key_for_dev_12345")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # Tokens expire in 7 days

# This tells FastAPI where our login route is, which enables the Swagger UI Auth button
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})

    # Create the secure JWT token
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def get_current_user(token: str = Depends(oauth2_scheme)):
    """
    This is our 'Bouncer'. It intercepts the request, grabs the token from the
    Authorization header, decodes it, and returns the user's data.
    If the token is fake or expired, it kicks them out (401 Unauthorized).
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # Decode the token using our secret key
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: int = payload.get("user_id")
        email: str = payload.get("email")
        role: str = payload.get("role")

        if user_id is None or email is None:
            raise credentials_exception

        # We pack the decoded data into the schema we made earlier
        # token_data = schemas.TokenData(user_id=user_id, email=email)
        token_data = schemas.TokenData(user_id=user_id, email=email, role=role)

    except JWTError:
        raise credentials_exception

    return token_data


pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def get_password_hash(password):
    return pwd_context.hash(password)


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_current_doctor(current_user: schemas.TokenData = Depends(get_current_user)):
    """
    VIP Bouncer: First checks if the user is logged in,
    then checks if they have the 'DOCTOR' role.
    """
    if current_user.role != UserRole.DOCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action. Doctors only.",
        )
    return current_user
