from db import SessionLocal
import models
from passlib.context import CryptContext

# 1. Setup Password Hashing
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
def get_hash(password):
    return pwd_context.hash(password)

# 2. Connect to DB
db = SessionLocal()

# 3. Create Admin Data
admin_email = "admin@gmail.com"
admin_pass = "Admin@123"

# Check if exists first
existing = db.query(models.User).filter(models.User.email == admin_email).first()

if not existing:
    admin_user = models.User(
        email=admin_email,
        hashed_password=get_hash(admin_pass),
        role=models.UserRole.ADMIN,  # <--- THIS MAKES THEM ADMIN
        is_2fa_enabled=True,
        has_signed_baa=True
    )
    db.add(admin_user)
    db.commit()
    print(f"✅ Success! Admin created: {admin_email} / {admin_pass}")
else:
    print("⚠️  Admin user already exists.")

db.close()