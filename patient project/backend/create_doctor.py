from db import SessionLocal
import models
from passlib.context import CryptContext

# 1. Setup Password Hashing
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

# 2. Connect to DB
db = SessionLocal()

# 3. Create Doctor Credentials
doctor_email = "doctor@gmail.com"
doctor_pass = "Doctor@123"

# Check if exists first to avoid duplicates
existing = db.query(models.User).filter(models.User.email == doctor_email).first()

if not existing:
    doctor_user = models.User(
        email=doctor_email,
        hashed_password=pwd_context.hash(doctor_pass),
        role=models.UserRole.DOCTOR,  # <--- ASSIGNS DOCTOR ROLE
        is_2fa_enabled=True,
        has_signed_baa=True
    )
    db.add(doctor_user)
    db.commit()
    print(f"✅ Success! Doctor created: {doctor_email}")
else:
    print("⚠️ Doctor user already exists.")

db.close()